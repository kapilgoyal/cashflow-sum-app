from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json


def _parse_numbers(a, b):
    return float(a), float(b)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json(status, {"error": message})

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            if "a" not in qs or "b" not in qs:
                self._send_error(400, "query params a and b are required")
                return
            a, b = _parse_numbers(qs["a"][0], qs["b"][0])
            self._send_json(200, {"sum": a + b})
        except (TypeError, ValueError) as e:
            self._send_error(400, str(e))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if "a" not in data or "b" not in data:
                self._send_error(400, "JSON body must include a and b")
                return
            a, b = _parse_numbers(data["a"], data["b"])
            self._send_json(200, {"sum": a + b})
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            self._send_error(400, str(e))

    def log_message(self, format, *args):
        return
