import { createRoot } from "react-dom/client";
import "./index.css";
import { connect } from "./store";
import { App } from "./App";

connect(); // abre el WebSocket una vez, al arrancar.

// Sin StrictMode a propósito: el editor sincroniza capas con efectos y
// refs; el doble-montaje de StrictMode en dev sólo agrega ruido a la pieza
// más frágil sin beneficio aquí. Comportamiento = producción.
createRoot(document.getElementById("root")!).render(<App />);
