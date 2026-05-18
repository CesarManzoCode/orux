import {
  Files, GitBranch, Shield, PanelRight,
} from "lucide-react";
import { useStore } from "../useStore";

// Capa 26 — Activity rail. Tres bloques con jerarquía real: navegación
// PRIMARIA (explorador, control de versiones) arriba, ACCIONES de equipo
// (admin) separadas por un hairline, y el toggle del inspector anclado
// abajo (chrome de ventana, no navegación). Indicadores sutiles: un punto
// cuando hay algo que mirar (cambios git, propuestas para vos) — la rail
// avisa sin gritar.
export function Rail(props: {
  vista: "archivos" | "git";
  setVista: (v: "archivos" | "git") => void;
  abrirAdmin: () => void;
  inspOpen: boolean;
  toggleInsp: () => void;
}) {
  const s = useStore();
  // Propuestas que esperan TU verde (sos dueño): la rail lo señala aunque
  // estés en otra vista.
  const propsParaMi = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  ).length;
  const cambiosGit = s.git?.available ? s.git.changes : 0;

  return (
    <nav className="rail isla">
      <div className="rail-grp">
        <button
          className={"rail-b" + (props.vista === "archivos" ? " activo" : "")}
          title="explorador de archivos"
          onClick={() => props.setVista("archivos")}
        >
          <Files size={18} />
          {propsParaMi > 0 && <span className="rail-dot warn" />}
        </button>
        <button
          className={"rail-b" + (props.vista === "git" ? " activo" : "")}
          title="control de versiones"
          onClick={() => props.setVista("git")}
        >
          <GitBranch size={18} />
          {cambiosGit > 0 && <span className="rail-dot" />}
        </button>
      </div>

      {s.esAdmin && (
        <div className="rail-grp">
          <span className="rail-sep" />
          <button
            className="rail-b"
            title="administración · ownership"
            onClick={props.abrirAdmin}
          >
            <Shield size={18} />
          </button>
        </div>
      )}

      <span className="rail-fill" />

      <div className="rail-grp">
        <button
          className={"rail-b" + (props.inspOpen ? " activo" : "")}
          title={props.inspOpen ? "ocultar inspector" : "mostrar inspector"}
          onClick={props.toggleInsp}
        >
          <PanelRight size={18} />
        </button>
      </div>
    </nav>
  );
}
