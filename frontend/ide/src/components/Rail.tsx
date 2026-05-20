import {
  Files, GitBranch, Shield,
} from "lucide-react";
import { useStore } from "../useStore";

// Capa 26 — Activity rail. Dos bloques con jerarquía real: navegación
// PRIMARIA (explorador, control de versiones) arriba y ACCIONES de equipo
// (admin) separadas por un hairline. El toggle del inspector vive en el
// TopBar (esquina superior derecha): pasaba desapercibido acá abajo, y
// arriba es donde el ojo lo busca en cualquier IDE.
export function Rail(props: {
  vista: "archivos" | "git";
  setVista: (v: "archivos" | "git") => void;
  abrirAdmin: () => void;
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
    </nav>
  );
}
