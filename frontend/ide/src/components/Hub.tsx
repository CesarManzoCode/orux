// Hub — la pantalla "entre login y workspace". El usuario ya está
// autenticado: acá decide a qué equipo entrar, crear uno nuevo, o unirse
// con código. Tras el feedback de testing real, este componente lleva la
// validación de nombre (rechaza HTML/control/exceso ANTES de molestar al
// server), estados busy/feedback en los CTAs, y limpia el input tras error
// para que el segundo intento sea limpio.
import { useEffect, useRef, useState } from "react";
import { useStore } from "../useStore";
import { crearEquipo, redimirInvite, seleccionarEquipo, salir } from "../store";
import { validarNombreEquipo, normalizarNombreEquipo } from "../validate";
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
  // Estados busy: bloquean el doble-submit y dan feedback visual ("creando…")
  // mientras esperamos respuesta del server. Se resetean cuando llega `team_ready`
  // (vía useEffect) o cuando llega un `lobby` con error (vía equipoError).
  const [creando, setCreando] = useState(false);
  const [uniendo, setUniendo] = useState(false);
  // Error de validación CLIENT-side (HTML/control/exceso). Se muestra al
  // intentar submit con un nombre inválido. Distinto a equipoError, que es
  // el del server. Limpio en cada onChange.
  const [errLocal, setErrLocal] = useState<string>("");
  // Para anunciar al lector de pantalla cuando un equipo se crea (success
  // toast inline). Vive 4s y se desvanece. No interrumpe el flujo (el
  // server ya disparó team_ready y entramos al IDE casi de inmediato).
  const [creadoToast, setCreadoToast] = useState<string>("");
  // Si el usuario llegó al hub HABIENDO ESTADO antes en un equipo (volvió
  // desde el IDE con "salirEquipo"), mostramos un "volver" en la cabecera.
  // Hoy lo derivamos del primer equipo de la lista — siempre estará ahí.
  const equipoAnterior = s.equipos[0];

  // Referencias para enfocar inputs tras errores — muscle memory: el
  // usuario teclea, falla, queremos que el cursor vuelva al input sin
  // que tenga que cazar el foco a mano.
  const refNombre = useRef<HTMLInputElement>(null);
  const refCode = useRef<HTMLInputElement>(null);

  // Si el server rebota con error (longitud, ya existe), salimos del busy
  // y enfocamos el input. equipoError se setea en `case "lobby"` del store.
  useEffect(() => {
    if (s.equipoError) {
      setCreando(false);
      setUniendo(false);
      // Si el último input que el usuario tocó fue el código, focamos ahí.
      // Si no, en el nombre. Heurística simple — "el último que tocó" se
      // approxima por cuál input está más vacío entre los dos.
      if (code) refCode.current?.focus();
      else refNombre.current?.focus();
    }
  }, [s.equipoError, code]);

  // Toast de "equipo creado": se dispara cuando pasamos a fase=team viniendo
  // de fase=lobby con `creando` activo. Lo mostramos brevemente. La fase
  // cambia en el siguiente frame, así que usamos un cleanup con timer.
  useEffect(() => {
    if (s.fase === "team" && creando && s.equipo) {
      setCreadoToast(t.hub_just_created(s.equipo.nombre));
      const id = setTimeout(() => setCreadoToast(""), 4000);
      setCreando(false);
      return () => clearTimeout(id);
    }
  }, [s.fase, creando, s.equipo, t]);

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

  // Submit crear: pasa el filtro local antes de mandar al server. Si pasa,
  // marca busy y manda. El server responde con `team_ready` (éxito) o
  // `lobby` con error.
  function onCrear() {
    const n = nombre;
    const e = validarNombreEquipo(n);
    if (e) {
      setErrLocal(t.hub_invalid_name);
      refNombre.current?.focus();
      return;
    }
    setErrLocal("");
    setCreando(true);
    crearEquipo(normalizarNombreEquipo(n));
  }

  function onUnirse() {
    const c = code.trim();
    if (!c) return;
    setUniendo(true);
    redimirInvite(c);
  }

  // Si llega un equipoError tras `uniendo`, el código de error es
  // tipográfico — limpiamos el input para que el segundo intento parta de
  // cero (UX clásica de "código inválido").
  useEffect(() => {
    if (s.equipoError && uniendo) {
      setCode("");
    }
  }, [s.equipoError, uniendo]);

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
          {/* Si llegamos aquí porque "volvimos al hub", damos un atajo
              de regreso al equipo previo. Es discreto: para el primer
              login no aparece (no hay equipos todavía). */}
          {equipoAnterior && s.fase === "lobby" && (
            <button
              className="hub-back"
              onClick={() => seleccionarEquipo(equipoAnterior.id)}
              title={t.hub_back_team}
            >
              ← {equipoAnterior.nombre}
            </button>
          )}
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

      {/* Toast inline de "equipo creado". role="status" para que lectores
          de pantalla lo anuncien sin interrumpir. */}
      {creadoToast && (
        <div className="hub-toast" role="status">{creadoToast}</div>
      )}

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
                ref={refNombre}
                id="hb-new"
                placeholder={t.hub_create_placeholder}
                value={nombre}
                onChange={(e) => {
                  setNombre(e.target.value);
                  if (errLocal) setErrLocal("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && nombre.trim() && !creando) onCrear();
                }}
                maxLength={40}
                aria-invalid={!!errLocal}
                aria-describedby={errLocal ? "hb-new-err" : undefined}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                className="primario"
                disabled={!nombre.trim() || creando}
                onClick={onCrear}
              >
                {creando ? t.hub_create_busy : t.hub_create_btn}
              </button>
            </div>
            {errLocal ? (
              <div id="hb-new-err" className="fg-err" role="alert">{errLocal}</div>
            ) : (
              <p className="fg-hint">{t.hub_create_hint}</p>
            )}
          </div>

          <div className="hub-sep" />

          <div className="fg">
            <label htmlFor="hb-code">{t.hub_join_label}</label>
            <div className="hub-row">
              <input
                ref={refCode}
                id="hb-code"
                placeholder={t.hub_join_placeholder}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && code.trim() && !uniendo) onUnirse();
                }}
                maxLength={64}
                autoComplete="off"
                spellCheck={false}
                autoCapitalize="off"
              />
              <button
                className="secundario"
                disabled={!code.trim() || uniendo}
                onClick={onUnirse}
              >
                {uniendo ? t.hub_join_busy : t.hub_join_btn}
              </button>
            </div>
            <p className="fg-hint">{t.hub_join_hint}</p>
          </div>

          {/* equipoError = mensaje del SERVER (longitud, ya existe, código
              inválido, plan lleno...). Lo mostramos con role=alert para
              que sea anunciado. Se vacía cuando el usuario tipea de nuevo
              (case "lobby" siguiente lo limpia). */}
          {s.equipoError && (
            <div className="err" role="alert">{s.equipoError}</div>
          )}
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
