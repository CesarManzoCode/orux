import { useEffect, useMemo, useRef, useState } from "react";
import { Shield, X } from "lucide-react";
import { useStore } from "../useStore";
import { adminAsignarVarios, nombreDe, nombreVisible } from "../store";
import { arbol, archivosDe, chipDe, type Nodo } from "../lang";
import { useI18n } from "../i18n";
import { ModalPortal } from "./ModalPortal";

export function AdminModal({ onClose }: { onClose: () => void }) {
  const s = useStore();
  const { t } = useI18n();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [user, setUser] = useState("");
  const [colapsadas, setColapsadas] = useState<Set<string>>(new Set());
  // Al abrir, el foco entra al modal (botón de cerrar): el usuario de
  // teclado no queda con el foco detrás del diálogo. Deps [] = solo al
  // montar (mismo motivo que en los otros modales).
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  // `paths` se recalcula en cada render pero su identidad NO es estable
  // — el dep anterior `[paths.join("\0")]` se evaluaba en cada render
  // igualmente y el memo no servía. Atamos el memo a `s.files` (referencia
  // estable mientras el store no cambia esa porción): la rama derecha
  // recalcula `paths` dentro del memo, una sola vez.
  const { paths, raiz } = useMemo(() => {
    const ps = Object.keys(s.files);
    return { paths: ps, raiz: arbol(ps) };
  }, [s.files]);

  useEffect(() => {
    // window (no document) — homogéneo con el resto de modales del IDE
    // (ConfirmDialog, LegalModal, InviteModal, NuevoArchivoModal): un solo
    // patrón de listener evita sorpresas si en el futuro alguien añade un
    // capturer global.
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
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
    setSel(new Set());
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
            aria-label={nombre}
            ref={(el) => { if (el) el.indeterminate = dentro > 0 && dentro < archivos.length; }}
            checked={archivos.length > 0 && dentro === archivos.length}
            onChange={(e) => toggleDir(archivos, e.target.checked)} />
          {/* Antes era <span onClick>: sin rol, sin teclado, chevron como
              texto. Ahora es <button> con aria-expanded — patrón coherente
              con el resto del IDE (Inspector Sec, FileTree dirs). */}
          <button
            type="button"
            className="amtw"
            aria-expanded={!cerrada}
            aria-label={(cerrada ? t.am_dir_expand : t.am_dir_collapse) + " " + nombre}
            onClick={() => setColapsadas((c) => {
              const n = new Set(c);
              n.has(rd) ? n.delete(rd) : n.add(rd);
              return n;
            })}
          >
            <span aria-hidden>{cerrada ? "▸" : "▾"}</span>
          </button>
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
          <input type="checkbox" aria-label={f.path} checked={sel.has(f.path)}
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
    <ModalPortal>
    <div
      className="modalbg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="am-h"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal am-modal">
        <header className="modal-head">
          <h2 id="am-h" className="modal-h">
            <Shield size={15} /> {t.am_title}
          </h2>
          <button ref={closeRef} className="modal-x" aria-label={t.am_close} onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <div className="ambar">
          <label className="amsel">
            {t.am_owner_label}
            <select value={user} onChange={(e) => setUser(e.target.value)}>
              <option value="">{t.am_owner_empty}</option>
              {s.usuarios.map((u) => (
                <option key={u} value={u}>{nombreVisible(u)}</option>
              ))}
            </select>
          </label>
          <span className="amcount">
            {n + " " + (n === 1 ? t.am_selected_one : t.am_selected_many)}
          </span>
          <span className="spacer" />
          <button onClick={() => setSel(new Set(paths))}>{t.am_all}</button>
          <button onClick={() => setSel(new Set())}>{t.am_none}</button>
          <button className="amgo" disabled={n === 0 || !user} onClick={() => aplicar(user)}>
            {t.am_assign(n)}
          </button>
          <button className="amno" disabled={n === 0} onClick={() => aplicar("")}>
            {t.am_remove(n)}
          </button>
        </div>
        <div className="amtree">
          {paths.length === 0
            ? <div className="amvacio">{t.am_no_files}</div>
            : filas}
        </div>
        <footer className="am-foot">
          {n === 0
            ? t.am_hint_empty
            : user
              ? t.am_hint_assign(nombreVisible(user), n)
              : t.am_hint_nouser(n)}
        </footer>
      </div>
    </div>
    </ModalPortal>
  );
}
