"""Debugging engine: sandboxed run, error analysis, security scan, model-driven repair.

HONEST LIMITS
- Sandbox = temp dir + minimal env + timeout + CPU/memory/file-size limits + a
  static block-list of dangerous commands. It is NOT kernel-level isolation
  (Android/Termux without root cannot do namespaces). Treat it as a safety net,
  not a guarantee. Network is not blocked.
- Only languages whose interpreter/compiler is installed can be run.
- Dependencies are DETECTED, never auto-installed.
"""
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import resource
except ImportError:  # non-POSIX
    resource = None

MAX_OUT = 20000

# language -> (extension, compile_cmd or None, run_cmd). {src}/{out} are filled in.
RUNNERS = {
    "python": (".py", None, [sys.executable, "-I", "{src}"]),
    "javascript": (".js", None, ["node", "{src}"]),
    "bash": (".sh", None, ["bash", "{src}"]),
    "ruby": (".rb", None, ["ruby", "{src}"]),
    "php": (".php", None, ["php", "{src}"]),
    "lua": (".lua", None, ["lua", "{src}"]),
    "c": (".c", ["gcc", "{src}", "-o", "{out}"], ["{out}"]),
    "cpp": (".cpp", ["g++", "{src}", "-o", "{out}"], ["{out}"]),
    "go": (".go", None, ["go", "run", "{src}"]),
}

DANGEROUS = [
    (r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(/|~|\$HOME|\*)", "recursive delete of /, ~ or *"),
    (r"\bmkfs\b|\bdd\s+if=|>\s*/dev/sd|>\s*/dev/block", "disk-level write"),
    (r"\b(shutdown|reboot|poweroff|halt)\b", "power command"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"(curl|wget)[^\n|]*\|\s*(ba)?sh", "download-and-execute"),
    (r"chmod\s+-R\s+777\s+/", "chmod 777 on /"),
    (r"shutil\.rmtree\(\s*['\"](/|~)", "rmtree on / or ~"),
    (r"os\.(system|popen)\([^)]*\brm\s+-", "os.system rm"),
    (r"\bsu\s+-c\b|\bsudo\b", "privilege escalation"),
    (r"\bpm\s+(uninstall|clear)\b|\bsettings\s+put\b", "android system change"),
]

SECURITY_PATTERNS = [
    (r"\beval\s*\(", "eval() on dynamic input"),
    (r"\bexec\s*\(", "exec() on dynamic input"),
    (r"shell\s*=\s*True", "subprocess with shell=True"),
    (r"pickle\.loads?\(", "pickle on untrusted data"),
    (r"(password|passwd|secret|api_?key|token)\s*=\s*['\"][^'\"]{4,}['\"]", "hard-coded secret"),
    (r"verify\s*=\s*False", "TLS verification disabled"),
    (r"(SELECT|INSERT|UPDATE|DELETE)[^\n]*['\"]\s*\+\s*\w+|f['\"](SELECT|INSERT|UPDATE|DELETE)[^'\"]*\{", "possible SQL injection (string-built query)"),
    (r"innerHTML\s*=", "innerHTML assignment (XSS risk)"),
]


def check_dangerous(code):
    """Return list of reasons the code must NOT be auto-executed."""
    return [why for pat, why in DANGEROUS if re.search(pat, code)]


def security_scan(code):
    return [why for pat, why in SECURITY_PATTERNS if re.search(pat, code, re.I)]


def available_languages():
    out = {}
    for lang, (_, comp, run) in RUNNERS.items():
        tool = (comp or run)[0]
        out[lang] = bool(shutil.which(tool)) if tool not in ("{out}",) else True
        if comp:
            out[lang] = bool(shutil.which(comp[0]))
    return out


def _is_android():
    return (hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ
            or "com.termux" in sys.prefix)


def _limits(lang, mem_mb, cpu_s):
    """CPU time + file-size limits always; address-space limit only off-Android.

    Android's bionic linker needs large virtual-address mappings, so RLIMIT_AS
    makes even `python -c "print(1)"` crash there (seen on a real Termux run).
    RLIMIT_NPROC is not used: it counts per-UID processes, which on Android
    would block the whole app.
    """
    def apply():
        if resource is None:
            return
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024 * 1024,) * 2)
        if mem_mb and lang not in ("javascript", "go") and not _is_android():
            lim = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    return apply


def run_code(code, language, stdin="", timeout=10, mem_mb=1024, safe_mode=True):
    """Run code in a throwaway dir.

    safe_mode=True  : code flagged by check_dangerous() is not executed.
    safe_mode=False : no block-list (user choice). Timeout/CPU/memory limits and the
                      temp working dir still apply, but the code CAN damage files the
                      Termux user can access.
    Generation of code is never filtered by this module.
    """
    language = language.lower()
    if language not in RUNNERS:
        return {"ok": None, "status": "unsupported", "error": f"No runner for '{language}'"}
    blocked = check_dangerous(code) if safe_mode else []
    if blocked:
        return {"ok": False, "status": "blocked", "blocked": blocked,
                "error": "Not executed (dangerous): " + "; ".join(blocked)}
    ext, comp, run = RUNNERS[language]
    tool = (comp or run)[0]
    if not shutil.which(tool):
        return {"ok": None, "status": "missing_tool", "error": f"'{tool}' not installed"}

    work = Path(tempfile.mkdtemp(prefix="uca_run_"))
    try:
        src = work / ("main" + ext)
        out = work / "prog"
        src.write_text(code, encoding="utf-8")
        fill = lambda cmd: [c.format(src=src, out=out) for c in cmd]
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(work), "TMPDIR": str(work),
               "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        if language == "go":
            env.update(GOCACHE=str(work / "gc"), GOPATH=str(work / "gp"))
        if comp:
            c = subprocess.run(fill(comp), cwd=work, env=env, capture_output=True,
                               text=True, timeout=60)
            if c.returncode != 0:
                return {"ok": False, "status": "compile_error", "returncode": c.returncode,
                        "stdout": "", "stderr": c.stderr[:MAX_OUT]}
        def _go(limited):
            return subprocess.run(fill(run), cwd=work, env=env, input=stdin, capture_output=True,
                                  text=True, timeout=timeout,
                                  preexec_fn=_limits(language, mem_mb if limited else 0, timeout + 2) if resource else None)
        try:
            p = _go(True)
            if p.returncode != 0 and ("bionic/linker" in p.stderr or "MapShadow" in p.stderr):
                p = _go(False)   # limits broke the loader itself; retry without memory limit
        except subprocess.TimeoutExpired as e:
            return {"ok": False, "status": "timeout", "returncode": None,
                    "stdout": (e.stdout or b"")[:MAX_OUT] if isinstance(e.stdout, str) else "",
                    "stderr": f"Timed out after {timeout}s"}
        return {"ok": p.returncode == 0, "status": "ok" if p.returncode == 0 else "runtime_error",
                "returncode": p.returncode, "stdout": p.stdout[:MAX_OUT], "stderr": p.stderr[:MAX_OUT]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def analyze_error(language, stderr):
    """Pull error type, line number and a one-line summary out of stderr."""
    info = {"type": "unknown", "line": None, "summary": "", "missing_dependency": None}
    s = (stderr or "").strip()
    if not s:
        return info
    lines = s.splitlines()
    if language == "python":
        info["summary"] = lines[-1]
        m = re.match(r"(\w+(?:Error|Exception|Exit|Interrupt))\b", lines[-1])
        if m:
            info["type"] = m.group(1)
        ln = re.findall(r'File ".*?main\.py", line (\d+)', s)
        if ln:
            info["line"] = int(ln[-1])
        m = re.search(r"No module named '([\w\.]+)'", s)
        if m:
            info["missing_dependency"] = m.group(1).split(".")[0]
    elif language == "javascript":
        m = re.search(r"main\.js:(\d+)", s)
        info["line"] = int(m.group(1)) if m else None
        m = re.search(r"^(\w*Error): (.*)$", s, re.M)
        if m:
            info["type"], info["summary"] = m.group(1), m.group(0)
        m = re.search(r"Cannot find module '([^']+)'", s)
        if m:
            info["missing_dependency"] = m.group(1)
    elif language in ("c", "cpp"):
        m = re.search(r"main\.\w+:(\d+):\d+: (error|fatal error): (.*)", s)
        if m:
            info.update(type="compile_error", line=int(m.group(1)), summary=m.group(3))
        m = re.search(r"fatal error: (\S+): No such file", s)
        if m:
            info["missing_dependency"] = m.group(1)
    else:
        info["summary"] = lines[-1]
        m = re.search(r"line (\d+)", s)
        info["line"] = int(m.group(1)) if m else None
        m = re.search(r"(\S+): (command )?not found", s)
        if m:
            info["missing_dependency"] = m.group(1)
    if not info["summary"]:
        info["summary"] = lines[-1]
    return info


def extract_code(text):
    """Take the first fenced block from a model reply (or the raw text)."""
    m = re.search(r"```[\w+#-]*\n(.*?)```", text or "", re.S)
    return (m.group(1) if m else (text or "")).strip("\n")


def make_diff(before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        "before", "after"))


REPAIR_PROMPT = """Fix the {lang} program below. Return ONLY the complete corrected code in one fenced code block. Do not change what the program is meant to do.

Error ({etype}, line {line}): {summary}

Full error output:
{stderr}

Code:
```{lang}
{code}
```"""


def repair(code, language, model_fn, max_attempts=3, stdin="", timeout=10, safe_mode=True):
    """Run -> on failure ask model to fix -> re-run, up to max_attempts.

    model_fn(prompt: str) -> str  (e.g. lambda p: LocalModel().generate(p)["content"])
    Returns dict with success, final_code, attempts log and a before/after diff.
    Never overwrites anything on disk; caller decides what to do with final_code.
    """
    language = language.lower()
    current, attempts = code, []
    first = run_code(current, language, stdin, timeout, safe_mode=safe_mode)
    if first.get("ok") is None or first.get("status") == "blocked":
        return {"success": False, "final_code": code, "attempts": [], "initial": first,
                "diff": "", "security": security_scan(code),
                "message": first.get("error", "cannot run")}
    if first["ok"]:
        return {"success": True, "final_code": code, "attempts": [], "initial": first,
                "diff": "", "security": security_scan(code), "message": "Already runs fine."}
    result = first
    for n in range(1, max_attempts + 1):
        a = analyze_error(language, result.get("stderr", ""))
        prompt = REPAIR_PROMPT.format(lang=language, etype=a["type"], line=a["line"],
                                      summary=a["summary"], stderr=result.get("stderr", "")[-1500:],
                                      code=current)
        try:
            reply = model_fn(prompt)
        except Exception as exc:
            attempts.append({"n": n, "error": f"model failed: {exc}"})
            break
        fixed = extract_code(reply)
        if not fixed.strip() or fixed.strip() == current.strip():
            attempts.append({"n": n, "analysis": a, "note": "model returned no change"})
            continue
        result = run_code(fixed, language, stdin, timeout, safe_mode=safe_mode)
        attempts.append({"n": n, "analysis": a, "ok": result.get("ok"), "status": result.get("status")})
        if result.get("status") == "blocked":
            attempts[-1]["note"] = "fix rejected: dangerous"
            result = {"ok": False, "stderr": result.get("error", "")}
            continue
        current = fixed
        if result.get("ok"):
            break
    ok = bool(result.get("ok"))
    return {"success": ok, "final_code": current if ok else code, "attempts": attempts,
            "initial": first, "diff": make_diff(code, current) if ok else "",
            "security": security_scan(current if ok else code),
            "message": f"Fixed in {len(attempts)} attempt(s)." if ok else "Could not fix; original kept."}


def record(db_path, language, code, passed, error_summary="", fixed_code=""):
    """Save outcome to error_solutions / verification_results (needs db_schema.migrate())."""
    import sqlite3
    c = sqlite3.connect(str(db_path), timeout=30)
    try:
        if passed and error_summary and fixed_code:
            c.execute("INSERT INTO error_solutions(language,error_pattern,solution,fixed_code) VALUES(?,?,?,?)",
                      (language, error_summary[:300], "auto-repaired and re-run OK", fixed_code))
        c.execute("INSERT INTO verification_results(example_id,check_type,passed,output) VALUES(?,?,?,?)",
                  (None, "sandbox_run", 1 if passed else 0, error_summary[:500]))
        c.commit()
    finally:
        c.close()
