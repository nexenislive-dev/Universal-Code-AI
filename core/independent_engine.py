"""
Independent Engine
Jab system enough data collect kar leta hai to ye engine use hota hai.
Kisi bhi external module / API par depend nahi karta.
"""

from typing import Dict, Any, List, Optional
from core.knowledge_db import KnowledgeDB
from utils.helpers import clean_code, detect_language


class IndependentEngine:
    """
    Fully local generation engine.
    Knowledge DB se relevant examples retrieve karke
    unhe base bana kar response banata hai.
    """

    def __init__(self, db: KnowledgeDB):
        self.db = db

    def generate(self, request: str, language: Optional[str] = None) -> Dict[str, Any]:
        lang = language or detect_language(request)

        # 1. Best matching examples retrieve
        results = self.db.search(query=request[:180], language=lang if lang != "unknown" else None, limit=6, min_score=0.45)

        if not results:
            results = self.db.search(query=request[:120], limit=5, min_score=0.35)

        if not results:
            return {
                "success": False,
                "content": (
                    "⚠️ Independent mode active.\n"
                    "Knowledge database mein is request ke liye sufficient verified examples nahi mile.\n\n"
                    "Training phase mein bot se connect karke aur examples generate karein.\n"
                    "Ya phir manually knowledge add karein."
                ),
                "mode": "independent",
                "examples_used": 0
            }

        # 2. Build response from best examples
        parts = [
            "🔒 INDEPENDENT MODE (No external module/API)",
            f"Retrieved {len(results)} verified examples from local knowledge.\n"
        ]

        best = results[0]
        parts.append(f"Best match (score={best['verification_score']:.2f}, lang={best['language']}):")
        if best.get("title"):
            parts.append(f"Title: {best['title']}")
        parts.append(f"\n```{best['language']}\n{best['code']}\n```")

        if len(results) > 1:
            parts.append("\n--- Other relevant examples ---")
            for r in results[1:3]:
                parts.append(f"\n[{r['language']}] score={r['verification_score']:.2f}")
                parts.append(f"```{r['language']}\n{r['code'][:800]}{'...' if len(r['code'])>800 else ''}\n```")

        parts.append(
            "\n💡 Yeh local verified knowledge se generate hua hai. "
            "Aap isse modify karke use kar sakte ho."
        )

        for r in results:
            self.db.increment_usage(r["id"])

        return {
            "success": True,
            "content": "\n".join(parts),
            "mode": "independent",
            "language": best["language"],
            "examples_used": len(results),
            "best_score": best["verification_score"]
        }
