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
import { useI18n } from "../i18n";

function hace(ts: number, ahora: string): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return ahora;
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  return Math.floor(s / 3600) + "h";
}

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

function ImpactoMini({ im }: { im: Impact }) {
  const { t } = useI18n();
  const sev = severidadMax([im]) || "media";
  return (
    <div className="inimp">
      <span className={"insev s-" + sev}>{t.tr_sev[sev] ?? sev}</span>
      <span className="inimp-tx">
        <b>{im.author_name}</b> {t.ins_changed}{" "}
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

export function Inspector({
  onClose,
  width,
}: {
  onClose: () => void;
  width?: number;
}) {
  const s = useStore();
  const { t } = useI18n();
  const path = s.currentPath;
  const c = path ? chipDe(path) : null;

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
    <aside
      className="inspector isla"
      style={width != null ? { width: width + "px" } : undefined}
    >
      <header className="in-head">
        <span className="in-eyebrow">{t.ins_title}</span>
        <button className="in-x" title={t.ins_hide} onClick={onClose}>
          <PanelRightClose size={15} />
        </button>
      </header>

      {path ? (
        <div className="in-file">
          <span className={"chip" + (c!.cls ? " " + c!.cls : "")}>{c!.txt}</span>
          <span className="in-file-n" title={path}>
            {path.split("/").pop()}
          </span>
          {s.dirty[path] && <span className="in-flag warn">{t.ins_unmarked}</span>}
          {riesgo && (
            <span className={"in-flag r-" + riesgo}>{t.ins_risk[riesgo]}</span>
          )}
        </div>
      ) : (
        <div className="in-file off">{t.ins_no_file}</div>
      )}

      <div className="in-scroll">
        <Sec ic={<Radio size={13} />} tit={t.ins_presence_title} n={aqui.length}>
          {aqui.length === 0 ? (
            <p className="in-empty">{t.ins_nobody(otrosEquipo.length)}</p>
          ) : (
            aqui.map((p) => (
              <div className="inrow" key={p.client_id}>
                <span className="inav" style={{ background: p.color }} />
                <span className="inrow-n">{p.name}</span>
                <span className="inrow-m">{t.ins_line} {p.line}</span>
              </div>
            ))
          )}
        </Sec>

        <Sec ic={<KeyRound size={13} />} tit={t.ins_ownership_title}>
          {!path ? (
            <p className="in-empty">—</p>
          ) : !due ? (
            <div className="inrow">
              <span className="in-flag faint">{t.ins_no_owner}</span>
              <button className="in-act" onClick={() => reclamar(path)}>
                {t.ins_claim}
              </button>
            </div>
          ) : esMio ? (
            <div className="inrow">
              <span className="in-flag ok">{t.ins_mine}</span>
              <span className="inrow-m">{t.ins_mine_sub}</span>
            </div>
          ) : (
            <div className="inrow col">
              <span className="in-flag warn">{t.ins_of(nombreDe(due))}</span>
              <span className="inrow-m">{t.ins_others_sub}</span>
            </div>
          )}
        </Sec>

        <Sec
          ic={<Waypoints size={13} />} tit={t.ins_impact_title}
          n={impLo.length} tono={riesgo === "alta" ? "alarma" : undefined}
        >
          {impLo.length === 0 && impDesde.length === 0 ? (
            <p className="in-empty">{t.ins_no_impact}</p>
          ) : (
            <>
              {impLo.map((im, i) => <ImpactoMini im={im} key={"l" + i} />)}
              {impDesde.length > 0 && (
                <p className="in-note">{t.ins_downstream(impDesde.length)}</p>
              )}
            </>
          )}
        </Sec>

        <Sec
          ic={<GitPullRequest size={13} />} tit={t.ins_proposals_title}
          n={props.length}
        >
          {props.length === 0 ? (
            <p className="in-empty">
              {t.ins_no_proposals}
              {propsMios.length > 0 && t.ins_waiting_others(propsMios.length)}
            </p>
          ) : (
            props.map((p) => (
              <div className="inrow col" key={p.id}>
                <span className="inrow-n">
                  <b>{p.author_name}</b> {t.ins_proposes}
                </span>
                <span className="inrow-m">
                  {esMio ? t.ins_waiting : t.ins_in_review}
                </span>
              </div>
            ))
          )}
        </Sec>

        <Sec ic={<Activity size={13} />} tit={t.ins_activity_title} n={s.actividad.length}>
          {s.actividad.length === 0 ? (
            <p className="in-empty">{t.ins_no_activity}</p>
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
                  <span className="infeed-t">{hace(a.ts, t.ins_now)}</span>
                </li>
              ))}
            </ul>
          )}
        </Sec>

        {impLo.length > 0 && (
          <div className="in-foot">
            <AlertTriangle size={12} />
            {t.ins_impact_count(impLo.length)}
          </div>
        )}
      </div>
    </aside>
  );
}
