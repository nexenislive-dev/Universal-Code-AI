# Android APK build status (Stage 4)

This source tree is prepared for a Kivy/Buildozer Android debug build. The Android entry point now opens the Kivy UI; desktop/Termux `python main.py` remains the CLI.

## Important runtime boundary

The APK UI connects to a local llama.cpp OpenAI-compatible server at `127.0.0.1:8080`. The server binary is not embedded in this APK build. For the current prototype, start llama.cpp separately in Termux on the same phone, then open the APK. This is a local loopback connection and does not use an API key or paid cloud service.

## Build

Buildozer needs Linux build dependencies, Android SDK/NDK, Java, and network access to download toolchains. Run `BUILD_ANDROID_UBUNTU.sh` from Ubuntu 22.04/24.04. It produces a debug APK in `bin/` only if the build succeeds.

This environment did not have Buildozer, Kivy, Android SDK, or Android NDK installed, so no APK was compiled here. Do not treat this source package as an installable APK.
