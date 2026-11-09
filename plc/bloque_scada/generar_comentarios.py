"""Genera SCADA_comentarios.csv (comentarios de dispositivo para GX Works2).

Z no admite comentario: GX Works2 rechaza el archivo entero ("Invalid device").

Mismo estilo que el export de programa: UTF-16 LE con BOM, tabs, CRLF.
Comentarios de hasta 32 caracteres, en ASCII.
"""
from pathlib import Path

AQUI = Path(__file__).parent

C = {
    "D6000": "SCADA Vida +1/s",
    "D6001": "SCADA Estado celda",
    "D6002": "SCADA Estado JIG1",
    "D6003": "SCADA Estado JIG2",
    "D6004": "SCADA Tipo auto (D44)",
    "D6005": "SCADA JIG1 t entre pzas 0.1s",
    "D6006": "SCADA JIG2 t entre pzas 0.1s",
    "D6007": "SCADA Fecha MMDD",
    "D6008": "SCADA Hora HHMM",
    "D6010": "SCADA Piezas JIG1 total",
    "D6012": "SCADA Piezas JIG2 total",
    "D6014": "SCADA Seg produc total",
    "D6016": "SCADA Seg en falla total",
    "D6018": "SCADA Cant fallas total",
    "D6020": "SCADA RB1 cambios punta",
    "D6022": "SCADA RB2 cambios punta",
    "D6024": "SCADA RB1 limpiezas tobera",
    "D6026": "SCADA RB2 limpiezas tobera",
    "D6040": "SCADA cronometro JIG1",
    "D6041": "SCADA cronometro JIG2",
    "D6090": "SCADA reloj anio",
    "D6091": "SCADA reloj mes",
    "D6092": "SCADA reloj dia",
    "D6093": "SCADA reloj hora",
    "D6094": "SCADA reloj minuto",
    "D6095": "SCADA reloj segundo",
    "D6096": "SCADA reloj dia semana",
    "D6097": "SCADA hora del renglon",
    "D6098": "SCADA auxiliar calculo",
    "D6099": "SCADA auxiliar calculo",
    "M6000": "SCADA pulso 1s",
    "M6001": "SCADA pulso 0.1s",
    "M6002": "SCADA pieza JIG1",
    "M6003": "SCADA pieza JIG2",
    "M6004": "SCADA produciendo",
    "M6005": "SCADA en falla",
    "M6010": "SCADA Emergencia (M1843)",
    "M6011": "SCADA Falla general (M1980)",
    "M6012": "SCADA Falla JIG1 (M1974)",
    "M6013": "SCADA Falla JIG2 (M1975)",
    "M6014": "SCADA Falla RB1 (M1977)",
    "M6015": "SCADA Falla RB2 (M1978)",
    "M6016": "SCADA Alarma RB1 (B83)",
    "M6017": "SCADA Alarma RB2 (B183)",
    "M6018": "SCADA Teach RB1 (B87)",
    "M6019": "SCADA Teach RB2 (B187)",
    "M6020": "SCADA Servo ON RB1 (B81)",
    "M6021": "SCADA Servo ON RB2 (B181)",
    "M6022": "SCADA Falla CC-Link (M3979)",
    "M6023": "SCADA Bateria baja (M3978)",
    "M6024": "SCADA Auto (M1000)",
}
# Parte alta de los contadores de 32 bits
for d in range(6010, 6028, 2):
    C[f"D{d+1}"] = C[f"D{d}"][:25].rstrip() + " (alta)"
# Tabla de 24 horas
campos = ["fecha MMDD", "pzas JIG1", "pzas JIG2", "seg prod", "seg falla"]
for h in range(24):
    for k, campo in enumerate(campos):
        C[f"D{6100 + h*5 + k}"] = f"SCADA H{h:02d} {campo}"

def clave(dev):
    return (dev[0], int(dev[1:]))

for dev, txt in C.items():
    assert len(txt) <= 32 and txt.isascii(), (dev, txt)

filas = ['"COMMENT"', '"Device Name"\t"Comment"']
filas += [f'"{d}"\t"{C[d]}"' for d in sorted(C, key=clave)]
destino = AQUI / "SCADA_comentarios.csv"
destino.write_bytes(b"\xff\xfe" + ("\r\n".join(filas) + "\r\n").encode("utf-16-le"))
print(destino, len(C), "comentarios")
