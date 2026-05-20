import { createRoot } from "react-dom/client";
import "./index.css";
import { connect } from "./store";
import { App } from "./App";
import { I18nProvider } from "./i18n";

connect();

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
