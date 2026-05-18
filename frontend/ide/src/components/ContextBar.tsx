import { KeyRound, Radio, Waypoints, Pencil, GitPullRequest } from "lucide-react";
import { useStore } from "../useStore";
import {
  reclamar, nombreDe, impactosQueAfectan, severidadMax, presentesEn,
} from "../store";

// Capa 26 — Barra de coordinación del archivo abierto. La cara visible de
// la tesis: presencia acá · dueño · riesgo, en una tira densa de
// instrumento (no un renglón suelto). Tocás algo ajeno → se negocia, y la
// barra lo dice antes de que escribas.
export function ContextBar() {
  const s = useStore();
  const path = s.currentPath;
  if (!path) return <div className="ctxbar vacia" />;

  const aqui = presentesEn(path);
  const due = s.owners[path];
  const esMio = s.yo && due === s.yo.client_id;
  const riesgo = severidadMax(impactosQueAfectan(path));
  // Modo de edición REAL (derivado, no inventado): si el archivo es tuyo o
  // no tiene dueño, escribís directo; si es de otro, lo que tipees se le
  // propone. Es el titular de la barra — lo que el dev necesita saber
  // ANTES de tocar una tecla.
  const proponiendo = !!due && !esMio;

  return (
    <div className="ctxbar">
      <span
        className={"ctx-mode " + (proponiendo ? "prop" : "live")}
        title={
          proponiendo
            ? "tus cambios se proponen al dueño; no se aplican hasta que apruebe"
            : "editás directo: tus cambios se aplican en vivo"
        }
      >
        {proponiendo ? <GitPullRequest size={12} /> : <Pencil size={12} />}
        {proponiendo ? (
          <>modo propuesta <i className="ctx-arrow">→</i> {nombreDe(due!)}</>
        ) : (
          <>edición directa</>
        )}
      </span>

      {/* La tesis, visible (no escondida en un tooltip): por qué tocar
          algo ajeno no rompe nada. Sólo cuando aplica. */}
      {proponiendo && (
        <span className="ctx-nota">
          no se aplica hasta que <b>{nombreDe(due!)}</b> lo apruebe
        </span>
      )}

      <span className="ctx-div" />

      <span className="ctx-seg">
        <Radio size={12} className="ctx-i" />
        {aqui.length === 0 ? (
          <span className="ctx-mut">solo vos acá</span>
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

      {/* Ownership: sólo cuando aporta algo el chip de modo no dijo ya.
          Si es de otro, el chip de modo "modo propuesta → X" ya lo cubre
          (no se duplica). Acá vive la ACCIÓN (reclamar) y el sello "tuyo". */}
      {(!due || esMio) && (
        <>
          <span className="ctx-div" />
          <span className="ctx-seg">
            <KeyRound size={12} className="ctx-i" />
            {!due ? (
              <button className="reclamar" onClick={() => reclamar(path)}>
                reclamar este archivo
              </button>
            ) : (
              <span className="otag tuyo">tuyo · lo editás directo</span>
            )}
          </span>
        </>
      )}

      {riesgo && (
        <>
          <span className="ctx-div" />
          <span className="ctx-seg">
            <Waypoints size={12} className="ctx-i" />
            <span className={"otag r-" + riesgo}>impacto · {riesgo}</span>
          </span>
        </>
      )}
    </div>
  );
}
