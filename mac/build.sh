#!/usr/bin/env bash
# Builds offcard.app for the Mac: the SwiftUI menu bar app, with the offcard engine (offcard.py,
# built by PyInstaller as a folder) inside it as a helper.
#
#   mac/build.sh OUT_DIR
#
# Needs Xcode (swiftc) and a Python with pyinstaller, numpy, rawpy and pillow. Builds for this
# Mac's processor (arm64 or x86_64).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mkdir -p "$1" && cd "$1" && pwd)"
work="$out/.work"
app="$out/offcard.app"
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/engine.py")"
arch="$(uname -m)"

rm -rf "$work" "$app"
mkdir -p "$work" "$app/Contents/MacOS" "$app/Contents/Resources"

echo "== engine (PyInstaller)"
python -m PyInstaller --noconfirm --log-level WARN --name OffcardEngine \
  --distpath "$work/dist" --workpath "$work/build" --specpath "$work" \
  --add-data "$root/engine.py:." --add-data "$root/hdr.py:." \
  --add-data "$root/ui:ui" --add-data "$root/docs/icon.png:docs" \
  "$root/offcard.py"
cp -R "$work/dist/OffcardEngine" "$app/Contents/Resources/engine"

echo "== app (SwiftUI, $arch)"
swiftc -parse-as-library -O -target "$arch-apple-macos14.0" -sdk "$(xcrun --show-sdk-path)" \
  "$root"/mac/Sources/*.swift -o "$app/Contents/MacOS/offcard"

cp "$root/docs/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>offcard</string>
  <key>CFBundleDisplayName</key><string>offcard</string>
  <key>CFBundleIdentifier</key><string>io.github.imsoumya18.offcard</string>
  <key>CFBundleExecutable</key><string>offcard</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
  <key>CFBundleVersion</key><string>$version</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHumanReadableCopyright</key><string>© imsoumya18. MIT License.</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

codesign --force --deep -s - "$app"
rm -rf "$work"
echo "== built $app ($version, $arch)"
