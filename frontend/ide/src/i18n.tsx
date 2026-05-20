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

    // Login — errores de validación
    login_user_short: "Tu usuario es muy corto (mínimo 2 caracteres).",
    login_user_long: "Tu usuario es muy largo (máximo 32 caracteres).",
    login_user_charset: "Usa solo letras, números, '.', '_', '-', '@' o '+'.",
    login_user_starts: "El usuario debe empezar con letra o número.",
    login_user_reserved: "Ese prefijo está reservado — elige otro nombre.",

    // Hub
    hub_layer: "capa de coordinación · hub",
    hub_just_created: (n: string) => `equipo "${n}" creado — ya estás dentro como admin`,
    hub_invalid_name: "ese nombre no se puede usar",
    hub_create_busy: "creando…",
    hub_join_busy: "uniéndome…",
    hub_back_team: "volver al equipo",
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
    tb_invite_title: "abrir código de invitación",
    tb_clean: "limpio",
    tb_changes_title: "cambios en el árbol de trabajo",
    tb_branch_title: "rama actual",
    tb_inspector_show: "mostrar inspector",
    tb_inspector_hide: "ocultar inspector",
    tb_signout: "salir",
    tb_hub: "hub",
    tb_hub_title: "volver al hub (sin cerrar sesión)",

    // Invite modal
    inv_title: "invitar a este equipo",
    inv_intro: "Comparte este código con quien quieres invitar. Es de un solo uso: en cuanto alguien lo redime, generamos uno nuevo.",
    inv_copy: "copiar",
    inv_copied: "copiado",
    inv_copy_failed: "no se pudo copiar — selecciónalo a mano",
    inv_regenerate: "generar otro código",
    inv_close: "cerrar",
    inv_how_title: "cómo se usa",
    inv_how_1: "Tu invitado entra a la app y abre el hub.",
    inv_how_2: "Pega este código en \"unirme con un código\".",
    inv_how_3: "Aparece dentro de este equipo con el rol \"member\".",
    inv_limit_note: "Plan free: 5 devs por equipo. Premium: sin tope.",

    // Nuevo archivo modal
    nf_title: "nuevo archivo",
    nf_label: "Ruta y nombre",
    nf_placeholder: "ej: src/main.py",
    nf_hint: "Usa rutas relativas como src/main.py o tests/test_api.py. Los lenguajes con análisis profundo: .py · .ts · .tsx · .js · .jsx · .go · .rs",
    nf_create: "crear",
    nf_cancel: "cancelar",
    nf_err_exists: "ya existe un archivo con ese nombre",
    nf_err_vacio: "el nombre no puede estar vacío",
    nf_err_muy_largo: "el nombre es muy largo",
    nf_err_control: "el nombre tiene caracteres invisibles o de control",
    nf_err_prohibido: "no uses < > : \" | ? * \\ en nombres de archivo",
    nf_err_invisible: "el nombre tiene caracteres invisibles",
    nf_err_absoluto: "usa rutas relativas — no '/' al inicio ni unidades de Windows",
    nf_err_barra_invertida: "usa '/' como separador, no '\\'",
    nf_err_segmento_vacio: "evita '//' en la ruta",
    nf_err_punto: "evita '.' como nombre de carpeta",
    nf_err_doble_punto: "no se permite '..' en rutas",
    nf_err_segmento_largo: "alguna carpeta o archivo es muy largo",
    nf_err_profundidad: "demasiadas carpetas anidadas",
    nf_err_espacios_borde: "evita espacios al inicio o final de un nombre",
    nf_err_reservado_win: "ese nombre está reservado por Windows (CON, AUX, etc.)",

    // Confirmar salir
    leave_title: "tienes cambios sin enviar",
    leave_desc_one: "Hay 1 archivo con cambios locales que aún no se han enviado al equipo.",
    leave_desc_many: (n: number) =>
      `Hay ${n} archivos con cambios locales que aún no se han enviado al equipo.`,
    leave_keep: "seguir editando",
    leave_discard: "descartar y salir",

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
    ctx_prop_title: "lo que escribas queda local — Ctrl+S envía la propuesta al dueño",
    ctx_live_title: "editas directo: tus cambios se aplican en vivo",
    ctx_mode_prop: "modo propuesta",
    ctx_mode_live: "edición directa",
    ctx_prop_note: (name: string) =>
      "pulsa Ctrl+S para enviar la propuesta a " + name,
    ctx_alone: "solo aquí",
    ctx_reclaim: "reclamar este archivo",
    ctx_reclaim_title: "tomar la propiedad — podrás editar en vivo sin proponer",
    ctx_mine: "tuyo · lo editas directo",
    ctx_impact: (s: string) => "impacto · " + s,

    // Inspector
    ins_title: "inspector de coordinación",
    ins_no_file: "ningún archivo abierto",
    ins_no_file_sub: "Abre un archivo del explorador para ver presencia, ownership e impacto.",
    ins_unmarked: "sin marcar",
    ins_unmarked_title_owner: "tienes cambios sin marcar — Ctrl+S analiza el impacto",
    ins_unmarked_title_other: "tienes una propuesta sin enviar — Ctrl+S la envía al dueño",
    ins_risk: { alta: "riesgo alto", media: "riesgo medio", baja: "riesgo bajo" } as Record<string,string>,
    ins_presence_title: "presencia viva",
    ins_presence_explain: "Quién está ahora en este archivo y en qué línea. Si nadie más está, estás solo aquí.",
    ins_nobody: (n: number) => `Nadie más en este archivo. ${n} en el equipo.`,
    ins_line: "línea",
    ins_ownership_title: "ownership",
    ins_no_owner: "sin dueño",
    ins_no_owner_sub: "Nadie reclamó este archivo. Reclamarlo te deja editarlo en vivo.",
    ins_claim: "reclamar",
    ins_claim_busy: "reclamando…",
    ins_mine: "tuyo",
    ins_mine_sub: "lo editas directo — Ctrl+S analiza el impacto",
    ins_of: (name: string) => "de " + name,
    ins_others_sub: "lo que escribas queda local — Ctrl+S envía la propuesta",
    ins_draft_marker: "tienes una propuesta local sin enviar",
    ins_send_proposal: "enviar propuesta",
    ins_discard_draft: "descartar",
    ins_discard_confirm: "¿Descartar la propuesta local? Lo que escribiste no se enviará.",
    ins_impact_title: "impacto",
    ins_no_impact: "Sin impacto detectado sobre este archivo.",
    ins_impact_explain: "Orux detecta si algún cambio reciente afecta cómo se usa este archivo. Aparece cuando alguien marca su edición con Ctrl+S y el análisis encuentra usos.",
    ins_downstream: (n: number) => `Tus cambios aquí afectan a ${n} archivo(s) aguas abajo.`,
    ins_changed: "cambió",
    ins_proposals_title: "cambios propuestos",
    ins_no_proposals: "Nada propuesto sobre este archivo.",
    ins_no_proposals_sub_owner: "Cuando alguien edite este archivo sin ser dueño, su propuesta aparece aquí para aprobar o rechazar.",
    ins_no_proposals_sub_dirty: "Tienes cambios locales sin enviar — pulsa Ctrl+S para proponer.",
    ins_no_proposals_sub_plain: "Estás editando en vivo — cualquier cambio se aplica al instante.",
    ins_waiting_others: (n: number) => ` ${n} esperan tu revisión en otros.`,
    ins_proposes: "propone cambios",
    ins_waiting: "esperando tu aprobación",
    ins_in_review: "en revisión",
    ins_activity_title: "actividad",
    ins_no_activity: "Sin actividad de coordinación todavía.",
    ins_activity_explain: "Aquí aparecen los hechos de coordinación: quién entra y sale, propuestas, ownership y cambios en git.",
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
    stb_unmarked: "sin marcar",
    stb_unmarked_title: "archivos editados sin Ctrl+S (análisis pendiente)",
    stb_drafts: "borrador",
    stb_drafts_pl: "borradores",
    stb_drafts_title: "propuestas locales aún no enviadas — Ctrl+S las envía",
    stb_online_label: "en línea",
    stb_spaces: "4 esp · UTF-8",

    // Tabs
    tab_close: "cerrar archivo",
    tab_close_dirty: "este archivo tiene cambios sin marcar — pulsa Ctrl+S antes de cerrar",
    tab_own_mine: "tuyo · editas directo",
    tab_own_other: "tiene dueño — Ctrl+S envía tu propuesta",
    tab_dirty_owner: "cambios sin marcar — Ctrl+S analiza el impacto",
    tab_dirty_other: "propuesta sin enviar — Ctrl+S la envía al dueño",

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

    // Login — validation errors
    login_user_short: "Username is too short (minimum 2 characters).",
    login_user_long: "Username is too long (maximum 32 characters).",
    login_user_charset: "Use only letters, numbers, '.', '_', '-', '@' or '+'.",
    login_user_starts: "The username must start with a letter or number.",
    login_user_reserved: "That prefix is reserved — choose another name.",

    // Hub
    hub_layer: "coordination layer · hub",
    hub_just_created: (n: string) => `team "${n}" created — you're in as admin`,
    hub_invalid_name: "can't use that name",
    hub_create_busy: "creating…",
    hub_join_busy: "joining…",
    hub_back_team: "back to team",
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
    tb_invite_title: "open invitation code",
    tb_clean: "clean",
    tb_changes_title: "changes in working tree",
    tb_branch_title: "current branch",
    tb_inspector_show: "show inspector",
    tb_inspector_hide: "hide inspector",
    tb_signout: "sign out",
    tb_hub: "hub",
    tb_hub_title: "back to hub (keep session)",

    // Invite modal
    inv_title: "invite to this team",
    inv_intro: "Share this code with the person you want to invite. It's one-time-use: once someone redeems it, we generate a new one.",
    inv_copy: "copy",
    inv_copied: "copied",
    inv_copy_failed: "couldn't copy — select it manually",
    inv_regenerate: "generate another code",
    inv_close: "close",
    inv_how_title: "how it works",
    inv_how_1: "Your invitee opens the app and goes to the hub.",
    inv_how_2: "They paste this code into \"join with a code\".",
    inv_how_3: "They appear inside this team with the \"member\" role.",
    inv_limit_note: "Free plan: 5 devs per team. Premium: no cap.",

    // New file modal
    nf_title: "new file",
    nf_label: "Path and name",
    nf_placeholder: "e.g.: src/main.py",
    nf_hint: "Use relative paths like src/main.py or tests/test_api.py. Languages with deep analysis: .py · .ts · .tsx · .js · .jsx · .go · .rs",
    nf_create: "create",
    nf_cancel: "cancel",
    nf_err_exists: "a file with that name already exists",
    nf_err_vacio: "the name can't be empty",
    nf_err_muy_largo: "the name is too long",
    nf_err_control: "the name has invisible or control characters",
    nf_err_prohibido: "don't use < > : \" | ? * \\ in file names",
    nf_err_invisible: "the name has invisible characters",
    nf_err_absoluto: "use relative paths — no leading '/' or Windows drives",
    nf_err_barra_invertida: "use '/' as separator, not '\\'",
    nf_err_segmento_vacio: "avoid '//' in the path",
    nf_err_punto: "avoid '.' as a folder name",
    nf_err_doble_punto: "'..' is not allowed in paths",
    nf_err_segmento_largo: "a folder or file name is too long",
    nf_err_profundidad: "too many nested folders",
    nf_err_espacios_borde: "avoid leading/trailing spaces in a name",
    nf_err_reservado_win: "that name is reserved by Windows (CON, AUX, etc.)",

    // Leave confirm
    leave_title: "you have unsent changes",
    leave_desc_one: "There is 1 file with local changes not yet sent to the team.",
    leave_desc_many: (n: number) =>
      `There are ${n} files with local changes not yet sent to the team.`,
    leave_keep: "keep editing",
    leave_discard: "discard and leave",

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
    ctx_prop_title: "what you type stays local — Ctrl+S sends the proposal to the owner",
    ctx_live_title: "you edit directly: your changes apply live",
    ctx_mode_prop: "proposal mode",
    ctx_mode_live: "direct edit",
    ctx_prop_note: (name: string) =>
      "press Ctrl+S to send the proposal to " + name,
    ctx_alone: "only you here",
    ctx_reclaim: "claim this file",
    ctx_reclaim_title: "take ownership — you'll be able to edit live without proposing",
    ctx_mine: "yours · you edit directly",
    ctx_impact: (s: string) => "impact · " + s,

    // Inspector
    ins_title: "coordination inspector",
    ins_no_file: "no file open",
    ins_no_file_sub: "Open a file from the explorer to see presence, ownership, and impact.",
    ins_unmarked: "uncommitted",
    ins_unmarked_title_owner: "you have unmarked changes — Ctrl+S analyses the impact",
    ins_unmarked_title_other: "you have an unsent proposal — Ctrl+S sends it to the owner",
    ins_risk: { alta: "high risk", media: "medium risk", baja: "low risk" } as Record<string,string>,
    ins_presence_title: "live presence",
    ins_presence_explain: "Who is in this file right now, and on what line. If nobody else is here, you're alone in it.",
    ins_nobody: (n: number) => `Nobody else in this file. ${n} in the team.`,
    ins_line: "line",
    ins_ownership_title: "ownership",
    ins_no_owner: "no owner",
    ins_no_owner_sub: "Nobody claimed this file. Claiming lets you edit it live.",
    ins_claim: "claim",
    ins_claim_busy: "claiming…",
    ins_mine: "yours",
    ins_mine_sub: "you edit directly — Ctrl+S analyses the impact",
    ins_of: (name: string) => name + "'s",
    ins_others_sub: "what you type stays local — Ctrl+S sends the proposal",
    ins_draft_marker: "you have a local proposal not yet sent",
    ins_send_proposal: "send proposal",
    ins_discard_draft: "discard",
    ins_discard_confirm: "Discard the local proposal? What you wrote won't be sent.",
    ins_impact_title: "impact",
    ins_no_impact: "No impact detected on this file.",
    ins_impact_explain: "Orux detects whether a recent change affects how this file is used. It shows up when someone marks their edit with Ctrl+S and the analysis finds usages.",
    ins_downstream: (n: number) => `Your changes here affect ${n} file(s) downstream.`,
    ins_changed: "changed",
    ins_proposals_title: "proposed changes",
    ins_no_proposals: "Nothing proposed on this file.",
    ins_no_proposals_sub_owner: "When someone edits this file without owning it, their proposal shows up here to approve or reject.",
    ins_no_proposals_sub_dirty: "You have local changes not yet sent — press Ctrl+S to propose.",
    ins_no_proposals_sub_plain: "You're editing live — any change applies instantly.",
    ins_waiting_others: (n: number) => ` ${n} await your review in others.`,
    ins_proposes: "proposes changes",
    ins_waiting: "awaiting your approval",
    ins_in_review: "in review",
    ins_activity_title: "activity",
    ins_no_activity: "No coordination activity yet.",
    ins_activity_explain: "Coordination facts appear here: who joins and leaves, proposals, ownership and git changes.",
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
    stb_unmarked: "unmarked",
    stb_unmarked_title: "files edited without Ctrl+S (analysis pending)",
    stb_drafts: "draft",
    stb_drafts_pl: "drafts",
    stb_drafts_title: "local proposals not yet sent — Ctrl+S sends them",
    stb_online_label: "online",
    stb_spaces: "4 spc · UTF-8",

    // Tabs
    tab_close: "close file",
    tab_close_dirty: "this file has unmarked changes — press Ctrl+S before closing",
    tab_own_mine: "yours · you edit directly",
    tab_own_other: "has owner — Ctrl+S sends your proposal",
    tab_dirty_owner: "unmarked changes — Ctrl+S analyses the impact",
    tab_dirty_other: "unsent proposal — Ctrl+S sends it to the owner",

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
