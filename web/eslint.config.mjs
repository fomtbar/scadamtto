// eslint-config-next 16 ya exporta configuracion plana: no hace falta
// FlatCompat (que ademas rompe con este paquete al serializar sus plugins).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const configuracion = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...nextCoreWebVitals,
  ...nextTypescript,
];

export default configuracion;
