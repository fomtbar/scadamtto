"""Lectura y escritura de config/tags.toml.

El dashboard puede dar de alta, editar y borrar variables, pero la fuente de
verdad sigue siendo el archivo: se versiona, se puede revisar en un diff y
sobrevive a que el proceso no arranque. Guardar los tags en la base habria
significado que un problema de red deje al adquisidor sin saber que leer.

La escritura es atomica (archivo temporal + reemplazo) y deja una copia del
archivo anterior, porque quien edita desde una pantalla no siempre tiene el
proyecto en git a mano.

El TOML se serializa a mano en lugar de usar tomli-w: son escalares planos
dentro de un array de tablas, y evita sumar una dependencia mas al entorno de
la PC de planta.
"""
from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

from src.core.config import MAX_NOMBRE_TAG, ErrorConfig
from src.core.models import MODOS_REGISTRO, TIPOS

_CABECERA = """\
# Tabla de tags a recolectar.
#
# Se puede editar a mano o desde el dashboard (http://localhost:8080).
# OJO: si lo edita el dashboard, los comentarios que agregues dentro de cada
# [[tag]] se pierden al reescribir el archivo. Esta cabecera se conserva.
#
#   nombre       lo que va literal a la columna NombreTag (max 50 caracteres)
#   plc          clave del PLC en site.toml
#   direccion    D5002 / M1000 / W1A0 (Mitsubishi) | DB1.DBW0 / M100.0 (Siemens)
#   tipo         bit | int16 | uint16 | int32 | uint32 | float32
#   escala/offset  valor_final = crudo * escala + offset
#   scan_ms      periodo de lectura
#   registro     "intervalo" graba cada scan | "cambio" solo cuando cambia
#   banda_muerta cuanto tiene que cambiar para grabar (solo con "cambio")
#   heartbeat_s  fuerza un registro cada N segundos aunque no cambie (0 = nunca)
"""

# Orden y valores por defecto de las claves de cada [[tag]].
_CAMPOS: dict[str, object] = {
    "nombre": "", "plc": "", "direccion": "", "tipo": "int16",
    "escala": 1.0, "offset": 0.0, "scan_ms": 1000,
    "registro": "intervalo", "banda_muerta": 0.0, "heartbeat_s": 0,
}


def ruta_tags(raiz: str | Path) -> Path:
    return Path(raiz) / "config" / "tags.toml"


def leer(raiz: str | Path) -> list[dict]:
    ruta = ruta_tags(raiz)
    try:
        with open(ruta, "rb") as f:
            datos = tomllib.load(f)
    except FileNotFoundError:
        return []
    except tomllib.TOMLDecodeError as e:
        raise ErrorConfig(f"{ruta} tiene un error de sintaxis TOML: {e}") from None
    return [{**_CAMPOS, **t} for t in datos.get("tag", [])]


def _escalar(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    texto = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{texto}"'


def serializar(tags: list[dict]) -> str:
    partes = [_CABECERA]
    for t in tags:
        partes.append("\n[[tag]]")
        for clave, defecto in _CAMPOS.items():
            valor = t.get(clave, defecto)
            # Los campos que solo aplican a registro="cambio" se omiten si estan
            # en su valor por defecto, para no ensuciar el archivo.
            if clave in ("banda_muerta", "heartbeat_s") and not valor:
                continue
            partes.append(f"{clave:<12} = {_escalar(valor)}")
    return "\n".join(partes) + "\n"


def validar(tags: list[dict], plcs_validos: set[str]) -> list[dict]:
    """Aplica las mismas reglas que la carga de config, antes de escribir.

    Devuelve los tags normalizados. Lanza ErrorConfig con un mensaje que nombra
    el tag culpable, que es lo que despues ve el usuario en el dashboard.
    """
    from src.core.addressing import parsear

    if not tags:
        raise ErrorConfig("La lista de tags no puede quedar vacia")

    salida: list[dict] = []
    vistos: set[str] = set()
    for i, crudo in enumerate(tags, 1):
        t = {**_CAMPOS, **crudo}
        nombre = str(t["nombre"]).strip()
        donde = f"tag {nombre!r}" if nombre else f"tag #{i}"
        if not nombre:
            raise ErrorConfig(f"{donde}: el nombre no puede estar vacio")
        if len(nombre) > MAX_NOMBRE_TAG:
            raise ErrorConfig(
                f"{donde}: el nombre tiene {len(nombre)} caracteres y la columna "
                f"NombreTag admite {MAX_NOMBRE_TAG}"
            )
        if nombre in vistos:
            raise ErrorConfig(f"El nombre de tag {nombre!r} esta repetido")
        vistos.add(nombre)

        plc = str(t["plc"]).strip()
        if plc not in plcs_validos:
            raise ErrorConfig(
                f"{donde}: el PLC {plc!r} no existe en site.toml. "
                f"Disponibles: {', '.join(sorted(plcs_validos)) or '(ninguno)'}"
            )
        tipo = str(t["tipo"]).lower()
        if tipo not in TIPOS:
            raise ErrorConfig(f"{donde}: tipo {tipo!r} invalido. Validos: {', '.join(TIPOS)}")
        registro = str(t["registro"]).lower()
        if registro not in MODOS_REGISTRO:
            raise ErrorConfig(
                f"{donde}: registro {registro!r} invalido. Validos: {', '.join(MODOS_REGISTRO)}"
            )
        direccion = str(t["direccion"]).strip().upper()
        if not direccion:
            raise ErrorConfig(f"{donde}: falta la direccion")

        try:
            scan_ms = int(t["scan_ms"])
            escala = float(t["escala"])
            offset = float(t["offset"])
            banda = float(t["banda_muerta"])
            heartbeat = int(t["heartbeat_s"])
        except (TypeError, ValueError) as e:
            raise ErrorConfig(f"{donde}: valor numerico invalido ({e})") from None
        if scan_ms < 10:
            raise ErrorConfig(f"{donde}: scan_ms {scan_ms} es demasiado chico (minimo 10)")

        salida.append({
            "nombre": nombre, "plc": plc, "direccion": direccion, "tipo": tipo,
            "escala": escala, "offset": offset, "scan_ms": scan_ms,
            "registro": registro, "banda_muerta": banda, "heartbeat_s": heartbeat,
        })
    return salida


def validar_direccion(marca: str, direccion: str, tipo: str) -> None:
    """Chequea que la direccion exista para esa marca y concuerde con el tipo.

    Va aparte de validar() porque necesita saber la marca del PLC, que vive en
    site.toml. Lanza ErrorConfig con el mensaje del parser, que ya explica los
    formatos validos.
    """
    from src.core.addressing import parsear

    try:
        d = parsear(marca, direccion)
    except ValueError as e:
        raise ErrorConfig(str(e)) from None
    es_bit = tipo == "bit"
    if d.es_bit != es_bit:
        raise ErrorConfig(
            f"{direccion} es una direccion de {'bit' if d.es_bit else 'palabra'} "
            f"pero el tipo elegido es {tipo!r}"
        )


def escribir(raiz: str | Path, tags: list[dict]) -> Path:
    """Reescribe tags.toml de forma atomica, dejando copia del anterior."""
    ruta = ruta_tags(raiz)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        shutil.copyfile(ruta, ruta.with_suffix(".toml.bak"))
    tmp = ruta.with_suffix(".toml.tmp")
    tmp.write_text(serializar(tags), encoding="utf-8")
    # os.replace via Path.replace: el reemplazo es atomico, asi que nunca queda
    # un tags.toml a medio escribir si se corta la luz justo ahi.
    tmp.replace(ruta)
    return ruta
