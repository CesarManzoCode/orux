import { FileQuestion, X, KeyRound, GitPullRequest } from "lucide-react";
import { useStore } from "../useStore";
import { cerrarArchivo, propuestasDe } from "../store";
import { chipDe } from "../lang";
import { useI18n } from "../i18n";

// Capa 26 — Pestaña del archivo abierto. Sigue siendo de UNA pestaña (es
// chrome, no gestor multi-tab), pero ahora LEE estado de coordinación:
// dueño, propuestas pendientes y "sin marcar". Una pestaña de IDE dice en
// qué estado está el archivo sin que abras nada.
//
// Pulido pre-mercado (capa 28+): los tooltips ahora dicen la verdad según
// el rol del usuario sobre el archivo. Si soy dueño, el dot dice "Ctrl+S
// analiza el impacto"; si NO soy dueño, dice "Ctrl+S envía la propuesta
// al dueño" — porque eso es lo que efectivamente hace cada uno (capa 28).
export function Tabs() {
  const s = useStore();
  const { t } = useI18n();
  if (!s.currentPath) {
    return (
      <div className="tabs">
        <span className="vacio"><FileQuestion size={14} /> sin archivo abierto</span>
      </div>
    );
  }
  const path = s.currentPath;
  const c = chipDe(path);
  const nombre = path.split("/").pop();
  const sinMarcar = !!s.dirty[path];
  const due = s.owners[path];
  const esMio = !!(s.yo && due === s.yo.client_id);
  // "Soy no-dueño con dueño asignado": en capa 28 lo que tipeo va a un
  // draft local y se manda al pulsar Ctrl+S. La pestaña refleja eso.
  const esDeOtro = !esMio && !!due;
  const props = propuestasDe(path).length;
  const tooltipDot = esDeOtro ? t.tab_dirty_other : t.tab_dirty_owner;
  return (
    <div className="tabs">
      <div className="tab activo">
        <span className={"chip" + (c.cls ? " " + c.cls : "")}>{c.txt}</span>
        <span className="nom" title={path}>{nombre}</span>
        {due && (
          <span
            className={"tab-own" + (esMio ? " mio" : "")}
            title={esMio ? t.tab_own_mine : t.tab_own_other}
            aria-label={esMio ? t.tab_own_mine : t.tab_own_other}
          >
            <KeyRound size={11} />
          </span>
        )}
        {props > 0 && (
          <span
            className="tab-prop"
            title={t.ft_proposals(props)}
            aria-label={t.ft_proposals(props)}
          >
            <GitPullRequest size={11} /> {props}
          </span>
        )}
        {sinMarcar && (
          <span
            className="dot-sinmarcar"
            title={tooltipDot}
            aria-label={tooltipDot}
          >
            ●
          </span>
        )}
        <button
          className="tabx"
          // El close avisa con tooltip distinto si tiene cambios: el
          // usuario que está a punto de cerrar un archivo con draft ve
          // "tienes cambios sin marcar" — no rompe el cierre (el draft
          // permanece en memoria), pero queda claro.
          title={sinMarcar ? t.tab_close_dirty : t.tab_close}
          aria-label={sinMarcar ? t.tab_close_dirty : t.tab_close}
          onClick={cerrarArchivo}
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}
