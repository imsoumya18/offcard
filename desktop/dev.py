#!/usr/bin/env python3
"""Try the Windows panel in a browser on any system, on the real engine, without the Tauri app:

    python3 desktop/dev.py [port]        then open http://127.0.0.1:4179/

It starts offcard.py --serve, serves desktop/panel, and passes /api/ calls on with the token, the
way the app does. OFFCARD_TEST_CARDS and the rest of the engine's settings carry through.
"""
import http.client, http.server, json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4179
urlfile = os.path.join(tempfile.mkdtemp(), "url.json")
engine = subprocess.Popen([sys.executable, os.path.join(HERE, "..", "offcard.py"), "--serve", "--agent"],
                          env={**os.environ, "OFFCARD_URL_FILE": urlfile}, stdout=subprocess.DEVNULL)
while not (os.path.exists(urlfile) and os.path.getsize(urlfile)):
    time.sleep(0.1)
info = json.load(open(urlfile))
host, token = info["url"].split("/")[2], info["token"]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(HERE, "panel"), **k)

    def log_message(self, *a):
        pass

    def _pass_on(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        c = http.client.HTTPConnection(host, timeout=60)
        c.request(method, self.path, self.rfile.read(n) if n else None, {"X-Token": token, "Host": host})
        r = c.getresponse()
        body = r.read()
        self.send_response(r.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._pass_on("GET") if self.path.startswith("/api/") else super().do_GET()

    def do_POST(self):
        self._pass_on("POST")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


try:
    print(f"http://127.0.0.1:{PORT}/", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
finally:
    engine.terminate()
