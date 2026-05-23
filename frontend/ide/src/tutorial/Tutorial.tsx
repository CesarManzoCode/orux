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
import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { OruxBot, type BotPos } from "./OruxBot";
import { Spotlight } from "./Spotlight";
import { construirGuion, type Step, type StepSide, type TutorialAPI } from "./script";
import { mockClearAll } from "./mock";

function posJuntoA(el: Element, side: StepSide): BotPos {
  const r = el.getBoundingClientRect();
  // Margen entre el target y el bot. El logomark tiene 32px + glow, así
  // que 20-24px de separación deja espacio para que el ojo conecte ambos.
  const gap = 24;
  // Default: anchor top-left (top/left = esquina superior izquierda del bot).
  switch (side) {
    case "der":
      return { top: r.top + r.height / 2 - 18, left: r.right + gap, anchor: "tl" };
    case "izq":
      return { top: r.top + r.height / 2 - 18, left: r.left - gap, anchor: "tr" };
    case "abajo":
      return { top: r.bottom + gap, left: r.left + r.width / 2, anchor: "tl" };
    case "arriba":
      return { top: r.top - gap, left: r.left + r.width / 2, anchor: "bl" };
    case "centro":
    default:
      return { top: window.innerHeight / 2 - 32, left: window.innerWidth / 2, anchor: "center" };
  }
}

function posCentral(): BotPos {
  return {
    top: window.innerHeight / 2 - 60,
    left: window.innerWidth / 2,
    anchor: "center",
  };
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
  // Cada vez que entramos a un paso, corremos su `before` (típicamente,
  // mutar el mock para que la UI muestre el estado que el bot va a narrar).
  useEffect(() => {
    step?.before?.();
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
        ctaLabel={isLast ? t.tut_cta_start : undefined}
        onCta={isLast ? salir : undefined}
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
