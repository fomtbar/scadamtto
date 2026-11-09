"""Une el backup de comentarios del proyecto (COMMENT_bk.csv) con los del
bloque SCADA (SCADA_comentarios.csv) en un solo archivo: COMMENT_con_SCADA.csv.

Read from CSV File de GX Works2 REEMPLAZA todos los comentarios, por eso hay
que importar el archivo completo. Respeta el formato del export original
(UTF-16 LE con BOM, tabs, LF) y ordena cada dispositivo nuevo dentro de su
grupo (X, Y, M, L, B, T, D, SM, SD). Si un dispositivo ya tenia comentario,
se conserva el original y se avisa.
"""
import re
from pathlib import Path

AQUI = Path(__file__).parent


def leer(ruta: Path) -> tuple[list[str], list[tuple[str, str]]]:
    lineas = ruta.read_bytes().decode("utf-16").replace("\r\n", "\n").split("\n")
    lineas = [l for l in lineas if l.strip()]
    filas = []
    for l in lineas[2:]:
        dev, com = l.split("\t", 1)
        filas.append((dev.strip('"'), com))
    return lineas[:2], filas


HEX = {"X", "Y", "B", "W", "SB", "SW", "DX", "DY"}


def clave(dev: str) -> tuple[str, int]:
    """Tipo y numero; X, Y, B y W se numeran en hexadecimal."""
    m = re.fullmatch(r"(SB|SW|SM|SD|DX|DY|[A-Z])([0-9A-F]+)", dev)
    if not m:
        return dev, -1
    tipo, num = m.groups()
    return tipo, int(num, 16 if tipo in HEX else 10)


cabecera, originales = leer(AQUI / "COMMENT_bk.csv")
_, nuevos = leer(AQUI / "SCADA_comentarios.csv")

existentes = {d for d, _ in originales}
orden_tipos = list(dict.fromkeys(clave(d)[0] for d, _ in originales))
resultado = list(originales)
agregados = 0
for dev, com in nuevos:
    if dev in existentes:
        print(f"AVISO: {dev} ya tenia comentario, se deja el original")
        continue
    tipo, num = clave(dev)
    # posicion: despues del ultimo del mismo tipo con numero menor
    pos = None
    for i, (d, _) in enumerate(resultado):
        t, n = clave(d)
        if t == tipo and n < num:
            pos = i + 1
    if pos is None:
        idx_tipo = orden_tipos.index(tipo)
        pos = next((i for i, (d, _) in enumerate(resultado)
                    if orden_tipos.index(clave(d)[0]) >= idx_tipo), len(resultado))
    resultado.insert(pos, (dev, com))
    agregados += 1

texto = "\n".join(cabecera + [f'"{d}"\t{c}' for d, c in resultado]) + "\n"
destino = AQUI / "COMMENT_con_SCADA.csv"
destino.write_bytes(b"\xff\xfe" + texto.encode("utf-16-le"))
print(f"{destino}: {len(originales)} originales + {agregados} SCADA = {len(resultado)}")
