# Universal Code AI (personal)
Local coding assistant: Python backend + HTML UI + bundled llama.cpp server. Built as an APK by GitHub Actions
(`Actions` tab -> `Build Android APK` -> `Run workflow`; APK appears under the run's **Artifacts**).
The GGUF model (~2 GB) is NOT in the APK: copy it to Download/ and enter its path in Settings -> Start model.
Termux/desktop use: `python main_cli.py` or `python server.py`.
