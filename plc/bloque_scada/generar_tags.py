"""Genera tags_scada.toml: las tags que el adquisidor lee del bloque SCADA.

Cada celda lleva su prefijo en el nombre (FCA0203.Celda.Estado), asi la web
separa las celdas con un LIKE 'FCA0203.%' y una celda nueva no choca con las
anteriores en test.ValorActual.

Uso:  python generar_tags.py [PREFIJO] [CLAVE_PLC]
      python generar_tags.py FCA0203 mitsu_q1      (valores por defecto)
"""
import sys
from pathlib import Path

AQUI = Path(__file__).parent
PREFIJO = sys.argv[1] if len(sys.argv) > 1 else "FCA0203"
PLC = sys.argv[2] if len(sys.argv) > 2 else "mitsu_q1"

PALABRAS = [
    ("Celda.Vida", "D6000"), ("Celda.Estado", "D6001"),
    ("JIG1.Estado", "D6002"), ("JIG2.Estado", "D6003"),
    ("Celda.TipoAuto", "D6004"),
    ("JIG1.TiempoEntrePiezas_ds", "D6005"), ("JIG2.TiempoEntrePiezas_ds", "D6006"),
    ("PLC.FechaMMDD", "D6007"), ("PLC.HoraHHMM", "D6008"),
]
DOBLES = [
    ("JIG1.PiezasTotal", "D6010"), ("JIG2.PiezasTotal", "D6012"),
    ("Celda.SegProduciendoTotal", "D6014"), ("Celda.SegFallaTotal", "D6016"),
    ("Celda.FallasTotal", "D6018"),
    ("RB1.CambiosPuntaTotal", "D6020"), ("RB2.CambiosPuntaTotal", "D6022"),
    ("RB1.LimpiezasToberaTotal", "D6024"), ("RB2.LimpiezasToberaTotal", "D6026"),
]
BITS = [
    ("Celda.Emergencia", "M6010"), ("Celda.FallaGeneral", "M6011"),
    ("JIG1.Falla", "M6012"), ("JIG2.Falla", "M6013"),
    ("RB1.Falla", "M6014"), ("RB2.Falla", "M6015"),
    ("RB1.Alarma", "M6016"), ("RB2.Alarma", "M6017"),
    ("RB1.ModoTeach", "M6018"), ("RB2.ModoTeach", "M6019"),
    ("RB1.ServoOn", "M6020"), ("RB2.ServoOn", "M6021"),
    ("PLC.FallaCCLink", "M6022"), ("PLC.BateriaBaja", "M6023"),
    ("Celda.Auto", "M6024"),
]
CAMPOS_HORA = ["Fecha", "PiezasJ1", "PiezasJ2", "SegProd", "SegFalla"]


def tag(nombre: str, direccion: str, tipo: str, scan_ms: int) -> str:
    completo = f"{PREFIJO}.{nombre}"
    assert len(completo) <= 50, completo
    return f'''
[[tag]]
nombre       = "{completo}"
plc          = "{PLC}"
direccion    = "{direccion}"
tipo         = "{tipo}"
escala       = 1.0
offset       = 0.0
scan_ms      = {scan_ms}
registro     = "intervalo"
'''


partes = [f"# Tags del bloque SCADA de la celda {PREFIJO} "
          f"(D6000-D6219, M6010-M6024) - agregar al final de config/tags.toml\n"]
partes += [tag(n, d, "int16", 1000) for n, d in PALABRAS]
partes += [tag(n, d, "int32", 1000) for n, d in DOBLES]
partes += [tag(n, d, "bit", 1000) for n, d in BITS]
for h in range(24):
    for k, campo in enumerate(CAMPOS_HORA):
        partes.append(tag(f"Hora.{h:02d}.{campo}", f"D{6100 + h * 5 + k}", "int16", 5000))

destino = AQUI / "tags_scada.toml"
destino.write_text("".join(partes), encoding="utf-8", newline="\n")
print(destino, sum(p.count("[[tag]]") for p in partes), "tags")
