import Link from "next/link";
import type { Celda } from "@/lib/celdas";

/** Una solapa por celda del catalogo (src/lib/celdas.ts). */
export function Solapas({ celdas, actual }: { celdas: Celda[]; actual: string }) {
  return (
    <nav className="flex flex-wrap" aria-label="Celdas">
      {celdas.map((c) => (
        <Link
          key={c.id}
          href={`/celda/${c.id}`}
          className="solapa"
          aria-current={c.id === actual ? "page" : undefined}
        >
          Celda {c.nombre}
          {c.enDesarrollo ? <span className="rotulo ml-2 !text-[0.6rem]">próx.</span> : null}
        </Link>
      ))}
    </nav>
  );
}
