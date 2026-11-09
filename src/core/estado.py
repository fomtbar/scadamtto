"""Estado vivo del proceso, compartido con el dashboard.

Lo escriben los hilos de scan y el de escritura; lo lee el servidor web. Todo
pasa por un lock porque son hilos distintos y el snapshot tiene que ser
coherente (no sirve mostrar el contador de una lectura y el error de otra).
"""
from __future__ import annotations

import threading
from datetime import datetime

from src.core.models import EstadoPlc, EstadoTag


class Supervisor:
    def __init__(self):
        self._lock = threading.Lock()
        self.plcs: dict[str, EstadoPlc] = {}
        self.db_conectada = False
        self.db_ultimo_error = ""
        self.db_filas_escritas = 0
        self.db_ultima_escritura: datetime | None = None
        self.buffer_pendientes = 0
        self.arranque = datetime.now()

    def registrar_plc(self, nombre: str, marca: str, ip: str, puerto: int) -> None:
        """Alta de un PLC. Si ya existia conserva sus contadores.

        Importa al recargar tags en caliente: reiniciar los contadores en cada
        alta de variable haria ilegible el panel de diagnostico.
        """
        with self._lock:
            e = self.plcs.get(nombre)
            if e is None:
                self.plcs[nombre] = EstadoPlc(nombre=nombre, marca=marca, ip=ip, puerto=puerto)
            else:
                e.marca, e.ip, e.puerto = marca, ip, puerto

    def sincronizar_tags(self, plc: str, nombres: set[str]) -> None:
        """Saca del panel los tags que ya no estan configurados."""
        with self._lock:
            e = self.plcs.get(plc)
            if e is not None:
                e.tags = {n: v for n, v in e.tags.items() if n in nombres}

    def plc_conectado(self, nombre: str, conectado: bool, error: str = "") -> None:
        with self._lock:
            e = self.plcs[nombre]
            if conectado and not e.conectado:
                e.reconexiones += 1
            e.conectado = conectado
            e.ultimo_error = error

    def lectura(self, nombre: str, ok: bool, error: str = "") -> None:
        with self._lock:
            e = self.plcs[nombre]
            if ok:
                e.lecturas_ok += 1
            else:
                e.lecturas_error += 1
                e.ultimo_error = error

    def tag(self, plc: str, nombre: str, valor: float | None, buena: bool,
            momento: datetime, registrado: bool, error: str = "") -> None:
        with self._lock:
            t = self.plcs[plc].tags.setdefault(nombre, EstadoTag())
            t.ultimo_valor = valor
            t.ultima_muestra = momento
            t.buena = buena
            t.error = error
            if registrado:
                t.ultimo_registro = momento

    def db(self, conectada: bool, error: str = "", filas: int = 0) -> None:
        with self._lock:
            self.db_conectada = conectada
            if error:
                self.db_ultimo_error = error
            if filas:
                self.db_filas_escritas += filas
                self.db_ultima_escritura = datetime.now()

    def pendientes(self, n: int) -> None:
        with self._lock:
            self.buffer_pendientes = n

    def snapshot(self) -> dict:
        """Copia serializable para el dashboard."""
        def iso(d):
            return d.isoformat(sep=" ", timespec="seconds") if d else None

        with self._lock:
            return {
                "arranque": iso(self.arranque),
                "ahora": iso(datetime.now()),
                "db": {
                    "conectada": self.db_conectada,
                    "ultimo_error": self.db_ultimo_error,
                    "filas_escritas": self.db_filas_escritas,
                    "ultima_escritura": iso(self.db_ultima_escritura),
                },
                "buffer_pendientes": self.buffer_pendientes,
                "plcs": [
                    {
                        "nombre": p.nombre, "marca": p.marca, "ip": p.ip, "puerto": p.puerto,
                        "conectado": p.conectado, "ultimo_error": p.ultimo_error,
                        "lecturas_ok": p.lecturas_ok, "lecturas_error": p.lecturas_error,
                        "reconexiones": p.reconexiones,
                        "tags": [
                            {
                                "nombre": n, "valor": t.ultimo_valor, "buena": t.buena,
                                "ultima_muestra": iso(t.ultima_muestra),
                                "ultimo_registro": iso(t.ultimo_registro),
                                "error": t.error,
                            }
                            for n, t in sorted(p.tags.items())
                        ],
                    }
                    for p in self.plcs.values()
                ],
            }
