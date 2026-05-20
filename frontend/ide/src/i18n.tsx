import {
  createContext, useContext, useState, useCallback,
  type ReactNode,
} from "react";

export type Lang = "es" | "en";
const KEY = "orux_lang";

function cargaLang(): Lang {
  try { return (localStorage.getItem(KEY) as Lang) || "es"; }
  catch { return "es"; }
}

/* ─── Traducciones ────────────────────────────────────────────────────────── */
export const T = {
  es: {
    lang_es: "Español",
    lang_en: "English",

    // Login — lado izquierdo (pitch)
    login_eyebrow: "capa de coordinación · en producción",
    login_feed_header: "coordinación en vivo",
    login_feed_approved: "propuesta aprobada",
    login_feed_impact: "impacto: 4 usos · avisado",
    login_sys_git_pre: "sobre",
    login_sys_pres_pre: "presencia",
    login_sys_pres_val: "por línea",
    login_sys_prev_pre: "se",
    login_sys_prev_val: "previene",
    login_sys_prev_post: ", no se fusiona",
    login_pitch_title1: "Tu equipo toca el código.",
    login_pitch_title2: "El sistema coordina el riesgo.",
    login_pitch_desc: "Misma seguridad que branches, PRs y reviews — sin la ceremonia. El sistema sabe sin que nadie le pregunte.",
    login_li1_b: "Presencia por línea.",
    login_li1: " Ves quién toca qué, en vivo.",
    login_li2_b: "Impacto con resolución real.",
    login_li2: " Avisa qué se rompe antes de que se rompa.",
    login_li3_b: "Sobre Git.",
    login_li3: " No lo reemplaza — ",
    login_li3_post: " basta.",
    // Login — lado derecho (consola)
    login_session_cue: "sesión cifrada · cuenta cerrada",
    login_desc: "Ingresa con tu usuario o crea uno nuevo. Sin cuenta no se ve el workspace.",
    login_user_label: "Usuario",
    login_user_placeholder: "tu usuario",
    login_pass_label: "Contraseña",
    login_pass_placeholder: "••••••••",
    login_verifying: "Verificando…",
    login_enter: "Entrar",
    login_register: "Crear cuenta",
    login_offline: "Sin conexión con el servidor — intenta de nuevo.",
    login_foot: "Tu sesión viaja cifrada. El workspace es un repo Git real — git clone basta.",
    login_sec1: "sesión HMAC",
    login_sec2: "cuenta cerrada",
    login_sec3: "sin telemetría",

    // Hub
    hub_layer: "coordination layer · hub",
    hub_stable: "identidad estable",
    hub_signout: "salir",
    hub_signout_title: "salir de la cuenta",
    hub_conn_active: "sesión activa",
    hub_conn_connecting: "conectando…",
    hub_conn_offline: "sin conexión",
    hub_teams_eyebrow: "tus equipos",
    hub_teams_empty: "aún vacío",
    hub_teams_hint: "elige uno para abrir su workspace",
    hub_open: "abrir →",
    hub_empty_title: "Aún no estás en ningún equipo.",
    hub_empty_desc: "Crea uno (quedas como admin) o únete con un código que te pasó un admin. Otro equipo no existe para ti hasta que estés dentro del tuyo.",
    hub_id_eyebrow: "tu identidad",
    hub_kpi_team: "equipo",
    hub_kpi_teams: "equipos",
    hub_kpi_admin: "como admin",
    hub_id_foot: "Tu identidad sobrevive a reconectar — el sistema sabe quién eres sin que lo digas.",
    hub_new_eyebrow: "crear o unirme",
    hub_create_label: "Crear un equipo",
    hub_create_placeholder: "nombre del equipo",
    hub_create_btn: "crear",
    hub_create_hint: "Quedas como admin del equipo que creas.",
    hub_join_label: "Unirme con un código",
    hub_join_placeholder: "código de invitación",
    hub_join_btn: "unirme",
    hub_join_hint: "El admin del equipo te pasó el código.",
    hub_sys_eyebrow: "sistema",
    hub_sys1_pre: "sesión",
    hub_sys1_label: "HMAC",
    hub_sys1_desc: "el token se firma localmente, no viaja en claro",
    hub_sys2_pre: "identidad",
    hub_sys2_label: "estable",
    hub_sys2_desc: "el mismo punto que te representa en todos tus equipos",
    hub_sys3_pre: "sin",
    hub_sys3_label: "telemetría",
    hub_sys3_desc: "orux no te observa; el workspace es un repo Git real",

    // TopBar
    tb_connecting: "conectando…",
    tb_connected: "conectado",
    tb_disconnected: "desconectado",
    tb_error: "error de conexión",
    tb_invite: "invitar",
    tb_invite_title: "código de un solo uso — compártelo",
    tb_clean: "limpio",
    tb_changes_title: "cambios en el árbol de trabajo",
    tb_branch_title: "rama actual",
    tb_inspector_show: "mostrar inspector",
    tb_inspector_hide: "ocultar inspector",
    tb_signout: "salir",

    // Rail
    rail_files_title: "explorador de archivos",
    rail_git_title: "control de versiones",
    rail_admin_title: "administración · ownership",

    // Sidebar — Archivos
    sb_explorer: "explorador",
    sb_new_file: "nuevo archivo",
    sb_new_file_prompt: "nombre del archivo (ej: src/main.py)",
    sb_empty_title: "Workspace vacío",
    sb_empty_sub: "Aún no hay archivos. Crea el primero con \"nuevo archivo\".",

    // Sidebar — Git
    sg_title: "control de versiones",
    sg_refresh_title: "releer estado de git",
    sg_refresh: "actualizar",
    sg_no_git_title: "Sin git",
    sg_no_git_sub: "Este workspace no es un repositorio git, o git no está disponible.",
    sg_clean: "limpio",
    sg_change: "cambio",
    sg_changes: "cambios",
    sg_commit_placeholder: "mensaje de commit…",
    sg_commit_btn: "commit",
    sg_remote_label: "remoto",
    sg_url_placeholder: "URL del repo (https://…)",
    sg_user_placeholder: "usuario",
    sg_token_placeholder: "token (no se guarda)",
    sg_branch_placeholder: "rama destino (vacío = rama del equipo + PR)",
    sg_clone_btn: "clonar",
    sg_push_btn: "push",
    sg_clone_confirm: "Clonar REEMPLAZA todo el workspace actual por ese repo. Lo no pusheado se pierde. ¿Seguro?",
    sg_pr_link: "abrir PR en GitHub",

    // FileTree
    ft_dirty: "cambios sin marcar",
    ft_proposals: (n: number) => n + " propuesta(s) pendiente(s)",
    ft_impact: (s: string) => "impacto · " + s,
    ft_mine: "tuyo",
    ft_owned: "tiene dueño",
    ft_presence_inside: "alguien editando adentro",
    ft_impact_inside: "impacto adentro",
    ft_delete_title: (path: string) => "eliminar " + path,
    ft_delete_confirm: (path: string) => "¿Eliminar " + path + "? No se puede deshacer.",

    // ContextBar
    ctx_prop_title: "tus cambios se proponen al dueño; no se aplican hasta que apruebe",
    ctx_live_title: "editas directo: tus cambios se aplican en vivo",
    ctx_mode_prop: "modo propuesta",
    ctx_mode_live: "edición directa",
    ctx_prop_note: (name: string) => "no se aplica hasta que " + name + " lo apruebe",
    ctx_alone: "solo aquí",
    ctx_reclaim: "reclamar este archivo",
    ctx_mine: "tuyo · lo editas directo",
    ctx_impact: (s: string) => "impacto · " + s,

    // Inspector
    ins_title: "inspector de coordinación",
    ins_no_file: "ningún archivo abierto",
    ins_unmarked: "sin marcar",
    ins_risk: { alta: "riesgo alto", media: "riesgo medio", baja: "riesgo bajo" } as Record<string,string>,
    ins_presence_title: "presencia viva",
    ins_nobody: (n: number) => `Nadie más en este archivo. ${n} en el equipo.`,
    ins_line: "línea",
    ins_ownership_title: "ownership",
    ins_no_owner: "sin dueño",
    ins_claim: "reclamar",
    ins_mine: "tuyo",
    ins_mine_sub: "lo editas directo",
    ins_of: (name: string) => "de " + name,
    ins_others_sub: "lo que escribas se le propone — no se aplica hasta que apruebe",
    ins_impact_title: "impacto",
    ins_no_impact: "Sin impacto detectado sobre este archivo.",
    ins_downstream: (n: number) => `Tus cambios aquí afectan a ${n} archivo(s) aguas abajo.`,
    ins_changed: "cambió",
    ins_proposals_title: "cambios propuestos",
    ins_no_proposals: "Nada propuesto sobre este archivo.",
    ins_waiting_others: (n: number) => ` ${n} esperan tu revisión en otros.`,
    ins_proposes: "propone cambios",
    ins_waiting: "esperando tu aprobación",
    ins_in_review: "en revisión",
    ins_activity_title: "actividad",
    ins_no_activity: "Sin actividad de coordinación todavía.",
    ins_impact_count: (n: number) => `${n} aviso(s) de impacto activos sobre este archivo`,
    ins_hide: "ocultar inspector",
    ins_now: "ahora",

    // Trays
    tr_proposals: "propuestas para ti",
    tr_proposes: "propone cambios a",
    tr_approve: "aprobar",
    tr_reject: "rechazar",
    tr_impact: "impacto en tus archivos",
    tr_changed: "cambió",
    tr_in: "en",
    tr_affects: "— afecta tu",
    tr_sev: { alta: "alta", media: "media", baja: "baja" } as Record<string,string>,
    tr_view: (path: string) => "ver " + path,
    tr_dismiss: "visto",

    // StatusBar
    stb_connecting: "conectando…",
    stb_online: "en línea",
    stb_offline: "sin conexión",
    stb_error: "error",
    stb_no_git: "sin git",
    stb_clean: "limpio",
    stb_change: "cambio",
    stb_changes: "cambios",
    stb_to_review: "para revisar",
    stb_to_review_title: "propuestas que esperan tu revisión",
    stb_online_label: "en línea",
    stb_spaces: "4 esp · UTF-8",

    // AdminModal
    am_title: "administración · ownership",
    am_close: "cerrar",
    am_owner_label: "dueño:",
    am_owner_empty: "— elige un usuario —",
    am_selected_one: "seleccionado",
    am_selected_many: "seleccionados",
    am_all: "todo",
    am_none: "nada",
    am_assign: (n: number) => "asignar a " + n,
    am_remove: (n: number) => "quitar dueño a " + n,
    am_no_files: "no hay archivos en el workspace.",
    am_hint_empty: "selecciona archivos o carpetas; elige un dueño; aplica al lote.",
    am_hint_assign: (user: string, n: number) =>
      `"asignar" pondrá a «${user}» como dueño de ${n} archivo(s). "quitar" los deja sin dueño.`,
    am_hint_nouser: (n: number) =>
      `${n} archivo(s) seleccionados — elige un usuario, o usa "quitar dueño".`,
  },

  en: {
    lang_es: "Español",
    lang_en: "English",

    // Login
    login_eyebrow: "coordination layer · in production",
    login_feed_header: "live coordination",
    login_feed_approved: "proposal approved",
    login_feed_impact: "impact: 4 uses · notified",
    login_sys_git_pre: "on",
    login_sys_pres_pre: "presence",
    login_sys_pres_val: "by line",
    login_sys_prev_pre: "it",
    login_sys_prev_val: "prevents",
    login_sys_prev_post: ", not merges",
    login_pitch_title1: "Your team touches the code.",
    login_pitch_title2: "The system coordinates the risk.",
    login_pitch_desc: "Same safety as branches, PRs and reviews — without the ceremony. The system knows without anyone asking.",
    login_li1_b: "Line-level presence.",
    login_li1: " See who's touching what, live.",
    login_li2_b: "Real-resolution impact.",
    login_li2: " Warns what will break before it does.",
    login_li3_b: "On Git.",
    login_li3: " Doesn't replace it — ",
    login_li3_post: " is enough.",
    login_session_cue: "encrypted session · closed account",
    login_desc: "Sign in with your username or create a new one. Without an account you can't see the workspace.",
    login_user_label: "Username",
    login_user_placeholder: "your username",
    login_pass_label: "Password",
    login_pass_placeholder: "••••••••",
    login_verifying: "Verifying…",
    login_enter: "Sign in",
    login_register: "Create account",
    login_offline: "No connection to server — try again.",
    login_foot: "Your session travels encrypted. The workspace is a real Git repo — git clone is enough.",
    login_sec1: "HMAC session",
    login_sec2: "closed account",
    login_sec3: "no telemetry",

    // Hub
    hub_layer: "coordination layer · hub",
    hub_stable: "stable identity",
    hub_signout: "sign out",
    hub_signout_title: "sign out of account",
    hub_conn_active: "active session",
    hub_conn_connecting: "connecting…",
    hub_conn_offline: "no connection",
    hub_teams_eyebrow: "your teams",
    hub_teams_empty: "still empty",
    hub_teams_hint: "choose one to open its workspace",
    hub_open: "open →",
    hub_empty_title: "You're not in any team yet.",
    hub_empty_desc: "Create one (you become admin) or join with a code from an admin. Another team doesn't exist for you until you're inside yours.",
    hub_id_eyebrow: "your identity",
    hub_kpi_team: "team",
    hub_kpi_teams: "teams",
    hub_kpi_admin: "as admin",
    hub_id_foot: "Your identity survives reconnects — the system knows who you are without you saying.",
    hub_new_eyebrow: "create or join",
    hub_create_label: "Create a team",
    hub_create_placeholder: "team name",
    hub_create_btn: "create",
    hub_create_hint: "You become admin of the team you create.",
    hub_join_label: "Join with a code",
    hub_join_placeholder: "invitation code",
    hub_join_btn: "join",
    hub_join_hint: "The team admin gave you the code.",
    hub_sys_eyebrow: "system",
    hub_sys1_pre: "HMAC",
    hub_sys1_label: "session",
    hub_sys1_desc: "the token is signed locally, doesn't travel in cleartext",
    hub_sys2_pre: "identity",
    hub_sys2_label: "stable",
    hub_sys2_desc: "the same point representing you across all your teams",
    hub_sys3_pre: "no",
    hub_sys3_label: "telemetry",
    hub_sys3_desc: "orux doesn't observe you; the workspace is a real Git repo",

    // TopBar
    tb_connecting: "connecting…",
    tb_connected: "connected",
    tb_disconnected: "disconnected",
    tb_error: "connection error",
    tb_invite: "invite",
    tb_invite_title: "one-time code — share it",
    tb_clean: "clean",
    tb_changes_title: "changes in working tree",
    tb_branch_title: "current branch",
    tb_inspector_show: "show inspector",
    tb_inspector_hide: "hide inspector",
    tb_signout: "sign out",

    // Rail
    rail_files_title: "file explorer",
    rail_git_title: "version control",
    rail_admin_title: "administration · ownership",

    // Sidebar — Files
    sb_explorer: "explorer",
    sb_new_file: "new file",
    sb_new_file_prompt: "file name (e.g.: src/main.py)",
    sb_empty_title: "Empty workspace",
    sb_empty_sub: "No files yet. Create the first one with \"new file\".",

    // Sidebar — Git
    sg_title: "version control",
    sg_refresh_title: "re-read git status",
    sg_refresh: "refresh",
    sg_no_git_title: "No git",
    sg_no_git_sub: "This workspace is not a git repository, or git is not available.",
    sg_clean: "clean",
    sg_change: "change",
    sg_changes: "changes",
    sg_commit_placeholder: "commit message…",
    sg_commit_btn: "commit",
    sg_remote_label: "remote",
    sg_url_placeholder: "Repo URL (https://…)",
    sg_user_placeholder: "username",
    sg_token_placeholder: "token (not saved)",
    sg_branch_placeholder: "target branch (empty = team branch + PR)",
    sg_clone_btn: "clone",
    sg_push_btn: "push",
    sg_clone_confirm: "Clone REPLACES the entire current workspace with that repo. Unpushed changes will be lost. Are you sure?",
    sg_pr_link: "open PR on GitHub",

    // FileTree
    ft_dirty: "uncommitted changes",
    ft_proposals: (n: number) => n + " pending proposal(s)",
    ft_impact: (s: string) => "impact · " + s,
    ft_mine: "yours",
    ft_owned: "has owner",
    ft_presence_inside: "someone editing inside",
    ft_impact_inside: "impact inside",
    ft_delete_title: (path: string) => "delete " + path,
    ft_delete_confirm: (path: string) => "Delete " + path + "? This cannot be undone.",

    // ContextBar
    ctx_prop_title: "your changes are proposed to the owner; not applied until approved",
    ctx_live_title: "you edit directly: your changes apply live",
    ctx_mode_prop: "proposal mode",
    ctx_mode_live: "direct edit",
    ctx_prop_note: (name: string) => "not applied until " + name + " approves",
    ctx_alone: "only you here",
    ctx_reclaim: "claim this file",
    ctx_mine: "yours · you edit directly",
    ctx_impact: (s: string) => "impact · " + s,

    // Inspector
    ins_title: "coordination inspector",
    ins_no_file: "no file open",
    ins_unmarked: "uncommitted",
    ins_risk: { alta: "high risk", media: "medium risk", baja: "low risk" } as Record<string,string>,
    ins_presence_title: "live presence",
    ins_nobody: (n: number) => `Nobody else in this file. ${n} in the team.`,
    ins_line: "line",
    ins_ownership_title: "ownership",
    ins_no_owner: "no owner",
    ins_claim: "claim",
    ins_mine: "yours",
    ins_mine_sub: "you edit directly",
    ins_of: (name: string) => name + "'s",
    ins_others_sub: "what you type is proposed to them — not applied until they approve",
    ins_impact_title: "impact",
    ins_no_impact: "No impact detected on this file.",
    ins_downstream: (n: number) => `Your changes here affect ${n} file(s) downstream.`,
    ins_changed: "changed",
    ins_proposals_title: "proposed changes",
    ins_no_proposals: "Nothing proposed on this file.",
    ins_waiting_others: (n: number) => ` ${n} await your review in others.`,
    ins_proposes: "proposes changes",
    ins_waiting: "awaiting your approval",
    ins_in_review: "in review",
    ins_activity_title: "activity",
    ins_no_activity: "No coordination activity yet.",
    ins_impact_count: (n: number) => `${n} active impact notice(s) on this file`,
    ins_hide: "hide inspector",
    ins_now: "now",

    // Trays
    tr_proposals: "proposals for you",
    tr_proposes: "proposes changes to",
    tr_approve: "approve",
    tr_reject: "reject",
    tr_impact: "impact on your files",
    tr_changed: "changed",
    tr_in: "in",
    tr_affects: "— affects your",
    tr_sev: { alta: "high", media: "medium", baja: "low" } as Record<string,string>,
    tr_view: (path: string) => "view " + path,
    tr_dismiss: "dismiss",

    // StatusBar
    stb_connecting: "connecting…",
    stb_online: "online",
    stb_offline: "offline",
    stb_error: "error",
    stb_no_git: "no git",
    stb_clean: "clean",
    stb_change: "change",
    stb_changes: "changes",
    stb_to_review: "to review",
    stb_to_review_title: "proposals awaiting your review",
    stb_online_label: "online",
    stb_spaces: "4 spc · UTF-8",

    // AdminModal
    am_title: "administration · ownership",
    am_close: "close",
    am_owner_label: "owner:",
    am_owner_empty: "— choose a user —",
    am_selected_one: "selected",
    am_selected_many: "selected",
    am_all: "all",
    am_none: "none",
    am_assign: (n: number) => "assign to " + n,
    am_remove: (n: number) => "remove owner from " + n,
    am_no_files: "no files in the workspace.",
    am_hint_empty: "select files or folders; choose an owner; apply to batch.",
    am_hint_assign: (user: string, n: number) =>
      `"assign" will set «${user}» as owner of ${n} file(s). "remove" leaves them without owner.`,
    am_hint_nouser: (n: number) =>
      `${n} file(s) selected — choose a user, or use "remove owner".`,
  },
} as const;

export type Traducciones = typeof T["es"];

/* ─── Contexto ────────────────────────────────────────────────────────────── */
interface I18nCtx {
  lang: Lang;
  t: Traducciones;
  setLang: (l: Lang) => void;
}

const Ctx = createContext<I18nCtx>({
  lang: "es",
  t: T.es,
  setLang: () => {},
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(cargaLang);

  const setLang = useCallback((l: Lang) => {
    try { localStorage.setItem(KEY, l); } catch {}
    setLangState(l);
  }, []);

  return (
    <Ctx.Provider value={{ lang, t: T[lang], setLang }}>
      {children}
    </Ctx.Provider>
  );
}

export function useI18n() { return useContext(Ctx); }

/* Selector de idioma reutilizable — pill compacta con las dos opciones. */
export function LangToggle({ className = "" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <span className={"lang-toggle " + className}>
      <button
        className={lang === "es" ? "lt-active" : ""}
        onClick={() => setLang("es")}
      >ES</button>
      <button
        className={lang === "en" ? "lt-active" : ""}
        onClick={() => setLang("en")}
      >EN</button>
    </span>
  );
}
