#!/usr/bin/env python3
"""End-to-end test: build a fake Sony card, import it, check the result.

Usage:  python tests/smoke_test.py <command to run the engine...>
  e.g.  python tests/smoke_test.py python engine.py
"""
import json
import os
import pathlib
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


def tiff_with_exposure(dt, exposure, bias, pad, model="ILCE-6600", focal=16.0):
    """Minimal little-endian TIFF like a Sony RAW: IFD0 (Model) -> Exif IFD (DateTimeOriginal,
    ExposureTime, ExposureBiasValue, FocalLength), then random padding."""
    model_b = model.encode() + b"\0"
    date = dt.encode() + b"\0"
    ifd0 = 8
    exif_ifd = ifd0 + 2 + 2 * 12 + 4
    data = exif_ifd + 2 + 4 * 12 + 4
    blobs = [model_b, date, struct.pack("<II", *exposure), struct.pack("<ii", round(bias * 10), 10),
             struct.pack("<II", round(focal * 10), 10)]
    offs, o = [], data
    for b in blobs:
        offs.append(o)
        o += len(b)
    t = b"II*\0" + struct.pack("<I", ifd0)
    t += struct.pack("<H", 2) + struct.pack("<HHII", 0x0110, 2, len(model_b), offs[0]) \
        + struct.pack("<HHII", 0x8769, 4, 1, exif_ifd) + struct.pack("<I", 0)
    t += struct.pack("<H", 4) + struct.pack("<HHII", 0x829A, 5, 1, offs[2]) \
        + struct.pack("<HHII", 0x9003, 2, len(date), offs[1]) + struct.pack("<HHII", 0x9204, 10, 1, offs[3]) \
        + struct.pack("<HHII", 0x920A, 5, 1, offs[4]) + struct.pack("<I", 0)
    return t + b"".join(blobs) + os.urandom(pad)


def make_bracket_day(folder):
    """Two exposure-bracketed sets with an ordinary burst between them (which isn't one)."""
    shots = [("10:00:00", (1, 100), 0), ("10:00:00", (1, 400), -2), ("10:00:01", (1, 25), 2),   # set 1
             ("10:00:06", (1, 100), 0), ("10:00:06", (1, 100), 0), ("10:00:07", (1, 100), 0),   # burst
             ("10:00:12", (1, 800), -3), ("10:00:12", (1, 100), 0), ("10:00:13", (1, 13), 3)]   # set 2
    for i, (hms, exp, bias) in enumerate(shots):
        write(os.path.join(folder, f"DSC{100 + i:05d}.ARW"),
              tiff_with_exposure(f"2026:03:01 {hms}", exp, bias, 20_000))


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


def run(cmd, env=None, expect=0):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    print(r.stdout, r.stderr, sep="", flush=True)
    if r.returncode != expect:
        sys.exit(f"FAIL: exit code {r.returncode}, expected {expect}")
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


def verify(tool, dest, card, expect):
    res = json.loads(run(tool + ["verify", "--dest", dest, "--card", card, "--json"], expect=expect))
    st = res["cards"][0]
    return res["safe"], len(st["missing"]), len(st["different"]), len(st["trashed_jpg"]), st["verified"]


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

        # Backup drive too full -> plan says so, import copies nothing and exits with code 3.
        full = {"SHOTLOFT_TEST_FREE_BYTES": "1000"}
        plan = json.loads(run(tool + ["plan", "--dest", dest, "--card", card, "--json"], env=full))
        if plan["enough_space"] or plan["needed_bytes"] <= 0:
            sys.exit(f"FAIL: a full drive was not detected: {plan}")
        run(tool + ["import", "--dest", dest, "--card", card], env=full, expect=3)
        if os.path.exists(dest) and tree(dest):
            sys.exit("FAIL: files were copied although the drive was full")

        run(tool + ["plan", "--dest", dest, "--card", card])
        run(tool + ["import", "--dest", dest, "--card", card])
        check_tree(dest, "first import")
        if new_items(tool, dest, card) != 0:
            sys.exit("FAIL: second run wants to copy files again")

        # "Safe to format" check: everything verified byte for byte.
        if verify(tool, dest, card, 0) != (True, 0, 0, 0, 7):
            sys.exit(f"FAIL: verify after import: {verify(tool, dest, card, 0)}")
        # One byte changed where the quick fingerprint doesn't look -> caught as different.
        victim = os.path.join(dest, "2026", "2. February", "10Feb26", "DSC00002.ARW")
        with open(victim, "r+b") as f:
            f.seek(100_000); b = f.read(1); f.seek(100_000); f.write(bytes([b[0] ^ 0xFF]))
        if verify(tool, dest, card, 1)[:3] != (False, 0, 1):
            sys.exit("FAIL: a damaged backup copy was not detected")
        with open(victim, "r+b") as f:
            f.seek(100_000); f.write(b)
        # A backup file missing -> caught as missing.
        moved = victim + ".away"
        os.rename(victim, moved)
        if verify(tool, dest, card, 1)[:3] != (False, 1, 0):
            sys.exit("FAIL: a missing backup file was not detected")
        os.rename(moved, victim)

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
        if verify(tool, dest, card, 0)[:4] != (True, 0, 0, 1):
            sys.exit("FAIL: a JPG removed on purpose should not make the card unsafe")

        # HDR merges live in the day's HDR folder and are never taken for backed-up files.
        hdr_dir = os.path.join(feb, "HDR")
        os.makedirs(hdr_dir)
        os.rename(os.path.join(feb, "DSC00002.ARW"), os.path.join(hdr_dir, "DSC00002.ARW"))
        if verify(tool, dest, card, 1)[:3] != (False, 1, 0):
            sys.exit("FAIL: a file inside an HDR folder counted as backed up")
        os.rename(os.path.join(hdr_dir, "DSC00002.ARW"), os.path.join(feb, "DSC00002.ARW"))
        os.rmdir(hdr_dir)

        # Bracket sets for HDR, searched through subfolders: two sets found, the burst between them
        # isn't one, and a copy of the same shots in another folder makes its own two sets.
        root = os.path.join(tmp, "brackets")
        day = os.path.join(root, "2026", "01Mar26")
        make_bracket_day(day)
        make_bracket_day(os.path.join(root, "copy"))
        sets = json.loads(run(tool + ["brackets", "--folder", root, "--json"]))
        got = [(os.path.relpath(s["folder"], root), s["names"], s["biases"], os.path.basename(s["output"]), s["done"])
               for s in sets]
        one = ["DSC00100.ARW", "DSC00101.ARW", "DSC00102.ARW"], [0.0, -2.0, 2.0], "DSC00100-00102_HDR.jpg", False
        two = ["DSC00106.ARW", "DSC00107.ARW", "DSC00108.ARW"], [-3.0, 0.0, 3.0], "DSC00106-00108_HDR.jpg", False
        day_rel = os.path.join("2026", "01Mar26")
        want = [(day_rel, *one), (day_rel, *two), ("copy", *one), ("copy", *two)]
        if sorted(got) != sorted(want):
            sys.exit(f"FAIL: bracket sets: {got}")
        write(os.path.join(day, "HDR", "DSC00100-00102_HDR.jpg"), b"x")
        done = {(os.path.relpath(s["folder"], root), s["names"][0]): s["done"]
                for s in json.loads(run(tool + ["brackets", "--folder", root, "--json"]))}
        if [k for k, v in done.items() if v] != [(day_rel, "DSC00100.ARW")]:
            sys.exit(f"FAIL: a merged set isn't shown as merged: {done}")

        # Eject refuses anything that isn't a mounted drive (here: the fake card folder).
        out = run(tool + ["eject", "--card", card], expect=1)
        if "not the top of a mounted drive" not in out:
            sys.exit(f"FAIL: eject should refuse a plain folder: {out}")

        # Update notice: a newer release is reported, an older or equal one isn't, offline is quiet.
        for tag, expected in (("v99.0.0", True), ("v0.0.1", False)):
            fake = os.path.join(tmp, "latest.json")
            with open(fake, "w") as f:
                json.dump({"tag_name": tag}, f)
            out = json.loads(run(tool + ["check-update", "--json"],
                                 env={"SHOTLOFT_UPDATE_URL": pathlib.Path(fake).as_uri()}))
            if out["update_available"] != expected or out["latest"] != tag[1:]:
                sys.exit(f"FAIL: update check with {tag}: {out}")
        missing = pathlib.Path(tmp, "nope.json").as_uri()
        out = json.loads(run(tool + ["check-update", "--json"], env={"SHOTLOFT_UPDATE_URL": missing}))
        if out["latest"] is not None or out["update_available"]:
            sys.exit(f"FAIL: offline update check should be quiet: {out}")
    print("PASS")


if __name__ == "__main__":
    main()
