// Demo cinemático del IDE para la landing. Corre el flujo del tutorial en
// bucle infinito mutando el store real con las funciones de mock. Encima
// renderiza un cursor simulado, halos sobre los targets antes de cada click,
// y un stepper "Paso N/6 — fase actual" arriba-izquierda.
//
// ÚNICA PERSPECTIVA (TU = dueño):
//   Tomás soy yo. Soy dueño de tests/ y models/. Ana se conecta a MI
//   archivo (procesar_pago.py), lo edita y me manda una propuesta; yo
//   apruebo. El rename causa impacto en 2 archivos; Orux Premium prepara
//   el auto-fix y se aplica → verde otra vez.
//
//   El guión de Ana sigue en código por si en algún momento querés volver
//   al hero con dos iframes, pero el visitante de la landing ve UNA sola
//   pantalla — narrativas sincronizadas en doble pantalla saturaban el
//   parser visual del visitante en los 5s que le dedica al hero.
//
// SINCRONIZACIÓN: aunque el hero monte un solo iframe hoy, mantengo el
// alineamiento al epoch absoluto (Math.floor(Date.now()/TOTAL_MS)*TOTAL_MS)
// para que si dos pestañas/instancias coincidan, vean lo mismo. Si el
// visitante llega a mitad de ciclo, los eventos pasados que mutan estado
// se aplican inmediato; los visuales (cursor, click, toast) se omiten.
//
// Pensado para servirse en /app/?demo=1&p=tu|ana&lang=es|en.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { emitToast, __setForTutorial, getState } from "../store";
import {
  mockClearAll, mockSeedRepo, mockOpenFile, mockAnaEntra,
  mockPropuestaDeAna, mockAprobar, mockImpactoCascada,
  mockAutoFixPremium, mockLimpiarImpactos, TUT, pathsPorLang,
  mockTuEntra, mockTuSale, mockEditarDraft, mockAplicarPropuestaDeAna,
} from "./mock";

// Duración total del ciclo. 35s = la mitad del demo viejo (70s). El demo
// viejo era "cinematográfico" pero ESO: cinematográfico. El visitante de
// landing no se queda 70s mirando un hero — registra 5-8s y decide si
// scrollea. Con 35s cada beat queda en 4-6s, suficiente para leer un toast
// y registrar el halo, y el ciclo cierra antes de que se aburra.
const TOTAL_MS = 35000;

type Tono = "info" | "ok" | "warn";

// El paso del guión: índice (0..total-1), total de pasos, texto narrativo
// y tono. El stepper consume esto.
interface PasoState {
  i: number;
  total: number;
  texto: string;
  tono: Tono;
}

const PASOS_TOTAL = 6;

// "Orux Premium" entra como peer mientras prepara el auto-fix. Refuerza que
// el premium es un actor más, no un botón mágico.
function premiumEntra(path: string, line: number): void {
  const peers = { ...getState().peers };
  peers[TUT.premium.client_id] = {
    client_id: TUT.premium.client_id,
    name: TUT.premium.name,
    color: "#8b5cf6",
    path,
    line,
  };
  __setForTutorial({ peers });
}

function premiumSale(): void {
  const peers = { ...getState().peers };
  delete peers[TUT.premium.client_id];
  __setForTutorial({ peers });
}

// Aplica una clase temporal a un target para resaltarlo. Tres tonos:
//   - "fuerte": halo verde intenso, para botones/files que el cursor va
//     a clickear. Llama la atención fuerte.
//   - "suave": halo verde fino con glow generoso, para áreas grandes del
//     IDE (secciones del Inspector, sidebar). Para "mirá acá, cambió" sin
//     gritar.
//   - "warn": variante ámbar del suave, para hitos de riesgo (impacto
//     detectado). Color coherente con los chips reales de severidad.
// Si el target no existe (timing raro), no hace nada — el cursor sigue
// moviéndose igual; el halo es decoración secundaria.
type Tono2 = "fuerte" | "suave" | "warn";
function resaltarTarget(selector: string, ms: number, tono: Tono2 = "fuerte"): void {
  const el = document.querySelector(selector) as HTMLElement | null;
  if (!el) return;
  const clases =
    tono === "fuerte" ? ["demo-focus"] :
    tono === "warn"   ? ["demo-focus-soft", "warn"] :
                        ["demo-focus-soft"];
  clases.forEach((c) => el.classList.add(c));
  window.setTimeout(() => {
    clases.forEach((c) => el.classList.remove(c));
  }, ms);
}

interface CursorPos { x: number; y: number; visible: boolean; }

export function DemoLoop() {
  const { t, lang } = useI18n();
  // Persona del demo: deriva del yo del store. Si yo soy Ana, vista ANA;
  // si no, vista TU (default). La identidad la fija main.tsx según ?p=…
  // al inicializar el demoMode — acá solo la leemos del store ya cargado.
  const esAna = getState().yo?.client_id === TUT.ana.client_id;

  const [paso, setPaso] = useState<PasoState>({
    i: 0, total: PASOS_TOTAL, texto: t.demo_step_setup, tono: "info",
  });
  const [cursor, setCursor] = useState<CursorPos>({ x: 0, y: 0, visible: false });
  const [clicking, setClicking] = useState(false);

  useEffect(() => {
    const paths = pathsPorLang(lang);
    let cancelado = false;
    const timers: number[] = [];
    let propAna = "";
    let propFix = "";

    function decir(i: number, texto: string, tono: Tono = "info"): void {
      setPaso({ i, total: PASOS_TOTAL, texto, tono });
    }

    // Mueve el cursor al centro del elemento que matchea `selector`. Si el
    // selector no existe (el target aún no se renderizó), oculta el cursor —
    // mejor desaparecer que apuntar a 0,0.
    function moverCursorA(selector: string): void {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) {
        setCursor((c) => ({ ...c, visible: false }));
        return;
      }
      const r = el.getBoundingClientRect();
      setCursor({
        x: r.left + r.width / 2 - 4,
        y: r.top + r.height / 2 - 4,
        visible: true,
      });
    }

    // Posición de reposo del cursor — área neutral del viewport (centro
    // arriba del editor, lejos de los paneles donde aparece la acción). El
    // cursor SIEMPRE está visible (decisión: que el visitante entienda en
    // todo momento de quién es ese cursor); entre interacciones vuelve acá.
    function cursorEnReposo(): void {
      setCursor({
        x: Math.round(window.innerWidth * 0.55),
        y: Math.round(window.innerHeight * 0.30),
        visible: true,
      });
    }

    function clickear(): void {
      setClicking(true);
      window.setTimeout(() => setClicking(false), 700);
    }

    function arrancarCiclo(): void {
      if (cancelado) return;
      propAna = "";
      propFix = "";

      // EPOCH del ciclo: alineado al múltiplo de TOTAL_MS más cercano hacia
      // atrás. Aunque el hero hoy monte un solo iframe, mantengo el
      // alineamiento por si dos pestañas/instancias del demo coinciden:
      // ambas calculan el MISMO epoch porque miran Date.now() y dividen
      // por la misma constante.
      const cicloStart = Math.floor(Date.now() / TOTAL_MS) * TOTAL_MS;

      // `programar` con dos modos:
      //   - default (visual): si el evento ya pasó en este ciclo, se SKIP.
      //     Cursor moves, clicks, toasts y resaltos son efímeros — aplicar-
      //     los fuera de tiempo confunde más que ayuda.
      //   - soloEstado: si ya pasó, se aplica INMEDIATO (sin delay). Esto
      //     vale para mutaciones del store (seed, mockAnaEntra, propuesta,
      //     impacto). Así el iframe que cargó a mitad de ciclo arranca con
      //     el estado correcto del momento y se engancha al próximo evento
      //     futuro sin desorientar al visitante.
      function programar(
        ms: number,
        fn: () => void,
        opts: { soloEstado?: boolean } = {},
      ): void {
        const delay = (cicloStart + ms) - Date.now();
        if (delay < 0) {
          if (opts.soloEstado) {
            try { fn(); } catch { /* silenciar */ }
          }
          return;
        }
        const id = window.setTimeout(() => {
          if (!cancelado) fn();
        }, delay);
        timers.push(id);
      }

      if (esAna) {
        ejecutarGuionAna(programar);
      } else {
        ejecutarGuionTu(programar);
      }

      // Próximo ciclo: alineado al siguiente epoch absoluto. Aunque este
      // ciclo haya driftado por ms, el próximo se ancla al múltiplo de
      // TOTAL_MS — nunca derivamos más allá del jitter de un solo setTimeout.
      programar(TOTAL_MS, () => arrancarCiclo());
    }

    // ──────────────────────────────────────────────────────────────────
    // GUIÓN TU — vista del DUEÑO. 6 BEATS × ~5s = 30s + 5s de cierre.
    //
    //   0 ( 0.0–3.5s)  SETUP        Tu archivo abierto
    //   1 ( 3.5–7.0s)  ANA_ENTERS   Ana se conecta
    //   2 ( 7.0–13.0s) ANA_EDITS    Ana edita + cursor en la línea
    //   3 (13.0–19.0s) APPROVE      Propuesta + aprobar (click)
    //   4 (19.0–28.0s) IMPACT       Impacto detectado en 2 archivos
    //   5 (28.0–35.0s) RESOLVED     Premium auto-fix + verde
    //
    // Halos en 4000ms (vs 2400ms del guión viejo): un halo que aparece y
    // se va en menos de 3s no le da tiempo al ojo a registrar QUÉ pulsó.
    // ──────────────────────────────────────────────────────────────────
    function ejecutarGuionTu(
      programar: (ms: number, fn: () => void, opts?: { soloEstado?: boolean }) => void,
    ): void {
      // ── BEAT 0 · SETUP (0–3.5s). Tomás abre SU archivo (procesar_pago).
      //    Mostramos el archivo de Ana desde el inicio: hace que la entrada
      //    de Ana en el beat 1 se sienta como "ya estabas mirando ahí".
      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(0, t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(800, () => cursorEnReposo());

      // ── BEAT 1 · ANA_ENTERS (3.5–7s). Ana se conecta en línea 1.
      programar(3500, () => {
        mockAnaEntra(paths.main, 1);
        decir(1, t.demo_step_ana_enters, "info");
        emitToast(t.demo_step_ana_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 4000, "suave");
      }, { soloEstado: true });

      // ── BEAT 2 · ANA_EDITS (7–13s). Ana edita. El peer-cursor azul en
      //    la línea 1 + halo suave en el editor narran "alguien está
      //    tipeando ahí". 6 segundos de ventana — el más largo de todos
      //    los beats porque acá vive el "live multiplayer".
      programar(7000, () => {
        mockAnaEntra(paths.main, 1);
        decir(2, t.demo_step_ana_editing, "info");
        emitToast(t.demo_step_ana_editing, "ok");
      }, { soloEstado: true });

      // ── BEAT 3 · APPROVE (13–19s). Propuesta llega + cursor va al
      //    botón Aprobar + click + estado aprobado.
      programar(13000, () => {
        propAna = mockPropuestaDeAna(lang);
        decir(3, t.demo_step_ana_proposes, "info");
        emitToast(t.demo_step_ana_proposes, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 4000, "suave");
      }, { soloEstado: true });
      programar(14500, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 3500, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(17000, () => clickear());
      programar(17300, () => {
        if (propAna) mockAprobar(propAna);
        decir(3, t.demo_step_approved, "ok");
        emitToast(t.demo_step_approved, "ok");
      }, { soloEstado: true });
      programar(18500, () => cursorEnReposo());

      // ── BEAT 4 · IMPACT (19–28s). El rename rompe 2 archivos. Halo
      //    ámbar en el panel de impacto + el árbol de files (los rojos
      //    aparecen ahí). 9 segundos de ventana para que el visitante
      //    procese "AH, Orux atrapó el riesgo antes del merge". Este
      //    beat es el ÚNICO con tono warn — distingue visualmente
      //    "algo grave" del flujo verde.
      programar(19500, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(19800, () => {
        decir(4, t.demo_step_impact, "warn");
        emitToast(t.demo_step_impact, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 6500, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 5500, "warn");
      });

      // ── BEAT 5 · RESOLVED (28–35s). Premium entra, prepara y aplica
      //    el auto-fix. Impactos limpios → verde. El "resolved" es
      //    explícito (no es solo silencio): el visitante necesita ver
      //    que "alguien lo arregló", no que "se calló solo".
      programar(28000, () => {
        premiumEntra(paths.api, 3);
        decir(5, t.demo_step_premium_enters, "info");
        emitToast(t.demo_step_premium_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 3500, "suave");
      }, { soloEstado: true });
      programar(30500, () => {
        propFix = mockAutoFixPremium(lang);
        decir(5, t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2800, "suave");
      }, { soloEstado: true });
      programar(33000, () => {
        if (propFix) mockAprobar(propFix);
        mockLimpiarImpactos();
        premiumSale();
        decir(5, t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });
    }

    // ──────────────────────────────────────────────────────────────────
    // GUIÓN ANA — vista de la EDITORA. CONSERVADO por compatibilidad
    // (?p=ana sigue siendo válido) pero el hero de la landing solo monta
    // TU. Si en algún futuro querés volver al hero dual, este guión está
    // listo. Tiempos alineados con el de TU para mostrar el "mismo evento
    // global" desde el otro lado.
    // ──────────────────────────────────────────────────────────────────
    function ejecutarGuionAna(
      programar: (ms: number, fn: () => void, opts?: { soloEstado?: boolean }) => void,
    ): void {
      const selFileApi = `[data-tour-id="file-${paths.api}"]`;
      const renamed = lang === "en"
        ? "def charge_payment(amount, currency):\n    if amount <= 0:\n        return None\n    payment = Payment(amount, currency)\n    return payment.charge()\n"
        : "def cobrar_pago(monto, moneda):\n    if monto <= 0:\n        return None\n    pago = Pago(monto, moneda)\n    return pago.cobrar()\n";

      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(0, t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(800, () => cursorEnReposo());

      programar(3500, () => {
        mockTuEntra(paths.tests, 1);
        decir(1, t.demo_step_tu_enters, "info");
        emitToast(t.demo_step_tu_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 4000, "suave");
      }, { soloEstado: true });

      programar(7000, () => {
        mockEditarDraft(paths.main, renamed);
        decir(2, t.demo_step_ana_editing_mine, "info");
        emitToast(t.demo_step_ana_editing_mine, "ok");
      }, { soloEstado: true });

      programar(13000, () => {
        decir(3, t.demo_step_ana_sending, "info");
        emitToast(t.demo_step_ana_sending, "ok");
      });
      programar(17000, () => clickear());
      programar(17300, () => {
        mockAplicarPropuestaDeAna(paths.main, lang);
        decir(3, t.demo_step_tu_approved, "ok");
        emitToast(t.demo_step_tu_approved, "ok");
      }, { soloEstado: true });
      programar(18500, () => cursorEnReposo());

      programar(19500, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(19800, () => {
        decir(4, t.demo_step_impact_mine, "warn");
        emitToast(t.demo_step_impact_mine, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 6500, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 5500, "warn");
      });
      programar(23500, () => {
        resaltarTarget(selFileApi, 2800, "fuerte");
        moverCursorA(selFileApi);
      });
      programar(25800, () => clickear());
      programar(26100, () => {
        mockOpenFile(paths.api);
        decir(4, t.demo_step_focus_impact_mine, "info");
        emitToast(t.demo_step_focus_impact_mine, "ok");
      }, { soloEstado: true });
      programar(27500, () => cursorEnReposo());

      programar(28000, () => {
        premiumEntra(paths.api, 3);
        decir(5, t.demo_step_premium_enters, "info");
        emitToast(t.demo_step_premium_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 3500, "suave");
      }, { soloEstado: true });
      programar(30500, () => {
        propFix = mockAutoFixPremium(lang);
        decir(5, t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2800, "suave");
      }, { soloEstado: true });
      programar(32500, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2500, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(33500, () => clickear());
      programar(33800, () => {
        if (propFix) mockAprobar(propFix);
        mockLimpiarImpactos();
        premiumSale();
        mockTuSale();
        decir(5, t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });
    }

    arrancarCiclo();

    return () => {
      cancelado = true;
      timers.forEach((id) => window.clearTimeout(id));
      // Limpiar cualquier halo que quedara colgado al desmontar (.demo-focus
      // fuerte y .demo-focus-soft incluyendo la variante .warn).
      document.querySelectorAll(".demo-focus, .demo-focus-soft").forEach((el) => {
        el.classList.remove("demo-focus", "demo-focus-soft", "warn");
      });
      mockClearAll();
    };
    // Re-disparar al cambiar lang o persona: el contenido y los paths son
    // distintos, así que el bucle anterior se desmonta limpio y arranca
    // con el nuevo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, esAna]);

  return (
    <>
      <DemoCursor
        pos={cursor}
        clicking={clicking}
        label={esAna ? t.demo_cursor_label_ana : t.demo_cursor_label}
      />
      <DemoStepper paso={paso} label={t.demo_label} />
    </>
  );
}

// Cursor del visitante. Visualmente distinto a los peers reales: flecha
// estilo puntero de mouse (los peers usan badge circular con inicial),
// etiqueta en verde marca-Orux debajo, ripple expandiendo en cada click.
function DemoCursor({
  pos, clicking, label,
}: { pos: CursorPos; clicking: boolean; label: string }) {
  return (
    <div
      className={
        "demo-cursor" +
        (pos.visible ? " is-visible" : "") +
        (clicking ? " is-clicking" : "")
      }
      style={{ left: pos.x + "px", top: pos.y + "px" }}
      aria-hidden
    >
      <svg className="demo-cursor-arrow" viewBox="0 0 18 24" fill="none">
        <path
          d="M2 2 L2 18 L6 14 L9 21 L12 20 L9 13 L15 13 Z"
          fill="#43b98a"
          stroke="#08090b"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      <span className="demo-cursor-label">{label}</span>
    </div>
  );
}

// Stepper "Paso N/6 — texto del beat" fijo top-left. Tres razones:
//   1) Honestidad: comunica que esto es demo automática.
//   2) Progreso visible: ●●●○○○ le dice al visitante "estás a la mitad",
//      así sabe que va a haber más antes de scrollear.
//   3) Contexto: el texto del beat le dice QUÉ está mirando, no descifrar
//      cambios sutiles del IDE.
//
// Reemplaza al DemoBadge bottom-center anterior: dos pills compitiendo
// por la atención era ruido; una sola unidad arriba-izquierda enmarca la
// escena sin pisarla.
function DemoStepper({
  paso, label,
}: { paso: PasoState; label: string }) {
  // ● para pasados+actual, ○ para futuros. El actual también lleva el
  // tono (.is-warn / .is-ok / .is-info) para que el dot pulse del color
  // correcto. El array de dots se renderiza explícito para que cada uno
  // sea un span — el ::before/::after no permite tantos elementos.
  const dots = [];
  for (let k = 0; k < paso.total; k++) {
    const filled = k <= paso.i;
    const isActive = k === paso.i;
    dots.push(
      <span
        key={k}
        className={
          "demo-step-dot" +
          (filled ? " is-filled" : "") +
          (isActive ? " is-active is-" + paso.tono : "")
        }
        aria-hidden
      />,
    );
  }
  return (
    <div className="demo-stepper" role="status" aria-live="polite">
      <span className="demo-stepper-label">{label}</span>
      <span className="demo-stepper-sep" aria-hidden>·</span>
      <span className="demo-stepper-dots" aria-hidden>{dots}</span>
      <span className="demo-stepper-count" aria-hidden>
        {paso.i + 1}/{paso.total}
      </span>
      <span className="demo-stepper-sep" aria-hidden>—</span>
      <span
        key={paso.texto}
        className={"demo-stepper-text tone-" + paso.tono}
      >
        {paso.texto}
      </span>
    </div>
  );
}
