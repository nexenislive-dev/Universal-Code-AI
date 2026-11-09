import sqlite3, sys, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import db_schema
from core.knowledge_db import KnowledgeDB

def test_all():
    tmp = Path(tempfile.mkdtemp())
    db_schema.BACKUP_DIR = tmp / "bk"
    p = tmp / "k.db"
    kdb = KnowledgeDB(p)                       # old schema
    kid = kdb.add("python", "print('hello world from test')", title="t", tags=[], category="x", source="s", score=0.8)
    created = db_schema.migrate(p)
    assert len(created) == 12, created
    assert KnowledgeDB(p).get_stats()["total_examples"] == 1   # old data kept
    assert db_schema.migrate(p) == []                          # idempotent
    assert db_schema.integrity_ok(p)
    b = db_schema.backup(p)
    c = sqlite3.connect(p); c.execute("DELETE FROM knowledge"); c.commit(); c.close()
    db_schema.restore(b, p)
    assert KnowledgeDB(p).get_stats()["total_examples"] == 1   # restored
    bad = tmp / "bad.db"; bad.write_bytes(b"garbage" * 100)
    try: db_schema.restore(bad, p); assert False
    except Exception: pass
    shutil.rmtree(tmp)

if __name__ == "__main__":
    test_all(); print("ALL PASSED")
