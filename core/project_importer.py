"""Project importer + analyzer: ZIP/folder -> structure, languages, dependencies,
file relationships, entry points, incomplete functions.

Safety: ZIP extraction is zip-slip / zip-bomb protected. Nothing in the source is
ever modified or deleted; ZIPs are extracted into a NEW folder, folders are
analysed in place (read-only).
"""
import ast
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

from config import BASE_DIR

PROJECTS_DIR = BASE_DIR / "projects"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist",
             ".gradle", ".idea", "bin", "obj", "target", ".dart_tool"}
EXT_LANG = {".py": "python", ".java": "java", ".kt": "kotlin", ".js": "javascript",
            ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".c": "c",
            ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp",
            ".php": "php", ".html": "html", ".css": "css", ".sql": "sql", ".dart": "dart",
            ".go": "go", ".rs": "rust", ".rb": "ruby", ".swift": "swift", ".sh": "bash",
            ".xml": "xml", ".json": "json", ".yml": "yaml", ".yaml": "yaml",
            ".lua": "lua", ".r": "r"}
MAX_FILES = 5000
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024  # analysis read limit per file

FRAMEWORK_HINTS = [
    ("flask", "Flask (Python web)"), ("django", "Django"), ("fastapi", "FastAPI"),
    ("kivy", "Kivy (Python GUI/Android)"), ("telebot", "Telegram bot (pyTelegramBotAPI)"),
    ("telegram", "Telegram bot"), ("discord", "Discord bot"), ("express", "Express (Node)"),
    ("react", "React"), ("vue", "Vue"), ("next", "Next.js"), ("android", "Android"),
    ("tkinter", "Tkinter GUI"), ("pygame", "Pygame"), ("sqlalchemy", "SQLAlchemy"),
]


# ---------------------------------------------------------------- import
def safe_extract_zip(zip_path, name=None, projects_dir=None):
    """Extract into a new folder under projects/. Never overwrites an existing folder."""
    zip_path = Path(zip_path)
    projects_dir = Path(projects_dir or PROJECTS_DIR)
    projects_dir.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w\-]+", "_", name or zip_path.stem) or "project"
    dest, i = projects_dir / base, 1
    while dest.exists():                      # never touch existing projects
        i += 1
        dest = projects_dir / f"{base}_{i}"
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise ValueError(f"Too many files ({len(infos)} > {MAX_FILES})")
        if sum(x.file_size for x in infos) > MAX_TOTAL_BYTES:
            raise ValueError("Archive too large when extracted (zip-bomb protection)")
        dest.mkdir()
        root = dest.resolve()
        for info in infos:
            target = (dest / info.filename).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"Unsafe path in zip (zip-slip): {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
    # if zip had a single top folder, analyse inside it
    kids = [k for k in dest.iterdir()]
    if len(kids) == 1 and kids[0].is_dir():
        return kids[0]
    return dest


# ------------------------------------------------------------- scanning
def _iter_files(root):
    n = 0
    for p in sorted(Path(root).rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            n += 1
            if n > MAX_FILES:
                return
            yield p


def _read(p):
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _tree(root, files, max_lines=80):
    lines, seen = [], set()
    for f in files:
        rel = f.relative_to(root)
        for d in range(len(rel.parts) - 1):
            key = rel.parts[: d + 1]
            if key not in seen:
                seen.add(key)
                lines.append("  " * d + key[-1] + "/")
        lines.append("  " * (len(rel.parts) - 1) + rel.name)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... (+{len(lines) - max_lines} more)"]
    return "\n".join(lines)


# --------------------------------------------------------- python parse
def _py_module_index(root, py_files):
    idx = {}
    for f in py_files:
        rel = f.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            idx[".".join(parts)] = f
    return idx


def _analyze_python(root, f, text, mod_idx):
    info = {"imports": [], "local_deps": [], "defs": [], "incomplete": [], "syntax_error": None}
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        info["syntax_error"] = f"line {e.lineno}: {e.msg}"
        return info
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            info["imports"] += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = ("." * node.level) + (node.module or "")
            info["imports"].append(mod)
            # "from pkg import mod" may import a submodule: add pkg.mod as a candidate
            for a in node.names:
                if a.name != "*":
                    info["imports"].append(mod + ("" if mod.endswith(".") else ".") + a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            info["defs"].append(node.name)
            if not isinstance(node, ast.ClassDef):
                body = [b for b in node.body if not (isinstance(b, ast.Expr) and isinstance(getattr(b, "value", None), ast.Constant) and isinstance(b.value.value, str))]
                stub = (not body
                        or all(isinstance(b, ast.Pass) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and b.value.value is Ellipsis) for b in body)
                        or (len(body) == 1 and isinstance(body[0], ast.Raise)
                            and "NotImplementedError" in ast.dump(body[0])))
                if stub:
                    info["incomplete"].append({"name": node.name, "line": node.lineno})
    pkg = list(f.relative_to(root).with_suffix("").parts)
    for imp in info["imports"]:
        resolved = None
        if imp.startswith("."):
            up = len(imp) - len(imp.lstrip("."))
            base = pkg[:-up] if pkg[-1] != "__init__" else pkg[: -up + 1 or None]
            cand = ".".join(base + [p for p in imp.lstrip(".").split(".") if p])
            if cand in mod_idx:
                resolved = cand
        else:
            parts = imp.split(".")
            for n in range(len(parts), 0, -1):
                if ".".join(parts[:n]) in mod_idx:
                    resolved = ".".join(parts[:n])
                    break
        if resolved and mod_idx[resolved] != f:
            info["local_deps"].append(str(mod_idx[resolved].relative_to(root)))
    info["local_deps"] = sorted(set(info["local_deps"]))
    return info


_JS_IMP = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*|require\s*\(\s*)['"]([^'"]+)['"]""")


def _analyze_js(root, f, text):
    imps = _JS_IMP.findall(text)
    local = []
    for i in imps:
        if i.startswith("."):
            base = (f.parent / i).resolve()
            for c in [base] + [base.with_suffix(e) for e in (".js", ".jsx", ".ts", ".tsx")] + \
                     [base / "index.js", base / "index.ts"]:
                if c.is_file():
                    local.append(str(c.relative_to(root.resolve())))
                    break
    todo = [{"line": n + 1} for n, ln in enumerate(text.splitlines())
            if re.search(r"throw new Error\(['\"]not implemented", ln, re.I)]
    return {"imports": imps, "local_deps": sorted(set(local)), "incomplete": todo}


# ---------------------------------------------------------------- main
def analyze_project(root):
    """Read-only analysis of a project folder. Returns a JSON-serialisable dict."""
    root = Path(root).resolve()
    files = list(_iter_files(root))
    langs, per_file = Counter(), {}
    py_files = [f for f in files if f.suffix == ".py"]
    mod_idx = _py_module_index(root, py_files)
    todos, third_party = [], {"python": set(), "javascript": set()}
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    deps_files, entry = {}, []

    for f in files:
        lang = EXT_LANG.get(f.suffix.lower())
        if lang:
            langs[lang] += 1
        rel = str(f.relative_to(root))
        if f.name in ("requirements.txt", "package.json", "pom.xml", "build.gradle",
                      "pubspec.yaml", "Cargo.toml", "go.mod", "composer.json", "Gemfile",
                      "AndroidManifest.xml", "buildozer.spec", "Dockerfile"):
            deps_files[rel] = f.name
        if lang in ("python", "javascript", "typescript"):
            text = _read(f)
            if lang == "python":
                a = _analyze_python(root, f, text, mod_idx)
                for imp in a["imports"]:
                    top = imp.lstrip(".").split(".")[0]
                    if imp.startswith(".") or not top:
                        continue
                    if top not in stdlib and not any(m == top or m.startswith(top + ".") for m in mod_idx):
                        third_party["python"].add(top)
                if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", text):
                    entry.append(rel)
            else:
                a = _analyze_js(root, f, text)
                for imp in a["imports"]:
                    if not imp.startswith(".") and not imp.startswith("node:"):
                        third_party["javascript"].add(imp.split("/")[0] if not imp.startswith("@") else "/".join(imp.split("/")[:2]))
            for item in a.get("incomplete", []):
                todos.append({"file": rel, **item})
            if a.get("syntax_error"):
                todos.append({"file": rel, "name": "SYNTAX ERROR", "line": a["syntax_error"]})
            per_file[rel] = {"imports": a["imports"][:30], "depends_on": a["local_deps"]}

    # declared dependencies
    declared = []
    for rel, name in deps_files.items():
        text = _read(root / rel)
        if name == "requirements.txt":
            declared += [re.split(r"[=<>~! ;\[]", l.strip())[0].lower() for l in text.splitlines()
                         if l.strip() and not l.startswith("#")]
        elif name == "package.json":
            try:
                j = json.loads(text)
                declared += list(j.get("dependencies", {})) + list(j.get("devDependencies", {}))
            except ValueError:
                pass
    declared_set = {d.replace("_", "-") for d in declared}
    undeclared_py = sorted(m for m in third_party["python"] if m.replace("_", "-").lower() not in declared_set)

    # reverse graph: who is imported most
    used_by = Counter(d for v in per_file.values() for d in v["depends_on"])
    text_blob = " ".join(third_party["python"] | third_party["javascript"]).lower()
    frameworks = sorted({label for key, label in FRAMEWORK_HINTS if key in text_blob})
    if any(n == "AndroidManifest.xml" for n in deps_files.values()) and "Android" not in frameworks:
        frameworks.append("Android")

    return {
        "root": str(root),
        "file_count": len(files),
        "languages": dict(langs.most_common()),
        "tree": _tree(root, files),
        "entry_points": entry[:10],
        "frameworks": frameworks,
        "config_files": deps_files,
        "third_party": {k: sorted(v) for k, v in third_party.items()},
        "undeclared_python_deps": undeclared_py,
        "core_files": [f for f, _ in used_by.most_common(5)],
        "relationships": per_file,
        "incomplete_or_broken": todos,
    }


def summarize(report):
    """Short human-readable summary (also usable as model context)."""
    langs = ", ".join(f"{k}:{v}" for k, v in report["languages"].items()) or "none"
    out = [f"Files: {report['file_count']} | Languages: {langs}"]
    if report["frameworks"]:
        out.append("Frameworks: " + ", ".join(report["frameworks"]))
    if report["entry_points"]:
        out.append("Entry points: " + ", ".join(report["entry_points"]))
    if report["core_files"]:
        out.append("Most-imported files: " + ", ".join(report["core_files"]))
    if report["undeclared_python_deps"]:
        out.append("Python deps used but not in requirements.txt: " + ", ".join(report["undeclared_python_deps"]))
    if report["incomplete_or_broken"]:
        out.append(f"Incomplete/broken spots: {len(report['incomplete_or_broken'])}")
        for t in report["incomplete_or_broken"][:10]:
            ln = t["line"] if isinstance(t["line"], int) else str(t["line"]).replace("line ", "")
            out.append(f"  - {t['file']}: {t.get('name', 'not implemented')} (line {ln})")
    return "\n".join(out)


def import_and_analyze(path, name=None):
    """Entry point: path can be a .zip or a folder."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        p = safe_extract_zip(p, name)
    elif not p.is_dir():
        raise FileNotFoundError(path)
    rep = analyze_project(p)
    return rep, summarize(rep)
