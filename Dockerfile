# Imagen del servidor laidea. Solo el server Python: el cliente estático
# (web/) lo sirve Caddy (ver docker-compose.yml). No agrega nada al producto,
# solo lo empaqueta para correr en un VPS.
FROM python:3.12-slim AS base

# `git` es REQUISITO de runtime: la capa 8 invoca el binario `git` para
# reportar el estado del workspace (que es un repo git). Sin git, GitRepo
# degrada a "no disponible" — lo instalamos para que funcione de verdad.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Usuario no-root: no se corre el server como root en un servidor expuesto.
RUN useradd --create-home --uid 10001 laidea

WORKDIR /app
# Instalamos primero solo los metadatos para cachear la capa de dependencias.
COPY pyproject.toml README.md ./
COPY laidea ./laidea
RUN pip install --no-cache-dir .

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

# El server no expone HTTP; un connect TCP al puerto basta para saber que
# está vivo y aceptando conexiones.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import socket;socket.create_connection(('127.0.0.1',8765),2).close()"

CMD ["python", "-m", "laidea.server"]
