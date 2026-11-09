"""Complete project generator: request -> plan -> files -> validate -> fix -> ZIP.

The model is injected as model_fn(prompt:str)->str so it works with LocalModel,
any other backend, or a fake in tests. One model call per file keeps prompts small
(important for 1.5B-3B models). Nothing is reported as working unless a check
actually passed; files that could not be checked are labelled "unchecked".
"""
import ast
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict

from config import BASE_DIR
from core import project_importer
from core.debugging_engine import extract_code

PROJECTS_DIR = BASE_DIR / "projects"
EXPORTS_DIR = BASE_DIR / "exports"
MAX_FILES = 40

PIP_NAMES = {"yaml": "pyyaml", "PIL": "pillow", "cv2": "opencv-python", "bs4": "beautifulsoup4",
             "sklearn": "scikit-learn", "dotenv": "python-dotenv", "telebot": "pyTelegramBotAPI",
             "telegram": "python-telegram-bot", "jwt": "pyjwt", "dateutil": "python-dateutil"}

PLAN_PROMPT = """You are a software architect. Design a complete project for this request.
Reply with ONLY one JSON object, no other text:
{{"name": "short_snake_case_name", "language": "main language", "description": "one line",
 "files": [{{"path": "relative/path.ext", "purpose": "what this file contains and which other files it uses"}}]}}
Rules: at most {max_files} files; include every file needed to run (entry point, modules,
config, README, dependency file); no placeholders; relative paths only.

Request: {request}"""

FILE_PROMPT = """Project: {name} ({language}) - {description}
All files in the project:
{file_list}

Already written files (signatures):
{done}

Write the COMPLETE content of `{path}` ({purpose}).
It must be fully implemented: no TODO, no `pass`, no placeholder functions. Import only
from files listed above or from standard/real libraries. Reply with ONLY the file content
in one fenced code block."""

FIX_PROMPT = """This file `{path}` has a problem:
{problem}

Return the COMPLETE corrected file in one fenced code block, nothing else.

```
{code}
```"""


# ------------------------------------------------------------ planning
def _safe_rel(path):
    p = Path(str(path).replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts or str(p).startswith("~"):
        return None
    return p.as_posix()


def parse_plan(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("model did not return JSON")
    plan = json.loads(m.group(0))
    files, seen = [], set()
    for f in plan.get("files", []):
        rel = _safe_rel(f.get("path", "")) if isinstance(f, dict) else None
        if rel and rel not in seen:
            seen.add(rel)
            files.append({"path": rel, "purpose": str(f.get("purpose", ""))[:300]})
    if not files:
        raise ValueError("plan has no valid files")
    return {"name": re.sub(r"[^\w\-]+", "_", str(plan.get("name") or "project"))[:40] or "project",
            "language": str(plan.get("language", "")).lower(),
            "description": str(plan.get("description", ""))[:200], "files": files[:MAX_FILES]}


def plan_project(request, model_fn, retries=1):
    last = None
    for _ in range(retries + 1):
        try:
            return parse_plan(model_fn(PLAN_PROMPT.format(request=request, max_files=MAX_FILES)))
        except Exception as exc:
            last = exc
    raise ValueError(f"Could not get a valid plan: {last}")


# ---------------------------------------------------------- validation
def _run(cmd, cwd, timeout=20):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stderr or p.stdout)[-800:]
    except FileNotFoundError:
        return None, f"{cmd[0]} not installed"
    except subprocess.TimeoutExpired:
        return False, "check timed out"


def validate_file(root, rel):
    """-> (status, detail) with status in ok / error / unchecked."""
    path, ext = Path(root) / rel, Path(rel).suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return "error", "file is empty"
    try:
        if ext == ".py":
            ast.parse(text)
            return "ok", ""
        if ext in (".json",):
            json.loads(text)
            return "ok", ""
    except (SyntaxError, ValueError) as exc:
        return "error", f"{type(exc).__name__}: {exc}"
    cmds = {".js": ["node", "--check", str(path)], ".sh": ["bash", "-n", str(path)],
            ".c": ["gcc", "-fsyntax-only", str(path)], ".cpp": ["g++", "-fsyntax-only", str(path)],
            ".php": ["php", "-l", str(path)], ".rb": ["ruby", "-c", str(path)],
            ".lua": ["luac", "-p", str(path)]}
    if ext in cmds:
        ok, out = _run(cmds[ext], root)
        if ok is None:
            return "unchecked", out
        return ("ok", "") if ok else ("error", out)
    if ext in (".html", ".htm"):
        return ("ok", "") if re.search(r"<html|<body|<div|<!doctype", text, re.I) else ("error", "no HTML structure")
    return "unchecked", "no validator for this file type"


# ------------------------------------------------------------ pipeline
def _signature(root, rel, limit=12):
    try:
        lines = (Path(root) / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    keep = [l for l in lines if re.match(r"\s*(def |class |function |export |import |from |public |const |module\.exports)", l)]
    return "\n".join(keep[:limit])


def _unique_dir(base, name):
    base.mkdir(parents=True, exist_ok=True)
    d, i = base / name, 1
    while d.exists():          # never overwrite an existing project
        i += 1
        d = base / f"{name}_{i}"
    d.mkdir()
    return d


def generate_project(request, model_fn, fix_attempts=2, projects_dir=None, exports_dir=None,
                     db_path=None, progress=None):
    """Run the whole pipeline. Returns a report dict (never raises for model problems)."""
    say = progress or (lambda msg: None)
    projects_dir, exports_dir = Path(projects_dir or PROJECTS_DIR), Path(exports_dir or EXPORTS_DIR)
    report = {"request": request, "success": False, "files": {}, "issues": [], "zip": None, "dir": None}
    say("Planning architecture...")
    try:
        plan = plan_project(request, model_fn)
    except ValueError as exc:
        report["issues"].append(str(exc))
        return report
    report["plan"] = plan
    root = _unique_dir(projects_dir, plan["name"])
    report["dir"] = str(root)
    file_list = "\n".join(f"- {f['path']}: {f['purpose']}" for f in plan["files"])

    for n, f in enumerate(plan["files"], 1):
        rel = f["path"]
        say(f"Writing {rel} ({n}/{len(plan['files'])})")
        done = "\n".join(f"{p}:\n{_signature(root, p)}" for p in report["files"] if _signature(root, p))
        try:
            code = extract_code(model_fn(FILE_PROMPT.format(
                name=plan["name"], language=plan["language"], description=plan["description"],
                file_list=file_list, done=done or "(none yet)", path=rel, purpose=f["purpose"])))
        except Exception as exc:
            report["files"][rel] = {"status": "error", "detail": f"model failed: {exc}", "fixed": 0}
            report["issues"].append(f"{rel}: model failed")
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code + "\n", encoding="utf-8")
        status, detail = validate_file(root, rel)
        tries = 0
        while status == "error" and tries < fix_attempts:
            tries += 1
            say(f"Fixing {rel} (attempt {tries})")
            try:
                fixed = extract_code(model_fn(FIX_PROMPT.format(path=rel, problem=detail, code=target.read_text())))
            except Exception:
                break
            if fixed.strip() and fixed.strip() != target.read_text().strip():
                target.write_text(fixed + "\n", encoding="utf-8")
            status, detail = validate_file(root, rel)
        report["files"][rel] = {"status": status, "detail": detail, "fixed": tries}

    # cross-file checks (imports, stubs, missing deps) using the importer
    say("Checking connections between files...")
    analysis = project_importer.analyze_project(root)
    stubs = {}
    for t in analysis["incomplete_or_broken"]:
        if t.get("name") != "SYNTAX ERROR":
            stubs.setdefault(t["file"], []).append(t["name"])
    for rel, names in stubs.items():           # one completion pass per file with stubs
        say(f"Completing empty functions in {rel}")
        try:
            fixed = extract_code(model_fn(FIX_PROMPT.format(
                path=rel, problem="These functions are empty or unimplemented: " + ", ".join(names) + ". Implement them fully.",
                code=(root / rel).read_text())))
            if fixed.strip():
                old = (root / rel).read_text()
                (root / rel).write_text(fixed + "\n", encoding="utf-8")
                st, dt = validate_file(root, rel)
                if st == "error":
                    (root / rel).write_text(old, encoding="utf-8")   # keep the earlier working version
        except Exception:
            pass
    analysis = project_importer.analyze_project(root)
    for t in analysis["incomplete_or_broken"]:
        report["issues"].append(f"{t['file']}: {t.get('name', 'not implemented')} still incomplete")
    missing = [f["path"] for f in plan["files"] if not (root / f["path"]).exists()]
    report["issues"] += [f"missing file: {m}" for m in missing]

    deps = analysis["undeclared_python_deps"]
    if deps and not (root / "requirements.txt").exists():
        (root / "requirements.txt").write_text("\n".join(PIP_NAMES.get(d, d) for d in deps) + "\n")
        report["issues"].append("requirements.txt was missing; generated from imports: " + ", ".join(deps))
    for rel, v in report["files"].items():
        if v["status"] == "error":
            report["issues"].append(f"{rel}: {v['detail'][:150]}")

    # ZIP
    exports_dir.mkdir(parents=True, exist_ok=True)
    zp = exports_dir / f"{root.name}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, f"{root.name}/{p.relative_to(root).as_posix()}")
    report["zip"] = str(zp)
    counts = {s: sum(1 for v in report["files"].values() if v["status"] == s) for s in ("ok", "error", "unchecked")}
    report["counts"] = counts
    report["success"] = counts["error"] == 0 and not missing and not any("incomplete" in i for i in report["issues"])
    if db_path:
        try:
            c = sqlite3.connect(str(db_path), timeout=30)
            c.execute("INSERT INTO generated_projects(name,request,path,zip_path,status) VALUES(?,?,?,?,?)",
                      (plan["name"], request, str(root), str(zp), "ok" if report["success"] else "has_issues"))
            c.commit()
            c.close()
        except sqlite3.Error as exc:
            report["issues"].append(f"db record failed: {exc}")
    return report


def format_report(r):
    if not r.get("plan"):
        return "FAILED: " + "; ".join(r["issues"])
    c = r.get("counts", {})
    out = [f"Project: {r['plan']['name']}  ->  {r['dir']}",
           f"ZIP: {r['zip']}",
           f"Files OK: {c.get('ok', 0)} | errors: {c.get('error', 0)} | unchecked: {c.get('unchecked', 0)}",
           "Result: " + ("all checks passed" if r["success"] else "HAS ISSUES (see below)")]
    out += [f"  ! {i}" for i in r["issues"]]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# ORIGINAL ProjectGenerator (unchanged) - still used by main_cli.py and gui_app.py
# to save ```file:path blocks from model output into a project + ZIP.
# ---------------------------------------------------------------------------
FILE_MARKER = re.compile(r"```file:([^\n`]+)\n(.*?)```", re.S | re.I)

class ProjectGenerator:
    def __init__(self, projects_dir: Path):
        self.projects_dir = Path(projects_dir).resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def parse(content: str) -> Dict[str, str]:
        files = {}
        for raw_path, body in FILE_MARKER.findall(content or ""):
            path = PurePosixPath(raw_path.strip().replace('\\', '/'))
            if path.is_absolute() or not path.parts or any(p in ('..', '') for p in path.parts):
                continue
            clean = str(path)
            if clean not in ('.', ''):
                files[clean] = body.strip() + "\n"
        return files

    def save(self, content: str, name: str = "generated_project") -> Dict[str, Any]:
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_-") or "generated_project"
        files = self.parse(content)
        if not files:
            return {"success": False, "error": "Model output mein ```file:path markers nahi mile. Multi-file project format dobara request karo."}
        root = (self.projects_dir / safe_name).resolve()
        if self.projects_dir not in root.parents:
            return {"success": False, "error": "Invalid project path"}
        root.mkdir(parents=True, exist_ok=True)
        written = []
        for rel, body in files.items():
            target = (root / rel).resolve()
            if root != target and root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            written.append(rel)
        if not written:
            return {"success": False, "error": "No safe files to write"}
        archive = self.projects_dir / f"{safe_name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in written:
                zf.write(root / rel, arcname=f"{safe_name}/{rel}")
        return {"success": True, "project_dir": str(root), "zip_path": str(archive), "files": written, "file_count": len(written)}
