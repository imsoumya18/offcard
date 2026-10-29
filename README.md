<div align="center">

<img src="docs/icon.png" alt="ShotLoft" width="128">

# ShotLoft

**Utility tools for Sony cameras: card backup, HDR merge**

[![Latest version](https://img.shields.io/github/v/release/imsoumya18/shotloft?label=version&color=008787)](https://github.com/imsoumya18/shotloft/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/shotloft/build.yml?branch=main&label=build)](https://github.com/imsoumya18/shotloft/actions/workflows/build.yml)
[![Downloads](https://img.shields.io/github/downloads/imsoumya18/shotloft/total)](https://github.com/imsoumya18/shotloft/releases)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-008787)](#install)
[![License: MIT](https://img.shields.io/github/license/imsoumya18/shotloft?color=008787)](LICENSE)

[Install](#install) • [How to use](#how-to-use) • [Tech stack](#tech-stack) • [What's new](CHANGELOG.md)

</div>

## Install

**Mac and Linux:** open Terminal and run

```bash
curl -fsSL https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.sh | bash
```

**Windows:** open PowerShell and run

```powershell
irm https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.ps1 | iex
```

ShotLoft then appears in Applications, the Start menu, or your app menu. Run the same line again
to update; the app tells you when a new version is out.

<details>
<summary>Download the app directly instead</summary>

| Your computer | Download |
|---|---|
| Windows | [shotloft-windows.exe](https://github.com/imsoumya18/shotloft/releases/latest/download/shotloft-windows.exe) |
| Mac, Apple chip | [shotloft-macos-apple-silicon.zip](https://github.com/imsoumya18/shotloft/releases/latest/download/shotloft-macos-apple-silicon.zip) |
| Mac, Intel chip | [shotloft-macos-intel.zip](https://github.com/imsoumya18/shotloft/releases/latest/download/shotloft-macos-intel.zip) |
| Linux, 64-bit | [shotloft-linux.zip](https://github.com/imsoumya18/shotloft/releases/latest/download/shotloft-linux.zip) |

Apps downloaded in a browser get a security warning the first time. On a Mac, allow it in
**System Settings → Privacy & Security → Open Anyway**; on Windows, click **More info → Run
anyway**. The one-line install avoids this.
</details>

## How to use

**On a Mac**, ShotLoft lives in the menu bar: click its aperture icon for a small panel with your
card, where it goes, and the tools. It opens at login (switch that off under ⋯), and when you put
in a card with new photos, the icon gets a dot.
**On Windows and Linux**, open ShotLoft and pick a tool.

### Card Backup

1. Put the memory card in, and connect the drive you back up to.
2. Click **Card Backup** (on a Mac, the menu bar icon), then **Choose backup folder** (only the
   first time).
3. Click **Back up**. Only new photos and videos are copied. On a Mac, the panel first shows the
   folders it will create and how many files go into each.
4. Before formatting the card, click **Check it's safe to format**. Then click **Eject card**.

The card is only ever read, never changed. Your backup folder is sorted by the day you took each
shot, and every file gets one clean number in shooting order:

```
Camera Backup/                      ← the folder you chose
└── 2026/
    └── 10. October/
        └── 24Oct26/
            ├── Photos/
            │   ├── DSC00001.ARW
            │   └── DSC00001.JPG      ← shot as RAW + JPG
            ├── Videos/
            │   ├── C00001.MP4
            │   └── C00001M01.XML
            └── HDR/                  ← made by HDR Merge
                └── DSC00012-00014_HDR.jpg
```

### HDR Merge

1. On the camera, shoot with **Continuous Bracket (BRK C)** in **RAW**, for example 3 shots at
   ±2 EV.
2. Click **HDR Merge** (on a Mac, it opens in its own window) and choose a folder. Your backup folder works: every folder inside it is
   searched.
3. Tick the bracketed sets it finds, and click **Merge to HDR**. Each takes about 30 seconds.

Results go into the day's `HDR` folder, beside `Photos` and `Videos` (in other folders, an `HDR`
folder next to the shots). The original shots are never changed.

## Tech stack

| Part | Built with |
|---|---|
| Mac app | Native [SwiftUI](https://developer.apple.com/xcode/swiftui/) menu bar app on Liquid Glass, with the Python engine inside |
| Windows and Linux | One HTML page: in a [pywebview](https://pywebview.flowrl.com/) (WebView2) window on Windows, in the browser on Linux |
| Backup engine | Python standard library: EXIF reading, content fingerprints, byte-by-byte verify |
| HDR merge | [NumPy](https://numpy.org/), [rawpy](https://github.com/letmaik/rawpy) ([LibRaw](https://www.libraw.org/)), [Pillow](https://python-pillow.org/): noise-weighted RAW merge, alignment, ghost removal, exposure fusion |
| Packaging | [PyInstaller](https://pyinstaller.org/), with one-line installers in Bash and PowerShell |
| CI and releases | GitHub Actions: tests and builds for Windows, macOS (Apple and Intel) and Linux |

How it all works, running from source and releasing: [DEVELOPMENT.md](DEVELOPMENT.md).

## Good to know

- Made for Sony Alpha and ZV cameras; tested on the a6600. Folder dates come from the camera's clock.
- Your photos never leave your computer. The only internet use is checking for a new version.
- ShotLoft was called *Sony Import* up to v2.0.0.
- **Uninstall:** delete ShotLoft from Applications (Mac), `%LOCALAPPDATA%\Programs\ShotLoft` and
  its Start menu shortcut (Windows), or `~/.local/bin/shotloft` and
  `~/.local/share/applications/shotloft.desktop` (Linux). Settings are in `~/.shotloft.json`.

## License

[MIT](LICENSE) © imsoumya18
