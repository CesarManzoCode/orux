import { KeyRound, Radio, Waypoints, Pencil, GitPullRequest, Send } from "lucide-react";
import { useStore } from "../useStore";
import {
  reclamar, nombreDe, impactosQueAfectan, severidadMax, presentesEn,
} from "../store";
import { useI18n } from "../i18n";

export function ContextBar() {
  const s = useStore();
  const { t } = useI18n();
  const path = s.currentPath;
  if (!path) return <div className="ctxbar vacia" />;

  const aqui = presentesEn(path);
  const due = s.owners[path];
  const esMio = s.yo && due === s.yo.client_id;
  const riesgo = severidadMax(impactosQueAfectan(path));
  const proponiendo = !!due && !esMio;
  // ✱ Borrador: el usuario escribió en un archivo de OTRO dueño y aún
  // no pulsó Ctrl+S. Lo que escribió vive SOLO en su navegador —
  // hacer esto visible en la ContextBar elimina la pregunta "¿se está
  // viendo lo que escribo?" del testing real (capa 28).
  const tieneDraft = !!s.drafts[path];

  return (
    <div className="ctxbar">
      <span
        className={"ctx-mode " + (proponiendo ? "prop" : "live")}
        title={proponiendo ? t.ctx_prop_title : t.ctx_live_title}
      >
        {proponiendo ? <GitPullRequest size={12} /> : <Pencil size={12} />}
        {proponiendo ? (
          <>{t.ctx_mode_prop} <i className="ctx-arrow">→</i> {nombreDe(due!)}</>
        ) : (
          <>{t.ctx_mode_live}</>
        )}
      </span>

      {proponiendo && (
        <span className="ctx-nota">
          {t.ctx_prop_note(nombreDe(due!))}
        </span>
      )}

      {tieneDraft && (
        <span
          className="ctx-draft"
          title={t.ctx_draft_title}
        >
          <Send size={11} />
          {t.ctx_draft_label}
        </span>
      )}

      <span className="ctx-div" />

      <span className="ctx-seg">
        <Radio size={12} className="ctx-i" />
        {aqui.length === 0 ? (
          <span className="ctx-mut">{t.ctx_alone}</span>
        ) : (
          <span className="aqui">
            {aqui.map((p) => (
              <span key={p.client_id} className="quien" style={{ background: p.color }}>
                {p.name} · {p.line}
              </span>
            ))}
          </span>
        )}
      </span>

      {(!due || esMio) && (
        <>
          <span className="ctx-div" />
          <span className="ctx-seg">
            <KeyRound size={12} className="ctx-i" />
            {!due ? (
              <button className="reclamar" onClick={() => reclamar(path)}>
                {t.ctx_reclaim}
              </button>
            ) : (
              <span className="otag tuyo">{t.ctx_mine}</span>
            )}
          </span>
        </>
      )}

      {riesgo && (
        <>
          <span className="ctx-div" />
          <span className="ctx-seg">
            <Waypoints size={12} className="ctx-i" />
            <span className={"otag r-" + riesgo}>{t.ctx_impact(riesgo)}</span>
          </span>
        </>
      )}
    </div>
  );
}
