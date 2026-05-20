import { useEffect, useState, type ReactNode } from "react";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import { T, cargaLang, guardaLang, type Lang, type Traducciones } from "./i18n";

const APP = "/app";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

function Reveal({
  children, delay = 0, className,
}: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div className={className} variants={fadeUp}
      initial="hidden" whileInView="show"
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
      <span className="mk" aria-hidden />
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

function Stage({ t }: { t: Traducciones }) {
  return (
    <div className="stage" aria-hidden>
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
            <span className="f on"><span className="dirn">›</span> roster.py <em className="own me">{t.stage_mine}</em></span>
            <span className="f"><span className="dirn">›</span> sync.py <em className="own peer">Ana</em></span>
            <span className="f"><span className="dirn">›</span> impact.py</span>
            <span className="f"><span className="dirn">›</span> git.py</span>
            <div className="rail-h" style={{ marginTop: 12 }}>api /</div>
            <span className="f"><span className="dirn">›</span> routes.py</span>
          </aside>
          <div className="ide-code">
            <div className="ln"><span className="n">11</span><code><span className="kw">def</span> <span className="fn">claim</span>(path, user):</code></div>
            <div className="ln me"><span className="n">12</span><code>    owners[path] = user  <span className="cm"># {t.stage_mine}</span></code></div>
            <div className="ln"><span className="n">13</span><code>    <span className="kw">return</span> Ownership(path)</code></div>
            <div className="ln"><span className="n">14</span><code></code></div>
            <div className="ln peer"><span className="n">15</span><code><span className="kw">def</span> <span className="fn">presence</span>(line):</code><span className="cursor">Ana</span></div>
            <div className="ln"><span className="n">16</span><code>    roster.touch(line)</code></div>
            <div className="ln"><span className="n">17</span><code>    broadcast(<span className="st">"presence"</span>)</code></div>
          </div>
        </div>
        <div className="ide-status">
          <span className="s acc"><span className="dotg" /> main</span>
          <span className="s">↑2 ↓0</span>
          <span className="s">{t.stage_live}</span>
          <span className="s acc">{t.stage_clean}</span>
          <span className="s push">Python · UTF-8</span>
        </div>
      </div>

      <div className="float card-impact">
        <div className="ft"><span className="ic">▲</span> {t.stage_impact_title}</div>
        <div className="body">
          {t.stage_impact_body1} <code>claim()</code> {t.stage_impact_body2}{" "}
          <b>4 {t.stage_impact_count}</b> {t.stage_impact_body3}
        </div>
        <div className="uses">
          <span>server/sync.py:142</span>
          <span>api/routes.py:88</span>
          <span>cli/admin.py:14</span>
          <span>tests/test_own.py:23</span>
        </div>
        <div className="auto">{t.stage_impact_auto}</div>
      </div>

      <div className="float card-prop">
        <div className="ft"><span className="ic">◇</span> {t.stage_prop_title}</div>
        <div className="meta">{t.stage_prop_meta} <b>+12 −3</b> · impacto calculado</div>
        <div className="acts">
          <span className="ap">{t.stage_prop_approve}</span>
          <span className="vw">{t.stage_prop_view}</span>
        </div>
        <div className="pend">{t.stage_prop_pend}</div>
      </div>
    </div>
  );
}

export function App() {
  const reduce = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);
  const [lang, setLangState] = useState<Lang>(cargaLang);
  const t = T[lang];

  const setLang = (l: Lang) => { guardaLang(l); setLangState(l); };

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 16);
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
              {t.hero_h1_1}{" "}
              <span className="dim">{t.hero_h1_2}</span>
            </motion.h1>
            <motion.p className="sub" variants={fadeUp}>{t.hero_sub}</motion.p>
            <motion.div className="cta" variants={fadeUp}>
              <a className="btn primary lg" href={APP}>
                {t.hero_cta_primary} <span className="arr">→</span>
              </a>
              <a className="btn ghost lg" href="#como">{t.hero_cta_secondary}</a>
            </motion.div>
            <motion.div className="signals" variants={fadeUp}>
              <span className="sig">{t.hero_sig1} <b>{t.hero_sig1_b}</b></span>
              <span className="sig">{t.hero_sig2} <b>{t.hero_sig2_b}</b></span>
              <span className="sig">{t.hero_sig3} <b>{t.hero_sig3_b}</b></span>
            </motion.div>
          </motion.div>

          <motion.div className="hero-stage-col"
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.85, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
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
        </div>
      </section>

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
