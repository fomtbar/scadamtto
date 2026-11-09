"""Carga y validacion de la configuracion.

La config va en tres archivos, siguiendo el esquema de visionMantev2 (que se
peleo con el problema de que un update pise la config de planta):

  config/app.default.toml  parametros de la app, versionado. Es la semilla.
  config/app.toml          copia editable, se crea sola en el primer arranque.
  config/site.toml         IPs, puertos y credenciales. NO versionado.
  config/tags.toml         la tabla de tags. Es el archivo que se toca al
                           ampliar la lista de datos a recolectar.

La validacion se hace a mano porque pydantic-core no tiene wheel para el
interprete instalado. Es poca y los mensajes de error dicen que archivo y que
tag estan mal, que es lo que importa cuando esto falla a las 3 de la manana.
"""
from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from src.core.models import MODOS_REGISTRO, TIPOS, TagDef

# Limite de la columna NombreTag.
MAX_NOMBRE_TAG = 50

ENV_PASSWORD = "SCADAMTTO_DB_PASSWORD"

# Como se persiste en SQL Server.
#   actual    -> una fila por tag, se actualiza en el lugar. La tabla no crece.
#   historial -> una fila por muestra. Sirve para analisis, pero crece sin fin.
MODOS_DB = ("actual", "historial")


class ErrorConfig(Exception):
    """La configuracion no es valida. El mensaje dice como arreglarla."""


@dataclass
class ConfigApp:
    # Lectura
    max_palabras_por_lectura: int = 480   # tope del 3E es 960; se deja margen
    max_bits_por_lectura: int = 1024
    max_hueco: int = 16                   # cuantas unidades sin usar se toleran
    # Persistencia
    lote_db: int = 200
    buffer_max_filas: int = 2_000_000
    buffer_ruta: str = "data/buffer.sqlite"
    # Reconexion
    reconexion_min_s: float = 1.0
    reconexion_max_s: float = 30.0
    # Web
    web_habilitado: bool = True
    web_host: str = "127.0.0.1"
    web_puerto: int = 8080
    # Log
    nivel_log: str = "INFO"


@dataclass
class Config:
    app: ConfigApp
    plcs: dict[str, dict]
    db: dict
    tags: list[TagDef]
    raiz: Path = field(default=Path("."))

    @property
    def marca_por_plc(self) -> dict[str, str]:
        return {n: c["marca"] for n, c in self.plcs.items()}

    @property
    def plcs_habilitados(self) -> dict[str, dict]:
        return {n: c for n, c in self.plcs.items() if c.get("habilitado", True)}


def raiz_por_defecto() -> Path:
    """Directorio donde se busca config/, logs/ y data/.

    Congelado con PyInstaller, __file__ apunta adentro del bundle, que es de solo
    lectura y se borra al salir. Lo que vale ahi es la carpeta del .exe, que es
    donde queda config/ al lado del binario.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def _leer_toml(ruta: Path) -> dict:
    try:
        with open(ruta, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ErrorConfig(f"Falta el archivo de configuracion: {ruta}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErrorConfig(f"{ruta} tiene un error de sintaxis TOML: {e}") from None


def _exigir(cfg: dict, clave: str, donde: str):
    if clave not in cfg:
        raise ErrorConfig(f"Falta '{clave}' en {donde}")
    return cfg[clave]


def _validar_plcs(crudo: dict) -> dict[str, dict]:
    from src.plc.factory import MARCAS

    plcs = crudo.get("plc", {})
    if not plcs:
        raise ErrorConfig("site.toml no define ningun PLC (se espera al menos un [plc.<nombre>])")
    for nombre, cfg in plcs.items():
        donde = f"[plc.{nombre}] de site.toml"
        marca = str(_exigir(cfg, "marca", donde)).lower()
        if marca not in MARCAS:
            raise ErrorConfig(
                f"{donde}: marca {marca!r} no soportada. Validas: {', '.join(MARCAS)}"
            )
        cfg["marca"] = marca
        if marca != "mock":
            _exigir(cfg, "ip", donde)
        if marca == "mitsubishi":
            puerto = int(_exigir(cfg, "puerto", donde))
            if not 1 <= puerto <= 65535:
                raise ErrorConfig(f"{donde}: puerto {puerto} fuera de rango")
            commtype = str(cfg.get("commtype", "binary")).lower()
            if commtype not in ("binary", "ascii"):
                raise ErrorConfig(
                    f"{donde}: commtype {commtype!r} invalido. Tiene que coincidir con el "
                    "'Communication data code' del PLC: 'ascii' o 'binary'."
                )
            cfg["commtype"] = commtype
        cfg.setdefault("puerto", 102 if marca == "siemens" else 0)
    return plcs


def _validar_db(crudo: dict) -> dict:
    db = crudo.get("db")
    if not db:
        raise ErrorConfig("site.toml no tiene seccion [db]")
    for clave in ("servidor", "base", "usuario"):
        _exigir(db, clave, "[db] de site.toml")
    # La password puede venir del entorno, que es lo recomendado para no tenerla
    # en un archivo aunque ese archivo no se versione.
    desde_env = os.environ.get(ENV_PASSWORD)
    if desde_env:
        db["password"] = desde_env
    elif "password" not in db:
        raise ErrorConfig(
            f"Falta la password de la DB: ponela en [db].password de site.toml "
            f"o en la variable de entorno {ENV_PASSWORD}"
        )
    db.setdefault("esquema", "test")
    db.setdefault("tabla", "RegistroPLC")
    db.setdefault("tabla_actual", "ValorActual")
    modo = str(db.get("modo", "actual")).lower()
    if modo not in MODOS_DB:
        raise ErrorConfig(
            f"[db].modo invalido: {modo!r}. Validos: {', '.join(MODOS_DB)}. "
            "'actual' = una fila por tag que se actualiza en el lugar; "
            "'historial' = una fila por muestra."
        )
    db["modo"] = modo
    return db


def _validar_tags(crudo: dict, plcs: dict[str, dict]) -> list[TagDef]:
    lista = crudo.get("tag", [])
    if not lista:
        raise ErrorConfig("tags.toml no define ningun tag (se espera al menos un [[tag]])")
    tags: list[TagDef] = []
    vistos: set[str] = set()
    for i, t in enumerate(lista, 1):
        donde = f"tag #{i} de tags.toml"
        nombre = str(_exigir(t, "nombre", donde))
        donde = f"tag {nombre!r} de tags.toml"
        if len(nombre) > MAX_NOMBRE_TAG:
            raise ErrorConfig(
                f"{donde}: el nombre tiene {len(nombre)} caracteres y la columna "
                f"NombreTag admite {MAX_NOMBRE_TAG}"
            )
        if nombre in vistos:
            raise ErrorConfig(f"El nombre de tag {nombre!r} esta repetido en tags.toml")
        vistos.add(nombre)

        plc = str(_exigir(t, "plc", donde))
        if plc not in plcs:
            raise ErrorConfig(
                f"{donde}: apunta al PLC {plc!r}, que no esta definido en site.toml. "
                f"Definidos: {', '.join(sorted(plcs)) or '(ninguno)'}"
            )
        tipo = str(t.get("tipo", "int16")).lower()
        if tipo not in TIPOS:
            raise ErrorConfig(f"{donde}: tipo {tipo!r} invalido. Validos: {', '.join(TIPOS)}")
        registro = str(t.get("registro", "intervalo")).lower()
        if registro not in MODOS_REGISTRO:
            raise ErrorConfig(
                f"{donde}: registro {registro!r} invalido. Validos: {', '.join(MODOS_REGISTRO)}"
            )
        scan_ms = int(t.get("scan_ms", 1000))
        if scan_ms < 10:
            raise ErrorConfig(f"{donde}: scan_ms {scan_ms} es demasiado chico (minimo 10)")

        tags.append(TagDef(
            nombre=nombre,
            plc=plc,
            direccion=str(_exigir(t, "direccion", donde)),
            tipo=tipo,
            escala=float(t.get("escala", 1.0)),
            offset=float(t.get("offset", 0.0)),
            scan_ms=scan_ms,
            registro=registro,
            banda_muerta=float(t.get("banda_muerta", 0.0)),
            heartbeat_s=int(t.get("heartbeat_s", 0)),
        ))
    return tags


def cargar(raiz: str | Path = ".") -> Config:
    """Carga las tres capas de config y devuelve un objeto validado."""
    raiz = Path(raiz)
    cfg_dir = raiz / "config"

    # Primer arranque: se siembra app.toml desde la version versionada.
    app_toml = cfg_dir / "app.toml"
    app_default = cfg_dir / "app.default.toml"
    if not app_toml.exists() and app_default.exists():
        shutil.copyfile(app_default, app_toml)

    site = cfg_dir / "site.toml"
    if not site.exists():
        raise ErrorConfig(
            f"Falta {site}. Copia config/site.example.toml a config/site.toml y "
            "completa las IPs y credenciales de esta maquina."
        )

    crudo_app = _leer_toml(app_toml) if app_toml.exists() else {}
    seccion = crudo_app.get("app", {})
    campos = {f for f in ConfigApp.__dataclass_fields__}
    desconocidos = set(seccion) - campos
    if desconocidos:
        raise ErrorConfig(
            f"app.toml tiene claves desconocidas en [app]: {', '.join(sorted(desconocidos))}"
        )
    app = ConfigApp(**seccion)

    crudo_site = _leer_toml(site)
    plcs = _validar_plcs(crudo_site)
    db = _validar_db(crudo_site)
    tags = _validar_tags(_leer_toml(cfg_dir / "tags.toml"), plcs)

    # Un tag que apunta a un PLC deshabilitado no es un error, pero si todos lo
    # estan no hay nada que hacer y conviene decirlo fuerte.
    habilitados = {n for n, c in plcs.items() if c.get("habilitado", True)}
    if not habilitados:
        raise ErrorConfig("Todos los PLC de site.toml estan con habilitado = false")
    if not any(t.plc in habilitados for t in tags):
        raise ErrorConfig(
            "Ningun tag apunta a un PLC habilitado. "
            f"PLC habilitados: {', '.join(sorted(habilitados))}"
        )

    return Config(app=app, plcs=plcs, db=db, tags=tags, raiz=raiz)
