// Confirmación al "volver al hub" con drafts. Antes el botón "hub" del
// TopBar disparaba `salirEquipo` ciegamente; si tenías propuestas locales
// (capa 28) sin enviar al equipo, se perdían silenciosamente. Este modal
// muestra cuántos drafts hay y te pregunta: seguir editando, o descartar
// y salir igual. El `beforeunload` global cubre cerrar pestaña/recargar
// (que es lo MÁS grave); este cubre la acción intencional desde dentro.
import { useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useI18n } from "../i18n";

export function ConfirmarSalida({
  drafts,
  onContinuar,
  onCancelar,
}: {
  drafts: number;
  onContinuar: () => void;
  onCancelar: () => void;
}) {
  const { t } = useI18n();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onCancelar(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancelar]);

  return (
    <div
      className="modalbg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="leave-h"
      onClick={(e) => { if (e.target === e.currentTarget) onCancelar(); }}
    >
      <div className="modal cnf-modal">
        <header className="modal-head">
          <h2 id="leave-h" className="modal-h cnf-h">
            <AlertTriangle size={15} /> {t.leave_title}
          </h2>
          <button
            className="modal-x"
            aria-label={t.leave_keep}
            onClick={onCancelar}
          >
            <X size={16} />
          </button>
        </header>
        <p className="modal-intro cnf-desc">
          {drafts === 1 ? t.leave_desc_one : t.leave_desc_many(drafts)}
        </p>
        <footer className="modal-foot">
          <button className="secundario" onClick={onCancelar} autoFocus>
            {t.leave_keep}
          </button>
          <button className="primario danger" onClick={onContinuar}>
            {t.leave_discard}
          </button>
        </footer>
      </div>
    </div>
  );
}
