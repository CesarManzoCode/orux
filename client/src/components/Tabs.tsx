import { useStore } from "../useStore";
import { cerrarArchivo } from "../store";
import { chipDe } from "../lang";

// Pestaña del archivo abierto (minimal: la actual). Cerrar = sin archivo
// (no borra). Es chrome, no gestión multi-pestaña.
export function Tabs() {
  const s = useStore();
  if (!s.currentPath) {
    return <div className="tabs"><span className="vacio">sin archivo abierto</span></div>;
  }
  const c = chipDe(s.currentPath);
  const nombre = s.currentPath.split("/").pop();
  const sinMarcar = !!s.dirty[s.currentPath];
  return (
    <div className="tabs">
      <div className="tab">
        <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>
        <span className="nom" title={s.currentPath}>{nombre}</span>
        {/* Capa 19: dot de "sin marcar" — hay cambios desde el último
            checkpoint. Dispara el reflejo Ctrl+S; es verdad (sin analizar),
            no es "sin guardar" (el contenido ya viaja en vivo). */}
        {sinMarcar && (
          <span
            className="dot-sinmarcar"
            title="cambios sin marcar — Ctrl+S para analizar el impacto"
          >
            ●
          </span>
        )}
        <button className="tabx" title="cerrar" onClick={cerrarArchivo}>✕</button>
      </div>
    </div>
  );
}
