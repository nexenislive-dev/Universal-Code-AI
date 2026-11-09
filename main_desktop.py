#!/usr/bin/env python3
"""Universal Code AI entry point. Android launches Kivy UI; desktop keeps CLI."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    # Buildozer/python-for-android sets ANDROID_ARGUMENT for packaged apps.
    if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("UCA_FORCE_GUI") == "1":
        from gui_app import UniversalCodeAIApp
        UniversalCodeAIApp().run()
    else:
        from main_cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
