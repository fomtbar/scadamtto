import { NextResponse } from "next/server";
import { destino, probarConexion } from "@/lib/db";
import { modoDemo } from "@/lib/lectura";

/**
 * La usan el healthcheck del compose y la prueba de humo de deploy.sh.
 * Comprueba que el proceso esta vivo y que llega a la base con una consulta
 * parametrizada (ver probarConexion en src/lib/db.ts).
 */
export const dynamic = "force-dynamic";

export async function GET() {
  if (modoDemo()) return NextResponse.json({ ok: true, base: "demo" });
  try {
    const tags = await probarConexion();
    return NextResponse.json({ ok: true, base: "arriba", tags, destino: destino() });
  } catch (error) {
    console.error("[health] la base no responde:", (error as Error).message);
    // 503 y no 500: el proceso esta sano, quien no responde es la base.
    return NextResponse.json({ ok: false, base: "caida", destino: destino() }, { status: 503 });
  }
}
