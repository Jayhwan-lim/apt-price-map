# 그땐 얼마? Android

Trusted Web Activity (TWA) for https://geuttaeneolma.com/. The app opens the
live site full screen in the device's browser engine (Chrome, Samsung
Internet or another TWA-capable browser), so it shares the website's service
worker, storage and updates. No app update is needed when the site changes.
Without a TWA-capable browser it falls back to a Custom Tab.

- Package: `com.geuttaeneolma.app` (permanent once published)
- minSdk 26, targetSdk 36 (Play requires API 36 for new apps from 2026-08-31)
- Library: `com.google.androidbrowserhelper:androidbrowserhelper`
- Domain proof: `web/.well-known/assetlinks.json`. If the fingerprint there
  does not match the signing certificate, the app still opens but shows a
  browser address bar.

## Signing

Play App Signing: Google holds the app signing key; we sign uploads with an
upload key kept outside the repository.

| GitHub secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | base64 of the upload keystore (`upload` alias, PKCS12) |
| `ANDROID_KEYSTORE_PASSWORD` | keystore and key password |

`assetlinks.json` must list two SHA-256 fingerprints:

1. Upload key: `28:8F:5E:46:19:26:D5:82:92:71:B8:BB:02:DD:BE:F0:FD:54:2C:4B:B4:80:8E:08:BB:6C:83:D8:4B:ED:34:47`
   (directly installed release APKs)
2. App signing key from Play Console → Test and release → App integrity
   (installs from Play). Add it after the first upload.

## Build

GitHub Actions [Android app](../.github/workflows/android.yml) runs on
changes under `android/`:

- `geuttaeneolma-android-debug`: debug APK for quick device tests (debug
  signature, so it shows the browser address bar).
- `geuttaeneolma-android-release` (only when the secrets exist):
  `app-release.aab` for Play Console and a signed `app-release.apk`.

Bump `versionCode` in `app/build.gradle` before every Play upload.

Local: Android SDK 36, Gradle 8.13, JDK 17+,
`gradle -p android :app:assembleDebug`.

## Smoke test on device

1. Launch: splash, then the map with no address bar (release build).
2. Search 파크리오, pick an area and year, check the chart and trades.
3. 가격으로 시작 → year/month/budget → tap a result.
4. Tap a Coupang banner: it opens outside the app.
5. Back button, a shared `https://geuttaeneolma.com/#...` link, rotation,
   and airplane mode then retry.
