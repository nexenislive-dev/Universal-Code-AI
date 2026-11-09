import sys, tempfile, zipfile, shutil, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import project_importer as pi

def mk(tmp):
    src = tmp / "demo"; (src / "app").mkdir(parents=True); (src / "web").mkdir()
    (src / "main.py").write_text("import flask\nimport requests\nfrom app import utils\nfrom app.models import User\nif __name__ == '__main__':\n    print(utils.f())\n")
    (src / "app/__init__.py").write_text("")
    (src / "app/utils.py").write_text("from . import models\ndef f():\n    return 1\ndef todo_fn():\n    pass\ndef later():\n    raise NotImplementedError\ndef ok():\n    '''doc'''\n    return 2\n")
    (src / "app/models.py").write_text("class User:\n    pass\n")
    (src / "broken.py").write_text("def x(:\n")
    (src / "requirements.txt").write_text("flask==2.0\n")
    (src / "web/index.js").write_text("import a from './a'\nconst r = require('express')\nfunction q(){ throw new Error('not implemented') }\n")
    (src / "web/a.js").write_text("export default 1\n")
    (src / "node_modules").mkdir(); (src / "node_modules/x.js").write_text("ignored")
    return src

def test_all():
    tmp = Path(tempfile.mkdtemp()); src = mk(tmp)
    before = {str(p): hashlib.md5(p.read_bytes()).hexdigest() for p in src.rglob("*") if p.is_file()}
    rep, summary = pi.import_and_analyze(src)
    after = {str(p): hashlib.md5(p.read_bytes()).hexdigest() for p in src.rglob("*") if p.is_file()}
    assert before == after, "source was modified!"
    assert rep["languages"]["python"] == 5 and rep["languages"]["javascript"] == 2
    assert "main.py" in rep["entry_points"]
    assert "Flask (Python web)" in rep["frameworks"]
    assert rep["undeclared_python_deps"] == ["requests"], rep["undeclared_python_deps"]
    assert "app/utils.py" in rep["relationships"]["main.py"]["depends_on"]
    assert "app/models.py" in rep["relationships"]["app/utils.py"]["depends_on"]
    assert "web/a.js" in rep["relationships"]["web/index.js"]["depends_on"]
    names = {(t["file"], t.get("name")) for t in rep["incomplete_or_broken"]}
    assert ("app/utils.py", "todo_fn") in names and ("app/utils.py", "later") in names
    assert ("app/utils.py", "ok") not in names and ("app/utils.py", "f") not in names
    assert ("broken.py", "SYNTAX ERROR") in names
    assert not any("node_modules" in k for k in rep["relationships"])
    assert "express" in rep["third_party"]["javascript"]
    print(summary)
    # zip import: new folder, no overwrite
    z = tmp / "demo.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for p in src.rglob("*"):
            if p.is_file(): zf.write(p, "demo/" + str(p.relative_to(src)))
    out = tmp / "projects"
    d1 = pi.safe_extract_zip(z, projects_dir=out); d2 = pi.safe_extract_zip(z, projects_dir=out)
    assert d1 != d2 and d1.exists() and d2.exists()
    # zip-slip
    evil = tmp / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf: zf.writestr("../../escaped.txt", "x")
    try: pi.safe_extract_zip(evil, projects_dir=out); assert False
    except ValueError: pass
    assert not (tmp / "escaped.txt").exists() and not (out.parent.parent / "escaped.txt").exists()
    shutil.rmtree(tmp)

if __name__ == "__main__":
    test_all(); print("ALL PASSED")
