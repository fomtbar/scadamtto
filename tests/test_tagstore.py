"""Tests del almacen de tags y del colapso de muestras del writer."""
from __future__ import annotations

import tomllib
from datetime import datetime, timedelta

import pytest

from src.core import tagstore
from src.core.config import ErrorConfig
from src.core.models import Muestra
from src.db.writer import _ultima_por_tag

PLCS = {"q", "s7"}


def tag(nombre="D5002", **extra):
    base = {"nombre": nombre, "plc": "q", "direccion": "D5002", "tipo": "int16"}
    return {**base, **extra}


class TestValidacion:
    def test_completa_los_defaults(self):
        t = tagstore.validar([tag()], PLCS)[0]
        assert t["escala"] == 1.0 and t["scan_ms"] == 1000 and t["registro"] == "intervalo"

    def test_normaliza_direccion_a_mayusculas(self):
        assert tagstore.validar([tag(direccion="d5002")], PLCS)[0]["direccion"] == "D5002"

    def test_nombre_vacio(self):
        with pytest.raises(ErrorConfig, match="no puede estar vacio"):
            tagstore.validar([tag(nombre="  ")], PLCS)

    def test_nombre_demasiado_largo(self):
        # La columna NombreTag es varchar(50): pasarse trunca o falla en la DB.
        with pytest.raises(ErrorConfig, match="50"):
            tagstore.validar([tag(nombre="x" * 51)], PLCS)

    def test_nombre_repetido(self):
        with pytest.raises(ErrorConfig, match="repetido"):
            tagstore.validar([tag(), tag()], PLCS)

    def test_plc_inexistente(self):
        with pytest.raises(ErrorConfig, match="no existe en site.toml"):
            tagstore.validar([tag(plc="otro")], PLCS)

    def test_scan_demasiado_chico(self):
        with pytest.raises(ErrorConfig, match="demasiado chico"):
            tagstore.validar([tag(scan_ms=5)], PLCS)

    def test_numero_invalido(self):
        with pytest.raises(ErrorConfig, match="numerico"):
            tagstore.validar([tag(escala="dos")], PLCS)

    def test_lista_vacia(self):
        with pytest.raises(ErrorConfig, match="vacia"):
            tagstore.validar([], PLCS)


class TestValidarDireccion:
    def test_ok(self):
        tagstore.validar_direccion("mitsubishi", "D5002", "int16")
        tagstore.validar_direccion("mitsubishi", "M1000", "bit")
        tagstore.validar_direccion("siemens", "DB1.DBW0", "int16")

    def test_bit_con_direccion_de_palabra(self):
        with pytest.raises(ErrorConfig, match="palabra"):
            tagstore.validar_direccion("mitsubishi", "D5002", "bit")

    def test_palabra_con_direccion_de_bit(self):
        with pytest.raises(ErrorConfig, match="bit"):
            tagstore.validar_direccion("mitsubishi", "M1000", "int16")

    def test_direccion_inexistente(self):
        with pytest.raises(ErrorConfig, match="invalida"):
            tagstore.validar_direccion("mitsubishi", "Z999", "int16")


class TestSerializacion:
    def test_ida_y_vuelta(self, tmp_path):
        originales = tagstore.validar(
            [tag("A"), tag("B", direccion="M1000", tipo="bit", registro="cambio",
                 banda_muerta=0.5, heartbeat_s=60, escala=0.1)],
            PLCS,
        )
        (tmp_path / "config").mkdir()
        tagstore.escribir(tmp_path, originales)
        assert tagstore.leer(tmp_path) == originales

    def test_genera_toml_valido(self):
        texto = tagstore.serializar(tagstore.validar([tag()], PLCS))
        assert tomllib.loads(texto)["tag"][0]["nombre"] == "D5002"

    def test_escapa_comillas_en_el_nombre(self):
        t = tagstore.validar([tag(nombre='raro"comilla')], PLCS)
        assert tomllib.loads(tagstore.serializar(t))["tag"][0]["nombre"] == 'raro"comilla'

    def test_omite_campos_opcionales_en_cero(self):
        # Se comprueba sobre el TOML parseado, no sobre el texto: la cabecera de
        # comentarios nombra esos campos y daria un falso positivo.
        bloque = tomllib.loads(tagstore.serializar(tagstore.validar([tag()], PLCS)))["tag"][0]
        assert "banda_muerta" not in bloque and "heartbeat_s" not in bloque

    def test_deja_copia_de_respaldo(self, tmp_path):
        (tmp_path / "config").mkdir()
        tagstore.escribir(tmp_path, tagstore.validar([tag("A")], PLCS))
        tagstore.escribir(tmp_path, tagstore.validar([tag("B")], PLCS))
        bak = tmp_path / "config" / "tags.toml.bak"
        assert bak.exists() and 'nombre       = "A"' in bak.read_text(encoding="utf-8")

    def test_leer_archivo_inexistente(self, tmp_path):
        assert tagstore.leer(tmp_path) == []


class TestColapso:
    """En modo 'actual' solo interesa la ultima muestra de cada tag."""

    def _m(self, nombre, valor, seg):
        return Muestra(datetime(2026, 1, 1) + timedelta(seconds=seg), nombre, valor, True)

    def test_se_queda_con_la_ultima(self):
        r = _ultima_por_tag([self._m("A", 1, 0), self._m("A", 2, 1), self._m("A", 3, 2)])
        assert len(r) == 1 and r[0].valor == 3

    def test_respeta_tags_distintos(self):
        r = _ultima_por_tag([self._m("A", 1, 0), self._m("B", 9, 1), self._m("A", 2, 2)])
        assert {m.nombre_tag: m.valor for m in r} == {"A": 2, "B": 9}

    def test_lista_vacia(self):
        assert _ultima_por_tag([]) == []

    def test_conserva_una_lectura_fallida_final(self):
        # Si la ultima lectura fallo, eso es lo que tiene que quedar en la tabla:
        # el SCADA necesita ver Estado=0, no el ultimo valor bueno.
        r = _ultima_por_tag([self._m("A", 1, 0), Muestra(datetime(2026, 1, 1, 0, 0, 5), "A", None, False)])
        assert len(r) == 1 and r[0].valor is None and r[0].estado is False
