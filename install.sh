#!/bin/bash
# Sony Import installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/imsoumya18/sony-import/main/install.sh | bash
#
# Downloads the latest release for this computer and installs it:
#   macOS: "Sony Import.app" in /Applications (or ~/Applications), opens in Terminal
#   Linux: ~/.local/bin/sony-import plus an app-menu entry
# Files downloaded this way don't get macOS's "downloaded from the internet" mark, so the app
# opens without the Gatekeeper warning. Run the same command again to update.
set -euo pipefail

REPO="imsoumya18/sony-import"
RELEASES="${SONY_IMPORT_RELEASES:-https://github.com/$REPO/releases/latest/download}"
RAW="${SONY_IMPORT_RAW:-https://raw.githubusercontent.com/$REPO/main}"

if [ -t 1 ]; then
  TEAL=$'\033[1;38;5;30m'; GREEN=$'\033[1;38;5;28m'; RED=$'\033[1;38;5;167m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  TEAL=""; GREEN=""; RED=""; DIM=""; OFF=""
fi
say()  { printf '  %s\n' "$*"; }
step() { printf '  %s›%s %s\n' "$TEAL" "$OFF" "$*"; }
fail() { printf '\n  %s✗ %s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

printf '\n  %sSony Import installer%s\n\n' "$TEAL" "$OFF"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

download() {  # url, file
  curl -fsSL --retry 2 "$1" -o "$2" || fail "Download failed: $1 (check your internet connection)"
}

case "$(uname -s)" in
  Darwin)
    # Apple chip even when Terminal runs under Rosetta
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]; then
      zip="sony-import-macos-apple-silicon.zip"; chip="Apple chip"
    else
      zip="sony-import-macos-intel.zip"; chip="Intel chip"
    fi
    step "Downloading the latest version for Mac ($chip)..."
    download "$RELEASES/$zip" "$tmp/app.zip"
    unzip -q "$tmp/app.zip" -d "$tmp" || fail "Could not unpack the download"
    version="$("$tmp/sony-import" --version 2>/dev/null | awk '{print $2}')" || version=""

    if [ -n "${SONY_IMPORT_APPS_DIR:-}" ]; then
      apps="$SONY_IMPORT_APPS_DIR"          # explicit choice: create it if needed
    elif [ -w /Applications ]; then
      apps="/Applications"
    else
      apps="$HOME/Applications"             # no admin rights: per-user Applications folder
    fi
    mkdir -p "$apps" || fail "Could not create $apps"
    app="$apps/Sony Import.app"
    step "Installing to $app ..."
    rm -rf "$app"
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
    cp "$tmp/sony-import" "$app/Contents/Resources/sony-import"
    chmod +x "$app/Contents/Resources/sony-import"
    curl -fsSL "$RAW/docs/AppIcon.icns" -o "$app/Contents/Resources/AppIcon.icns" 2>/dev/null || true  # icon is optional

    # The app itself is a tiny launcher that opens the tool in a Terminal window.
    cat > "$app/Contents/MacOS/launcher" <<'LAUNCHER'
#!/bin/bash
exec open -a Terminal "$(cd "$(dirname "$0")/../Resources" && pwd)/sony-import"
LAUNCHER
    chmod +x "$app/Contents/MacOS/launcher"

    cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Sony Import</string>
  <key>CFBundleDisplayName</key><string>Sony Import</string>
  <key>CFBundleIdentifier</key><string>io.github.imsoumya18.sony-import</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${version:-1.0}</string>
  <key>CFBundleVersion</key><string>${version:-1.0}</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
</dict>
</plist>
PLIST
    xattr -cr "$app" 2>/dev/null || true   # make sure nothing carries the "from the internet" mark
    touch "$app"                           # refresh the Finder / Launchpad icon

    printf '\n  %s✓ Sony Import %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open it from your Applications folder or Launchpad: ${TEAL}Sony Import${OFF}"
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    if [ -z "${SONY_IMPORT_NO_REVEAL:-}" ]; then
      open -R "$app" 2>/dev/null || true   # show it in Finder
    fi
    ;;

  Linux)
    [ "$(uname -m)" = "x86_64" ] || fail "Only 64-bit Intel/AMD Linux is supported for now."
    step "Downloading the latest version for Linux..."
    download "$RELEASES/sony-import-linux.zip" "$tmp/app.zip"
    unzip -q "$tmp/app.zip" -d "$tmp" || fail "Could not unpack the download"
    bin="${SONY_IMPORT_BIN_DIR:-$HOME/.local/bin}"
    mkdir -p "$bin"
    install -m 755 "$tmp/sony-import" "$bin/sony-import"
    version="$("$bin/sony-import" --version 2>/dev/null | awk '{print $2}')" || version=""

    apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    mkdir -p "$apps_dir/applications" "$apps_dir/icons"
    curl -fsSL "$RAW/docs/icon.png" -o "$apps_dir/icons/sony-import.png" 2>/dev/null || true  # icon is optional
    cat > "$apps_dir/applications/sony-import.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Sony Import
Comment=Back up your Sony camera card, sorted by date
Exec=$bin/sony-import
Icon=$apps_dir/icons/sony-import.png
Terminal=true
Categories=Graphics;Photography;
DESKTOP

    printf '\n  %s✓ Sony Import %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open ${TEAL}Sony Import${OFF} from your app menu, or run: sony-import"
    case ":$PATH:" in
      *":$bin:"*) ;;
      *) say "${DIM}(To run it by name, add $bin to your PATH.)${OFF}" ;;
    esac
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    ;;

  *)
    fail "This installer is for macOS and Linux. On Windows, download sony-import-windows.exe from the README."
    ;;
esac
