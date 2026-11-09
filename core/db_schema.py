"""Extended SQLite schema (12 modules), safe migration, backup and restore.

Existing tables (knowledge, documents, learning_stats, system_state) are
NEVER altered or dropped. Only new tables are added with IF NOT EXISTS.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, BASE_DIR

BACKUP_DIR = BASE_DIR / "backups"

NEW_TABLES = {
    "programming_languages": """CREATE TABLE IF NOT EXISTS programming_languages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
        file_ext TEXT, run_cmd TEXT, check_cmd TEXT, available INTEGER DEFAULT 0)""",
    "code_examples": """CREATE TABLE IF NOT EXISTS code_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT NOT NULL, topic TEXT,
        source TEXT, code TEXT NOT NULL, explanation TEXT, license TEXT,
        verified INTEGER DEFAULT 0, content_hash TEXT UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "documentation": """CREATE TABLE IF NOT EXISTS documentation (
        id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, title TEXT,
        source TEXT, content TEXT, license TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "knowledge_entries": """CREATE TABLE IF NOT EXISTS knowledge_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, topic TEXT,
        source TEXT, code_example TEXT, explanation TEXT, license TEXT,
        verification_status TEXT DEFAULT 'unverified',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "error_solutions": """CREATE TABLE IF NOT EXISTS error_solutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, error_pattern TEXT,
        solution TEXT, fixed_code TEXT, times_used INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "project_templates": """CREATE TABLE IF NOT EXISTS project_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, project_type TEXT,
        language TEXT, structure_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "training_datasets": """CREATE TABLE IF NOT EXISTS training_datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, path TEXT,
        num_samples INTEGER DEFAULT 0, notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "model_versions": """CREATE TABLE IF NOT EXISTS model_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, path TEXT, base_model TEXT,
        quantization TEXT, is_active INTEGER DEFAULT 0, eval_score REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "training_history": """CREATE TABLE IF NOT EXISTS training_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, model_version_id INTEGER,
        dataset_id INTEGER, method TEXT, status TEXT, log TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "generated_projects": """CREATE TABLE IF NOT EXISTS generated_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, request TEXT, path TEXT,
        zip_path TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "user_feedback": """CREATE TABLE IF NOT EXISTS user_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT, request TEXT, response TEXT,
        rating INTEGER, correction TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    "verification_results": """CREATE TABLE IF NOT EXISTS verification_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, example_id INTEGER, check_type TEXT,
        passed INTEGER, output TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
}


def migrate(db_path=DB_PATH):
    """Add missing tables. Auto-backs up first. Returns list of created tables."""
    db_path = Path(db_path)
    if db_path.exists():
        backup(db_path, tag="pre-migrate")
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        before = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for ddl in NEW_TABLES.values():
            conn.execute(ddl)
        conn.commit()
        after = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return sorted(after - before)
    finally:
        conn.close()


def integrity_ok(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def backup(db_path=DB_PATH, tag="manual", keep=10):
    """Consistent online backup (sqlite backup API). Keeps last `keep` backups."""
    db_path = Path(db_path)
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = BACKUP_DIR / f"{db_path.stem}_{tag}_{stamp}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    files = sorted(BACKUP_DIR.glob(f"{db_path.stem}_*.db"))
    for old in files[:-keep]:
        old.unlink()
    return dest


def list_backups():
    return sorted(BACKUP_DIR.glob("*.db")) if BACKUP_DIR.exists() else []


def restore(backup_path, db_path=DB_PATH):
    """Restore a backup. Current DB is saved first, so nothing is lost."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    if not integrity_ok(backup_path):
        raise ValueError("Backup failed integrity check; not restored.")
    db_path = Path(db_path)
    if db_path.exists():
        backup(db_path, tag="pre-restore")
    shutil.copy2(backup_path, db_path)
    return db_path
