import sys, json, threading, tempfile, time, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server

def call(port, path, body=None, headers=None, raw=None):
    h = dict(headers or {})
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()

def test_all():
    tmp = Path(tempfile.mkdtemp())
    srv = server.make_server(0); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    X = {"X-UCA": "1"}
    s, b = call(port, "/"); assert s == 200 and b"Universal Code AI" in b
    s, b = call(port, "/api/status"); st = json.loads(b); assert "python" in st["languages"] and st["safe_mode"] is True
    assert call(port, "/api/run", {"code": "print(1)"})[0] == 403                    # missing header
    assert call(port, "/api/status", headers={"Host": "evil.com"})[0] == 403          # host check
    s, b = call(port, "/api/run", {"code": "print(6*7)", "language": "python"}, X); assert json.loads(b)["stdout"].strip() == "42"
    s, b = call(port, "/api/run", {"code": "import os; os.system('rm -rf /')", "language": "python"}, X); assert json.loads(b)["status"] == "blocked"
    call(port, "/api/safe_mode", {"on": False}, X); assert json.loads(call(port, "/api/status")[1])["safe_mode"] is False
    call(port, "/api/safe_mode", {"on": True}, X)
    server.MODEL_FN = lambda p: "```python\nprint('fixed')\n```" if "Fix the" in p else "Here:\n```python\nprint('hi')\n```"
    s, b = call(port, "/api/chat", {"message": "hello"}, X); assert "print('hi')" in json.loads(b)["reply"]
    s, b = call(port, "/api/repair", {"code": "print('x'", "language": "python"}, X); r = json.loads(b); assert r["success"] and "fixed" in r["final_code"]
    # project job
    plan = {"name": "demo", "files": [{"path": "main.py", "purpose": "entry"}]}
    server.MODEL_FN = lambda p: json.dumps(plan) if p.startswith("You are a software architect") else "```python\nprint('demo')\n```"
    s, b = call(port, "/api/project", {"request": "demo"}, X); job = json.loads(b)["job"]
    for _ in range(50):
        j = json.loads(call(port, "/api/job/" + job)[1])
        if j["done"]: break
        time.sleep(0.2)
    assert j["done"] and j["success"] and j["zip"], j
    s, b = call(port, "/api/download?path=" + j["zip"]); assert s == 200 and b[:2] == b"PK"
    assert call(port, "/api/download?path=/etc/passwd")[0] == 403
    s, b = call(port, "/api/save_zip", {"path": j["zip"]}, X); assert s == 200 and Path(json.loads(b)["saved"]).exists(), b
    assert call(port, "/api/save_zip", {"path": "/etc/passwd"}, X)[0] == 403
    assert any(p["name"] == "demo" for p in json.loads(call(port, "/api/projects")[1]))
    # zip import
    import zipfile, io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr("a/main.py", "print(1)\n")
    s, b = call(port, "/api/import?name=up", headers=X, raw=buf.getvalue()); assert s == 200 and "python:1" in json.loads(b)["summary"], b
    srv.shutdown()

if __name__ == "__main__":
    test_all(); print("ALL PASSED")
