#!/usr/bin/env python3
"""Local web server for Universal Code AI (stdlib only, binds to 127.0.0.1).

Serves ui/index.html and a small JSON API used by the Android WebView app or a browser.
Safety: localhost only; every POST must carry header X-UCA: 1 (blocks random web pages
from calling the API); zip downloads limited to exports/.
"""
import json
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DB_PATH, BASE_DIR
from core import db_schema, debugging_engine as dbg, project_importer, project_generator
from core.local_model import LocalModel
from core.model_manager import ModelManager
from utils.helpers import detect_language

UI_DIR = ROOT / "ui"
EXPORTS = BASE_DIR / "exports"
SYSTEM = ("You are Universal Code AI, an expert programmer. Give complete, working code in fenced "
          "code blocks. Reply in the language the user writes in.")
STATE = {"safe_mode": True, "history": []}
JOBS = {}
MODEL_FN = None            # tests can override: MODEL_FN = lambda prompt: "..."


def model_fn(prompt, system=SYSTEM):
    if MODEL_FN:
        return MODEL_FN(prompt)
    r = LocalModel(timeout=900).generate(prompt, system=system, temperature=0.2, max_tokens=1800)
    if not r["success"]:
        raise RuntimeError(r.get("error", "Local model not running. Start it in Settings."))
    return r["content"]


def ensure_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    if Path(DB_PATH).exists():
        c = sqlite3.connect(str(DB_PATH))
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        c.close()
        if set(db_schema.NEW_TABLES) <= have:
            return
    db_schema.migrate(DB_PATH)


def status():
    h = LocalModel().health()
    stats = {}
    try:
        c = sqlite3.connect(str(DB_PATH))
        for t in ("generated_projects", "code_examples", "error_solutions"):
            stats[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        c.close()
    except sqlite3.Error:
        pass
    return {"model_online": bool(h.get("available")), "safe_mode": STATE["safe_mode"],
            "languages": {k: v for k, v in dbg.available_languages().items() if v}, "db": stats}


def run_job(job_id, request):
    job = JOBS[job_id]
    try:
        rep = project_generator.generate_project(request, model_fn, db_path=DB_PATH,
                                                 progress=lambda m: job["log"].append(m))
        job["report"] = project_generator.format_report(rep)
        job["zip"] = rep.get("zip")
        job["success"] = rep.get("success")
    except Exception as exc:
        job["report"] = f"FAILED: {exc}"
        job["success"] = False
    job["done"] = True


class Handler(BaseHTTPRequestHandler):
    server_version = "UCA/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "json" in ctype else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html")
            if u.path == "/api/status":
                return self._send(200, status())
            if u.path.startswith("/api/job/"):
                j = JOBS.get(u.path.rsplit("/", 1)[1])
                return self._send(200 if j else 404, j or {"error": "no such job"})
            if u.path == "/api/projects":
                c = sqlite3.connect(str(DB_PATH))
                rows = c.execute("SELECT name,request,zip_path,status,created_at FROM generated_projects ORDER BY id DESC LIMIT 50").fetchall()
                c.close()
                return self._send(200, [dict(zip(("name", "request", "zip", "status", "created"), r)) for r in rows])
            if u.path == "/api/download":
                p = Path(parse_qs(u.query).get("path", [""])[0]).resolve()
                if EXPORTS.resolve() not in p.parents or p.suffix != ".zip" or not p.is_file():
                    return self._send(403, {"error": "not allowed"})
                return self._send(200, p.read_bytes(), "application/zip")
            return self._send(404, {"error": "not found"})
        except Exception as exc:
            return self._send(500, {"error": str(exc)})

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-UCA") != "1":
            return self._send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60 * 1024 * 1024:
            return self._send(413, {"error": "too large"})
        raw = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/import":                                  # raw zip bytes
                tmp = BASE_DIR / "projects" / f"_upload_{uuid.uuid4().hex[:8]}.zip"
                tmp.parent.mkdir(exist_ok=True)
                tmp.write_bytes(raw)
                try:
                    rep, summary = project_importer.import_and_analyze(tmp, parse_qs(u.query).get("name", [None])[0])
                finally:
                    tmp.unlink(missing_ok=True)
                return self._send(200, {"summary": summary, "tree": rep["tree"], "dir": rep["root"]})
            d = json.loads(raw or b"{}")
            if u.path == "/api/chat":
                msg = str(d.get("message", "")).strip()
                if not msg:
                    return self._send(400, {"error": "empty message"})
                hist = "\n".join(f"{r}: {t}" for r, t in STATE["history"][-6:])
                reply = model_fn((hist + "\n" if hist else "") + "user: " + msg)
                STATE["history"] += [("user", msg[:1500]), ("assistant", reply[:1500])]
                return self._send(200, {"reply": reply})
            if u.path == "/api/clear":
                STATE["history"].clear()
                return self._send(200, {"ok": True})
            if u.path in ("/api/run", "/api/repair"):
                code, lang = d.get("code", ""), (d.get("language") or detect_language(d.get("code", ""))).lower()
                safe = STATE["safe_mode"]
                if u.path == "/api/run":
                    r = dbg.run_code(code, lang, d.get("stdin", ""), safe_mode=safe)
                    return self._send(200, r)
                r = dbg.repair(code, lang, model_fn, safe_mode=safe)
                return self._send(200, r)
            if u.path == "/api/safe_mode":
                STATE["safe_mode"] = bool(d.get("on", True))
                return self._send(200, {"safe_mode": STATE["safe_mode"]})
            if u.path == "/api/project":
                jid = uuid.uuid4().hex[:8]
                JOBS[jid] = {"log": [], "done": False}
                threading.Thread(target=run_job, args=(jid, str(d.get("request", ""))), daemon=True).start()
                return self._send(200, {"job": jid})
            if u.path == "/api/model/start":
                m = ModelManager(d.get("path") or None)
                return self._send(200, m.start(context=2048))
            if u.path == "/api/model/stop":
                return self._send(200, ModelManager().stop())
            if u.path == "/api/save_zip":
                src = Path(str(d.get("path", ""))).resolve()
                if EXPORTS.resolve() not in src.parents or src.suffix != ".zip" or not src.is_file():
                    return self._send(403, {"error": "not allowed"})
                for dest in (Path("/storage/emulated/0/Download"), Path.home() / "storage" / "downloads", EXPORTS):
                    if dest.is_dir():
                        try:
                            if (dest / src.name).resolve() != src:
                                shutil.copy2(src, dest / src.name)
                            return self._send(200, {"saved": str(dest / src.name)})
                        except OSError:
                            continue
                return self._send(500, {"error": "could not write to Download folder (storage permission?)"})
            if u.path == "/api/backup":
                return self._send(200, {"path": str(db_schema.backup(DB_PATH))})
            return self._send(404, {"error": "not found"})
        except Exception as exc:
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def make_server(port=8765):
    ensure_db()
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = make_server(port)
    print(f"Universal Code AI UI: http://127.0.0.1:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
