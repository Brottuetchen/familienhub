#!/bin/sh
# Regenerates docs/screenshots/<lang>/*.png from the demo family (no real data). Run from anywhere.
set -e
cd "$(dirname "$0")/.."
flutter pub get >/dev/null
flutter test --update-goldens test_screenshots/
ls -la ../docs/screenshots/*/
