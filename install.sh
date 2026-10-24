#!/bin/bash
# ShotLoft installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.sh | bash
#
# Downloads the latest release for this computer and installs it:
#   macOS: the ShotLoft app in /Applications (or ~/Applications)
#   Linux: ~/.local/bin/shotloft plus an app-menu entry (the app opens in the browser)
# Files downloaded this way don't get macOS's "downloaded from the internet" mark, so the app
# opens without the Gatekeeper warning. Run the same command again to update.
set -euo pipefail

REPO="imsoumya18/shotloft"
RELEASES="${SHOTLOFT_RELEASES:-https://github.com/$REPO/releases/latest/download}"
RAW="${SHOTLOFT_RAW:-https://raw.githubusercontent.com/$REPO/main}"

if [ -t 1 ]; then
  TEAL=$'\033[1;38;5;30m'; GREEN=$'\033[1;38;5;28m'; RED=$'\033[1;38;5;167m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  TEAL=""; GREEN=""; RED=""; DIM=""; OFF=""
fi
say()  { printf '  %s\n' "$*"; }
step() { printf '  %s›%s %s\n' "$TEAL" "$OFF" "$*"; }
fail() { printf '\n  %s✗ %s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

printf '\n  %sShotLoft installer%s\n\n' "$TEAL" "$OFF"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

download() {  # file, then one or more release file names to try in order
  local out="$1"; shift
  for name in "$@"; do
    curl -fsIL --retry 2 "$RELEASES/$name" -o /dev/null 2>/dev/null || continue   # does it exist?
    if [ -t 2 ]; then
      curl -fL --retry 2 --progress-bar "$RELEASES/$name" -o "$out" && return 0  # progress bar
    else
      curl -fsSL --retry 2 "$RELEASES/$name" -o "$out" && return 0
    fi
  done
  fail "Download failed (check your internet connection)"
}

wait_until_closed() {  # pgrep pattern: ask the user to quit the app before anything is downloaded
  pgrep -f "$1" >/dev/null 2>&1 || return 0
  if ! { [ -r /dev/tty ] && [ -w /dev/tty ]; }; then
    fail "ShotLoft is open. Quit it, then run this line again."
  fi
  while pgrep -f "$1" >/dev/null 2>&1; do
    printf '  %s!%s ShotLoft is open. Quit it (it has to be closed to update), then press Enter... ' "$RED" "$OFF" > /dev/tty
    read -r _ < /dev/tty || fail "Cancelled."
  done
}

# ShotLoft was called Sony Import until v2.0.0. Until the first ShotLoft release exists, fall back
# to the last Sony Import one; after installing, remove the old Sony Import app if it's ours.
OLD_BUNDLE_ID="io.github.imsoumya18.sony-import"

case "$(uname -s)" in
  Darwin)
    # Apple chip even when Terminal runs under Rosetta
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]; then
      arch="apple-silicon"; chip="Apple chip"
    else
      arch="intel"; chip="Intel chip"
    fi
    if [ -n "${SHOTLOFT_APPS_DIR:-}" ]; then
      apps="$SHOTLOFT_APPS_DIR"          # explicit choice: create it if needed
    elif [ -w /Applications ]; then
      apps="/Applications"
    else
      apps="$HOME/Applications"          # no admin rights: per-user Applications folder
    fi
    # Check before downloading: only the copy that would be replaced matters.
    wait_until_closed "$apps/(ShotLoft|Sony Import)\.app/Contents/"

    step "Downloading the latest version for Mac ($chip)..."
    download "$tmp/app.zip" "shotloft-macos-$arch.zip" "sony-import-macos-$arch.zip"
    ditto -x -k "$tmp/app.zip" "$tmp/unpacked" || fail "Could not unpack the download"
    src="$(find "$tmp/unpacked" -maxdepth 1 -name '*.app' | head -1)"
    [ -n "$src" ] || fail "The download doesn't contain the ShotLoft app"
    name="$(basename "$src")"

    mkdir -p "$apps" || fail "Could not create $apps"
    app="$apps/$name"
    wait_until_closed "$apps/(ShotLoft|Sony Import)\.app/Contents/"   # in case it was opened meanwhile
    step "Installing to $app ..."
    rm -rf "$app"
    ditto "$src" "$app" || fail "Could not install to $apps"
    xattr -cr "$app" 2>/dev/null || true   # make sure nothing carries the "from the internet" mark
    touch "$app"                           # refresh the Finder / Launchpad icon
    exe="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Contents/Info.plist" 2>/dev/null)"
    version="$("$app/Contents/MacOS/$exe" --version 2>/dev/null | awk '{print $2}')" || version=""

    if [ "$name" = "ShotLoft.app" ]; then      # remove the old Sony Import app, only if it's ours
      # A normal install looks in both Applications folders. With an explicit folder (tests, CI),
      # only that folder is touched.
      olds=("$apps/Sony Import.app")
      [ -z "${SHOTLOFT_APPS_DIR:-}" ] && olds+=("/Applications/Sony Import.app" "$HOME/Applications/Sony Import.app")
      for old in "${olds[@]}"; do
        [ -d "$old" ] || continue
        id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$old/Contents/Info.plist" 2>/dev/null)"
        if [ "$id" = "$OLD_BUNDLE_ID" ]; then
          rm -rf "$old" && say "${DIM}Removed the old version (Sony Import): $old${OFF}"
        fi
      done
    fi

    printf '\n  %s✓ ShotLoft %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open it from your Applications folder or Launchpad: ${TEAL}ShotLoft${OFF}"
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    if [ -z "${SHOTLOFT_NO_REVEAL:-}" ]; then
      open -R "$app" 2>/dev/null || true   # show it in Finder
    fi
    ;;

  Linux)
    [ "$(uname -m)" = "x86_64" ] || fail "Only 64-bit Intel/AMD Linux is supported for now."
    bin="${SHOTLOFT_BIN_DIR:-$HOME/.local/bin}"
    wait_until_closed "^$bin/shotloft( |$)"
    step "Downloading the latest version for Linux..."
    download "$tmp/app.zip" "shotloft-linux.zip" "sony-import-linux.zip"
    unzip -q "$tmp/app.zip" -d "$tmp/unpacked" || fail "Could not unpack the download"
    src="$tmp/unpacked/shotloft"; [ -f "$src" ] || src="$tmp/unpacked/sony-import"
    [ -f "$src" ] || fail "The download doesn't contain the ShotLoft app"
    mkdir -p "$bin"
    install -m 755 "$src" "$bin/shotloft"
    version="$("$bin/shotloft" --version 2>/dev/null | awk '{print $2}')" || version=""

    apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    mkdir -p "$apps_dir/applications" "$apps_dir/icons"
    curl -fsSL "$RAW/docs/icon.png" -o "$apps_dir/icons/shotloft.png" 2>/dev/null || true  # icon is optional
    # The app opens in your browser on Linux; no terminal window needed.
    cat > "$apps_dir/applications/shotloft.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ShotLoft
Comment=Back up your Sony camera card, sorted by date
Exec=$bin/shotloft
Icon=$apps_dir/icons/shotloft.png
Terminal=false
Categories=Graphics;Photography;
DESKTOP

    old_desktop="$apps_dir/applications/sony-import.desktop"   # the old Sony Import entry, if ours
    if [ -f "$old_desktop" ] && grep -q "^Name=Sony Import" "$old_desktop"; then
      rm -f "$old_desktop" "$apps_dir/icons/sony-import.png" "$bin/sony-import"
      say "${DIM}Removed the old version (Sony Import).${OFF}"
    fi

    printf '\n  %s✓ ShotLoft %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open ${TEAL}ShotLoft${OFF} from your app menu. It opens in your web browser."
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    ;;

  *)
    fail "This installer is for macOS and Linux. On Windows, use the PowerShell line from the README."
    ;;
esac
