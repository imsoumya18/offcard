#!/bin/bash
# Prints the release notes for a version (e.g. 0.3.1): its section of CHANGELOG.md plus install
# lines. Exits 1 if CHANGELOG.md has no section for that version.
set -euo pipefail
v="${1#v}"
notes="$(awk -v head="## [$v]" 'index($0, "## [") == 1 { p = (index($0, head) == 1); next } p' CHANGELOG.md)"
[ -n "$(echo "$notes" | tr -d '[:space:]')" ] || exit 1
echo "$notes" | sed -e '/./,$!d'      # drop leading blank lines
cat <<'FOOT'

---

**Install or update** (the same line does both):

- **Mac / Linux** (Terminal): `curl -fsSL https://raw.githubusercontent.com/imsoumya18/offcard/main/install.sh | bash`
- **Windows** (PowerShell): `irm https://raw.githubusercontent.com/imsoumya18/offcard/main/install.ps1 | iex`

Or download the file for your computer below.
FOOT
