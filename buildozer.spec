[app]
title = Universal Code AI
package.name = universalcodeai
package.domain = org.personal
source.dir = .
source.include_exts = py,html,bin,json,txt
source.exclude_dirs = tests,bin,__pycache__,.git,.github,logs,projects,exports,backups,models,data,scripts,modules
version = 0.5.0
requirements = python3,sqlite3,openssl,certifi
orientation = portrait
fullscreen = 0
# targetSdk 28 on purpose: Android blocks running binaries from app storage for targetSdk >= 29,
# and the bundled llama-server must be executed from there. (Personal sideload APK, not for Play Store.)
android.api = 28
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK
android.accept_sdk_license = True
android.allow_backup = False
p4a.bootstrap = webview
p4a.port = 5000

[buildozer]
log_level = 2
warn_on_root = 0
