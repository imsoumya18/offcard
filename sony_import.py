#!/usr/bin/env python3
"""Back up photos and videos from Sony camera cards into Year/Month/Day folders.

The card is only ever read, never written. "Already backed up" is decided by
scanning the destination itself (size + capture time + content sample), so
there is no state file and any destination folder works.

The backup folder comes from --dest, or the SONY_IMPORT_DEST environment variable.

Subcommands (all print human text; add --json for machine output):
  detect  [--dest DIR]                find Sony cards; check the backup drive
  plan    --dest DIR [--card PATH..]  report what is new on each card
  import  --dest DIR [--card PATH..]  copy new files (progress bar), write --report
  trash-jpgs --report FILE            move JPGs that have an ARW twin to the Trash
Run with no subcommand for a fully interactive session in a terminal.
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime

DEFAULT_DEST = os.environ.get("SONY_IMPORT_DEST")  # backup folder; --dest overrides
PHOTO_EXT = {".ARW", ".JPG", ".JPEG", ".HIF", ".HEIF"}
SONY_DCIM_DIR = re.compile(r"^\d{3}(MSDCF|\d{5})$")
NUM_WIDTH = 5
CHUNK = 8 * 1024 * 1024


# ---------------------------------------------------------------- metadata

def _tiff_datetime(f, base):
    """Return 'YYYY:MM:DD HH:MM:SS[.sub]' from a TIFF/EXIF block starting at base."""
    f.seek(base)
    head = f.read(8)
    if head[:2] == b"II":
        e = "<"
    elif head[:2] == b"MM":
        e = ">"
    else:
        return None

    def read_ifd(off):
        f.seek(base + off)
        n = struct.unpack(e + "H", f.read(2))[0]
        tags = {}
        for _ in range(n):
            tag, typ, cnt, val = struct.unpack(e + "HHI4s", f.read(12))
            tags[tag] = (typ, cnt, val)
        return tags

    def ascii_val(entry):
        typ, cnt, val = entry
        if cnt <= 4:
            raw = val[:cnt]
        else:
            pos = f.tell()
            f.seek(base + struct.unpack(e + "I", val)[0])
            raw = f.read(cnt)
            f.seek(pos)
        return raw.split(b"\0")[0].decode("ascii", "ignore").strip()

    ifd0 = read_ifd(struct.unpack(e + "I", head[4:8])[0])
    dt = sub = None
    if 0x8769 in ifd0:
        exif = read_ifd(struct.unpack(e + "I", ifd0[0x8769][2])[0])
        if 0x9003 in exif:
            dt = ascii_val(exif[0x9003])
        if 0x9291 in exif:
            sub = ascii_val(exif[0x9291])
    if not dt and 0x0132 in ifd0:
        dt = ascii_val(ifd0[0x0132])
    if not dt:
        return None
    return dt + ("." + sub if sub else "")


def _jpeg_datetime(f):
    f.seek(0)
    if f.read(2) != b"\xff\xd8":
        return None
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        if marker[1] in (0xD9, 0xDA):
            return None
        length = struct.unpack(">H", f.read(2))[0]
        start = f.tell()
        if marker[1] == 0xE1 and f.read(6) == b"Exif\0\0":
            return _tiff_datetime(f, start + 6)
        f.seek(start + length - 2)


def _sips_datetime(path):
    try:
        out = subprocess.run(["sips", "-g", "creation", path],
                             capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"creation:\s*(\d{4}:\d\d:\d\d \d\d:\d\d:\d\d)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _mtime_datetime(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y:%m:%d %H:%M:%S")


def photo_datetime(path):
    ext = os.path.splitext(path)[1].upper()
    dt = None
    try:
        with open(path, "rb") as f:
            if ext == ".ARW":
                dt = _tiff_datetime(f, 0)
            elif ext in (".JPG", ".JPEG"):
                dt = _jpeg_datetime(f)
    except Exception:
        dt = None
    return dt or _sips_datetime(path) or _mtime_datetime(path)


def video_datetime(mp4, xml):
    if xml and os.path.exists(xml):
        try:
            with open(xml, "r", encoding="utf-8", errors="ignore") as f:
                m = re.search(r'<CreationDate value="(\d{4})-(\d\d)-(\d\d)T(\d\d:\d\d:\d\d)', f.read())
            if m:
                return f"{m.group(1)}:{m.group(2)}:{m.group(3)} {m.group(4)}"
        except Exception:
            pass
    return _mtime_datetime(mp4)


def fingerprint(path):
    """Hash of three 64 KB samples (start, middle, end): cheap, and tells apart
    burst shots that share size and capture second (Sony compressed RAW is fixed-size)."""
    size = os.path.getsize(path)
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for off in (0, size // 2, max(size - 65536, 0)):
            f.seek(off)
            h.update(f.read(65536))
    return h.hexdigest()


def video_xml_for(mp4):
    stem, _ = os.path.splitext(mp4)
    xml = stem + "M01.XML"
    return xml if os.path.exists(xml) else None


# ---------------------------------------------------------------- detection

def is_sony_card(root):
    dcim = os.path.join(root, "DCIM")
    if not os.path.isdir(dcim) or not os.path.isdir(os.path.join(root, "PRIVATE", "M4ROOT")):
        return False
    try:
        return any(SONY_DCIM_DIR.match(d) for d in os.listdir(dcim))
    except OSError:
        return False


def drive_of(path):
    """'/Volumes/T7/Photos' -> '/Volumes/T7'; None for folders on the internal disk."""
    parts = os.path.abspath(path).split(os.sep)
    return os.sep.join(parts[:3]) if len(parts) > 2 and parts[1] == "Volumes" else None


def detect(dest=None):
    cards = []
    for name in sorted(os.listdir("/Volumes")):
        root = os.path.join("/Volumes", name)
        if os.path.isdir(root) and is_sony_card(root):
            cards.append(root)
    drive = drive_of(dest) if dest else None
    return {
        "cards": cards,
        "dest": dest,
        "dest_drive": drive,
        "dest_drive_connected": bool(dest) and (drive is None or os.path.isdir(drive)),
        "dest_exists": bool(dest) and os.path.isdir(dest),
    }


# ---------------------------------------------------------------- card scan

def scan_card(root):
    """Return list of items. An item is one photo, one ARW+JPG pair, or one video."""
    items = []
    dcim = os.path.join(root, "DCIM")
    for d in sorted(os.listdir(dcim)):
        folder = os.path.join(dcim, d)
        if not (os.path.isdir(folder) and SONY_DCIM_DIR.match(d)):
            continue
        by_stem = {}
        for fn in sorted(os.listdir(folder)):
            if fn.startswith("."):
                continue
            stem, ext = os.path.splitext(fn)
            if ext.upper() in PHOTO_EXT:
                by_stem.setdefault(stem, []).append(os.path.join(folder, fn))
        for stem, paths in by_stem.items():
            arw = [p for p in paths if p.upper().endswith(".ARW")]
            jpg = [p for p in paths if p.upper().endswith((".JPG", ".JPEG"))]
            other = [p for p in paths if p not in arw and p not in jpg]
            if arw and jpg:
                # JPG first: if the ARW made it to the backup, the JPG did too.
                files = jpg[:1] + arw[:1]
                items.append({"kind": "pair", "card": root, "files": files,
                              "key_file": arw[0], "dt": photo_datetime(arw[0])})
                rest = jpg[1:] + arw[1:] + other
            else:
                rest = paths
            for p in rest:
                items.append({"kind": "photo", "card": root, "files": [p],
                              "key_file": p, "dt": photo_datetime(p)})
    clip = os.path.join(root, "PRIVATE", "M4ROOT", "CLIP")
    if os.path.isdir(clip):
        for fn in sorted(os.listdir(clip)):
            if fn.startswith(".") or not fn.upper().endswith(".MP4"):
                continue
            mp4 = os.path.join(clip, fn)
            xml = video_xml_for(mp4)
            items.append({"kind": "video", "card": root,
                          "files": [mp4] + ([xml] if xml else []),
                          "key_file": mp4, "dt": video_datetime(mp4, xml)})
    for it in items:
        it["size"] = sum(os.path.getsize(p) for p in it["files"])
        it["key_size"] = os.path.getsize(it["key_file"])
        it["fp"] = fingerprint(it["key_file"])
    return items


# ---------------------------------------------------------------- destination scan

class DestIndex:
    """Files already in the destination, matched by size then capture time."""

    def __init__(self, dest):
        self.dest = dest
        self.by_size = {}
        self.max_photo = 0
        self.max_video = 0
        self.file_count = 0
        self._dt_cache = {}
        self._fp_cache = {}
        if not os.path.isdir(dest):
            return
        for dirpath, dirnames, filenames in os.walk(dest):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                ext = os.path.splitext(fn)[1].upper()
                if ext not in PHOTO_EXT and ext != ".MP4":
                    continue
                p = os.path.join(dirpath, fn)
                self.file_count += 1
                self.by_size.setdefault(os.path.getsize(p), []).append(p)
                m = re.match(r"^DSC(\d+)", fn, re.I)
                if m and ext in PHOTO_EXT:
                    self.max_photo = max(self.max_photo, int(m.group(1)))
                m = re.match(r"^C(\d+)", fn, re.I)
                if m and ext == ".MP4":
                    self.max_video = max(self.max_video, int(m.group(1)))

    def _dt(self, p):
        if p not in self._dt_cache:
            if p.upper().endswith(".MP4"):
                self._dt_cache[p] = video_datetime(p, video_xml_for(p))
            else:
                self._dt_cache[p] = photo_datetime(p)
        return self._dt_cache[p]

    def _fp(self, p):
        if p not in self._fp_cache:
            self._fp_cache[p] = fingerprint(p)
        return self._fp_cache[p]

    def contains(self, item):
        ext = os.path.splitext(item["key_file"])[1].upper()
        for p in self.by_size.get(item["key_size"], []):
            if (os.path.splitext(p)[1].upper() == ext and self._dt(p) == item["dt"]
                    and self._fp(p) == item["fp"]):
                return True
        return False


# ---------------------------------------------------------------- planning

def day_folder(dest, dt):
    d = datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S")
    return os.path.join(dest, f"{d.year}", f"{d.month}. {calendar.month_name[d.month]}",
                        f"{d.day:02d}{calendar.month_abbr[d.month]}{d.year % 100:02d}")


def build_plan(dest, cards):
    index = DestIndex(dest)
    new, seen_keys, per_card = [], set(), {}
    for card in cards:
        items = scan_card(card)
        stats = {"card": card, "photos_on_card": 0, "videos_on_card": 0,
                 "already_photos": 0, "already_videos": 0, "new_photos": 0, "new_videos": 0,
                 "new_bytes": 0, "from": None, "to": None}
        for it in items:
            is_video = it["kind"] == "video"
            stats["videos_on_card" if is_video else "photos_on_card"] += len(it["files"]) if not is_video else 1
            key = (it["key_size"], it["dt"], it["fp"])
            if key in seen_keys or index.contains(it):
                stats["already_videos" if is_video else "already_photos"] += 1 if is_video else len(it["files"])
                continue
            seen_keys.add(key)
            new.append(it)
            stats["new_videos" if is_video else "new_photos"] += 1 if is_video else len(it["files"])
            stats["new_bytes"] += it["size"]
            stats["from"] = min(filter(None, [stats["from"], it["dt"]]))
            stats["to"] = max(filter(None, [stats["to"], it["dt"]]))
        per_card[card] = stats
    new.sort(key=lambda it: (it["dt"], it["key_file"]))
    photo_n, video_n = index.max_photo, index.max_video
    for it in new:
        folder = day_folder(dest, it["dt"])
        if it["kind"] == "video":
            video_n += 1
            base = f"C{video_n:0{NUM_WIDTH}d}"
            it["targets"] = []
            for src in it["files"]:
                if src.upper().endswith(".MP4"):
                    name = base + ".MP4"
                else:
                    name = base + "M01.XML"
                it["targets"].append(os.path.join(folder, "Videos", name))
        else:
            photo_n += 1
            base = f"DSC{photo_n:0{NUM_WIDTH}d}"
            it["targets"] = [os.path.join(folder, base + os.path.splitext(s)[1].upper())
                             for s in it["files"]]
    return {"dest": dest, "dest_existing_files": index.file_count,
            "cards": list(per_card.values()), "items": new}


# ---------------------------------------------------------------- copying

def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


class Progress:
    def __init__(self, total_bytes, total_files):
        self.total, self.files_total = max(total_bytes, 1), total_files
        self.done, self.files_done = 0, 0
        self.tty = sys.stdout.isatty()
        self.last_pct = -1
        self.start = time.time()

    def update(self, nbytes=0, file_done=False):
        self.done += nbytes
        self.files_done += 1 if file_done else 0
        pct = int(self.done * 100 / self.total)
        if self.tty:
            bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
            sys.stdout.write(f"\r[{bar}] {pct:3d}%  {self.files_done}/{self.files_total} files  "
                             f"{human(self.done)} / {human(self.total)}   ")
            sys.stdout.flush()
        elif pct >= self.last_pct + 5 or (file_done and self.files_done == self.files_total):
            print(f"PROGRESS {pct}% {self.files_done}/{self.files_total} files "
                  f"{human(self.done)}/{human(self.total)}", flush=True)
            self.last_pct = pct

    def finish(self):
        if self.tty:
            sys.stdout.write("\n")
        print(f"Finished in {time.time() - self.start:.0f}s", flush=True)


def copy_file(src, dst, progress):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".partial"
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        while True:
            buf = fi.read(CHUNK)
            if not buf:
                break
            fo.write(buf)
            progress.update(len(buf))
    st = os.stat(src)
    os.utime(tmp, (st.st_atime, st.st_mtime))
    if os.path.getsize(tmp) != st.st_size:
        os.remove(tmp)
        raise IOError(f"size mismatch copying {src}")
    os.rename(tmp, dst)
    progress.update(0, file_done=True)


def run_import(plan):
    items = plan["items"]
    total_files = sum(len(it["files"]) for it in items)
    progress = Progress(sum(it["size"] for it in items), total_files)
    copied, errors, pairs = [], [], []
    for it in items:
        try:
            for src, dst in zip(it["files"], it["targets"]):
                if os.path.exists(dst):
                    raise IOError(f"target already exists: {dst}")
                copy_file(src, dst, progress)
                copied.append({"src": src, "dst": dst, "dt": it["dt"]})
            if it["kind"] == "pair":
                jpg = next(t for t in it["targets"] if t.upper().endswith((".JPG", ".JPEG")))
                arw = next(t for t in it["targets"] if t.upper().endswith(".ARW"))
                pairs.append({"arw": arw, "jpg": jpg})
        except Exception as e:
            errors.append({"files": it["files"], "error": str(e)})
    progress.finish()
    by_day = {}
    for c in sorted(copied, key=lambda c: c["dt"]):
        day = os.path.relpath(day_folder(plan["dest"], c["dt"]), plan["dest"])
        kind = "videos" if c["dst"].upper().endswith(".MP4") else (
            "xml" if c["dst"].upper().endswith(".XML") else "photos")
        by_day.setdefault(day, {"photos": 0, "videos": 0, "xml": 0})[kind] += 1
    return {"dest": plan["dest"], "copied": copied, "errors": errors,
            "raw_jpg_pairs": pairs, "by_day": by_day}


def trash(paths):
    """Move files to the macOS Trash via Finder (recoverable)."""
    moved = []
    for i in range(0, len(paths), 100):
        batch = [p for p in paths[i:i + 100] if os.path.exists(p)]
        if not batch:
            continue
        files = ", ".join('POSIX file "%s"' % p.replace('"', '\\"') for p in batch)
        r = subprocess.run(["osascript", "-e", f'tell application "Finder" to delete {{{files}}}'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        moved += batch
    return moved


# ---------------------------------------------------------------- printing

def print_detect(info):
    print("Sony cards found:" if info["cards"] else "No Sony camera card found.")
    for c in info["cards"]:
        print(f"  - {c}")
    if not info["dest"]:
        print("No backup folder set (use --dest or SONY_IMPORT_DEST).")
        return
    if info["dest_drive"]:
        print(f"Backup drive {info['dest_drive']}: "
              f"{'connected' if info['dest_drive_connected'] else 'NOT connected'}")
    if info["dest_drive_connected"]:
        print(f"Backup folder {info['dest']}: {'exists' if info['dest_exists'] else 'does not exist yet'}")


def print_plan(plan):
    print(f"Destination: {plan['dest']}  ({plan['dest_existing_files']} media files already there)")
    for s in plan["cards"]:
        print(f"\nCard {s['card']}")
        print(f"  On card: {counts(s['photos_on_card'], s['videos_on_card']) or 'nothing'}")
        print(f"  Already backed up: {counts(s['already_photos'], s['already_videos']) or 'nothing'}")
        if s["new_photos"] or s["new_videos"]:
            print(f"  To back up: {counts(s['new_photos'], s['new_videos'])} "
                  f"({human(s['new_bytes'])})")
            print(f"  Shot between: {s['from'][:19]}  ->  {s['to'][:19]}")
        else:
            print("  Nothing new to back up.")
    days = {}
    for it in plan["items"]:  # items are already in capture order
        day = os.path.relpath(day_folder(plan["dest"], it["dt"]), plan["dest"])
        d = days.setdefault(day, [0, 0])
        d[1 if it["kind"] == "video" else 0] += 1 if it["kind"] == "video" else len(it["files"])
    if days:
        print("\nDay folders that will receive files:")
        for day, (p, v) in days.items():
            print(f"  {day}: {counts(p, v)}")


def counts(p, v):
    parts = [f"{p} photo{'s' * (p != 1)}"] if p else []
    parts += [f"{v} video{'s' * (v != 1)}"] if v else []
    return ", ".join(parts)


def print_report(rep):
    print(f"\nCopied {len(rep['copied'])} files into {rep['dest']}")
    for day, c in rep["by_day"].items():
        print(f"  {day}: {counts(c['photos'], c['videos'])}")
    if rep["errors"]:
        print(f"\n{len(rep['errors'])} ERRORS:")
        for e in rep["errors"]:
            print(f"  {e['files']}: {e['error']}")
    if rep["raw_jpg_pairs"]:
        print(f"\n{len(rep['raw_jpg_pairs'])} photos were shot as RAW+JPG:")
        for p in rep["raw_jpg_pairs"]:
            print(f"  {os.path.relpath(p['arw'], rep['dest'])}  +  {os.path.basename(p['jpg'])}")


# ---------------------------------------------------------------- CLI

def ask(q):
    try:
        return input(q).strip()
    except EOFError:
        return ""


def interactive(dest):
    if not dest:
        dest = os.path.expanduser(ask("Backup folder (e.g. /Volumes/MySSD/Photos/Sony Backup): "))
        if not dest:
            return 0
    info = detect(dest)
    print_detect(info)
    if not info["cards"] or not info["dest_drive_connected"]:
        print("\nConnect the missing drive(s) and run again.")
        return 1
    print(f"\nSource: {', '.join(info['cards'])}\nDestination: {dest}")
    a = ask("Use these? [y = yes / n = cancel / or type another destination path]: ")
    if a.lower() in ("n", "no", ""):
        return 0
    if a.lower() not in ("y", "yes"):
        dest = os.path.expanduser(a)
        if drive_of(dest) and not os.path.isdir(drive_of(dest)):
            print(f"{drive_of(dest)} is not connected.")
            return 1
    plan = build_plan(dest, info["cards"])
    print()
    print_plan(plan)
    if not plan["items"]:
        return 0
    if ask("\nStart copying? [y/n]: ").lower() not in ("y", "yes"):
        return 0
    rep = run_import(plan)
    print_report(rep)
    if rep["raw_jpg_pairs"] and ask("\nMove the JPG copies of these to the Trash? [y/n]: ").lower() in ("y", "yes"):
        moved = trash([p["jpg"] for p in rep["raw_jpg_pairs"]])
        print(f"Moved {len(moved)} JPGs to the Trash.")
    return 1 if rep["errors"] else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=DEFAULT_DEST, help="backup folder (interactive mode)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("detect")
    p.add_argument("--dest", default=DEFAULT_DEST)
    p.add_argument("--json", action="store_true")
    for name in ("plan", "import"):
        p = sub.add_parser(name)
        p.add_argument("--dest", default=DEFAULT_DEST)
        p.add_argument("--card", action="append", help="card root; default: all detected")
        p.add_argument("--json", action="store_true")
        if name == "import":
            p.add_argument("--report", help="write the final report JSON here")
    p = sub.add_parser("trash-jpgs")
    p.add_argument("--report", required=True)
    args = ap.parse_args()

    if args.cmd is None:
        return interactive(args.dest)
    if args.cmd == "detect":
        info = detect(args.dest)
        print(json.dumps(info, indent=2)) if args.json else print_detect(info)
        return 0
    if args.cmd == "trash-jpgs":
        with open(args.report) as f:
            rep = json.load(f)
        moved = trash([p["jpg"] for p in rep["raw_jpg_pairs"]])
        print(f"Moved {len(moved)} JPGs to the Trash.")
        return 0

    if not args.dest:
        print("No backup folder: pass --dest or set SONY_IMPORT_DEST.", file=sys.stderr)
        return 2
    cards = args.card or detect()["cards"]
    for c in cards:
        if not is_sony_card(c):
            print(f"Not a Sony camera card: {c}", file=sys.stderr)
            return 2
    if not cards:
        print("No Sony camera card found.", file=sys.stderr)
        return 2
    plan = build_plan(os.path.abspath(args.dest), cards)
    if args.cmd == "plan":
        if args.json:
            slim = {k: v for k, v in plan.items() if k != "items"}
            slim["new_items"] = len(plan["items"])
            print(json.dumps(slim, indent=2))
        else:
            print_plan(plan)
        return 0
    if not plan["items"]:
        print("Nothing new to back up.")
        return 0
    rep = run_import(plan)
    print_report(rep)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(rep, f, indent=2)
        print(f"\nReport written to {args.report}")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
