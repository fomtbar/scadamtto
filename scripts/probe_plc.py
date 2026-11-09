"""Diagnostico de conexion con un PLC Mitsubishi.

Es la herramienta para la PC de planta: dice si el problema es de red, de
puerto, de codificacion o de que otro cliente tiene tomada la conexion, sin
tener que adivinar.

    python scripts/probe_plc.py                        usa config/site.toml
    python scripts/probe_plc.py --ip 192.168.0.103 --puerto 8192
    python scripts/probe_plc.py --barrer                prueba puertos candidatos

Recordatorio: GX Works muestra el puerto del Open Setting en HEX. Un '2000' en
esa tabla es 8192 decimal.
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Puertos que suelen aparecer en los Open Settings, ya convertidos a decimal.
CANDIDATOS = [8192, 1025, 1026, 1027, 1028, 1029, 5007, 5000, 5001, 5002, 12288, 12289, 2000]


def frame_ascii(dispositivo: str = "D*", numero: int = 0, cantidad: int = 1) -> bytes:
    cuerpo = "0010" + "0401" + "0000" + dispositivo + "%06d" % numero + "%04X" % cantidad
    return ("5000" + "00" + "FF" + "03FF" + "00" + "%04X" % len(cuerpo) + cuerpo).encode()


def frame_binario(codigo: int = 0xA8, numero: int = 0, cantidad: int = 1) -> bytes:
    cuerpo = (struct.pack("<HHH", 0x0010, 0x0401, 0x0000)
              + numero.to_bytes(3, "little") + bytes([codigo])
              + struct.pack("<H", cantidad))
    return b"\x50\x00\x00\xff\xff\x03\x00" + struct.pack("<H", len(cuerpo)) + cuerpo


def tcp_abierto(ip: str, puerto: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        s = socket.create_connection((ip, puerto), timeout=timeout)
    except Exception as e:
        return False, type(e).__name__
    origen = s.getsockname()[0]
    s.close()
    return True, origen


def probar_mc(ip: str, puerto: int, numero: int, timeout: float = 4.0) -> dict:
    """Manda un frame 3E en ASCII y otro en binario. Devuelve lo que contesto."""
    salida = {}
    for modo, req in (("ascii", frame_ascii("D*", numero)), ("binario", frame_binario(0xA8, numero))):
        try:
            s = socket.create_connection((ip, puerto), timeout=timeout)
            s.settimeout(timeout)
            s.sendall(req)
            r = s.recv(512)
            s.close()
        except Exception as e:
            salida[modo] = f"sin respuesta ({type(e).__name__})"
            continue
        if not r:
            salida[modo] = "el PLC cerro la conexion sin contestar"
        elif modo == "ascii":
            endcode = r[18:22].decode("ascii", "replace")
            salida[modo] = (f"endcode={endcode} datos={r[22:].decode('ascii','replace')!r}"
                            + ("  <-- OK" if endcode == "0000" else ""))
        else:
            endcode = struct.unpack("<H", r[9:11])[0] if len(r) >= 11 else -1
            salida[modo] = (f"endcode=0x{endcode:04X} datos={r[11:]!r}"
                            + ("  <-- OK" if endcode == 0 else ""))
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip")
    ap.add_argument("--puerto", type=int)
    ap.add_argument("--plc", help="nombre del PLC en site.toml (por defecto, el primer mitsubishi)")
    ap.add_argument("--registro", type=int, default=5002, help="numero de registro D a leer")
    ap.add_argument("--barrer", action="store_true", help="probar todos los puertos candidatos")
    args = ap.parse_args()

    ip, puerto, commtype = args.ip, args.puerto, None
    if ip is None or puerto is None:
        from src.core.config import cargar, raiz_por_defecto
        cfg = cargar(raiz_por_defecto())
        nombre = args.plc or next(
            (n for n, c in cfg.plcs.items() if c["marca"] == "mitsubishi"), None)
        if nombre is None:
            print("No hay ningun PLC mitsubishi en site.toml; usa --ip y --puerto")
            return 2
        c = cfg.plcs[nombre]
        ip = ip or c["ip"]
        puerto = puerto or int(c["puerto"])
        commtype = c.get("commtype")
        print(f"Usando [plc.{nombre}] de site.toml")

    print(f"\nPLC objetivo: {ip}:{puerto}" + (f"  (commtype configurado: {commtype})" if commtype else ""))
    print("=" * 68)

    puertos = CANDIDATOS if args.barrer else [puerto]
    if args.barrer:
        print("\n[barrido de puertos candidatos]")
        abiertos = []
        for p in puertos:
            ok, info = tcp_abierto(ip, p, timeout=1.5)
            if ok:
                abiertos.append(p)
                print(f"  {p:>6} (0x{p:04X})  ABIERTO   origen: {info}")
        if not abiertos:
            print("  ninguno abierto")
            print("\n  -> No hay servicio TCP escuchando. Revisa que la PC tenga una placa")
            print("     en la misma subred que el PLC: el PLC no tiene default router")
            print("     configurado, asi que no se lo puede alcanzar ruteando.")
            return 1
        puertos = abiertos

    for p in puertos:
        ok, info = tcp_abierto(ip, p)
        print(f"\n[TCP {p}]")
        if not ok:
            print(f"  cerrado ({info})")
            print("  -> Revisa el puerto del Open Setting (GX Works lo muestra en HEX)")
            print("     y que la PC este en la misma subred que el PLC.")
            continue
        print(f"  abierto. Direccion de origen usada por Windows: {info}")
        print("  (tiene que ser la placa conectada a la red del PLC)")
        for modo, resultado in probar_mc(ip, p, args.registro).items():
            print(f"  MC 3E {modo:8} -> {resultado}")

    print("\nLectura de la respuesta:")
    print("  endcode 0000  la comunicacion anda; usa ese modo como commtype en site.toml")
    print("  sin respuesta / el PLC cerro la conexion:")
    print("     - el puerto es de 'Socket communication', no de 'MC Protocol', o")
    print("     - otro cliente (GX Works, WinCC) tiene tomada la unica conexion MC, o")
    print("     - el Communication data code del PLC no es el que se esta probando")
    print("  endcode distinto de 0000: hay MC Protocol pero rechazo el pedido")
    print("     (tipico: C059 comando no soportado, C051 cantidad fuera de rango)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
