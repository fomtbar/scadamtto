"""Modelos de datos del adquisidor.

Se usan dataclasses de la stdlib en lugar de pydantic: pydantic-core es una
extension en Rust y no tiene wheel para el interprete instalado (3.15), con lo
cual exigiria toolchain de compilacion en la PC de planta. La validacion se
hace a mano en core/config.py, que es poca y explicita.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Tipos de dato admitidos por tag. Determinan cuantas palabras se leen y como
# se decodifica el crudo que devuelve el PLC.
TIPOS_PALABRA = ("int16", "uint16", "int32", "uint32", "float32")
TIPOS = TIPOS_PALABRA + ("bit",)

# Cuantas palabras de 16 bits ocupa cada tipo.
PALABRAS_POR_TIPO = {
    "int16": 1, "uint16": 1,
    "int32": 2, "uint32": 2, "float32": 2,
}

MODOS_REGISTRO = ("intervalo", "cambio")


@dataclass(frozen=True)
class TagDef:
    """Definicion de un tag tal como viene de config/tags.toml."""
    nombre: str                 # va literal a RegistroPLC.NombreTag (varchar(50))
    plc: str                    # clave del PLC en site.toml
    direccion: str              # 'D5002', 'M1000', 'DB1.DBW0', ...
    tipo: str = "int16"
    escala: float = 1.0
    offset: float = 0.0
    scan_ms: int = 1000
    registro: str = "intervalo"
    banda_muerta: float = 0.0   # solo aplica con registro='cambio'
    heartbeat_s: int = 0        # 0 = sin heartbeat; fuerza fila cada N seg

    @property
    def es_bit(self) -> bool:
        return self.tipo == "bit"

    @property
    def palabras(self) -> int:
        return PALABRAS_POR_TIPO.get(self.tipo, 1)


@dataclass(frozen=True)
class Muestra:
    """Una lectura lista para persistir.

    `valor` es None cuando la lectura fallo; en ese caso `estado` es False y en
    SQL Server la fila queda con Valor NULL, para no confundir un timeout con
    un cero real del proceso.
    """
    fecha_hora: datetime
    nombre_tag: str
    valor: float | None
    estado: bool

    @property
    def buena(self) -> bool:
        return self.estado and self.valor is not None


@dataclass
class EstadoTag:
    """Estado vivo de un tag, para el dashboard y la politica de registro."""
    ultimo_valor: float | None = None
    ultima_muestra: datetime | None = None      # cuando se leyo por ultima vez
    ultimo_registro: datetime | None = None     # cuando se guardo por ultima vez
    buena: bool = False
    error: str = ""


@dataclass
class EstadoPlc:
    """Estado vivo de un PLC, para el dashboard."""
    nombre: str
    marca: str
    ip: str
    puerto: int
    conectado: bool = False
    ultimo_error: str = ""
    lecturas_ok: int = 0
    lecturas_error: int = 0
    reconexiones: int = 0
    tags: dict[str, EstadoTag] = field(default_factory=dict)
