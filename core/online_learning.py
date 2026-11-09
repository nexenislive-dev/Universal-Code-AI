"""Collect public text/documentation into the local knowledge DB.
This is retrieval/knowledge acquisition, NOT neural-model training.
Only fetches an explicitly supplied URL; respects size and content-type limits.
"""
import re
import urllib.request
import urllib.parse
from html import unescape
from typing import Dict, Any


class OnlineLearning:
    MAX_BYTES = 1_500_000
    USER_AGENT = "UniversalCodeAI-PersonalResearch/1.0"

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _html_to_text(raw: str) -> str:
        raw = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw)
        raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        raw = unescape(raw)
        return re.sub(r"\s+", " ", raw).strip()

    def learn_url(self, url: str, topic: str = "", language: str = "general") -> Dict[str, Any]:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {"success": False, "error": "Valid http/https URL required"}
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "text/html,text/plain,text/markdown,application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(x in content_type for x in ("text/", "json", "xml")):
                    return {"success": False, "error": f"Unsupported content type: {content_type}"}
                data = resp.read(self.MAX_BYTES + 1)
            if len(data) > self.MAX_BYTES:
                return {"success": False, "error": "Page exceeds 1.5 MB limit"}
            text = data.decode("utf-8", errors="replace")
            if "html" in content_type:
                text = self._html_to_text(text)
            else:
                text = re.sub(r"\s+", " ", text).strip()
            if len(text) < 100:
                return {"success": False, "error": "Not enough readable text found"}
            doc_id = self.db.add_document(
                source_url=url, topic=topic or parsed.path.rsplit("/", 1)[-1] or parsed.netloc,
                language=language, content=text[:200_000]
            )
            return {"success": True, "document_id": doc_id, "characters_saved": min(len(text), 200_000), "source": url}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
