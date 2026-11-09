import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "scadaMtto · Celdas",
  description: "Estado de las celdas de soldadura: producción y mantenimiento.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

/**
 * Fija el tema ANTES de pintar, para que no parpadee: lo guardado por el
 * boton, y si no hay nada, lo que pida el sistema operativo.
 * localStorage puede tirar error (modo privado, navegador bloqueado).
 */
const fijarTema = `(function(){try{var t=localStorage.getItem("tema");if(t!=="claro"&&t!=="oscuro"){t=matchMedia("(prefers-color-scheme: dark)").matches?"oscuro":"claro"}document.documentElement.dataset.theme=t==="oscuro"?"dark":"light"}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: fijarTema }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
