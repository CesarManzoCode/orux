# Imagen del servidor laidea. Solo el server Python: el cliente estático
# (web/) lo sirve Caddy (ver docker-compose.yml). No agrega nada al producto,
# solo lo empaqueta para correr en un VPS.
FROM python:3.12-slim AS base

# `git` es REQUISITO de runtime: la capa 8 invoca el binario `git` para
# reportar el estado del workspace (que es un repo git). Sin git, GitRepo
# degrada a "no disponible" — lo instalamos para que funcione de verdad.
#
# `libatomic1`: el Node que pyright-python baja (capa 17) es un binario
# prearmado que enlaza `libatomic.so.1`, y python:3.12-slim (Debian slim)
# NO la trae -> el log lo gritó: "node: error while loading shared
# libraries: libatomic.so.1". Sin ella pyright no arranca y el análisis
# degrada mudo a capa 16. Una sola lib, sin recomendados.
#
# `nodejs`/`npm` (capa 18): a diferencia de pyright (su paquete pip trae su
# propio Node), `typescript-language-server` —el Tier 0 de JS/TS— es npm y
# necesita Node instalado. python:3.12-slim no lo trae. Es el precio honesto
# de darle resolución real a los devs de TS (el gatillo original del
# multi-lenguaje): la imagen crece, pero la feature es real.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates libatomic1 nodejs npm curl \
 && rm -rf /var/lib/apt/lists/*

# Usuario no-root: no se corre el server como root en un servidor expuesto.
RUN useradd --create-home --uid 10001 laidea

WORKDIR /app
# Instalamos primero solo los metadatos para cachear la capa de dependencias.
# El backend vive en /backend (reorg de repo): contexto de build = raíz,
# por eso las rutas llevan el prefijo. README.md sigue en la raíz (doc del
# proyecto entero, no del paquete).
COPY backend/pyproject.toml README.md ./
COPY backend/laidea ./laidea
RUN pip install --no-cache-dir .

# Capa 17: el paquete pip `pyright` descarga un runtime Node la PRIMERA vez
# que se invoca. Si eso pasara en runtime, el 1er análisis de cada deploy
# necesitaría red y un cache escribible por el usuario no-root. Lo
# PRE-CALENTAMOS acá (build, como root, con red): Node queda horneado en la
# imagen y el server arranca offline y rápido. CLAVE: pyright-python
# ESCRIBE en su cache en cada arranque (lock/chequeos de versión), así que
# el dir debe ser PROPIEDAD del usuario runtime no-root, no solo legible
# (un `chmod a+rX` lo dejaba read-only y el langserver no levantaba en el
# VPS -> degradaba a capa 16 sin avisar). Si pyright no estuviera, el
# análisis degrada a tree-sitter/ast (no fatal) — por eso `|| true`.
ENV PYRIGHT_PYTHON_CACHE_DIR=/opt/pyright
RUN mkdir -p /opt/pyright \
 && (pyright --version || true) \
 && chown -R laidea:laidea /opt/pyright

# Capa 18: typescript-language-server + su tsserver (paquete `typescript`),
# global. Versiones fijas (reproducible). A diferencia de pyright-python NO
# necesita un cache escribible en runtime (es un global npm normal, los
# binarios quedan en /usr/local/bin, world-exec). Si fallara, el análisis
# de JS/TS degrada a tree-sitter/regex (no fatal).
RUN npm install -g --no-fund --no-audit \
      typescript@5.4.5 typescript-language-server@4.3.3 \
 && npm cache clean --force

# Capa 20: Rust = rust-analyzer (binario oficial prearmado, glibc; slim es
# bookworm = glibc, ok). NO necesita el toolchain Rust para documentSymbol/
# references sobre el workspace. Liviano: un binario.
RUN curl -fsSL -o /tmp/ra.gz \
      https://github.com/rust-lang/rust-analyzer/releases/download/2024-05-13/rust-analyzer-x86_64-unknown-linux-gnu.gz \
 && gunzip -c /tmp/ra.gz > /usr/local/bin/rust-analyzer \
 && chmod a+rx /usr/local/bin/rust-analyzer \
 && rm /tmp/ra.gz

# Capa 20: Go = gopls. Honesto: a diferencia de rust-analyzer, gopls se
# instala con `go install` y ADEMÁS necesita el toolchain Go en runtime
# (ejecuta `go` para cargar paquetes). Por eso entra el SDK de Go entero
# (es el costo real de Go, comparable en peso a una JVM). GOCACHE en /tmp
# (escribible por el user no-root en runtime; misma lección que el cache de
# pyright). PATH y dirs world-rx para que el usuario `laidea` lo use.
ENV GO_VERSION=1.22.5 \
    GOPATH=/opt/go \
    GOCACHE=/tmp/go-build \
    PATH=/usr/local/go/bin:/opt/go/bin:$PATH
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
      | tar -C /usr/local -xz \
 && GOBIN=/opt/go/bin go install golang.org/x/tools/gopls@v0.15.3 \
 && chmod -R a+rX /usr/local/go /opt/go \
 && rm -rf /root/.cache/go-build

# Estado persistente (workspace=repo git, users, ownership, secret). Es un
# VOLUME: vive fuera del contenedor para sobrevivir recrearlo. Propiedad del
# usuario no-root para que pueda escribir.
RUN mkdir -p /data && chown -R laidea:laidea /data
VOLUME /data
ENV LAIDEA_DATA=/data \
    LAIDEA_HOST=0.0.0.0 \
    LAIDEA_PORT=8765 \
    PYTHONUNBUFFERED=1

USER laidea
EXPOSE 8765

# Healthcheck: abre un WebSocket REAL y lo cierra. Un connect TCP crudo
# bastaba para saber que el puerto está vivo, pero el server websockets
# intentaba parsear una request HTTP inexistente y escupía un traceback
# ruidoso cada 30s. Un handshake WS válido verifica lo mismo y no ensucia
# los logs (el server lo absorbe en silencio: conexión sin auth -> se cierra).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import asyncio, websockets\nasync def m():\n    async with websockets.connect('ws://127.0.0.1:8765'):\n        pass\nasyncio.run(m())"]

CMD ["python", "-m", "laidea.server"]
