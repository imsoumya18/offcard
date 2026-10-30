#!/usr/bin/env python3
"""End-to-end test of the desktop app's backend, the way its page uses it.

Usage:  python tests/app_test.py <command to run the app...>
  e.g.  python tests/app_test.py python offcard.py
        python tests/app_test.py "dist/offcard.app/Contents/MacOS/offcard"

HDR merge needs NumPy, rawpy and Pillow wherever the app runs (the built app bundles them).
"""
import http.client, json, os, subprocess, sys, tempfile, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import make_card, make_bracket_day, EXPECTED, tree  # noqa: E402


def main():
    tool = sys.argv[1:]
    if not tool:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        card, dest, home = (os.path.join(tmp, n) for n in ("card", "backup", "home"))
        os.makedirs(home)
        make_card(card)
        urlfile = os.path.join(tmp, "url.json")
        env = {**os.environ, "HOME": home, "USERPROFILE": home, "OFFCARD_NO_UPDATE_CHECK": "1",
               "OFFCARD_TEST_CARDS": card, "OFFCARD_URL_FILE": urlfile}
        proc = subprocess.Popen(tool + ["--serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(600):
                if os.path.exists(urlfile) and os.path.getsize(urlfile):
                    break
                if proc.poll() is not None:
                    sys.exit(f"FAIL: app exited early with code {proc.returncode}")
                time.sleep(0.1)
            else:
                sys.exit("FAIL: app never started")
            info = json.load(open(urlfile))
            u = urllib.parse.urlparse(info["url"])
            host, token = u.netloc, info["token"]

            def call(path, body=None, tok=token, hdr_host=host):
                c = http.client.HTTPConnection(host, timeout=30)
                c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                          {"X-Token": tok, "Host": hdr_host, "Content-Type": "application/json"})
                r = c.getresponse()
                return r.status, (json.loads(r.read() or b"{}") if path.startswith("/api") else r.read())

            def wait(kind, key="job"):
                for _ in range(600):
                    st, s = call("/api/state")
                    j = s[key]
                    if j and j["kind"] == kind and j["state"] != "running":
                        if j["state"] == "error":
                            sys.exit(f"FAIL: {kind}: {j['error']}")
                        return j["result"]
                    time.sleep(0.1)
                sys.exit(f"FAIL: {kind} never finished")

            # Security: no token, wrong token, or a foreign Host header are all refused.
            assert call("/api/state", tok="")[0] == 403, "no token"
            assert call("/api/state", tok="wrong")[0] == 403, "wrong token"
            assert call("/api/state", hdr_host="evil.example:80")[0] == 403, "foreign host"
            assert call("/?t=wrong")[0] == 403 and call(f"/?t={token}")[0] == 200, "page token"

            st, s = call("/api/state")
            assert st == 200 and s["cards"] and s["cards"][0]["photos"] == 5 and s["dest"] is None, s
            assert call("/api/dest", {"path": dest})[0] == 200
            call("/api/plan", {})
            plan = wait("plan")
            assert plan["new_photos"] == 5 and plan["new_videos"] == 1 and plan["enough_space"], plan
            # the folder preview: every file lands in a leaf, and nothing there exists yet
            def leaves(n, path=()):
                path = path + (n["name"],)
                return [(path, n["files"], n["new"])] if not n["children"] else \
                    [x for c in n["children"] for x in leaves(c, path)]
            got = leaves(plan["tree"])
            assert sum(f for _, f, _ in got) == plan["new_files"] and all(new for *_, new in got), got
            assert all(p[-1] in ("Photos", "Videos") and len(p) == 5 for p, _, _ in got), got
            call("/api/import", {})
            rep = wait("import")
            assert rep["photos"] == 5 and rep["videos"] == 1 and not rep["errors"] and rep["raw_jpg_pairs"] == 1, rep
            got = tree(dest)
            assert got == EXPECTED, f"backup tree: missing {EXPECTED - got}, extra {got - EXPECTED}"
            call("/api/verify", {})
            ver = wait("verify")
            assert ver["safe"] and ver["cards"][0]["verified"] == 7, ver
            st, ej = call("/api/eject", {})  # the test card is a folder, so eject must refuse
            assert st == 200 and not ej["results"][0]["ejected"], ej
            call("/api/reset", {})
            call("/api/plan", {})
            again = wait("plan")
            assert again["new_files"] == 0 and again["already_photos"] == 5, again

            # HDR Merge: a folder is searched with its subfolders in the background, a folder on
            # a memory card is refused, and a merge of fake RAW files fails cleanly, set by set.
            make_bracket_day(os.path.join(dest, "2026", "3. March", "01Mar26"))
            assert call("/api/hdr/folder", {"path": card})[0] == 400, "a folder on a card must be refused"
            st, r = call("/api/hdr/folder", {"path": dest})
            assert st == 200, r
            st, s = call("/api/state")
            assert s["hdr_missing"] is None, s["hdr_missing"]
            assert s["hdr_folder"] == dest and s["hdr_folder_exists"], s
            call("/api/hdr/scan", {})
            scan = wait("scan", key="hdr_job")
            assert scan["sets"] == 2, scan
            st, sets = call("/api/hdr/sets")
            assert [x["folder"] for x in sets["sets"]] == [os.path.join("2026", "3. March", "01Mar26")] * 2, sets
            assert [len(x["names"]) for x in sets["sets"]] == [3, 3] and not any(x["done"] for x in sets["sets"]), sets
            st, r = call("/api/hdr/merge", {"ids": [0], "tiff": False})
            assert st == 200, r
            res = wait("merge", key="hdr_job")
            assert res["merged"] == 0 and len(res["failed"]) == 1, res
            assert not os.path.exists(os.path.join(dest, "2026", "3. March", "HDR")), "a failed merge left an HDR folder"
            assert not os.path.exists(os.path.join(dest, "2026", "3. March", "01Mar26", "HDR")), "a failed merge left an HDR folder"

            # Day tags and choosing files: into a fresh folder, tag one day, back up one file of
            # it, then the rest; everything for that day lands in "05Jan26 - Birth Day".
            dest2 = os.path.join(tmp, "backup2")
            assert call("/api/dest", {"path": dest2})[0] == 200
            call("/api/reset", {})
            call("/api/plan", {})
            wait("plan")
            st, items = call("/api/plan/items")
            assert st == 200 and len(items["items"]) == 5, items
            first = items["items"][0]
            st, summary = call("/api/tag", {"day": first["day"], "tag": " Birth/Day: "})
            assert st == 200, summary
            day = next(d for d in summary["days"] if d["key"] == first["day"])
            assert day["tag"] == "Birth Day" and day["folder"].endswith(first["day"] + " - Birth Day"), day
            st, s = call("/api/state")
            assert s["recent_tags"][0] == "Birth Day" and s["job"]["result"]["days"] == summary["days"], s["recent_tags"]
            st, th = call("/api/plan/thumbs", {"ids": [first["id"]]})
            assert st == 200 and str(first["id"]) in th["thumbs"], th
            assert call("/api/import", {"ids": []})[0] == 400, "an empty choice must be refused"
            call("/api/import", {"ids": [first["id"]]})
            part = wait("import")
            assert part["files"] == len(first["names"]) and not part["errors"], part
            folder = os.path.join(dest2, day["folder"])
            assert os.path.isdir(folder), sorted(os.listdir(dest2))
            assert any(f.startswith("DSC00001.") or f.startswith("C00001") for _, _, fs in os.walk(folder) for f in fs), "the chosen file starts at 1"
            call("/api/reset", {})
            call("/api/plan", {})
            rest = wait("plan")
            assert rest["new_files"] == 5 * 0 + sum(len(i["names"]) for i in items["items"][1:]), rest
            again = next((d for d in rest["days"] if d["key"] == first["day"]), None)
            assert again is None or again["tag"] == "Birth Day", again
            call("/api/import", {})
            wait("import")
            assert not [n for n in os.listdir(os.path.dirname(folder)) if n.startswith(first["day"]) and n != os.path.basename(folder)], \
                "a second folder was made for a tagged day"
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()

        # The HDR merge itself, on synthetic frames, inside this very app (bundled libraries too).
        os.remove(urlfile)
        r = subprocess.run(tool + ["--hdr-selftest"], env=env, capture_output=True, text=True, timeout=600)
        out = open(urlfile).read() if os.path.exists(urlfile) else r.stdout
        if r.returncode != 0 or out.strip() != "PASS":
            sys.exit(f"FAIL: HDR self-test: {out.strip() or r.stderr[-2000:]}")
    print("PASS")


if __name__ == "__main__":
    main()
