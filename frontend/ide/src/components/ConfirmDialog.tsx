// Diálogo de confirmación accesible — reemplazo del `window.confirm()`
// nativo (que es feo, no se puede estilar, suele bloquear el event loop y
// rompe la sensación premium del IDE). Se usa para acciones destructivas
// que no pueden volverse atrás con un undo trivial:
//   · borrar archivo (queda commit Git)
//   · clonar y reemplazar workspace (rebasea todo)
//
// Patrón idéntico al de los demás modales (.modalbg + .modal + head/foot)
// para que el usuario sienta una sola gramática visual. Tres slots:
//   tono="danger"  → primario rojo (eliminar, push fuerza, etc.)
//   tono="warn"    → primario ámbar (acciones que cambian estado pero no
//                    destruyen contenido; clonar entra acá hoy — el repo
//                    nuevo reemplaza pero no destruye los pushes ya hechos)
//   tono="default" → primario acento (acciones reversibles)
import { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";
import { ModalPortal } from "./ModalPortal";

export type ConfirmTone = "default" | "warn" | "danger";

export function ConfirmDialog({
  title,
  message,
  okLabel,
  cancelLabel,
  tone = "default",
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  okLabel: string;
  cancelLabel: string;
  tone?: ConfirmTone;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Esc cancela. El foco arranca en cancel (la opción "segura") para que
  // pulsar Enter por reflejo NO ejecute la acción destructiva — un patrón
  // que aprendimos en testing real: el usuario lee el modal con el ojo y
  // confirma con la mano, no al revés.
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onCancel(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  // Trap mínimo: Tab cicla entre cancel ↔ confirm. Es un modal de 2 botones
  // — no hace falta una librería pesada. preventDefault para que el Tab
  // del browser no pase a controles de abajo (que el aria-modal "esconde"
  // pero el browser igual los focaría sin esto).
  function onTabTrap(e: React.KeyboardEvent) {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const cancel = cancelRef.current;
    const ok = cancel?.parentElement?.querySelector<HTMLButtonElement>(".primario");
    if (!cancel || !ok) return;
    (document.activeElement === cancel ? ok : cancel).focus();
  }

  const primaryCls =
    tone === "danger" ? "primario danger" :
    tone === "warn" ? "primario warn" :
    "primario";

  return (
    <ModalPortal>
      <div
        className="modalbg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cfm-h"
        aria-describedby="cfm-msg"
        onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
        onKeyDown={onTabTrap}
      >
        <div className="modal cnf-modal">
          <header className="modal-head">
            <h2 id="cfm-h" className="modal-h cnf-h">
              {tone === "danger" || tone === "warn"
                ? <AlertTriangle size={15} />
                : null}
              {title}
            </h2>
            <button className="modal-x" aria-label={cancelLabel} onClick={onCancel}>
              <X size={16} />
            </button>
          </header>
          <p id="cfm-msg" className="modal-intro cnf-desc">{message}</p>
          <footer className="modal-foot">
            <button
              ref={cancelRef}
              className="secundario"
              onClick={onCancel}
            >
              {cancelLabel}
            </button>
            <button className={primaryCls} onClick={onConfirm}>
              {okLabel}
            </button>
          </footer>
        </div>
      </div>
    </ModalPortal>
  );
}
