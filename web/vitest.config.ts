import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  test: {
    // Ninguno de estos tests toca la base ni el navegador: son reglas puras.
    // Lo que necesita base va en scripts/verificar-lectura.mts, y lo que
    // necesita navegador en e2e/.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
