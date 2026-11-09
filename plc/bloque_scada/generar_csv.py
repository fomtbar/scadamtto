"""Genera SCADA.csv (formato "Write to CSV File" de GX Works2) desde SCADA_lista.txt.

Formato tomado de un export real (plcEnpdf/SOLDADOR.csv): UTF-16 LE con BOM,
separado por tabs, CRLF, todo entre comillas. Cada instruccion ocupa un renglon
con su primer operando y cada operando extra va en un renglon aparte con las
otras columnas vacias.

Los numeros de paso son una estimacion: GX Works2 recalcula los pasos al
convertir. Si la importacion los rechazara, generar con --sin-pasos.

Uso:  python generar_csv.py [--sin-pasos]
"""
import sys
from pathlib import Path

AQUI = Path(__file__).parent
ORIGEN = AQUI / "SCADA_lista.txt"
NOMBRE_PROGRAMA = "SCADA"
PLC = "QCPU (Q mode) Q03UDE"
COLUMNAS = ["Step No.", "Line Statement", "Instruction", "I/O(Device)", "Blank", "PI Statement", "Note"]


def leer_instrucciones(ruta: Path) -> list[list[str]]:
    instrucciones = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.split(";", 1)[0].strip()
        if linea:
            instrucciones.append(linea.split())
    return instrucciones


def pasos(partes: list[str]) -> int:
    """Estimacion del tamano en pasos (no tiene que ser exacta)."""
    instr, operandos = partes[0], partes[1:]
    base = {
        "LD": 1, "LDI": 1, "AND": 1, "ANI": 1, "OR": 1, "ORI": 1, "OUT": 1,
        "SET": 1, "RST": 1, "LDP": 2, "ANDP": 2, "ORP": 2,
        "MOV": 2, "INC": 2, "DINC": 2, "DATERD": 2, "FMOV": 4, "*": 4, "+": 4,
    }.get(instr, 3)  # comparaciones (LD<>, AND<, ...) = 3
    extra = sum(1 for o in operandos if o.startswith(("SM", "SD")) or "Z" in o[1:])
    return base + extra


def generar(sin_pasos: bool) -> Path:
    filas = [[f'"{NOMBRE_PROGRAMA}"'], ['"PLC Information:"', f'"{PLC}"'],
             [f'"{c}"' for c in COLUMNAS]]
    paso = 0
    for partes in leer_instrucciones(ORIGEN) + [["END"]]:
        instr, operandos = partes[0], partes[1:]
        primero = operandos[0] if operandos else ""
        numero = "" if sin_pasos else str(paso)
        filas.append([f'"{v}"' for v in (numero, "", instr, primero, "", "", "")])
        for op in operandos[1:]:
            filas.append([f'"{v}"' for v in ("", "", "", op, "", "", "")])
        paso += pasos(partes)
    texto = "\r\n".join("\t".join(f) for f in filas) + "\r\n"
    destino = AQUI / ("SCADA_sin_pasos.csv" if sin_pasos else "SCADA.csv")
    destino.write_bytes(b"\xff\xfe" + texto.encode("utf-16-le"))
    return destino


if __name__ == "__main__":
    print(generar("--sin-pasos" in sys.argv))
