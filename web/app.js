/*
 * Cliente del prototipo. Esta es la otra mitad del contrato del protocolo:
 * tiene que hablar exactamente el mismo lenguaje que el servidor de Python.
 *
 * Estado local que mantenemos:
 *  - files:        espejo del workspace del servidor (path -> contenido).
 *                  El servidor es la fuente de verdad; este dict es solo
 *                  una copia para renderizar la UI rápido.
 *  - currentPath:  qué archivo se está mostrando ahora mismo en el textarea.
 *  - applyingRemote: bandera para no mandar al servidor cambios que el propio
 *                    servidor nos acaba de mandar (eso causaría loop infinito).
 */
const editor = document.getElementById("editor");
const statusEl = document.getElementById("status");
const lista = document.getElementById("lista");
const actual = document.getElementById("actual");
const botonNuevo = document.getElementById("nuevo");
const yoEl = document.getElementById("yo");
const aquiEl = document.getElementById("aqui");
const wrap = document.getElementById("wrap");
const capaScroll = document.getElementById("capa-scroll");
const resaltadoCode = document.querySelector("#resaltado code");
const gutterScroll = document.getElementById("gutter-scroll");
const lineaActivaEl = document.getElementById("lineaActiva");
const ownerEl = document.getElementById("owner");
const reclamarBtn = document.getElementById("reclamar");
const propuestasEl = document.getElementById("propuestas");
const impactosEl = document.getElementById("impactos");
const avisoEl = document.getElementById("aviso");
const loginEl = document.getElementById("login");
const uEl = document.getElementById("u");
const pEl = document.getElementById("p");
const loginErr = document.getElementById("loginErr");
const entrarBtn = document.getElementById("entrar");
const crearBtn = document.getElementById("crear");
const salirEl = document.getElementById("salir");
const gitEl = document.getElementById("git");
// Chrome IDE (capa de UX): rail de actividad, pestaña, barra de estado.
// Capa 13: el botón admin del rail abre el modal (admin.js), ya no una
// vista del sidebar; por eso el rail solo cablea aquí archivos/git.
const railBtns = document.querySelectorAll('#rail button[data-vista="archivos"], #rail button[data-vista="git"]');
const railAdminBtn = document.querySelector('#rail button[data-vista="admin"]');
const vistaPanels = document.querySelectorAll('aside .vista');
const tabsEl = document.getElementById("tabs");
const proyEl = document.getElementById("proy");
const sbGit = document.getElementById("sb-git");
const sbLang = document.getElementById("sb-lang");
const sbYo = document.getElementById("sb-yo");

function mostrarLogin(err) {
  loginEl.classList.add("on");
  loginErr.textContent = err || "";
  salirEl.style.display = "none";
  uEl.focus();
}
function ocultarLogin() {
  loginEl.classList.remove("on");
  salirEl.style.display = "";
}
function enviarAuth(tipo) {
  const username = uEl.value.trim();
  const password = pEl.value;
  if (!username || !password) {
    loginErr.textContent = "usuario y contraseña requeridos";
    return;
  }
  if (ws.readyState !== WebSocket.OPEN) {
    loginErr.textContent = "sin conexión al servidor";
    return;
  }
  loginErr.textContent = "entrando…";
  ws.send(JSON.stringify({ type: tipo, username, password }));
}
entrarBtn.addEventListener("click", () => enviarAuth("login"));
crearBtn.addEventListener("click", () => enviarAuth("register"));
pEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") enviarAuth("login");
});
// "salir": olvida la sesión y recarga -> vuelve la pantalla de login.
// Útil para probar con otro usuario (mismo navegador comparte sesión).
salirEl.addEventListener("click", () => {
  localStorage.removeItem("laidea_session");
  localStorage.removeItem("laidea_user");
  location.reload();
});

// Estas dos constantes DEBEN coincidir con el CSS del textarea
// (line-height y padding-top). Si cambias el CSS, cámbialas aquí: son el
// contrato que hace que la línea N del texto caiga sobre la marca N.
const LINE_H = 22;
const PAD_TOP = 20;

const files = {};
let currentPath = null;
let applyingRemote = false;

/*
 * Estado de presencia (capa 2). El servidor es la fuente de verdad; esto
 * es el espejo local para pintar.
 *  - yo:    mi identidad anónima (id, nombre, color), me la asigna el server.
 *  - peers: client_id -> {name, color, path, line} de los demás presentes.
 *  - ultimaPresencia: lo último que le mandé al server, para no spamear un
 *    presence idéntico en cada tecla (solo mando si cambié de archivo o línea).
 */
let yo = null;
const peers = {};
let ultimaPresencia = { path: null, line: 0 };

/*
 * Estado de ownership (capa 4).
 *  - owners:     path -> client_id del dueño. Espejo del mapa del server.
 *  - propuestas: id -> {path, author_id, author_name, content}. Cambios
 *                tentativos que ESTE cliente (como dueño) tiene que resolver.
 */
const owners = {};
const propuestas = {};

/*
 * Estado de impacto (capa 6). impactos: clave -> aviso. La clave es
 * `source_path::affected_path`: si el autor sigue tecleando, el aviso
 * nuevo reemplaza al viejo en vez de acumular (mismo criterio que las
 * propuestas con su id determinista). Cada aviso: el server me dice que
 * un cambio ajeno toca un archivo MÍO.
 */
const impactos = {};

// Estado git. gitEstado: última foto del repo. gitResultado: feedback del
// último commit. gitMsgBorrador: lo tipeado, para no perderlo si el panel
// se re-renderiza por un git_status entrante.
let gitEstado = null;
let gitResultado = null;
let gitMsgBorrador = "";
// Remoto: url/usuario en memoria de SESIÓN (no localStorage) para no
// retipear. El token NUNCA se guarda — ni acá ni en ningún lado.
const gitRemoto = { url: "", user: "" };

// Capa 12: ¿soy el admin del workspace? + usuarios para el selector del
// panel. Lo decide el SERVER (admin_info), nunca el cliente; el cliente
// solo pinta. A un no-admin ni se le muestra el panel (y aunque forzara
// un admin_assign, el server lo ignora). La lista se refresca recargando
// (decisión mínima, mismo criterio que git_refresh).
let esAdmin = false;
let usuariosLista = [];

// Nombre legible de un client_id. Si está presente lo sacamos del roster;
// si soy yo, mi nombre; si no, lo reconstruimos del esquema del server
// (client_id "3" -> "anónimo-3"). Cuando llegue auth esto usará el real.
function nombreDe(cid) {
  if (yo && cid === yo.client_id) return yo.name;
  if (peers[cid]) return peers[cid].name;
  return cid;  // capa 7: el client_id ES el usuario
}

/*
 * Capa 7: identidad real. La app está CERRADA — el server no manda nada
 * hasta autenticarse. Al abrir el socket: si tenemos un token de sesión
 * firmado guardado (de un login previo), lo presentamos para auto-login;
 * si no, mostramos el formulario. El token lo emite el server (va firmado
 * con HMAC); reemplaza al token anónimo sin firmar de antes.
 */
/*
 * URL del WebSocket. Tiene que funcionar en DOS mundos sin tocar nada:
 *  - Dev: el cliente lo sirve Live Server (puerto 5500) o se abre como
 *    file://, y el server corre aparte en localhost:8765.
 *  - Deploy: Caddy sirve esta página por https en el dominio real y
 *    proxya `/ws` al server -> mismo host, wss, ruta /ws.
 * Antes estaba hardcodeado a ws://localhost:8765, lo que rompía cualquier
 * despliegue. Esto lo deriva del origen de la página.
 */
const WS_URL = (function () {
  const dev = location.protocol === "file:" || location.port === "5500";
  if (dev) return "ws://localhost:8765";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return proto + "//" + location.host + "/ws";
})();
const ws = new WebSocket(WS_URL);

// Nombre del "proyecto" en el breadcrumb del topbar: el host en deploy,
// "local" en dev. Es presentación; el workspace sigue siendo uno solo.
proyEl.textContent =
  (location.hostname && location.hostname !== "localhost")
    ? location.hostname : "local";
renderTabs();
renderEstado();

ws.onopen = () => {
  statusEl.textContent = "conectado"; statusEl.className = "ok";
  const sess = localStorage.getItem("laidea_session");
  if (sess) {
    ws.send(JSON.stringify({ type: "session", token: sess }));
  } else {
    mostrarLogin();
  }
};
ws.onclose = () => { statusEl.textContent = "desconectado"; statusEl.className = "bad"; editor.disabled = true; };
ws.onerror = () => { statusEl.textContent = "error de conexión"; statusEl.className = "bad"; };

/*
 * Recepción de mensajes. Aquí decidimos qué hacer según el `type` que mandó
 * el servidor. Es la cara complementaria del `decode` de Python.
 */
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  if (msg.type === "auth_ok") {
    // Autenticado. Guardamos el token de sesión fresco (para auto-login al
    // recargar) y el usuario, y dejamos pasar a la app. Lo que sigue
    // (init/welcome/ownership) lo procesan los handlers de abajo.
    localStorage.setItem("laidea_session", msg.token);
    localStorage.setItem("laidea_user", msg.username);
    ocultarLogin();
    return;
  }

  if (msg.type === "auth_error") {
    // Falló el login/registro, o el token de sesión guardado ya no vale.
    // Si fue el token, lo tiramos para no reintentar en bucle al recargar.
    localStorage.removeItem("laidea_session");
    mostrarLogin(msg.reason);
    return;
  }

  if (msg.type === "init") {
    // El servidor manda el workspace completo: al conectar Y de nuevo
    // tras un clone (capa 10), que REEMPLAZA todo. Por eso limpiamos
    // antes de copiar: si fuera merge, tras clonar quedarían colgando
    // los archivos del proyecto anterior.
    for (const k of Object.keys(files)) delete files[k];
    Object.assign(files, msg.files);
    const primero = Object.keys(files).sort()[0];
    if (primero) {
      seleccionar(primero);
    } else {
      // Repo vacío: sin archivo abierto (mismo estado que cerrar uno).
      cerrarArchivo();
    }
  }

  if (msg.type === "update") {
    // Guard defensivo: si por alguna razón el mensaje no trae `path`
    // (servidor en otra versión del protocolo, mensaje corrupto, etc.)
    // lo ignoramos en vez de crear silenciosamente un archivo llamado
    // "undefined". Esto te salva de horas de debugging la próxima vez
    // que tengas un servidor stale corriendo.
    if (typeof msg.path !== "string" || !msg.path) return;

    // Otro cliente editó un archivo. Actualizamos nuestro espejo local.
    const eraNuevo = !(msg.path in files);
    files[msg.path] = msg.content;
    if (eraNuevo) renderLista();

    // Si el archivo que cambió es el que tenemos abierto, refrescamos el
    // textarea — preservando la posición del cursor, porque si la perdiéramos
    // sería extremadamente molesto escribir mientras otro escribe.
    if (msg.path === currentPath) {
      const inicio = editor.selectionStart;
      const fin = editor.selectionEnd;
      applyingRemote = true;
      editor.value = msg.content;
      applyingRemote = false;
      pintarResaltado();
      editor.selectionStart = inicio;
      editor.selectionEnd = fin;
    }
  }

  if (msg.type === "delete") {
    // Un archivo se borró (lo pediste vos o alguien con permiso). El
    // server difunde a todos para converger sin adivinar.
    if (typeof msg.path !== "string" || !(msg.path in files)) return;
    delete files[msg.path];
    if (msg.path === currentPath) {
      // Estabas en el archivo borrado: saltá a otro o quedate sin nada.
      currentPath = null;
      const otro = Object.keys(files).sort()[0];
      if (otro) {
        seleccionar(otro);
      } else {
        cerrarArchivo();  // nada que abrir: editor sin archivo
      }
    }
    renderLista();
  }

  if (msg.type === "welcome") {
    // El servidor me dice quién soy y quiénes más están presentes ahora.
    yo = msg.you;
    yoEl.textContent = "tú: " + yo.name;
    yoEl.style.color = yo.color;
    for (const p of msg.peers) peers[p.client_id] = p;
    renderLista();
    renderPresencia();
    renderEstado();  // ya sé quién soy: pintar identidad en la barra
  }

  if (msg.type === "presence") {
    // Alguien se movió (cambió de archivo o de línea). Refrescamos su
    // marcador. Es solo estado de UI: no toca el contenido de ningún archivo.
    peers[msg.client_id] = {
      client_id: msg.client_id, name: msg.name, color: msg.color,
      path: msg.path, line: msg.line,
    };
    renderLista();
    renderPresencia();
  }

  if (msg.type === "leave") {
    // Se desconectó: lo despintamos de todos lados.
    delete peers[msg.client_id];
    renderLista();
    renderPresencia();
  }

  if (msg.type === "ownership") {
    // Mapa completo, idempotente: reemplazamos el espejo entero en vez de
    // aplicar deltas. Sencillo y sin estado que se desincronice.
    for (const k of Object.keys(owners)) delete owners[k];
    Object.assign(owners, msg.owners);
    renderOwnership();
    renderPropuestas();
    renderAdmin();  // refleja el dueño nuevo en el selector
  }

  if (msg.type === "proposal") {
    // Soy dueño de ese archivo y alguien propone un cambio. Lo guardo por
    // id (determinista: si el autor sigue tecleando, su nueva propuesta
    // reemplaza a la vieja en vez de acumular).
    const p = msg.proposal;
    propuestas[p.id] = p;
    renderPropuestas();
  }

  if (msg.type === "impact") {
    // Cambiaron algo que un archivo MÍO usa. Solo entera, no pide acción.
    // Clave determinista source::affected: tecleo del autor -> reemplaza.
    impactos[msg.source_path + "::" + msg.affected_path] = msg;
    renderImpactos();
  }

  if (msg.type === "admin_info") {
    // El server me dice si soy el admin del workspace (lo decide ÉL, no
    // el cliente) y la lista de usuarios para el selector. Una sola vez
    // tras el handshake; si entra gente nueva después, recargá.
    esAdmin = !!msg.is_admin;
    usuariosLista = msg.users || [];
    // El ícono de admin del rail solo existe si sos admin (abre el modal,
    // lo maneja admin.js). Si dejaste de serlo (re-init), se oculta y el
    // modal se cierra desde renderAdmin().
    railAdminBtn.style.display = esAdmin ? "" : "none";
    renderAdmin();
  }

  if (msg.type === "git_status") {
    // Foto del repo. El server la manda tras el handshake, al "actualizar"
    // y tras un commit (de cualquiera: el repo es compartido).
    gitEstado = msg;
    renderGit();
    renderEstado();  // rama/cambios en la barra de estado inferior
  }

  if (msg.type === "git_result") {
    // Resultado de TU commit. Si salió, limpiamos el borrador.
    gitResultado = msg;
    if (msg.ok) gitMsgBorrador = "";
    renderGit();
  }
};

/*
 * Calcula en qué línea (1-indexada) está el cursor: contar saltos de línea
 * antes de la posición del cursor. Es el mismo criterio que el server y la
 * UI usan, así que con esto basta para "dónde estoy escribiendo".
 */
function lineaActual() {
  return editor.value.slice(0, editor.selectionStart).split("\n").length;
}

/*
 * Anuncia mi presencia al server, pero solo si de verdad cambió algo
 * (archivo o línea). Mandar un presence idéntico en cada pulsación sería
 * ruido de red puro. No anuncio mientras aplico un cambio remoto: el cursor
 * no se movió por decisión mía.
 */
function enviarPresencia() {
  if (!currentPath || applyingRemote) return;
  if (ws.readyState !== WebSocket.OPEN) return;
  const line = lineaActual();
  if (ultimaPresencia.path === currentPath && ultimaPresencia.line === line) return;
  ultimaPresencia = { path: currentPath, line };
  ws.send(JSON.stringify({ type: "presence", path: currentPath, line }));
}

// El cursor se mueve por muchas vías; cubrimos todas las baratas.
for (const ev of ["keyup", "click", "input", "select"]) {
  editor.addEventListener(ev, enviarPresencia);
}
// La capa de presencia se desplaza junto con el scroll del textarea para
// que cada marca siga pegada a su línea aunque se haga scroll.
editor.addEventListener("scroll", () => {
  capaScroll.style.transform = "translateY(" + (-editor.scrollTop) + "px)";
});

/*
 * Ergonomía de editor de verdad (pulido, sin dependencias): cerrar pares,
 * sobre-escribir el cierre, borrar el par vacío, Tab = 4 espacios, y Enter
 * que conserva la sangría (y agrega una más tras `:` o un `(` abierto).
 * Tras mutar el textarea a mano disparamos `input`: así corren los mismos
 * listeners de siempre (mandar update, presencia, resaltado) sin duplicar
 * lógica ni romper nada.
 */
const PARES = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`" };
const CIERRES = new Set([")", "]", "}", '"', "'", "`"]);

function _muta(nuevo, caret) {
  editor.value = nuevo;
  editor.selectionStart = editor.selectionEnd = caret;
  editor.dispatchEvent(new Event("input", { bubbles: true }));
}

editor.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const v = editor.value;
  const a = editor.selectionStart, b = editor.selectionEnd;
  const k = e.key;

  if (k in PARES) {
    e.preventDefault();
    const cierre = PARES[k];
    if (a !== b) {                       // hay selección -> envolverla
      _muta(v.slice(0, a) + k + v.slice(a, b) + cierre + v.slice(b), b + 2);
    } else {
      _muta(v.slice(0, a) + k + cierre + v.slice(a), a + 1);
    }
    return;
  }
  if (CIERRES.has(k) && a === b && v[a] === k) {
    // Ya hay un cierre ahí (lo puso el auto-par): pasar por encima.
    e.preventDefault();
    editor.selectionStart = editor.selectionEnd = a + 1;
    return;
  }
  if (k === "Backspace" && a === b && a > 0 &&
      PARES[v[a - 1]] === v[a]) {
    e.preventDefault();
    _muta(v.slice(0, a - 1) + v.slice(a + 1), a - 1);
    return;
  }
  if (k === "Tab") {
    e.preventDefault();
    _muta(v.slice(0, a) + "    " + v.slice(b), a + 4);
    return;
  }
  if (k === "Enter") {
    e.preventDefault();
    const iniLinea = v.lastIndexOf("\n", a - 1) + 1;
    const sangria = (v.slice(iniLinea, a).match(/^[ \t]*/) || [""])[0];
    const previo = v[a - 1];
    const extra = (previo === ":" || previo === "(" ||
                   previo === "[" || previo === "{") ? "    " : "";
    _muta(v.slice(0, a) + "\n" + sangria + extra + v.slice(b),
          a + 1 + sangria.length + extra.length);
    return;
  }
});

/*
 * Resaltado de sintaxis, vanilla y mínimo (Python). Pinta una capa <pre>
 * detrás del textarea transparente — no es un compilador, es heurística
 * "se ve como código". Mismo espíritu que el análisis semántico mínimo:
 * honesto, suficiente, sin dependencias.
 */
function escHtml(s) {
  return s.replace(/[&<>]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
const _RE_PY = new RegExp(
  "('''[\\s\\S]*?'''|\"\"\"[\\s\\S]*?\"\"\"" +              // triple str
  "|[rbfRBF]{0,2}\"(?:\\\\.|[^\"\\\\\\n])*\"" +              // str "
  "|[rbfRBF]{0,2}'(?:\\\\.|[^'\\\\\\n])*')" +                // str '
  "|(#[^\\n]*)" +                                            // comentario
  "|\\b(def|class)(\\s+)([A-Za-z_]\\w*)" +                    // def/class nombre
  "|(@[A-Za-z_][\\w.]*)" +                                    // decorador
  "|\\b(False|None|True|and|as|assert|async|await|break|case|class|" +
  "continue|def|del|elif|else|except|finally|for|from|global|if|" +
  "import|in|is|lambda|match|nonlocal|not|or|pass|raise|return|try|" +
  "while|with|yield)\\b" +                                    // keyword
  "|\\b(print|len|range|int|str|float|bool|list|dict|set|tuple|" +
  "isinstance|enumerate|zip|open|super|self|cls)\\b" +         // builtin
  "|\\b(0[xXbBoO][0-9a-fA-F_]+|\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)\\b",
  "g"
);
function resaltarPy(src) {
  let out = "", last = 0, m;
  _RE_PY.lastIndex = 0;
  while ((m = _RE_PY.exec(src)) !== null) {
    out += escHtml(src.slice(last, m.index));
    if (m[1]) out += '<span class="tk-str">' + escHtml(m[1]) + "</span>";
    else if (m[2]) out += '<span class="tk-com">' + escHtml(m[2]) + "</span>";
    else if (m[3]) out += '<span class="tk-kw">' + m[3] + "</span>" +
      m[4] + '<span class="tk-def">' + escHtml(m[5]) + "</span>";
    else if (m[6]) out += '<span class="tk-dec">' + escHtml(m[6]) + "</span>";
    else if (m[7]) out += '<span class="tk-kw">' + m[7] + "</span>";
    else if (m[8]) out += '<span class="tk-bi">' + m[8] + "</span>";
    else if (m[9]) out += '<span class="tk-num">' + m[9] + "</span>";
    last = _RE_PY.lastIndex;
    if (m.index === _RE_PY.lastIndex) _RE_PY.lastIndex++;  // anti-bucle
  }
  out += escHtml(src.slice(last));
  return out;
}
// Extensión -> lenguaje de Prism. Debe coincidir con los componentes
// que trae web/vendor/prism.js (ver su README): mapear algo que el
// bundle no incluye solo da texto plano (el try/catch lo cubre).
const _LANG = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  mjs: "javascript", cjs: "javascript", py: "python", json: "json",
  css: "css", scss: "css", html: "markup", htm: "markup", xml: "markup",
  svg: "markup", vue: "markup", md: "markdown", markdown: "markdown",
  sh: "bash", bash: "bash", yml: "yaml", yaml: "yaml", toml: "yaml",
  sql: "sql", java: "java", go: "go", rs: "rust", rb: "ruby",
  c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp",
  hxx: "cpp", cs: "csharp", php: "php", kt: "kotlin", kts: "kotlin",
  swift: "swift", dockerfile: "docker",
};
// Archivos SIN extensión que igual son código (Dockerfile, Makefile).
// Match por nombre base, también `Dockerfile.dev` / `xxx.Dockerfile`.
const _NOMBRE = { dockerfile: "docker", makefile: "makefile" };
function langDe(path) {
  if (!path) return null;
  const base = path.split("/").pop().toLowerCase();
  for (const clave in _NOMBRE) {
    if (base === clave || base.startsWith(clave + ".") ||
        base.endsWith("." + clave)) return _NOMBRE[clave];
  }
  const i = base.lastIndexOf(".");
  if (i < 0) return null;
  return _LANG[base.slice(i + 1)] || null;
}

/*
 * Chrome de IDE (capa de UX, no de features): que se vea como una
 * herramienta real, porque con un equipo SIN amistad de por medio un
 * aspecto de prototipo es un "no" antes de evaluar el core. Nada de esto
 * toca el protocolo, el ownership/locks ni la métrica del overlay: es
 * navegación y presentación sobre el estado que ya existe.
 */

// Lenguaje -> chip de tipo (texto corto + clase de color) y nombre
// legible para la barra de estado. Derivado de langDe (Prism), así un
// solo mapa manda. Desconocido -> chip neutro con la extensión.
const _CHIP = {
  python: ["py", "t-py", "Python"],
  typescript: ["ts", "t-ts", "TypeScript"], tsx: ["tsx", "t-ts", "TSX"],
  javascript: ["js", "t-js", "JavaScript"], jsx: ["jsx", "t-js", "JSX"],
  go: ["go", "t-go", "Go"], rust: ["rs", "t-rs", "Rust"],
  java: ["java", "t-java", "Java"], kotlin: ["kt", "t-java", "Kotlin"],
  cpp: ["cpp", "t-cpp", "C++"], c: ["c", "t-cpp", "C"],
  csharp: ["c#", "t-cpp", "C#"],
  markdown: ["md", "t-md", "Markdown"],
  json: ["json", "t-cfg", "JSON"], yaml: ["yml", "t-cfg", "YAML"],
  docker: ["dok", "t-cfg", "Dockerfile"], makefile: ["mk", "t-cfg", "Makefile"],
  bash: ["sh", "t-cfg", "Shell"], sql: ["sql", "t-cfg", "SQL"],
  markup: ["<>", "t-cfg", "Markup"], css: ["css", "t-cfg", "CSS"],
  ruby: ["rb", "t-rs", "Ruby"], php: ["php", "t-cfg", "PHP"],
  swift: ["sw", "t-rs", "Swift"],
};
function chipDe(path) {
  const lang = langDe(path);
  if (lang && _CHIP[lang]) {
    const [txt, cls, nom] = _CHIP[lang];
    return { txt, cls, nom };
  }
  const base = (path || "").split("/").pop();
  const ext = base.includes(".") ? base.split(".").pop().toLowerCase() : "";
  return { txt: (ext || "·").slice(0, 4), cls: "", nom: ext || "texto" };
}
// <span class="ti t-xx">py</span> para lista y pestaña.
function chipEl(path) {
  const { txt, cls } = chipDe(path);
  const s = document.createElement("span");
  s.className = "ti" + (cls ? " " + cls : "");
  s.textContent = txt;
  return s;
}

// Rail de actividad: cambia qué panel muestra el sidebar. Pura
// navegación entre lo que ya existe (archivos / git / admin).
let vistaActiva = "archivos";
function setVista(v) {
  vistaActiva = v;
  railBtns.forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
  vistaPanels.forEach((p) => p.classList.toggle("on", p.dataset.vista === v));
}
railBtns.forEach((b) =>
  b.addEventListener("click", () => setVista(b.dataset.vista))
);

// Pestaña del archivo abierto (minimal: solo la actual). Cerrarla deja
// el editor sin archivo, mismo estado que arrancar sin nada.
function renderTabs() {
  tabsEl.innerHTML = "";
  if (!currentPath) {
    const v = document.createElement("span");
    v.className = "vacio";
    v.textContent = "sin archivo abierto";
    tabsEl.appendChild(v);
    return;
  }
  const tab = document.createElement("div");
  tab.className = "tab";
  tab.appendChild(chipEl(currentPath));
  const nom = document.createElement("span");
  nom.className = "nom";
  nom.textContent = currentPath.split("/").pop();
  nom.title = currentPath;
  tab.appendChild(nom);
  const x = document.createElement("button");
  x.className = "tabx";
  x.textContent = "✕";
  x.title = "cerrar";
  x.addEventListener("click", cerrarArchivo);
  tab.appendChild(x);
  tabsEl.appendChild(tab);
}
// Cerrar = sin archivo abierto (NO borra: solo cierra la pestaña).
function cerrarArchivo() {
  currentPath = null;
  actual.textContent = "";
  applyingRemote = true;
  editor.value = "";
  applyingRemote = false;
  pintarResaltado();
  editor.disabled = true;
  wrap.classList.add("off");
  renderLista();
  renderOwnership();
  renderAdmin();
  renderTabs();
  renderEstado();
}

// Barra de estado inferior: rama · cambios · lenguaje · identidad.
// Solo lee estado existente (git, archivo abierto, usuario).
function renderEstado() {
  sbGit.innerHTML = "";
  if (gitEstado && gitEstado.available) {
    const r = document.createElement("span");
    r.innerHTML = "⎇ <b></b>";
    r.querySelector("b").textContent = gitEstado.branch || "—";
    sbGit.appendChild(r);
    const n = gitEstado.changes || 0;
    const c = document.createElement("span");
    c.className = "sep";
    c.textContent = "·";
    const cc = document.createElement("span");
    cc.textContent = n === 0 ? "limpio"
      : n + (n === 1 ? " cambio" : " cambios");
    sbGit.appendChild(c); sbGit.appendChild(cc);
  } else {
    sbGit.textContent = "sin git";
  }
  sbLang.textContent = currentPath ? chipDe(currentPath).nom : "—";
  sbYo.innerHTML = "";
  if (yo) {
    const d = document.createElement("span");
    d.className = "pt";
    d.style.background = yo.color;
    const t = document.createElement("span");
    t.textContent = yo.name;
    sbYo.appendChild(d); sbYo.appendChild(t);
  }
}
function pintarResaltado() {
  const txt = editor.value;
  const lang = langDe(currentPath);
  // try/catch BLINDADO: un highlighter roto (gramática incompleta, bug de
  // Prism, lo que sea) NUNCA puede tirar una excepción que aborte
  // seleccionar() y deje el editor/sidebar/gutter desincronizados (era
  // EXACTAMENTE el bug del .ts). Si algo falla -> texto plano escapado.
  let html;
  try {
    if (window.Prism && lang && Prism.languages[lang]) {
      html = Prism.highlight(txt, Prism.languages[lang], lang);
    } else if (currentPath && currentPath.endsWith(".py")) {
      html = resaltarPy(txt);   // fallback vanilla si no hay Prism
    } else {
      html = escHtml(txt);
    }
  } catch (e) {
    html = escHtml(txt);        // degradación: plano, pero NO se rompe
  }
  resaltadoCode.innerHTML = html;
  // Gutter: un número por línea (mismo line-height → alineado).
  const n = txt.split("\n").length;
  let g = "";
  for (let i = 1; i <= n; i++) g += i + "\n";
  gutterScroll.textContent = g;
  posicionarLineaActiva();
}
// Banda de la línea donde está el cursor. Reusa LINE_H/PAD_TOP: misma
// matemática que los marcadores de presencia.
function posicionarLineaActiva() {
  if (!currentPath || editor.disabled) {
    lineaActivaEl.style.display = "none";
    return;
  }
  const ln = editor.value.slice(0, editor.selectionStart).split("\n").length;
  lineaActivaEl.style.display = "block";
  lineaActivaEl.style.top =
    (PAD_TOP + (ln - 1) * LINE_H - editor.scrollTop) + "px";
}
editor.addEventListener("input", pintarResaltado);
for (const ev of ["keyup", "click", "select"]) {
  editor.addEventListener(ev, posicionarLineaActiva);
}
editor.addEventListener("scroll", () => {
  resaltadoCode.style.transform =
    "translate(" + (-editor.scrollLeft) + "px," + (-editor.scrollTop) + "px)";
  gutterScroll.style.transform = "translateY(" + (-editor.scrollTop) + "px)";
  posicionarLineaActiva();
});

/*
 * Cuando el usuario edita el textarea, mandamos un UpdateMessage al servidor.
 * La bandera `applyingRemote` evita el caso: servidor manda update -> nosotros
 * cambiamos `editor.value` -> dispara evento `input` -> mandaríamos de vuelta
 * al servidor lo que él acaba de mandarnos. Loop infinito.
 */
editor.addEventListener("input", () => {
  if (applyingRemote) return;
  if (!currentPath) return;
  if (ws.readyState !== WebSocket.OPEN) return;
  files[currentPath] = editor.value;
  ws.send(JSON.stringify({ type: "update", path: currentPath, content: editor.value }));
});

/*
 * Crear un archivo nuevo: pedimos un nombre, lo agregamos localmente con
 * contenido vacío, y mandamos un update vacío al servidor. El servidor lo
 * crea automáticamente porque su workspace.update() crea-si-no-existe.
 */
botonNuevo.addEventListener("click", () => {
  const nombre = prompt("nombre del archivo (ej: main.py, notas.md):");
  if (!nombre) return;
  if (nombre in files) { seleccionar(nombre); return; }
  files[nombre] = "";
  ws.send(JSON.stringify({ type: "update", path: nombre, content: "" }));
  renderLista();
  seleccionar(nombre);
});

function seleccionar(path) {
  currentPath = path;
  actual.textContent = path;
  applyingRemote = true;
  editor.value = files[path] ?? "";
  applyingRemote = false;
  pintarResaltado();
  editor.disabled = false;
  wrap.classList.remove("off");
  editor.focus();
  renderLista();
  renderPresencia();
  renderOwnership();
  renderAdmin();  // el panel admin actúa sobre el archivo abierto
  renderTabs();   // pestaña del archivo abierto
  renderEstado(); // barra de estado (lenguaje del archivo)
  // Abrir un archivo ya es "estar presente ahí": anúncialo.
  enviarPresencia();
}

/*
 * Cabecera de ownership del archivo abierto: sin dueño (botón "reclamar"),
 * tuyo (chip verde), o ajeno (chip ámbar + aviso de que tus cambios se
 * proponen). Es la cara visible de la tesis: "tocas algo ajeno -> se negocia".
 */
function renderOwnership() {
  ownerEl.innerHTML = "";
  reclamarBtn.style.display = "none";
  avisoEl.className = "";
  if (!currentPath) return;

  const dueño = owners[currentPath];
  if (!dueño) {
    // Sin dueño: cualquiera escribe y se aplica directo. Ofrecemos reclamar.
    reclamarBtn.style.display = "";
  } else if (yo && dueño === yo.client_id) {
    const t = document.createElement("span");
    t.className = "tag tuyo";
    t.textContent = "tuyo";
    ownerEl.appendChild(t);
  } else {
    const t = document.createElement("span");
    t.className = "tag ajeno";
    t.textContent = "de " + nombreDe(dueño);
    ownerEl.appendChild(t);
    // Aviso honesto al autor: lo que escribas no se aplica solo, se propone.
    avisoEl.textContent =
      "📝 este archivo es de " + nombreDe(dueño) +
      ". Lo que escribas se le propone para aprobación — no se aplica hasta que diga que sí.";
    avisoEl.className = "on";
  }
}

reclamarBtn.addEventListener("click", () => {
  if (!currentPath || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "claim", path: currentPath }));
});

/*
 * Capa 13: el panel admin se mudó a su PROPIO modal (admin.js) y dejó de
 * ser por-archivo. La primera queja real de uso: repartir owners de a uno
 * en 100 archivos es inusable. `renderAdmin()` la define admin.js (script
 * clásico, mismo scope global; carga después de éste y queda disponible
 * cuando llega cualquier mensaje). app.js solo la INVOCA — desde el
 * handler de ownership, admin_info, seleccionar() y cerrarArchivo() — para
 * que el modal, si está abierto, refleje al instante los cambios. Estado
 * compartido que admin.js usa: `owners`, `usuariosLista`, `esAdmin`, `ws`,
 * `files`, `nombreDe`. Nada de esto se duplica: es el mismo espejo.
 */

/*
 * Diff por líneas, mínimo pero real: LCS clásico (programación dinámica)
 * para no marcar todo como borrado+agregado cuando solo cambió una línea.
 * Devuelve filas {tipo: 'eq'|'add'|'del', texto}. El README pide ver
 * "líneas agregadas, eliminadas y modificadas" — esto es justo eso.
 */
function diffLineas(viejo, nuevo) {
  const a = viejo.split("\n"), b = nuevo.split("\n");
  const n = a.length, m = b.length;
  const lcs = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j]
        ? lcs[i + 1][j + 1] + 1
        : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const filas = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { filas.push({ t: "eq", x: a[i] }); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { filas.push({ t: "del", x: a[i] }); i++; }
    else { filas.push({ t: "add", x: b[j] }); j++; }
  }
  while (i < n) filas.push({ t: "del", x: a[i++] });
  while (j < m) filas.push({ t: "add", x: b[j++] });
  return filas;
}

/*
 * Bandeja del dueño: las propuestas sobre archivos que YO poseo, cada una
 * con su diff y los botones verde/rojo. "Botón verde o rojo. Sin
 * formularios, sin workflows pesados."
 */
function renderPropuestas() {
  // Limpieza: una propuesta deja de ser mía si ya no soy dueño de su path
  // (solté ownership, me desconecté y volví con otro id, etc.).
  for (const id of Object.keys(propuestas)) {
    const p = propuestas[id];
    if (!yo || owners[p.path] !== yo.client_id) delete propuestas[id];
  }
  const lista = Object.values(propuestas);
  propuestasEl.innerHTML = "";
  if (lista.length === 0) { propuestasEl.className = ""; return; }
  propuestasEl.className = "on";

  const h = document.createElement("h3");
  h.textContent = "propuestas para tus archivos (" + lista.length + ")";
  propuestasEl.appendChild(h);

  for (const p of lista) {
    const box = document.createElement("div");
    box.className = "prop";

    const cab = document.createElement("div");
    cab.className = "cab";
    const quien = document.createElement("span");
    quien.className = "quien";
    quien.innerHTML = "<b>" + p.author_name + "</b> propone cambios a <b>" + p.path + "</b>";
    cab.appendChild(quien);

    const acc = document.createElement("div");
    acc.className = "acc";
    const ok = document.createElement("button");
    ok.className = "ok"; ok.textContent = "✓ aprobar";
    ok.addEventListener("click", () => resolver(p.id, true));
    const no = document.createElement("button");
    no.className = "no"; no.textContent = "✗ rechazar";
    no.addEventListener("click", () => resolver(p.id, false));
    acc.appendChild(ok); acc.appendChild(no);
    cab.appendChild(acc);
    box.appendChild(cab);

    const diff = document.createElement("div");
    diff.className = "diff";
    for (const f of diffLineas(files[p.path] ?? "", p.content)) {
      const ln = document.createElement("div");
      ln.className = f.t;
      ln.textContent = (f.t === "add" ? "+ " : f.t === "del" ? "- " : "  ") + f.x;
      diff.appendChild(ln);
    }
    box.appendChild(diff);
    propuestasEl.appendChild(box);
  }
}

function resolver(id, aceptar) {
  if (ws.readyState !== WebSocket.OPEN) return;
  // Optimista: la sacamos de la bandeja ya. El server confirma aplicando
  // (a todos) o, si rechazo, revirtiéndole al autor.
  delete propuestas[id];
  renderPropuestas();
  ws.send(JSON.stringify({ type: "resolve", proposal_id: id, accept: aceptar }));
}

/*
 * Panel de impacto (capa 6). Le dice al dueño, sin que pregunte, qué
 * cambios ajenos tocan archivos suyos. NO pide aprobar/rechazar (eso es
 * ownership); solo entera y deja saltar al archivo afectado. "Antes tenías
 * que recordar dónde se usaba esa función; ahora se hace solo."
 */
function renderImpactos() {
  const lista = Object.entries(impactos);
  impactosEl.innerHTML = "";
  if (lista.length === 0) { impactosEl.className = ""; return; }
  impactosEl.className = "on";

  const h = document.createElement("h3");
  h.textContent = "impacto en tus archivos (" + lista.length + ")";
  impactosEl.appendChild(h);

  for (const [clave, m] of lista) {
    const fila = document.createElement("div");
    fila.className = "imp";

    const izq = document.createElement("div");
    izq.className = "impizq";
    const txt = document.createElement("span");
    const syms = m.symbols.map((s) => "<code>" + s + "</code>").join(", ");
    txt.innerHTML =
      "<b>" + m.author_name + "</b> cambió " + syms +
      " en <b>" + m.source_path + "</b> — afecta tu <b>" + m.affected_path + "</b>";
    izq.appendChild(txt);
    // El POR QUÉ concreto (lo que lo vuelve aviso real y no adorno).
    // textContent: el motivo viene del server con nombres de símbolos,
    // no se interpola como HTML.
    const motivos = m.motivos || [];
    for (let i = 0; i < m.symbols.length; i++) {
      const razon = motivos[i];
      if (!razon) continue;
      const p = document.createElement("div");
      p.className = "por";
      p.textContent = "↳ " + razon;
      izq.appendChild(p);
    }
    fila.appendChild(izq);

    const acc = document.createElement("div");
    acc.className = "acc";
    const ver = document.createElement("button");
    ver.textContent = "ver " + m.affected_path;
    ver.addEventListener("click", () => {
      if (m.affected_path in files) seleccionar(m.affected_path);
    });
    const ok = document.createElement("button");
    ok.textContent = "visto";
    ok.addEventListener("click", () => {
      delete impactos[clave];
      renderImpactos();
    });
    acc.appendChild(ver); acc.appendChild(ok);
    fila.appendChild(acc);
    impactosEl.appendChild(fila);
  }
}

// Iniciales para los puntos del sidebar: el número de "anónimo-3" -> "3".
// Cuando llegue auth y haya nombres reales, esto mostrará la inicial.
function inicial(name) {
  const m = name.match(/(\d+)$/);
  return m ? m[1] : name.slice(0, 2);
}

// Carpetas expandidas (se recuerda entre re-renders). Además, los
// ancestros del archivo abierto se expanden solos para que se vea.
const carpetasAbiertas = new Set();

function _arbol(paths) {
  // Convierte ["a/b.py","a/c.py","x.py"] en un árbol anidado.
  const raiz = { dirs: {}, files: [] };
  for (const p of paths) {
    const partes = p.split("/");
    let nodo = raiz;
    for (let i = 0; i < partes.length - 1; i++) {
      nodo.dirs[partes[i]] = nodo.dirs[partes[i]] || { dirs: {}, files: [] };
      nodo = nodo.dirs[partes[i]];
    }
    nodo.files.push({ nombre: partes[partes.length - 1], path: p });
  }
  return raiz;
}

function renderLista() {
  lista.innerHTML = "";
  const paths = Object.keys(files);
  if (paths.length === 0) {
    const vacio = document.createElement("li");
    vacio.textContent = "— sin archivos —";
    vacio.className = "vacio";
    lista.appendChild(vacio);
    return;
  }
  // El archivo abierto siempre visible: abrimos sus carpetas padre.
  const ancestros = new Set();
  if (currentPath) {
    const partes = currentPath.split("/");
    for (let i = 1; i < partes.length; i++) {
      ancestros.add(partes.slice(0, i).join("/"));
    }
  }

  const pintar = (nodo, prefijo, depth) => {
    for (const nombre of Object.keys(nodo.dirs).sort()) {
      const ruta = prefijo ? prefijo + "/" + nombre : nombre;
      const abierta = carpetasAbiertas.has(ruta) || ancestros.has(ruta);
      const li = document.createElement("li");
      li.className = "dir";
      li.style.paddingLeft = (depth * 14 + 8) + "px";
      const car = document.createElement("span");
      car.className = "car";
      car.textContent = abierta ? "▾" : "▸";
      const nm = document.createElement("span");
      nm.className = "dnombre";
      nm.textContent = nombre;
      li.appendChild(car);
      li.appendChild(nm);
      li.addEventListener("click", () => {
        if (carpetasAbiertas.has(ruta) || ancestros.has(ruta)) {
          carpetasAbiertas.delete(ruta);
        } else {
          carpetasAbiertas.add(ruta);
        }
        renderLista();
      });
      lista.appendChild(li);
      if (abierta) pintar(nodo.dirs[nombre], ruta, depth + 1);
    }
    for (const f of nodo.files.sort((a, b) => a.nombre.localeCompare(b.nombre))) {
      const li = document.createElement("li");
      li.className = "file";
      if (f.path === currentPath) li.classList.add("activo");
      li.style.paddingLeft = (depth * 14 + 22) + "px";

      li.appendChild(chipEl(f.path));  // ícono de tipo (py/ts/go…)
      const nombre = document.createElement("span");
      nombre.className = "fnombre";
      nombre.textContent = f.nombre;
      li.appendChild(nombre);

      const badges = document.createElement("span");
      badges.className = "badges";
      for (const p of Object.values(peers)) {
        if (p.path !== f.path) continue;
        const b = document.createElement("span");
        b.className = "badge";
        b.style.background = p.color;
        b.textContent = inicial(p.name);
        b.title = p.name + " · línea " + p.line;
        badges.appendChild(b);
      }
      const der = document.createElement("span");
      der.className = "der";
      der.appendChild(badges);
      const x = document.createElement("button");
      x.className = "del-x";
      x.textContent = "✕";
      x.title = "eliminar " + f.path;
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        if (ws.readyState !== WebSocket.OPEN) return;
        if (confirm("¿Eliminar " + f.path + "? No se puede deshacer.")) {
          ws.send(JSON.stringify({ type: "delete", path: f.path }));
        }
      });
      der.appendChild(x);
      li.appendChild(der);
      li.addEventListener("click", () => seleccionar(f.path));
      lista.appendChild(li);
    }
  };
  pintar(_arbol(paths), "", 0);
}

/*
 * Presencia dentro del archivo abierto: la lista "quién está aquí" en la
 * cabecera + una marca de color sobre la línea donde cada peer escribe.
 * La marca se reconstruye entera cada vez: con pocos peers es trivial y
 * evita llevar estado de qué nodo es de quién.
 */
function renderPresencia() {
  const aqui = Object.values(peers).filter((p) => p.path === currentPath);

  aquiEl.innerHTML = "";
  for (const p of aqui) {
    const q = document.createElement("span");
    q.className = "quien";
    q.style.background = p.color;
    q.textContent = p.name + " · L" + p.line;
    aquiEl.appendChild(q);
  }

  capaScroll.innerHTML = "";
  for (const p of aqui) {
    const marca = document.createElement("div");
    marca.className = "marca";
    marca.style.top = (PAD_TOP + (p.line - 1) * LINE_H) + "px";

    const tinte = document.createElement("div");
    tinte.className = "tinte";
    tinte.style.background = p.color;
    marca.appendChild(tinte);

    const raya = document.createElement("div");
    raya.className = "raya";
    raya.style.background = p.color;
    marca.appendChild(raya);

    const etiqueta = document.createElement("div");
    etiqueta.className = "etiqueta";
    etiqueta.style.background = p.color;
    etiqueta.textContent = p.name;
    marca.appendChild(etiqueta);

    capaScroll.appendChild(marca);
  }
  capaScroll.style.transform = "translateY(" + (-editor.scrollTop) + "px)";
}

/*
 * Panel Git (capa 8). SOLO LECTURA: rama, cuántos cambios sin commitear,
 * últimos commits, y un botón para re-consultar. El commit se hace en la
 * terminal del dev — la herramienta no se interpone (vive sobre Git, no
 * lo reemplaza). Si el server no tiene git, el panel no aparece.
 */
function renderGit() {
  gitEl.innerHTML = "";
  if (!gitEstado || !gitEstado.available) return;

  const cab = document.createElement("div");
  cab.className = "cab";
  const titulo = document.createElement("span");
  titulo.textContent = "git";
  const act = document.createElement("button");
  act.textContent = "actualizar";
  act.addEventListener("click", () => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "git_refresh" }));
    }
  });
  cab.appendChild(titulo);
  cab.appendChild(act);
  gitEl.appendChild(cab);

  const rama = document.createElement("div");
  rama.className = "rama";
  rama.innerHTML = "rama <b>" + gitEstado.branch + "</b>";
  gitEl.appendChild(rama);

  const n = gitEstado.changes;
  const cambios = document.createElement("div");
  cambios.className = "cambios" + (n === 0 ? " limpio" : "");
  cambios.textContent = n === 0
    ? "sin cambios sin commitear"
    : n + (n === 1 ? " cambio sin commitear" : " cambios sin commitear");
  gitEl.appendChild(cambios);

  if (gitEstado.commits.length) {
    const ol = document.createElement("ol");
    for (const c of gitEstado.commits) {
      const li = document.createElement("li");
      li.textContent = c;
      li.title = c;
      ol.appendChild(li);
    }
    gitEl.appendChild(ol);
  }

  // Capa 9b: commitear desde acá (no hay terminal en el deploy). El autor
  // lo pone el server = vos (capa 7). Sin push todavía (otra capa).
  const form = document.createElement("div");
  form.className = "commitbox";
  const inp = document.createElement("input");
  inp.placeholder = "mensaje de commit…";
  inp.value = gitMsgBorrador;  // no se pierde al re-renderizar el panel
  inp.addEventListener("input", () => { gitMsgBorrador = inp.value; });
  const enviar = () => {
    const m = inp.value.trim();
    if (!m || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "commit", message: m }));
  };
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter") enviar(); });
  const btn = document.createElement("button");
  btn.textContent = "commit";
  btn.addEventListener("click", enviar);
  form.appendChild(inp);
  form.appendChild(btn);
  gitEl.appendChild(form);

  if (gitResultado) {
    const r = document.createElement("div");
    r.className = "gitres " + (gitResultado.ok ? "ok" : "bad");
    r.textContent = gitResultado.detail;
    gitEl.appendChild(r);
  }

  // Capa 10: remoto. clonar (REEMPLAZA el workspace, destructivo) y push.
  // Credenciales EFÍMERAS: el token no se guarda ni en localStorage ni
  // entre re-renders; url/usuario sí quedan en memoria de sesión para no
  // retipearlos. Solo seguro sobre wss (en prod lo es).
  const rem = document.createElement("div");
  rem.className = "remoto";
  const tit = document.createElement("div");
  tit.className = "remtit";
  tit.textContent = "remoto";
  rem.appendChild(tit);

  const url = document.createElement("input");
  url.placeholder = "URL del repo (https://…)";
  url.value = gitRemoto.url;
  url.addEventListener("input", () => { gitRemoto.url = url.value; });
  const usr = document.createElement("input");
  usr.placeholder = "usuario";
  usr.value = gitRemoto.user;
  usr.addEventListener("input", () => { gitRemoto.user = usr.value; });
  const tok = document.createElement("input");
  tok.type = "password";
  tok.placeholder = "token (no se guarda)";
  rem.appendChild(url); rem.appendChild(usr); rem.appendChild(tok);

  const acc = document.createElement("div");
  acc.className = "remacc";
  const bClon = document.createElement("button");
  bClon.className = "no";
  bClon.textContent = "clonar (reemplaza)";
  bClon.addEventListener("click", () => {
    if (ws.readyState !== WebSocket.OPEN) return;
    if (!url.value.trim()) { gitResultado = { ok: false, detail: "falta la URL" }; renderGit(); return; }
    if (!confirm("Clonar REEMPLAZA todo el workspace actual por ese repo. " +
                 "Lo no pusheado se pierde. ¿Seguro?")) return;
    ws.send(JSON.stringify({
      type: "clone", url: url.value.trim(),
      username: usr.value.trim(), token: tok.value,
    }));
    tok.value = "";  // el token no sobrevive a la acción
  });
  const bPush = document.createElement("button");
  bPush.textContent = "push";
  bPush.addEventListener("click", () => {
    if (ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: "push", username: usr.value.trim(),
      token: tok.value, url: url.value.trim(),
    }));
    tok.value = "";
  });
  acc.appendChild(bClon); acc.appendChild(bPush);
  rem.appendChild(acc);
  gitEl.appendChild(rem);
}

renderLista();
