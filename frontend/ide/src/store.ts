// Estado global + conexión WebSocket. Es la mitad del contrato del
// protocolo: habla EXACTO el mismo JSON que el server Python (que no se
// tocó). Portado 1:1 de la lógica vanilla; React sólo consume este store
// vía useSyncExternalStore. No hay framework de estado: un objeto + set de
// listeners. La app es chica; re-render global es aceptable y simple.

export interface Peer {
  client_id: string; name: string; color: string;
  path: string | null; line: number;
}
export interface Proposal {
  id: string; path: string; author_id: string;
  author_name: string; content: string;
  // Capa 29 (UX): momento en que el cliente recibió la propuesta. NO viene
  // del server (el protocolo no lo incluye); se setea al recibir el mensaje
  // para que el inspector pueda mostrar "hace Xm" sin mentir — representa
  // "cuando me llegó", no "cuando se creó en el server". Si la misma
  // propuesta se re-envía, conservamos el seen_at del primer arribo.
  seen_at?: number;
}
export interface Impact {
  source_path: string; author_name: string;
  affected_path: string; symbols: string[]; motivos: string[];
  // Capa 24: cadena de hops del impacto transitivo (premium). Vacío =
  // impacto directo (free). El server ya manda [] por defecto.
  cadena?: string[];
  // Capa 24d: severidad por símbolo (1:1 con symbols). Vacío en mensajes
  // viejos -> el cliente asume "media".
  severidades?: string[];
  // Capa 35 (anti-degradación-silenciosa): el analizador que produjo este
  // impacto en el server. "lsp" | "ast" | "treesitter" | "regex". Vacío =
  // server viejo (no inventamos profundidad — no se muestra chip). Si llega
  // algo distinto de "lsp", el Inspector muestra un chip discreto para que
  // el dueño sepa que el fan-out fue token-scan, no resolución real.
  analizador?: string;
}
export interface GitStatus {
  available: boolean; branch: string; changes: number; commits: string[];
}
// Capa 26 (rediseño enterprise): bitácora de coordinación SOLO en el
// cliente. No es protocolo nuevo — se deriva de los mensajes que ya
// llegan. Es el "feed de actividad" del inspector: hechos discretos de
// coordinación (entró/salió, propuesta, impacto, ownership, git), NO el
// stream de tecleo (eso ya lo dicen la presencia y el dirty). Honesto:
// el `update` del server no trae autor, así que NO inventamos quién
// editó — solo registramos lo que sí tiene actor real.
export type ActKind =
  | "join" | "leave" | "propuesta" | "impacto"
  | "ownership" | "git" | "delete" | "workspace";
export interface ActItem {
  id: number; ts: number; kind: ActKind;
  actor: string; path: string | null; text: string;
}
export interface State {
  conn: "conectando" | "conectado" | "desconectado" | "error";
  authed: boolean;
  // Capa 35: el server manda `code` (label estable) Y `reason` (texto
  // legible). Guardamos ambos para que Login.tsx decida si traduce el code
  // o cae al reason crudo (clientes viejos sin code, casos sin label).
  loginError: { code: string; reason: string } | null;
  yo: { client_id: string; name: string; color: string } | null;
  files: Record<string, string>;
  currentPath: string | null;
  owners: Record<string, string>;
  peers: Record<string, Peer>;
  proposals: Record<string, Proposal>;
  impacts: Record<string, Impact>;
  // Capa 19: archivos con cambios desde el último checkpoint (Ctrl+S). Es
  // el dot de "sin marcar": dispara el reflejo de guardar y es verdad (hay
  // cambios sin analizar). NO es "sin guardar" (el contenido ya viaja en
  // vivo para el dueño); para un no-dueño con draft, el Ctrl+S es lo que
  // dispara la propuesta al dueño (ver `drafts` abajo).
  dirty: Record<string, boolean>;
  // Capa 28: drafts locales del NO-DUEÑO. Mientras tipeás en un archivo
  // ajeno, lo escrito queda acá (no viaja al server hasta Ctrl+S). El
  // editor lee `drafts[path] ?? files[path]`; los demás clientes (incluido
  // el dueño) NO ven nada hasta que confirmás con Ctrl+S y se crea la
  // propuesta. Un `update` entrante (aprobación, edición del dueño, etc.)
  // limpia el draft: la verdad del server gana.
  drafts: Record<string, string>;
  git: GitStatus | null;
  gitResult: { ok: boolean; detail: string; pr_url: string } | null;
  esAdmin: boolean;
  usuarios: string[];
  proyecto: string;
  // Capa 15: gate de equipo. "auth" = sin loguear; "lobby" = logueado pero
  // sin equipo (elegir/crear/unirse); "team" = dentro de un equipo (IDE).
  fase: "auth" | "lobby" | "team";
  // Capa 30: `plan` ('free' | 'premium') viaja en cada equipo del lobby
  // (lo agrega `equipos_de` en el server). El Hub lo usa para el badge de
  // plan y para mostrar el botón "Mejorar a Premium". Opcional por
  // compat: un server viejo no lo manda y el Hub asume 'free'.
  // Capa 31: `miembros` = cantidad de miembros del equipo. El cobro
  // premium es por asiento (un asiento por miembro), así que el Hub lo
  // muestra. Opcional por la misma razón de compat.
  equipos: {
    id: string; nombre: string; rol: string;
    plan?: string; miembros?: number;
  }[];
  equipoError: string;
  equipo: { id: string; nombre: string; rol: string } | null;
  inviteCode: string;  // último código emitido por el admin (para compartir)
  // Capa 26: bitácora de sesión (más reciente primero, acotada) + caret
  // del archivo abierto (línea/columna 1-based). El caret NO viaja al
  // server (eso ya lo hace `presence` con la línea); vive acá solo para
  // que la status bar y el inspector lo muestren.
  actividad: ActItem[];
  caret: { line: number; col: number };
  // Demo cinematográfico para la landing: si es true, el IDE corre en modo
  // "kiosk" — sin conexión WS, con datos fake del mock loop y un overlay que
  // bloquea cualquier interacción del visitante. Se activa con `?demo=1` y
  // se inyecta desde main.tsx vía __setForTutorial.
  demoMode: boolean;
  // Sub-modo del demo: si es true, el iframe está montado como PIP (picture-
  // in-picture) en el hero del landing, embebido chico junto al iframe
  // principal. A ese tamaño el DemoStepper y DemoCursor son ruido visual
  // (texto a ~3px, cursor sobredimensionado), así que el DemoLoop los
  // suprime. El resto del demo (peer cursors, halos, toasts) sigue
  // mostrándose porque a baja escala todavía comunica "hay actividad".
  demoPip: boolean;
}

const inicial: State = {
  conn: "conectando", authed: false, loginError: null, yo: null,
  files: {}, currentPath: null, owners: {}, peers: {}, proposals: {},
  impacts: {}, dirty: {}, drafts: {}, git: null, gitResult: null, esAdmin: false,
  usuarios: [],
  proyecto:
    location.hostname && location.hostname !== "localhost"
      ? location.hostname : "local",
  fase: "auth", equipos: [], equipoError: "", equipo: null, inviteCode: "",
  actividad: [], caret: { line: 1, col: 1 }, demoMode: false, demoPip: false,
};

let state: State = inicial;
const listeners = new Set<() => void>();
function set(patch: Partial<State>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}
export function subscribe(l: () => void) {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
export function getState() { return state; }

// Setter expuesto para usos que necesitan inyectar estado fake en el cliente
// sin tocar el servidor — saltea protocolo y broadcast. Usos legítimos:
//
//   1) Tutorial guiado del onboarding (src/tutorial/mock.ts), que solo arranca
//      con `files` vacío (workspace virgen) y limpia al saltar/terminar.
//   2) Modo demo cinematográfico (?demo=1, ver main.tsx + tutorial/DemoLoop):
//      sin conexión WS, mocks en bucle infinito, overlay anti-interacción.
//
// NO usar para otros flujos: cualquier estado inyectado bypasea protocol/
// broadcast y los otros clientes nunca van a verlo.
export function __setForTutorial(patch: Partial<State>): void { set(patch); }

// ── Toast emitter (cliente puro, fuera del estado React) ────────────────
// Pequeño bus pub/sub para que acciones del store (guardar, clonar, borrar)
// puedan pedir feedback visual sin acoplarse a React. `App.tsx` se suscribe
// una sola vez y renderiza la última notificación. Tres tonos:
//   ok    → confirmación de acción exitosa (Ctrl+S, propuesta enviada)
//   warn  → advertencia neutra (no hay drafts para guardar)
//   bad   → falló algo (error de copia, push rechazado, etc.)
// El emisor mantiene la i18n FUERA del store: el caller pasa el texto ya
// traducido. Eso es a propósito — el store no debe conocer idiomas.
export type ToastTone = "ok" | "warn" | "bad";
export interface Toast { id: number; text: string; tone: ToastTone; ts: number }
let toastSeq = 0;
const toastListeners = new Set<(t: Toast) => void>();
export function subscribeToasts(cb: (t: Toast) => void): () => void {
  toastListeners.add(cb);
  return () => { toastListeners.delete(cb); };
}
export function emitToast(text: string, tone: ToastTone = "ok"): void {
  const t: Toast = { id: ++toastSeq, text, tone, ts: Date.now() };
  toastListeners.forEach((l) => l(t));
}

// --- Capa 26: bitácora de coordinación (cliente puro) ---
let actSeq = 0;
const ACT_CAP = 80;          // techo: es un feed, no un historial
const ACT_COALESCE = 9000;   // mismo hecho repetido < 9s = se refresca, no se duplica
function act(kind: ActKind, actor: string, text: string, path: string | null = null) {
  const ahora = Date.now();
  const prev = state.actividad[0];
  // Coalescer ruido: el MISMO hecho (tipo+actor+path) muy seguido sube
  // su timestamp en vez de apilar filas idénticas (p.ej. impacto que se
  // recalcula al tipear). El feed se mantiene legible.
  if (prev && prev.kind === kind && prev.actor === actor && prev.path === path
      && ahora - prev.ts < ACT_COALESCE) {
    const [, ...resto] = state.actividad;
    set({ actividad: [{ ...prev, ts: ahora }, ...resto] });
    return;
  }
  const item: ActItem = { id: ++actSeq, ts: ahora, kind, actor, path, text };
  set({ actividad: [item, ...state.actividad].slice(0, ACT_CAP) });
}

// --- Capa 26: selectores derivados (reusados por FileTree e Inspector;
// una sola fuente de verdad para "¿este archivo tiene señal?") ---
export function impactosQueAfectan(path: string): Impact[] {
  return Object.values(state.impacts).filter((i) => i.affected_path === path);
}
export function propuestasDe(path: string): Proposal[] {
  return Object.values(state.proposals).filter((p) => p.path === path);
}
const _SEVR: Record<string, number> = { alta: 3, media: 2, baja: 1 };
// Severidad máxima de una lista de impactos -> etiqueta o null.
export function severidadMax(ims: Impact[]): "alta" | "media" | "baja" | null {
  let mx = 0;
  for (const im of ims)
    for (let i = 0; i < im.symbols.length; i++) {
      const s = (im.severidades && im.severidades[i]) || "media";
      mx = Math.max(mx, _SEVR[s] || 2);
    }
  return mx >= 3 ? "alta" : mx === 2 ? "media" : mx === 1 ? "baja" : null;
}
// Presentes (otros) en un archivo concreto, para badges del árbol/inspector.
export function presentesEn(path: string): Peer[] {
  return Object.values(state.peers).filter(
    (p) => p.path === path && (!state.yo || p.client_id !== state.yo.client_id),
  );
}
export function setCaret(line: number, col: number) {
  if (state.caret.line === line && state.caret.col === col) return;
  set({ caret: { line, col } });
}

// URL del WS: dev (Vite 5173 / localhost / file) -> server suelto en 8765;
// deploy -> mismo host, wss, ruta /ws (Caddy proxya). Igual criterio que
// el cliente vanilla.
function wsUrl(): string {
  const dev =
    location.protocol === "file:" ||
    location.port === "5173" ||
    location.port === "5500";
  if (dev) return "ws://localhost:8765";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return proto + "//" + location.host + "/ws";
}

let ws: WebSocket | null = null;
let lastPresence = { path: "", line: 0 };

// Reconnect automático: si la red parpadea (wifi, suspender el laptop, server
// reiniciándose) el cliente intenta solo, con backoff exponencial. Sin esto el
// usuario veía "desconectado" y quedaba paralizado — el bug más caro porque
// cualquier hiccup = abandono. Empieza en 500 ms (hiccup chiquito, ni se nota)
// y duplica hasta 30 s (techo: no martillar al server eternamente). El
// `onopen` exitoso resetea el contador. `cierreIntencional` evita
// reconectar cuando `salirEquipo()` cierra el WS a propósito para volver al
// lobby —ese flujo ya llama a `connect()` explícito acto seguido.
const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 30_000;
let reconnectTimer: number | null = null;
let reconnectIntento = 0;
let cierreIntencional = false;

function cancelarReconnect() {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function programarReconnect() {
  cancelarReconnect();
  const delay = Math.min(
    RECONNECT_BASE_MS * 2 ** reconnectIntento, RECONNECT_MAX_MS,
  );
  reconnectIntento += 1;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function send(obj: unknown) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// Mismo color determinístico que el server (state/presence.py::color_de):
// SHA-256(username) -> int(hex, 16) % len(PALETA). El mod sobre el entero
// completo se mantiene char a char en hex porque (m*16 + d) % n preserva
// el resultado. Web Crypto es async, así que el Hub muestra el accent por
// defecto un tic hasta que el color cae; el welcome del equipo igual lo
// sobreescribe luego.
const PALETA = ["#e0607a", "#5fa8e0", "#8de0a8", "#e0c46a", "#b98de0", "#e09a5f"];
async function colorDeUsuario(username: string): Promise<string> {
  const data = new TextEncoder().encode(username);
  const buf = await crypto.subtle.digest("SHA-256", data);
  const hex = Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  let mod = 0;
  for (const c of hex) mod = (mod * 16 + parseInt(c, 16)) % PALETA.length;
  return PALETA[mod];
}
function sembrarYo(username: string) {
  // Identidad mínima inmediata (nombre = usuario, color tentativo) para que
  // el Hub muestre algo apenas autentica. El color real cae cuando termina
  // el hash; el welcome del equipo después lo confirma con el del server.
  set({ yo: { client_id: username, name: nombreVisible(username), color: "" } });
  colorDeUsuario(username).then((color) => {
    const yo = state.yo;
    if (yo && yo.client_id === username) set({ yo: { ...yo, color } });
  }).catch(() => { /* sin crypto.subtle: el welcome traerá el color */ });
}

function onMessage(raw: string) {
  const m = JSON.parse(raw);
  switch (m.type) {
    case "auth_ok":
      localStorage.setItem("orux_session", m.token);
      localStorage.setItem("orux_user", m.username);
      // Autenticado pero todavía sin equipo: el server manda `lobby` a
      // continuación. La app sigue cerrada un escalón más.
      // Sembramos `yo` con la identidad del usuario para que el Hub
      // (que se renderiza antes del welcome de equipo) muestre nombre y
      // color en vez de "—" / "?". El welcome de cada equipo después
      // confirma color y client_id con la fuente autoritativa.
      sembrarYo(m.username);
      set({ authed: true, loginError: null, fase: "lobby" });
      break;
    case "auth_error":
      localStorage.removeItem("orux_session");
      set({
        authed: false,
        // Capa 35: code puede no venir (server viejo) — lo normalizamos a
        // "" para que el componente no tenga que chequear undefined.
        loginError: { code: m.code || "", reason: m.reason },
        fase: "auth",
      });
      break;
    case "lobby": {
      set({ fase: "lobby", equipos: m.teams || [], equipoError: m.error || "" });
      // Invitación por link: si llegamos con ?invite=<code> (guardado en
      // sessionStorage), lo canjeamos ahora — ya estamos autenticados y en
      // el lobby. Se consume una sola vez: lo borramos ANTES de mandar el
      // redeem, así un `lobby` posterior (código inválido) no reintenta. Si
      // el código es válido el server entra directo al equipo; si no,
      // reenvía `lobby` con el error y se ve el Hub normal.
      let invite: string | null = null;
      try { invite = sessionStorage.getItem("orux_invite"); } catch { /* sin storage */ }
      if (invite) {
        try { sessionStorage.removeItem("orux_invite"); } catch { /* idem */ }
        send({ type: "redeem_invite", code: invite });
      }
      break;
    }
    case "team_ready":
      // Entramos a un equipo: lo que sigue (init/welcome/...) es de ÉL.
      set({
        fase: "team",
        equipo: { id: m.team_id, nombre: m.nombre, rol: m.rol },
        equipoError: "",
        // estado de equipo anterior, limpio (por si se cambió de equipo).
        files: {}, owners: {}, peers: {}, proposals: {}, impacts: {},
        dirty: {}, drafts: {}, currentPath: null, inviteCode: "",
        // Equipo nuevo = sesión nueva: la bitácora arranca limpia.
        actividad: [], caret: { line: 1, col: 1 },
      });
      break;
    case "invite_created":
      set({ inviteCode: m.code });
      break;
    case "init": {
      const files: Record<string, string> = { ...m.files };
      const primero = Object.keys(files).sort()[0] ?? null;
      set({
        files,
        currentPath: primero,
        // ownership/propuestas viejas no aplican tras un re-init (clone).
        proposals: {},
        // Capa 19: el workspace es otro (clone) -> el server re-baseó;
        // acá también arrancamos sin "sin marcar".
        dirty: {},
        // Capa 28: el workspace es otro -> cualquier draft de no-dueño
        // del workspace anterior es basura. Se descarta.
        drafts: {},
      });
      if (primero) presence(primero, 1);
      act("workspace", "", `workspace cargado · ${Object.keys(files).length} archivos`);
      break;
    }
    case "update": {
      if (typeof m.path !== "string" || !m.path) break;
      // Cambió el contenido (lo tocó alguien): hay cambios sin checkpoint.
      // El checkpoint es global por archivo en el server, así que el dot
      // aplica sin importar quién tipeó (cualquiera puede Ctrl+S).
      // Capa 28: un update entrante = el server fija una nueva verdad
      // (aprobación de mi propuesta, edición del dueño, rechazo que
      // revierte). Cualquier draft local sobre este path queda obsoleto:
      // se descarta. La verdad gana; si quería seguir proponiendo, vuelvo
      // a escribir.
      const drafts = { ...state.drafts };
      delete drafts[m.path];
      set({
        files: { ...state.files, [m.path]: m.content },
        dirty: { ...state.dirty, [m.path]: true },
        drafts,
      });
      break;
    }
    case "delete": {
      if (!(m.path in state.files)) break;
      const files = { ...state.files };
      delete files[m.path];
      const dirty = { ...state.dirty };
      delete dirty[m.path];
      const drafts = { ...state.drafts };
      delete drafts[m.path];
      let cur = state.currentPath;
      if (cur === m.path) cur = Object.keys(files).sort()[0] ?? null;
      act("delete", "", "se eliminó", m.path);
      // Toast SOLO al autor que pidió el borrado. Si otro miembro del
      // equipo borró, no spameamos a todos con "✓ borrado X" — la
      // actividad del Inspector ya lo registra. El texto viene
      // pre-traducido del caller (FileTree.tsx).
      const toastOk = _deletePedidos.get(m.path);
      if (toastOk !== undefined) {
        _deletePedidos.delete(m.path);
        if (toastOk) emitToast(toastOk, "ok");
      }
      set({ files, dirty, drafts, currentPath: cur });
      break;
    }
    case "welcome": {
      // El server manda la identidad cruda (gh:<login> para usuarios de
      // GitHub); la limpiamos para mostrar. client_id queda crudo.
      const peers: Record<string, Peer> = {};
      for (const p of m.peers)
        peers[p.client_id] = { ...p, name: nombreVisible(p.name) };
      set({ yo: { ...m.you, name: nombreVisible(m.you.name) }, peers });
      break;
    }
    case "presence":
      // Llega presencia de alguien que no teníamos (y no soy yo) = entró
      // al equipo. Los movimientos de línea NO se registran (sería ruido;
      // eso ya se ve en vivo en el editor y el árbol).
      if (
        !(m.client_id in state.peers) &&
        (!state.yo || m.client_id !== state.yo.client_id)
      ) {
        act("join", nombreVisible(m.name), "se conectó al equipo");
      }
      set({
        peers: {
          ...state.peers,
          [m.client_id]: {
            client_id: m.client_id, name: nombreVisible(m.name), color: m.color,
            path: m.path, line: m.line,
          },
        },
      });
      break;
    case "leave": {
      const peers = { ...state.peers };
      const ido = peers[m.client_id];
      delete peers[m.client_id];
      if (ido) act("leave", ido.name, "se desconectó");
      set({ peers });
      break;
    }
    case "ownership": {
      // Diff contra lo anterior: registramos QUÉ ownership cambió. En un
      // reparto masivo (admin) serían decenas de filas idénticas -> lo
      // resumimos en una sola. Honesto y legible.
      const antes = state.owners, ahora = m.owners as Record<string, string>;
      const cambiados: string[] = [];
      for (const p of new Set([...Object.keys(antes), ...Object.keys(ahora)]))
        if (antes[p] !== ahora[p]) cambiados.push(p);
      if (cambiados.length > 3) {
        act("ownership", "", `reparto de ownership · ${cambiados.length} archivos`);
      } else {
        for (const p of cambiados) {
          const due = ahora[p];
          act("ownership", "", due ? `${nombreDe(due)} ahora posee` : "sin dueño", p);
        }
      }
      // Capa 28: si el dueño de un archivo cambió en algo que afecta mi rol
      // sobre ese path (ya no es de otro, o ahora es mío), el draft local
      // dejó de tener sentido: o pasa a ser edición directa, o el server
      // re-fija la verdad. Limpiamos el draft de cualquier path tocado por
      // este reparto y dejamos la edición normal restaurarse.
      const drafts = { ...state.drafts };
      let drafted = false;
      for (const p of cambiados) {
        if (p in drafts) { delete drafts[p]; drafted = true; }
      }
      set({ owners: { ...ahora }, ...(drafted ? { drafts } : {}) });
      break;
    }
    case "proposal": {
      // author_name es texto para mostrar (se le saca el gh:); author_id,
      // que es identidad, queda intacto dentro de ...m.proposal.
      const autor = nombreVisible(m.proposal.author_name);
      act("propuesta", autor, "propuso cambios", m.proposal.path);
      // Conservar seen_at si la propuesta ya existía (re-broadcast): el "hace
      // X" no debe rebotar a "recién" cuando el server reenvía el mismo id.
      const prev = state.proposals[m.proposal.id];
      const seen_at = prev?.seen_at ?? Date.now();
      set({
        proposals: {
          ...state.proposals,
          [m.proposal.id]: { ...m.proposal, author_name: autor, seen_at },
        },
      });
      break;
    }
    case "impact": {
      const key = m.source_path + "::" + m.affected_path;
      const autor = nombreVisible(m.author_name);
      act("impacto", autor, `tocó ${m.source_path} — afecta`, m.affected_path);
      set({ impacts: { ...state.impacts, [key]: { ...m, author_name: autor } } });
      break;
    }
    case "admin_info":
      set({ esAdmin: !!m.is_admin, usuarios: m.users || [] });
      break;
    case "git_status":
      set({ git: m });
      break;
    case "git_result":
      act("git", "", (m.ok ? "✓ " : "✗ ") + String(m.detail).split("\n")[0]);
      set({ gitResult: { ok: m.ok, detail: m.detail, pr_url: m.pr_url || "" } });
      break;
  }
}

// OAuth GitHub: cuando el login con GitHub sale bien, el callback del backend
// redirige el navegador a /app/#session=<token>. El token va en el FRAGMENT
// (#...), NO en el query — el fragmento no viaja al server ni aparece en
// Referer/logs de proxy (decisión de seguridad del backend, `_volver` en
// api/app.py). Por eso se lee de `location.hash`, no de `location.search`.
// Ese token es el MISMO de la capa 7 (HMAC); lo absorbemos como si fuera el
// `orux_session` de localStorage y `connect()` lo manda como SessionMessage,
// igual que el auto-login. Limpiamos el fragmento para que el token no quede
// en la barra ni en el historial. (El error, ?oauth_error=, sí va en el
// query y lo muestra Login.tsx.)
function absorberSesionDeURL() {
  try {
    const hash = location.hash.replace(/^#/, "");
    const token = new URLSearchParams(hash).get("session");
    if (!token) return;
    localStorage.setItem("orux_session", token);
    // Saca el token del fragmento; deja intactos el path y el query.
    history.replaceState(null, "", location.pathname + location.search);
  } catch { /* sin URL API / storage bloqueado: sigue el login normal */ }
}

// Invitación por link: un link de invitación es /app/?invite=<code>. El
// código se guarda en sessionStorage —sobrevive el ida-y-vuelta de OAuth y
// se borra al cerrar la pestaña— y se canjea en cuanto se llega al lobby
// (ver el caso "lobby" de onMessage). Limpiamos el query de la URL.
function absorberInviteDeURL() {
  try {
    const params = new URLSearchParams(location.search);
    const code = params.get("invite");
    if (!code) return;
    sessionStorage.setItem("orux_invite", code);
    params.delete("invite");
    const q = params.toString();
    history.replaceState(
      null, "", location.pathname + (q ? "?" + q : "") + location.hash,
    );
  } catch { /* sin URL API / storage: el invitado puede pegar el código a mano */ }
}

export function connect() {
  absorberSesionDeURL();
  absorberInviteDeURL();
  // Cualquier reintento pendiente queda invalidado: este connect() es la
  // verdad. Y arrancamos limpios: el cierre que venga lo marcamos como NO
  // intencional salvo que alguien (salirEquipo) lo pida explícito.
  cancelarReconnect();
  cierreIntencional = false;
  set({ conn: "conectando" });
  ws = new WebSocket(wsUrl());
  ws.onopen = () => {
    // Conexión viva: el backoff vuelve a cero. La próxima vez que se caiga
    // arrancamos con 500 ms, no con el último delay acumulado.
    reconnectIntento = 0;
    set({ conn: "conectado" });
    const sess = localStorage.getItem("orux_session");
    if (sess) send({ type: "session", token: sess });
    else set({ authed: false });
  };
  ws.onclose = () => {
    set({ conn: "desconectado" });
    // Cierre normal (cambio de equipo, salir): no reintentar. El cierre
    // accidental sí dispara el backoff.
    if (!cierreIntencional) programarReconnect();
  };
  ws.onerror = () => set({ conn: "error" });
  ws.onmessage = (e) => onMessage(e.data as string);
}

// --- Acciones (cliente -> server) ---

export function autenticar(tipo: "login" | "register", username: string, password: string) {
  send({ type: tipo, username, password });
}
export function salir() {
  localStorage.removeItem("orux_session");
  localStorage.removeItem("orux_user");
  location.reload();
}
// Capa 28+: volver al hub SIN cerrar la sesión. El servidor no expone aún un
// "leave_team" explícito, pero un re-handshake con el token de sesión y SIN
// `select_team` cae directamente en el lobby (es el flujo que ya hace el
// auto-login al abrir el IDE). Para no inventar protocolo, cerramos el WS,
// limpiamos el estado del equipo en el cliente y dejamos que la nueva
// conexión nos vuelva a poner en el lobby. Resultado: el usuario ve "tus
// equipos" sin perder identidad, sin reload entero.
export function salirEquipo() {
  // 1) Suelta el WS viejo (su onclose ya marca conn=desconectado). El
  //    server libera la presencia del equipo y los demás verán "se fue".
  //    Marcamos el cierre como INTENCIONAL para que el reconnect automático
  //    no se dispare —el connect() de abajo es la reconexión que queremos,
  //    no un reintento por caída de red.
  cierreIntencional = true;
  try { ws?.close(); } catch { /* ya cerrado, da igual */ }
  ws = null;
  lastPresence = { path: "", line: 0 };
  // 2) Limpia el estado VOLÁTIL del equipo: archivos, owners, presencia,
  //    propuestas, impactos, drafts y la bitácora. La sesión, los equipos
  //    listados y `yo` se mantienen — son del usuario, no del equipo.
  set({
    fase: "lobby",
    files: {}, owners: {}, peers: {}, proposals: {}, impacts: {},
    dirty: {}, drafts: {}, currentPath: null, inviteCode: "",
    git: null, gitResult: null, esAdmin: false, usuarios: [],
    equipo: null, equipoError: "",
    actividad: [], caret: { line: 1, col: 1 },
  });
  // 3) Reconecta. El server verá el SessionMessage del localStorage y nos
  //    devolverá `lobby` con la lista de equipos del usuario (capa 15).
  connect();
}
// Capa 28+: descartar el draft de un archivo. Útil para "me arrepentí de
// proponer este cambio" — la verdad del server vuelve a verse en el editor.
// No manda nada al server (el draft NUNCA viajó). Limpia `dirty` también
// porque el dot ● solo tiene sentido si hay cambios locales que se podrían
// enviar.
export function descartarDraft(path: string) {
  const drafts = { ...state.drafts };
  const dirty = { ...state.dirty };
  delete drafts[path];
  delete dirty[path];
  set({ drafts, dirty });
}
// Capa 28+: cuántos drafts / archivos sin marcar tengo (para statusbar y
// para el guard al salir). Son derivaciones puras: dirty puede incluir
// archivos que ya tienen su contenido en el server (dueño con cambios
// pre-Ctrl+S); drafts solo cuenta los que aún no salieron de mi máquina.
export function contarDrafts(): number {
  return Object.keys(state.drafts).length;
}
export function contarDirty(): number {
  return Object.values(state.dirty).filter(Boolean).length;
}
// --- Capa 15: gate de equipo ---
export function crearEquipo(nombre: string) {
  send({ type: "create_team", nombre });
}
export function redimirInvite(code: string) {
  send({ type: "redeem_invite", code });
}
export function seleccionarEquipo(team_id: string) {
  send({ type: "select_team", team_id });
}
export function crearInvite() {
  send({ type: "create_invite" });
}
// Capa 30: arranca el pago de la suscripción Premium de un equipo. NO va
// por WebSocket — habla con la API HTTP (otro contenedor; Caddy la proxya
// en /api). Le manda el token de sesión (el server verifica que somos
// admin del equipo), recibe la URL de la página de pago hosteada de
// Stripe y redirige el navegador ahí. Devuelve null si todo bien (estamos
// redirigiendo) o un texto de error para mostrar. En dev (sin Caddy) /api
// no resuelve: es una función de deploy, igual que el webhook necesita
// una URL pública con HTTPS.
export async function iniciarCheckout(teamId: string): Promise<string | null> {
  const sess = localStorage.getItem("orux_session");
  if (!sess) return "sesión no encontrada";
  try {
    const r = await fetch("/api/v1/billing/checkout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + sess,
      },
      body: JSON.stringify({ team_id: teamId }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return data.error || "HTTP " + r.status;
    if (typeof data.url === "string" && data.url) {
      // BACKEND-AUDIT M-05: la URL viene del server tras consultar a
      // Stripe — pero cualquier bug intermedio (config de _PUBLIC_URL
      // ya filtrado el callback, response manipulada por un proxy,
      // futuro cambio que devuelva la URL del request en vez de la de
      // Stripe) terminaría haciendo phishing. Validamos el dominio
      // explícito antes de navegar; si no matchea, devolvemos error.
      if (!/^https:\/\/(checkout|buy)\.stripe\.com\//.test(data.url)) {
        return "URL de pago inesperada (no es Stripe)";
      }
      window.location.href = data.url;  // a la página de pago de Stripe
      return null;
    }
    return "respuesta inesperada del servidor";
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}
// Capa 30: vuelve a pedir el lobby (lista de equipos con su plan) sin un
// reload duro. Tras volver de Stripe, el webhook puede tardar un par de
// segundos en marcar el equipo como premium; reconectar el WS dispara
// session->lobby con la lista fresca. Mismo patrón close+connect que
// `salirEquipo` (no inventa protocolo nuevo).
export function refrescarEquipos() {
  try { ws?.close(); } catch { /* ya cerrado, da igual */ }
  ws = null;
  lastPresence = { path: "", line: 0 };
  connect();
}
export function seleccionar(path: string) {
  set({ currentPath: path });
  presence(path, 1);
}
export function cerrarArchivo() {
  set({ currentPath: null });
}
// Capa 28: ¿es archivo con dueño distinto a mí? Centraliza la pregunta que
// gobierna la ruta "propuesta diferida": mientras sea verdad, lo que escribo
// no viaja al server hasta que pulse Ctrl+S.
export function esDeOtro(path: string): boolean {
  const due = state.owners[path];
  return !!(due && state.yo && due !== state.yo.client_id);
}
// Edición local: actualiza el espejo y avisa al server (que NO hace eco al
// emisor, así que no hay loop — por eso no hace falta el viejo applyingRemote).
// Capa 28: si el archivo es de OTRO dueño, lo escrito NO viaja: queda en
// drafts. El editor renderiza el draft (es el feedback inmediato del usuario),
// pero al dueño no le llega ninguna propuesta hasta que se pulse Ctrl+S.
// Antes éramos en vivo y eso hacía un flujo de "propuestas por tecla" que
// invadía la pantalla del dueño.
export function editar(path: string, content: string) {
  if (esDeOtro(path)) {
    set({
      drafts: { ...state.drafts, [path]: content },
      dirty: { ...state.dirty, [path]: true },
    });
    return;
  }
  set({
    files: { ...state.files, [path]: content },
    dirty: { ...state.dirty, [path]: true },  // capa 19: sin checkpoint
  });
  send({ type: "update", path, content });
}
// Capa 19/28: checkpoint explícito (Ctrl+S). Dos significados según rol:
// - Dueño (o archivo sin dueño): NO guarda nada (el contenido ya se
//   sincronizó por `editar`); le dice al server "analizá el impacto de
//   este punto coherente".
// - No-dueño con draft: ESTE es el momento de notificar al dueño. Se manda
//   `update` con el draft; el server lo convierte en propuesta y avisa al
//   dueño. NO se manda `save` porque la propuesta aún no es realidad: el
//   análisis de impacto vendrá cuando el dueño apruebe (server lo hace).
// Limpia el dot de "sin marcar" en ambos casos.
export function guardar(path: string | null) {
  if (!path) return;
  const dirty = { ...state.dirty };
  delete dirty[path];
  set({ dirty });
  if (esDeOtro(path)) {
    const contenido = state.drafts[path];
    if (contenido == null) return;  // nada que proponer
    send({ type: "update", path, content: contenido });
    return;
  }
  send({ type: "save", path });
}
export function presence(path: string, line: number) {
  if (lastPresence.path === path && lastPresence.line === line) return;
  lastPresence = { path, line };
  send({ type: "presence", path, line });
}
export function reclamar(path: string) { send({ type: "claim", path }); }
export function resolver(proposal_id: string, accept: boolean) {
  const props = { ...state.proposals };
  delete props[proposal_id];
  set({ proposals: props });
  send({ type: "resolve", proposal_id, accept });
}
// Capa 36 (G.2): trackeo local de "yo pedí borrar X" para mostrar el toast
// de éxito CUANDO el server confirma el delete (broadcast `delete`), no
// antes. Sin esto, el usuario veía "✓ borrado X" al confirmar el diálogo
// aunque el server pudiera rechazar — falso positivo cosmético. Map por
// path → texto ya traducido (el store no tiene acceso al hook `useI18n`,
// así que el caller pasa el string i18n-resuelto).
const _deletePedidos = new Map<string, string>();
export function borrar(path: string, toastOk: string = ""): void {
  _deletePedidos.set(path, toastOk);
  send({ type: "delete", path });
}
export function commitear(message: string) { send({ type: "commit", message }); }
export function gitRefresh() { send({ type: "git_refresh" }); }
export function clonar(url: string, username: string, token: string) {
  send({ type: "clone", url, username, token });
}
export function pushear(
  username: string, token: string, url: string, rama: string,
) {
  // rama vacía = la rama de publicación del equipo (default seguro: PR,
  // el server fuerza-con-lease solo ahí). "main"/otra = push directo sin
  // forzar. El server decide; el cliente solo manda a dónde.
  send({ type: "push", username, token, url, rama });
}
export function nuevoArchivo(path: string) {
  // El server NO hace eco del update al emisor (capa 1, sin loop): si no
  // reflejamos el archivo local, el creador no lo ve hasta recargar
  // (mientras los demás sí, vía broadcast). Espejo local optimista —mismo
  // criterio que `editar`— + abrirlo (paridad con lo que ve el otro). El
  // server, en el 1er update de un path sin dueño, hace dueño al creador y
  // difunde `ownership` a TODOS (incluido el emisor): eso llega solo.
  if (path in state.files) return;  // ya existe: no pisarlo
  set({
    files: { ...state.files, [path]: "" },
    dirty: { ...state.dirty, [path]: true },  // capa 19: sin checkpoint
    currentPath: path,
  });
  send({ type: "update", path, content: "" });
  presence(path, 1);
}
export function adminAsignarVarios(paths: string[], username: string) {
  send({ type: "admin_assign_many", paths, username });
}
export function descartarImpacto(key: string) {
  const im = { ...state.impacts };
  delete im[key];
  set({ impacts: im });
}
// Nombre para MOSTRAR: la identidad de un usuario de GitHub es `gh:<login>`
// (el prefijo es una defensa de seguridad — ver identity/oauth.py: evita que
// alguien preregistre el handle de una víctima). Pero ese `gh:` no se le
// muestra a la gente: en pantalla va sólo el login. La identidad real
// (client_id, author_id, owners, la lista de usuarios del admin) NUNCA se
// toca — sólo se limpia el texto que ve un humano.
export function nombreVisible(name: string): string {
  return name.startsWith("gh:") ? name.slice(3) : name;
}
export function nombreDe(cid: string): string {
  if (state.yo && cid === state.yo.client_id) return state.yo.name;
  if (state.peers[cid]) return state.peers[cid].name;
  return nombreVisible(cid);
}
