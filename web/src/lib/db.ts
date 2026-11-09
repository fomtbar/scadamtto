import "server-only";
import sql from "mssql";

/**
 * Pool unico contra el SQL Server de la compania (base Mantenimiento).
 *
 * Esta aplicacion SOLO LEE: un SELECT sobre la tabla que mantiene el
 * adquisidor (test.ValorActual). No escribe nada en ningun lado.
 *
 * Configuracion con variables sueltas y no con cadena de conexion: la
 * contrasena viaja como propiedad y un ';' o '{' adentro no rompen nada.
 */

function requerida(nombre: string): string {
  const valor = process.env[nombre];
  if (!valor) throw new Error(`Falta la variable de entorno ${nombre}.`);
  return valor;
}

/**
 * Esquema y tabla van en el texto de la consulta (no se pueden pasar como
 * parametro), asi que se validan como identificadores simples.
 */
function identificador(nombre: string, predeterminado: string): string {
  const valor = process.env[nombre] || predeterminado;
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(valor)) {
    throw new Error(`${nombre}=${valor} no es un nombre de tabla/esquema valido.`);
  }
  return valor;
}

export function tablaValores(): string {
  return `[${identificador("DB_ESQUEMA", "test")}].[${identificador("DB_TABLA", "ValorActual")}]`;
}

function configuracion(): sql.config {
  return {
    server: requerida("DB_HOST"),
    port: Number(process.env.DB_PUERTO ?? 1433),
    database: requerida("DB_NOMBRE"),
    user: requerida("DB_USUARIO"),
    password: requerida("DB_PASSWORD"),
    options: {
      encrypt: false,
      trustServerCertificate: (process.env.DB_TRUST_CERT ?? "true") !== "false",
    },
    pool: { max: 5, min: 0, idleTimeoutMillis: 30_000 },
    connectionTimeout: 15_000,
    requestTimeout: 15_000,
  };
}

// En globalThis para que el hot-reload de desarrollo no abra un pool por recarga.
const global_ = globalThis as unknown as { poolScada?: Promise<sql.ConnectionPool> };

export function obtenerPool(): Promise<sql.ConnectionPool> {
  if (!global_.poolScada) {
    global_.poolScada = new sql.ConnectionPool(configuracion()).connect().catch((error) => {
      // Sin esto, un fallo al arrancar dejaria la app rota hasta reiniciar.
      global_.poolScada = undefined;
      throw error;
    });
  }
  return global_.poolScada;
}

export function destino(): string {
  return `${process.env.DB_HOST}:${process.env.DB_PUERTO ?? 1433}/${process.env.DB_NOMBRE}`;
}

export type Parametros = Record<string, [tipo: sql.ISqlType | (() => sql.ISqlType), valor: unknown]>;

export async function consultar<T = Record<string, unknown>>(consulta: string, params?: Parametros): Promise<T[]> {
  const peticion = (await obtenerPool()).request();
  for (const [nombre, [tipo, valor]] of Object.entries(params ?? {})) {
    peticion.input(nombre, tipo, valor ?? null);
  }
  const resultado = await peticion.query<T>(consulta);
  return resultado.recordset ?? [];
}

/**
 * Comprobacion de /api/health. Lleva un parametro NVarChar(n) A PROPOSITO:
 * en examenesWeb un SELECT 1 sin parametros seguia en verde mientras el
 * empaquetado de mssql rompia todas las consultas reales.
 */
export async function probarConexion(): Promise<number> {
  const filas = await consultar<{ total: number }>(
    `SELECT COUNT(*) AS total FROM ${tablaValores()} WHERE NombreTag LIKE @patron`,
    { patron: [sql.VarChar(60), "%"] },
  );
  return filas[0]?.total ?? 0;
}

export { sql };
