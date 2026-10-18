"""
P2P Tunnel Standalone Ultra-Lightweight HTTP Rendezvous Signaling Server.
Runs on any VPS, cloud instance, or locally with zero external dependencies.
"""

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# In-memory storage for rooms: { room_id: { role: { "data": blob, "updated_at": ts } } }
ROOMS = {}


class RendezvousHandler(BaseHTTPRequestHandler):
    def _send_response_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/register":
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)
            try:
                req_json = json.loads(raw_body.decode("utf-8"))
                room = req_json.get("room")
                encrypted_blob = req_json.get("data")
                if not room or not encrypted_blob:
                    self._send_response_json(400, {"error": "Missing room or data"})
                    return

                now = time.time()
                if room not in ROOMS:
                    ROOMS[room] = {}

                # We store the blob per room
                ROOMS[room]["latest"] = encrypted_blob
                ROOMS[room]["updated_at"] = now
                self._send_response_json(200, {"status": "registered"})
            except Exception as e:
                self._send_response_json(500, {"error": str(e)})
        else:
            self._send_response_json(404, {"error": "Not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/query":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            if not room or room not in ROOMS or "latest" not in ROOMS[room]:
                self._send_response_json(404, {"error": "No peer registered yet"})
                return

            self._send_response_json(200, {"data": ROOMS[room]["latest"]})
        elif parsed.path == "/health":
            self._send_response_json(200, {"status": "ok", "rooms_count": len(ROOMS)})
        else:
            self._send_response_json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        return


def run_signaling_server(host: str = "0.0.0.0", port: int = 8765):
    server = HTTPServer((host, port), RendezvousHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_signaling_server()
