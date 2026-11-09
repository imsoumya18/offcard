#!/usr/bin/env python3
"""Changing the backup folder while the card is being checked stops that check, and the next one is
for the new folder; while a backup runs, the folder can't change.

Usage:  python tests/dest_change_test.py <command to run the app...>
  e.g.  python tests/dest_change_test.py python offcard.py
"""
import http.client, json, os, subprocess, sys, tempfile, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import make_card  # noqa: E402


def main():
    tool = sys.argv[1:]
    if not tool:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        card, home = os.path.join(tmp, "card"), os.path.join(tmp, "home")
        a, b, c, d = (os.path.join(tmp, n) for n in "abcd")
        os.makedirs(home)
        make_card(card)
        urlfile = os.path.join(tmp, "url.json")
        env = {**os.environ, "HOME": home, "USERPROFILE": home, "OFFCARD_NO_UPDATE_CHECK": "1", "OFFCARD_TEST_CARDS": card,
               "OFFCARD_URL_FILE": urlfile, "OFFCARD_TEST_SLOW": "0.6"}
        proc = subprocess.Popen(tool + ["--serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(600):
                if os.path.exists(urlfile) and os.path.getsize(urlfile):
                    break
                time.sleep(0.1)
            info = json.load(open(urlfile))
            host, token = urllib.parse.urlparse(info["url"]).netloc, info["token"]

            def call(path, body=None):
                conn = http.client.HTTPConnection(host, timeout=60)
                conn.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                             {"X-Token": token, "Host": host, "Content-Type": "application/json"})
                r = conn.getresponse()
                return r.status, json.loads(r.read() or b"{}")

            def job():
                return call("/api/state")[1]["job"]

            def wait_done():
                for _ in range(600):
                    j = job()
                    if j and j["state"] != "running":
                        return j
                    time.sleep(0.1)
                sys.exit("FAIL: the check never finished")

            assert call("/api/dest", {"path": a})[0] == 200
            assert call("/api/plan", {})[0] == 200
            time.sleep(0.8)
            assert job()["state"] == "running", "the check should still be running"
            for path in ("/api/update/check", "/api/update"):     # no updating while something runs
                st, r = call(path, {})
                assert st == 400 and "finishes" in r["error"], (path, r)

            # Change the folder mid-check, three times quickly: each stops the check that's running.
            for dest in (b, c, d):
                t = time.time()
                st, r = call("/api/dest", {"path": dest})
                assert st == 200, r
                assert time.time() - t < 5, "stopping the check took too long"
                assert job() is None, "the old check is still there"
                if dest != d:
                    assert call("/api/plan", {})[0] == 200
                    time.sleep(0.7)
            assert call("/api/plan", {})[0] == 200
            j = wait_done()
            s = call("/api/state")[1]
            assert j["state"] == "done" and j["result"]["new_files"] == 7, j
            assert s["plan_for"][1] == d and s["dest"] == d, s["plan_for"]
            assert not any(os.path.exists(x) for x in (a, b, c, d)), "a check wrote to a folder"

            # While backing up, the folder stays put.
            assert call("/api/import", {})[0] == 200
            time.sleep(0.5)
            assert job()["kind"] == "import" and job()["state"] == "running"
            st, r = call("/api/dest", {"path": a})
            assert st == 400 and "Wait" in r["error"], r
            j = wait_done()
            assert j["state"] == "done" and call("/api/state")[1]["dest"] == d
            print("PASS")
        finally:
            proc.terminate()


if __name__ == "__main__":
    main()
