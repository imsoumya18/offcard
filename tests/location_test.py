#!/usr/bin/env python3
"""What kind of place a backup folder is, and that a memory card is never allowed as one.

Usage:  python tests/location_test.py
"""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, ".."), HERE]
import engine as E                     # noqa: E402
from smoke_test import make_card       # noqa: E402

MAC = ["/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)",
       "/dev/disk4s2 on /Volumes/Soumya_T7 (exfat, local, nodev, nosuid, noowners)",
       "//me@nas._smb._tcp.local/Photo Share on /Volumes/Photo Share (smbfs, nodev, nosuid, mounted by me)"]
LINUX = ["/dev/nvme0n1p2 / ext4 rw,relatime 0 0", "/dev/sda1 /media/me/T7 exfat rw 0 0",
         "nas:/export /mnt/nas nfs4 rw,relatime 0 0", "//nas/Photo /mnt/photo\\040share cifs rw 0 0"]
CASES = [(MAC, "/Users/me/Pictures", False), (MAC, "/Volumes/Soumya_T7/Sony Backup", False),
         (MAC, "/Volumes/Photo Share/Sony", True), (MAC, "/Volumes/Photo Share", True), (MAC, "/Volumes/Photo Sharing", False),
         (LINUX, "/home/me/Pictures", False), (LINUX, "/media/me/T7/Sony", False), (LINUX, "/mnt/nas/Sony", True),
         (LINUX, "/mnt/photo share/x", True), (LINUX, "/mnt/nasty", False)]


def main():
    for mounts, path, want in CASES:
        if E._mounted_network(mounts, path) != want:
            sys.exit(f"FAIL: {path} should be {'network' if want else 'local'}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        if E.location_kind(tmp) not in ("internal", "external"):
            sys.exit(f"FAIL: {tmp} is {E.location_kind(tmp)}")
        card = os.path.join(tmp, "card")
        make_card(card)
        for dest in (card, os.path.join(card, "DCIM"), os.path.join(card, "new", "folder")):
            try:
                E.build_plan(dest, [card])
            except RuntimeError as e:
                if "memory card" not in str(e):
                    raise
            else:
                sys.exit(f"FAIL: backing up onto the card was allowed: {dest}")
        if any(n in os.listdir(card) for n in ("new", "Photos", "2026")):
            sys.exit("FAIL: something was written to the card")
    print("PASS")


if __name__ == "__main__":
    main()
