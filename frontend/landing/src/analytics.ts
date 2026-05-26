// Analytics minimalista propio para la landing. Sin Plausible/Umami/GA: un
// endpoint propio (`/api/v1/track`) que vimos pageviews en los logs del
// container `api` con `docker compose logs api | grep client_track`.
//
// Privacy-first por diseño:
//   - cero cookies, cero localStorage, cero IDs persistentes
//   - la IP NO se loguea con el evento (solo se usa para rate limit en el
//     server y queda en su bucket en memoria)
//   - el server corta UA y referrer a tamaños sanos antes de loguear
//   - sin trackeo cross-page (no hay router; la landing es un solo HTML)
//
// Por qué no usar un servicio externo:
//   - no querés cargar JS de terceros en la primera impresión (CSP, perf,
//     bloqueo de adblockers)
//   - los datos básicos (cuántos visitan, de dónde, qué browser) los tenés
//     en los logs del container, gratis
//   - si más adelante hace falta UI (gráficas, retention), se cambia por
//     un servicio sin tocar nada de privacidad: el frontend ya no manda
//     nada sensible

function esDev(): boolean {
  // Mismo criterio que el error-reporter del IDE: dev = Vite local o file://
  return (
    location.protocol === "file:" ||
    location.port === "5173" ||
    location.port === "5500"
  );
}

// AUDITORIA-SEGURIDAD 2026-05-25 B-FE-09: respetar DNT y Global Privacy
// Control. Si el usuario expresa esa señal en su navegador, no medimos —
// ni siquiera un pageview agregado. Es coherente con el claim "sin
// trackers" de la landing.
function respetaPrivacy(): boolean {
  try {
    const nav = navigator as any;
    const win = window as any;
    if (nav?.doNotTrack === "1" || nav?.msDoNotTrack === "1") return false;
    if (win?.doNotTrack === "1") return false;
    if (nav?.globalPrivacyControl === true) return false;
    return true;
  } catch {
    return true;
  }
}

function endpoint(): string {
  // Mismo origen: Caddy proxya /api/* al container `api`. En dev nunca
  // llegamos acá por el early return de `instalar()`.
  return location.origin + "/api/v1/track";
}

function track(event: string): void {
  // AUDITORIA-SEGURIDAD 2026-05-25 B-FE-09: gate de DNT/GPC.
  if (!respetaPrivacy()) return;
  try {
    fetch(endpoint(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        event,
        // AUDITORIA-SEGURIDAD 2026-05-25 B-FE-09: solo el `pathname` —
        // no reenviamos `location.search` para no pasar parámetros de
        // campañas (UTMs) ni códigos accidentalmente sensibles a los
        // logs.
        url: location.pathname,
        // referrer puede ser vacío si el usuario llegó tipeando la URL,
        // desde un bookmark, o desde HTTPS→HTTP (downgrade); eso es OK
        // y se loguea como "" en el server.
        referrer: document.referrer || "",
      }),
      // Sobrevive a "el usuario está cerrando la pestaña": el browser
      // termina el request en background. Para pageview esto es relevante
      // solo si la página se cierra inmediatamente; igual no hace daño.
      keepalive: true,
    }).catch(() => {
      // Fire-and-forget: si el endpoint no responde no hacemos nada.
      // Mejor perder un evento que romper la página por reporting.
    });
  } catch {
    // Idem (extensiones que bloquean fetch, navegadores muy viejos).
  }
}

export function instalar(): void {
  if (esDev()) return;

  // Pageview al cargar. Esperamos `load` (no DOMContentLoaded) para que
  // el document.referrer esté firme y para no competir con el render
  // crítico del hero — el evento puede esperar 100-200ms.
  if (document.readyState === "complete") {
    track("pageview");
  } else {
    window.addEventListener("load", () => track("pageview"), { once: true });
  }
}
