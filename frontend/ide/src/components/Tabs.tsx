import { FileQuestion, X, KeyRound, GitPullRequest } from "lucide-react";
import { useStore } from "../useStore";
import { cerrarArchivo, propuestasDe } from "../store";
import { chipDe } from "../lang";

// Capa 26 — Pestaña del archivo abierto. Sigue siendo de UNA pestaña (es
// chrome, no gestor multi-tab), pero ahora LEE estado de coordinación:
// dueño, propuestas pendientes y "sin marcar". Una pestaña de IDE dice en
// qué estado está el archivo sin que abras nada.
export function Tabs() {
  const s = useStore();
  if (!s.currentPath) {
    return (
      <div className="tabs">
        <span className="vacio"><FileQuestion size={14} /> sin archivo abierto</span>
      </div>
    );
  }
  const path = s.currentPath;
  const c = chipDe(path);
  const nombre = path.split("/").pop();
  const sinMarcar = !!s.dirty[path];
  const due = s.owners[path];
  const esMio = !!(s.yo && due === s.yo.client_id);
  const props = propuestasDe(path).length;
  return (
    <div className="tabs">
      <div className="tab activo">
        <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>
        <span className="nom" title={path}>{nombre}</span>
        {due && (
          <span
            className={"tab-own" + (esMio ? " mio" : "")}
            title={esMio ? "tuyo" : "tiene dueño — tus cambios se proponen"}
          >
            <KeyRound size={11} />
          </span>
        )}
        {props > 0 && (
          <span className="tab-prop" title={props + " propuesta(s) pendiente(s)"}>
            <GitPullRequest size={11} /> {props}
          </span>
        )}
        {sinMarcar && (
          <span
            className="dot-sinmarcar"
            title="cambios sin marcar — Ctrl+S para analizar el impacto"
          >
            ●
          </span>
        )}
        <button className="tabx" title="cerrar" onClick={cerrarArchivo}><X size={12} /></button>
      </div>
    </div>
  );
}
