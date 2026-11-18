"""Local-only web fixture with predictable asynchronous HTTP responses."""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Keep experiment output clean.

    def send_content(self, content: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_content((FIXTURES / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/app.js":
            self.send_content((FIXTURES / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        elif parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0][:80]
            # Use fixed timings so requests can intentionally finish out of order.
            delays = {"old": 0.350, "new": 0.035, "fail": 0.045}
            time.sleep(delays.get(query, 0.050))
            if query == "fail":
                self.send_content(json.dumps({"error": "Deliberate test failure"}).encode(),
                                  "application/json", 503)
            else:
                self.send_content(json.dumps({"query": query, "items": [query]}).encode(),
                                  "application/json")
        else:
            self.send_content(b"Not found", "text/plain", 404)


def create_server(port: int = 8765):
    return ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)


def main():
    server = create_server()
    print("Fixture running at http://127.0.0.1:8765/?mode=buggy")
    print("Fixed version:   http://127.0.0.1:8765/?mode=fixed")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
