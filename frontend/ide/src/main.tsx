import { createRoot } from "react-dom/client";
import "./index.css";
import { connect, __setForTutorial } from "./store";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import { instalar as instalarErrorReporter } from "./error-reporter";

// Anti-debugging-a-ciegas: instalamos el reporter ANTES de connect() para
// no perder errores tempranos (un import roto, una API del navegador que
// el cliente esperaba, etc.). En dev es no-op.
instalarErrorReporter();

// Modo demo cinematográfico — se activa con ?demo=1 y está pensado para
// embebirse como iframe en el hero de la landing. NO conecta al WebSocket
// (cero carga del backend), inyecta un usuario/equipo fake que satisface
// los gates de auth/lobby del App, y deja que App.tsx monte DemoLoop +
// overlay anti-interacción. El visitante solo mira: cualquier clic es
// absorbido por el overlay.
function esDemo(): boolean {
  try {
    return new URLSearchParams(location.search).get("demo") === "1";
  } catch {
    return false;
  }
}

// Si el demo recibe ?lang=es o ?lang=en, lo persistimos en el storage que
// usa el I18nProvider — así el IDE arranca con ese idioma sin un flash.
// La landing inyecta el idioma del visitante al armar el src del iframe.
function aplicarLangDemo(): void {
  try {
    const lang = new URLSearchParams(location.search).get("lang");
    if (lang === "es" || lang === "en") {
      localStorage.setItem("orux_lang", lang);
    }
  } catch {
    /* navegador con storage bloqueado: cae al default del provider */
  }
}

if (esDemo()) {
  aplicarLangDemo();
  __setForTutorial({
    demoMode: true,
    authed: true,
    fase: "team",
    yo: { client_id: "demo:tu", name: "tú", color: "#43b98a" },
    equipo: { id: "demo", nombre: "demo", rol: "admin" },
    esAdmin: false,
  });
} else {
  connect();
}

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
