import { useState } from "react";
import { FolderOpen, KeyRound } from "lucide-react";
import { useStore } from "../useStore";
import {
  seleccionar, borrar,
  impactosQueAfectan, propuestasDe, severidadMax,
  type Peer,
} from "../store";
import { arbol, chipDe, inicial, type Nodo } from "../lang";
import { useI18n } from "../i18n";

function Chip({ path }: { path: string }) {
  const c = chipDe(path);
  return <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>;
}

export function FileTree() {
  const s = useStore();
  const { t } = useI18n();
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
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
      const cerrada = abiertas.has(rd) ? false
        : !(s.currentPath && s.currentPath.startsWith(rd + "/"));
      filas.push(
        <li key={"d:" + rd} className="row dir"
            style={{ paddingLeft: depth * 14 + 8 }}
            onClick={() => toggle(rd)}>
          <span className="twist">{cerrada ? "▸" : "▾"}</span>
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
            className={"row file" + (f.path === s.currentPath ? " activo" : "")}
            style={{ paddingLeft: depth * 14 + 22 }}
            onClick={() => seleccionar(f.path)}>
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
          <button className="delx" title={t.ft_delete_title(f.path)}
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(t.ft_delete_confirm(f.path))) borrar(f.path);
            }}>✕</button>
        </li>
      );
    }
  };
  pintar(arbol(paths), "", 0);
  return <ul className="tree">{filas}</ul>;
}
