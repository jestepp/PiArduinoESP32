# XIAO Camera Android App

This is a minimal Android app for the firmware in `src/camera_sense`.

It does two things:

- Opens the ESP32 camera web UI in a WebView.
- Scans for the `XIAO-S3-Camera` BLE device and writes Wi-Fi credentials to the config characteristic.

## Build APK

Open `android/CameraControlApp` in Android Studio and choose:

```text
Build > Build Bundle(s) / APK(s) > Build APK(s)
```

This workstation currently has Java but not the Android Gradle tooling on `PATH`, so the APK cannot be built here from the command line without installing Android Studio or the Android SDK/Gradle toolchain.
