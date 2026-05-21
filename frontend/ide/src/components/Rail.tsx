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

  // Botones icon-only: `title` no se anuncia en lectores de pantalla móviles
  // ni en navegación por teclado pura, y los toggles deben anunciar estado.
  // `aria-pressed` marca el panel activo entre "archivos" y "git" (mismo
  // patrón que un segmented control), y cada botón lleva `aria-label`
  // explícito. Admin no es un toggle (abre un modal) — sólo aria-label.
  const ariaFiles =
    propsParaMi > 0
      ? `${t.rail_files_title} · ${propsParaMi}`
      : t.rail_files_title;
  const ariaGit =
    cambiosGit > 0
      ? `${t.rail_git_title} · ${cambiosGit}`
      : t.rail_git_title;
  return (
    <nav className="rail isla" aria-label={t.rail_nav_label}>
      <div className="rail-grp" role="group" aria-label={t.rail_views_label}>
        <button
          className={"rail-b" + (props.vista === "archivos" ? " activo" : "")}
          title={t.rail_files_title}
          aria-label={ariaFiles}
          aria-pressed={props.vista === "archivos"}
          onClick={() => props.setVista("archivos")}
        >
          <Files size={18} aria-hidden />
          {propsParaMi > 0 && <span className="rail-dot warn" aria-hidden />}
        </button>
        <button
          className={"rail-b" + (props.vista === "git" ? " activo" : "")}
          title={t.rail_git_title}
          aria-label={ariaGit}
          aria-pressed={props.vista === "git"}
          onClick={() => props.setVista("git")}
        >
          <GitBranch size={18} aria-hidden />
          {cambiosGit > 0 && <span className="rail-dot" aria-hidden />}
        </button>
      </div>

      {s.esAdmin && (
        <div className="rail-grp">
          <span className="rail-sep" aria-hidden />
          <button
            className="rail-b"
            title={t.rail_admin_title}
            aria-label={t.rail_admin_title}
            aria-haspopup="dialog"
            onClick={props.abrirAdmin}
          >
            <Shield size={18} aria-hidden />
          </button>
        </div>
      )}
    </nav>
  );
}
