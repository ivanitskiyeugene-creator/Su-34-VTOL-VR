"""Static server for the cockpit preview.

Serves the repository root so the viewer can read assets/model/* directly,
and binds 0.0.0.0 so the preview proxy can reach it.

    python tools/cockpit_viewer/serve.py [port]
"""
import http.server
import os
import socketserver
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


VIEWER = "/tools/cockpit_viewer/index.html"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_GET(self):
        # the live preview opens the bare host root - send it to the viewer
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", VIEWER)
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", PORT), Handler) as httpd:
        print("cockpit preview: http://localhost:%d/tools/cockpit_viewer/index.html" % PORT, flush=True)
        httpd.serve_forever()
