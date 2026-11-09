#!/usr/bin/env python3
"""Command-line front door for the new modules (works in Termux).

  python uca_tools.py migrate                      add the 12 tables (auto-backup first)
  python uca_tools.py backup | restore <file>      DB backup / restore
  python uca_tools.py analyze <zip-or-folder>      understand an existing project
  python uca_tools.py run <file> [--unsafe]        run a file in the sandbox
  python uca_tools.py repair <file> [--unsafe]     run -> ask local model to fix -> re-run (original kept)
  python uca_tools.py project "<request>"          plan + generate + validate + ZIP (needs model-start)
"""
import sys
from pathlib import Path

from config import DB_PATH
from core import db_schema, debugging_engine as dbg, project_importer, project_generator
from core.local_model import LocalModel
from utils.helpers import detect_language


def model_fn(prompt):
    r = LocalModel().generate(prompt, system="You are an expert software engineer. Follow the output format exactly.",
                              temperature=0.2, max_tokens=4096)
    if not r["success"]:
        raise RuntimeError(r.get("error", "local model not available - run model-start first"))
    return r["content"]


def main(a):
    if len(a) < 2:
        print(__doc__); return 1
    cmd, rest = a[1], [x for x in a[2:] if x != "--unsafe"]
    unsafe = "--unsafe" in a
    if cmd == "migrate":
        print("created:", db_schema.migrate()); print("integrity ok:", db_schema.integrity_ok())
    elif cmd == "backup":
        print(db_schema.backup(DB_PATH))
    elif cmd == "restore":
        print("restored from", db_schema.restore(rest[0]))
    elif cmd == "analyze":
        rep, summary = project_importer.import_and_analyze(rest[0]); print(summary); print("\n" + rep["tree"])
    elif cmd in ("run", "repair"):
        path = Path(rest[0]); code = path.read_text(encoding="utf-8"); lang = detect_language(code, path.name)
        if cmd == "run":
            r = dbg.run_code(code, lang, safe_mode=not unsafe)
            print(r.get("stdout", "")); print(r.get("stderr", "") or r.get("error", ""))
            print("status:", r["status"])
        else:
            r = dbg.repair(code, lang, model_fn, safe_mode=not unsafe)
            print(r["message"]); print(r["diff"])
            if r["security"]: print("security notes:", r["security"])
            if r["success"] and r["diff"]:
                out = path.with_name(path.stem + "_fixed" + path.suffix); out.write_text(r["final_code"]); print("saved:", out)
    elif cmd == "project":
        rep = project_generator.generate_project(" ".join(rest), model_fn, db_path=DB_PATH, progress=print)
        print(project_generator.format_report(rep))
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
