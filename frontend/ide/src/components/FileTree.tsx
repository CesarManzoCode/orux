import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { useStore } from "../useStore";
import { seleccionar, borrar } from "../store";
import { arbol, chipDe, inicial, type Nodo } from "../lang";

function Chip({ path }: { path: string }) {
  const c = chipDe(path);
  return <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>;
}

export function FileTree() {
  const s = useStore();
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  const paths = Object.keys(s.files);

  if (paths.length === 0) {
    // Estado vacío real: orienta hacia la acción, no parece roto.
    return (
      <div className="empty">
        <div className="empty-ic"><FolderOpen size={20} /></div>
        <div className="empty-tit">Workspace vacío</div>
        <div className="empty-sub">
          Todavía no hay archivos. Creá el primero con “nuevo archivo”.
        </div>
      </div>
    );
  }

  const toggle = (ruta: string) => {
    const n = new Set(abiertas);
    n.has(ruta) ? n.delete(ruta) : n.add(ruta);
    setAbiertas(n);
  };

  const filas: JSX.Element[] = [];
  const pintar = (nodo: Nodo, ruta: string, depth: number) => {
    for (const nombre of Object.keys(nodo.dirs).sort()) {
      const rd = ruta ? ruta + "/" + nombre : nombre;
      // Las carpetas con el archivo abierto adentro se expanden solas.
      const cerrada = abiertas.has(rd) ? false
        : !(s.currentPath && s.currentPath.startsWith(rd + "/"));
      filas.push(
        <li key={"d:" + rd} className="row dir"
            style={{ paddingLeft: depth * 14 + 8 }}
            onClick={() => toggle(rd)}>
          <span className="twist">{cerrada ? "▸" : "▾"}</span>
          <span className="name">{nombre}/</span>
        </li>
      );
      if (!cerrada) pintar(nodo.dirs[nombre], rd, depth + 1);
    }
    for (const f of nodo.files.slice().sort((a, b) => a.nombre.localeCompare(b.nombre))) {
      const aqui = Object.values(s.peers).filter((p) => p.path === f.path);
      filas.push(
        <li key={"f:" + f.path}
            className={"row file" + (f.path === s.currentPath ? " activo" : "")}
            style={{ paddingLeft: depth * 14 + 22 }}
            onClick={() => seleccionar(f.path)}>
          <Chip path={f.path} />
          <span className="name">{f.nombre}</span>
          <span className="badges">
            {aqui.map((p) => (
              <span key={p.client_id} className="badge"
                    style={{ background: p.color }}
                    title={p.name + " · línea " + p.line}>
                {inicial(p.name)}
              </span>
            ))}
          </span>
          <button className="delx" title={"eliminar " + f.path}
            onClick={(e) => {
              e.stopPropagation();
              if (confirm("¿Eliminar " + f.path + "? No se puede deshacer.")) borrar(f.path);
            }}>✕</button>
        </li>
      );
    }
  };
  pintar(arbol(paths), "", 0);
  return <ul className="tree">{filas}</ul>;
}
