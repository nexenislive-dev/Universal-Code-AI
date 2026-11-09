import sys, json, tempfile, zipfile, sqlite3, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import project_generator as pg, db_schema

PLAN = {"name": "todo app!", "language": "python", "description": "todo cli",
        "files": [{"path": "main.py", "purpose": "entry, uses store.py"},
                  {"path": "store.py", "purpose": "storage"},
                  {"path": "../evil.py", "purpose": "path traversal"},
                  {"path": "data.json", "purpose": "config"}]}
FILES = {
 "main.py": "import store\nimport requests\nif __name__ == '__main__':\n    print(store.add('x'))\n",
 "store.py": "def add(x):\n    pass\n",
 "data.json": "{\"a\": 1}",
}
state = {"calls": 0, "store_fixed": False, "broken_once": False}

def fake_model(prompt):
    state["calls"] += 1
    if prompt.startswith("You are a software architect"):
        return "Sure!\n```json\n" + json.dumps(PLAN) + "\n```"
    if "These functions are empty" in prompt:                    # stub completion
        state["store_fixed"] = True
        return "```python\nITEMS = []\ndef add(x):\n    ITEMS.append(x)\n    return len(ITEMS)\n```"
    if "has a problem" in prompt and "data.json" in prompt:      # fix broken json
        return "```json\n{\"a\": 1}\n```"
    for name, code in FILES.items():
        if f"content of `{name}`" in prompt:
            if name == "data.json" and not state["broken_once"]:
                state["broken_once"] = True
                return "```json\n{a: 1,}\n```"                  # invalid on purpose
            return "```\n" + code + "\n```"
    return ""

def test_all():
    tmp = Path(tempfile.mkdtemp())
    db_schema.BACKUP_DIR = tmp / "bk"; db = tmp / "k.db"; sqlite3.connect(db).close(); db_schema.migrate(db)
    msgs = []
    r = pg.generate_project("todo app", fake_model, projects_dir=tmp / "p", exports_dir=tmp / "e",
                            db_path=db, progress=msgs.append)
    print(pg.format_report(r))
    assert r["plan"]["name"] == "todo_app_"
    assert [f["path"] for f in r["plan"]["files"]] == ["main.py", "store.py", "data.json"]   # traversal path dropped
    assert not (tmp / "evil.py").exists()
    assert r["files"]["data.json"]["status"] == "ok" and r["files"]["data.json"]["fixed"] == 1  # broken json repaired
    assert state["store_fixed"]                                       # stub got completed
    assert "ITEMS" in (Path(r["dir"]) / "store.py").read_text()
    assert (Path(r["dir"]) / "requirements.txt").read_text().strip() == "requests"
    assert r["success"] and Path(r["zip"]).exists()
    names = zipfile.ZipFile(r["zip"]).namelist(); assert any(n.endswith("main.py") for n in names)
    assert sqlite3.connect(db).execute("select status from generated_projects").fetchone()[0] == "ok"
    assert any("Writing main.py" in m for m in msgs)
    # second run never overwrites the first
    r2 = pg.generate_project("todo app", fake_model, projects_dir=tmp / "p", exports_dir=tmp / "e")
    assert r2["dir"] != r["dir"] and Path(r["dir"]).exists()
    # model gives garbage plan -> honest failure, nothing created
    r3 = pg.generate_project("x", lambda p: "no json here", projects_dir=tmp / "p3", exports_dir=tmp / "e3")
    assert not r3["success"] and "plan" in r3["issues"][0].lower() and not (tmp / "p3").exists()
    # model never fixes a broken file -> reported as error, success False
    def bad_model(p):
        if p.startswith("You are a software architect"): return json.dumps({"name": "b", "files": [{"path": "a.py", "purpose": "x"}]})
        return "```python\ndef f(:\n```"
    r4 = pg.generate_project("bad", bad_model, projects_dir=tmp / "p4", exports_dir=tmp / "e4")
    assert not r4["success"] and r4["files"]["a.py"]["status"] == "error", r4
    shutil.rmtree(tmp)

if __name__ == "__main__":
    test_all(); print("ALL PASSED")
