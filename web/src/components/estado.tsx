import type { Vista } from "@/lib/dominio";
import { minSeg, miles } from "./formato";

/** Estado de la celda en grande y de cada jig al lado. */
export function FranjaEstado({ vista }: { vista: Vista }) {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <section className="panel estado flex items-center justify-between gap-4 px-4 py-3" data-tono={vista.celda.tono}>
        <div>
          <div className="rotulo">Estado de la celda</div>
          <div className="texto-tono mt-0.5 text-3xl font-semibold tracking-tight" data-tono={vista.celda.tono}>
            {vista.celda.texto}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-5 gap-y-0.5 text-right">
          <dt className="rotulo self-center">Modo</dt>
          <dd className="num font-semibold">{vista.auto ? "AUTO" : "MANUAL"}</dd>
          <dt className="rotulo self-center">Tipo de auto</dt>
          <dd className="num font-semibold">{vista.tipoAuto ?? "—"}</dd>
        </dl>
      </section>

      {vista.jigs.map((j) => (
        <section key={j.nombre} className="panel estado px-4 py-3" data-tono={j.estado.tono}>
          <div className="flex items-baseline justify-between">
            <span className="rotulo">{j.nombre}</span>
            <span className="texto-tono text-lg font-semibold" data-tono={j.estado.tono}>
              {j.estado.texto}
            </span>
          </div>
          <dl className="mt-1.5 grid grid-cols-2 gap-y-0.5">
            <dt className="text-tenue">Entre piezas</dt>
            <dd className="num text-right font-semibold">{minSeg(j.segEntrePiezas)}</dd>
            <dt className="text-tenue">Acumulado</dt>
            <dd className="num text-right">{miles(j.piezasTotal)}</dd>
          </dl>
        </section>
      ))}
    </div>
  );
}
