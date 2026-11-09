"""Lee una vez todos los tags de tags.toml y los imprime.

Es la verificacion rapida contra el PLC real: si aca salen valores plausibles y
coinciden con lo que muestra GX Works en monitor, la configuracion esta bien.

    python scripts/read_once.py
    python scripts/read_once.py --crudo    muestra tambien el valor sin escalar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import ErrorConfig, cargar, raiz_por_defecto
from src.core.scangroups import agrupar, construir_items
from src.plc.base import ErrorPlc
from src.plc.factory import crear_plc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(raiz_por_defecto()))
    ap.add_argument("--crudo", action="store_true")
    args = ap.parse_args()

    try:
        cfg = cargar(args.config)
    except ErrorConfig as e:
        print(f"Configuracion invalida: {e}")
        return 2

    fallos = 0
    for nombre, cfg_plc in cfg.plcs_habilitados.items():
        tags = [t for t in cfg.tags if t.plc == nombre]
        if not tags:
            continue
        print(f"\n[{nombre}] {cfg_plc['marca']} {cfg_plc.get('ip','')}:{cfg_plc.get('puerto','')}")
        items = construir_items(tags, cfg.marca_por_plc)
        bits = [i for i in items if i.clave.es_bit]
        palabras = [i for i in items if not i.clave.es_bit]
        grupos = (agrupar(palabras, cfg.app.max_palabras_por_lectura, cfg.app.max_hueco)
                  + agrupar(bits, cfg.app.max_bits_por_lectura, cfg.app.max_hueco))

        driver = crear_plc(nombre, cfg_plc)
        try:
            driver.conectar()
        except ErrorPlc as e:
            print(f"  ERROR: {e}")
            fallos += 1
            continue
        print(f"  conectado. {len(grupos)} lectura(s) para {len(tags)} tag(s)\n")
        print(f"  {'TAG':<22} {'DIRECCION':<14} {'TIPO':<9} {'VALOR':>14}")
        print(f"  {'-'*22} {'-'*14} {'-'*9} {'-'*14}")
        try:
            for g in grupos:
                crudo = driver.leer_grupo(g)
                for item in g.items:
                    v = driver.decodificar(g, crudo, item)
                    final = v * item.tag.escala + item.tag.offset
                    extra = f"   (crudo {v})" if args.crudo and final != v else ""
                    print(f"  {item.tag.nombre:<22} {item.tag.direccion:<14} "
                          f"{item.tag.tipo:<9} {final:>14.4f}{extra}")
        except ErrorPlc as e:
            print(f"  ERROR de lectura: {e}")
            fallos += 1
        finally:
            driver.desconectar()
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
