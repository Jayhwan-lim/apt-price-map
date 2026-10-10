# 그땐 얼마? Android

Android 8.0+ app wrapping the live https://geuttaeneolma.com/ site.
The map, comparisons, and data update with the website. External links
(including Coupang Partners) open in the device browser.

## Build

GitHub Actions [Android debug APK](../.github/workflows/android.yml) builds
`android/app/build/outputs/apk/debug/app-debug.apk`. Download the
`geuttaeneolma-android-debug` artifact from the workflow run, unzip it,
and install the APK on an Android phone. This is a **debug build** for testing;
it is not signed for Play Store publication. A production release needs a
private signing key, Play Store listing, target API policy review, and device
testing.

For local builds with Android SDK 35 and Gradle 8.9:
`gradle -p android :app:assembleDebug`.

## Smoke test on device

1. Open: map should show 50m scale and the latest site.
2. Search for 파크리오, select an area/year, and inspect the chart and trades.
3. Switch to 가격으로 시작, select a year/month and budget, then tap a result.
4. Tap a Coupang banner: it should open the device browser.
5. Check app Back, a shared `https://geuttaeneolma.com/#...` link,
   screen rotation, and retry after a temporary network failure.

Android may show a chooser for web links until a release signing certificate
is added to `/.well-known/assetlinks.json` on the production domain.
No credentials or API keys are embedded in the APK.
