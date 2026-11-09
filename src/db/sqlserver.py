"""Sink a SQL Server usando python-tds.

Se usa python-tds y no pyodbc porque pyodbc es una extension en C y no tiene
wheel para el interprete instalado (3.15), con lo cual exigiria Visual C++ Build
Tools en la PC de planta. python-tds implementa el protocolo TDS en Python puro:
no compila nada y tampoco depende de que este instalado el driver ODBC.

Las filas se insertan con FechaHora explicita, nunca dejando actuar el
DEFAULT getdate() de la tabla: una muestra bufferizada se escribe minutos (u
horas) despues de haber sido tomada, y el timestamp que importa es el del scan.
"""
from __future__ import annotations

import re

import pytds
from loguru import logger

from src.core.models import Muestra

# Los nombres de esquema/tabla vienen de un TOML editado a mano y se interpolan
# en el SQL (no se pueden parametrizar), asi que se validan antes.
_RE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _ident(nombre: str, campo: str) -> str:
    if not _RE_IDENT.match(nombre):
        raise ValueError(
            f"Nombre invalido en la config de la DB ({campo}): {nombre!r}. "
            "Solo letras, digitos y guion bajo."
        )
    return f"[{nombre}]"


class ErrorDb(Exception):
    """Falla al hablar con SQL Server."""


class SqlServerSink:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._cn = None
        self.modo = str(cfg.get("modo", "actual")).lower()
        esquema = _ident(cfg.get("esquema", "test"), "esquema")
        self.tabla_historial = f"{esquema}.{_ident(cfg.get('tabla', 'RegistroPLC'), 'tabla')}"
        self.tabla_actual = f"{esquema}.{_ident(cfg.get('tabla_actual', 'ValorActual'), 'tabla_actual')}"
        self.destino = self.tabla_actual if self.modo == "actual" else self.tabla_historial

        self._sql_insert = (
            f"INSERT INTO {self.tabla_historial} (FechaHora,NombreTag,Valor,Estado) "
            "VALUES (%s,%s,%s,%s)"
        )
        # UPSERT sobre la tabla de valor actual, una fila por tag.
        #
        # FechaHora solo se mueve cuando el valor cambia de verdad; FechaLectura
        # se actualiza siempre. Esa es la diferencia que le permite al SCADA
        # distinguir "esta variable no se mueve" de "el adquisidor esta caido":
        # con un solo timestamp las dos situaciones se ven identicas.
        #
        # El EXISTS(SELECT ... INTERSECT SELECT ...) es el modismo de T-SQL para
        # comparar con semantica null-safe: con "Valor = %s" una lectura fallida
        # (NULL) nunca compara igual a otra, y FechaHora se moveria en cada scan
        # durante toda una caida del PLC.
        self._sql_upsert = f"""
UPDATE {self.tabla_actual} SET
    FechaHora = CASE WHEN EXISTS (SELECT Valor, Estado INTERSECT SELECT %s, %s)
                     THEN FechaHora ELSE %s END,
    Valor = %s, Estado = %s, FechaLectura = %s
WHERE NombreTag = %s;
IF @@ROWCOUNT = 0
    INSERT INTO {self.tabla_actual} (NombreTag, Valor, Estado, FechaHora, FechaLectura)
    VALUES (%s, %s, %s, %s, %s);
"""

    @property
    def conectado(self) -> bool:
        return self._cn is not None

    def conectar(self) -> None:
        self.desconectar()
        cfg = self.cfg
        try:
            self._cn = pytds.connect(
                dsn=cfg["servidor"],
                port=int(cfg.get("puerto", 1433)),
                database=cfg["base"],
                user=cfg["usuario"],
                password=cfg["password"],
                timeout=float(cfg.get("timeout_s", 30.0)),
                login_timeout=float(cfg.get("timeout_s", 30.0)),
                autocommit=False,
                appname="scadaMtto",
            )
            logger.info(f"SQL Server: conectado a {cfg['servidor']}/{cfg['base']} -> {self.destino}")
        except Exception as e:
            self._cn = None
            raise ErrorDb(
                f"No se pudo conectar a SQL Server {cfg['servidor']}/{cfg['base']} "
                f"como {cfg['usuario']} -- {type(e).__name__}: {e}"
            ) from e

    def desconectar(self) -> None:
        if self._cn is not None:
            try:
                self._cn.close()
            except Exception:
                pass
            self._cn = None

    def escribir(self, muestras: list[Muestra]) -> int:
        """Persiste un lote segun el modo configurado."""
        if self.modo == "actual":
            return self.upsert(muestras)
        return self.insertar(muestras)

    def insertar(self, muestras: list[Muestra]) -> int:
        """Modo historial: una fila por muestra, en una sola transaccion.

        O entra todo o no entra nada: si el commit falla, las muestras siguen en
        el buffer local y se reintentan enteras. Eso evita duplicados parciales.
        """
        if not muestras:
            return 0
        if self._cn is None:
            raise ErrorDb("SQL Server no conectado")
        filas = [
            (m.fecha_hora, m.nombre_tag, m.valor, m.estado)
            for m in muestras
        ]
        return self._ejecutar(self._sql_insert, filas, "insertando")

    def upsert(self, muestras: list[Muestra]) -> int:
        """Modo actual: actualiza la fila del tag, o la crea si no existe.

        Se espera que el lote traiga **una sola muestra por tag** (la mas
        reciente); de eso se encarga el writer. Mandar varias del mismo tag
        funcionaria igual, pero seria escribir de mas sobre la misma fila.
        """
        if not muestras:
            return 0
        if self._cn is None:
            raise ErrorDb("SQL Server no conectado")
        filas = [
            (m.valor, m.estado, m.fecha_hora,          # comparacion + FechaHora nueva
             m.valor, m.estado, m.fecha_hora,          # SET del UPDATE
             m.nombre_tag,                             # WHERE
             m.nombre_tag, m.valor, m.estado,          # INSERT si no existia
             m.fecha_hora, m.fecha_hora)
            for m in muestras
        ]
        return self._ejecutar(self._sql_upsert, filas, "actualizando")

    def _ejecutar(self, sql: str, filas: list[tuple], accion: str) -> int:
        try:
            cur = self._cn.cursor()
            cur.executemany(sql, filas)
            self._cn.commit()
            return len(filas)
        except Exception as e:
            try:
                self._cn.rollback()
            except Exception:
                pass
            # Cualquier error de envio invalida la conexion: puede ser un socket
            # muerto y reusarlo solo encadena fallas.
            self.desconectar()
            raise ErrorDb(f"Error {accion} {len(filas)} filas: {type(e).__name__}: {e}") from e

    def probar(self) -> str:
        """Devuelve la version del servidor. Para diagnostico."""
        if self._cn is None:
            raise ErrorDb("SQL Server no conectado")
        cur = self._cn.cursor()
        cur.execute("SELECT @@VERSION")
        return cur.fetchone()[0].splitlines()[0].strip()
