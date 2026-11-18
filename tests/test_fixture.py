"""Small unit-level smoke test of the local API, independent of a browser."""
import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

from webstatecheck.server import create_server


def test_fixture_api_success_and_failure():
    httpd = create_server(0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urlopen(base + "/api/search?q=hello", timeout=5) as response:
            assert json.loads(response.read())["query"] == "hello"
        try:
            urlopen(base + "/api/search?q=fail", timeout=5)
        except HTTPError as exc:
            assert exc.code == 503
        else:
            raise AssertionError("Expected a deliberate HTTP 503")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
