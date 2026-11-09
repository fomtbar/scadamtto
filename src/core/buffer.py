"""Buffer local store-and-forward sobre SQLite.

El poller no escribe nunca directo a SQL Server: deja las muestras aca y un hilo
aparte las drena. Eso resuelve tres cosas de golpe:

- La DB esta en otra red que la del PLC. Si se cae el enlace, el scan sigue
  corriendo y no se pierde ni una muestra.
- Una DB lenta no frena el scan del PLC (que tiene que ser regular para que las
  series temporales sirvan).
- Es durable: si se corta la luz, lo que ya entro al buffer sigue estando en el
  proximo arranque. Una cola en memoria se perderia.

SQLite en modo WAL soporta un escritor y varios lectores en paralelo, que es
justo la forma de acceso que tiene esto.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from src.core.models import Muestra

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS pendientes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora  TEXT    NOT NULL,
    nombre_tag  TEXT    NOT NULL,
    valor       REAL,
    estado      INTEGER NOT NULL
);
"""


class Buffer:
    """Cola durable de muestras pendientes de enviar a SQL Server."""

    def __init__(self, ruta: str | Path, max_filas: int = 2_000_000):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.max_filas = max_filas
        # sqlite3 no permite compartir una conexion entre hilos, y aca hay al
        # menos dos (poller y writer). Cada hilo se abre la suya.
        self._local = threading.local()
        # Registro de todas las conexiones abiertas, de cualquier hilo, para
        # poder cerrarlas al apagar. threading.local no permite recorrerlas.
        self._abiertas: set[sqlite3.Connection] = set()
        self._lock = threading.Lock()
        with self._conexion() as cn:
            cn.executescript(_ESQUEMA)

    def _conexion(self) -> sqlite3.Connection:
        cn = getattr(self._local, "cn", None)
        if cn is None:
            cn = sqlite3.connect(self.ruta, timeout=30.0, isolation_level=None)
            cn.execute("PRAGMA journal_mode=WAL")
            # NORMAL en WAL es durable ante caida del proceso; solo se arriesga
            # la ultima transaccion ante corte de energia, y a cambio no hace un
            # fsync por cada scan.
            cn.execute("PRAGMA synchronous=NORMAL")
            cn.execute("PRAGMA busy_timeout=30000")
            self._local.cn = cn
            with self._lock:
                self._abiertas.add(cn)
        return cn

    def guardar(self, muestras: list[Muestra]) -> int:
        if not muestras:
            return 0
        filas = [
            (m.fecha_hora.isoformat(sep=" ", timespec="milliseconds"),
             m.nombre_tag, m.valor, 1 if m.estado else 0)
            for m in muestras
        ]
        cn = self._conexion()
        with cn:
            cn.executemany(
                "INSERT INTO pendientes (fecha_hora,nombre_tag,valor,estado) VALUES (?,?,?,?)",
                filas,
            )
        return len(filas)

    def tomar(self, limite: int) -> list[tuple[int, Muestra]]:
        """Devuelve las muestras mas viejas sin sacarlas del buffer.

        Se borran recien con confirmar(), despues de que SQL Server haya hecho
        commit. Si el envio falla, siguen aca y se reintentan.
        """
        cn = self._conexion()
        filas = cn.execute(
            "SELECT id,fecha_hora,nombre_tag,valor,estado FROM pendientes "
            "ORDER BY id LIMIT ?",
            (limite,),
        ).fetchall()
        salida = []
        for id_, fecha, nombre, valor, estado in filas:
            salida.append((id_, Muestra(datetime.fromisoformat(fecha), nombre, valor, bool(estado))))
        return salida

    def confirmar(self, ids: list[int]) -> int:
        if not ids:
            return 0
        cn = self._conexion()
        with cn:
            cn.execute(
                f"DELETE FROM pendientes WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
        return len(ids)

    def pendientes(self) -> int:
        return self._conexion().execute("SELECT COUNT(*) FROM pendientes").fetchone()[0]

    def podar(self) -> int:
        """Descarta las muestras mas viejas si el buffer paso el tope.

        Solo puede pasar con la DB caida mucho tiempo. Se prefiere perder lo mas
        viejo antes que llenar el disco de la PC de planta.
        """
        cn = self._conexion()
        total = self.pendientes()
        if total <= self.max_filas:
            return 0
        sobran = total - self.max_filas
        with cn:
            cn.execute(
                "DELETE FROM pendientes WHERE id IN "
                "(SELECT id FROM pendientes ORDER BY id LIMIT ?)",
                (sobran,),
            )
        return sobran

    def cerrar_hilo(self) -> None:
        """Cierra la conexion del hilo que llama.

        La llaman los hilos de scan y el writer al terminar. Importa por la
        recarga en caliente de tags: cada recarga levanta hilos de scan nuevos,
        y sin esto la conexion de los viejos quedaria abierta hasta el apagado.
        """
        cn = getattr(self._local, "cn", None)
        if cn is not None:
            with self._lock:
                self._abiertas.discard(cn)
            cn.close()
            self._local.cn = None

    def cerrar(self) -> None:
        """Cierra todas las conexiones que queden abiertas, de cualquier hilo."""
        self.cerrar_hilo()
        with self._lock:
            pendientes, self._abiertas = self._abiertas, set()
        for cn in pendientes:
            try:
                cn.close()
            except sqlite3.ProgrammingError:
                # Conexion de otro hilo: sqlite3 se niega a cerrarla desde aca.
                # Solo pasa si ese hilo no termino; el proceso esta saliendo.
                pass
