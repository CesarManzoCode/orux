import { useState } from "react";
import {
  FilePlus2, RefreshCw, GitCommitHorizontal, ExternalLink,
  GitBranch, DownloadCloud, UploadCloud,
} from "lucide-react";
import { useStore } from "../useStore";
import { commitear, gitRefresh, clonar, pushear, emitToast } from "../store";
import { useI18n } from "../i18n";
import { FileTree } from "./FileTree";
import { NuevoArchivoModal } from "./NuevoArchivoModal";
import { ConfirmDialog } from "./ConfirmDialog";

function PanelArchivos() {
  const { t } = useI18n();
  // Antes era un `prompt()` nativo. Ahora un modal propio que valida con
  // las mismas reglas que el backend (validate.ts ↔ paths.py) y muestra
  // mensajes claros en vez de "el server rebota silencioso".
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <div className="h2">{t.sb_explorer}</div>
      <button
        className="btn-nuevo"
        onClick={() => setAbierto(true)}
        aria-label={t.sb_new_file}
      >
        <FilePlus2 size={15} /> {t.sb_new_file}
      </button>
      <FileTree />
      {abierto && <NuevoArchivoModal onClose={() => setAbierto(false)} />}
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
  // Modo del bloque REMOTO. Antes se mostraban los 4 inputs siempre y los
  // placeholders intentaban explicar cuándo aplicaba cada uno — confuso y
  // visualmente encimado. Ahora el usuario elige primero PÚBLICO (clone
  // sin credenciales, único campo: URL) o PRIVADO (clone+push con token).
  // Los datos se preservan al cambiar de modo: si alguien llenó URL en
  // público y se cambia a privado, no pierde lo escrito.
  const [modo, setModo] = useState<"publico" | "privado">("publico");
  // Reemplaza window.confirm() del clone — modal estilizado y accesible.
  const [pidiendoClone, setPidiendoClone] = useState(false);

  return (
    <div className="gitp">
      <div className="cab">
        <span>{t.sg_title}</span>
        <button onClick={gitRefresh} title={t.sg_refresh_title} aria-label={t.sg_refresh_title}>
          <RefreshCw size={11} /> {t.sg_refresh}
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
              <GitBranch size={12} /> <b>{g.branch}</b>
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
              aria-label={t.sg_commit_placeholder}
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && msg.trim()) { commitear(msg.trim()); setMsg(""); }
              }}
            />
            <button
              onClick={() => { if (msg.trim()) { commitear(msg.trim()); setMsg(""); } }}
              aria-label={t.sg_commit_btn}
            >
              <GitCommitHorizontal size={13} /> {t.sg_commit_btn}
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
          <div className="remoto" role="group" aria-label={t.sg_remote_label}>
            <div className="remtit" id="git-remote-h">{t.sg_remote_label}</div>

            {/* Segmented control: público vs privado. Sólo se renderiza el
                formulario del modo activo — eso es lo que descomprime la
                vista (antes había 4 inputs amontonados todo el tiempo). */}
            <div className="rem-tabs" role="tablist" aria-labelledby="git-remote-h">
              <button
                type="button" role="tab"
                aria-selected={modo === "publico"}
                className={"rem-tab" + (modo === "publico" ? " on" : "")}
                onClick={() => setModo("publico")}
              >
                {t.sg_mode_public}
              </button>
              <button
                type="button" role="tab"
                aria-selected={modo === "privado"}
                className={"rem-tab" + (modo === "privado" ? " on" : "")}
                onClick={() => setModo("privado")}
              >
                {t.sg_mode_private}
              </button>
            </div>
            <p className="rem-hint">
              {modo === "publico" ? t.sg_mode_public_hint : t.sg_mode_private_hint}
            </p>

            {/* URL: común a los dos modos. Va siempre. */}
            <label className="rem-field">
              <span className="rem-lbl">{t.sg_lbl_url}</span>
              <input
                placeholder={t.sg_url_placeholder}
                aria-label={t.sg_lbl_url}
                autoComplete="off" spellCheck={false}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>

            {/* Credenciales y rama destino — sólo modo privado.
                En modo público no aplican (clone sin auth, sin push). */}
            {modo === "privado" && (
              <>
                <label className="rem-field">
                  <span className="rem-lbl">{t.sg_lbl_user}</span>
                  <input
                    placeholder={t.sg_user_placeholder}
                    aria-label={t.sg_lbl_user}
                    autoComplete="username" spellCheck={false}
                    value={user}
                    onChange={(e) => setUser(e.target.value)}
                  />
                </label>
                <label className="rem-field">
                  <span className="rem-lbl">
                    {t.sg_lbl_token}
                    <span className="rem-lbl-hint"> · {t.sg_lbl_token_hint}</span>
                  </span>
                  <input
                    type="password"
                    placeholder={t.sg_token_placeholder}
                    aria-label={t.sg_lbl_token}
                    autoComplete="off"
                    value={tok}
                    onChange={(e) => setTok(e.target.value)}
                  />
                </label>
                <label className="rem-field">
                  <span className="rem-lbl">
                    {t.sg_lbl_branch}
                    <span className="rem-lbl-hint"> · {t.sg_lbl_branch_hint}</span>
                  </span>
                  <input
                    placeholder={t.sg_branch_placeholder}
                    aria-label={t.sg_lbl_branch}
                    autoComplete="off" spellCheck={false}
                    value={rama}
                    onChange={(e) => setRama(e.target.value)}
                  />
                </label>
              </>
            )}

            <div className="remacc">
              <button
                className="no"
                onClick={() => { if (!url.trim()) return; setPidiendoClone(true); }}
                aria-label={t.sg_clone_btn}
              >
                <DownloadCloud size={12} /> {t.sg_clone_btn}
              </button>
              {/* Push sólo en privado: pushear sin auth no funciona contra
                  ningún remote real. Si el usuario está en público y quiere
                  pushear, cambia a privado y los datos del URL se preservan. */}
              {modo === "privado" && (
                <button
                  onClick={() => { pushear(user.trim(), tok, url.trim(), rama.trim()); setTok(""); }}
                  aria-label={t.sg_push_btn}
                >
                  <UploadCloud size={12} /> {t.sg_push_btn}
                </button>
              )}
            </div>
          </div>
          {pidiendoClone && (
            <ConfirmDialog
              title={t.confirm_clone_title}
              message={t.confirm_clone_msg}
              okLabel={t.confirm_clone_ok}
              cancelLabel={t.confirm_default_cancel}
              tone="warn"
              onCancel={() => setPidiendoClone(false)}
              onConfirm={() => {
                setPidiendoClone(false);
                // Modo público manda credenciales vacías (clone anónimo).
                // Si el usuario rellenó user/token en privado y luego se
                // cambió a público, no queremos enviar esos restos.
                if (modo === "publico") {
                  clonar(url.trim(), "", "");
                } else {
                  clonar(url.trim(), user.trim(), tok);
                  setTok("");
                }
                emitToast(t.toast_clone_started, "ok");
              }}
            />
          )}
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
