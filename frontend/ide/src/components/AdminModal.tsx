import { useEffect, useMemo, useState } from "react";
import { Shield, X } from "lucide-react";
import { useStore } from "../useStore";
import { adminAsignarVarios, nombreDe } from "../store";
import { arbol, archivosDe, chipDe, type Nodo } from "../lang";

// Capa 13 — reparto MASIVO de ownership, en su propio modal. La primera
// queja real: de a uno en 100 archivos es inusable. Acá: árbol con
// checkboxes, carpetas con tri-estado (seleccionan todos sus archivos),
// un dueño elegido UNA vez, "asignar a N". Un solo mensaje bulk. Carpeta =
// sus archivos (el ownership sigue por archivo; por prefijo está diferido).
export function AdminModal({ onClose }: { onClose: () => void }) {
  const s = useStore();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [user, setUser] = useState("");
  const [colapsadas, setColapsadas] = useState<Set<string>>(new Set());
  const paths = Object.keys(s.files);
  const raiz = useMemo(() => arbol(paths), [paths.join("\0")]);

  // Esc cierra; limpiar selección de paths que ya no existen.
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);
  useEffect(() => {
    setSel((prev) => {
      const n = new Set([...prev].filter((p) => p in s.files));
      return n.size === prev.size ? prev : n;
    });
  }, [s.files]);

  const toggleFile = (p: string, on: boolean) => {
    setSel((prev) => {
      const n = new Set(prev);
      on ? n.add(p) : n.delete(p);
      return n;
    });
  };
  const toggleDir = (archivos: string[], on: boolean) => {
    setSel((prev) => {
      const n = new Set(prev);
      archivos.forEach((p) => (on ? n.add(p) : n.delete(p)));
      return n;
    });
  };

  function aplicar(username: string) {
    if (sel.size === 0) return;
    adminAsignarVarios([...sel], username);
    setSel(new Set()); // el server difunde el ownership nuevo
  }

  const filas: JSX.Element[] = [];
  const pintar = (nodo: Nodo, ruta: string, depth: number) => {
    for (const nombre of Object.keys(nodo.dirs).sort()) {
      const rd = ruta ? ruta + "/" + nombre : nombre;
      const sub = nodo.dirs[nombre];
      const archivos = archivosDe(sub);
      const dentro = archivos.filter((p) => sel.has(p)).length;
      const cerrada = colapsadas.has(rd);
      filas.push(
        <div className="amrow dir" key={"d:" + rd} style={{ paddingLeft: depth * 16 + 8 }}>
          <input type="checkbox"
            ref={(el) => { if (el) el.indeterminate = dentro > 0 && dentro < archivos.length; }}
            checked={archivos.length > 0 && dentro === archivos.length}
            onChange={(e) => toggleDir(archivos, e.target.checked)} />
          <span className="amtw" style={{ cursor: "pointer" }}
            onClick={() => setColapsadas((c) => { const n = new Set(c); n.has(rd) ? n.delete(rd) : n.add(rd); return n; })}>
            {cerrada ? "▸" : "▾"}
          </span>
          <span className="amname">{nombre}/</span>
          <span className="ammeta">{archivos.length}</span>
        </div>
      );
      if (!cerrada) pintar(sub, rd, depth + 1);
    }
    for (const f of nodo.files.slice().sort((a, b) => a.nombre.localeCompare(b.nombre))) {
      const due = s.owners[f.path];
      const c = chipDe(f.path);
      filas.push(
        <div className="amrow file" key={"f:" + f.path} style={{ paddingLeft: depth * 16 + 26 }}>
          <input type="checkbox" checked={sel.has(f.path)}
            onChange={(e) => toggleFile(f.path, e.target.checked)} />
          <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>
          <span className="amname">{f.nombre}</span>
          {due && <span className="amowner">→ {nombreDe(due)}</span>}
        </div>
      );
    }
  };
  pintar(raiz, "", 0);

  const n = sel.size;
  return (
    <div className="ammodal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="amcard">
        <div className="amhead">
          <span className="amtit"><Shield size={15} /> administración · ownership</span>
          <button className="amx" title="cerrar" onClick={onClose}><X size={15} /></button>
        </div>
        <div className="ambar">
          <label className="amsel">
            dueño:
            <select value={user} onChange={(e) => setUser(e.target.value)}>
              <option value="">— elegí un usuario —</option>
              {s.usuarios.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </label>
          <span className="amcount">{n + (n === 1 ? " seleccionado" : " seleccionados")}</span>
          <span className="spacer" />
          <button onClick={() => setSel(new Set(paths))}>todo</button>
          <button onClick={() => setSel(new Set())}>nada</button>
          <button className="amgo" disabled={n === 0 || !user} onClick={() => aplicar(user)}>
            asignar a {n}
          </button>
          <button className="amno" disabled={n === 0} onClick={() => aplicar("")}>
            quitar dueño a {n}
          </button>
        </div>
        <div className="amtree">
          {paths.length === 0
            ? <div className="amvacio">no hay archivos en el workspace.</div>
            : filas}
        </div>
        <div className="amfoot">
          {n === 0
            ? "seleccioná archivos o carpetas; elegí un dueño; aplicá al lote."
            : user
              ? `“asignar” pondrá a «${user}» como dueño de ${n} archivo(s). “quitar” los deja sin dueño.`
              : `${n} archivo(s) seleccionados — elegí un usuario, o usá “quitar dueño”.`}
        </div>
      </div>
    </div>
  );
}
