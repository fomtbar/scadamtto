"""Tests de instancia unica, parada por archivo y del bucle principal."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from src.utils.proceso import InstanciaUnica, ParadaPorArchivo, YaCorriendo

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
PUERTO_TEST = 47899   # distinto del real, para no chocar con un adquisidor corriendo


class TestInstanciaUnica:
    def test_segunda_instancia_falla(self):
        with InstanciaUnica(PUERTO_TEST):
            with pytest.raises(YaCorriendo):
                InstanciaUnica(PUERTO_TEST).adquirir()

    def test_se_libera_al_salir(self):
        with InstanciaUnica(PUERTO_TEST):
            pass
        with InstanciaUnica(PUERTO_TEST):   # no tiene que fallar
            pass

    def test_otro_proceso_lo_ve(self):
        # El caso real: dos procesos distintos, no dos objetos del mismo.
        codigo = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(RAIZ_PROYECTO)!r})
            from src.utils.proceso import InstanciaUnica, YaCorriendo
            try:
                InstanciaUnica({PUERTO_TEST}).adquirir()
            except YaCorriendo:
                sys.exit(3)
            sys.exit(0)
        """)
        with InstanciaUnica(PUERTO_TEST):
            r = subprocess.run([sys.executable, "-c", codigo], timeout=30)
        assert r.returncode == 3


class TestParadaPorArchivo:
    def test_sin_archivo(self, tmp_path):
        p = ParadaPorArchivo(tmp_path)
        assert not p.pedida() and not p.existia_al_arrancar()

    def test_archivo_creado_despues_detiene(self, tmp_path):
        p = ParadaPorArchivo(tmp_path)
        p.ruta.touch()
        assert p.pedida()

    def test_archivo_previo_no_detiene(self, tmp_path):
        # Servicio detenido a proposito + alguien lo corre a mano: no lo frena.
        flag = tmp_path / "stop.flag"
        flag.touch()
        viejo = time.time() - 60
        os.utime(flag, (viejo, viejo))
        p = ParadaPorArchivo(tmp_path)
        assert p.existia_al_arrancar() and not p.pedida()

    def test_tocar_de_nuevo_el_previo_detiene(self, tmp_path):
        flag = tmp_path / "stop.flag"
        flag.touch()
        viejo = time.time() - 60
        os.utime(flag, (viejo, viejo))
        p = ParadaPorArchivo(tmp_path)
        flag.touch()   # lo que hace detener.cmd
        assert p.pedida()


@pytest.fixture
def raiz_mock(tmp_path):
    """Raiz de proyecto completa con PLC simulado y una DB inalcanzable.

    La DB inalcanzable es a proposito: el test es sobre el ciclo de vida, no
    sobre SQL Server, y las muestras quedan en el buffer local.
    """
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.toml").write_text(
        "[app]\nweb_habilitado = false\nreconexion_max_s = 1.0\n", encoding="utf-8")
    (cfg / "site.toml").write_text(textwrap.dedent("""
        [plc.sim]
        marca = "mock"
        ip = "0.0.0.0"
        puerto = 0

        [db]
        servidor = "127.0.0.1"
        puerto = 1
        base = "x"
        usuario = "x"
        password = "x"
        timeout_s = 1.0
    """), encoding="utf-8")
    (cfg / "tags.toml").write_text(textwrap.dedent("""
        [[tag]]
        nombre = "T1"
        plc = "sim"
        direccion = "D100"
        tipo = "int16"
        scan_ms = 100
    """), encoding="utf-8")
    return tmp_path


def test_stop_flag_detiene_el_servicio(raiz_mock, monkeypatch):
    import main

    monkeypatch.setattr(main, "configurar", lambda *a, **k: None)
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(codigo=main._correr(raiz_mock)))
    hilo.start()
    time.sleep(2.0)
    assert hilo.is_alive(), "el servicio se cerro solo antes de pedirle la parada"

    (raiz_mock / "stop.flag").touch()
    hilo.join(timeout=30)
    assert not hilo.is_alive(), "el servicio no atendio el stop.flag"
    assert resultado["codigo"] == main.SALIDA_OK
