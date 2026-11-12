"use client";

import { useState } from "react";
import { refFalla, type FallaAcumulada, type Vista } from "@/lib/dominio";
import type { DefFalla } from "@/lib/fallas";
import { horasMin, miles } from "./formato";

/** "(M3841 · F073)": marca para buscar en GX Works2 y codigo de los contadores del PLC. */
function Ref({ def }: { def: DefFalla }) {
  return (
    <span className="num ml-1.5 whitespace-nowrap text-[0.75rem] font-normal text-tenue">({refFalla(def)})</span>
  );
}

/** 45 -> "45 s", 3010 -> "50 min", 5400 -> "1 h 30 min". */
function duracion(seg: number): string {
  if (seg < 60) return `${seg} s`;
  return horasMin(Math.round(seg / 60));
}

type Orden = "veces" | "tiempo";

function Barras({ filas, orden }: { filas: FallaAcumulada[]; orden: Orden }) {
  const medida = (f: FallaAcumulada) => (orden === "veces" ? f.veces : f.seg);
  const top = [...filas].sort((a, b) => medida(b) - medida(a)).slice(0, 10).filter((f) => medida(f) > 0);
  const maximo = Math.max(1, ...top.map(medida));

  if (top.length === 0) return <p className="py-3 text-tenue">Sin fallas registradas.</p>;

  return (
    <ol className="flex flex-col gap-1.5">
      {top.map((f) => (
        <li key={f.def.codigo} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5">
          <span className="truncate">
            <span className="rotulo mr-1.5 inline-block w-10">{f.def.grupo}</span>
            <span className={f.activa ? "texto-tono font-semibold" : ""} data-tono="falla">
              {f.def.texto}
            </span>
            <Ref def={f.def} />
          </span>
          <span className="num text-right text-[0.8rem]">
            {orden === "veces" ? miles(f.veces) : duracion(f.seg)}
          </span>
          <span className="col-span-2 block h-2 bg-[var(--panel-alt)]">
            <span
              className="block h-full"
              style={{
                width: `${(medida(f) / maximo) * 100}%`,
                background: f.activa ? "var(--falla)" : "var(--barra-j1)",
              }}
            />
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Fallas de la celda: activas, ultimas 20 del registro del PLC y acumulado por tipo. */
export function Fallas({ vista }: { vista: Vista }) {
  const { fallas } = vista;
  const [orden, setOrden] = useState<Orden>("veces");

  return (
    <section className="panel">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-linea px-4 py-2">
        <h2 className="rotulo">Fallas</h2>
        <span
          className={fallas.activas.length ? "texto-tono text-[0.75rem] font-semibold" : "text-[0.75rem] text-tenue"}
          data-tono="falla"
        >
          {fallas.activas.length
            ? `${fallas.activas.length} activa${fallas.activas.length > 1 ? "s" : ""}`
            : "Sin fallas activas"}
        </span>
      </div>

      {!fallas.hayTags ? (
        <p className="px-4 py-4 text-tenue">
          Todavía no llegan datos de fallas: falta cargar en el PLC la sección de fallas del bloque SCADA, o sus tags
          (Falla.*) en el adquisidor.
        </p>
      ) : (
        <>
          {fallas.activas.length ? (
            <div className="estado border-b border-linea px-4 py-2" data-tono="falla">
              <ul className="flex flex-wrap gap-x-6 gap-y-1">
                {fallas.activas.map((f) => (
                  <li key={f.codigo} className="flex items-center gap-2 font-semibold">
                    <span className="lampara" data-on="true" data-tono="falla" aria-hidden />
                    <span className="rotulo">{f.grupo}</span>
                    {f.texto}
                    <Ref def={f} />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="grid gap-x-6 lg:grid-cols-2 [&>*]:min-w-0">
            <div className="px-4 py-2">
              <div className="rotulo mb-1">Últimas fallas</div>
              {fallas.ultimas.length === 0 ? (
                <p className="py-3 text-tenue">El registro del PLC todavía está vacío.</p>
              ) : (
                <table className="tabla">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th className="!text-left">Equipo</th>
                      <th className="!text-left">Falla</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fallas.ultimas.map((u) => (
                      <tr key={u.orden}>
                        <td className="num whitespace-nowrap">{u.cuando}</td>
                        <td className="!text-left">{u.def?.grupo ?? "—"}</td>
                        <td className="!text-left">
                          {u.def ? (
                            <>
                              {u.def.texto}
                              <Ref def={u.def} />
                            </>
                          ) : (
                            `Código ${u.codigo} (no está en el catálogo)`
                          )}
                        </td>
                        <td>
                          {u.activa ? (
                            <span className="texto-tono font-semibold" data-tono="falla">
                              Activa
                            </span>
                          ) : (
                            <span className="text-tenue">Normal</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="border-t border-linea px-4 py-2 lg:border-t-0 lg:border-l">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="rotulo">Más frecuentes (acumulado)</span>
                <div className="flex" role="group" aria-label="Ordenar por">
                  {(["veces", "tiempo"] as const).map((o) => (
                    <button
                      key={o}
                      type="button"
                      className="boton first:rounded-r-none last:-ml-px last:rounded-l-none"
                      aria-pressed={orden === o}
                      data-activo={orden === o}
                      onClick={() => setOrden(o)}
                    >
                      {o === "veces" ? "Veces" : "Tiempo"}
                    </button>
                  ))}
                </div>
              </div>
              <Barras filas={fallas.acumulado} orden={orden} />
            </div>
          </div>

          {fallas.acumulado.length ? (
            <details className="border-t border-linea px-4 py-2">
              <summary className="rotulo cursor-pointer select-none">
                Todas las fallas registradas ({fallas.acumulado.length})
              </summary>
              <table className="tabla num mt-2">
                <thead>
                  <tr>
                    <th>Falla</th>
                    <th className="!text-left">Equipo</th>
                    <th>Veces</th>
                    <th>Tiempo activa</th>
                  </tr>
                </thead>
                <tbody>
                  {fallas.acumulado.map((f) => (
                    <tr key={f.def.codigo}>
                      <td className="font-sans">
                        {f.def.texto}
                        <Ref def={f.def} />
                      </td>
                      <td className="!text-left font-sans">{f.def.grupo}</td>
                      <td>{miles(f.veces)}</td>
                      <td>{duracion(f.seg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
