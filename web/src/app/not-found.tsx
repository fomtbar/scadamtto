import Link from "next/link";
import { CELDAS } from "@/lib/celdas";

export default function NoEncontrada() {
  return (
    <main className="mx-auto max-w-md px-4 py-20 text-center">
      <p className="rotulo">404</p>
      <p className="mt-1 text-lg font-semibold">No existe esa celda.</p>
      <Link href={`/celda/${CELDAS[0].id}`} className="boton mt-4">
        Ir a la celda {CELDAS[0].nombre}
      </Link>
    </main>
  );
}
