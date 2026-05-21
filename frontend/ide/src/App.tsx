import { useEffect, useState } from "react";
import { useStore } from "./useStore";
import { getState, guardar, contarDrafts, resolver, seleccionar } from "./store";
import { Login } from "./components/Login";
import { Lobby } from "./components/Lobby";
import { TopBar } from "./components/TopBar";
import { Rail } from "./components/Rail";
import { Sidebar } from "./components/Sidebar";
import { Tabs } from "./components/Tabs";
import { ContextBar } from "./components/ContextBar";
import { Editor } from "./components/Editor";
import { StatusBar } from "./components/StatusBar";
import { AdminModal } from "./components/AdminModal";
import { Inspector } from "./components/Inspector";
import { Splitter } from "./components/Splitter";
import { KbdHelp } from "./components/KbdHelp";
import { useI18n } from "./i18n";

// Capa 27 — Anchos redimensionables del Sidebar y el Inspector.
// Límites: dejamos respirar al editor (mínimos generosos) sin que ningún
// panel acapare la ventana (máximos contenidos).
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 520;
const SIDEBAR_DEF = 248;
const INSP_MIN = 240;
const INSP_MAX = 560;
const INSP_DEF = 312;

function leerAncho(key: string, def: number, min: number, max: number): number {
  // localStorage puede tener basura (otro origen, mano del usuario): clamp.
  const raw = localStorage.getItem(key);
  const n = raw ? parseInt(raw, 10) : NaN;
  if (!Number.isFinite(n)) return def;
  return Math.min(max, Math.max(min, n));
}

export function App() {
  const s = useStore();
  const { t } = useI18n();
  const [vista, setVista] = useState<"archivos" | "git">("archivos");
  const [adminOpen, setAdminOpen] = useState(false);
  // Capa 30 — Cheatsheet de atajos y toast inline. El toast es texto + ttl;
  // suficiente para confirmar "aprobada"/"rechazada" tras un atajo (cuando
  // el ojo no estaba en el botón). Mismo patrón micro que el del Hub.
  const [kbdOpen, setKbdOpen] = useState(false);
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null);
  // Capa 26: el inspector se puede colapsar (pantallas medianas, o quien
  // quiere todo el ancho para el código). La preferencia persiste — una
  // herramienta de uso diario respeta cómo la dejaste.
  const [inspOpen, setInspOpen] = useState(
    () => localStorage.getItem("orux_insp") !== "0",
  );
  const toggleInsp = () => {
    const next = !inspOpen;
    localStorage.setItem("orux_insp", next ? "1" : "0");
    setInspOpen(next);
  };

  // Capa 27 — anchos redimensionables (Sidebar y Inspector). El ancho
  // ACTUAL vive en estado y se persiste a localStorage en cada cambio:
  // es un número (cero costo), y así el ancho sigue ahí si la pestaña
  // se cierra a mitad de arrastre.
  const [wSidebar, setWSidebar] = useState(() =>
    leerAncho("orux_w_side", SIDEBAR_DEF, SIDEBAR_MIN, SIDEBAR_MAX),
  );
  const [wInsp, setWInsp] = useState(() =>
    leerAncho("orux_w_insp", INSP_DEF, INSP_MIN, INSP_MAX),
  );
  useEffect(() => { localStorage.setItem("orux_w_side", String(wSidebar)); }, [wSidebar]);
  useEffect(() => { localStorage.setItem("orux_w_insp", String(wInsp)); }, [wInsp]);

  const onResizeSide = (dx: number) => {
    setWSidebar((w) =>
      Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, w + dx)),
    );
  };
  const onResizeInsp = (dx: number) => {
    setWInsp((w) =>
      Math.min(INSP_MAX, Math.max(INSP_MIN, w + dx)),
    );
  };

  // Si dejás de ser admin (re-init tras un clone), el modal se cierra solo.
  useEffect(() => { if (!s.esAdmin && adminOpen) setAdminOpen(false); }, [s.esAdmin, adminOpen]);

  // Capa 19: Ctrl+S / Cmd+S global = checkpoint del archivo abierto. El
  // Editor ya lo captura cuando el textarea tiene foco; este handler cubre
  // el resto (el reflejo del dev no depende de dónde esté el foco) y
  // bloquea el "guardar página" del navegador siempre.
  //
  // Capa 30: este mismo handler también canaliza los atajos de coordinación
  // (Alt+A/R/J/K y «?»). Son aceleradores del Inspector — no inventan
  // protocolo; reusan `resolver` y `seleccionar`. Reglas para no romper el
  // editor: Alt-* se ignora si el target es un campo de texto editable
  // (Alt+letra ya escribe en algunos layouts); «?» se ignora si el foco
  // está en input/textarea/contenteditable.
  useEffect(() => {
    function esCampoEditable(el: EventTarget | null): boolean {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return true;
      return el.isContentEditable;
    }
    function mostrarToast(text: string, ok = true) {
      setToast({ text, ok });
      setTimeout(() => setToast((cur) => (cur && cur.text === text ? null : cur)), 1800);
    }
    // Propuestas esperando MI review (yo soy dueño). Reusa la misma lógica
    // que el Inspector — sin selectores derivados nuevos para no inflar el
    // store por una feature de polish.
    function propuestasParaMi() {
      const st = getState();
      const yo = st.yo?.client_id;
      if (!yo) return [];
      return Object.values(st.proposals).filter(
        (p) => st.owners[p.path] === yo,
      );
    }
    function archivosConPropPendiente(): string[] {
      // Únicos paths con propuesta-para-mí, ordenados (estabilidad de
      // navegación: la lista no debe bailar entre Alt+J consecutivos).
      const ps = propuestasParaMi();
      return [...new Set(ps.map((p) => p.path))].sort();
    }
    function navegar(delta: 1 | -1) {
      const paths = archivosConPropPendiente();
      if (paths.length === 0) { mostrarToast(t.kbd_toast_no_targets, false); return; }
      const actual = getState().currentPath;
      const idx = actual ? paths.indexOf(actual) : -1;
      // Si el archivo abierto no está en la lista, J va al primero; K al último.
      const nextIdx = idx < 0
        ? (delta > 0 ? 0 : paths.length - 1)
        : (idx + delta + paths.length) % paths.length;
      seleccionar(paths[nextIdx]);
    }

    function onKey(e: KeyboardEvent) {
      // Ctrl/Cmd+S — capa 19, intacto.
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        guardar(getState().currentPath);
        return;
      }
      // Atajos Alt-* (sin Ctrl/Meta/Shift): aceleradores del Inspector.
      // Bloqueamos si el foco está editando texto (evita que Alt+A escriba
      // un carácter especial según layout). Los demás atajos del editor
      // (que no usan Alt) siguen funcionando dentro del textarea.
      if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        if (esCampoEditable(e.target)) return;
        const k = e.key.toLowerCase();
        if (k === "a" || k === "r") {
          const ps = propuestasParaMi();
          if (ps.length === 0) {
            e.preventDefault();
            mostrarToast(t.kbd_toast_no_props, false);
            return;
          }
          // Preferir la propuesta del archivo abierto (lo que el ojo está
          // mirando); si no hay, tomar la primera global.
          const cur = getState().currentPath;
          const target = ps.find((p) => p.path === cur) ?? ps[0];
          e.preventDefault();
          resolver(target.id, k === "a");
          mostrarToast(
            (k === "a" ? t.kbd_toast_approved : t.kbd_toast_rejected) + " · " + target.path,
            k === "a",
          );
          return;
        }
        if (k === "j" || k === "k") {
          e.preventDefault();
          navegar(k === "j" ? 1 : -1);
          return;
        }
      }
      // «?» abre la hoja de atajos. En el layout US es Shift+/, así que
      // chequeamos por `key` directamente (es independiente del layout).
      // Lo ignoramos si el foco está editando texto (no querés que abrir
      // ayuda interrumpa una búsqueda).
      if (e.key === "?" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (esCampoEditable(e.target)) return;
        e.preventDefault();
        setKbdOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [t]);

  // Pulido pre-mercado: warning al cerrar pestaña / recargar / navegar si
  // hay drafts (propuestas locales sin enviar al server). Sin esto, capa 28
  // perdía silenciosamente todo lo escrito en archivos ajenos. El mensaje
  // de `returnValue` es opcional — los navegadores modernos muestran el
  // suyo por seguridad ("¿salir del sitio?"), pero seteándolo nos
  // aseguramos que beforeunload haga el prompt.
  //
  // No incluimos `dirty` "solo del dueño" (sin draft): ese contenido YA
  // viajó al server, lo único pendiente es Ctrl+S para análisis. Perder
  // el dot no es pérdida de trabajo. Solo gateamos cuando hay drafts.
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (contarDrafts() === 0) return;
      // El standard moderno: preventDefault + setear returnValue. Mensajes
      // custom ya no se muestran (los navegadores los reemplazaron por
      // genéricos por seguridad), pero el prompt aparece.
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  // La app está cerrada por dos compuertas: sin autenticar -> login;
  // autenticado pero sin equipo -> lobby (capa 15). Sólo dentro de un
  // equipo se ve el IDE, y es el de ESE equipo y de ningún otro.
  if (!s.authed) return <Login />;
  if (s.fase !== "team") return <Lobby />;

  return (
    <div className={"app" + (inspOpen ? "" : " sin-insp")}>
      <TopBar inspOpen={inspOpen} toggleInsp={toggleInsp} />
      <div className="layout">
        <Rail
          vista={vista}
          setVista={setVista}
          abrirAdmin={() => setAdminOpen(true)}
        />
        <Sidebar vista={vista} width={wSidebar} />
        <Splitter
          lado="left"
          ariaLabel="redimensionar explorador"
          onResize={onResizeSide}
        />
        <main className="main isla">
          <Tabs />
          <ContextBar />
          <Editor />
        </main>
        {inspOpen && (
          <>
            <Splitter
              lado="right"
              ariaLabel="redimensionar inspector"
              onResize={onResizeInsp}
            />
            <Inspector onClose={toggleInsp} width={wInsp} />
          </>
        )}
      </div>
      <StatusBar />
      {adminOpen && s.esAdmin && <AdminModal onClose={() => setAdminOpen(false)} />}
      {kbdOpen && <KbdHelp onClose={() => setKbdOpen(false)} />}
      {toast && (
        <div className={"kbd-toast " + (toast.ok ? "ok" : "warn")} role="status">
          {toast.text}
        </div>
      )}
    </div>
  );
}
