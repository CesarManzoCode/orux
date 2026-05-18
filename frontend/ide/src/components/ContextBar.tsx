import { KeyRound, Radio, Waypoints } from "lucide-react";
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

  return (
    <div className="ctxbar">
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

      <span className="ctx-div" />

      <span className="ctx-seg">
        <KeyRound size={12} className="ctx-i" />
        {!due ? (
          <button className="reclamar" onClick={() => reclamar(path)}>
            reclamar este archivo
          </button>
        ) : esMio ? (
          <span className="otag tuyo">tuyo</span>
        ) : (
          <>
            <span className="otag ajeno">de {nombreDe(due)}</span>
            <span className="ctx-nota">
              lo que escribas se le propone — no se aplica hasta que apruebe
            </span>
          </>
        )}
      </span>

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
