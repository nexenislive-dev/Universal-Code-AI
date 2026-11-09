#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Build the official llama.cpp server natively inside Termux (no root / no API key).
pkg update -y
pkg install -y git cmake ninja clang make curl coreutils

if [ ! -d "$HOME/llama.cpp/.git" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$HOME/llama.cpp"
else
  git -C "$HOME/llama.cpp" pull --ff-only
fi

cmake -S "$HOME/llama.cpp" -B "$HOME/llama.cpp/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_OPENMP=OFF \
  -DGGML_LLAMAFILE=OFF

# Limit parallelism: compiling on a phone can exhaust RAM.
cmake --build "$HOME/llama.cpp/build" --config Release -j2 --target llama-server

printf '\nBuild complete: %s\n' "$HOME/llama.cpp/build/bin/llama-server"
printf 'Next: from this project run: bash scripts/download_model.sh\n'
printf 'Then: python main.py and use model-start (or bash scripts/start_model.sh).\n'
