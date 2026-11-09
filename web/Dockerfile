# ==========================================================
#  scadaMtto web - Next.js standalone + mssql (tedious)
#
#  Mismo esquema que examenesWeb: Debian slim y no Alpine (musl da
#  sorpresas en dependencias transitivas) y nada de ODBC: 'mssql'
#  habla TDS desde JavaScript.
# ==========================================================

# -- Etapa 1: dependencias --------------------------------
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# En la red de la compania npm se corta a mitad de descarga (ECONNRESET):
# reintentos con espera larga y cache de BuildKit entre intentos.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund \
      --fetch-retries=5 \
      --fetch-retry-mintimeout=20000 \
      --fetch-retry-maxtimeout=180000 \
      --fetch-timeout=600000

# -- Etapa 2: compilacion ---------------------------------
FROM node:22-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# La compilacion no toca la base: las paginas y rutas son force-dynamic.
RUN npm run build

# -- Etapa 3: desarrollo ----------------------------------
# La usa infraestructura/docker-compose.override.yml (codigo por bind-mount).
FROM node:22-bookworm-slim AS dev
WORKDIR /app
ENV NODE_ENV=development
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3108
ENV HOSTNAME=0.0.0.0
ENV TZ=America/Argentina/Buenos_Aires
COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
EXPOSE 3108
CMD ["npm", "run", "dev"]

# -- Etapa 4: ejecucion -----------------------------------
FROM node:22-bookworm-slim AS runner
WORKDIR /app

# curl lo necesita el healthcheck del compose. Es lo unico que se instala.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3108
ENV HOSTNAME=0.0.0.0
ENV TZ=America/Argentina/Buenos_Aires

RUN groupadd --system --gid 1001 nodejs \
 && useradd --system --uid 1001 --gid nodejs nextjs

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3108
CMD ["node", "server.js"]
