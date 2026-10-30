<div align="center">

<img src="docs/icon.png" alt="offcard" width="128">

# offcard

**Back up your Sony camera card, sorted by day. Merge brackets into HDR.**

[![Latest version](https://img.shields.io/github/v/release/imsoumya18/offcard?label=version&color=48484a)](https://github.com/imsoumya18/offcard/releases/latest)
[![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-48484a)](#install)
[![License: MIT](https://img.shields.io/github/license/imsoumya18/offcard?color=48484a)](LICENSE)

<img src="docs/launch.gif" alt="offcard in the Mac menu bar: a card goes in, the panel shows what's new and where it goes, Back Up fills a ring, then Safe to format" width="760">

</div>

## What it does

- **Backs up only what's new** from the card to your drive, into `Year / Month / Day` folders.
- **Checks every byte** before you format the card.
- **Merges bracketed RAW shots** into one HDR photo.

The card is only ever read, never changed. Nothing leaves your computer.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/imsoumya18/offcard/main/install.sh | bash   # Mac, Linux
```
```powershell
irm https://raw.githubusercontent.com/imsoumya18/offcard/main/install.ps1 | iex   # Windows
```

Run it again to update. Or [download](https://github.com/imsoumya18/offcard/releases/latest) it.

## How to use

On a Mac, click the **›››** icon in the menu bar.

1. Put the card in. offcard shows what's new and the folder it goes into.
2. Click **Back Up**.
3. Click **Check Before Formatting**, then **Eject**.

**Tag a day:** click **+ Add tag** to name its folder `24Oct26 - Birthday`.
**Pick files:** the **⌄** on Back Up has Photos Only, Videos Only and **Choose Files…**.
**HDR Merge:** shoot in RAW with Continuous Bracket (BRK C), click **HDR Merge**, then **Merge**.

```
Sony Backup/
└── 2026/10. October/24Oct26 - Birthday/
    ├── Photos/   DSC00001.ARW …
    ├── Videos/   C00001.MP4 …
    └── HDR/      DSC00012-00014_HDR.jpg
```

On Windows and Linux, offcard opens as a window with the same tools; tags and picking files are
Mac-only for now.

---

Made for Sony Alpha and ZV cameras · [What's new](CHANGELOG.md) · [How it's built](DEVELOPMENT.md) ·
[MIT](LICENSE) © imsoumya18
