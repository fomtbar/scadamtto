import "server-only";
import { consultar, sql, tablaValores } from "./db";
import { sinPrefijo, type Tags } from "./dominio";
import { tagsDemo, type Variante } from "./demo";
import type { Celda } from "./celdas";

type Fila = {
  NombreTag: string;
  Valor: number | null;
  Estado: boolean;
  SegLectura: number;
  SegCambio: number;
  Ahora: string;
};

/**
 * DATOS_DEMO: "si" muestra la celda andando; "falla" y "viejo" sirven para
 * ver como se presentan una falla y un dato desactualizado.
 */
function variante(): Variante | null {
  const v = (process.env.DATOS_DEMO ?? "").trim().toLowerCase();
  return v === "si" ? "normal" : v === "falla" || v === "viejo" ? v : null;
}

export function modoDemo(): boolean {
  return variante() !== null;
}

/** Hora del servidor como "YYYY-MM-DD HH:MM:SS" (para el modo demo). */
function ahoraLocal(): string {
  const d = new Date();
  const dos = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())} ${dos(d.getHours())}:${dos(d.getMinutes())}:${dos(d.getSeconds())}`;
}

/**
 * Todas las tags de una celda, sin el prefijo, mas la hora del SQL Server.
 *
 * Las antiguedades se calculan en SQL contra GETDATE(): FechaLectura y
 * FechaHora son datetime sin zona, escritos con la hora local, y asi no hay
 * que adivinar la zona del contenedor.
 */
export async function leerCelda(celda: Celda): Promise<{ tags: Tags; ahora: string }> {
  const demo = variante();
  if (demo) return { tags: tagsDemo(new Date(), demo), ahora: ahoraLocal() };

  const filas = await consultar<Fila>(
    `SELECT NombreTag, Valor, Estado,
            DATEDIFF(SECOND, FechaLectura, GETDATE()) AS SegLectura,
            DATEDIFF(SECOND, FechaHora,    GETDATE()) AS SegCambio,
            CONVERT(varchar(19), GETDATE(), 120)      AS Ahora
       FROM ${tablaValores()}
      WHERE NombreTag LIKE @patron`,
    { patron: [sql.VarChar(60), `${celda.prefijo}.%`] },
  );

  const tags: Tags = {};
  for (const f of filas) {
    const clave = sinPrefijo(f.NombreTag, celda.prefijo);
    if (!clave) continue;
    tags[clave] = { valor: f.Valor, ok: !!f.Estado, segLectura: f.SegLectura, segCambio: f.SegCambio };
  }

  let ahora = filas[0]?.Ahora;
  if (!ahora) {
    const r = await consultar<{ Ahora: string }>("SELECT CONVERT(varchar(19), GETDATE(), 120) AS Ahora");
    ahora = r[0].Ahora;
  }
  return { tags, ahora };
}
