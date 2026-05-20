import { useState } from "react";
import {
  FilePlus2, RefreshCw, GitCommitHorizontal, ExternalLink,
  GitBranch, DownloadCloud, UploadCloud,
} from "lucide-react";
import { useStore } from "../useStore";
import { nuevoArchivo, commitear, gitRefresh, clonar, pushear } from "../store";
import { useI18n } from "../i18n";
import { FileTree } from "./FileTree";

function PanelArchivos() {
  const { t } = useI18n();
  return (
    <>
      <div className="h2">{t.sb_explorer}</div>
      <button className="btn-nuevo" onClick={() => {
        const n = prompt(t.sb_new_file_prompt);
        if (n && n.trim()) nuevoArchivo(n.trim());
      }}>
        <FilePlus2 size={15} /> {t.sb_new_file}
      </button>
      <FileTree />
    </>
  );
}

function PanelGit() {
  const s = useStore();
  const { t } = useI18n();
  const g = s.git;
  const [msg, setMsg] = useState("");
  const [url, setUrl] = useState("");
  const [user, setUser] = useState("");
  const [tok, setTok] = useState("");
  const [rama, setRama] = useState("");

  return (
    <div className="gitp">
      <div className="cab">
        <span>{t.sg_title}</span>
        <button onClick={gitRefresh} title={t.sg_refresh_title}>
          <RefreshCw size={11} style={{ verticalAlign: "-1px" }} /> {t.sg_refresh}
        </button>
      </div>
      {!g || !g.available ? (
        <div className="empty compacto">
          <div className="empty-ic"><GitBranch size={20} /></div>
          <div className="empty-tit">{t.sg_no_git_title}</div>
          <div className="empty-sub">{t.sg_no_git_sub}</div>
        </div>
      ) : (
        <>
          <div className="estado">
            <span className="rama">
              <GitBranch size={12} style={{ verticalAlign: "-2px" }} /> <b>{g.branch}</b>
            </span>
            <span className={"cambios" + (g.changes === 0 ? " limpio" : "")}>
              {g.changes === 0
                ? t.sg_clean
                : g.changes + " " + (g.changes === 1 ? t.sg_change : t.sg_changes)}
            </span>
          </div>
          {g.commits.length > 0 && (
            <ol>{g.commits.map((c, i) => <li key={i} title={c}>{c}</li>)}</ol>
          )}
          <div className="commitbox">
            <input
              placeholder={t.sg_commit_placeholder}
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && msg.trim()) { commitear(msg.trim()); setMsg(""); }
              }}
            />
            <button onClick={() => { if (msg.trim()) { commitear(msg.trim()); setMsg(""); } }}>
              <GitCommitHorizontal size={13} style={{ verticalAlign: "-2px" }} /> {t.sg_commit_btn}
            </button>
          </div>
          {s.gitResult && (
            <div className={"res " + (s.gitResult.ok ? "ok" : "bad")}>
              {s.gitResult.detail}
              {s.gitResult.pr_url && (
                <a
                  className="prlink"
                  href={s.gitResult.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t.sg_pr_link} <ExternalLink size={11} />
                </a>
              )}
            </div>
          )}
          <div className="remoto">
            <div className="remtit">{t.sg_remote_label}</div>
            <input placeholder={t.sg_url_placeholder} value={url} onChange={(e) => setUrl(e.target.value)} />
            <input placeholder={t.sg_user_placeholder} value={user} onChange={(e) => setUser(e.target.value)} />
            <input type="password" placeholder={t.sg_token_placeholder} value={tok} onChange={(e) => setTok(e.target.value)} />
            <input
              placeholder={t.sg_branch_placeholder}
              value={rama}
              onChange={(e) => setRama(e.target.value)}
            />
            <div className="remacc">
              <button className="no" onClick={() => {
                if (!url.trim()) return;
                if (!confirm(t.sg_clone_confirm)) return;
                clonar(url.trim(), user.trim(), tok);
                setTok("");
              }}>
                <DownloadCloud size={12} style={{ verticalAlign: "-2px" }} /> {t.sg_clone_btn}
              </button>
              <button onClick={() => { pushear(user.trim(), tok, url.trim(), rama.trim()); setTok(""); }}>
                <UploadCloud size={12} style={{ verticalAlign: "-2px" }} /> {t.sg_push_btn}
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
