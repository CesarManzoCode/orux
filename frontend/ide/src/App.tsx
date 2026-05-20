import { useEffect, useState } from "react";
import { useStore } from "./useStore";
import { getState, guardar } from "./store";
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
  const [vista, setVista] = useState<"archivos" | "git">("archivos");
  const [adminOpen, setAdminOpen] = useState(false);
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
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        guardar(getState().currentPath);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
    </div>
  );
}
