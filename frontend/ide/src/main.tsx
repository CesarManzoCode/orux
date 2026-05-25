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

// Perspectiva del demo: ?p=tu (default — el dueño que recibe propuestas) o
// ?p=ana (la peer que edita y propone). El hero de la landing embebe el
// iframe TU como principal (grande, expandido al viewport) y el iframe ANA
// como PIP — el "self-view" del otro user, prueba visual de que son dos
// clientes corriendo en paralelo y sincronizados.
function leerPersona(): "tu" | "ana" {
  try {
    const p = new URLSearchParams(location.search).get("p");
    return p === "ana" ? "ana" : "tu";
  } catch {
    return "tu";
  }
}

// ?pip=1 indica que el iframe está montado como PIP en el hero (no como
// iframe principal). El DemoLoop usa este flag para suprimir el Stepper y
// el cursor del visitante — a la escala del PIP (~0.25) ese chrome se
// vuelve ruido. Sólo el iframe principal lleva el stepper que cuenta la
// narrativa; el PIP demuestra "es otro IDE real corriendo".
function esPip(): boolean {
  try {
    return new URLSearchParams(location.search).get("pip") === "1";
  } catch {
    return false;
  }
}

if (esDemo()) {
  aplicarLangDemo();
  const persona = leerPersona();
  const pip = esPip();
  if (persona === "ana") {
    // Vista de Ana: ella es el "yo" del IDE. El color azul (#62a8f0) es el
    // mismo que TUT.ana en mock.ts — coherencia visual cross-iframe (en el
    // iframe del dueño, Ana aparece como peer con ese azul; acá, Ana se ve
    // a sí misma con el mismo azul). rol=member porque Ana NO administra
    // el workspace en este escenario.
    __setForTutorial({
      demoMode: true,
      demoPip: pip,
      authed: true,
      fase: "team",
      yo: { client_id: "tutorial:ana", name: "Ana", color: "#62a8f0" },
      equipo: { id: "demo", nombre: "demo", rol: "member" },
      esAdmin: false,
    });
  } else {
    __setForTutorial({
      demoMode: true,
      demoPip: pip,
      authed: true,
      fase: "team",
      yo: { client_id: "demo:tu", name: "tú", color: "#43b98a" },
      equipo: { id: "demo", nombre: "demo", rol: "admin" },
      esAdmin: false,
    });
  }
} else {
  connect();
}

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
