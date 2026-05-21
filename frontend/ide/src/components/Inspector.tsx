import { useCallback, useEffect, useState, useMemo, type ReactNode } from "react";
import {
  Radio, KeyRound, Waypoints, GitPullRequest, Activity,
  LogIn, LogOut, GitBranch, Trash2, FolderSync, AlertTriangle,
  PanelRightClose, ChevronDown, Send, Undo2, ShieldCheck, Sparkles,
  Bell, Hand, X,
} from "lucide-react";
import { useStore } from "../useStore";
import {
  reclamar, seleccionar, resolver, nombreDe, guardar, descartarDraft,
  descartarImpacto, impactosQueAfectan, propuestasDe, severidadMax, presentesEn,
  type ActItem, type Impact, type Proposal,
} from "../store";
import { chipDe, diffLineas, inicial } from "../lang";
import { useI18n } from "../i18n";

// ── Helpers de tiempo: la presencia se siente VIVA si "hace cuánto" se
// lee de un vistazo. "ahora" para <5s; segundos, minutos, horas en
// adelante. Mismo modelo que usaba el feed antes — extraído para reuso
// (hero + propuestas).
function hace(ts: number, ahora: string): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return ahora;
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  return Math.floor(s / 3600) + "h";
}

// Capa 28: el inspector se llenó de secciones (presencia, ownership, impacto,
// propuestas, actividad). Cada una valiosa, pero juntas el panel pesa. La
// cura no es esconder señal: es dejarte plegar lo que ahora mismo no querés.
// El estado de plegado se persiste en localStorage para que el ojo respete
// como dejaste el panel; el conteo del header sigue visible plegado (la
// "señal" no se apaga, sólo el detalle).
const COLAPSO_KEY = "orux_insp_colapso";
function leerColapso(): Set<string> {
  try {
    const raw = localStorage.getItem(COLAPSO_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? new Set<string>(arr) : new Set();
  } catch { return new Set(); }
}
function escribirColapso(s: Set<string>) {
  try { localStorage.setItem(COLAPSO_KEY, JSON.stringify([...s])); } catch {}
}

function Sec(props: {
  k: string; ic: ReactNode; tit: string; n?: number; tono?: string;
  colapsadas: Set<string>; toggle: (k: string) => void;
  children: ReactNode;
}) {
  const plegada = props.colapsadas.has(props.k);
  return (
    <section
      className={
        "insec" + (props.tono ? " " + props.tono : "") +
        (plegada ? " plegada" : "")
      }
    >
      <button
        type="button"
        className="insec-h"
        aria-expanded={!plegada}
        onClick={() => props.toggle(props.k)}
      >
        <span className="insec-ic">{props.ic}</span>
        <span className="insec-t">{props.tit}</span>
        {props.n != null && <span className="insec-n">{props.n}</span>}
        <span className="insec-chev">
          <ChevronDown size={13} />
        </span>
      </button>
      {!plegada && <div className="insec-b">{props.children}</div>}
    </section>
  );
}

function ImpactoMini({ im }: { im: Impact }) {
  const { t } = useI18n();
  const sev = severidadMax([im]) || "media";
  // Botón "visto" — el dueño revisó el aviso y lo descarta para que no se
  // quede ahí permanente. Solo borra de su estado local: si el cambio vuelve
  // a llegar (porque otro Ctrl+S), reaparece. Sin eso la lista crece sin
  // forma de limpiarla.
  const key = im.source_path + "::" + im.affected_path;
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
      <button
        type="button"
        className="inimp-x"
        title={t.ins_impact_dismiss}
        aria-label={t.ins_impact_dismiss}
        onClick={() => descartarImpacto(key)}
      >
        <X size={12} />
      </button>
    </div>
  );
}

const ACT_IC: Record<ActItem["kind"], ReactNode> = {
  join: <LogIn size={12} />, leave: <LogOut size={12} />,
  propuesta: <GitPullRequest size={12} />, impacto: <Waypoints size={12} />,
  ownership: <KeyRound size={12} />, git: <GitBranch size={12} />,
  delete: <Trash2 size={12} />, workspace: <FolderSync size={12} />,
};

// ── PropCard: la propuesta ELEVADA. Antes era una fila plana con un diff
// pequeño. Ahora trae: autor con su color (mismo idioma que avatares de
// TopBar/FileTree), "hace X", stats +adds/−dels (calculados de
// diffLineas) y aprobar/rechazar grandes. El diff sigue debajo, pero
// ahora se LEE en contexto. La decisión es del dueño — la UI debe
// inspirar confianza para apretar el botón.
function PropCard({
  p, mio, files, peerColor,
}: {
  p: Proposal; mio: boolean; files: Record<string, string>;
  peerColor: string | null;
}) {
  const { t } = useI18n();
  const filas = useMemo(
    () => diffLineas(files[p.path] ?? "", p.content),
    [files, p.content, p.path],
  );
  // Stats sobrios: contamos add/del; el reviewer ve el "tamaño" del cambio
  // sin tener que escanear el diff entero.
  const adds = filas.filter((f) => f.t === "add").length;
  const dels = filas.filter((f) => f.t === "del").length;
  // Tiempo: "hace X" — el seen_at se setea al recibir (honest, no inventado).
  const ts = p.seen_at;
  const ahora = ts == null ? t.ins_prop_seen_now : hace(ts, t.ins_prop_seen_now);
  const tiempo = ts == null || ahora === t.ins_prop_seen_now
    ? t.ins_prop_seen_now : t.ins_prop_seen(ahora);

  // Botones de acción: SOLO si esta propuesta es para mí (soy dueño).
  // Si la propuse yo, sólo mostramos estado "en revisión" (lo decide el otro).
  return (
    <article className="inprop">
      <header className="inprop-h">
        <span
          className="inprop-av"
          style={{ background: peerColor || "var(--muted)" }}
          title={p.author_name}
          aria-hidden
        >
          {inicial(p.author_name)}
        </span>
        <span className="inprop-meta">
          <span className="inprop-who">
            <b>{p.author_name}</b> {t.ins_proposes}
          </span>
          <span className="inprop-sub">
            <span className="inprop-ago" title={ts ? new Date(ts).toLocaleString() : ""}>
              {tiempo}
            </span>
            <span className="inprop-dot">·</span>
            {adds === 0 && dels === 0 ? (
              <span className="inprop-nochg">{t.ins_prop_no_change}</span>
            ) : (
              <span className="inprop-stats">
                <span className="ip-add">{t.ins_prop_stats_added(adds)}</span>
                <span className="ip-del">{t.ins_prop_stats_removed(dels)}</span>
              </span>
            )}
          </span>
        </span>
        {mio && (
          <span className="inprop-a">
            <button
              className="ok"
              onClick={() => resolver(p.id, true)}
              aria-label={t.tr_approve}
              title={t.kbd_btn_hint_approve}
            >
              {t.tr_approve}
            </button>
            <button
              className="no"
              onClick={() => resolver(p.id, false)}
              aria-label={t.tr_reject}
              title={t.kbd_btn_hint_reject}
            >
              {t.tr_reject}
            </button>
          </span>
        )}
        {!mio && <span className="inprop-status">{t.ins_in_review}</span>}
      </header>
      {(adds > 0 || dels > 0) && (
        <div className="diff">
          {filas.map((f, i) => (
            <div key={i} className={f.t}>{f.x || " "}</div>
          ))}
        </div>
      )}
    </article>
  );
}

// Item de atención: una "tarjeta-callout" con icono, título y subtítulo.
// La regla es: SI hay algo aquí, el usuario sabe qué hacer. Si no hay
// nada, mostramos "todo en orden" — esto reduce la ansiedad ("¿se me
// pasó algo?"). El tono dirige el ojo: alta = rojo, media = ámbar,
// info = azul, calma = verde.
function AtnItem(props: {
  tono: "alta" | "media" | "info" | "calma";
  ic: ReactNode; tit: string; sub: string;
}) {
  return (
    <div className={"in-atn-item t-" + props.tono}>
      <span className="in-atn-ic">{props.ic}</span>
      <span className="in-atn-tx">
        <span className="in-atn-tit">{props.tit}</span>
        <span className="in-atn-sub">{props.sub}</span>
      </span>
    </div>
  );
}

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

  const [colapsadas, setColapsadas] = useState<Set<string>>(leerColapso);
  const toggle = useCallback((k: string) => {
    setColapsadas((prev) => {
      const n = new Set(prev);
      if (n.has(k)) n.delete(k); else n.add(k);
      escribirColapso(n);
      return n;
    });
  }, []);
  // Estado optimista de "reclamando" (UX: el server responde con ownership
  // en milisegundos pero el feedback visual instantáneo previene
  // doble-clicks y reasegura al usuario de que su acción se registró). Se
  // resetea cuando el `owners[path]` realmente cambió a mío, o si pasamos
  // 3s sin respuesta (paranoia).
  const [claimingPath, setClaimingPath] = useState<string | null>(null);

  // Capa 29 UX: tick interno que refresca los "hace X" cada 15s. Sin esto
  // las propuestas se quedan congeladas en "recién" durante toda la sesión.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 15000);
    return () => clearInterval(id);
  }, []);

  const aqui = path ? presentesEn(path) : [];
  const due = path ? s.owners[path] : undefined;
  const esMio = !!(s.yo && due === s.yo.client_id);
  const esDeOtro = !esMio && !!due;
  const tieneDraft = !!(path && s.drafts[path] != null);
  const sinMarcarLocal = !!(path && s.dirty[path]);
  const impLo = path ? impactosQueAfectan(path) : [];
  const impDesde = path
    ? Object.values(s.impacts).filter((i) => i.source_path === path) : [];
  // Capa 28: propuestas DEL archivo abierto. Las que están dirigidas a mí
  // (porque soy dueño) traen diff + aprobar/rechazar acá mismo.
  const props = path ? propuestasDe(path) : [];
  const propsParaMi = props.filter(() => esMio);
  const riesgo = severidadMax(impLo);
  const otrosEquipo = Object.values(s.peers).filter(
    (p) => !s.yo || p.client_id !== s.yo.client_id,
  );
  // Todas las propuestas a la espera de mi review (de cualquier archivo)
  const propsMios = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  );
  // El badge de "cambios propuestos" prioriza lo accionable: lo que espera
  // MI review. Si no hay nada para mí en este archivo, cae al total de
  // propuestas del archivo (incluye las mías en revisión).
  const nProps = propsParaMi.length || props.length;
  // Total global de borradores (todos los archivos donde tengo cambios locales
  // sin enviar). El callout usa singular/plural según el contexto del archivo
  // actual, pero esto da el peso del "mismo problema" global.
  const totalDrafts = Object.keys(s.drafts).length;
  // Color por peer (para el avatar de la propuesta — el autor se ve con su
  // identidad visual, no como texto plano).
  const colorPorAutor = (autor: string): string | null => {
    const peer = Object.values(s.peers).find((p) => p.client_id === autor);
    if (peer) return peer.color;
    if (s.yo && s.yo.client_id === autor) return s.yo.color;
    return null;
  };

  // Si el ownership real ya muestra que el path es mío, salimos del estado
  // "reclamando" (era una bandera optimista; el server confirmó).
  useEffect(() => {
    if (claimingPath && claimingPath === path && esMio) {
      setClaimingPath(null);
    }
  }, [claimingPath, path, esMio]);

  function reclamarConFeedback() {
    if (!path) return;
    setClaimingPath(path);
    reclamar(path);
    setTimeout(() => {
      setClaimingPath((p) => (p === path ? null : p));
    }, 3000);
  }

  function enviarPropuesta() {
    if (!path) return;
    guardar(path);
  }

  function descartar() {
    if (!path) return;
    if (!confirm(t.ins_discard_confirm)) return;
    descartarDraft(path);
  }

  // ── HERO: la fila superior del inspector. Antes era "chip + nombre + flags";
  // ahora es un bloque diseñado: chip + nombre, una línea de estado que dice
  // EN PROSA qué es el archivo ahora mismo (modo de edición + dueño), un
  // subtítulo con la consecuencia (qué pasa al escribir), y a la derecha la
  // pulsación de "vivo" si hay peers. Es lo primero que el ojo lee — debe
  // contestar "¿qué soy aquí?" en 1 segundo.
  const modoLabel = !path
    ? "" // hero vacío
    : esMio
      ? t.ins_hero_mode_live
      : esDeOtro
        ? t.ins_hero_mode_propose
        : t.ins_hero_mode_free;
  const modoCls = !path ? "" : esMio ? "live" : esDeOtro ? "prop" : "free";
  const modoDesc = !path
    ? ""
    : esMio
      ? t.ins_hero_mode_live_desc
      : esDeOtro
        ? t.ins_hero_mode_propose_desc(nombreDe(due!))
        : t.ins_hero_mode_free_desc;

  // ── ATENCIÓN: lista priorizada de avisos accionables. La regla es
  // "qué deberías hacer ahora", no "qué información hay". Ordenamos por
  // urgencia: propuestas para mí > borrador mío > impacto alto > sin
  // marcar > sin dueño > otros presentes (info, no acción). Si la lista
  // queda vacía, mostramos "todo en orden" — no un vacío inquietante.
  type Atn = {
    tono: "alta" | "media" | "info" | "calma";
    ic: ReactNode; tit: string; sub: string;
  };
  const atenciones: Atn[] = useMemo(() => {
    if (!path) return [];
    const out: Atn[] = [];
    if (propsParaMi.length > 0) {
      out.push({
        tono: "alta",
        ic: <GitPullRequest size={14} />,
        tit: t.ins_attn_props_for_me(propsParaMi.length),
        sub: t.ins_attn_props_for_me_sub,
      });
    }
    if (tieneDraft) {
      out.push({
        tono: "media",
        ic: <Send size={14} />,
        tit: t.ins_attn_draft_ready,
        sub: t.ins_attn_draft_ready_sub,
      });
    }
    if (riesgo === "alta") {
      out.push({
        tono: "alta",
        ic: <AlertTriangle size={14} />,
        tit: t.ins_attn_impact_high,
        sub: t.ins_attn_impact_high_sub,
      });
    }
    if (sinMarcarLocal && !tieneDraft) {
      out.push({
        tono: "info",
        ic: <Bell size={14} />,
        tit: esDeOtro ? t.ins_attn_unmarked_other : t.ins_attn_unmarked_owner,
        sub: esDeOtro ? t.ins_attn_unmarked_other_sub : t.ins_attn_unmarked_owner_sub,
      });
    }
    if (!due && !sinMarcarLocal) {
      out.push({
        tono: "info",
        ic: <Hand size={14} />,
        tit: t.ins_attn_no_owner,
        sub: t.ins_attn_no_owner_sub,
      });
    }
    if (out.length === 0 && aqui.length > 0) {
      // Información: estás acompañado. Es bueno saberlo, pero no es alarma.
      const nombres = aqui.slice(0, 2).map((p) => p.name).join(", ")
        + (aqui.length > 2 ? "…" : "");
      out.push({
        tono: "info",
        ic: <Radio size={14} />,
        tit: t.ins_attn_other_present(nombres),
        sub: t.ins_attn_other_present_sub,
      });
    }
    return out;
  }, [path, propsParaMi.length, tieneDraft, riesgo, sinMarcarLocal, esDeOtro,
      due, aqui, t]);

  return (
    <aside
      className="inspector isla"
      style={width != null ? { width: width + "px" } : undefined}
    >
      <header className="in-head">
        <span className="in-eyebrow">{t.ins_title}</span>
        <button
          className="in-x"
          title={t.ins_hide}
          aria-label={t.ins_hide}
          onClick={onClose}
        >
          <PanelRightClose size={15} />
        </button>
      </header>

      {/* HERO: estado del archivo. Si no hay path abierto, mostramos un
          empty-state honesto que dice qué hace el panel. */}
      {path ? (
        <section className="in-hero">
          <div className="in-hero-top">
            <span className={"chip" + (c!.cls ? " " + c!.cls : "")}>{c!.txt}</span>
            <span className="in-hero-name" title={path}>
              {path.split("/").pop()}
            </span>
            {/* badge "vivo": pulsa SI hay peers en el archivo. Es el latido
                del producto — sin gente, no late. */}
            {aqui.length > 0 ? (
              <span className="in-hero-live" title={t.ed_team_tooltip}>
                <span className="in-hero-live-dot" />
                {t.ed_team_count(aqui.length)}
              </span>
            ) : (
              <span className="in-hero-live solo">{t.ed_team_alone}</span>
            )}
          </div>
          <div className="in-hero-row">
            <span className={"in-mode m-" + modoCls}>{modoLabel}</span>
            <span className="in-hero-sep">·</span>
            <span className="in-hero-owner">
              {esMio
                ? t.ins_hero_owner_mine
                : esDeOtro
                  ? t.ins_hero_owner_other(nombreDe(due!))
                  : t.ins_hero_owner_none}
            </span>
            {riesgo && (
              <span className={"in-hero-risk r-" + riesgo}>
                <AlertTriangle size={11} />
                {t.ins_risk[riesgo]}
              </span>
            )}
            {tieneDraft && (
              <span className="in-hero-tag warn-soft" title={t.ins_unmarked_title_other}>
                {t.ins_draft_marker}
              </span>
            )}
            {sinMarcarLocal && !tieneDraft && (
              <span
                className="in-hero-tag faint"
                title={esDeOtro
                  ? t.ins_unmarked_title_other
                  : t.ins_unmarked_title_owner}
              >
                {t.ins_unmarked}
              </span>
            )}
          </div>
          <p className="in-hero-desc">{modoDesc}</p>
        </section>
      ) : (
        <section className="in-hero in-hero-empty">
          <div className="in-hero-empty-ic">
            <Sparkles size={20} />
          </div>
          <div className="in-hero-empty-tit">{t.ins_no_file}</div>
          <p className="in-hero-empty-sub">{t.ins_no_file_sub}</p>
        </section>
      )}

      {/* ATENCIÓN: callout priorizado de qué hacer ahora. Si no hay nada,
          mostramos "todo en orden" — evita la sensación de "se me pasó algo".
          NO se muestra si no hay archivo (no hay nada que ordenar). */}
      {path && (
        <section className="in-atn">
          <h3 className="in-atn-h">
            {atenciones.length === 0 || atenciones[0].tono === "calma"
              ? (
                <>
                  <ShieldCheck size={11} />
                  {t.ins_attn_calm_title}
                </>
              )
              : (
                <>
                  <Bell size={11} />
                  {t.ins_attn_title}
                </>
              )}
          </h3>
          {atenciones.length === 0 ? (
            <AtnItem
              tono="calma"
              ic={<ShieldCheck size={14} />}
              tit={t.ins_attn_calm_title}
              sub={t.ins_attn_calm_sub}
            />
          ) : (
            atenciones.map((a, i) => (
              <AtnItem
                key={i}
                tono={a.tono}
                ic={a.ic}
                tit={a.tit}
                sub={a.sub}
              />
            ))
          )}
        </section>
      )}

      <div className="in-scroll">
        <Sec
          k="pres" ic={<Radio size={13} />} tit={t.ins_presence_title}
          n={aqui.length} colapsadas={colapsadas} toggle={toggle}
        >
          {aqui.length === 0 ? (
            <>
              <p className="in-empty">{t.ins_presence_solo_title}</p>
              <p className="in-explain">
                {t.ins_presence_solo_team(otrosEquipo.length)}
              </p>
              <p className="in-explain">{t.ins_presence_explain}</p>
            </>
          ) : (
            <>
              {aqui.map((p) => (
                <div className="inrow live" key={p.client_id}>
                  <span className="inav-wrap">
                    <span className="inav-pulse" style={{ background: p.color }} />
                    <span className="inav" style={{ background: p.color }}>
                      {inicial(p.name)}
                    </span>
                  </span>
                  <span className="inrow-n">{p.name}</span>
                  <span className="inrow-pill" title={t.ins_presence_live_dot}>
                    {t.ins_line} {p.line}
                  </span>
                </div>
              ))}
              <p className="in-explain">{t.ins_presence_explain}</p>
            </>
          )}
        </Sec>

        <Sec
          k="own" ic={<KeyRound size={13} />} tit={t.ins_ownership_title}
          colapsadas={colapsadas} toggle={toggle}
        >
          {!path ? (
            <p className="in-empty">{t.ins_pick_file}</p>
          ) : !due ? (
            <>
              <div className="inrow">
                <span className="in-flag faint">{t.ins_no_owner}</span>
                <button
                  className="in-act primario"
                  onClick={reclamarConFeedback}
                  disabled={claimingPath === path}
                  aria-busy={claimingPath === path}
                >
                  <Hand size={11} />
                  {claimingPath === path ? t.ins_claim_busy : t.ins_claim}
                </button>
              </div>
              <p className="in-explain">{t.ins_no_owner_sub}</p>
            </>
          ) : esMio ? (
            <>
              <div className="inrow">
                <span className="in-flag ok">
                  <ShieldCheck size={10} style={{ marginRight: 3, verticalAlign: -1 }} />
                  {t.ins_mine}
                </span>
                <span className="inrow-m">{t.ins_mine_sub}</span>
              </div>
            </>
          ) : (
            <div className="inrow col">
              <span className="in-flag warn">{t.ins_of(nombreDe(due))}</span>
              <span className="inrow-m">{t.ins_others_sub}</span>
              {tieneDraft && (
                <>
                  <p className="in-draft-note">
                    <span className="in-flag warn-soft">
                      {t.ins_draft_marker}
                    </span>
                  </p>
                  <div className="in-draft-acc">
                    <button
                      className="in-act primario"
                      onClick={enviarPropuesta}
                    >
                      <Send size={11} /> {t.ins_send_proposal}
                    </button>
                    <button
                      className="in-act secundario"
                      onClick={descartar}
                      title={t.ins_discard_confirm}
                    >
                      <Undo2 size={11} /> {t.ins_discard_draft}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </Sec>

        <Sec
          k="imp" ic={<Waypoints size={13} />} tit={t.ins_impact_title}
          n={impLo.length} tono={riesgo === "alta" ? "alarma" : undefined}
          colapsadas={colapsadas} toggle={toggle}
        >
          {impLo.length === 0 && impDesde.length === 0 ? (
            <>
              <p className="in-empty">{t.ins_no_impact}</p>
              <p className="in-explain">{t.ins_impact_explain}</p>
            </>
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
          k="prop" ic={<GitPullRequest size={13} />} tit={t.ins_proposals_title}
          n={nProps} colapsadas={colapsadas} toggle={toggle}
        >
          {props.length === 0 ? (
            <>
              <p className="in-empty">
                {t.ins_no_proposals}
                {propsMios.length > 0 && t.ins_waiting_others(propsMios.length)}
              </p>
              {path && (
                <p className="in-explain">
                  {tieneDraft
                    ? t.ins_no_proposals_sub_dirty
                    : esDeOtro
                      ? t.ins_no_proposals_sub_owner
                      : t.ins_no_proposals_sub_plain}
                </p>
              )}
            </>
          ) : (
            props.map((p) => (
              <PropCard
                key={p.id}
                p={p}
                mio={esMio}
                files={s.files}
                peerColor={colorPorAutor(p.author_id)}
              />
            ))
          )}
        </Sec>

        <Sec
          k="act" ic={<Activity size={13} />} tit={t.ins_activity_title}
          n={s.actividad.length} colapsadas={colapsadas} toggle={toggle}
        >
          {s.actividad.length === 0 ? (
            <>
              <p className="in-empty">{t.ins_no_activity}</p>
              <p className="in-explain">{t.ins_activity_explain}</p>
            </>
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

        {(impLo.length > 0 || totalDrafts > 0) && (
          <div className="in-foot">
            {impLo.length > 0 ? (
              <>
                <AlertTriangle size={12} />
                {t.ins_impact_count(impLo.length)}
              </>
            ) : (
              <>
                <Send size={12} />
                {totalDrafts} {totalDrafts === 1 ? t.stb_drafts : t.stb_drafts_pl}
              </>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
