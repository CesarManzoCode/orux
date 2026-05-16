import { useState } from "react";
import { useStore } from "../useStore";
import { nuevoArchivo, commitear, gitRefresh, clonar, pushear } from "../store";
import { FileTree } from "./FileTree";

function PanelArchivos() {
  return (
    <>
      <div className="h2">archivos</div>
      <button className="btn-nuevo" onClick={() => {
        const n = prompt("nombre del archivo (ej: src/main.py)");
        if (n && n.trim()) nuevoArchivo(n.trim());
      }}>+ nuevo archivo</button>
      <FileTree />
    </>
  );
}

function PanelGit() {
  const s = useStore();
  const g = s.git;
  const [msg, setMsg] = useState("");
  // Credenciales EFÍMERAS: el token vive sólo en este estado y se limpia
  // tras la acción; url/usuario quedan en memoria de sesión para no
  // retipear. NADA va a localStorage (igual que el cliente vanilla).
  const [url, setUrl] = useState("");
  const [user, setUser] = useState("");
  const [tok, setTok] = useState("");

  return (
    <div className="gitp">
      <div className="cab">
        <span>control de versiones</span>
        <button onClick={gitRefresh}>actualizar</button>
      </div>
      {!g || !g.available ? (
        <div className="cambios limpio">git no disponible</div>
      ) : (
        <>
          <div className="rama">rama <b>{g.branch}</b></div>
          <div className={"cambios" + (g.changes === 0 ? " limpio" : "")}>
            {g.changes === 0 ? "sin cambios sin commitear"
              : g.changes + (g.changes === 1 ? " cambio sin commitear" : " cambios sin commitear")}
          </div>
          {g.commits.length > 0 && (
            <ol>{g.commits.map((c, i) => <li key={i} title={c}>{c}</li>)}</ol>
          )}
          <div className="commitbox">
            <input placeholder="mensaje de commit…" value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && msg.trim()) { commitear(msg.trim()); setMsg(""); } }} />
            <button onClick={() => { if (msg.trim()) { commitear(msg.trim()); setMsg(""); } }}>commit</button>
          </div>
          {s.gitResult && (
            <div className={"res " + (s.gitResult.ok ? "ok" : "bad")}>{s.gitResult.detail}</div>
          )}
          <div className="remoto">
            <div className="remtit">remoto</div>
            <input placeholder="URL del repo (https://…)" value={url} onChange={(e) => setUrl(e.target.value)} />
            <input placeholder="usuario" value={user} onChange={(e) => setUser(e.target.value)} />
            <input type="password" placeholder="token (no se guarda)" value={tok} onChange={(e) => setTok(e.target.value)} />
            <div className="remacc">
              <button className="no" onClick={() => {
                if (!url.trim()) return;
                if (!confirm("Clonar REEMPLAZA todo el workspace actual por ese repo. Lo no pusheado se pierde. ¿Seguro?")) return;
                clonar(url.trim(), user.trim(), tok);
                setTok("");
              }}>clonar (reemplaza)</button>
              <button onClick={() => { pushear(user.trim(), tok, url.trim()); setTok(""); }}>push</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function Sidebar({ vista }: { vista: "archivos" | "git" }) {
  return (
    <aside className="sidebar isla">
      {vista === "archivos" ? <PanelArchivos /> : <PanelGit />}
    </aside>
  );
}
