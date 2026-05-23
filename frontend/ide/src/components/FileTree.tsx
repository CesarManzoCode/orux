import { useState } from "react";
import { FolderOpen, KeyRound, ChevronRight, Trash2 } from "lucide-react";
import { useStore } from "../useStore";
import {
  seleccionar, borrar,
  impactosQueAfectan, propuestasDe, severidadMax,
  type Peer,
} from "../store";
import { arbol, chipDe, inicial, type Nodo } from "../lang";
import { useI18n } from "../i18n";
import { ConfirmDialog } from "./ConfirmDialog";

function Chip({ path }: { path: string }) {
  const c = chipDe(path);
  return <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>;
}

// Guías verticales tipo tree: una columna `.tg` (14px) por nivel de
// profundidad. Cada columna pinta un hairline vertical centrado, así el
// ojo conecta archivos con su carpeta sin tener que contar sangría — el
// mismo patrón que usa VSCode / JetBrains / Sublime. depth=0 no pinta
// nada (raíz del workspace). aria-hidden porque la jerarquía ya está en
// el DOM (ul anidado conceptualmente); las guías son sólo señal visual.
function Guides({ depth }: { depth: number }) {
  if (depth === 0) return null;
  return (
    <>
      {Array.from({ length: depth }, (_, i) => (
        <span className="tg" key={i} aria-hidden />
      ))}
    </>
  );
}

export function FileTree() {
  const s = useStore();
  const { t } = useI18n();
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  // Modal de confirmación al borrar — reemplaza window.confirm() (mismo
  // mensaje, mejor presentación + a11y). `confirmDel` guarda el path en
  // espera de confirmación; null = sin modal.
  const [confirmDel, setConfirmDel] = useState<string | null>(null);
  const paths = Object.keys(s.files);

  if (paths.length === 0) {
    return (
      <div className="empty">
        <div className="empty-ic"><FolderOpen size={20} /></div>
        <div className="empty-tit">{t.sb_empty_title}</div>
        <div className="empty-sub">{t.sb_empty_sub}</div>
      </div>
    );
  }

  const toggle = (ruta: string) => {
    const n = new Set(abiertas);
    n.has(ruta) ? n.delete(ruta) : n.add(ruta);
    setAbiertas(n);
  };

  const yoId = s.yo?.client_id;
  const presPorPath: Record<string, Peer[]> = {};
  for (const p of Object.values(s.peers)) {
    if (!p.path || p.client_id === yoId) continue;
    (presPorPath[p.path] ||= []).push(p);
  }
  const hayPresenciaBajo = (pref: string) =>
    Object.keys(presPorPath).some((q) => q.startsWith(pref + "/"));
  const hayRiesgoBajo = (pref: string) =>
    Object.values(s.impacts).some((i) => i.affected_path.startsWith(pref + "/"));

  const filas: JSX.Element[] = [];
  const pintar = (nodo: Nodo, ruta: string, depth: number) => {
    for (const nombre of Object.keys(nodo.dirs).sort()) {
      const rd = ruta ? ruta + "/" + nombre : nombre;
      // "cerrada" se controla por toggle explícito O por revelación
      // automática del archivo activo (si el current está debajo de
      // este dir, se considera abierto sin tocar el set). Mismo
      // comportamiento que antes, sólo cambia el rendering.
      const cerrada = abiertas.has(rd) ? false
        : !(s.currentPath && s.currentPath.startsWith(rd + "/"));
      filas.push(
        <li key={"d:" + rd}
            className={"row dir" + (cerrada ? "" : " abierta")}
            onClick={() => toggle(rd)}>
          <span className="row-indent">
            <Guides depth={depth} />
            <span className="twist" aria-hidden>
              <ChevronRight size={12} strokeWidth={2.2} />
            </span>
          </span>
          <span className="name">{nombre}</span>
          <span className="sig">
            {hayRiesgoBajo(rd) && (
              <span className="sig-risk s-media" title={t.ft_impact_inside} />
            )}
            {hayPresenciaBajo(rd) && (
              <span className="sig-live" title={t.ft_presence_inside} />
            )}
          </span>
        </li>
      );
      if (!cerrada) pintar(nodo.dirs[nombre], rd, depth + 1);
    }
    for (const f of nodo.files.slice().sort((a, b) => a.nombre.localeCompare(b.nombre))) {
      const aqui = presPorPath[f.path] || [];
      const due = s.owners[f.path];
      const esMio = !!(yoId && due === yoId);
      const props = propuestasDe(f.path).length;
      const riesgo = severidadMax(impactosQueAfectan(f.path));
      const sinMarcar = !!s.dirty[f.path];
      filas.push(
        <li key={"f:" + f.path}
            data-tour-id={"file-" + f.path}
            className={"row file" + (f.path === s.currentPath ? " activo" : "")}
            onClick={() => seleccionar(f.path)}>
          <span className="row-indent">
            <Guides depth={depth} />
            {/* twist-pad: mismo ancho que el chevron de las carpetas, así
                los archivos quedan alineados visualmente con el contenido
                de su carpeta padre — no con el chevron. */}
            <span className="twist-pad" aria-hidden />
          </span>
          <Chip path={f.path} />
          <span className="name">{f.nombre}</span>
          <span className="sig">
            {sinMarcar && <span className="sig-dirty" title={t.ft_dirty} />}
            {props > 0 && (
              <span className="sig-prop" title={t.ft_proposals(props)}>
                {props}
              </span>
            )}
            {riesgo && (
              <span className={"sig-risk s-" + riesgo} title={t.ft_impact(riesgo)} />
            )}
            {due && (
              <span
                className={"sig-own" + (esMio ? " mio" : "")}
                title={esMio ? t.ft_mine : t.ft_owned}
              >
                <KeyRound size={10} />
              </span>
            )}
            {aqui.map((p) => (
              <span key={p.client_id} className="badge"
                    style={{ background: p.color }}
                    title={p.name + " · " + t.ins_line + " " + p.line}>
                {inicial(p.name)}
              </span>
            ))}
          </span>
          <button className="delx"
            title={t.ft_delete_title(f.path)}
            aria-label={t.ft_delete_title(f.path)}
            onClick={(e) => {
              e.stopPropagation();
              setConfirmDel(f.path);
            }}>
            <Trash2 size={11} />
          </button>
        </li>
      );
    }
  };
  pintar(arbol(paths), "", 0);
  return (
    <>
      <ul className="tree" data-tour-id="files-tree">{filas}</ul>
      {confirmDel && (
        <ConfirmDialog
          title={t.confirm_delete_title}
          message={t.confirm_delete_msg(confirmDel)}
          okLabel={t.confirm_delete_ok}
          cancelLabel={t.confirm_default_cancel}
          tone="danger"
          onCancel={() => setConfirmDel(null)}
          onConfirm={() => {
            const p = confirmDel;
            setConfirmDel(null);
            // Capa 36 (G.2): el toast de éxito sale CUANDO el server
            // confirma el delete (broadcast `delete`), no antes. Pasamos
            // el texto i18n al store para que lo emita en el momento
            // correcto. Si el server rechaza, simplemente no llega el
            // toast (la actividad del Inspector tampoco registra el
            // delete que no ocurrió).
            borrar(p, t.toast_delete_done(p));
          }}
        />
      )}
    </>
  );
}
