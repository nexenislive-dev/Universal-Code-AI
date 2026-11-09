"""Safe, non-executing syntax checks for common generated file types."""
import ast
import json
from pathlib import Path

class CodeValidator:
    def validate_file(self, path):
        p = Path(path)
        ext = p.suffix.lower()
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            if ext == ".py":
                ast.parse(text, filename=str(p))
            elif ext == ".json":
                json.loads(text)
            elif ext in (".html", ".htm"):
                if text.count("<") != text.count(">"):
                    return {"ok": False, "check": "basic-html", "error": "Possible unmatched angle bracket"}
            else:
                return {"ok": None, "check": "not-supported", "message": "No syntax checker configured; not executed."}
            return {"ok": True, "check": "syntax", "message": "Syntax check passed; runtime behavior not tested."}
        except (SyntaxError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "check": "syntax", "error": str(exc)}

    def validate_project(self, project_dir):
        root = Path(project_dir)
        results = []
        for p in root.rglob("*"):
            if p.is_file():
                results.append({"file": str(p.relative_to(root)), **self.validate_file(p)})
        checked = [r for r in results if r.get("ok") is not None]
        return {"files": results, "checked": len(checked), "passed": sum(1 for r in checked if r["ok"]),
                "failed": sum(1 for r in checked if not r["ok"]),
                "note": "Static checks only. Generated code was not executed."}
