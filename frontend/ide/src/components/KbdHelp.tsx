// Capa 30 — Hoja de atajos de teclado. La feature NO inventa flujos:
// acelera lo que ya hacen los botones del Inspector (aprobar/rechazar,
// navegar entre archivos con propuestas). Por eso esta vista no
// "enseña" un producto nuevo — sólo muestra los aceleradores y dónde
// vive cada acción real.
//
// Por qué Alt como modificador: el editor captura casi todas las teclas
// dentro del textarea (es lo correcto para un editor). Ctrl+S ya es del
// producto (checkpoint, capa 19). Alt deja la mano izquierda como
// "puente" entre editor y coordinación sin pisar atajos del browser ni
// del OS comunes.
import { useEffect } from "react";
import { X } from "lucide-react";
import { useI18n } from "../i18n";
import { ModalPortal } from "./ModalPortal";

// Una fila del cheatsheet: combo de teclas + descripción. La tecla se
// renderiza con `<kbd>` (los lectores de pantalla la anuncian como
// "tecla", y el estilo monoespaciado refuerza la convención de IDE).
function Row({ keys, desc }: { keys: string[]; desc: string }) {
  return (
    <div className="kbd-row">
      <span className="kbd-keys">
        {keys.map((k, i) => (
          <span key={i}>
            <kbd>{k}</kbd>
            {i < keys.length - 1 && <span className="kbd-plus">+</span>}
          </span>
        ))}
      </span>
      <span className="kbd-desc">{desc}</span>
    </div>
  );
}

export function KbdHelp({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();

  // Esc cierra. Mismo patrón que los demás modales (InviteModal,
  // ConfirmarSalida) — no inventamos focus-trap pesado: este modal NO
  // tiene controles interactivos más allá del botón cerrar; un Tab más
  // pulido es trabajo para cuando exista un real menú de comandos.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <ModalPortal>
      <div
        className="modalbg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kbd-h"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="modal kbd-modal">
          <header className="modal-head">
            <h2 id="kbd-h" className="modal-h">{t.kbd_help_title}</h2>
            <button
              className="modal-x"
              aria-label={t.kbd_help_close}
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </header>

          <p className="modal-intro">{t.kbd_help_sub}</p>

          <section className="kbd-section">
            <h3 className="kbd-section-h">{t.kbd_section_review}</h3>
            <Row keys={["Alt", "A"]} desc={t.kbd_approve} />
            <Row keys={["Alt", "R"]} desc={t.kbd_reject} />
          </section>

          <section className="kbd-section">
            <h3 className="kbd-section-h">{t.kbd_section_nav}</h3>
            <Row keys={["Alt", "J"]} desc={t.kbd_next} />
            <Row keys={["Alt", "K"]} desc={t.kbd_prev} />
          </section>

          <section className="kbd-section">
            <h3 className="kbd-section-h">{t.kbd_section_global}</h3>
            <Row keys={["Ctrl", "S"]} desc={t.kbd_save} />
            <Row keys={["?"]} desc={t.kbd_help_open} />
          </section>

          <p className="kbd-hint">{t.kbd_help_hint}</p>

          <footer className="modal-foot">
            <button className="primario" onClick={onClose}>
              {t.kbd_help_close}
            </button>
          </footer>
        </div>
      </div>
    </ModalPortal>
  );
}
