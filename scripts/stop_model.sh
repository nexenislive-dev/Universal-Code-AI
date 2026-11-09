#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python - <<'PY'
from core.model_manager import ModelManager
import json
print(json.dumps(ModelManager().stop(), indent=2))
PY
