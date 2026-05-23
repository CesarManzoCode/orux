import { useEffect, useId, useState, type ReactNode } from "react";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import { T, cargaLang, guardaLang, type Lang, type Traducciones } from "./i18n";

const APP = "/app";

// Logomark de marca — la figura hexafoil. Solo la marca, sin wordmark;
// el texto "Orux" se compone aparte. Gradiente plateado/acero coherente
// con la dirección de arte "Infraestructura". useId() le da un id único
// al <linearGradient> para que dos instancias en la misma página (nav +
// footer) no colisionen entre sí.
function Logomark({ size = 22, className }: { size?: number; className?: string }) {
  const id = useId();
  const gradId = `lm-silver-${id}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="45%" stopColor="#C8C8CC" />
          <stop offset="100%" stopColor="#6E6E72" />
        </linearGradient>
      </defs>
      <g transform="translate(24,24)" fill="none" stroke={`url(#${gradId})`}
        strokeWidth="2.2" strokeLinejoin="round">
        <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        <g transform="rotate(60)"><path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" /></g>
        <g transform="rotate(120)"><path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" /></g>
        <g transform="rotate(180)"><path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" /></g>
        <g transform="rotate(240)"><path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" /></g>
        <g transform="rotate(300)"><path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" /></g>
        <circle cx="0" cy="0" r="1.9" fill={`url(#${gradId})`} stroke="none" />
      </g>
    </svg>
  );
}

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};
// Stagger del hero: 0.05 (no 0.08) — la cascada se siente "instrumento
// se asienta", no "se está dibujando despacio". Con 9 hijos, 0.05 deja
// el último item en 360ms, dentro del bolsillo del TTI percibido.
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
};

function Reveal({
  children, delay = 0, className,
}: { children: ReactNode; delay?: number; className?: string }) {
  // Con prefers-reduced-motion el contenido se monta directo en su sitio
  // final: framer-motion anima por JS, así que el `animation: none` del
  // CSS no lo frena — hay que cortarlo acá, arrancando ya en "show".
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} variants={fadeUp}
      initial={reduce ? "show" : "hidden"} whileInView="show"
      viewport={{ once: true, amount: 0.4 }} transition={{ delay }}>
      {children}
    </motion.div>
  );
}

function Head({ k, children, sub }: { k: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <>
      <Reveal><div className="kicker">{k}</div></Reveal>
      <Reveal delay={0.06}><h2 className="lead">{children}</h2></Reveal>
      {sub && <Reveal delay={0.1}><p className="sec-sub">{sub}</p></Reveal>}
    </>
  );
}

function Brand({ href = "#top", tag }: { href?: string; tag?: boolean }) {
  return (
    <a className="brand" href={href}>
      <Logomark className="mk" size={24} />
      <b>Orux</b>
      {tag && <span className="tag">coordination layer</span>}
    </a>
  );
}

/* Selector de idioma para la landing */
function LangPill({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  return (
    <span className="lnd-lang">
      <button className={lang === "es" ? "ll-active" : ""} onClick={() => setLang("es")}>ES</button>
      <button className={lang === "en" ? "ll-active" : ""} onClick={() => setLang("en")}>EN</button>
    </span>
  );
}

/* Tabla comparativa antes/después (reemplaza el diagrama .risk anterior) */
type CmpRow = { topic: string; left: string; right: string };
function Compare({
  headLeft, headRight, rows, foot, footB,
}: {
  headLeft: string; headRight: string;
  rows: readonly CmpRow[];
  foot: string; footB: string;
}) {
  return (
    <div className="compare">
      <div className="cmp-head" role="row">
        <div className="cmp-h-topic" />
        <div className="h-left" role="columnheader">{headLeft}</div>
        <div className="h-right" role="columnheader">{headRight}</div>
      </div>
      {rows.map((r) => (
        <div className="cmp-row" role="row" key={r.topic}>
          <div className="cmp-topic">{r.topic}</div>
          <div className="cmp-left"  data-label={headLeft}>{r.left}</div>
          <div className="cmp-right" data-label={headRight}>{r.right}</div>
        </div>
      ))}
      <div className="cmp-foot">
        <span className="x" aria-hidden>⚠</span>
        <div>{foot}<b>{footB}</b></div>
      </div>
    </div>
  );
}

/* Card de pilar con bloques WHAT/WHY/BENEFIT */
function Pillar({
  dot, title, idx, screen, h3, what, why, benefit, labels,
}: {
  dot: string; title: string; idx: string;
  screen: ReactNode; h3: string;
  what: string; why: string; benefit: string;
  labels: { what: string; why: string; benefit: string };
}) {
  return (
    <div className="mod">
      <div className="mod-h">
        <span className="d" style={{ background: dot }} /> {title}
        <span className="ix">{idx}</span>
      </div>
      <div className="mod-screen">{screen}</div>
      <div className="mod-cap">
        <h3>{h3}</h3>
        <div className="mod-bits">
          <div className="mod-bit"><span className="lab">{labels.what}</span><p>{what}</p></div>
          <div className="mod-bit"><span className="lab">{labels.why}</span><p>{why}</p></div>
          <div className="mod-bit benefit"><span className="lab">{labels.benefit}</span><p>{benefit}</p></div>
        </div>
      </div>
    </div>
  );
}

/* Tarjeta de audiencia (para quién es) */
function AudienceCard({
  idx, t, d, b,
}: { idx: string; t: string; d: string; b: readonly string[] }) {
  return (
    <div className="aud-card">
      <div className="aud-h">
        <span className="aud-ix">{idx}</span>
      </div>
      <h3>{t}</h3>
      <p>{d}</p>
      <ul>{b.map((it) => <li key={it}>{it}</li>)}</ul>
    </div>
  );
}

/* Tarjeta de seguridad */
function SecCard({ t, d }: { t: string; d: string }) {
  return (
    <div className="sec-card">
      <div className="sec-shield" aria-hidden>
        <svg viewBox="0 0 16 16" fill="none">
          <path d="M8 1.5 L13.5 3.5 V8.2 C13.5 11.5 11 13.5 8 14.5 C5 13.5 2.5 11.5 2.5 8.2 V3.5 Z"
            stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
          <path d="M5.5 8.2 L7.2 9.9 L10.5 6.6" stroke="currentColor" strokeWidth="1.2"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <h3>{t}</h3>
      <p>{d}</p>
    </div>
  );
}

/* FAQ accordion */
type FaqItem = { q: string; a: string };
function Faq({ items }: { items: readonly FaqItem[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="faq" role="list">
      {items.map((it, i) => {
        const isOpen = open === i;
        const aId = `faq-a-${i}`;
        return (
          <div className={"faq-item" + (isOpen ? " open" : "")} key={i} role="listitem">
            <button
              type="button"
              className="faq-q"
              aria-expanded={isOpen}
              aria-controls={aId}
              onClick={() => setOpen(isOpen ? null : i)}
            >
              <span>{it.q}</span>
              <span className="chev" aria-hidden>
                <svg viewBox="0 0 12 12" fill="none">
                  <path d="M2 4.5 L6 8.5 L10 4.5" stroke="currentColor"
                    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  id={aId}
                  className="faq-a"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                >
                  <div className="faq-a-inner">{it.a}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
 * STAGE — el "video sin video" del hero. Loop de ~12s, infinito, SIEMPRE
 * activo: sin observer que lo apague fuera de viewport, sin pausa al
 * hover, sin honor a prefers-reduced-motion. La animación es parte de
 * la identidad del producto; el visitante debe verla pase lo que pase.
 *
 * Las 4 fases:
 *   1) edit    — Ana modifica la firma de claim() en vivo (typing).
 *   2) detect  — card ▲ "Impacto" aterriza con blur+spring, lista 4 usos.
 *   3) propose — card ◇ "Propuesta" aterriza, cursor T cae sobre Aprobar.
 *   4) synced  — Aprobar → check verde, status ↑2→↑3, chip "sincronizado".
 *
 * Cada card vive dentro de un <motion.div> wrapper que aporta la entrada
 * cinematográfica (opacity + y + scale + blur con spring), mientras el
 * div.float interior mantiene su perspectiva 3D estática (rotateY -11deg)
 * en CSS. Así no hay choque de transforms y los media queries de mobile
 * siguen funcionando (apuntan al .card-slot, no al .float).
 * ───────────────────────────────────────────────────────────────────── */
type StagePhase = "edit" | "detect" | "propose" | "synced";
const PHASE_ORDER: readonly StagePhase[] = ["edit", "detect", "propose", "synced"];
const PHASE_MS: Record<StagePhase, number> = {
  edit:    3200,
  detect:  2800,
  propose: 3400,
  synced:  2600,
};
const TYPE_TARGET = ", user";

function useStagePhase(): StagePhase {
  const [phase, setPhase] = useState<StagePhase>("edit");
  useEffect(() => {
    const t = setTimeout(() => {
      setPhase((p) => PHASE_ORDER[(PHASE_ORDER.indexOf(p) + 1) % PHASE_ORDER.length]);
    }, PHASE_MS[phase]);
    return () => clearTimeout(t);
  }, [phase]);
  return phase;
}

// "Typing" del ", user" durante la fase edit. En cualquier otra fase la
// firma se muestra ya completa — porque el frame post-edit debe contar
// "esto ya cambió, ahora corresponde mirar el impacto".
function useTyping(phase: StagePhase) {
  const [typed, setTyped] = useState("");
  useEffect(() => {
    if (phase !== "edit") { setTyped(TYPE_TARGET); return; }
    setTyped("");
    let i = 0;
    let iv: ReturnType<typeof setInterval> | null = null;
    const start = setTimeout(() => {
      iv = setInterval(() => {
        i += 1;
        setTyped(TYPE_TARGET.slice(0, i));
        if (i >= TYPE_TARGET.length && iv) { clearInterval(iv); iv = null; }
      }, 160);
    }, 650);
    return () => {
      clearTimeout(start);
      if (iv) clearInterval(iv);
    };
  }, [phase]);
  return typed;
}

// Transición compartida para las dos cards: spring suave + opacity/filter
// con cubic-bezier (el spring queda raro aplicado a opacity y blur). El
// resultado es: la card cae desde abajo-borrosa-pequeña hacia su posición
// real con un pequeño "settle" cinematográfico, no rebote de juguete.
const cardEnterTransition = {
  type: "spring" as const,
  damping: 26,
  stiffness: 200,
  mass: 0.9,
  opacity: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
  filter:  { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
};

function Stage({ t }: { t: Traducciones }) {
  const phase = useStagePhase();
  const typed = useTyping(phase);

  const showImpact = phase !== "edit";
  const showProp   = phase === "propose" || phase === "synced";
  const synced     = phase === "synced";
  const editing    = phase === "edit";
  const riskHalo   = phase === "detect" || phase === "propose";

  return (
    <div className={"stage stage-anim phase-" + phase} aria-hidden>
      <div className="stage-back2" />
      <div className="stage-back" />
      <div className="ide">
        <div className="ide-bar">
          <span className="tl r" /><span className="tl y" /><span className="tl g" />
          <span className="ide-path">workspace · <span className="br">main</span></span>
          <span className="ide-live">
            <span className="faces">
              <i className="face" style={{ background: "#43b98a" }}>T</i>
              <i className="face" style={{ background: "#6ea8e6" }}>A</i>
              <i className="face" style={{ background: "#d6a341" }}>K</i>
            </span>
            <span>{t.stage_live}</span>
          </span>
        </div>
        <div className="ide-body">
          <aside className="ide-rail">
            <div className="rail-h">core /</div>
            <span className="f"><span className="dirn">›</span> roster.py</span>
            <span className="f"><span className="dirn">›</span> sync.py <em className="own peer">Ana</em></span>
            <span className="f"><span className="dirn">›</span> impact.py</span>
            <span className="f"><span className="dirn">›</span> git.py</span>
            <div className="rail-h" style={{ marginTop: 12 }}>api /</div>
            <span className="f on"><span className="dirn">›</span> routes.py <em className="own me">{t.stage_mine}</em></span>
          </aside>
          <div className="ide-code">
            {/* Línea 11 — Ana edita la firma de claim. Fase 1: cursor de
                Ana visible + typing en vivo. Fase 2+: firma completa, halo
                ámbar (línea cambiada, posible impacto). */}
            <div className={"ln" + (editing ? " peer" : "") + (riskHalo ? " risk" : "")}>
              <span className="n">11</span>
              <code>
                <span className="kw">def</span>{" "}
                <span className="fn">claim</span>(path<span className="typed">{typed}</span>):
              </code>
              {editing && <span className="cursor cursor-ana">Ana</span>}
            </div>
            <div className="ln"><span className="n">12</span><code>    owners[path] = user</code></div>
            <div className="ln"><span className="n">13</span><code>    <span className="kw">return</span> Ownership(path)</code></div>
            <div className="ln"><span className="n">14</span><code></code></div>
            <div className="ln me"><span className="n">15</span><code><span className="kw">def</span> <span className="fn">presence</span>(line):</code></div>
            <div className="ln me"><span className="n">16</span><code>    roster.touch(line)</code></div>
            <div className="ln me"><span className="n">17</span><code>    broadcast(<span className="st">"presence"</span>)</code></div>
          </div>
        </div>
        <div className="ide-status">
          <span className="s acc"><span className="dotg" /> main</span>
          <span className="s s-up">↑{synced ? "3" : "2"} ↓0</span>
          <span className="s">{t.stage_live}</span>
          <span className="s acc">{t.stage_clean}</span>
          <span className="s push">Python · UTF-8</span>
        </div>

        <AnimatePresence>
          {synced && (
            <motion.div
              className="synced-chip"
              initial={{ opacity: 0, y: 14, scale: 0.88 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.92 }}
              transition={{ type: "spring", damping: 20, stiffness: 380, mass: 0.7 }}
            >
              <span className="check" aria-hidden>✓</span>
              <span>{t.stage_synced}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Slot externo posicionado (CSS) + motion wrapper (entrada cinemática)
          + .float con su perspectiva 3D propia. Tres capas para que cada
          parte haga UNA cosa y no chocar transforms. */}
      <motion.div
        className="card-slot card-slot-impact"
        initial={{ opacity: 0, y: 24, scale: 0.92, filter: "blur(10px)" }}
        animate={{
          opacity: showImpact ? 1 : 0,
          y:       showImpact ? 0 : 24,
          scale:   showImpact ? 1 : 0.92,
          filter:  showImpact ? "blur(0px)" : "blur(10px)",
        }}
        transition={cardEnterTransition}
      >
        <div className="float card-impact">
          <div className="ft"><span className="ic">▲</span> {t.stage_impact_title}</div>
          <div className="body">
            {t.stage_impact_body1} <code>claim()</code> {t.stage_impact_body2}{" "}
            <b>4 {t.stage_impact_count}</b> {t.stage_impact_body3}
          </div>
          <div className="uses">
            {["server/sync.py:142","api/routes.py:88","cli/admin.py:14","tests/test_own.py:23"].map((u, i) => (
              <motion.span
                key={u}
                initial={false}
                animate={{
                  opacity: showImpact ? 1 : 0,
                  x:       showImpact ? 0 : -10,
                }}
                transition={{
                  duration: 0.42,
                  ease: [0.22, 1, 0.36, 1],
                  delay: showImpact ? 0.28 + i * 0.085 : 0,
                }}
              >{u}</motion.span>
            ))}
          </div>
          <div className="auto">{t.stage_impact_auto}</div>
        </div>
      </motion.div>

      <motion.div
        className={"card-slot card-slot-prop" + (synced ? " is-synced" : "")}
        initial={{ opacity: 0, y: 28, scale: 0.92, filter: "blur(10px)" }}
        animate={{
          opacity: showProp ? 1 : 0,
          y:       showProp ? 0 : 28,
          scale:   showProp ? 1 : 0.92,
          filter:  showProp ? "blur(0px)" : "blur(10px)",
        }}
        transition={cardEnterTransition}
      >
        <div className={"float card-prop" + (synced ? " is-synced" : "")}>
          <div className="ft"><span className="ic">◇</span> {t.stage_prop_title}</div>
          <div className="meta">{t.stage_prop_meta} <b>+12 −3</b> · impacto calculado</div>
          <div className="acts">
            <span className={"ap" + (phase === "propose" ? " is-pressed" : "")}>
              {synced ? <span className="ap-check" aria-hidden>✓</span> : t.stage_prop_approve}
              <AnimatePresence>
                {phase === "propose" && (
                  <motion.span
                    className="ptr-T"
                    initial={{ opacity: 0, x: 22, y: 22, scale: 0.55 }}
                    animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ type: "spring", damping: 18, stiffness: 280, mass: 0.7, delay: 0.45 }}
                    aria-hidden
                  >T</motion.span>
                )}
              </AnimatePresence>
            </span>
            <span className="vw">{t.stage_prop_view}</span>
          </div>
          <div className="pend">{synced ? t.stage_synced : t.stage_prop_pend}</div>
        </div>
      </motion.div>
    </div>
  );
}

export function App() {
  const reduce = useReducedMotion();
  // Dos disparadores distintos para dos efectos distintos:
  //  · `scrolled` apenas salgas del top → activa el fondo translúcido
  //    del nav (es un acabado: "ya empezaste a leer").
  //  · `pastHero` cuando dejás atrás el hero (~viewport completo) →
  //    activa el sticky CTA móvil. Antes ambos usaban el mismo umbral
  //    (16px), así que el sticky aparecía a los 4 px de scroll y robaba
  //    fold antes de que el visitante hubiese leído el pitch.
  const [scrolled, setScrolled] = useState(false);
  const [pastHero, setPastHero] = useState(false);
  const [lang, setLangState] = useState<Lang>(cargaLang);
  const t = T[lang];

  const setLang = (l: Lang) => { guardaLang(l); setLangState(l); };

  useEffect(() => {
    const on = () => {
      const y = window.scrollY;
      setScrolled(y > 16);
      // Umbral móvil: ~80% del viewport. El sticky entra cuando el
      // visitante DEJÓ el hero, no cuando movió el dedo.
      setPastHero(y > Math.min(window.innerHeight * 0.8, 720));
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  // Sincroniza el atributo lang del <html> con el idioma elegido
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const heroInit = reduce ? "show" : "hidden";

  return (
    <>
      <div className="grid-bg" aria-hidden />
      <div className="traces" aria-hidden />
      <div className="vignette" aria-hidden />

      <nav className={"nav" + (scrolled ? " scrolled" : "")}>
        <div className="wrap">
          <Brand tag />
          <div className="nav-links">
            <a href="#problema">{t.nav_problema}</a>
            <a href="#pilares">{t.nav_pilares}</a>
            <a href="#como">{t.nav_como}</a>
            <a href="#seguridad">{t.nav_seguridad}</a>
            <a href="#faq">{t.nav_faq}</a>
            <a href="#precio">{t.nav_precio}</a>
          </div>
          <div className="nav-right">
            <span className="nav-stat"><i />{t.nav_produccion}</span>
            <span className="nav-sep" />
            <LangPill lang={lang} setLang={setLang} />
            <span className="nav-sep" />
            <a className="btn ghost sm" href={APP}>
              {t.nav_entrar} <span className="arr">{t.nav_arr}</span>
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <header className="hero" id="top">
        <div className="wrap">
          <motion.div className="hero-copy" variants={stagger}
            initial={heroInit} animate="show">
            <motion.div variants={fadeUp}>
              <span className="eyebrow">
                <span className="live" /> {t.hero_eyebrow}
              </span>
            </motion.div>
            <motion.h1 variants={fadeUp}>
              <span className="h1-top">{t.hero_h1_1}</span>
              <span className="dim">{t.hero_h1_2}</span>
            </motion.h1>
            <motion.p className="sub" variants={fadeUp}>{t.hero_sub}</motion.p>
            <motion.div className="cta" variants={fadeUp}>
              <a className="btn primary lg" href={APP}>
                {t.hero_cta_primary} <span className="arr">→</span>
              </a>
              <a className="btn ghost lg" href="#como">{t.hero_cta_secondary}</a>
            </motion.div>
            {/* Pill de tiempo-a-valor justo bajo el CTA: empuja la sensación
                "es rapidísimo entrar" sin gritar — el usuario ya leyó el
                pitch, ahora le decimos cuánto cuesta probarlo. */}
            <motion.div className="hero-time" variants={fadeUp} aria-hidden>
              <span className="hero-time-dot" />
              <span>{t.hero_time}</span>
            </motion.div>
            <motion.div className="signals" variants={fadeUp}>
              <span className="sig">{t.hero_sig1} <b>{t.hero_sig1_b}</b></span>
              <span className="sig">{t.hero_sig2} <b>{t.hero_sig2_b}</b></span>
              <span className="sig">{t.hero_sig3} <b>{t.hero_sig3_b}</b></span>
            </motion.div>
          </motion.div>

          <motion.div className="hero-stage-col"
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          >
            <Stage t={t} />
            <p className="stage-cap" aria-label={t.stage_cap_aria}>
              <span className="dotg" aria-hidden /><b>{t.stage_cap_1}</b>{" "}
              <span className="dotp" aria-hidden />{t.stage_cap_2}{" "}
              <span className="dotr" aria-hidden />
              <b>{t.stage_cap_3}</b>{" "}{t.stage_cap_4}
            </p>
          </motion.div>
        </div>
      </header>

      {/* ── Trust strip ── */}
      <div className="trust">
        <div className="wrap">
          {t.trust.map((item) => (
            <div className="ti" key={item.k}>
              <span className="tk">{item.k}</span>
              <span className="tv">
                {item.v_pre && <>{item.v_pre} </>}
                <b>{item.v_b}</b>
                {item.v_post}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── PROBLEMA · tabla comparativa antes/después ── */}
      <section id="problema">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s01_k} sub={t.s01_sub}>
            {t.s01_h_1}{" "}
            <span className="soft">{t.s01_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <Compare
              headLeft={t.cmp_head_left}
              headRight={t.cmp_head_right}
              rows={t.cmp_rows}
              foot={t.cmp_foot}
              footB={t.cmp_foot_b}
            />
          </Reveal>
        </div>
      </section>

      {/* ── PILARES · WHAT/WHY/BENEFIT ── */}
      <section id="pilares">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s02_k} sub={t.s02_sub}>
            {t.s02_h_1}{" "}
            <span className="soft">{t.s02_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="modules">
              <Pillar
                dot="var(--live)" title={t.mod1_title} idx="01 / 03"
                labels={t.mod_labels}
                screen={
                  <div className="scr-pres">
                    <div className="pl x a"><span className="n">12</span><span className="bar" /><span className="who">T</span></div>
                    <div className="pl y b"><span className="n">15</span><span className="bar" /><span className="who">A</span></div>
                    <div className="pl"><span className="n">16</span><span className="bar" style={{ background: "var(--bg-3)" }} /></div>
                    <div className="pl y b"><span className="n">22</span><span className="bar" /><span className="who">A</span></div>
                  </div>
                }
                h3={t.mod1_h3} what={t.mod1_what} why={t.mod1_why} benefit={t.mod1_benefit}
              />
              <Pillar
                dot="var(--peer)" title={t.mod2_title} idx="02 / 03"
                labels={t.mod_labels}
                screen={
                  <div className="scr-own">
                    <div className="row"><span className="fl">roster.py</span><span className="ar">→</span><span className="tg me">{t.mod_own_me}</span></div>
                    <div className="row"><span className="fl">sync.py</span><span className="ar">→</span><span className="tg pe">Ana</span></div>
                    <div className="row"><span className="fl">impact.py</span><span className="ar">→</span><span className="tg fr">{t.mod_own_free}</span></div>
                    <div className="row"><span className="fl">git.py</span><span className="ar">→</span><span className="tg pe">Kai</span></div>
                  </div>
                }
                h3={t.mod2_h3} what={t.mod2_what} why={t.mod2_why} benefit={t.mod2_benefit}
              />
              <Pillar
                dot="var(--risk)" title={t.mod3_title} idx="03 / 03"
                labels={t.mod_labels}
                screen={
                  <div className="scr-imp">
                    <div className="sig">
                      <code>claim(path)</code> <span className="chg">→ claim(path, user)</span>
                    </div>
                    <div className="u"><b>sync.py:142</b></div>
                    <div className="u"><b>routes.py:88</b></div>
                    <div className="u"><b>test_own.py:23</b></div>
                    <div className="ok">{t.mod_impact_ok}</div>
                  </div>
                }
                h3={t.mod3_h3} what={t.mod3_what} why={t.mod3_why} benefit={t.mod3_benefit}
              />
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── PARA QUIÉN ES ── */}
      <section id="audiencia">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s_aud_k} sub={t.s_aud_sub}>
            {t.s_aud_h_1}{" "}
            <span className="soft">{t.s_aud_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="audience">
              {t.aud.map((p, i) => (
                <AudienceCard key={p.t} idx={"0" + (i + 1)} t={p.t} d={p.d} b={p.b} />
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── FLUJO · cómo funciona en vivo (absorbe los 'pasos') ── */}
      <section id="como">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s03_k} sub={t.s03_sub}>
            {t.s03_h_1}{" "}
            <span className="soft">{t.s03_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="flow">
              {t.flow.map((f) => (
                <div className="fn" key={f.n}>
                  <div className="fn-n">{f.n}</div>
                  <h3>{f.t}</h3>
                  <p>{f.d}</p>
                  <span className={"chip " + f.chip.cls}>{f.chip.txt}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── NO SOMOS ── */}
      <section>
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s04_k}>
            {t.s04_h_1}{" "}
            <span className="soft">{t.s04_h_2}</span>
          </Head>
          <motion.div className="nots" variants={stagger}
            initial={reduce ? "show" : "hidden"}
            whileInView="show" viewport={{ once: true, amount: 0.3 }}>
            {t.nots.map((n) => (
              <motion.div className="not" key={n} variants={fadeUp}>
                <span aria-hidden>✕</span>
                <div>{n}</div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section id="faq">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s05_k} sub={t.s05_sub}>
            {t.s05_h_1}{" "}
            <span className="soft">{t.s05_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <Faq items={t.faq} />
          </Reveal>
        </div>
      </section>

      {/* ── SEGURIDAD Y PRIVACIDAD ── */}
      <section id="seguridad">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s_sec_k} sub={t.s_sec_sub}>
            {t.s_sec_h_1}{" "}
            <span className="soft">{t.s_sec_h_2}</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="security">
              {t.sec.map((s) => (
                <SecCard key={s.t} t={s.t} d={s.d} />
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="precio">
        <span className="sec-line" />
        <div className="wrap">
          <Head k={t.s06_k} sub={t.s06_sub}>
            {t.s06_h_1}{" "}
            <span className="soft">{t.s06_h_2}</span>
          </Head>
          <motion.div className="prices" variants={stagger}
            initial={reduce ? "show" : "hidden"}
            whileInView="show" viewport={{ once: true, amount: 0.2 }}>
            <motion.div className="price" variants={fadeUp}>
              <div className="tier">{t.free_tier}</div>
              <h4>{t.free_h4}</h4>
              <p className="price-sub">{t.free_sub}</p>
              <ul>{t.free.map((f) => <li key={f}>{f}</li>)}</ul>
              <a className="btn ghost full" href={APP}>{t.free_cta}</a>
            </motion.div>
            <motion.div className="price pro" variants={fadeUp}>
              <span className="badge">{t.pro_badge}</span>
              <div className="tier">{t.pro_tier}</div>
              <h4>{t.pro_h4}</h4>
              <p className="price-sub">{t.pro_sub}</p>
              <ul>{t.pro.map((f) => <li key={f}>{f}</li>)}</ul>
              <a className="btn primary full" href={APP}>{t.pro_cta} <span className="arr">→</span></a>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="final">
        <span className="sec-line" />
        <div className="wrap">
          <Reveal><h2>{t.final_h2}</h2></Reveal>
          <Reveal delay={0.06}><p className="final-sub">{t.final_sub}</p></Reveal>
          <Reveal delay={0.12} className="final-cta">
            <a className="btn primary lg" href={APP}>{t.final_cta} <span className="arr">→</span></a>
            <a className="btn ghost lg" href="#como">{t.final_ghost}</a>
          </Reveal>
          <Reveal delay={0.18}>
            <p className="final-micro">{t.final_micro}</p>
          </Reveal>
        </div>
      </section>

      {/* ── Sticky CTA móvil (solo aparece tras dejar atrás el hero) ── */}
      <div className={"sticky-cta" + (pastHero ? " visible" : "")} aria-hidden={!pastHero}>
        <div className="sticky-l">
          <span className="sticky-dot" />
          <span>{t.sticky_label}</span>
        </div>
        <a className="btn primary sm" href={APP} tabIndex={pastHero ? 0 : -1}>
          {t.sticky_cta} <span className="arr">→</span>
        </a>
      </div>

      <footer>
        <div className="wrap">
          <div className="foot-l">
            <Brand />
            <p>{t.foot_tagline}</p>
          </div>
          <div className="foot-r">
            <a href={APP}>{t.foot_enter}</a>
            <a href="#pilares">{t.foot_what}</a>
            <a href="#como">{t.foot_how}</a>
            <a href="#faq">{t.foot_faq}</a>
            <a href="#precio">{t.foot_price}</a>
          </div>
        </div>
      </footer>
    </>
  );
}
