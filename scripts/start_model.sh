#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python - <<'PY'
from core.model_manager import ModelManager
import json
result = ModelManager().start(context=2048)
print(json.dumps(result, indent=2))
if not result.get('success'):
    raise SystemExit(1)
PY
