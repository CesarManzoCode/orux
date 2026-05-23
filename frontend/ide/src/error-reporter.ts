// Reportería de errores JS no-capturados al backend (capa anti-debugging-
// a-ciegas). Sin esto, la primera semana de usuarios reales tendría bugs
// invisibles para nosotros — el usuario ve la pantalla rota y se va sin
// decirnos nada. Con esto: el operador ve `client_error: ...` en los logs
// del container `api`.
//
// Diseño:
//  - Listeners de `error` (errores síncronos / runtime) y `unhandledrejection`
//    (promesas rechazadas que nadie capturó).
//  - Debounce: si la app entra en un loop que tira 50 errores/s, mandamos
//    UN batch al segundo, no 50 requests.
//  - Buffer con tope DURO (descarta nuevos si está lleno) para que un loop
//    no se coma la memoria del cliente ni inunde la red.
//  - `keepalive: true` en el fetch: sobrevive a "el usuario está cerrando
//    la pestaña" — justo el momento en el que se pierden los errores
//    interesantes (la página explotó y el usuario huye).
//  - Fire-and-forget: si el endpoint /api/v1/errors falla, NO rompemos
//    la app reportando que falló el reporte (sería paradójico).
//  - Solo en producción. En dev los errores los ves en la consola del
//    navegador; saturar el container local con tu propio Ctrl+S es ruido.

const MAX_BUFFER = 20;       // tope duro de errores en buffer (overflow → drop)
const FLUSH_BATCH = 5;       // cuántos mandamos por flush
const FLUSH_MS = 1000;       // debounce: 1s entre batches

interface ErrorReport {
  kind: "error" | "unhandledrejection";
  message: string;
  stack: string;
  url: string;
}

let buffer: ErrorReport[] = [];
let flushTimer: number | null = null;

// Mismo criterio de dev que `store.ts:wsUrl()`: si el cliente corre en
// `:5173` o desde `file:`, es dev. En dev no instalamos los listeners
// (early return) — los errores se ven en la consola del navegador.
function esDev(): boolean {
  return (
    location.protocol === "file:" ||
    location.port === "5173" ||
    location.port === "5500"
  );
}

function endpoint(): string {
  // Mismo origen: Caddy proxya /api/* al container `api`. En dev nunca
  // llegamos acá por el early return de `instalar()`.
  return location.origin + "/api/v1/errors";
}

function enviar(rep: ErrorReport): void {
  try {
    fetch(endpoint(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        kind: rep.kind,
        message: rep.message,
        stack: rep.stack,
        url: rep.url,
        userAgent: navigator.userAgent,
      }),
      // Permite que el request sobreviva a un unload del documento (el
      // navegador lo termina en background). Es exactamente el caso útil:
      // la página crashea y el usuario cierra la pestaña.
      keepalive: true,
    }).catch(() => {
      // Fire-and-forget: si el endpoint no responde no nos importa.
      // Reportar el fallo de reporte sería un loop tonto.
    });
  } catch {
    // Idem: en navegadores muy viejos / extensiones que bloquean fetch,
    // tragamos el error en silencio. Mejor perder un report que romper.
  }
}

function flush(): void {
  flushTimer = null;
  const batch = buffer.splice(0, FLUSH_BATCH);
  for (const rep of batch) enviar(rep);
  // Si quedaron eventos en el buffer (overflow durante el flush),
  // programamos otro batch.
  if (buffer.length > 0) programar();
}

function programar(): void {
  if (flushTimer !== null) return;
  flushTimer = window.setTimeout(flush, FLUSH_MS);
}

function agregar(rep: ErrorReport): void {
  if (buffer.length >= MAX_BUFFER) return;  // overflow: dropear silente
  buffer.push(rep);
  programar();
}

// El campo `error` del ErrorEvent puede ser cualquier cosa (incluyendo
// undefined si el navegador no preservó el objeto Error). Normalizamos
// a strings sin asumir forma.
function describir(err: unknown): { message: string; stack: string } {
  if (err instanceof Error) {
    return { message: err.message || "?", stack: err.stack || "" };
  }
  return { message: String(err ?? "?"), stack: "" };
}

export function instalar(): void {
  if (esDev()) return;

  window.addEventListener("error", (e) => {
    const fuente = e.error ?? e.message;
    const { message, stack } = describir(fuente);
    agregar({
      kind: "error",
      message: message || String(e.message || "?"),
      stack,
      url: location.href,
    });
  });

  window.addEventListener("unhandledrejection", (e) => {
    const { message, stack } = describir(e.reason);
    agregar({
      kind: "unhandledrejection",
      message,
      stack,
      url: location.href,
    });
  });
}
