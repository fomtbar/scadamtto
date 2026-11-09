/**
 * Catalogo de celdas. Sumar una celda = agregar una linea aca y cargar sus
 * tags en el adquisidor con el mismo prefijo
 * (plc/bloque_scada/generar_tags.py <PREFIJO>).
 *
 * El prefijo es lo que va antes del primer punto en test.ValorActual:
 * "FCA0203.Celda.Estado".
 */

export type Celda = {
  /** Va en la URL: /celda/fca0203 */
  id: string;
  /** Lo que se lee en la solapa. */
  nombre: string;
  /** Prefijo de las tags en la base. */
  prefijo: string;
  descripcion: string;
};

export const CELDAS: Celda[] = [
  {
    id: "fca0203",
    nombre: "FCA 02/03",
    prefijo: "FCA0203",
    descripcion: "Soldadura de butacas · 2 robots Yaskawa · 2 jigs",
  },
];

export function buscarCelda(id: string): Celda | undefined {
  return CELDAS.find((c) => c.id === id.toLowerCase());
}
