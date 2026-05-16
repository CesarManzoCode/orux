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
}
export interface Impact {
  source_path: string; author_name: string;
  affected_path: string; symbols: string[]; motivos: string[];
}
export interface GitStatus {
  available: boolean; branch: string; changes: number; commits: string[];
}
export interface State {
  conn: "conectando" | "conectado" | "desconectado" | "error";
  authed: boolean;
  loginError: string | null;
  yo: { client_id: string; name: string; color: string } | null;
  files: Record<string, string>;
  currentPath: string | null;
  owners: Record<string, string>;
  peers: Record<string, Peer>;
  proposals: Record<string, Proposal>;
  impacts: Record<string, Impact>;
  git: GitStatus | null;
  gitResult: { ok: boolean; detail: string } | null;
  esAdmin: boolean;
  usuarios: string[];
  proyecto: string;
  // Capa 15: gate de equipo. "auth" = sin loguear; "lobby" = logueado pero
  // sin equipo (elegir/crear/unirse); "team" = dentro de un equipo (IDE).
  fase: "auth" | "lobby" | "team";
  equipos: { id: string; nombre: string; rol: string }[];
  equipoError: string;
  equipo: { id: string; nombre: string; rol: string } | null;
  inviteCode: string;  // último código emitido por el admin (para compartir)
}

const inicial: State = {
  conn: "conectando", authed: false, loginError: null, yo: null,
  files: {}, currentPath: null, owners: {}, peers: {}, proposals: {},
  impacts: {}, git: null, gitResult: null, esAdmin: false, usuarios: [],
  proyecto:
    location.hostname && location.hostname !== "localhost"
      ? location.hostname : "local",
  fase: "auth", equipos: [], equipoError: "", equipo: null, inviteCode: "",
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

function send(obj: unknown) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function onMessage(raw: string) {
  const m = JSON.parse(raw);
  switch (m.type) {
    case "auth_ok":
      localStorage.setItem("laidea_session", m.token);
      localStorage.setItem("laidea_user", m.username);
      // Autenticado pero todavía sin equipo: el server manda `lobby` a
      // continuación. La app sigue cerrada un escalón más.
      set({ authed: true, loginError: null, fase: "lobby" });
      break;
    case "auth_error":
      localStorage.removeItem("laidea_session");
      set({ authed: false, loginError: m.reason, fase: "auth" });
      break;
    case "lobby":
      set({ fase: "lobby", equipos: m.teams || [], equipoError: m.error || "" });
      break;
    case "team_ready":
      // Entramos a un equipo: lo que sigue (init/welcome/...) es de ÉL.
      set({
        fase: "team",
        equipo: { id: m.team_id, nombre: m.nombre, rol: m.rol },
        equipoError: "",
        // estado de equipo anterior, limpio (por si se cambió de equipo).
        files: {}, owners: {}, peers: {}, proposals: {}, impacts: {},
        currentPath: null, inviteCode: "",
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
      });
      if (primero) presence(primero, 1);
      break;
    }
    case "update": {
      if (typeof m.path !== "string" || !m.path) break;
      set({ files: { ...state.files, [m.path]: m.content } });
      break;
    }
    case "delete": {
      if (!(m.path in state.files)) break;
      const files = { ...state.files };
      delete files[m.path];
      let cur = state.currentPath;
      if (cur === m.path) cur = Object.keys(files).sort()[0] ?? null;
      set({ files, currentPath: cur });
      break;
    }
    case "welcome": {
      const peers: Record<string, Peer> = {};
      for (const p of m.peers) peers[p.client_id] = p;
      set({ yo: m.you, peers });
      break;
    }
    case "presence":
      set({
        peers: {
          ...state.peers,
          [m.client_id]: {
            client_id: m.client_id, name: m.name, color: m.color,
            path: m.path, line: m.line,
          },
        },
      });
      break;
    case "leave": {
      const peers = { ...state.peers };
      delete peers[m.client_id];
      set({ peers });
      break;
    }
    case "ownership":
      set({ owners: { ...m.owners } });
      break;
    case "proposal":
      set({ proposals: { ...state.proposals, [m.proposal.id]: m.proposal } });
      break;
    case "impact": {
      const key = m.source_path + "::" + m.affected_path;
      set({ impacts: { ...state.impacts, [key]: m } });
      break;
    }
    case "admin_info":
      set({ esAdmin: !!m.is_admin, usuarios: m.users || [] });
      break;
    case "git_status":
      set({ git: m });
      break;
    case "git_result":
      set({ gitResult: { ok: m.ok, detail: m.detail } });
      break;
  }
}

export function connect() {
  ws = new WebSocket(wsUrl());
  ws.onopen = () => {
    set({ conn: "conectado" });
    const sess = localStorage.getItem("laidea_session");
    if (sess) send({ type: "session", token: sess });
    else set({ authed: false });
  };
  ws.onclose = () => set({ conn: "desconectado" });
  ws.onerror = () => set({ conn: "error" });
  ws.onmessage = (e) => onMessage(e.data as string);
}

// --- Acciones (cliente -> server) ---

export function autenticar(tipo: "login" | "register", username: string, password: string) {
  send({ type: tipo, username, password });
}
export function salir() {
  localStorage.removeItem("laidea_session");
  localStorage.removeItem("laidea_user");
  location.reload();
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
export function seleccionar(path: string) {
  set({ currentPath: path });
  presence(path, 1);
}
export function cerrarArchivo() {
  set({ currentPath: null });
}
// Edición local: actualiza el espejo y avisa al server (que NO hace eco al
// emisor, así que no hay loop — por eso no hace falta el viejo applyingRemote).
export function editar(path: string, content: string) {
  set({ files: { ...state.files, [path]: content } });
  send({ type: "update", path, content });
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
export function borrar(path: string) { send({ type: "delete", path }); }
export function commitear(message: string) { send({ type: "commit", message }); }
export function gitRefresh() { send({ type: "git_refresh" }); }
export function clonar(url: string, username: string, token: string) {
  send({ type: "clone", url, username, token });
}
export function pushear(username: string, token: string, url: string) {
  send({ type: "push", username, token, url });
}
export function nuevoArchivo(path: string) {
  // El server NO hace eco del update al emisor (capa 1, sin loop): si no
  // reflejamos el archivo local, el creador no lo ve hasta recargar
  // (mientras los demás sí, vía broadcast). Espejo local optimista —mismo
  // criterio que `editar`— + abrirlo (paridad con lo que ve el otro). El
  // server, en el 1er update de un path sin dueño, hace dueño al creador y
  // difunde `ownership` a TODOS (incluido el emisor): eso llega solo.
  if (path in state.files) return;  // ya existe: no pisarlo
  set({ files: { ...state.files, [path]: "" }, currentPath: path });
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
export function nombreDe(cid: string): string {
  if (state.yo && cid === state.yo.client_id) return state.yo.name;
  if (state.peers[cid]) return state.peers[cid].name;
  return cid;
}
