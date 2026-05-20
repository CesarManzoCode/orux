import { Files, GitBranch, Shield } from "lucide-react";
import { useStore } from "../useStore";
import { useI18n } from "../i18n";

export function Rail(props: {
  vista: "archivos" | "git";
  setVista: (v: "archivos" | "git") => void;
  abrirAdmin: () => void;
}) {
  const s = useStore();
  const { t } = useI18n();

  const propsParaMi = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  ).length;
  const cambiosGit = s.git?.available ? s.git.changes : 0;

  return (
    <nav className="rail isla">
      <div className="rail-grp">
        <button
          className={"rail-b" + (props.vista === "archivos" ? " activo" : "")}
          title={t.rail_files_title}
          onClick={() => props.setVista("archivos")}
        >
          <Files size={18} />
          {propsParaMi > 0 && <span className="rail-dot warn" />}
        </button>
        <button
          className={"rail-b" + (props.vista === "git" ? " activo" : "")}
          title={t.rail_git_title}
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
            title={t.rail_admin_title}
            onClick={props.abrirAdmin}
          >
            <Shield size={18} />
          </button>
        </div>
      )}
    </nav>
  );
}
