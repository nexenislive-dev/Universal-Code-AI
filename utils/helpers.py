"""Utility helpers"""

import re
import uuid
import hashlib
from typing import Optional, List


def generate_id(prefix: str = "") -> str:
    return f"{prefix}{str(uuid.uuid4())[:10]}"


def clean_code(code: str) -> str:
    if not code:
        return ""
    code = re.sub(r"^```[\w]*\n?", "", code.strip())
    code = re.sub(r"\n?```$", "", code.strip())
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return code.strip()


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def detect_language(text: str, filename: Optional[str] = None) -> str:
    if filename:
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        ext_map = {
            "py": "python", "java": "java", "kt": "kotlin", "c": "c",
            "cpp": "cpp", "cc": "cpp", "cs": "csharp", "js": "javascript",
            "ts": "typescript", "php": "php", "go": "go", "rs": "rust",
            "rb": "ruby", "swift": "swift", "dart": "dart", "html": "html",
            "css": "css", "sql": "sql", "sh": "bash", "lua": "lua", "hs": "haskell"
        }
        if ext in ext_map:
            return ext_map[ext]

    text_l = text.lower()
    checks = [
        (r"\bdef\s+\w+\(|\bimport\s+\w+|print\s*\(", "python"),
        (r"\bpublic\s+class\b|System\.out\.println", "java"),
        (r"\bfun\s+\w+\(|\bval\s+\w+\s*=", "kotlin"),
        (r"#include\s*<|printf\s*\(", "c"),
        (r"std::|cout\s*<<", "cpp"),
        (r"using\s+System;|Console\.WriteLine", "csharp"),
        (r"\bfunction\s+\w+\(|\bconst\s+\w+\s*=|\blet\s+\w+\s*=", "javascript"),
        (r"\binterface\s+\w+|\btype\s+\w+\s*=", "typescript"),
        (r"<\?php|\becho\s+", "php"),
        (r"\bfunc\s+\w+\(|package\s+main", "go"),
        (r"\bfn\s+\w+\(|let\s+mut\s+", "rust"),
        (r"\bdef\s+\w+|puts\s+", "ruby"),
        (r"\bfunc\s+\w+\(|var\s+\w+\s*:", "swift"),
        (r"void\s+main\(|Widget\s+", "dart"),
        (r"<html|<!DOCTYPE\s+html", "html"),
        (r"\.\w+\s*\{|:\s*[^;]+;", "css"),
        (r"\bSELECT\b|\bFROM\b|\bINSERT\s+INTO", "sql"),
        (r"#!/bin/(ba)?sh|\becho\s+", "bash"),
        (r"\bfunction\s+\w+\(|local\s+", "lua"),
        (r"\bmodule\s+\w+|main\s*::\s*IO", "haskell"),
    ]
    for pat, lang in checks:
        if re.search(pat, text, re.I):
            return lang
    return "unknown"


def extract_code_blocks(text: str) -> List[str]:
    """Markdown code blocks nikaalta hai"""
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if blocks:
        return [b.strip() for b in blocks if b.strip()]
    return [clean_code(text)] if text.strip() else []
