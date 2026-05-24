// Tutorial: orquestador del onboarding interactivo. Lleva el estado del
// paso, dispara los side-effects del mock (que inyectan archivos, peers,
// propuestas, impacto en el store), posiciona el bot junto al target del
// paso actual y delega el spotlight al componente correspondiente.
//
// Trigger: el componente sólo se monta desde App.tsx cuando todas estas
// condiciones se cumplen, así que acá no hay gating:
//   - usuario dentro de un equipo (fase "team")
//   - workspace vacío (`files = {}`) — no contaminar workspaces reales
//   - `localStorage.orux_tutorial_done !== "1"` — primera entrada
//   - rol admin (los miembros invitados saltan; ya alguien les explicó)
//
// El skip es siempre visible (botón verde top-right) y también responde
// a Esc. Cualquier salida llama a `onDone`, que: limpia el mock (deja
// el workspace vacío otra vez) y persiste el flag para no volver a
// disparar el tutorial en esa sesión / navegador.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { OruxBot, type BotPos } from "./OruxBot";
import { Spotlight } from "./Spotlight";
import { construirGuion, type Step, type StepSide, type TutorialAPI } from "./script";
import { mockClearAll } from "./mock";

// Estimación del bounding box del bot (avatar 44 + gap 12 + bubble max 320
// = 376; alto promedio con 2-3 líneas de texto + posible CTA ~140). No es
// exacto (el bubble crece con el texto), pero alcanza para decidir flip y
// clamp: si nos quedamos cortos por unos píxeles, el clamp tira al borde —
// preferimos al bot pegado al borde que fuera del viewport.
const BOT_W = 376;
const BOT_H = 140;
const PAD = 12;

// Mantiene el bot DENTRO del viewport. Cada anchor define qué punto del bot
// se posa en (left, top); el bbox real del bot depende de eso. El clamp
// ajusta left/top para que el bbox completo quepa con un padding chico.
// Fix anti-overflow para zoom in del browser (ctrl+): con poco viewport,
// el bot se salía por el borde inferior o lateral y dejaba de verse.
function clampDentro(pos: BotPos): BotPos {
  const w = window.innerWidth;
  const h = window.innerHeight;
  let left = pos.left;
  let top = pos.top;
  switch (pos.anchor) {
    case "tr":
      left = Math.max(BOT_W + PAD, Math.min(left, w - PAD));
      top = Math.max(PAD, Math.min(top, h - BOT_H - PAD));
      break;
    case "bl":
      left = Math.max(PAD, Math.min(left, w - BOT_W - PAD));
      top = Math.max(BOT_H + PAD, Math.min(top, h - PAD));
      break;
    case "br":
      left = Math.max(BOT_W + PAD, Math.min(left, w - PAD));
      top = Math.max(BOT_H + PAD, Math.min(top, h - PAD));
      break;
    case "center":
      left = Math.max(BOT_W / 2 + PAD, Math.min(left, w - BOT_W / 2 - PAD));
      top = Math.max(BOT_H / 2 + PAD, Math.min(top, h - BOT_H / 2 - PAD));
      break;
    case "tl":
    default:
      left = Math.max(PAD, Math.min(left, w - BOT_W - PAD));
      top = Math.max(PAD, Math.min(top, h - BOT_H - PAD));
      break;
  }
  return { ...pos, left, top };
}

function posJuntoA(el: Element, sideDeseado: StepSide): BotPos {
  const r = el.getBoundingClientRect();
  // Margen entre el target y el bot. El logomark tiene 32px + glow, así
  // que 20-24px de separación deja espacio para que el ojo conecte ambos.
  const gap = 24;
  const w = window.innerWidth;
  const h = window.innerHeight;
  // Flip anti-overflow: si el lado pedido no entra (zoom in, target pegado
  // a un borde), probamos el opuesto. Si ninguno entra, caemos a centro —
  // preferible a un bot invisible fuera del viewport.
  let side = sideDeseado;
  if (side === "izq" && r.left - gap - BOT_W < PAD) {
    side = r.right + gap + BOT_W <= w - PAD ? "der" : "centro";
  } else if (side === "der" && r.right + gap + BOT_W > w - PAD) {
    side = r.left - gap - BOT_W >= PAD ? "izq" : "centro";
  } else if (side === "abajo" && r.bottom + gap + BOT_H > h - PAD) {
    side = r.top - gap - BOT_H >= PAD ? "arriba" : "centro";
  } else if (side === "arriba" && r.top - gap - BOT_H < PAD) {
    side = r.bottom + gap + BOT_H <= h - PAD ? "abajo" : "centro";
  }
  switch (side) {
    case "der":
      return clampDentro({ top: r.top + r.height / 2 - 18, left: r.right + gap, anchor: "tl" });
    case "izq":
      return clampDentro({ top: r.top + r.height / 2 - 18, left: r.left - gap, anchor: "tr" });
    case "abajo":
      return clampDentro({ top: r.bottom + gap, left: r.left + r.width / 2, anchor: "tl" });
    case "arriba":
      return clampDentro({ top: r.top - gap, left: r.left + r.width / 2, anchor: "bl" });
    case "centro":
    default:
      return posCentral();
  }
}

function posCentral(): BotPos {
  return clampDentro({
    top: window.innerHeight / 2 - 60,
    left: window.innerWidth / 2,
    anchor: "center",
  });
}

function posSame(a: BotPos, b: BotPos): boolean {
  return a.top === b.top && a.left === b.left && a.anchor === b.anchor;
}

export function Tutorial({
  api,
  onDone,
}: {
  api: TutorialAPI;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const steps = useMemo<Step[]>(() => construirGuion(api), [api]);
  const [idx, setIdx] = useState(0);
  const step = steps[idx];
  const isLast = idx === steps.length - 1;
  const [botPos, setBotPos] = useState<BotPos>(posCentral);
  // Escape de paso click: cuando es true, el bot muestra un CTA "Continuar"
  // que permite al usuario saltar al siguiente paso sin tener que clickear
  // el target. Se activa por timeout duro (estamos atascados) o por target
  // ausente (la sección del Inspector no se montó, el archivo no cargó, etc.).
  // Reset al cambiar de paso — más abajo, en el efecto dedicado.
  const [mostrarEscape, setMostrarEscape] = useState(false);

  // Mount-only: el tutorial necesita el inspector abierto y todas sus
  // secciones EXPANDIDAS (apunta a inspector-presencia / -propuestas /
  // -impacto y necesita que el spotlight reciba un bbox real, no la
  // cabecera plegada de 32px que casi no se ve). Disparamos un custom
  // event porque el state de `colapsadas` se hidrata de localStorage al
  // MONTAR el Inspector — un removeItem desde acá llega tarde. El
  // listener del Inspector limpia su set local y nos garantiza que las
  // secciones queden visibles.
  useEffect(() => {
    api.setInspectorOpen(true);
    try { localStorage.removeItem("orux_insp_colapso"); } catch {}
    window.dispatchEvent(new CustomEvent("orux:reset-inspector-colapso"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cleanup del mock + persiste flag. Una sola fuente de verdad para
  // "salida del tutorial" — skip, Esc o CTA final pasan todos por acá.
  const salir = useCallback(() => {
    try { localStorage.setItem("orux_tutorial_done", "1"); } catch {}
    mockClearAll();
    onDone();
  }, [onDone]);

  // ── before-effect del paso ─────────────────────────────────────────────
  // Cada vez que entramos a un paso, corremos su `before` UNA sola vez
  // (típicamente, mutar el mock para que la UI muestre el estado que el
  // bot va a narrar). El guard por step.id es defensa: si la referencia
  // de `step` cambia por un re-render del padre, el useEffect dispara
  // otra vez — sin guard, `before` mutaría el store en loop infinito.
  const beforeRun = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!step) return;
    if (beforeRun.current.has(step.id)) return;
    beforeRun.current.add(step.id);
    step.before?.();
  }, [step]);

  // ── posicionamiento del bot ────────────────────────────────────────────
  // Si el paso tiene target, ubicamos el bot al lado del target real
  // (siguiendo su bbox aún si se mueve por resize/scroll). Sin target,
  // el bot va centrado. Sólo seteamos estado si la pos cambió, para no
  // bombardear con re-renders cada frame del RAF.
  useEffect(() => {
    if (!step) return;
    let raf = 0;
    let alive = true;
    function tick() {
      if (!alive) return;
      let next: BotPos = posCentral();
      if (step.target) {
        const el = document.querySelector(`[data-tour-id="${step.target}"]`);
        if (el) {
          const r = el.getBoundingClientRect();
          // Si el target existe pero es prácticamente invisible (bbox
          // colapsado / display:none / off-screen) tratamos como "no
          // target": el bot va al centro y el spotlight muestra backdrop
          // pleno. Sin esto el bot quedaba pegado a una zona invisible y
          // la pantalla se veía sólo oscura.
          if (r.width >= 8 && r.height >= 8 &&
              r.bottom > 0 && r.right > 0 &&
              r.top < window.innerHeight && r.left < window.innerWidth) {
            next = posJuntoA(el, step.side ?? "der");
          }
        }
      }
      setBotPos((prev) => (posSame(prev, next) ? prev : next));
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(raf); };
  }, [step]);

  // ── timer de los pasos "say" ───────────────────────────────────────────
  // Para pasos automáticos, programamos avanzar después de `wait` ms
  // (default ~60ms por carácter, clampeado entre 2.4s y 7s). El último
  // paso NO se auto-avanza: muestra CTA "empezar" para que el usuario
  // confirme el cierre.
  useEffect(() => {
    if (!step) return;
    if (step.mode !== "say") return;
    if (isLast) return;
    const text = step.text(t);
    const wait = step.wait ?? Math.max(2400, Math.min(7000, text.length * 60));
    const id = window.setTimeout(() => {
      step.after?.();
      setIdx((i) => i + 1);
    }, wait);
    return () => window.clearTimeout(id);
  }, [step, t, isLast]);

  // ── Esc para salir ─────────────────────────────────────────────────────
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); salir(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [salir]);

  // ── escape de paso click (guardrail anti-atasco) ───────────────────────
  // Los pasos `say` se auto-avanzan; los `click` esperan a que el usuario
  // clickee el target. Si el target NUNCA aparece (la sección del Inspector
  // no se montó, el archivo no cargó por una race con el mock) o el usuario
  // se queda sin saber qué hacer, queda atrapado. Acá montamos un watchdog:
  //   • Si llevamos 18 s en un paso click, ofrecemos un CTA "Continuar" en
  //     el bot —el usuario sale del atasco sin abortar todo el tutorial.
  //   • Si tras 4 s el target sigue sin bbox válido, lo ofrecemos antes
  //     (no hace falta esperar 18 s si ya sabemos que la UI no respondió).
  // El último paso no entra acá: ya tiene su propio CTA "Empezar".
  useEffect(() => {
    setMostrarEscape(false);
    if (!step || step.mode !== "click" || isLast) return;
    const inicio = performance.now();
    const id = window.setInterval(() => {
      const transcurrido = performance.now() - inicio;
      if (transcurrido > 18_000) {
        setMostrarEscape(true);
        window.clearInterval(id);
        return;
      }
      if (step.target && transcurrido > 4_000) {
        const el = document.querySelector(`[data-tour-id="${step.target}"]`);
        const r = el?.getBoundingClientRect();
        const valido = !!r && r.width >= 8 && r.height >= 8 &&
          r.bottom > 0 && r.right > 0 &&
          r.top < window.innerHeight && r.left < window.innerWidth;
        if (!valido) {
          setMostrarEscape(true);
          window.clearInterval(id);
        }
      }
    }, 500);
    return () => window.clearInterval(id);
  }, [step, isLast]);

  // Acción del escape: mismo efecto que clickear el target real — ejecuta
  // el `after` del paso (si lo define) y avanza el índice. Si el paso no
  // tiene `after` (open-git, que delega al setVista real del Rail) el paso
  // queda incompleto, pero el usuario no queda atrapado: el siguiente paso
  // ya ejecuta su propio `before` y reinicia la narrativa.
  const onEscape = useCallback(() => {
    if (step?.after) step.after();
    setIdx((i) => i + 1);
  }, [step]);

  if (!step) return null;
  const text = step.text(t);

  // Click del spotlight: si el paso define `after`, lo corremos y NO
  // propagamos al target real (el efecto del mock ya hace lo necesario;
  // dejar que el target real reciba el click dispararía resolver real,
  // seleccionar real, etc., contra el backend). Si NO define `after`,
  // propagamos al target real: usado por "open-git" donde queremos que
  // `setVista` del Rail corra de verdad (es lo mismo que el usuario va a
  // hacer cuando salga del tutorial).
  const onSpotlightClick = () => {
    if (step.after) {
      step.after();
    } else if (step.target) {
      const el = document.querySelector(`[data-tour-id="${step.target}"]`);
      if (el instanceof HTMLElement) el.click();
    }
    setIdx((i) => i + 1);
  };

  return (
    <div className="tut-root" role="dialog" aria-modal="true" aria-label={t.tut_aria}>
      <Spotlight
        targetId={step.target}
        clickable={step.mode === "click"}
        onClick={onSpotlightClick}
      />
      <OruxBot
        text={text}
        pos={botPos}
        ctaLabel={
          isLast ? t.tut_cta_start
          : mostrarEscape ? t.tut_cta_continuar
          : undefined
        }
        onCta={
          isLast ? salir
          : mostrarEscape ? onEscape
          : undefined
        }
      />
      <button
        type="button"
        className="tut-skip"
        onClick={salir}
        aria-label={t.tut_skip_aria}
      >
        {t.tut_skip}
      </button>
    </div>
  );
}
