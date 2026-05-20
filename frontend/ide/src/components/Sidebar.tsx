import { useState } from "react";
import {
  FilePlus2, RefreshCw, GitCommitHorizontal, ExternalLink,
  GitBranch, DownloadCloud, UploadCloud,
} from "lucide-react";
import { useStore } from "../useStore";
import { nuevoArchivo, commitear, gitRefresh, clonar, pushear } from "../store";
import { FileTree } from "./FileTree";

function PanelArchivos() {
  return (
    <>
      {/* Encabezado de sección con conteo: estructura legible sin gritar. */}
      <div className="h2">explorador</div>
      <button className="btn-nuevo" onClick={() => {
        const n = prompt("nombre del archivo (ej: src/main.py)");
        if (n && n.trim()) nuevoArchivo(n.trim());
      }}>
        <FilePlus2 size={15} /> nuevo archivo
      </button>
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
  const [rama, setRama] = useState("");  // capa 21b: destino del push

  return (
    <div className="gitp">
      <div className="cab">
        <span>control de versiones</span>
        <button onClick={gitRefresh} title="releer estado de git">
          <RefreshCw size={11} style={{ verticalAlign: "-1px" }} /> actualizar
        </button>
      </div>
      {!g || !g.available ? (
        // Estado vacío con voz: no es un error, es contexto.
        <div className="empty compacto">
          <div className="empty-ic"><GitBranch size={20} /></div>
          <div className="empty-tit">Sin git</div>
          <div className="empty-sub">
            Este workspace no es un repositorio git, o git no está disponible.
          </div>
        </div>
      ) : (
        <>
          <div className="estado">
            <span className="rama"><GitBranch size={12} style={{ verticalAlign: "-2px" }} /> <b>{g.branch}</b></span>
            <span className={"cambios" + (g.changes === 0 ? " limpio" : "")}>
              {g.changes === 0 ? "limpio"
                : g.changes + (g.changes === 1 ? " cambio" : " cambios")}
            </span>
          </div>
          {g.commits.length > 0 && (
            <ol>{g.commits.map((c, i) => <li key={i} title={c}>{c}</li>)}</ol>
          )}
          <div className="commitbox">
            <input placeholder="mensaje de commit…" value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && msg.trim()) { commitear(msg.trim()); setMsg(""); } }} />
            <button onClick={() => { if (msg.trim()) { commitear(msg.trim()); setMsg(""); } }}>
              <GitCommitHorizontal size={13} style={{ verticalAlign: "-2px" }} /> commit
            </button>
          </div>
          {s.gitResult && (
            <div className={"res " + (s.gitResult.ok ? "ok" : "bad")}>
              {s.gitResult.detail}
              {/* Capa 21: orux pusheó la rama del equipo; el PR lo
                  abre el humano en GitHub (integración, no reemplazo). */}
              {s.gitResult.pr_url && (
                <a
                  className="prlink"
                  href={s.gitResult.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  abrir PR en GitHub <ExternalLink size={11} />
                </a>
              )}
            </div>
          )}
          <div className="remoto">
            <div className="remtit">remoto</div>
            <input placeholder="URL del repo (https://…)" value={url} onChange={(e) => setUrl(e.target.value)} />
            <input placeholder="usuario" value={user} onChange={(e) => setUser(e.target.value)} />
            <input type="password" placeholder="token (no se guarda)" value={tok} onChange={(e) => setTok(e.target.value)} />
            {/* Capa 21b: destino del push. Vacío = rama del equipo (seguro,
                abre PR). "main"/otra = push directo sin forzar. */}
            <input
              placeholder="rama destino (vacío = rama del equipo + PR)"
              value={rama}
              onChange={(e) => setRama(e.target.value)}
            />
            <div className="remacc">
              <button className="no" onClick={() => {
                if (!url.trim()) return;
                if (!confirm("Clonar REEMPLAZA todo el workspace actual por ese repo. Lo no pusheado se pierde. ¿Seguro?")) return;
                clonar(url.trim(), user.trim(), tok);
                setTok("");
              }}><DownloadCloud size={12} style={{ verticalAlign: "-2px" }} /> clonar</button>
              <button onClick={() => { pushear(user.trim(), tok, url.trim(), rama.trim()); setTok(""); }}>
                <UploadCloud size={12} style={{ verticalAlign: "-2px" }} /> push
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function Sidebar({
  vista,
  width,
}: {
  vista: "archivos" | "git";
  // Si el usuario redimensionó el panel, gana sobre los valores del CSS.
  // Si no, undefined → manda la regla del CSS (incluyendo media queries).
  width?: number;
}) {
  return (
    <aside
      className="sidebar isla"
      style={width != null ? { width: width + "px" } : undefined}
    >
      {vista === "archivos" ? <PanelArchivos /> : <PanelGit />}
    </aside>
  );
}
