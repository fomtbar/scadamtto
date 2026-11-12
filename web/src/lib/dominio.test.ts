import { describe, expect, it } from "vitest";
import { ayerMMDD, construirVista, cuandoFalla, estadoDe, refFalla, sinPrefijo, tablaHoras, vistaFallas, type Tags } from "./dominio";
import { FALLAS } from "./fallas";

const leida = (valor: number | null, extra: Partial<Tags[string]> = {}) => ({
  valor,
  ok: true,
  segLectura: 2,
  segCambio: 2,
  ...extra,
});

function renglon(tags: Tags, hora: number, fecha: number, j1: number, j2: number, prod = 0, falla = 0) {
  const p = `Hora.${String(hora).padStart(2, "0")}.`;
  tags[p + "Fecha"] = leida(fecha);
  tags[p + "PiezasJ1"] = leida(j1);
  tags[p + "PiezasJ2"] = leida(j2);
  tags[p + "SegProd"] = leida(prod);
  tags[p + "SegFalla"] = leida(falla);
}

describe("ayerMMDD", () => {
  it("resta un dia dentro del mes", () => expect(ayerMMDD(1109, 2026)).toBe(1108));
  it("cruza el anio", () => expect(ayerMMDD(101, 2026)).toBe(1231));
  it("cruza el mes", () => expect(ayerMMDD(301, 2026)).toBe(228));
  it("respeta el bisiesto", () => expect(ayerMMDD(301, 2028)).toBe(229));
});

describe("estadoDe", () => {
  it("traduce los codigos del PLC", () => {
    expect(estadoDe(3)).toMatchObject({ texto: "Produciendo", tono: "marcha" });
    expect(estadoDe(5)).toMatchObject({ texto: "Emergencia", tono: "falla" });
  });
  it("no rompe con codigos desconocidos ni sin dato", () => {
    expect(estadoDe(9).tono).toBe("aviso");
    expect(estadoDe(null).texto).toBe("Sin dato");
  });
});

describe("tablaHoras", () => {
  it("ordena de la hora mas vieja a la actual y marca la actual", () => {
    const horas = tablaHoras({}, 1109, 14, 2026);
    expect(horas).toHaveLength(24);
    expect(horas[0].hora).toBe(15);
    expect(horas[0].dia).toBe("ayer");
    expect(horas[23]).toMatchObject({ hora: 14, dia: "hoy", enCurso: true });
  });

  it("acepta horas de hoy hasta la actual y de ayer despues", () => {
    const tags: Tags = {};
    renglon(tags, 8, 1109, 10, 12);
    renglon(tags, 20, 1108, 5, 4);
    const horas = tablaHoras(tags, 1109, 14, 2026);
    expect(horas.find((h) => h.hora === 8)).toMatchObject({ valido: true, piezasJ1: 10, piezasJ2: 12 });
    expect(horas.find((h) => h.hora === 20)).toMatchObject({ valido: true, dia: "ayer", piezasJ1: 5 });
  });

  it("descarta renglones viejos de cuando el PLC estuvo apagado", () => {
    const tags: Tags = {};
    renglon(tags, 9, 1105, 30, 30); // de hace 4 dias
    renglon(tags, 20, 1109, 7, 7); // hora futura con fecha de hoy: imposible
    const horas = tablaHoras(tags, 1109, 14, 2026);
    expect(horas.find((h) => h.hora === 9)).toMatchObject({ valido: false, piezasJ1: 0 });
    expect(horas.find((h) => h.hora === 20)).toMatchObject({ valido: false, piezasJ1: 0 });
  });

  it("a las 0 h todo lo demas es de ayer", () => {
    const tags: Tags = {};
    renglon(tags, 23, 1231, 3, 3);
    renglon(tags, 0, 101, 1, 0);
    const horas = tablaHoras(tags, 101, 0, 2027);
    expect(horas.find((h) => h.hora === 23)).toMatchObject({ dia: "ayer", valido: true });
    expect(horas[23]).toMatchObject({ hora: 0, dia: "hoy", valido: true, piezasJ1: 1 });
  });
});

describe("construirVista", () => {
  const base = (): Tags => ({
    "Celda.Vida": leida(1234),
    "Celda.Estado": leida(3),
    "JIG1.Estado": leida(3),
    "JIG2.Estado": leida(2),
    "JIG1.TiempoEntrePiezas_ds": leida(1834),
    "PLC.FechaMMDD": leida(1109),
    "PLC.HoraHHMM": leida(1430),
    "Celda.Emergencia": leida(0),
    "RB1.Alarma": leida(1),
  });

  it("suma solo las horas validas de hoy", () => {
    const tags = base();
    renglon(tags, 8, 1109, 10, 12, 3000, 120);
    renglon(tags, 9, 1109, 11, 9, 3300, 0);
    renglon(tags, 22, 1108, 50, 50, 3600, 0); // ayer: no cuenta para hoy
    const v = construirVista(tags, "2026-11-09 14:31:05");
    expect(v.hoy).toMatchObject({ piezasJ1: 21, piezasJ2: 21, piezas: 42, minProd: 105, minFalla: 2 });
    expect(v.celda.texto).toBe("Produciendo");
    expect(v.jigs[0].segEntrePiezas).toBe(183);
    expect(v.senales.find((s) => s.clave === "RB1.Alarma")?.activa).toBe(true);
  });

  it("marca desactualizado si el adquisidor no lee hace mas de un minuto", () => {
    const tags = base();
    for (const k of Object.keys(tags)) tags[k] = { ...tags[k], segLectura: 300 };
    expect(construirVista(tags, "2026-11-09 14:31:05").desactualizado).toBe(true);
  });

  it("detecta el PLC sin programa cuando la vida no cambia", () => {
    const tags = base();
    tags["Celda.Vida"] = leida(1234, { segCambio: 120 });
    expect(construirVista(tags, "2026-11-09 14:31:05").plcVivo).toBe(false);
  });

  it("avisa si el reloj del PLC esta corrido", () => {
    const tags = base(); // PLC 14:30
    expect(construirVista(tags, "2026-11-09 14:31:05").reloj.aviso).toBe(false);
    expect(construirVista(tags, "2026-11-09 15:10:00").reloj).toMatchObject({ difMin: -40, aviso: true });
  });

  it("sin datos no rompe y usa la hora del servidor", () => {
    const v = construirVista({}, "2026-11-09 08:00:00");
    expect(v.hayDatos).toBe(false);
    expect(v.desactualizado).toBe(true);
    expect(v.horas[23].hora).toBe(8);
    expect(v.celda.texto).toBe("Sin dato");
  });

  it("ignora valores de lecturas fallidas", () => {
    const tags = base();
    tags["Celda.Estado"] = leida(4, { ok: false });
    expect(construirVista(tags, "2026-11-09 14:31:05").celda.texto).toBe("Sin dato");
  });
});

describe("sinPrefijo", () => {
  it("separa la celda del nombre", () => {
    expect(sinPrefijo("FCA0203.Hora.07.PiezasJ1", "FCA0203")).toBe("Hora.07.PiezasJ1");
    expect(sinPrefijo("FCA0405.Celda.Estado", "FCA0203")).toBeNull();
  });
});

describe("cuandoFalla", () => {
  it("arma dd/mm hh:mm del anio en curso", () => expect(cuandoFalla(1109, 705, 1110, 2026)).toBe("09/11 07:05"));
  it("si el MMDD es posterior a hoy, es del anio anterior", () =>
    expect(cuandoFalla(1230, 2359, 102, 2027)).toBe("30/12/26 23:59"));
});

describe("refFalla", () => {
  it("marca y codigo de 3 digitos", () =>
    expect(refFalla(FALLAS.find((f) => f.dispositivo === "M3841")!)).toBe("M3841 · F073"));
  it("codigo de un digito", () => expect(refFalla(FALLAS[0])).toBe("M1840 · F001"));
});

describe("vistaFallas", () => {
  const ult = (tags: Tags, n: number, codigo: number, mmdd: number, hhmm: number) => {
    const p = `Falla.Ult.${String(n).padStart(2, "0")}.`;
    tags[p + "Codigo"] = leida(codigo);
    tags[p + "Fecha"] = leida(mmdd);
    tags[p + "Hora"] = leida(hhmm);
  };

  it("sin tags de fallas avisa que no estan cargadas", () => {
    const v = vistaFallas({}, 1110, 2026);
    expect(v.hayTags).toBe(false);
    expect(v.ultimas).toEqual([]);
    expect(v.acumulado).toEqual([]);
  });

  it("saltea renglones vacios y no rompe con codigos desconocidos", () => {
    const tags: Tags = {};
    ult(tags, 1, 5, 1110, 830);
    ult(tags, 2, 0, 0, 0);
    ult(tags, 3, 999, 1109, 2210);
    tags["Falla.F005.Activa"] = leida(1);
    const v = vistaFallas(tags, 1110, 2026);
    expect(v.hayTags).toBe(true);
    expect(v.ultimas.map((u) => u.orden)).toEqual([1, 3]);
    expect(v.ultimas[0]).toMatchObject({ codigo: 5, activa: true, cuando: "10/11 08:30" });
    expect(v.ultimas[0].def?.dispositivo).toBe("M1844");
    expect(v.ultimas[1].def).toBeNull();
    expect(v.activas.map((a) => a.codigo)).toEqual([5]);
  });

  it("acumulado: solo las que aparecieron, de mas veces a menos", () => {
    const tags: Tags = {};
    tags["Falla.F001.Veces"] = leida(3);
    tags["Falla.F001.Seg"] = leida(100);
    tags["Falla.F002.Veces"] = leida(9);
    tags["Falla.F002.Seg"] = leida(10);
    tags["Falla.F003.Veces"] = leida(0);
    tags["Falla.F003.Seg"] = leida(0);
    const v = vistaFallas(tags, 1110, 2026);
    expect(v.acumulado.map((a) => [a.def.codigo, a.veces, a.seg])).toEqual([
      [2, 9, 10],
      [1, 3, 100],
    ]);
  });
});

describe("reloj del adquisidor", () => {
  it("detecta lecturas fechadas en el futuro", () => {
    const tags: Tags = { "Celda.Vida": leida(5, { segLectura: -1930, segCambio: -1930 }) };
    const v = construirVista(tags, "2026-11-12 07:57:00");
    expect(v.adquisidorAdelantadoSeg).toBe(1930);
  });
  it("tolera unos segundos de diferencia", () => {
    const tags: Tags = { "Celda.Vida": leida(5, { segLectura: -3, segCambio: -3 }) };
    expect(construirVista(tags, "2026-11-12 07:57:00").adquisidorAdelantadoSeg).toBeNull();
  });
});
