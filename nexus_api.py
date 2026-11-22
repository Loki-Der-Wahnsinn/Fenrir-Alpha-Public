import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PORT = int(os.environ.get("FENRIR_NEXUS_PORT", "3000"))
HOST = os.environ.get("FENRIR_NEXUS_HOST", "127.0.0.1")
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Fenrir-OS", "nexus-manager")


class NexusHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def _is_trusted_request(self) -> bool:
        host = self.headers.get("Host", "").strip().lower().split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost", "[::1]"}:
            self.send_response(400)
            self.end_headers()
            return False
        origin = self.headers.get("Origin", "").strip()
        if origin:
            from urllib.parse import urlparse

            parsed = urlparse(origin)
            if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
                self.send_response(403)
                self.end_headers()
                return False
        return True

    def do_GET(self):
        if not self._is_trusted_request():
            return
        super().do_GET()

    def do_POST(self):
        if not self._is_trusted_request():
            return
        if self.path == "/api/swarm":
            content_length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(content_length)
            response_data = {
                "analysis": "<p>Swarm-Engine Status bereit.</p>",
                "code": "<p>Warte auf gepruefte Aufgaben...</p>",
                "fenrir": "<p>Lokal verbunden.</p>",
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_nexus_server():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer((HOST, PORT), NexusHandler) as httpd:
            print(f"[NEXUS-OS] Dashboard Server lauscht auf http://{HOST}:{PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[NEXUS-OS] Konnte Server nicht starten: {e}")


def start_nexus_in_background():
    thread = threading.Thread(target=run_nexus_server, daemon=True)
    thread.start()


if __name__ == "__main__":
    run_nexus_server()
