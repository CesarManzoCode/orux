import { createRoot } from "react-dom/client";
import "./index.css";
import { connect } from "./store";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import { instalar as instalarErrorReporter } from "./error-reporter";

// Anti-debugging-a-ciegas: instalamos el reporter ANTES de connect() para
// no perder errores tempranos (un import roto, una API del navegador que
// el cliente esperaba, etc.). En dev es no-op.
instalarErrorReporter();

connect();

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
