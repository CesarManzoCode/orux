import { useEffect, useState } from "react";
import { useStore } from "./useStore";
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

export function App() {
  const s = useStore();
  const [vista, setVista] = useState<"archivos" | "git">("archivos");
  const [adminOpen, setAdminOpen] = useState(false);

  // Si dejás de ser admin (re-init tras un clone), el modal se cierra solo.
  useEffect(() => { if (!s.esAdmin && adminOpen) setAdminOpen(false); }, [s.esAdmin, adminOpen]);

  // La app está cerrada por dos compuertas: sin autenticar -> login;
  // autenticado pero sin equipo -> lobby (capa 15). Sólo dentro de un
  // equipo se ve el IDE, y es el de ESE equipo y de ningún otro.
  if (!s.authed) return <Login />;
  if (s.fase !== "team") return <Lobby />;

  return (
    <div className="app">
      <TopBar />
      <div className="layout">
        <Rail vista={vista} setVista={setVista} abrirAdmin={() => setAdminOpen(true)} />
        <Sidebar vista={vista} />
        <main className="main isla">
          <Tabs />
          <ContextBar />
          <Trays />
          <Editor />
        </main>
      </div>
      <StatusBar />
      {adminOpen && s.esAdmin && <AdminModal onClose={() => setAdminOpen(false)} />}
    </div>
  );
}
