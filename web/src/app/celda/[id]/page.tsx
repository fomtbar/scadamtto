import { notFound } from "next/navigation";
import { buscarCelda, CELDAS } from "@/lib/celdas";
import { Solapas } from "@/components/solapas";
import { Tablero } from "@/components/tablero";
import { BotonTema } from "@/components/tema";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const celda = buscarCelda((await params).id);
  return { title: celda ? `${celda.nombre} · scadaMtto` : "scadaMtto" };
}

export default async function PaginaCelda({ params }: { params: Promise<{ id: string }> }) {
  const celda = buscarCelda((await params).id);
  if (!celda) notFound();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="barra">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-end gap-x-6 px-4">
          <div className="flex h-[2.6rem] items-center gap-2 pr-2">
            <span className="inline-block h-3 w-3 bg-tinta" aria-hidden />
            <span className="text-[0.8rem] font-bold tracking-[0.12em] uppercase">scadaMtto</span>
          </div>
          <Solapas celdas={CELDAS} actual={celda.id} />
          <div className="ml-auto flex h-[2.6rem] items-center">
            <BotonTema />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-4">
        <Tablero celda={celda} />
      </main>
    </div>
  );
}
