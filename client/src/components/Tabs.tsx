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
  return (
    <div className="tabs">
      <div className="tab">
        <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>
        <span className="nom" title={s.currentPath}>{nombre}</span>
        <button className="tabx" title="cerrar" onClick={cerrarArchivo}>✕</button>
      </div>
    </div>
  );
}
