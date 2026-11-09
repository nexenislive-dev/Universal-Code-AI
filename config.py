"""
Universal Code AI - Configuration
Hybrid: Bot/API training → Independent Offline
"""

import os
from pathlib import Path

BASE_DIR = Path(os.environ.get("UCA_HOME") or Path(__file__).parent)  # UCA_HOME = writable data dir on Android
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "knowledge.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ====================== LOCAL MODEL ======================
# llama.cpp OpenAI-compatible server running on this device; no API key.
LOCAL_MODEL_BASE_URL = os.getenv("LOCAL_MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "local-coding-model")

# ====================== INDEPENDENCE THRESHOLDS ======================
# Jab ye cross ho jayein → system modules/API se free ho jayega
MIN_VERIFIED_EXAMPLES = 150
MIN_LANGUAGES = 6
MIN_AVG_SCORE = 0.65
MIN_STRONG_LANGUAGES = 4          # languages with >= 25 examples
STRONG_LANG_THRESHOLD = 25

# Force modes (testing)
FORCE_OFFLINE = False
FORCE_ONLINE = False

# ====================== LANGUAGES ======================
SUPPORTED_LANGUAGES = [
    "python", "java", "kotlin", "c", "cpp", "csharp",
    "javascript", "typescript", "php", "go", "rust",
    "ruby", "swift", "dart", "html", "css", "sql",
    "bash", "lua", "haskell"
]

LANGUAGE_EXTENSIONS = {
    "python": ".py", "java": ".java", "kotlin": ".kt", "c": ".c",
    "cpp": ".cpp", "csharp": ".cs", "javascript": ".js", "typescript": ".ts",
    "php": ".php", "go": ".go", "rust": ".rs", "ruby": ".rb",
    "swift": ".swift", "dart": ".dart", "html": ".html", "css": ".css",
    "sql": ".sql", "bash": ".sh", "lua": ".lua", "haskell": ".hs",
}

# ====================== GENERATION ======================
MAX_RETRIEVAL = 6
DEFAULT_TEMPERATURE = 0.15
MAX_TOKENS = 4096
