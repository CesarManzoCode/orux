// Modal de invitación — el botón "invitar" del TopBar ya no muestra el
// código como `<span>...<code>X</code></span>` (que invitaba al admin a
// adivinar qué hacer con el string). Ahora abre esta vista: código grande,
// botón copiar con feedback, microcopy de cómo se usa, y CTA para
// regenerar si se perdió el viejo. El flujo del server (capa 15) no cambia
// — sólo lo presentamos.
import { useEffect, useRef, useState } from "react";
import { Copy, Check, RefreshCw, X } from "lucide-react";
import { crearInvite } from "../store";
import { copiarTexto } from "../validate";
import { useI18n } from "../i18n";
import { ModalPortal } from "./ModalPortal";

export function InviteModal({
  code,
  onClose,
}: {
  code: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  // Estados del botón "copiar": idle / ok / failed. `ok` se resetea solo
  // a los 1.5s para que el botón vuelva a su estado normal sin ruido.
  const [estado, setEstado] = useState<"idle" | "ok" | "failed">("idle");
  // Foco a la caja del código al abrir (lo lee NVDA/JAWS, deja Tab pulida
  // y permite Ctrl+A para seleccionar todo si el usuario prefiere no usar
  // el botón). El usuario que no quiere usar nuestro botón puede copiar a
  // mano sin pelear con el foco del editor de abajo.
  const codeRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    codeRef.current?.select();
  }, []);

  // Esc cierra el modal — convención universal. preventDefault para que
  // el browser no haga nada extra (algunos atajos de OS interceptan Esc).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onCopiar = async () => {
    const ok = await copiarTexto(code);
    setEstado(ok ? "ok" : "failed");
    if (ok) setTimeout(() => setEstado("idle"), 1500);
  };

  const onRegenerar = () => {
    // El server (capa 15) crea uno nuevo y manda `invite_created`. El
    // store reemplaza `inviteCode` y el efecto repinta. El viejo SIGUE
    // siendo válido en el server hasta que alguien lo redima (un solo
    // uso) — esto es honestidad de alcance, no inventamos revocación.
    crearInvite();
    setEstado("idle");
  };

  return (
    <ModalPortal>
    <div
      className="modalbg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="inv-h"
      onClick={(e) => {
        // Click en el backdrop (no en la card) cierra. Patrón estándar.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal inv-modal">
        <header className="modal-head">
          <h2 id="inv-h" className="modal-h">{t.inv_title}</h2>
          <button className="modal-x" aria-label={t.inv_close} onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <p className="modal-intro">{t.inv_intro}</p>

        <div className="inv-code-row">
          <input
            ref={codeRef}
            className="inv-code"
            value={code}
            readOnly
            aria-label={t.inv_title}
            // Click sobre el campo selecciona todo: muscle memory de
            // "compartir cosa importante" desde formularios.
            onFocus={(e) => e.currentTarget.select()}
            onClick={(e) => e.currentTarget.select()}
          />
          <button
            className={"inv-btn " + (estado === "ok" ? "ok" : "")}
            onClick={onCopiar}
            aria-live="polite"
          >
            {estado === "ok" ? <Check size={14} /> : <Copy size={14} />}
            {estado === "ok" ? t.inv_copied : t.inv_copy}
          </button>
        </div>

        {estado === "failed" && (
          <div className="inv-err" role="alert">{t.inv_copy_failed}</div>
        )}

        <section className="inv-how">
          <h3 className="inv-how-h">{t.inv_how_title}</h3>
          <ol>
            <li>{t.inv_how_1}</li>
            <li>{t.inv_how_2}</li>
            <li>{t.inv_how_3}</li>
          </ol>
        </section>

        <p className="inv-limit">{t.inv_limit_note}</p>

        <footer className="modal-foot">
          <button className="secundario" onClick={onRegenerar}>
            <RefreshCw size={12} /> {t.inv_regenerate}
          </button>
          <button className="primario" onClick={onClose}>
            {t.inv_close}
          </button>
        </footer>
      </div>
    </div>
    </ModalPortal>
  );
}
