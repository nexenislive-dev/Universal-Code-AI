#!/usr/bin/env bash
set -euo pipefail
# Run inside Ubuntu 22.04/24.04 (e.g. Ubuntu proot), not directly in Termux.
python3 -m pip install --user --upgrade buildozer "Cython<3" virtualenv
export PATH="$HOME/.local/bin:$PATH"
buildozer --allow-root android debug
printf '\nAPK output (if build succeeds): %s/bin/*.apk\n' "$PWD"
