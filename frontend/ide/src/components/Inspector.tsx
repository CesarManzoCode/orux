import type { ReactNode } from "react";
import {
  Radio, KeyRound, Waypoints, GitPullRequest, Activity,
  LogIn, LogOut, GitBranch, Trash2, FolderSync, AlertTriangle,
  PanelRightClose,
} from "lucide-react";
import { useStore } from "../useStore";
import {
  reclamar, seleccionar, nombreDe,
  impactosQueAfectan, propuestasDe, severidadMax, presentesEn,
  type ActItem, type Impact,
} from "../store";
import { chipDe } from "../lang";

// Capa 26 — Inspector contextual. La tesis hecha UI: no es un editor con
// un panel de cards, es un puesto de coordinación. Todo lo que muestra
// responde a "¿quién toca esto / quién manda / qué se rompe / qué se
// propone / qué pasó?" sobre el ARCHIVO ABIERTO y el equipo. Cero datos
// inventados: si no hay señal, lo dice; nunca finge "riesgo: bajo".

function hace(ts: number): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return "ahora";
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  return Math.floor(s / 3600) + "h";
}

// Encabezado de sección del inspector: micro-mayúsculas + contador.
// Mismo patrón en todas las secciones = lectura de instrumento.
function Sec(props: {
  ic: ReactNode; tit: string; n?: number; tono?: string;
  children: ReactNode;
}) {
  return (
    <section className={"insec" + (props.tono ? " " + props.tono : "")}>
      <div className="insec-h">
        <span className="insec-ic">{props.ic}</span>
        <span className="insec-t">{props.tit}</span>
        {props.n != null && <span className="insec-n">{props.n}</span>}
      </div>
      <div className="insec-b">{props.children}</div>
    </section>
  );
}

const RIESGO: Record<string, string> = {
  alta: "riesgo alto", media: "riesgo medio", baja: "riesgo bajo",
};

function ImpactoMini({ im }: { im: Impact }) {
  const sev = severidadMax([im]) || "media";
  return (
    <div className="inimp">
      <span className={"insev s-" + sev}>{sev}</span>
      <span className="inimp-tx">
        <b>{im.author_name}</b> cambió{" "}
        {im.symbols.map((x, i) => (
          <code key={i}>{x}{i < im.symbols.length - 1 ? " " : ""}</code>
        ))}{" "}
        en <span className="inpath">{im.source_path}</span>
      </span>
    </div>
  );
}

const ACT_IC: Record<ActItem["kind"], ReactNode> = {
  join: <LogIn size={12} />, leave: <LogOut size={12} />,
  propuesta: <GitPullRequest size={12} />, impacto: <Waypoints size={12} />,
  ownership: <KeyRound size={12} />, git: <GitBranch size={12} />,
  delete: <Trash2 size={12} />, workspace: <FolderSync size={12} />,
};

export function Inspector({ onClose }: { onClose: () => void }) {
  const s = useStore();
  const path = s.currentPath;
  const c = path ? chipDe(path) : null;

  // Señales del archivo abierto (selectores derivados del store).
  const aqui = path ? presentesEn(path) : [];
  const due = path ? s.owners[path] : undefined;
  const esMio = !!(s.yo && due === s.yo.client_id);
  const impLo = path ? impactosQueAfectan(path) : [];
  const impDesde = path
    ? Object.values(s.impacts).filter((i) => i.source_path === path) : [];
  const props = path ? propuestasDe(path) : [];
  const riesgo = severidadMax(impLo);
  const otrosEquipo = Object.values(s.peers).filter(
    (p) => !s.yo || p.client_id !== s.yo.client_id,
  );
  const propsMios = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  );

  return (
    <aside className="inspector isla">
      <header className="in-head">
        <span className="in-eyebrow">inspector de coordinación</span>
        <button className="in-x" title="ocultar inspector" onClick={onClose}>
          <PanelRightClose size={15} />
        </button>
      </header>

      {path ? (
        <div className="in-file">
          <span className={"chip" + (c!.cls ? " " + c!.cls : "")}>{c!.txt}</span>
          <span className="in-file-n" title={path}>
            {path.split("/").pop()}
          </span>
          {s.dirty[path] && <span className="in-flag warn">sin marcar</span>}
          {riesgo && (
            <span className={"in-flag r-" + riesgo}>{RIESGO[riesgo]}</span>
          )}
        </div>
      ) : (
        <div className="in-file off">ningún archivo abierto</div>
      )}

      <div className="in-scroll">
        <Sec ic={<Radio size={13} />} tit="presencia viva" n={aqui.length}>
          {aqui.length === 0 ? (
            <p className="in-empty">
              Nadie más en este archivo. {otrosEquipo.length} en el equipo.
            </p>
          ) : (
            aqui.map((p) => (
              <div className="inrow" key={p.client_id}>
                <span className="inav" style={{ background: p.color }} />
                <span className="inrow-n">{p.name}</span>
                <span className="inrow-m">línea {p.line}</span>
              </div>
            ))
          )}
        </Sec>

        <Sec ic={<KeyRound size={13} />} tit="ownership">
          {!path ? (
            <p className="in-empty">—</p>
          ) : !due ? (
            <div className="inrow">
              <span className="in-flag faint">sin dueño</span>
              <button className="in-act" onClick={() => reclamar(path)}>
                reclamar
              </button>
            </div>
          ) : esMio ? (
            <div className="inrow">
              <span className="in-flag ok">tuyo</span>
              <span className="inrow-m">lo editás directo</span>
            </div>
          ) : (
            <div className="inrow col">
              <span className="in-flag warn">de {nombreDe(due)}</span>
              <span className="inrow-m">
                lo que escribas se le propone — no se aplica hasta que apruebe
              </span>
            </div>
          )}
        </Sec>

        <Sec
          ic={<Waypoints size={13} />} tit="impacto"
          n={impLo.length} tono={riesgo === "alta" ? "alarma" : undefined}
        >
          {impLo.length === 0 && impDesde.length === 0 ? (
            <p className="in-empty">Sin impacto detectado sobre este archivo.</p>
          ) : (
            <>
              {impLo.map((im, i) => <ImpactoMini im={im} key={"l" + i} />)}
              {impDesde.length > 0 && (
                <p className="in-note">
                  Tus cambios acá afectan a <b>{impDesde.length}</b>{" "}
                  archivo(s) aguas abajo.
                </p>
              )}
            </>
          )}
        </Sec>

        <Sec
          ic={<GitPullRequest size={13} />} tit="cambios propuestos"
          n={props.length}
        >
          {props.length === 0 ? (
            <p className="in-empty">
              Nada propuesto sobre este archivo.
              {propsMios.length > 0 &&
                ` ${propsMios.length} esperan tu revisión en otros.`}
            </p>
          ) : (
            props.map((p) => (
              <div className="inrow col" key={p.id}>
                <span className="inrow-n">
                  <b>{p.author_name}</b> propone cambios
                </span>
                <span className="inrow-m">
                  {esMio ? "esperando tu aprobación" : "en revisión"}
                </span>
              </div>
            ))
          )}
        </Sec>

        <Sec ic={<Activity size={13} />} tit="actividad" n={s.actividad.length}>
          {s.actividad.length === 0 ? (
            <p className="in-empty">Sin actividad de coordinación todavía.</p>
          ) : (
            <ul className="infeed">
              {s.actividad.slice(0, 40).map((a) => (
                <li
                  className={"infeed-i k-" + a.kind}
                  key={a.id}
                  onClick={() => {
                    if (a.path && a.path in s.files) seleccionar(a.path);
                  }}
                  style={{ cursor: a.path ? "pointer" : "default" }}
                >
                  <span className="infeed-ic">{ACT_IC[a.kind]}</span>
                  <span className="infeed-tx">
                    {a.actor && <b>{a.actor}</b>} {a.text}
                    {a.path && <span className="inpath"> {a.path}</span>}
                  </span>
                  <span className="infeed-t">{hace(a.ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </Sec>

        {impLo.length > 0 && (
          <div className="in-foot">
            <AlertTriangle size={12} />
            {impLo.length} aviso(s) de impacto activos sobre este archivo
          </div>
        )}
      </div>
    </aside>
  );
}
