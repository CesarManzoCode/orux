import { createRoot } from "react-dom/client";
// AUDITORIA-SEGURIDAD 2026-05-25 A-INF-02: tipografías self-hosted en vez
// de Google Fonts (que filtraba IP+UA+Referer en cada visita). Los .woff2
// vienen del bundle local; el variable font cubre 14..32 opsz con un solo
// archivo, y el mono carga los pesos 400/500/600/700 que el sistema usa.
import "@fontsource-variable/inter/index.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "@fontsource/jetbrains-mono/700.css";
import "./index.css";
import { App } from "./App";
import { instalar as instalarAnalytics } from "./analytics";

// Analytics propio (POST /api/v1/track). No-op en dev. Va ANTES de render
// para que el listener de `load` se registre temprano; el evento real se
// dispara cuando la página termina de cargar.
instalarAnalytics();

createRoot(document.getElementById("root")!).render(<App />);
