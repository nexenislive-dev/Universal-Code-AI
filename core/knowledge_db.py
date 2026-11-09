"""
Permanent Local Knowledge Database
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from config import DB_PATH, SUPPORTED_LANGUAGES
from utils.helpers import generate_id, hash_content, clean_code


class KnowledgeDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path), timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge (
                    id TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    code TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    tags TEXT,
                    category TEXT,
                    source TEXT,
                    verification_score REAL DEFAULT 0.5,
                    usage_count INTEGER DEFAULT 0,
                    complexity TEXT DEFAULT 'medium',
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(code_hash, language)
                )
            """)
            conn.commit()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS learning_stats (
                    language TEXT PRIMARY KEY,
                    total_examples INTEGER DEFAULT 0,
                    verified_examples INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0.0,
                    last_updated TEXT
                )
            """)
            conn.commit()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL UNIQUE,
                    topic TEXT, language TEXT DEFAULT 'general',
                    content TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            conn.commit()

            for idx in [
                "CREATE INDEX IF NOT EXISTS idx_lang ON knowledge(language)",
                "CREATE INDEX IF NOT EXISTS idx_score ON knowledge(verification_score)",
                "CREATE INDEX IF NOT EXISTS idx_hash ON knowledge(code_hash)",
            ]:
                try:
                    cur.execute(idx)
                    conn.commit()
                except Exception:
                    pass

            now = datetime.utcnow().isoformat()
            for lang in SUPPORTED_LANGUAGES:
                cur.execute(
                    "INSERT OR IGNORE INTO learning_stats (language, total_examples, verified_examples, avg_score, last_updated) VALUES (?,?,?,?,?)",
                    (lang, 0, 0, 0.0, now)
                )
            conn.commit()
        finally:
            conn.close()

    def add(self, language: str, code: str, title: str = "", description: str = "",
            tags: Optional[List[str]] = None, category: str = "example",
            source: str = "bot", score: float = 0.7, complexity: str = "medium") -> Optional[str]:
        language = language.lower().strip()
        code = clean_code(code)
        if not code or len(code) < 20:
            return None

        code_hash = hash_content(code + "|" + language)
        kid = generate_id("k_")
        now = datetime.utcnow().isoformat()

        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO knowledge
                    (id, language, title, description, code, code_hash, tags, category, source,
                     verification_score, complexity, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (kid, language, title[:200], description[:500], code, code_hash,
                      json.dumps(tags or []), category, source, score, complexity, now, now))
                conn.commit()
            self._refresh_stats(language)
            return kid
        except sqlite3.IntegrityError:
            return None

    def search(self, query: str = "", language: Optional[str] = None,
               limit: int = 8, min_score: float = 0.4) -> List[Dict]:
        with self._conn() as conn:
            sql = "SELECT * FROM knowledge WHERE verification_score >= ?"
            params: List[Any] = [min_score]
            if language:
                sql += " AND language = ?"
                params.append(language.lower())
            if query:
                sql += " AND (title LIKE ? OR description LIKE ? OR code LIKE ? OR tags LIKE ?)"
                q = f"%{query[:120]}%"
                params.extend([q, q, q, q])
            sql += " ORDER BY verification_score DESC, usage_count DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["tags"] = json.loads(d.get("tags") or "[]")
                out.append(d)
            return out

    def increment_usage(self, kid: str):
        with self._conn() as conn:
            conn.execute("UPDATE knowledge SET usage_count = usage_count + 1 WHERE id = ?", (kid,))
            conn.commit()

    def _refresh_stats(self, language: str):
        with self._conn() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN verification_score >= 0.6 THEN 1 ELSE 0 END) as verified,
                       AVG(verification_score) as avg_score
                FROM knowledge WHERE language = ?
            """, (language,)).fetchone()
            conn.execute("""
                INSERT OR REPLACE INTO learning_stats
                (language, total_examples, verified_examples, avg_score, last_updated)
                VALUES (?,?,?,?,?)
            """, (language, row["total"] or 0, row["verified"] or 0,
                  row["avg_score"] or 0.0, datetime.utcnow().isoformat()))
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            lang_stats = {r["language"]: dict(r) for r in conn.execute("SELECT * FROM learning_stats")}
            total = conn.execute("SELECT COUNT(*) as c FROM knowledge").fetchone()["c"]
            verified = conn.execute("SELECT COUNT(*) as c FROM knowledge WHERE verification_score >= 0.6").fetchone()["c"]
            avg = conn.execute("SELECT AVG(verification_score) as a FROM knowledge").fetchone()["a"] or 0.0
            covered = sum(1 for s in lang_stats.values() if s["verified_examples"] > 0)
            return {
                "total_examples": total,
                "verified_examples": verified,
                "avg_score": round(avg, 3),
                "languages_covered": covered,
                "language_stats": lang_stats
            }

    def add_document(self, source_url: str, topic: str, language: str, content: str):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""INSERT INTO documents(source_url,topic,language,content,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(source_url) DO UPDATE SET
                topic=excluded.topic, language=excluded.language, content=excluded.content, created_at=excluded.created_at""",
                (source_url, topic, language, content, now))
            row = conn.execute("SELECT id FROM documents WHERE source_url=?", (source_url,)).fetchone()
            conn.commit()
            return row["id"]

    def search_documents(self, query: str, limit: int = 5):
        terms = [x for x in query.split() if len(x) > 2][:8]
        if not terms:
            return []
        where = " OR ".join(["topic LIKE ? OR content LIKE ?" for _ in terms])
        params = []
        for term in terms:
            params.extend([f"%{term}%", f"%{term}%"])
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(f"SELECT id,source_url,topic,language,content FROM documents WHERE {where} ORDER BY id DESC LIMIT ?", params).fetchall()
            return [dict(row) for row in rows]

    def get_state(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_state(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?,?)", (key, value))
            conn.commit()

    def is_independent(self) -> bool:
        """True jab system modules/API se free ho chuka ho"""
        return self.get_state("mode", "training") == "independent"

    def set_independent(self, value: bool = True):
        self.set_state("mode", "independent" if value else "training")
