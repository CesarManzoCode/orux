import { Files, GitBranch, Shield } from "lucide-react";
import { useStore } from "../useStore";

// Barra de actividad. Íconos REALES (lucide), no emoji: parte de "deja de
// parecer juguete". Es navegación entre lo que ya existe; admin abre el
// modal (no una vista de sidebar) y sólo aparece si el server dice que
// sos admin.
export function Rail(props: {
  vista: "archivos" | "git";
  setVista: (v: "archivos" | "git") => void;
  abrirAdmin: () => void;
}) {
  const s = useStore();
  return (
    <nav className="rail isla">
      <button
        className={props.vista === "archivos" ? "activo" : ""}
        title="archivos" onClick={() => props.setVista("archivos")}
      >
        <Files size={18} />
      </button>
      <button
        className={props.vista === "git" ? "activo" : ""}
        title="control de versiones" onClick={() => props.setVista("git")}
      >
        <GitBranch size={18} />
      </button>
      {s.esAdmin && (
        <button title="administración" onClick={props.abrirAdmin}>
          <Shield size={18} />
        </button>
      )}
    </nav>
  );
}
