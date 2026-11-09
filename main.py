"""Android (python-for-android, webview bootstrap) entry point.

Starts the local web server on 127.0.0.1:5000; the WebView shows ui/index.html.
Desktop/Termux use: python main_cli.py  or  python server.py
"""
import os
import shutil
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PORT = 5000


def prepare():
    try:
        from android.storage import app_storage_path        # only exists inside the APK
        home = Path(app_storage_path()) / "uca"
    except ImportError:
        home = Path(os.environ.get("UCA_HOME") or (Path.home() / ".uca"))
    home.mkdir(parents=True, exist_ok=True)
    os.environ["UCA_HOME"] = str(home)                       # must be set before importing config
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
    except Exception:
        pass
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass
    src = HERE / "assets_bin" / "llama-server.bin"           # bundled by the GitHub build
    if src.is_file():
        dst = home / "bin" / "llama-server"
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.environ["UCA_LLAMA_SERVER"] = str(dst)
    return home


def run():
    prepare()
    import server
    srv = server.make_server(PORT)
    srv.serve_forever()


if __name__ == "__main__":
    run()
