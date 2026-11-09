"use client";

import { useEffect, useState } from "react";
import type { Celda } from "@/lib/celdas";
import type { Vista } from "@/lib/dominio";
import { FranjaEstado } from "./estado";
import { Produccion } from "./produccion";
import { Mantenimiento } from "./mantenimiento";
import { antiguedad } from "./formato";

const REFRESCO_MS = 5_000;

type Respuesta = Vista & { demo: boolean };

/**
 * Pide /api/celda/[id] cada 5 s. Si una consulta falla se queda con lo
 * ultimo que tuvo y lo dice, en vez de dejar la pantalla en blanco.
 */
export function Tablero({ celda }: { celda: Celda }) {
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ultima, setUltima] = useState<number | null>(null);
  const [ahora, setAhora] = useState(() => Date.now());

  useEffect(() => {
    let vivo = true;
    let control: AbortController | null = null;

    async function pedir() {
      control?.abort();
      control = new AbortController();
      try {
        const r = await fetch(`/api/celda/${celda.id}`, { cache: "no-store", signal: control.signal });
        const json = await r.json();
        if (!vivo) return;
        if (!r.ok) throw new Error(json.error ?? `HTTP ${r.status}`);
        setDatos(json);
        setError(null);
        setUltima(Date.now());
      } catch (e) {
        if (!vivo || (e as Error).name === "AbortError") return;
        setError((e as Error).message || "Sin conexión con el servidor.");
      }
    }

    pedir();
    const intervalo = setInterval(pedir, REFRESCO_MS);
    const reloj = setInterval(() => setAhora(Date.now()), 1_000);
    return () => {
      vivo = false;
      control?.abort();
      clearInterval(intervalo);
      clearInterval(reloj);
    };
  }, [celda.id]);

  const segDesdeConsulta = ultima ? Math.max(0, Math.round((ahora - ultima) / 1000)) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Celda {celda.nombre}</h1>
          <span className="text-tenue">{celda.descripcion}</span>
        </div>
        <div className="rotulo num">
          {datos?.demo ? <span className="text-aviso">Datos de ejemplo · </span> : null}
          {segDesdeConsulta === null ? "Conectando…" : `Actualizado hace ${segDesdeConsulta} s`}
          {datos?.reloj.servidor ? ` · ${datos.reloj.servidor}` : ""}
        </div>
      </div>

      {error ? (
        <div className="aviso-franja px-3 py-2">
          No se pudo actualizar: {error}
          {datos ? " Se muestra lo último recibido." : ""}
        </div>
      ) : null}

      {datos && datos.desactualizado ? (
        <div className="aviso-franja px-3 py-2">
          {datos.hayDatos
            ? `Dato desactualizado: el adquisidor no lee esta celda hace ${antiguedad(datos.segDesdeLectura)}. Los valores pueden no ser los actuales.`
            : "Todavía no hay datos de esta celda en la base. ¿Están cargadas sus tags en el adquisidor?"}
        </div>
      ) : null}

      {datos && !datos.desactualizado && !datos.plcVivo ? (
        <div className="aviso-franja px-3 py-2">
          El contador de vida del PLC no cambia: el programa SCADA del PLC no está corriendo o el PLC está en STOP.
        </div>
      ) : null}

      {datos ? (
        <div className={`flex flex-col gap-3 ${datos.desactualizado ? "viejo" : ""}`}>
          <FranjaEstado vista={datos} />
          <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_380px] [&>*]:min-w-0">
            <Produccion vista={datos} />
            <Mantenimiento vista={datos} />
          </div>
        </div>
      ) : !error ? (
        <div className="panel px-4 py-10 text-center text-tenue">Leyendo datos de la celda…</div>
      ) : null}
    </div>
  );
}
