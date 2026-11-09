/** 183 -> "3:03". Para tiempos de ciclo. */
export function minSeg(seg: number | null): string {
  if (seg === null) return "—";
  return `${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, "0")}`;
}

/** 312 -> "5 h 12 min". */
export function horasMin(min: number): string {
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

/** 42 -> "42 s", 420 -> "7 min", 7300 -> "2 h". */
export function antiguedad(seg: number | null): string {
  if (seg === null) return "—";
  if (seg < 90) return `${seg} s`;
  if (seg < 5400) return `${Math.round(seg / 60)} min`;
  return `${Math.round(seg / 3600)} h`;
}

export function miles(n: number | null): string {
  return n === null ? "—" : n.toLocaleString("es-AR");
}
