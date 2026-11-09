import { redirect } from "next/navigation";
import { CELDAS } from "@/lib/celdas";

export default function Inicio() {
  redirect(`/celda/${CELDAS[0].id}`);
}
