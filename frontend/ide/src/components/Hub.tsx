// Hub — la pantalla "entre login y workspace". El usuario ya está
// autenticado: acá decide a qué equipo entrar, crear uno nuevo, o unirse
// con código. Tras el feedback de testing real, este componente lleva la
// validación de nombre (rechaza HTML/control/exceso ANTES de molestar al
// server), estados busy/feedback en los CTAs, y limpia el input tras error
// para que el segundo intento sea limpio.
//
// Pasada 2026-05-20: badges de rol con icono (Shield/Users) — la palabra
// "admin"/"member" sola era texto plano sin jerarquía. El botón "Abrir"
// pasa de "abrir →" en miniatura a una afordancia visible (icono pill
// que se anima al hover): el testing real mostró que usuarios nuevos no
// pulsaban la tarjeta por miedo a no saber qué hacía. Navegación por
// teclado: la tarjeta ya es `<button>`; Enter/Space abren.
import { useEffect, useRef, useState } from "react";
import {
  Shield, Users, ChevronRight, ArrowRight, ArrowLeft, ArrowUpCircle,
} from "lucide-react";
import { useStore } from "../useStore";
import {
  crearEquipo, redimirInvite, seleccionarEquipo, salir,
  iniciarCheckout, refrescarEquipos, emitToast,
} from "../store";
import { validarNombreEquipo, normalizarNombreEquipo } from "../validate";
import { useI18n, LangToggle } from "../i18n";
import { Logomark } from "./Logomark";

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
  // Capa 30: id del equipo cuyo upgrade a Premium está en curso (esperando
  // a que la API devuelva la URL de Stripe). Bloquea el doble-click.
  const [upgrading, setUpgrading] = useState<string>("");
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

  // Capa 30: arranca el pago de Premium. `iniciarCheckout` pide a la API
  // la URL de Stripe y, si todo va bien, redirige el navegador ahí mismo
  // (devuelve null y dejamos el botón en "Abriendo…" hasta que la página
  // cambie). Si devuelve un texto, es un error: lo mostramos y soltamos
  // el busy.
  async function onUpgrade(teamId: string) {
    setUpgrading(teamId);
    const err = await iniciarCheckout(teamId);
    if (err) {
      setUpgrading("");
      emitToast(t.hub_upgrade_err + err, "bad");
    }
  }

  // Si llega un equipoError tras `uniendo`, el código de error es
  // tipográfico — limpiamos el input para que el segundo intento parta de
  // cero (UX clásica de "código inválido").
  useEffect(() => {
    if (s.equipoError && uniendo) {
      setCode("");
    }
  }, [s.equipoError, uniendo]);

  // Capa 30: retorno desde Stripe. Tras pagar (o cancelar), Stripe
  // devuelve el navegador a /app/?stripe=success|cancel. Acá lo
  // detectamos, mostramos un toast y limpiamos el query param (un reload
  // no debe repetir el aviso). En `success` el plan lo sube el WEBHOOK
  // (server↔Stripe), que puede tardar un par de segundos: reintentamos
  // refrescar la lista de equipos para que el badge pase a Premium solo.
  // Efecto de montaje (el param se consume una vez); por eso deps [].
  useEffect(() => {
    const st = new URLSearchParams(window.location.search).get("stripe");
    if (!st) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (st === "success") {
      emitToast(t.hub_pay_ok, "ok");
      const a = window.setTimeout(refrescarEquipos, 3000);
      const b = window.setTimeout(refrescarEquipos, 9000);
      return () => { window.clearTimeout(a); window.clearTimeout(b); };
    }
    if (st === "cancel") emitToast(t.hub_pay_cancel, "warn");
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="hub">
      <header className="hub-head">
        <div className="hub-brand">
          <Logomark size={26} className="hub-brand-mk" />
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
              aria-label={t.hub_back_team + ": " + equipoAnterior.nombre}
            >
              <ArrowLeft size={12} aria-hidden />
              <span>{equipoAnterior.nombre}</span>
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
            <ul className="hub-teams" role="list">
              {s.equipos.map((e) => {
                const esAdmin = e.rol === "admin";
                // Capa 30: plan del equipo (default 'free' si un server
                // viejo no lo manda). Decide el badge y si se ofrece el
                // upgrade.
                const esPremium = e.plan === "premium";
                // Capa 31: cobro por asiento. `miembros` = asientos que
                // se cobran (o se cobrarían al mejorar). Si un server
                // viejo no lo manda, cae a 0 / 1 y se omite el detalle.
                const asientos = e.miembros ?? 0;
                // Texto del badge ya viene del i18n; el icono añade jerarquía
                // visual y redundancia no-cromática (a11y daltonismo).
                const rolLabel = esAdmin ? t.hub_role_admin_label : t.hub_role_member_label;
                const rolTitle = esAdmin ? t.hub_role_admin_title : t.hub_role_member_title;
                const ariaLabel = t.hub_open_aria(e.nombre, rolLabel);
                return (
                  <li key={e.id}>
                    <button
                      className="hub-team"
                      onClick={() => seleccionarEquipo(e.id)}
                      title={t.hub_open_title}
                      aria-label={ariaLabel}
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
                        <span
                          className={"ht-rol r-" + (esAdmin ? "admin" : "member")}
                          title={rolTitle}
                        >
                          {esAdmin
                            ? <Shield size={10} strokeWidth={2.3} aria-hidden />
                            : <Users size={10} strokeWidth={2.3} aria-hidden />}
                          {rolLabel}
                        </span>
                        {/* Badge de plan: Premium destaca en acento,
                            Free queda sobrio (no es un error, es el
                            estado base). Capa 31: si es premium, el badge
                            muestra los asientos cobrados ("Premium · 4")
                            — el cobro es por miembro. */}
                        <span
                          className={"ht-plan p-" + (esPremium ? "premium" : "free")}
                          title={esPremium ? t.hub_plan_premium_title : t.hub_plan_free_title}
                        >
                          {esPremium
                            ? (asientos > 0
                                ? t.hub_plan_premium_seats(asientos)
                                : t.hub_plan_premium)
                            : t.hub_plan_free}
                        </span>
                      </span>
                      <span className="ht-go" aria-hidden>
                        <span className="ht-go-tx">{t.hub_open_short}</span>
                        <ChevronRight size={14} strokeWidth={2.4} />
                      </span>
                    </button>
                    {/* Upgrade: solo el admin de un equipo free. Va FUERA
                        del botón-tarjeta (un <button> no puede anidar
                        otro): es hermano dentro del <li>, así su click no
                        abre el equipo. */}
                    {esAdmin && !esPremium && (
                      <button
                        className="ht-upgrade"
                        onClick={() => onUpgrade(e.id)}
                        disabled={upgrading === e.id}
                        title={t.hub_upgrade_title(asientos || 1)}
                      >
                        <ArrowUpCircle size={13} strokeWidth={2.2} aria-hidden />
                        {upgrading === e.id ? t.hub_upgrade_busy : t.hub_upgrade_btn}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="hub-empty">
              <div className="hub-empty-ic" aria-hidden>
                <Users size={20} />
              </div>
              <div className="hub-empty-tx">
                <b>{t.hub_empty_title}</b>
                <span>{t.hub_empty_desc}</span>
              </div>
              {/* Pista visual hacia el formulario "crear o unirme". El usuario
                  nuevo a veces no ve la columna derecha — esta flecha es
                  redundancia útil. Pure decoration: aria-hidden. */}
              <div className="hub-empty-arrow" aria-hidden>
                <ArrowRight size={18} />
                <span>{t.hub_empty_arrow}</span>
              </div>
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
