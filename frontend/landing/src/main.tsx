import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { instalar as instalarAnalytics } from "./analytics";

// Analytics propio (POST /api/v1/track). No-op en dev. Va ANTES de render
// para que el listener de `load` se registre temprano; el evento real se
// dispara cuando la página termina de cargar.
instalarAnalytics();

createRoot(document.getElementById("root")!).render(<App />);
