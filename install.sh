#!/bin/bash
# Sony Import installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/imsoumya18/sony-import/main/install.sh | bash
#
# Downloads the latest release for this computer and installs it:
#   macOS: the Sony Import app in /Applications (or ~/Applications)
#   Linux: ~/.local/bin/sony-import plus an app-menu entry (the app opens in the browser)
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
    ditto -x -k "$tmp/app.zip" "$tmp" || fail "Could not unpack the download"
    [ -d "$tmp/Sony Import.app" ] || fail "The download doesn't contain Sony Import.app"

    if [ -n "${SONY_IMPORT_APPS_DIR:-}" ]; then
      apps="$SONY_IMPORT_APPS_DIR"          # explicit choice: create it if needed
    elif [ -w /Applications ]; then
      apps="/Applications"
    else
      apps="$HOME/Applications"             # no admin rights: per-user Applications folder
    fi
    mkdir -p "$apps" || fail "Could not create $apps"
    app="$apps/Sony Import.app"
    if pgrep -f "Sony Import.app/Contents/MacOS/Sony Import" >/dev/null 2>&1; then
      fail "Sony Import is open. Quit it, then run this line again."
    fi
    step "Installing to $app ..."
    rm -rf "$app"                            # also replaces the older Terminal-based version
    ditto "$tmp/Sony Import.app" "$app" || fail "Could not install to $apps"
    xattr -cr "$app" 2>/dev/null || true   # make sure nothing carries the "from the internet" mark
    touch "$app"                           # refresh the Finder / Launchpad icon
    version="$("$app/Contents/MacOS/Sony Import" --version 2>/dev/null | awk '{print $2}')" || version=""

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
    # The app opens in your browser on Linux; no terminal window needed.
    cat > "$apps_dir/applications/sony-import.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Sony Import
Comment=Back up your Sony camera card, sorted by date
Exec=$bin/sony-import
Icon=$apps_dir/icons/sony-import.png
Terminal=false
Categories=Graphics;Photography;
DESKTOP

    printf '\n  %s✓ Sony Import %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open ${TEAL}Sony Import${OFF} from your app menu. It opens in your web browser."
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    ;;

  *)
    fail "This installer is for macOS and Linux. On Windows, use the PowerShell line from the README."
    ;;
esac
