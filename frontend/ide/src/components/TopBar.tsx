import { useState } from "react";
import {
  GitBranch, UserPlus, PanelRight, PanelRightClose, Home,
} from "lucide-react";
import { useStore } from "../useStore";
import { salir, salirEquipo, crearInvite, contarDrafts } from "../store";
import { useI18n, LangToggle } from "../i18n";
import { InviteModal } from "./InviteModal";
import { ConfirmarSalida } from "./ConfirmarSalida";

function iniciales(n: string): string {
  const p = n.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return ((p[0]?.[0] ?? "?") + (p[1]?.[0] ?? "")).toUpperCase();
}

function Logomark() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="lm-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4cc38a" />
          <stop offset="1" stopColor="#34d9bf" />
        </linearGradient>
      </defs>
      <rect x="3.6" y="3.6" width="11.6" height="11.6" rx="3.2"
        stroke="#5b606e" strokeWidth="1.7" />
      <rect x="8.8" y="8.8" width="11.6" height="11.6" rx="3.2"
        fill="url(#lm-grad)" />
    </svg>
  );
}

export function TopBar({
  inspOpen,
  toggleInsp,
}: {
  inspOpen: boolean;
  toggleInsp: () => void;
}) {
  const s = useStore();
  const { t } = useI18n();
  // Modal de invitación: abierto sólo cuando el admin lo pide. Antes el
  // código colgaba pelado del topbar, lo que no era ni claro ni
  // profesional. Si todavía no tenemos código (admin entra primero), el
  // botón lo pide al server primero y luego abre el modal al recibirlo.
  const [inviteOpen, setInviteOpen] = useState(false);
  // Confirmación al volver al hub con drafts pendientes: el dev podría
  // tener varios archivos con propuestas locales (capa 28). `salirEquipo`
  // limpia el estado del equipo, así que sin este guard perdería todo.
  const [salidaPending, setSalidaPending] = useState<number | null>(null);

  function intentarSalir() {
    const n = contarDrafts();
    if (n > 0) {
      setSalidaPending(n);   // muestra modal
      return;
    }
    salirEquipo();           // sin drafts: vuelve al hub directo
  }
  function confirmarSalir() {
    setSalidaPending(null);
    salirEquipo();
  }

  const ETIQUETA: Record<string, string> = {
    conectando: t.tb_connecting,
    conectado: t.tb_connected,
    desconectado: t.tb_disconnected,
    error: t.tb_error,
  };

  const clase =
    s.conn === "conectado" ? "status ok"
    : s.conn === "conectando" ? "status" : "status bad";

  const otros = Object.values(s.peers).filter(
    (p) => !s.yo || p.client_id !== s.yo.client_id,
  );
  const visibles = otros.slice(0, 4);
  const extra = otros.length - visibles.length;
  const g = s.git;

  function abrirInvite() {
    // Si no hay código aún, lo pide. El modal se abre con el código vacío
    // y se actualiza al recibir el `invite_created` (UX de un solo paso:
    // se ve "—" un instante y luego el código real).
    if (!s.inviteCode) crearInvite();
    setInviteOpen(true);
  }

  return (
    <header className="topbar isla">
      <div className="tb-grp">
        <div className="mark"><Logomark /></div>
        <span className="brand"><b>Orux</b></span>
        <span className="chev">›</span>
        <span className="proy">{s.equipo ? s.equipo.nombre : s.proyecto}</span>
        {/* Volver al hub: presente solo cuando estamos dentro de un equipo
            y hay más de uno (caso típico: cambiar de equipo). Si solo hay
            uno, no aporta — el dev solo entra y sale del IDE. */}
        {s.equipo && s.equipos.length > 1 && (
          <button
            className="tb-hub"
            onClick={intentarSalir}
            title={t.tb_hub_title}
          >
            <Home size={12} /> {t.tb_hub}
          </button>
        )}
      </div>

      {visibles.length > 0 && (
        <>
          <span className="tb-div" />
          <span className="peers" title={otros.map((p) => p.name).join(", ")}>
            {visibles.map((p) => (
              <span key={p.client_id} className="av"
                style={{ background: p.color }} title={p.name}>
                {iniciales(p.name)}
              </span>
            ))}
            {extra > 0 && <span className="av mas">+{extra}</span>}
          </span>
        </>
      )}

      <span className="spacer" />

      {g && g.available && (
        <>
          <div className="tb-grp repo">
            <span className="tb-rama" title={t.tb_branch_title}>
              <GitBranch size={12} /> {g.branch || "—"}
            </span>
            <span
              className={"tb-chg" + (g.changes === 0 ? " limpio" : "")}
              title={t.tb_changes_title}
            >
              {g.changes === 0 ? t.tb_clean : g.changes + "Δ"}
            </span>
          </div>
          <span className="tb-div" />
        </>
      )}

      <div className="tb-grp">
        {/* Botón "invitar" abre el modal SIEMPRE — el código pelado fue
            reemplazado. Si ya hay código emitido, el modal lo muestra; si
            no, lo pide al server y luego lo muestra. El admin siempre
            puede volver a abrirlo (antes el botón desaparecía tras el
            primer click, sin forma de regenerarlo sin salir del equipo). */}
        {s.equipo?.rol === "admin" && (
          <button
            className="invitar"
            onClick={abrirInvite}
            title={t.tb_invite_title}
          >
            <UserPlus size={12} /> {t.tb_invite}
          </button>
        )}
        <span className={clase}>{ETIQUETA[s.conn] ?? ETIQUETA.conectando}</span>
      </div>

      <span className="tb-div" />

      <div className="tb-grp">
        {s.yo && (
          <span className="yo">
            <span className="dot" style={{ background: s.yo.color }} />
            {s.yo.name}
          </span>
        )}
        {s.authed && (
          <button className="salir" onClick={salir}>{t.tb_signout}</button>
        )}
      </div>

      <span className="tb-div" />
      <div className="tb-grp">
        <LangToggle />
      </div>

      <span className="tb-div" />
      <div className="tb-grp">
        <button
          className={"tb-insp" + (inspOpen ? " activo" : "")}
          title={inspOpen ? t.tb_inspector_hide : t.tb_inspector_show}
          aria-label={inspOpen ? t.tb_inspector_hide : t.tb_inspector_show}
          aria-pressed={inspOpen}
          onClick={toggleInsp}
        >
          {inspOpen ? <PanelRightClose size={14} /> : <PanelRight size={14} />}
        </button>
      </div>

      {inviteOpen && (
        <InviteModal
          code={s.inviteCode}
          onClose={() => setInviteOpen(false)}
        />
      )}
      {salidaPending != null && (
        <ConfirmarSalida
          drafts={salidaPending}
          onContinuar={confirmarSalir}
          onCancelar={() => setSalidaPending(null)}
        />
      )}
    </header>
  );
}
