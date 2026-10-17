#!/usr/bin/env python3
"""End-to-end test: build a fake Sony card, import it, check the result.

Usage:  python tests/smoke_test.py <command to run sony-import...>
  e.g.  python tests/smoke_test.py python sony-import.py
        python tests/smoke_test.py ./dist/sony-import
"""
import json
import os
import random
import struct
import subprocess
import sys
import tempfile


def tiff_with_date(dt, pad):
    """Minimal little-endian TIFF: IFD0 -> Exif IFD -> DateTimeOriginal, then random padding."""
    date = dt.encode() + b"\0"                      # 20 bytes
    ifd0 = 8
    exif_ifd = ifd0 + 2 + 12 + 4
    date_off = exif_ifd + 2 + 12 + 4
    t = b"II*\0" + struct.pack("<I", ifd0)
    t += struct.pack("<H", 1) + struct.pack("<HHII", 0x8769, 4, 1, exif_ifd) + struct.pack("<I", 0)
    t += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, len(date), date_off) + struct.pack("<I", 0)
    return t + date + os.urandom(pad)


def jpeg_with_date(dt, pad):
    exif = b"Exif\0\0" + tiff_with_date(dt, 0)
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + b"\xff\xd9" + os.urandom(pad)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def make_card(root):
    dcim = os.path.join(root, "DCIM", "100MSDCF")
    write(os.path.join(dcim, "DSC00010.ARW"), tiff_with_date("2026:01:05 10:00:00", 300_000))
    write(os.path.join(dcim, "DSC00010.JPG"), jpeg_with_date("2026:01:05 10:00:00", 100_000))
    write(os.path.join(dcim, "DSC00011.ARW"), tiff_with_date("2026:02:10 09:00:00", 300_000))
    # Burst: same size, same second, different content -> both must be kept.
    write(os.path.join(dcim, "DSC00012.ARW"), tiff_with_date("2026:02:10 09:00:01", 300_000))
    write(os.path.join(dcim, "DSC00013.ARW"), tiff_with_date("2026:02:10 09:00:01", 300_000))
    clip = os.path.join(root, "PRIVATE", "M4ROOT", "CLIP")
    write(os.path.join(clip, "C0001.MP4"), os.urandom(500_000))
    write(os.path.join(clip, "C0001M01.XML"),
          b'<?xml version="1.0"?><NonRealTimeMeta><CreationDate value="2026-01-05T12:00:00+05:30"/>'
          b"</NonRealTimeMeta>")


EXPECTED = {
    ("2026", "1. January", "05Jan26", "DSC00001.ARW"),
    ("2026", "1. January", "05Jan26", "DSC00001.JPG"),
    ("2026", "1. January", "05Jan26", "Videos", "C00001.MP4"),
    ("2026", "1. January", "05Jan26", "Videos", "C00001M01.XML"),
    ("2026", "2. February", "10Feb26", "DSC00002.ARW"),
    ("2026", "2. February", "10Feb26", "DSC00003.ARW"),
    ("2026", "2. February", "10Feb26", "DSC00004.ARW"),
}


def run(cmd):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout, r.stderr, sep="", flush=True)
    if r.returncode != 0:
        sys.exit(f"FAIL: exit code {r.returncode}")
    return r.stdout


def tree(dest):
    got = set()
    for dirpath, _, files in os.walk(dest):
        for fn in files:
            got.add(tuple(os.path.relpath(os.path.join(dirpath, fn), dest).split(os.sep)))
    return got


def check_tree(dest, what):
    got = tree(dest)
    if got != EXPECTED:
        sys.exit(f"FAIL ({what}): unexpected backup tree\n  missing: {EXPECTED - got}\n  extra: {got - EXPECTED}")


def new_items(tool, dest, card):
    return json.loads(run(tool + ["plan", "--dest", dest, "--card", card, "--json"]))["new_items"]


DAY = ("2026", "1. January", "05Jan26")
# A file deleted from the backup -> the next run must put back exactly that file, same name.
REPAIRS = [
    DAY + ("Videos", "C00001M01.XML"),   # video there, its XML missing
    DAY + ("Videos", "C00001.MP4"),      # XML there, its video missing
    DAY + ("DSC00001.ARW",),             # JPG of a RAW+JPG pair there, RAW missing
]


def main():
    tool = sys.argv[1:]
    if not tool:
        sys.exit(__doc__)
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmp:
        card, dest = os.path.join(tmp, "card"), os.path.join(tmp, "backup")
        make_card(card)
        run(tool + ["plan", "--dest", dest, "--card", card])
        run(tool + ["import", "--dest", dest, "--card", card])
        check_tree(dest, "first import")
        if new_items(tool, dest, card) != 0:
            sys.exit("FAIL: second run wants to copy files again")

        for rel in REPAIRS:
            os.remove(os.path.join(dest, *rel))
            run(tool + ["import", "--dest", dest, "--card", card])
            check_tree(dest, "after deleting " + "/".join(rel))

        # A single photo deleted -> copied back once (it has no partner to take a number from,
        # so it gets the next free number).
        feb = os.path.join(dest, "2026", "2. February", "10Feb26")
        os.remove(os.path.join(feb, "DSC00003.ARW"))
        run(tool + ["import", "--dest", dest, "--card", card])
        if sorted(os.listdir(feb)) != ["DSC00002.ARW", "DSC00004.ARW", "DSC00005.ARW"]:
            sys.exit(f"FAIL: deleted single photo not restored exactly once: {sorted(os.listdir(feb))}")
        if new_items(tool, dest, card) != 0:
            sys.exit("FAIL: restored photo would be copied again")

        # Renamed in the backup -> still recognised, nothing copied.
        os.rename(os.path.join(dest, *DAY, "DSC00001.ARW"), os.path.join(dest, *DAY, "renamed.ARW"))
        if new_items(tool, dest, card) != 0:
            sys.exit("FAIL: a renamed backup file was not recognised")
        os.rename(os.path.join(dest, *DAY, "renamed.ARW"), os.path.join(dest, *DAY, "DSC00001.ARW"))

        # JPG of a RAW+JPG pair removed on purpose (the Trash option) -> not brought back.
        os.remove(os.path.join(dest, *DAY, "DSC00001.JPG"))
        if new_items(tool, dest, card) != 0:
            sys.exit("FAIL: a JPG that was removed on purpose would be copied again")
    print("PASS")


if __name__ == "__main__":
    main()
