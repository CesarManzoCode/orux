import { useState } from "react";
import { useStore } from "../useStore";
import { crearEquipo, redimirInvite, seleccionarEquipo, salir } from "../store";
import { useI18n, LangToggle } from "../i18n";

function colorEquipo(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return `hsl(${((h % 360) + 360) % 360} 42% 56%)`;
}

export function Hub() {
  const s = useStore();
  const { t } = useI18n();
  const [nombre, setNombre] = useState("");
  const [code, setCode] = useState("");

  const yo = s.yo;
  const inicial = (yo?.name || "?").trim().charAt(0).toUpperCase() || "?";
  const nAdmin = s.equipos.filter((e) => e.rol === "admin").length;

  const connMap: Record<string, { txt: string; cls: string }> = {
    conectado: { txt: t.hub_conn_active, cls: "ok" },
    conectando: { txt: t.hub_conn_connecting, cls: "wt" },
    desconectado: { txt: t.hub_conn_offline, cls: "bad" },
    error: { txt: t.hub_conn_offline, cls: "bad" },
  };
  const conn = connMap[s.conn] || connMap.conectando;

  return (
    <div className="hub">
      <header className="hub-head">
        <div className="hub-brand">
          <b>Orux</b>
          <span className="hub-brand-sub">{t.hub_layer}</span>
        </div>
        <div className="hub-head-mid" aria-hidden>
          <span className={"hub-conn st-" + conn.cls}>
            <i /> {conn.txt}
          </span>
        </div>
        <div className="hub-me">
          <span
            className="hub-me-ava"
            style={{ background: yo?.color || "var(--accent)" }}
            aria-hidden
          >
            {inicial}
          </span>
          <span className="hub-me-meta">
            <b>{yo?.name || "—"}</b>
            <code>{t.hub_stable}</code>
          </span>
          <LangToggle />
          <button className="hub-me-out" onClick={salir} title={t.hub_signout_title}>
            {t.hub_signout}
          </button>
        </div>
      </header>

      <main className="hub-grid">
        <section className="hub-card hc-teams" aria-label={t.hub_teams_eyebrow}>
          <header className="hc-h">
            <span className="hc-h-eyebrow">{t.hub_teams_eyebrow}</span>
            <span className="hc-h-num">{s.equipos.length}</span>
            <span className="hc-h-hint">
              {s.equipos.length === 0
                ? t.hub_teams_empty
                : t.hub_teams_hint}
            </span>
          </header>

          {s.equipos.length > 0 ? (
            <div className="hub-teams">
              {s.equipos.map((e) => (
                <button
                  key={e.id}
                  className="hub-team"
                  onClick={() => seleccionarEquipo(e.id)}
                >
                  <span
                    className="ht-ava"
                    style={{ background: colorEquipo(e.id) }}
                    aria-hidden
                  >
                    {(e.nombre || "?").trim().charAt(0).toUpperCase() || "?"}
                  </span>
                  <span className="ht-meta">
                    <span className="ht-name">{e.nombre}</span>
                    <span className="ht-rol">{e.rol}</span>
                  </span>
                  <span className="ht-go" aria-hidden>{t.hub_open}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="hub-empty">
              <b>{t.hub_empty_title}</b>
              <span>{t.hub_empty_desc}</span>
            </div>
          )}
        </section>

        <section className="hub-card hc-id" aria-label={t.hub_id_eyebrow}>
          <header className="hc-h">
            <span className="hc-h-eyebrow">{t.hub_id_eyebrow}</span>
          </header>
          <div className="hc-id-row">
            <span
              className="hc-id-ava"
              style={{ background: yo?.color || "var(--accent)" }}
              aria-hidden
            >
              {inicial}
            </span>
            <div className="hc-id-meta">
              <b>{yo?.name || "—"}</b>
              <code>{yo?.color || "—"}</code>
            </div>
          </div>
          <div className="hc-id-kpis">
            <div>
              <b>{s.equipos.length}</b>
              <span>{s.equipos.length === 1 ? t.hub_kpi_team : t.hub_kpi_teams}</span>
            </div>
            <div>
              <b>{nAdmin}</b>
              <span>{t.hub_kpi_admin}</span>
            </div>
          </div>
          <p className="hc-id-foot">{t.hub_id_foot}</p>
        </section>

        <section className="hub-card hc-new" aria-label={t.hub_new_eyebrow}>
          <header className="hc-h">
            <span className="hc-h-eyebrow">{t.hub_new_eyebrow}</span>
          </header>

          <div className="fg">
            <label htmlFor="hb-new">{t.hub_create_label}</label>
            <div className="hub-row">
              <input
                id="hb-new"
                placeholder={t.hub_create_placeholder}
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && nombre.trim()) crearEquipo(nombre.trim());
                }}
              />
              <button
                className="primario"
                disabled={!nombre.trim()}
                onClick={() => { if (nombre.trim()) crearEquipo(nombre.trim()); }}
              >
                {t.hub_create_btn}
              </button>
            </div>
            <p className="fg-hint">{t.hub_create_hint}</p>
          </div>

          <div className="hub-sep" />

          <div className="fg">
            <label htmlFor="hb-code">{t.hub_join_label}</label>
            <div className="hub-row">
              <input
                id="hb-code"
                placeholder={t.hub_join_placeholder}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && code.trim()) redimirInvite(code.trim());
                }}
              />
              <button
                className="secundario"
                disabled={!code.trim()}
                onClick={() => { if (code.trim()) redimirInvite(code.trim()); }}
              >
                {t.hub_join_btn}
              </button>
            </div>
            <p className="fg-hint">{t.hub_join_hint}</p>
          </div>

          <div className="err" role="alert">{s.equipoError || ""}</div>
        </section>

        <section className="hub-card hc-sys" aria-label={t.hub_sys_eyebrow}>
          <header className="hc-h">
            <span className="hc-h-eyebrow">{t.hub_sys_eyebrow}</span>
          </header>
          <div className="hc-sys-list">
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> {t.hub_sys1_pre} <b>{t.hub_sys1_label}</b>
              <span>{t.hub_sys1_desc}</span>
            </div>
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> {t.hub_sys2_pre} <b>{t.hub_sys2_label}</b>
              <span>{t.hub_sys2_desc}</span>
            </div>
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> {t.hub_sys3_pre} <b>{t.hub_sys3_label}</b>
              <span>{t.hub_sys3_desc}</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
