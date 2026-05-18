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
import { Trays } from "./components/Trays";
import { Editor } from "./components/Editor";
import { StatusBar } from "./components/StatusBar";
import { AdminModal } from "./components/AdminModal";
import { Inspector } from "./components/Inspector";

export function App() {
  const s = useStore();
  const [vista, setVista] = useState<"archivos" | "git">("archivos");
  const [adminOpen, setAdminOpen] = useState(false);
  // Capa 26: el inspector se puede colapsar (pantallas medianas, o quien
  // quiere todo el ancho para el código). La preferencia persiste — una
  // herramienta de uso diario respeta cómo la dejaste.
  const [inspOpen, setInspOpen] = useState(
    () => localStorage.getItem("laidea_insp") !== "0",
  );
  const toggleInsp = () => {
    const next = !inspOpen;
    localStorage.setItem("laidea_insp", next ? "1" : "0");
    setInspOpen(next);
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
      <TopBar />
      <div className="layout">
        <Rail
          vista={vista}
          setVista={setVista}
          abrirAdmin={() => setAdminOpen(true)}
          inspOpen={inspOpen}
          toggleInsp={toggleInsp}
        />
        <Sidebar vista={vista} />
        <main className="main isla">
          <Tabs />
          <ContextBar />
          <Trays />
          <Editor />
        </main>
        {inspOpen && <Inspector onClose={toggleInsp} />}
      </div>
      <StatusBar />
      {adminOpen && s.esAdmin && <AdminModal onClose={() => setAdminOpen(false)} />}
    </div>
  );
}
