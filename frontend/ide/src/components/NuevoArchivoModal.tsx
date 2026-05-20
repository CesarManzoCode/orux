// Modal "nuevo archivo" — reemplaza el `prompt()` nativo del Sidebar. Tres
// problemas del prompt: no se puede estilar, no valida, y el aspecto de
// "1990's web" rompe la presentación premium del IDE. Acá validamos con las
// mismas reglas de path_seguro (ver validate.ts) y mostramos el mensaje de
// error con i18n, y damos hint con extensiones de análisis profundo.
import { useEffect, useRef, useState } from "react";
import { FilePlus2, X } from "lucide-react";
import { useStore } from "../useStore";
import { nuevoArchivo } from "../store";
import { validarPath } from "../validate";
import { useI18n } from "../i18n";

type ErrKey = "exists" | ReturnType<typeof validarPath>;

export function NuevoArchivoModal({ onClose }: { onClose: () => void }) {
  const s = useStore();
  const { t } = useI18n();
  const [valor, setValor] = useState("");
  const [err, setErr] = useState<ErrKey>(null);
  // Tocado: solo mostramos el error tras intento de submit, no en cada
  // tecla (sería ansioso para un usuario que está pensando el nombre).
  const [tocado, setTocado] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  // Esc cancela. Otros atajos los maneja el input nativo.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function chequear(v: string): ErrKey {
    const e = validarPath(v);
    if (e) return e;
    if (s.files[v] != null) return "exists";
    return null;
  }

  function submit() {
    const v = valor.trim();
    setTocado(true);
    const e = chequear(v);
    if (e) { setErr(e); return; }
    nuevoArchivo(v);
    onClose();
  }

  function onChange(v: string) {
    setValor(v);
    // Si ya hubo error, reevaluamos en vivo para que el usuario vea
    // desaparecer el mensaje cuando lo corrige.
    if (tocado) setErr(chequear(v.trim()));
  }

  const msgErr: Record<string, string> = {
    exists: t.nf_err_exists,
    vacio: t.nf_err_vacio,
    muy_largo: t.nf_err_muy_largo,
    control: t.nf_err_control,
    prohibido: t.nf_err_prohibido,
    invisible: t.nf_err_invisible,
    absoluto: t.nf_err_absoluto,
    barra_invertida: t.nf_err_barra_invertida,
    segmento_vacio: t.nf_err_segmento_vacio,
    punto: t.nf_err_punto,
    doble_punto: t.nf_err_doble_punto,
    segmento_largo: t.nf_err_segmento_largo,
    profundidad: t.nf_err_profundidad,
    espacios_borde: t.nf_err_espacios_borde,
    reservado_win: t.nf_err_reservado_win,
  };

  return (
    <div
      className="modalbg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nf-h"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal nf-modal">
        <header className="modal-head">
          <h2 id="nf-h" className="modal-h">
            <FilePlus2 size={15} /> {t.nf_title}
          </h2>
          <button className="modal-x" aria-label={t.nf_cancel} onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <div className="fg">
          <label htmlFor="nf-input">{t.nf_label}</label>
          <input
            id="nf-input"
            ref={inputRef}
            placeholder={t.nf_placeholder}
            value={valor}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); submit(); }
            }}
            aria-invalid={!!err}
            aria-describedby={err ? "nf-err" : "nf-hint"}
            maxLength={200}
            autoComplete="off"
            spellCheck={false}
          />
          {err ? (
            <div id="nf-err" className="fg-err" role="alert">
              {msgErr[err] ?? t.nf_err_vacio}
            </div>
          ) : (
            <p id="nf-hint" className="fg-hint">{t.nf_hint}</p>
          )}
        </div>

        <footer className="modal-foot">
          <button className="secundario" onClick={onClose}>{t.nf_cancel}</button>
          <button
            className="primario"
            onClick={submit}
            disabled={!valor.trim() || !!err}
          >
            {t.nf_create}
          </button>
        </footer>
      </div>
    </div>
  );
}
