// Modal de textos legales — sirve para Términos y Condiciones y para la
// Política de Privacidad. Se invoca desde Register (capa 29+) cuando el
// usuario hace clic en cualquiera de los dos enlaces del checkbox de
// aceptación. Es presentacional: NO acepta nada por sí mismo; aceptar es
// marcar el checkbox del formulario de registro.
//
// Patrón idéntico al de los demás modales del producto (`.modalbg` +
// `.modal` + `.modal-head/foot`), con dos extras propios:
//   1) la lista de secciones se construye desde i18n (10 bloques h/p por
//      cada documento) para que ES/EN compartan estructura, y traducir es
//      reescribir, no recolocar markup.
//   2) el cuerpo es scrollable (los legales crecen) sin que el header ni
//      el footer pierdan posición — eso es lo que hace usable un texto
//      largo en pantalla pequeña.
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useI18n } from "../i18n";
import { ModalPortal } from "./ModalPortal";

export type LegalDoc = "terms" | "privacy";

export function LegalModal({
  doc,
  onClose,
}: {
  doc: LegalDoc;
  onClose: () => void;
}) {
  const { t } = useI18n();

  // Al abrir, el foco entra por el botón de cerrar — arriba del documento.
  // Antes iba (autoFocus) al botón "Aceptar" del pie, debajo de un texto
  // legal largo: dejaba al usuario de teclado/lector al FINAL del texto.
  // Deps [] = solo al montar.
  const closeRef = useRef<HTMLButtonElement>(null);
  // El body es el contenedor scrollable; si el usuario abrió un doc, scrolleó
  // hasta abajo, cerró y volvió a abrir, sin esto reaparecería al final.
  // Resetear scrollTop al mount lo asienta siempre en el principio del texto.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [doc]);

  // Esc cierra — convención universal. preventDefault para que ningún
  // atajo de OS interfiera mientras el modal tiene el foco lógico.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Selecciona el bloque de claves a renderizar según el documento. Cada
  // documento tiene 10 secciones (h = título, p = párrafo); si en el
  // futuro se añade una sección, basta con sumar el par s11_h/s11_p y
  // ampliar el array — el modal no necesita lógica nueva.
  const meta =
    doc === "terms"
      ? {
          title: t.terms_title,
          intro: t.terms_intro,
          secs: [
            [t.terms_s1_h, t.terms_s1_p],
            [t.terms_s2_h, t.terms_s2_p],
            [t.terms_s3_h, t.terms_s3_p],
            [t.terms_s4_h, t.terms_s4_p],
            [t.terms_s5_h, t.terms_s5_p],
            [t.terms_s6_h, t.terms_s6_p],
            [t.terms_s7_h, t.terms_s7_p],
            [t.terms_s8_h, t.terms_s8_p],
            [t.terms_s9_h, t.terms_s9_p],
            [t.terms_s10_h, t.terms_s10_p],
          ],
        }
      : {
          title: t.privacy_title,
          intro: t.privacy_intro,
          secs: [
            [t.privacy_s1_h, t.privacy_s1_p],
            [t.privacy_s2_h, t.privacy_s2_p],
            [t.privacy_s3_h, t.privacy_s3_p],
            [t.privacy_s4_h, t.privacy_s4_p],
            [t.privacy_s5_h, t.privacy_s5_p],
            [t.privacy_s6_h, t.privacy_s6_p],
            [t.privacy_s7_h, t.privacy_s7_p],
            [t.privacy_s8_h, t.privacy_s8_p],
            [t.privacy_s9_h, t.privacy_s9_p],
            [t.privacy_s10_h, t.privacy_s10_p],
          ],
        };

  // Importante: este modal se monta dentro de .landing (Login.tsx), que es
  // un contenedor full-screen con framer-motion en otros descendientes; eso
  // hace que cualquier `transform` ancestral capture el position:fixed del
  // backdrop. ModalPortal saca el árbol a <body> y evita el recorte (es la
  // razón explícita por la que ese componente existe).
  return (
    <ModalPortal>
      <div
        className="modalbg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="legal-h"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <div className="modal legal-modal">
          <header className="modal-head">
            <h2 id="legal-h" className="modal-h">{meta.title}</h2>
            <button
              ref={closeRef}
              className="modal-x"
              aria-label={t.legal_close}
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </header>

          <div className="legal-body" ref={bodyRef}>
            <p className="legal-updated">
              {t.legal_updated_prefix} {t.legal_updated_date}
            </p>
            <p className="legal-intro">{meta.intro}</p>
            {meta.secs.map(([h, p], i) => (
              <section key={i} className="legal-sec">
                <h3 className="legal-h">{h}</h3>
                <p className="legal-p">{p}</p>
              </section>
            ))}
          </div>

          <footer className="modal-foot">
            <button className="primario" onClick={onClose}>
              {t.legal_accept}
            </button>
          </footer>
        </div>
      </div>
    </ModalPortal>
  );
}
