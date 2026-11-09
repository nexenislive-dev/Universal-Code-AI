"""Knowledge bookkeeping. It deliberately does NOT claim DB examples train a model."""
from core.knowledge_db import KnowledgeDB
from config import SUPPORTED_LANGUAGES

class TrainingManager:
    def __init__(self, db: KnowledgeDB):
        self.db = db

    def add_manual(self, language, code, title="", score=0.9):
        kid = self.db.add(language, code, title=title, tags=["manual", "unverified"],
                          category="user", source="user", score=min(float(score), 0.59))
        return {"success": bool(kid), "id": kid, "message": "Saved as unverified knowledge; this does not train model weights." if kid else "Duplicate or invalid code"}

    def get_report(self):
        stats = self.db.get_stats()
        docs = self.db.search_documents("programming", limit=100000)
        lines = ["=" * 52, " UNIVERSAL CODE AI – LOCAL KNOWLEDGE STATUS", "=" * 52,
                 f"Code examples: {stats['total_examples']}",
                 f"Verified examples (score >= 0.6): {stats['verified_examples']}",
                 f"Average score: {stats['avg_score']:.3f}",
                 f"Languages with examples: {stats['languages_covered']}",
                 f"Documentation records matching 'programming': {len(docs)}", "",
                 "Model training status: NOT inferred from database size.",
                 "A local pretrained model must be loaded separately.", "", "Language counts:"]
        for lang in SUPPORTED_LANGUAGES:
            item = stats["language_stats"].get(lang, {})
            lines.append(f"  {lang:12} {item.get('verified_examples',0):4} verified / {item.get('total_examples',0):4} total")
        return "\n".join(lines)
