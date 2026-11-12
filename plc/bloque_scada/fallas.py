"""Catalogo de fallas de la celda FCA 02/03: la UNICA fuente.

De aca salen:
  - la seccion 10 del programa SCADA (generar_csv.py),
  - los comentarios de D6300-D6859 (generar_comentarios.py),
  - las tags del adquisidor (generar_tags.py),
  - web/src/lib/fallas.ts (generar_fallas_web.py).

Cada falla es un bit del programa original que se autorretiene hasta el
reset (M1006). Se dejan afuera los resumenes (M1970-M1980, M2710/M2711,
M3710/M3711, M2971/M2975...) porque contarian dos veces la misma falla.

REGLA: el codigo es la posicion en la lista + 1 y queda guardado en el PLC
(registro de ultimas fallas). Para sumar fallas, agregarlas AL FINAL. No
borrar ni reordenar: si una falla deja de existir, se deja igual (nunca
dispara).

Memoria (dentro del latch D0-D7000, no se borra con corte de luz):
  D6300 + codigo         veces que aparecio (16 bits)
  D6420 + 2*codigo       segundos acumulados activa (32 bits)
  D6800..D6859           ultimas 20 fallas x (codigo, MMDD, HHMM); la mas nueva en D6800
"""

D_VECES = 6300
D_SEG = 6420
D_ULTIMAS = 6800
N_ULTIMAS = 20
CAMPOS_ULTIMA = 3  # codigo, MMDD, HHMM

GRUPOS = ["Celda", "RB1", "RB2", "JIG1", "JIG2"]

# (dispositivo, grupo, texto)  -- texto <= 48 caracteres, en castellano (puede llevar tildes:
#  solo va a la web y a los ';' del listado, no a los comentarios del PLC)
FALLAS: list[tuple[str, str, str]] = [
    # --- Celda --------------------------------------------------------------
    ("M1840", "Celda", "Aire bajo"),
    ("M1841", "Celda", "Puerta / enchufe de seguridad"),
    ("M1842", "Celda", "Ingreso no permitido (cortina 1)"),
    ("M1843", "Celda", "Parada de emergencia"),
    ("M1844", "Celda", "Falla rodillo 1"),
    ("M1845", "Celda", "Falla rodillo 2"),
    ("M1846", "Celda", "Cortina 1 interrumpida"),
    ("M1847", "Celda", "Cortina 2 interrumpida"),
    ("M1848", "Celda", "Cortina interrumpida"),
    ("M1849", "Celda", "Ingreso no permitido (cortina 2)"),
    ("M1850", "Celda", "Tiempo de ciclo excedido"),
    ("M1851", "Celda", "Sin tipo de auto seleccionado"),
    ("M1852", "JIG1", "Alerta de calidad"),
    ("M1853", "JIG2", "Alerta de calidad"),
    ("M1854", "JIG1", "Sin tipo de auto seleccionado"),
    ("M1855", "JIG2", "Sin tipo de auto seleccionado"),
    ("M1983", "Celda", "Cortina en operación manual"),
    ("M8000", "Celda", "Batería del PLC baja"),
    ("M8001", "Celda", "Falla CC-Link"),
    ("M8010", "Celda", "Fusible cortado"),
    # --- Robot 1 ------------------------------------------------------------
    ("M1864", "RB1", "Alarma / error del robot"),
    ("M1865", "RB1", "Batería del robot baja"),
    ("M1866", "RB1", "Falta de gas"),
    ("M1867", "RB1", "Falta de alambre"),
    ("M1868", "RB1", "Alambre pegado"),
    ("M1869", "RB1", "Falla de arco"),
    ("M1870", "RB1", "Falla de JOB maestro"),
    ("M1871", "RB1", "Control de alambre"),
    ("M1872", "RB1", "Presión de gas"),
    ("M1873", "RB1", "Sensor de choque actuado"),
    ("M1874", "RB1", "Confirmación de posición"),
    ("M1875", "RB1", "Tipo de auto NG"),
    ("M1876", "RB1", "Alambre pegado (OT)"),
    ("M1877", "RB1", "Sirga NG"),
    # --- Robot 2 ------------------------------------------------------------
    ("M1880", "RB2", "Alarma / error del robot"),
    ("M1881", "RB2", "Batería del robot baja"),
    ("M1882", "RB2", "Falta de gas"),
    ("M1883", "RB2", "Falta de alambre"),
    ("M1884", "RB2", "Alambre pegado"),
    ("M1885", "RB2", "Falla de arco"),
    ("M1886", "RB2", "Falla de JOB maestro"),
    ("M1887", "RB2", "Control de alambre"),
    ("M1888", "RB2", "Presión de gas"),
    ("M1889", "RB2", "Sensor de choque actuado"),
    ("M1890", "RB2", "Confirmación de posición"),
    ("M1891", "RB2", "Tipo de auto NG"),
    ("M1892", "RB2", "Alambre pegado (OT)"),
    ("M1893", "RB2", "Sirga NG"),
    # --- JIG1 ---------------------------------------------------------------
    ("M2840", "JIG1", "Cilindro change"),
    ("M2841", "JIG1", "Clamp 1"),
    ("M2842", "JIG1", "Slide"),
    ("M2843", "JIG1", "Clamp 2"),
    ("M2844", "JIG1", "Clamp 3"),
    ("M2860", "JIG1", "Sin pieza en todo el jig"),
    *[(f"M{2900 + i}", "JIG1", f"Confirmación pieza {i + 1}") for i in range(16)],
    ("M2976", "JIG1", "Pieza levantada"),
    # --- JIG2 ---------------------------------------------------------------
    ("M3840", "JIG2", "Cilindro change"),
    ("M3841", "JIG2", "Shift pin"),
    ("M3842", "JIG2", "Slide"),
    ("M3843", "JIG2", "Clamp 1"),
    ("M3844", "JIG2", "Clamp 2 (accion)"),
    ("M3853", "JIG2", "Clamp 2 (sensor 1)"),
    ("M3854", "JIG2", "Clamp 2 (sensor 2)"),
    ("M3856", "JIG2", "Change: cilindro izquierdo"),
    ("M3857", "JIG2", "Change: cilindro derecho"),
    ("M3858", "JIG2", "Change: electroválvula"),
    ("M3500", "JIG2", "Change: cil. 2 sensor avance"),
    ("M3501", "JIG2", "Change: cil. 1 sensor avance"),
    ("M3502", "JIG2", "Change: cil. 2 sensor retorno"),
    ("M3503", "JIG2", "Change: cil. 1 sensor retorno"),
    ("M3860", "JIG2", "Sin pieza en todo el jig"),
    *[(f"M{3900 + i}", "JIG2", f"Confirmación pieza {i + 1}") for i in range(16)],
    ("M3976", "JIG2", "Pieza levantada"),
]

MAX_CODIGO = (D_SEG - D_VECES) - 1  # 119: D6300+c no puede pisar D6420

assert len(FALLAS) <= MAX_CODIGO, len(FALLAS)
assert len({d for d, _, _ in FALLAS}) == len(FALLAS), "dispositivo repetido"
assert all(g in GRUPOS for _, g, _ in FALLAS)
assert all(len(t) <= 48 for _, _, t in FALLAS)
assert D_SEG + 2 * len(FALLAS) + 1 < D_ULTIMAS


def catalogo() -> list[tuple[int, str, str, str]]:
    """[(codigo, dispositivo, grupo, texto)] con codigo 1..N."""
    return [(i + 1, d, g, t) for i, (d, g, t) in enumerate(FALLAS)]


def d_veces(codigo: int) -> str:
    return f"D{D_VECES + codigo}"


def d_seg(codigo: int) -> str:
    return f"D{D_SEG + 2 * codigo}"


def lista_il() -> str:
    """Seccion 10 del programa SCADA, en el mismo formato de SCADA_lista.txt."""
    ultimo = D_ULTIMAS + CAMPOS_ULTIMA
    corrida = (N_ULTIMAS - 1) * CAMPOS_ULTIMA
    lineas = [
        "; --- 10. Fallas: veces, segundos y ultimas 20 (generado por fallas.py) ---",
        "; Por cada falla: al aparecer suma 1 en D6300+codigo, corre el registro",
        f"; D{D_ULTIMAS}.. un lugar y anota codigo, fecha MMDD y hora HHMM. Mientras",
        "; esta activa suma 1 por segundo en D6420+2*codigo (32 bits).",
    ]
    for codigo, dev, grupo, texto in catalogo():
        lineas += [
            f"; F{codigo:03d} {grupo} {texto}",
            f"LDP     {dev}",
            f"INC     {d_veces(codigo)}",
            f"BMOV    D{D_ULTIMAS}   D{ultimo}   K{corrida}",
            f"MOV     K{codigo}     D{D_ULTIMAS}",
            f"BMOV    D6007   D{D_ULTIMAS + 1}   K2",
            "LD      M6000",
            f"AND     {dev}",
            f"DINC    {d_seg(codigo)}",
        ]
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    for c, d, g, t in catalogo():
        print(f"F{c:03d}  {d:6} {g:5} {t}")
    print(len(FALLAS), "fallas")
