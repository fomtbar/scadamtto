import type { Tags } from "./dominio";
import { FALLAS, N_ULTIMAS } from "./fallas";

/**
 * Datos de ejemplo para DATOS_DEMO=si: sirven para ver la pantalla sin base
 * ni PLC (desarrollo, o para mostrarla antes de cargar el bloque SCADA).
 * Determinista dentro de cada minuto, para que el refresco no salte de mas.
 */

function pseudo(semilla: number): number {
  const x = Math.sin(semilla * 9301 + 49297) * 233280;
  return x - Math.floor(x);
}

export type Variante = "normal" | "falla" | "viejo";

export function tagsDemo(ahora: Date, variante: Variante = "normal"): Tags {
  const tags: Tags = {};
  // "viejo": el adquisidor dejo de leer hace 7 minutos.
  const segLectura = variante === "viejo" ? 420 : 1;
  const poner = (clave: string, valor: number, segCambio = 3) => {
    tags[clave] = { valor, ok: true, segLectura, segCambio: Math.max(segCambio, segLectura) };
  };

  const hora = ahora.getHours();
  const mmdd = (ahora.getMonth() + 1) * 100 + ahora.getDate();
  const ayer = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate() - 1);
  const mmddAyer = (ayer.getMonth() + 1) * 100 + ayer.getDate();
  const minuto = Math.floor(ahora.getTime() / 60_000);

  // Turnos de 6 a 22: fuera de eso la celda esta parada.
  const enTurno = (h: number) => h >= 6 && h < 22;
  const ciclo = minuto % 20; // cada 20 min: 14 produciendo, 3 en espera, 2 en falla, 1 manual
  const estado =
    variante === "falla" ? 4 : !enTurno(hora) ? 2 : ciclo < 14 ? 3 : ciclo < 17 ? 2 : ciclo < 19 ? 4 : 1;

  poner("Celda.Vida", Math.floor(ahora.getTime() / 1000) % 32768, 0);
  poner("Celda.Estado", estado);
  poner("JIG1.Estado", estado === 3 ? 3 : estado);
  poner("JIG2.Estado", estado === 3 && ciclo % 4 === 0 ? 2 : estado);
  poner("Celda.TipoAuto", 2);
  poner("Celda.Auto", estado === 1 ? 0 : 1);
  poner("JIG1.TiempoEntrePiezas_ds", 1650 + Math.round(pseudo(minuto) * 300));
  poner("JIG2.TiempoEntrePiezas_ds", 1720 + Math.round(pseudo(minuto + 7) * 300));
  poner("PLC.FechaMMDD", mmdd);
  poner("PLC.HoraHHMM", hora * 100 + ahora.getMinutes());

  poner("Celda.Emergencia", 0);
  poner("Celda.FallaGeneral", estado === 4 ? 1 : 0);
  poner("JIG1.Falla", 0);
  poner("JIG2.Falla", estado === 4 ? 1 : 0);
  poner("RB1.Falla", 0);
  poner("RB2.Falla", 0);
  poner("RB1.Alarma", 0);
  poner("RB2.Alarma", estado === 4 ? 1 : 0);
  poner("RB1.ModoTeach", variante === "falla" ? 1 : 0);
  poner("RB2.ModoTeach", 0);
  poner("RB1.ServoOn", 1);
  poner("RB2.ServoOn", 1);
  poner("PLC.FallaCCLink", 0);
  poner("PLC.BateriaBaja", 0);

  poner("JIG1.PiezasTotal", 48211 + minuto % 1000);
  poner("JIG2.PiezasTotal", 47903 + minuto % 1000);
  poner("Celda.FallasTotal", 1312);
  poner("RB1.CambiosPuntaTotal", 402);
  poner("RB2.CambiosPuntaTotal", 398);
  poner("RB1.LimpiezasToberaTotal", 5120);
  poner("RB2.LimpiezasToberaTotal", 5087);

  for (let h = 0; h < 24; h++) {
    const deHoy = h <= hora;
    const p = `Hora.${String(h).padStart(2, "0")}.`;
    const activo = enTurno(h);
    // La hora en curso va proporcional a los minutos transcurridos.
    const fraccion = h === hora ? ahora.getMinutes() / 60 : 1;
    const r = pseudo(h + (deHoy ? 0 : 50));
    poner(p + "Fecha", deHoy ? mmdd : mmddAyer);
    poner(p + "PiezasJ1", activo ? Math.round((16 + r * 6) * fraccion) : 0);
    poner(p + "PiezasJ2", activo ? Math.round((15 + pseudo(h + 3) * 6) * fraccion) : 0);
    poner(p + "SegProd", activo ? Math.round((2600 + r * 700) * fraccion) : 0);
    poner(p + "SegFalla", activo ? Math.round(r * 420 * fraccion) : 0);
  }

  // Fallas: algunas frecuentes (alambre, gas, confirmacion de pieza) y el
  // resto en cero, como en una celda real.
  const frecuentes: Record<string, [number, number]> = {
    M1868: [41, 2380], M1884: [37, 2110], M1867: [22, 5400], M1883: [19, 4920],
    M1866: [12, 3010], M2903: [28, 840], M3905: [24, 760], M2841: [9, 1260],
    M3843: [7, 980], M1840: [5, 4100], M1843: [14, 1650], M1873: [3, 2700], M1889: [2, 1900],
  };
  const activaAhora = variante === "falla" ? "M1884" : estado === 4 ? "M1868" : null;
  for (const f of FALLAS) {
    const k = `Falla.F${String(f.codigo).padStart(3, "0")}.`;
    const [veces, seg] = frecuentes[f.dispositivo] ?? [0, 0];
    poner(k + "Activa", f.dispositivo === activaAhora ? 1 : 0);
    poner(k + "Veces", veces);
    poner(k + "Seg", seg);
  }
  const porDispositivo = new Map(FALLAS.map((f) => [f.dispositivo, f.codigo]));
  const registro = ["M1868", "M3905", "M1884", "M1867", "M2903", "M1843", "M1868", "M2841", "M1866", "M1884", "M3843", "M2903"];
  if (activaAhora) registro.unshift(activaAhora);
  for (let n = 1; n <= N_ULTIMAS; n++) {
    const p = `Falla.Ult.${String(n).padStart(2, "0")}.`;
    const dev = registro[n - 1];
    // Una cada ~50 min hacia atras.
    const t = new Date(ahora.getTime() - (n - 1) * 50 * 60_000 - 7 * 60_000);
    poner(p + "Codigo", dev ? porDispositivo.get(dev)! : 0);
    poner(p + "Fecha", dev ? (t.getMonth() + 1) * 100 + t.getDate() : 0);
    poner(p + "Hora", dev ? t.getHours() * 100 + t.getMinutes() : 0);
  }
  return tags;
}
