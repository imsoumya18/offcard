#!/bin/bash
# offcard installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/imsoumya18/offcard/main/install.sh | bash
#
# Downloads the latest release for this computer and installs it:
#   macOS: the offcard app in /Applications (or ~/Applications)
#   Linux: ~/.local/bin/offcard plus an app-menu entry (the app opens in the browser)
# Files downloaded this way don't get macOS's "downloaded from the internet" mark, so the app
# opens without the Gatekeeper warning. Run the same command again to update.
set -euo pipefail

REPO="imsoumya18/offcard"
RELEASES="${OFFCARD_RELEASES:-https://github.com/$REPO/releases/latest/download}"
RAW="${OFFCARD_RAW:-https://raw.githubusercontent.com/$REPO/main}"

if [ -t 1 ]; then
  TEAL=$'\033[1;38;5;30m'; GREEN=$'\033[1;38;5;28m'; RED=$'\033[1;38;5;167m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  TEAL=""; GREEN=""; RED=""; DIM=""; OFF=""
fi
say()  { printf '  %s\n' "$*"; }
step() { printf '  %s›%s %s\n' "$TEAL" "$OFF" "$*"; }
fail() { printf '\n  %s✗ %s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

printf '\n  %soffcard installer%s\n\n' "$TEAL" "$OFF"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

download() {  # label, file, then one or more release file names to try in order
  local label="$1" out="$2"; shift 2
  local name url hdr size pid got pct fill mb tot secs start
  step "Downloading $label..."
  for name in "$@"; do
    url="$RELEASES/$name"
    if [ ! -t 2 ]; then                                    # scripts, CI: no animation
      curl -fsSL --retry 2 "$url" -o "$out" 2>/dev/null && return 0
      continue
    fi
    # One request: curl writes the response headers to $hdr as they arrive, so the size is known
    # as soon as GitHub answers, with no extra round trips on slow connections.
    hdr="$tmp/headers"; : > "$hdr"; : > "$out"
    curl -fsSL --retry 2 -D "$hdr" "$url" -o "$out" 2>/dev/null & pid=$!
    start=$SECONDS; size=0
    while kill -0 "$pid" 2>/dev/null; do
      [ "$size" -gt 0 ] || size="$(tr -d '\r' < "$hdr" | awk 'tolower($1)=="content-length:" {n=$2} END {print n+0}')"
      got="$(stat -f%z "$out" 2>/dev/null || stat -c%s "$out" 2>/dev/null || echo 0)"
      secs=$(( SECONDS - start ))
      if [ "$size" -le 0 ] || [ "$got" -eq 0 ]; then       # nothing yet: show it's still working
        printf '\r    %sconnecting to GitHub...%s %ss ' "$DIM" "$OFF" "$secs" >&2
      else
        pct=$(( got * 100 / size )); [ "$pct" -gt 100 ] && pct=100
        fill=$(( pct * 30 / 100 ))
        mb="$(awk -v n="$got" 'BEGIN {printf "%.1f", n/1048576}')"
        tot="$(awk -v n="$size" 'BEGIN {printf "%.1f", n/1048576}')"
        printf '\r    %s%s%s%s %3d%%  %s of %s MB    ' "$TEAL" "$(printf '%*s' "$fill" '' | tr ' ' '#')" "$OFF" \
          "$(printf '%*s' $(( 30 - fill )) '' | tr ' ' '-')" "$pct" "$mb" "$tot" >&2
      fi
      sleep 0.2
    done
    if wait "$pid"; then
      got="$(stat -f%z "$out" 2>/dev/null || stat -c%s "$out" 2>/dev/null || echo 0)"
      mb="$(awk -v n="$got" 'BEGIN {printf "%.1f", n/1048576}')"
      printf '\r    %s%s%s 100%%  %s MB, done.                 \n' "$TEAL" "$(printf '%30s' '' | tr ' ' '#')" "$OFF" "$mb" >&2
      return 0
    fi
    printf '\r%60s\r' '' >&2                              # not found: clear the line, try the next name
  done
  fail "Download failed (check your internet connection)"
}

wait_until_closed() {  # pgrep pattern: ask the user to quit the app before anything is downloaded
  pgrep -f "$1" >/dev/null 2>&1 || return 0
  if ! { [ -r /dev/tty ] && [ -w /dev/tty ]; }; then
    fail "offcard is open. Quit it, then run this line again."
  fi
  while pgrep -f "$1" >/dev/null 2>&1; do
    printf '  %s!%s offcard is open. Quit it (it has to be closed to update), then press Enter... ' "$RED" "$OFF" > /dev/tty
    read -r _ < /dev/tty || fail "Cancelled."
  done
}

# offcard was called ShotLoft until v2.6.1, and Sony Import until v2.0.0. After installing, the old
# apps are removed, but only if they're ours (checked by bundle ID or menu entry).
OLD_APPS=("ShotLoft:io.github.imsoumya18.shotloft" "Sony Import:io.github.imsoumya18.sony-import")

case "$(uname -s)" in
  Darwin)
    # Apple chip even when Terminal runs under Rosetta
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]; then
      arch="apple-silicon"; chip="Apple chip"
    else
      arch="intel"; chip="Intel chip"
    fi
    if [ -n "${OFFCARD_APPS_DIR:-}" ]; then
      apps="$OFFCARD_APPS_DIR"          # explicit choice: create it if needed
    elif [ -w /Applications ]; then
      apps="/Applications"
    else
      apps="$HOME/Applications"          # no admin rights: per-user Applications folder
    fi
    # Check before downloading: only the copy that would be replaced matters.
    wait_until_closed "$apps/(offcard|ShotLoft|Sony Import)\.app/Contents/"

    download "offcard for Mac ($chip)" "$tmp/app.zip" "offcard-macos-$arch.zip" "shotloft-macos-$arch.zip"
    ditto -x -k "$tmp/app.zip" "$tmp/unpacked" || fail "Could not unpack the download"
    src="$(find "$tmp/unpacked" -maxdepth 1 -name '*.app' | head -1)"
    [ -n "$src" ] || fail "The download doesn't contain the offcard app"
    name="$(basename "$src")"

    mkdir -p "$apps" || fail "Could not create $apps"
    app="$apps/$name"
    wait_until_closed "$apps/(offcard|ShotLoft|Sony Import)\.app/Contents/"   # in case it was opened meanwhile
    step "Installing to $app ..."
    rm -rf "$app"
    ditto "$src" "$app" || fail "Could not install to $apps"
    xattr -cr "$app" 2>/dev/null || true   # make sure nothing carries the "from the internet" mark
    touch "$app"                           # refresh the Finder / Launchpad icon
    exe="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Contents/Info.plist" 2>/dev/null)"
    version="$("$app/Contents/MacOS/$exe" --version 2>/dev/null | awk '{print $2}')" || version=""

    if [ "$name" = "offcard.app" ]; then      # remove the old ShotLoft and Sony Import apps, only if ours
      for entry in "${OLD_APPS[@]}"; do
        old_name="${entry%%:*}" old_id="${entry#*:}"
        # A normal install looks in both Applications folders. With an explicit folder (tests, CI),
        # only that folder is touched.
        olds=("$apps/$old_name.app")
        [ -z "${OFFCARD_APPS_DIR:-}" ] && olds+=("/Applications/$old_name.app" "$HOME/Applications/$old_name.app")
        for old in "${olds[@]}"; do
          [ -d "$old" ] || continue
          id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$old/Contents/Info.plist" 2>/dev/null)"
          if [ "$id" = "$old_id" ]; then
            rm -rf "$old" && say "${DIM}Removed the old version ($old_name): $old${OFF}"
          fi
        done
      done
    fi

    printf '\n  %s✓ offcard %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "It lives in your menu bar: click the ${TEAL}›››${OFF} icon at the top of the screen."
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    if [ -z "${OFFCARD_NO_REVEAL:-}" ]; then
      open "$app" 2>/dev/null || true   # start it, so its icon appears in the menu bar
    fi
    ;;

  Linux)
    [ "$(uname -m)" = "x86_64" ] || fail "Only 64-bit Intel/AMD Linux is supported for now."
    bin="${OFFCARD_BIN_DIR:-$HOME/.local/bin}"
    wait_until_closed "^$bin/(offcard|shotloft)( |$)"
    download "offcard for Linux" "$tmp/app.zip" "offcard-linux.zip" "shotloft-linux.zip"
    unzip -q "$tmp/app.zip" -d "$tmp/unpacked" || fail "Could not unpack the download"
    src="$tmp/unpacked/offcard"; [ -f "$src" ] || src="$tmp/unpacked/shotloft"
    [ -f "$src" ] || fail "The download doesn't contain the offcard app"
    mkdir -p "$bin"
    install -m 755 "$src" "$bin/offcard"
    version="$("$bin/offcard" --version 2>/dev/null | awk '{print $2}')" || version=""

    apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    mkdir -p "$apps_dir/applications" "$apps_dir/icons"
    curl -fsSL "$RAW/docs/icon.png" -o "$apps_dir/icons/offcard.png" 2>/dev/null || true  # icon is optional
    # The app opens in your browser on Linux; no terminal window needed.
    cat > "$apps_dir/applications/offcard.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=offcard
Comment=Back up your Sony camera card, sorted by date
Exec=$bin/offcard
Icon=$apps_dir/icons/offcard.png
Terminal=false
Categories=Graphics;Photography;
DESKTOP

    for old in "shotloft:ShotLoft" "sony-import:Sony Import"; do   # the old menu entries, if ours
      old_file="${old%%:*}" old_name="${old#*:}"
      old_desktop="$apps_dir/applications/$old_file.desktop"
      if [ -f "$old_desktop" ] && grep -q "^Name=$old_name\$" "$old_desktop"; then
        rm -f "$old_desktop" "$apps_dir/icons/$old_file.png" "$bin/$old_file"
        say "${DIM}Removed the old version ($old_name).${OFF}"
      fi
    done

    printf '\n  %s✓ offcard %s is installed.%s\n\n' "$GREEN" "${version}" "$OFF"
    say "Open ${TEAL}offcard${OFF} from your app menu. It opens in your web browser."
    say "${DIM}To update later, run the same command again.${OFF}"
    echo
    ;;

  *)
    fail "This installer is for macOS and Linux. On Windows, use the PowerShell line from the README."
    ;;
esac
