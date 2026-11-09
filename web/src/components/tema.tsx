"use client";

import { useSyncExternalStore } from "react";

/** El tema vive en <html data-theme>; layout.tsx lo fija antes de pintar. */
function leer(): "light" | "dark" {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

const avisos = new Set<() => void>();
function suscribir(aviso: () => void) {
  avisos.add(aviso);
  return () => avisos.delete(aviso);
}

export function BotonTema() {
  const tema = useSyncExternalStore(suscribir, leer, () => "light" as const);

  function cambiar() {
    const nuevo = tema === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nuevo;
    try {
      localStorage.setItem("tema", nuevo === "dark" ? "oscuro" : "claro");
    } catch {
      // Sin almacenamiento el cambio dura hasta recargar; no es grave.
    }
    avisos.forEach((a) => a());
  }

  return (
    <button type="button" className="boton" onClick={cambiar} title="Cambiar tema">
      <span
        aria-hidden
        className="inline-block h-2.5 w-2.5 border border-current"
        style={{ background: tema === "dark" ? "transparent" : "currentColor" }}
      />
      {tema === "dark" ? "Oscuro" : "Claro"}
    </button>
  );
}
