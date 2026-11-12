import type { Hora, Vista } from "@/lib/dominio";
import { horasMin } from "./formato";

function Indicador({ rotulo, valor, detalle }: { rotulo: string; valor: string; detalle?: string }) {
  return (
    <div className="border-l border-linea px-4 py-2 first:border-l-0">
      <div className="rotulo">{rotulo}</div>
      <div className="num text-2xl font-semibold leading-tight">{valor}</div>
      {detalle ? <div className="num text-[0.75rem] text-tenue">{detalle}</div> : null}
    </div>
  );
}

/** Barras de piezas por hora, apiladas JIG1 (abajo) y JIG2 (arriba). SVG propio. */
function GraficoHoras({ horas }: { horas: Hora[] }) {
  const ancho = 960;
  const alto = 190;
  const izq = 30;
  const arriba = 16;
  const abajo = 22;
  const util = alto - arriba - abajo;
  const paso = (ancho - izq) / horas.length;
  const barra = paso * 0.62;

  const maximo = Math.max(10, ...horas.map((h) => h.piezasJ1 + h.piezasJ2));
  const tope = Math.ceil(maximo / 10) * 10;
  const y = (v: number) => arriba + util - (v / tope) * util;
  const marcas = [0, tope / 2, tope];

  return (
    <svg
      viewBox={`0 0 ${ancho} ${alto}`}
      className="h-auto w-full"
      role="img"
      aria-label="Piezas por hora en las últimas 24 horas"
    >
      {marcas.map((m) => (
        <g key={m}>
          <line x1={izq} x2={ancho} y1={y(m)} y2={y(m)} stroke="var(--linea)" strokeWidth={1} />
          <text x={izq - 6} y={y(m) + 3.5} textAnchor="end" fontSize={10} fill="var(--apagado)" className="num">
            {m}
          </text>
        </g>
      ))}

      {horas.map((h, i) => {
        const x = izq + i * paso + (paso - barra) / 2;
        const total = h.piezasJ1 + h.piezasJ2;
        const centro = x + barra / 2;
        return (
          <g key={h.hora}>
            {h.valido ? (
              <>
                <rect x={x} y={y(h.piezasJ1)} width={barra} height={y(0) - y(h.piezasJ1)} fill="var(--barra-j1)" />
                <rect x={x} y={y(total)} width={barra} height={y(h.piezasJ1) - y(total)} fill="var(--barra-j2)" />
                {total > 0 ? (
                  <text x={centro} y={y(total) - 4} textAnchor="middle" fontSize={10} fill="var(--tenue)" className="num">
                    {total}
                  </text>
                ) : null}
              </>
            ) : (
              <line x1={x} x2={x + barra} y1={y(0) - 1} y2={y(0) - 1} stroke="var(--apagado)" strokeDasharray="2 2" />
            )}
            {h.enCurso ? (
              <rect
                x={x - 3}
                y={arriba - 2}
                width={barra + 6}
                height={util + 3}
                fill="none"
                stroke="var(--tinta)"
                strokeWidth={1}
                strokeDasharray="3 2"
              />
            ) : null}
            <text
              x={centro}
              y={alto - 6}
              textAnchor="middle"
              fontSize={10}
              fill={h.enCurso ? "var(--tinta)" : "var(--apagado)"}
              fontWeight={h.enCurso ? 700 : 400}
              className="num"
            >
              {String(h.hora).padStart(2, "0")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function Produccion({ vista }: { vista: Vista }) {
  const { hoy, horas } = vista;
  const reciente = [...horas].reverse();

  return (
    <section className="panel flex flex-col">
      <div className="flex items-baseline justify-between border-b border-linea px-4 py-2">
        <h2 className="rotulo">Producción · hoy</h2>
        <span className="text-[0.75rem] text-tenue">Fuente: tabla horaria del PLC</span>
      </div>

      <div className="grid grid-cols-2 border-b border-linea sm:grid-cols-4">
        <Indicador rotulo="Piezas" valor={String(hoy.piezas)} detalle={`J1 ${hoy.piezasJ1} · J2 ${hoy.piezasJ2}`} />
        <Indicador
          rotulo="Produciendo"
          valor={horasMin(hoy.minProd)}
          detalle={hoy.pctProd === null ? undefined : `${hoy.pctProd} % del día`}
        />
        <Indicador rotulo="En falla" valor={horasMin(hoy.minFalla)} />
        <Indicador
          rotulo="Piezas / hora prod."
          valor={hoy.minProd > 0 ? (hoy.piezas / (hoy.minProd / 60)).toFixed(1) : "—"}
        />
      </div>

      <div className="px-3 pt-3">
        <div className="mb-1 flex items-center justify-between px-1">
          <span className="rotulo">Piezas por hora · últimas 24 h</span>
          <span className="flex items-center gap-3 text-[0.75rem] text-tenue">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5" style={{ background: "var(--barra-j1)" }} /> JIG1
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5" style={{ background: "var(--barra-j2)" }} /> JIG2
            </span>
            <span>- - - sin dato</span>
          </span>
        </div>
        <GraficoHoras horas={horas} />
      </div>

      <details className="border-t border-linea px-4 py-2">
        <summary className="rotulo cursor-pointer select-none">Detalle por hora</summary>
        <div className="mt-2">
          <table className="tabla num">
            <thead>
              <tr>
                <th>Hora</th>
                <th>JIG1</th>
                <th>JIG2</th>
                <th>Total</th>
                <th>Prod.<span className="hidden sm:inline"> (min)</span></th>
                <th>Falla<span className="hidden sm:inline"> (min)</span></th>
              </tr>
            </thead>
            <tbody>
              {reciente.map((h) => (
                <tr key={h.hora} data-actual={h.enCurso} data-valido={h.valido}>
                  <td className="whitespace-nowrap">
                    {String(h.hora).padStart(2, "0")}:00{" "}
                    {h.dia === "ayer" ? <span className="hidden text-apagado sm:inline">ayer</span> : null}
                  </td>
                  <td>{h.valido ? h.piezasJ1 : "—"}</td>
                  <td>{h.valido ? h.piezasJ2 : "—"}</td>
                  <td>{h.valido ? h.piezasJ1 + h.piezasJ2 : "—"}</td>
                  <td>{h.valido ? Math.round(h.segProd / 60) : "—"}</td>
                  <td>{h.valido ? Math.round(h.segFalla / 60) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
