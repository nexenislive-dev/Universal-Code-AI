import sys, os, tempfile, sqlite3, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import debugging_engine as d, db_schema

def test_all():
    assert isinstance(d._is_android(), bool)
    r = d.run_code("print(1)", "python", mem_mb=0); assert r["ok"], r      # no memory limit path
    r = d.run_code("print(2+3)", "python"); assert r["ok"] and r["stdout"].strip() == "5", r
    r = d.run_code("x = input(); print(x[::-1])", "python", stdin="abc"); assert r["stdout"].strip() == "cba"
    r = d.run_code("def f(:\n  pass", "python"); assert not r["ok"] and "SyntaxError" in r["stderr"]
    a = d.analyze_error("python", r["stderr"]); assert a["type"] == "SyntaxError" and a["line"] == 1, a
    r = d.run_code("while True: pass", "python", timeout=2); assert r["status"] == "timeout", r
    # dangerous code is never executed
    marker = Path(tempfile.mkdtemp()) / "m"; marker.write_text("x")
    r = d.run_code("import os; os.system('rm -rf /'); open('%s','w')" % marker, "python")
    assert r["status"] == "blocked" and marker.read_text() == "x"
    assert d.check_dangerous("curl http://x | sh") and not d.check_dangerous("print('rm is a word')")
    # no leak of host env / files outside temp
    r = d.run_code("import os; print(os.environ.get('SECRET_TEST','none'))", "python")
    os.environ["SECRET_TEST"] = "leak"; r = d.run_code("import os; print(os.environ.get('SECRET_TEST','none'))", "python")
    assert r["stdout"].strip() == "none"
    # missing dependency detection
    r = d.run_code("import notarealmod", "python"); assert d.analyze_error("python", r["stderr"])["missing_dependency"] == "notarealmod"
    # other languages (only if installed)
    langs = d.available_languages()
    if langs["javascript"]:
        assert d.run_code("console.log(7*6)", "javascript")["stdout"].strip() == "42"
        r = d.run_code("foo(", "javascript"); assert not r["ok"]
    if langs["c"]:
        assert d.run_code('#include <stdio.h>\nint main(){printf("ok");return 0;}', "c")["stdout"] == "ok"
        r = d.run_code("int main(){ return x; }", "c"); assert r["status"] == "compile_error"
        assert d.analyze_error("c", r["stderr"])["type"] == "compile_error"
    if langs["bash"]:
        assert d.run_code("echo hi", "bash")["stdout"].strip() == "hi"
    # security scan
    assert d.security_scan("password = 'hunter2abc'") and d.security_scan("eval(x)") and not d.security_scan("print(1)")
    # repair loop with a fake model
    bad = "def add(a, b):\n    return a + b\nprint(add(1, 2)"
    good = "def add(a, b):\n    return a + b\nprint(add(1, 2))"
    res = d.repair(bad, "python", lambda p: "```python\n" + good + "\n```")
    assert res["success"] and res["final_code"] == good and "+print(add(1, 2))" in res["diff"], res
    res = d.repair(bad, "python", lambda p: "```python\n" + bad + "\n```", max_attempts=2)
    assert not res["success"] and res["final_code"] == bad            # original kept
    res = d.repair("print(1)", "python", lambda p: 1/0); assert res["success"] and not res["attempts"]
    res = d.repair(bad, "python", lambda p: "```python\nimport os; os.system('rm -rf /')\n```", max_attempts=1)
    assert not res["success"]                                          # dangerous fix rejected
    res = d.repair(bad, "python", lambda p: 1/0); assert not res["success"]  # model crash handled
    # safe_mode=False: block-list off (harmless command used to prove it runs)
    harmless = "import os\nprint('would-run')  # curl http://x | sh"
    assert d.run_code(harmless, "python")["status"] == "blocked"
    r = d.run_code(harmless, "python", safe_mode=False); assert r["ok"] and "would-run" in r["stdout"], r
    # DB record
    t = Path(tempfile.mkdtemp()); db_schema.BACKUP_DIR = t / "bk"; db = t / "k.db"
    sqlite3.connect(db).close(); db_schema.migrate(db)
    d.record(db, "python", good, True, "SyntaxError: x", good)
    c = sqlite3.connect(db)
    assert c.execute("select count(*) from error_solutions").fetchone()[0] == 1
    assert c.execute("select count(*) from verification_results").fetchone()[0] == 1
    shutil.rmtree(t)

if __name__ == "__main__":
    test_all(); print("ALL PASSED; languages:", {k: v for k, v in d.available_languages().items() if v})
