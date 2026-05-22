// Empty-state del workspace — la "primera sesión guiada". Un equipo recién
// creado entra a un workspace sin archivos; en vez de un editor en blanco
// (que no le dice a nadie qué hacer), esta vista lo orienta con las tres
// acciones que destraban Orux: traer el código (clone), crear un archivo
// para probar, e invitar al equipo.
//
// Reusa los modales que ya existen — NuevoArchivoModal e InviteModal son
// portales (se montan sobre <body>), así que se renderizan desde acá con
// estado local, sin levantar estado a App ni tocar TopBar/Sidebar.
import { useState } from "react";
import { DownloadCloud, FilePlus2, UserPlus } from "lucide-react";
import { useStore } from "../useStore";
import { crearInvite } from "../store";
import { useI18n } from "../i18n";
import { NuevoArchivoModal } from "./NuevoArchivoModal";
import { InviteModal } from "./InviteModal";

export function EmptyWorkspace({ onIrAGit }: { onIrAGit: () => void }) {
  const s = useStore();
  const { t } = useI18n();
  const [nuevoOpen, setNuevoOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  // Invitar es sólo del admin (igual que el botón del TopBar). En un equipo
  // recién creado quien ve esto ES el admin — pero gateamos igual por
  // coherencia: un miembro que cayó en un equipo vacío no puede invitar.
  const esAdmin = s.equipo?.rol === "admin";

  function abrirInvite() {
    // Si todavía no hay código emitido, lo pedimos; el modal abre con el
    // código vacío y se rellena al llegar `invite_created` (mismo patrón
    // que el botón "invitar" del TopBar).
    if (!s.inviteCode) crearInvite();
    setInviteOpen(true);
  }

  return (
    <div className="ews">
      <div className="ews-card">
        <h2 className="ews-h">{t.ews_title}</h2>
        <p className="ews-sub">{t.ews_sub}</p>

        <div className="ews-steps">
          <button className="ews-step ews-primary" onClick={onIrAGit}>
            <DownloadCloud size={18} aria-hidden />
            <span className="ews-step-tx">
              <b>{t.ews_clone_t}</b>
              <span>{t.ews_clone_d}</span>
            </span>
          </button>

          <button className="ews-step" onClick={() => setNuevoOpen(true)}>
            <FilePlus2 size={18} aria-hidden />
            <span className="ews-step-tx">
              <b>{t.ews_new_t}</b>
              <span>{t.ews_new_d}</span>
            </span>
          </button>

          {esAdmin && (
            <button className="ews-step" onClick={abrirInvite}>
              <UserPlus size={18} aria-hidden />
              <span className="ews-step-tx">
                <b>{t.ews_invite_t}</b>
                <span>{t.ews_invite_d}</span>
              </span>
            </button>
          )}
        </div>

        <p className="ews-foot">{t.ews_foot}</p>
      </div>

      {nuevoOpen && <NuevoArchivoModal onClose={() => setNuevoOpen(false)} />}
      {inviteOpen && (
        <InviteModal code={s.inviteCode} onClose={() => setInviteOpen(false)} />
      )}
    </div>
  );
}
