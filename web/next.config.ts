import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Imagen Docker chica: el build emite .next/standalone con su propio server.js.
  output: "standalone",

  // OBLIGATORIO (aprendido en examenesWeb). Si el bundler empaqueta 'mssql',
  // toda consulta con parametros muere con "r.type.validate is not a
  // function" mientras un SELECT sin parametros sigue andando. Externo, se
  // carga con require() desde node_modules y la salida standalone lo arrastra.
  serverExternalPackages: ["mssql", "tedious"],

  // Se sirve directo en la LAN (http://<ip>:3108), sin nada delante.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
        ],
      },
    ];
  },
};

export default nextConfig;
