#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$ROOT/models"
MODEL="$MODEL_DIR/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
URL="https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf?download=true"
EXPECTED_SHA256="cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046"
mkdir -p "$MODEL_DIR"
command -v curl >/dev/null 2>&1 || { echo 'curl missing. Run: pkg install curl'; exit 1; }
FREE_KB=$(df -Pk "$MODEL_DIR" | awk 'NR==2 {print $4}')
if [ "${FREE_KB:-0}" -lt 2500000 ]; then
  echo 'At least 2.5 GB free storage is recommended before downloading this ~1.12 GB model.'
  exit 1
fi
echo 'Downloading Qwen2.5-Coder 1.5B Instruct Q4_K_M (~1.12 GB).'
echo 'This is a one-time download; afterward local inference can run offline.'
curl -L --fail --retry 5 --retry-delay 2 -C - "$URL" -o "$MODEL"
echo "Model saved: $MODEL"
echo 'SHA256 expected from the official model card: cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046'
if ! command -v sha256sum >/dev/null 2>&1; then
  echo 'sha256sum missing. Install it with: pkg install coreutils'
  exit 1
fi
ACTUAL_SHA256=$(sha256sum "$MODEL" | awk '{print $1}')
echo "Actual SHA256: $ACTUAL_SHA256"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo 'SHA256 mismatch. Do not load this model file; check the download and retry.'
  exit 1
fi
echo 'SHA256 verified.'
