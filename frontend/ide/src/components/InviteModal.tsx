// Modal de invitación — el botón "invitar" del TopBar abre esta vista.
// Capa 33: ahora muestra LOS DOS — link de un clic Y código en limpio.
// El admin elige según el canal (WhatsApp / voz / papel / DM) y la persona
// invitada lo abre o lo pega en el hub. El link siempre fue posible, pero
// el código quedaba implícito en el URL y la gente ni lo veía.
import { useEffect, useRef, useState } from "react";
import { Copy, Check, RefreshCw, X, Link2, KeyRound } from "lucide-react";
import { crearInvite, emitToast } from "../store";
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
  // Lo que se comparte puede ser un LINK (un clic) o el CÓDIGO suelto (lo
  // pegan en "unirme con código"). Ambos envuelven el mismo token de un solo
  // uso del server (capa 15). Si todavía no llegó del server, link queda ""
  // y el input se ve vacío hasta que llega `invite_created`.
  const link = code
    ? location.origin + location.pathname + "?invite=" + encodeURIComponent(code)
    : "";
  // Dos estados independientes (link / code) — copiar uno no debe poner
  // "copiado" en el otro: el feedback visual tiene que coincidir con el
  // botón que realmente clickeaste.
  const [estLink, setEstLink] = useState<"idle" | "ok" | "failed">("idle");
  const [estCode, setEstCode] = useState<"idle" | "ok" | "failed">("idle");
  // Foco al primer input al abrir — el link es la opción "por default" que
  // queremos resaltar (más rápido para el invitado), por eso enfocamos ese.
  const linkRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    linkRef.current?.select();
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

  const copiar = async (
    valor: string,
    setEstado: (v: "idle" | "ok" | "failed") => void,
    okMsg: string,
  ) => {
    const ok = await copiarTexto(valor);
    setEstado(ok ? "ok" : "failed");
    emitToast(ok ? okMsg : t.toast_invite_failed, ok ? "ok" : "bad");
    if (ok) setTimeout(() => setEstado("idle"), 1500);
  };

  const onCopiarLink = () => copiar(link, setEstLink, t.toast_invite_copied);
  const onCopiarCode = () => copiar(code, setEstCode, t.toast_invite_copied);

  const onRegenerar = () => {
    // El server (capa 15) crea uno nuevo y manda `invite_created`. El
    // store reemplaza `inviteCode` y el efecto repinta. El viejo SIGUE
    // siendo válido en el server hasta que alguien lo redima (un solo
    // uso) — esto es honestidad de alcance, no inventamos revocación.
    crearInvite();
    setEstLink("idle");
    setEstCode("idle");
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

        <div className="inv-share">
          <div className="inv-share-block">
            <div className="inv-share-label">
              <Link2 size={11} strokeWidth={2.4} aria-hidden /> {t.inv_link_label}
            </div>
            <div className="inv-code-row">
              <input
                ref={linkRef}
                className="inv-code inv-code-link"
                value={link}
                readOnly
                aria-label={t.inv_link_label}
                onFocus={(e) => e.currentTarget.select()}
                onClick={(e) => e.currentTarget.select()}
              />
              <button
                className={"inv-btn " + (estLink === "ok" ? "ok" : "")}
                onClick={onCopiarLink}
              >
                {estLink === "ok" ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
                {estLink === "ok" ? t.inv_copied : t.inv_copy}
              </button>
            </div>
          </div>

          <div className="inv-share-block">
            <div className="inv-share-label">
              <KeyRound size={11} strokeWidth={2.4} aria-hidden /> {t.inv_code_label}
            </div>
            <div className="inv-code-row">
              <input
                ref={codeRef}
                className="inv-code inv-code-raw"
                value={code}
                readOnly
                aria-label={t.inv_code_label}
                onFocus={(e) => e.currentTarget.select()}
                onClick={(e) => e.currentTarget.select()}
              />
              <button
                className={"inv-btn " + (estCode === "ok" ? "ok" : "")}
                onClick={onCopiarCode}
              >
                {estCode === "ok" ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
                {estCode === "ok" ? t.inv_copied : t.inv_copy}
              </button>
            </div>
          </div>
        </div>

        {(estLink === "failed" || estCode === "failed") && (
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
