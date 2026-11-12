import { NextResponse } from "next/server";
import { buscarCelda } from "@/lib/celdas";
import { construirVista } from "@/lib/dominio";
import { leerCelda, modoDemo } from "@/lib/lectura";

export const dynamic = "force-dynamic";

/** Lo que pide el tablero cada 5 s. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const celda = buscarCelda(id);
  if (!celda) return NextResponse.json({ error: `No existe la celda ${id}` }, { status: 404 });
  if (celda.enDesarrollo) return NextResponse.json({ error: `La celda ${celda.nombre} está en desarrollo` }, { status: 404 });

  try {
    const { tags, ahora } = await leerCelda(celda);
    return NextResponse.json(
      { ...construirVista(tags, ahora), demo: modoDemo() },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error(`[celda ${id}] no se pudo leer:`, (error as Error).message);
    return NextResponse.json({ error: "No se pudo leer la base de datos." }, { status: 503 });
  }
}
