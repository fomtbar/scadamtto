"""Genera web/src/lib/fallas.ts desde fallas.py (el catalogo unico).

Uso:  python generar_fallas_web.py
"""
import json
from pathlib import Path

import fallas

DESTINO = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "fallas.ts"

filas = "\n".join(
    f"  {{ codigo: {c}, dispositivo: {json.dumps(d, ensure_ascii=False)}, grupo: {json.dumps(g, ensure_ascii=False)}, texto: {json.dumps(t, ensure_ascii=False)} }},"
    for c, d, g, t in fallas.catalogo()
)
texto = f"""// GENERADO por plc/bloque_scada/generar_fallas_web.py desde fallas.py. No editar a mano.

export type GrupoFalla = {" | ".join(json.dumps(g, ensure_ascii=False) for g in fallas.GRUPOS)};

export type DefFalla = {{ codigo: number; dispositivo: string; grupo: GrupoFalla; texto: string }};

/** Cantidad de renglones del registro de ultimas fallas del PLC (D{fallas.D_ULTIMAS}..). */
export const N_ULTIMAS = {fallas.N_ULTIMAS};

export const FALLAS: DefFalla[] = [
{filas}
];
"""
DESTINO.write_text(texto, encoding="utf-8", newline="\n")
print(DESTINO, len(fallas.FALLAS), "fallas")
