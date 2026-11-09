"""Dashboard web local: monitoreo y ABM de variables.

Usa http.server de la stdlib en lugar de FastAPI: FastAPI arrastra pydantic, y
pydantic-core es una extension en Rust sin wheel para el interprete instalado.
Para una pagina y un par de endpoints en localhost la stdlib alcanza, y deja el
despliegue en la PC de planta sin dependencias nativas.

Endpoints:
    GET  /               la pagina
    GET  /api/estado     estado vivo (PLCs, tags, DB, buffer)
    GET  /api/tags       lista de tags configurados + PLCs disponibles
    POST /api/tags       reemplaza la lista de tags, valida y recarga en caliente
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loguru import logger

from src.core.config import ErrorConfig

_ESTATICOS = Path(__file__).parent / "static"
_MAX_CUERPO = 1 << 20   # 1 MB: mas que de sobra para una lista de tags


def _handler(servicio):
    class Handler(BaseHTTPRequestHandler):
        server_version = "scadaMtto"

        # ------------------------------------------------------------ GET
        def do_GET(self):  # noqa: N802  (lo impone BaseHTTPRequestHandler)
            if self.path.startswith("/api/estado"):
                self._json(200, servicio.sup.snapshot())
            elif self.path.startswith("/api/tags"):
                self._json(200, {
                    "tags": servicio.tags(),
                    "plcs": servicio.plcs_disponibles(),
                    "modo_db": servicio.sink.modo,
                    "destino_db": servicio.sink.destino,
                })
            elif self.path in ("/", "/index.html"):
                try:
                    cuerpo = (_ESTATICOS / "index.html").read_bytes()
                except OSError:
                    self._bytes(500, "text/plain; charset=utf-8",
                                b"Falta src/web/static/index.html")
                    return
                self._bytes(200, "text/html; charset=utf-8", cuerpo)
            else:
                self._bytes(404, "text/plain; charset=utf-8", b"No encontrado")

        # ----------------------------------------------------------- POST
        def do_POST(self):  # noqa: N802
            if not self.path.startswith("/api/tags"):
                self._bytes(404, "text/plain; charset=utf-8", b"No encontrado")
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "Content-Length invalido"})
                return
            if largo <= 0 or largo > _MAX_CUERPO:
                self._json(400, {"error": "Cuerpo vacio o demasiado grande"})
                return
            try:
                datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                self._json(400, {"error": f"JSON invalido: {e}"})
                return

            tags = datos.get("tags") if isinstance(datos, dict) else None
            if not isinstance(tags, list):
                self._json(400, {"error": "Se esperaba un objeto con la clave 'tags'"})
                return

            try:
                guardados = servicio.guardar_tags(tags)
            except ErrorConfig as e:
                # Error de validacion: el archivo y los hilos quedaron intactos.
                self._json(400, {"error": str(e)})
                return
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            except Exception as e:
                logger.exception("Error guardando tags")
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
                return
            self._json(200, {"ok": True, "tags": guardados})

        # ---------------------------------------------------------- utiles
        def _json(self, codigo: int, cuerpo: dict):
            self._bytes(codigo, "application/json; charset=utf-8",
                        json.dumps(cuerpo, default=str).encode("utf-8"))

        def _bytes(self, codigo: int, tipo: str, cuerpo: bytes):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, formato, *args):
            # El log por defecto escribe a stderr y ensucia la consola con una
            # linea por request, y el dashboard hace polling cada segundo.
            logger.trace(f"web: {formato % args}")

    return Handler


class ServidorWeb:
    def __init__(self, host: str, puerto: int, servicio):
        self.host, self.puerto = host, puerto
        self._srv = ThreadingHTTPServer((host, puerto), _handler(servicio))
        self._srv.daemon_threads = True
        self._hilo = threading.Thread(target=self._srv.serve_forever, name="web", daemon=True)

    def arrancar(self) -> None:
        self._hilo.start()
        logger.info(f"dashboard en http://{self.host}:{self.puerto}")

    def parar(self) -> None:
        try:
            self._srv.shutdown()
            self._srv.server_close()
        except Exception:
            pass
