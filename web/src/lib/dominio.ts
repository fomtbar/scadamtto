/**
 * Reglas puras: de las filas crudas de test.ValorActual a lo que se ve en
 * pantalla. Sin base, sin React y sin reloj propio (la hora entra como
 * parametro), para poder probarlo entero con vitest.
 *
 * Los codigos y direcciones salen del bloque SCADA del PLC:
 * plc/bloque_scada/LEEME.md en la raiz del proyecto.
 */

import { FALLAS, N_ULTIMAS, type DefFalla } from "./fallas";

/** Una fila de ValorActual, ya sin el prefijo de la celda en la clave. */
export type Lectura = {
  /** null si la ultima lectura fallo. */
  valor: number | null;
  /** Columna Estado: 1 = lectura buena. */
  ok: boolean;
  /** Segundos desde la ultima lectura (FechaLectura). */
  segLectura: number;
  /** Segundos desde el ultimo cambio de valor (FechaHora). */
  segCambio: number;
};

export type Tags = Record<string, Lectura>;

export type Tono = "neutro" | "marcha" | "aviso" | "falla";

export type Estado = { codigo: number | null; texto: string; tono: Tono };

export type Hora = {
  hora: number;
  dia: "hoy" | "ayer";
  piezasJ1: number;
  piezasJ2: number;
  segProd: number;
  segFalla: number;
  enCurso: boolean;
  /** false si el renglon es de otro dia (el PLC estuvo apagado esa hora). */
  valido: boolean;
};

export type Senal = { clave: string; texto: string; activa: boolean; tono: Tono; grupo: string };

/** Referencia para seguir la falla en GX Works2: "M3841 · F073" (marca que la dispara y codigo del PLC). */
export function refFalla(def: DefFalla): string {
  return `${def.dispositivo} · F${String(def.codigo).padStart(3, "0")}`;
}

export type FallaAcumulada = { def: DefFalla; veces: number; seg: number; activa: boolean };

export type FallaReciente = {
  /** 1 = la mas nueva. */
  orden: number;
  codigo: number;
  /** null si el codigo no esta en el catalogo (programa del PLC mas nuevo que la web). */
  def: DefFalla | null;
  /** "dd/mm hh:mm", con "/aa" si es de otro anio. */
  cuando: string;
  activa: boolean;
};

export type VistaFallas = {
  /** El adquisidor ya trae las tags de fallas (bloque SCADA con la seccion 10). */
  hayTags: boolean;
  activas: DefFalla[];
  ultimas: FallaReciente[];
  /** Solo las que aparecieron alguna vez, de mas veces a menos. */
  acumulado: FallaAcumulada[];
};

export type Vista = {
  hayDatos: boolean;
  /** El adquisidor no leyo en el ultimo minuto: los valores pueden ser viejos. */
  desactualizado: boolean;
  segDesdeLectura: number | null;
  /**
   * La ultima lectura figura en el futuro: el reloj con que el adquisidor
   * fecha las filas (el de su PC, si no usa hora_servidor) esta adelantado
   * respecto del SQL Server. Segundos de adelanto, o null si esta bien.
   * Mientras pase, el aviso de "dato desactualizado" no puede funcionar.
   */
  adquisidorAdelantadoSeg: number | null;
  /** El contador de vida del PLC sigue cambiando. */
  plcVivo: boolean;
  celda: Estado;
  auto: boolean;
  tipoAuto: number | null;
  jigs: { nombre: string; estado: Estado; segEntrePiezas: number | null; piezasTotal: number | null }[];
  hoy: { piezasJ1: number; piezasJ2: number; piezas: number; minProd: number; minFalla: number; pctProd: number | null };
  horas: Hora[];
  senales: Senal[];
  contadores: { texto: string; valor: number | null }[];
  reloj: { plc: string | null; servidor: string; difMin: number | null; aviso: boolean };
  fallas: VistaFallas;
};

export const SEG_DESACTUALIZADO = 60;
export const SEG_VIDA = 15;
export const MIN_RELOJ = 5;
/** Tolerancia para considerar que una lectura "del futuro" es un reloj corrido. */
export const SEG_RELOJ_ADQUISIDOR = 30;

const ESTADOS: Record<number, Omit<Estado, "codigo">> = {
  0: { texto: "Sin modo", tono: "neutro" },
  1: { texto: "Manual", tono: "aviso" },
  2: { texto: "Auto en espera", tono: "neutro" },
  3: { texto: "Produciendo", tono: "marcha" },
  4: { texto: "Falla", tono: "falla" },
  5: { texto: "Emergencia", tono: "falla" },
  6: { texto: "Dry run", tono: "aviso" },
};

export function estadoDe(codigo: number | null | undefined): Estado {
  if (codigo === null || codigo === undefined) return { codigo: null, texto: "Sin dato", tono: "neutro" };
  const e = ESTADOS[codigo];
  return e ? { codigo, ...e } : { codigo, texto: `Código ${codigo}`, tono: "aviso" };
}

function valor(tags: Tags, clave: string): number | null {
  const t = tags[clave];
  return t && t.ok && t.valor !== null ? t.valor : null;
}

function bit(tags: Tags, clave: string): boolean {
  return (valor(tags, clave) ?? 0) !== 0;
}

/** MMDD del dia anterior. Recibe el anio para resolver bien el 29/02. */
export function ayerMMDD(mmdd: number, anio: number): number {
  const d = new Date(anio, Math.floor(mmdd / 100) - 1, (mmdd % 100) - 1);
  return (d.getMonth() + 1) * 100 + d.getDate();
}

/** "2026-11-09 14:05:33" -> partes. Es la hora del SQL Server. */
export function partesFecha(texto: string) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(texto);
  if (!m) throw new Error(`Fecha del servidor con formato inesperado: ${texto}`);
  const [anio, mes, dia, hora, minuto] = m.slice(1).map(Number);
  return { anio, mes, dia, hora, minuto, mmdd: mes * 100 + dia };
}

/**
 * Tabla de 24 horas que arma el PLC (D6100 + hora*5).
 *
 * Cada renglon trae la fecha MMDD en que se lleno. Las horas hasta la
 * actual tienen que ser de hoy; las posteriores, de ayer. Lo que no
 * coincide es un renglon viejo (el PLC estuvo apagado) y se muestra vacio.
 * Ordena de la hora mas vieja a la actual.
 */
export function tablaHoras(tags: Tags, hoy: number, horaActual: number, anio: number): Hora[] {
  const ayer = ayerMMDD(hoy, anio);
  const horas: Hora[] = [];
  for (let paso = 1; paso <= 24; paso++) {
    const hora = (horaActual + paso) % 24;
    const dia = hora <= horaActual ? "hoy" : "ayer";
    const pre = `Hora.${String(hora).padStart(2, "0")}.`;
    const fecha = valor(tags, pre + "Fecha");
    const valido = fecha === (dia === "hoy" ? hoy : ayer);
    const n = (c: string) => (valido ? (valor(tags, pre + c) ?? 0) : 0);
    horas.push({
      hora,
      dia,
      piezasJ1: n("PiezasJ1"),
      piezasJ2: n("PiezasJ2"),
      segProd: n("SegProd"),
      segFalla: n("SegFalla"),
      enCurso: hora === horaActual,
      valido,
    });
  }
  return horas;
}

const dos = (n: number) => String(n).padStart(2, "0");

/**
 * Fecha de una falla del registro del PLC. El PLC guarda MMDD sin anio: si
 * el MMDD es posterior a hoy, la falla es del anio anterior.
 */
export function cuandoFalla(mmdd: number, hhmm: number, hoy: number, anio: number): string {
  const delAnio = mmdd > hoy ? anio - 1 : anio;
  const texto = `${dos(mmdd % 100)}/${dos(Math.floor(mmdd / 100))} ${dos(Math.floor(hhmm / 100))}:${dos(hhmm % 100)}`;
  return delAnio === anio ? texto : `${texto.slice(0, 5)}/${String(delAnio).slice(2)}${texto.slice(5)}`;
}

const POR_CODIGO = new Map(FALLAS.map((f) => [f.codigo, f]));

/**
 * Fallas: activas ahora, registro de las ultimas (D6800..) y acumulado por
 * tipo (veces y segundos activa). Ver plc/bloque_scada/fallas.py.
 */
export function vistaFallas(tags: Tags, hoy: number, anio: number): VistaFallas {
  const clave = (c: number) => `Falla.F${String(c).padStart(3, "0")}`;
  const activa = (c: number) => bit(tags, `${clave(c)}.Activa`);
  const hayTags = `${clave(1)}.Veces` in tags || "Falla.Ult.01.Codigo" in tags;

  const ultimas: FallaReciente[] = [];
  for (let n = 1; n <= N_ULTIMAS; n++) {
    const pre = `Falla.Ult.${dos(n)}.`;
    const codigo = valor(tags, pre + "Codigo");
    const mmdd = valor(tags, pre + "Fecha");
    const hhmm = valor(tags, pre + "Hora");
    // Codigo 0 = renglon todavia vacio (el registro se llena de a uno).
    if (!codigo || mmdd === null || hhmm === null || mmdd < 101 || mmdd > 1231) continue;
    ultimas.push({
      orden: n,
      codigo,
      def: POR_CODIGO.get(codigo) ?? null,
      cuando: cuandoFalla(mmdd, hhmm, hoy, anio),
      activa: activa(codigo),
    });
  }

  const acumulado = FALLAS.map((def) => ({
    def,
    veces: valor(tags, `${clave(def.codigo)}.Veces`) ?? 0,
    seg: valor(tags, `${clave(def.codigo)}.Seg`) ?? 0,
    activa: activa(def.codigo),
  }))
    .filter((f) => f.veces > 0 || f.seg > 0)
    .sort((a, b) => b.veces - a.veces || b.seg - a.seg);

  return { hayTags, activas: FALLAS.filter((f) => activa(f.codigo)), ultimas, acumulado };
}

const SENALES: Omit<Senal, "activa">[] = [
  { clave: "Celda.Emergencia", texto: "Parada de emergencia", tono: "falla", grupo: "Celda" },
  { clave: "Celda.FallaGeneral", texto: "Falla general", tono: "falla", grupo: "Celda" },
  { clave: "Celda.Auto", texto: "Modo automático", tono: "neutro", grupo: "Celda" },
  { clave: "JIG1.Falla", texto: "Falla JIG1", tono: "falla", grupo: "Jigs" },
  { clave: "JIG2.Falla", texto: "Falla JIG2", tono: "falla", grupo: "Jigs" },
  { clave: "RB1.Falla", texto: "Falla RB1", tono: "falla", grupo: "Robot 1" },
  { clave: "RB1.Alarma", texto: "Alarma RB1", tono: "falla", grupo: "Robot 1" },
  { clave: "RB1.ModoTeach", texto: "RB1 en teach", tono: "aviso", grupo: "Robot 1" },
  { clave: "RB1.ServoOn", texto: "RB1 servo ON", tono: "neutro", grupo: "Robot 1" },
  { clave: "RB2.Falla", texto: "Falla RB2", tono: "falla", grupo: "Robot 2" },
  { clave: "RB2.Alarma", texto: "Alarma RB2", tono: "falla", grupo: "Robot 2" },
  { clave: "RB2.ModoTeach", texto: "RB2 en teach", tono: "aviso", grupo: "Robot 2" },
  { clave: "RB2.ServoOn", texto: "RB2 servo ON", tono: "neutro", grupo: "Robot 2" },
  { clave: "PLC.FallaCCLink", texto: "Falla CC-Link", tono: "falla", grupo: "PLC" },
  { clave: "PLC.BateriaBaja", texto: "Batería del PLC baja", tono: "aviso", grupo: "PLC" },
];

const CONTADORES: [string, string][] = [
  ["JIG1.PiezasTotal", "Piezas JIG1 (acumulado)"],
  ["JIG2.PiezasTotal", "Piezas JIG2 (acumulado)"],
  ["Celda.FallasTotal", "Fallas (acumulado)"],
  ["RB1.CambiosPuntaTotal", "Cambios de punta RB1"],
  ["RB2.CambiosPuntaTotal", "Cambios de punta RB2"],
  ["RB1.LimpiezasToberaTotal", "Limpiezas de tobera RB1"],
  ["RB2.LimpiezasToberaTotal", "Limpiezas de tobera RB2"],
];

/**
 * Arma todo lo que muestra una celda.
 *
 * @param ahoraServidor GETDATE() del SQL Server como "YYYY-MM-DD HH:MM:SS".
 *   Se usa la hora del servidor de base y no la del contenedor: es la misma
 *   referencia contra la que se miden FechaLectura y FechaHora.
 */
export function construirVista(tags: Tags, ahoraServidor: string): Vista {
  const srv = partesFecha(ahoraServidor);
  const claves = Object.keys(tags);
  const hayDatos = claves.length > 0;

  const segDesdeLectura = hayDatos ? Math.min(...claves.map((k) => tags[k].segLectura)) : null;
  const desactualizado = !hayDatos || segDesdeLectura === null || segDesdeLectura > SEG_DESACTUALIZADO;
  const vida = tags["Celda.Vida"];
  const plcVivo = !!vida && vida.ok && vida.segCambio <= SEG_VIDA;

  // Reloj del PLC. Si no llego (bloque sin cargar, PLC en 0), se usa el del
  // servidor para ubicar la tabla de horas.
  const fechaPlc = valor(tags, "PLC.FechaMMDD");
  const horaPlc = valor(tags, "PLC.HoraHHMM");
  const relojPlcValido = !!fechaPlc && fechaPlc >= 101 && fechaPlc <= 1231 && horaPlc !== null && horaPlc < 2400;
  const hoy = relojPlcValido ? fechaPlc! : srv.mmdd;
  const horaActual = relojPlcValido ? Math.floor(horaPlc! / 100) : srv.hora;

  let difMin: number | null = null;
  let plcTexto: string | null = null;
  if (relojPlcValido) {
    const plc = new Date(srv.anio, Math.floor(fechaPlc! / 100) - 1, fechaPlc! % 100, Math.floor(horaPlc! / 100), horaPlc! % 100);
    const ser = new Date(srv.anio, srv.mes - 1, srv.dia, srv.hora, srv.minuto);
    difMin = Math.round((plc.getTime() - ser.getTime()) / 60_000);
    plcTexto = `${dos(fechaPlc! % 100)}/${dos(Math.floor(fechaPlc! / 100))} ${dos(Math.floor(horaPlc! / 100))}:${dos(horaPlc! % 100)}`;
  }

  const horas = tablaHoras(tags, hoy, horaActual, srv.anio);
  const deHoy = horas.filter((h) => h.dia === "hoy" && h.valido);
  const piezasJ1 = deHoy.reduce((a, h) => a + h.piezasJ1, 0);
  const piezasJ2 = deHoy.reduce((a, h) => a + h.piezasJ2, 0);
  const segProd = deHoy.reduce((a, h) => a + h.segProd, 0);
  const segFalla = deHoy.reduce((a, h) => a + h.segFalla, 0);
  // % produciendo sobre el tiempo transcurrido del dia segun el PLC.
  const minDelDia = horaActual * 60 + (relojPlcValido ? horaPlc! % 100 : srv.minuto);
  const pctProd = minDelDia > 0 ? Math.min(100, Math.round((segProd / 60 / minDelDia) * 100)) : null;

  const jig = (n: 1 | 2) => {
    const ds = valor(tags, `JIG${n}.TiempoEntrePiezas_ds`);
    return {
      nombre: `JIG${n}`,
      estado: estadoDe(valor(tags, `JIG${n}.Estado`)),
      segEntrePiezas: ds ? Math.round(ds / 10) : null,
      piezasTotal: valor(tags, `JIG${n}.PiezasTotal`),
    };
  };

  return {
    hayDatos,
    desactualizado,
    segDesdeLectura,
    adquisidorAdelantadoSeg:
      segDesdeLectura !== null && segDesdeLectura < -SEG_RELOJ_ADQUISIDOR ? -segDesdeLectura : null,
    plcVivo,
    celda: estadoDe(valor(tags, "Celda.Estado")),
    auto: bit(tags, "Celda.Auto"),
    tipoAuto: valor(tags, "Celda.TipoAuto"),
    jigs: [jig(1), jig(2)],
    hoy: {
      piezasJ1,
      piezasJ2,
      piezas: piezasJ1 + piezasJ2,
      minProd: Math.round(segProd / 60),
      minFalla: Math.round(segFalla / 60),
      pctProd,
    },
    horas,
    senales: SENALES.map((s) => ({ ...s, activa: bit(tags, s.clave) })),
    contadores: CONTADORES.map(([clave, texto]) => ({ texto, valor: valor(tags, clave) })),
    reloj: {
      plc: plcTexto,
      servidor: ahoraServidor.slice(11, 16),
      difMin,
      aviso: difMin !== null && Math.abs(difMin) > MIN_RELOJ,
    },
    fallas: vistaFallas(tags, hoy, srv.anio),
  };
}

/** Quita el prefijo de la celda: "FCA0203.Celda.Estado" -> "Celda.Estado". */
export function sinPrefijo(nombreTag: string, prefijo: string): string | null {
  const p = prefijo + ".";
  return nombreTag.startsWith(p) ? nombreTag.slice(p.length) : null;
}
