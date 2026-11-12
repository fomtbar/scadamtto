import type { Senal, Vista } from "@/lib/dominio";
import { antiguedad, miles } from "./formato";

function Lampara({ s }: { s: Senal }) {
  return (
    <li className="flex items-center gap-2 py-[3px]">
      <span className="lampara" data-on={s.activa} data-tono={s.tono} aria-hidden />
      <span className={s.activa && s.tono !== "neutro" ? "texto-tono font-semibold" : s.activa ? "" : "text-tenue"} data-tono={s.tono}>
        {s.texto}
      </span>
      <span className="rotulo ml-auto">{s.activa ? "Sí" : "No"}</span>
    </li>
  );
}

/** Señales, contadores de consumibles y salud del enlace con el PLC. */
export function Mantenimiento({ vista }: { vista: Vista }) {
  const grupos = [...new Set(vista.senales.map((s) => s.grupo))];
  const activas = vista.senales.filter((s) => s.activa && s.tono !== "neutro").length;

  return (
    <section className="panel flex flex-col">
      <div className="flex items-baseline justify-between border-b border-linea px-4 py-2">
        <h2 className="rotulo">Mantenimiento</h2>
        <span className={activas ? "texto-tono text-[0.75rem] font-semibold" : "text-[0.75rem] text-tenue"} data-tono="falla">
          {activas ? `${activas} señal${activas > 1 ? "es" : ""} activa${activas > 1 ? "s" : ""}` : "Sin alarmas"}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-x-5 px-4 py-2 sm:grid-cols-2 xl:grid-cols-1">
        {grupos.map((g) => (
          <div key={g} className="py-1">
            <div className="rotulo mb-0.5">{g}</div>
            <ul>
              {vista.senales.filter((s) => s.grupo === g).map((s) => (
                <Lampara key={s.clave} s={s} />
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-linea px-4 py-2">
        <div className="rotulo mb-1">Contadores</div>
        <dl className="grid grid-cols-[1fr_auto] gap-y-0.5">
          {vista.contadores.map((c) => (
            <div key={c.texto} className="contents">
              <dt className="text-tenue">{c.texto}</dt>
              <dd className="num text-right">{miles(c.valor)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="border-t border-linea px-4 py-2">
        <div className="rotulo mb-1">Enlace</div>
        <dl className="grid grid-cols-[1fr_auto] gap-y-0.5">
          <dt className="text-tenue">Programa SCADA del PLC</dt>
          <dd className="texto-tono text-right font-semibold" data-tono={vista.plcVivo ? "neutro" : "aviso"}>
            {vista.plcVivo ? "Corriendo" : "Sin vida"}
          </dd>
          <dt className="text-tenue">Última lectura del adquisidor</dt>
          <dd className="num texto-tono text-right" data-tono={vista.adquisidorAdelantadoSeg !== null ? "aviso" : "neutro"}>
            {vista.segDesdeLectura === null
              ? "—"
              : vista.adquisidorAdelantadoSeg !== null
                ? `reloj ${antiguedad(vista.adquisidorAdelantadoSeg)} adelantado`
                : `hace ${antiguedad(Math.max(0, vista.segDesdeLectura))}`}
          </dd>
          <dt className="text-tenue">Reloj del PLC</dt>
          <dd className="num texto-tono text-right" data-tono={vista.reloj.aviso ? "aviso" : "neutro"}>
            {vista.reloj.plc ?? "—"}
            {vista.reloj.aviso && vista.reloj.difMin !== null ? ` (${vista.reloj.difMin > 0 ? "+" : ""}${vista.reloj.difMin} min)` : ""}
          </dd>
        </dl>
      </div>
    </section>
  );
}
