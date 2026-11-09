"""Verifica la conexion a SQL Server de punta a punta.

Conecta, escribe dos filas de prueba con el mismo camino que usa el adquisidor
(upsert o insert segun el modo configurado), las lee de vuelta y las borra.
Si esto pasa, la parte de base de datos esta lista.

    scadamtto testdb          (o: python scripts/test_db.py)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import ErrorConfig, cargar, raiz_por_defecto
from src.core.models import Muestra
from src.db.sqlserver import ErrorDb, SqlServerSink

MARCA = "__SMOKE__"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(raiz_por_defecto()))
    args = ap.parse_args()

    try:
        cfg = cargar(args.config)
    except ErrorConfig as e:
        print(f"Configuracion invalida: {e}")
        return 2

    sink = SqlServerSink(cfg.db)
    print(f"conectando a {cfg.db['servidor']}/{cfg.db['base']} como {cfg.db['usuario']} ...")
    try:
        sink.conectar()
    except ErrorDb as e:
        print(f"  FALLO: {e}")
        return 1
    print(f"  OK -- {sink.probar()}")
    print(f"  modo: {sink.modo}  ->  {sink.destino}")

    # Las columnas a leer dependen del modo: la tabla de valor actual no tiene
    # Id y si tiene FechaLectura.
    if sink.modo == "actual":
        columnas = "NombreTag, Valor, Estado, FechaHora, FechaLectura"
        paso2 = "mismo valor de nuevo (FechaHora no se debe mover)"
        segunda = lambda t: Muestra(t, MARCA, 12.5, True)          # noqa: E731
    else:
        columnas = "Id, FechaHora, NombreTag, Valor, Estado"
        paso2 = "segunda fila, lectura fallida"
        segunda = lambda t: Muestra(t, MARCA, None, False)         # noqa: E731

    try:
        print(f"\n1) escribiendo '{MARCA}' ...")
        sink.escribir([Muestra(datetime.now(), MARCA, 12.5, True)])
        _mostrar(sink, columnas)

        print(f"\n2) {paso2} ...")
        sink.escribir([segunda(datetime.now())])
        _mostrar(sink, columnas)

        cur = sink._cn.cursor()
        cur.execute(f"DELETE FROM {sink.destino} WHERE NombreTag=%s", (MARCA,))
        sink._cn.commit()
        print("\nfilas de prueba borradas -- todo OK")
    except Exception as e:
        print(f"\nFALLO: {type(e).__name__}: {e}")
        return 1
    finally:
        sink.desconectar()
    return 0


def _mostrar(sink: SqlServerSink, columnas: str) -> None:
    # Cursor nuevo en cada llamada: el commit de escribir() invalida el anterior.
    cur = sink._cn.cursor()
    cur.execute(
        f"SELECT {columnas} FROM {sink.destino} WHERE NombreTag=%s ORDER BY NombreTag", (MARCA,)
    )
    for fila in cur.fetchall():
        print("   ", fila)


if __name__ == "__main__":
    raise SystemExit(main())
