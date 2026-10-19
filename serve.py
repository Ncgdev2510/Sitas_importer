"""
Servidor local simple para visualizar el dashboard web de SITAS Cestoball.

Uso:
    python serve.py
    python serve.py --port 8080
"""

import argparse
import http.server
import socketserver
import webbrowser
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        if self.path in ("/admin", "/admin/"):
            self.path = "/admin.html"
        return super().do_GET()


def start_server(port: int = 8000, open_browser: bool = True):
    url = f"http://localhost:{port}"
    print(f"\n[+] Servidor del Dashboard de SITAS Cestoball iniciado en: {url}")
    print("[-] Sirviendo archivos desde:", WEB_DIR)
    print("[-] Presiona Ctrl+C para detener el servidor.\n")

    if open_browser:
        webbrowser.open(url)

    with socketserver.TCPServer(("", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicia el servidor local del Dashboard Web")
    parser.add_argument("--port", type=int, default=8000, help="Puerto HTTP (por defecto 8000)")
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador automáticamente")
    args = parser.parse_args()

    start_server(port=args.port, open_browser=not args.no_browser)
