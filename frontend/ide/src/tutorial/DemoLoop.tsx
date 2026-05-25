// Demo cinemático del IDE para la landing. Corre el flujo del tutorial en
// bucle infinito mutando el store real con las funciones de mock. Encima
// renderiza un cursor simulado, halos sobre los targets antes de cada click,
// y un badge "Demo · fase actual" abajo del centro.
//
// DOS PERSPECTIVAS:
//
//   - ?p=tu (default) — vista del DUEÑO: yo soy el reviewer. Ana entra
//     como peer, edita y manda una propuesta; yo apruebo. Después un peer
//     "Premium" prepara un auto-fix y yo lo apruebo también.
//
//   - ?p=ana — vista de ANA: yo soy la editora. Tomás (peer "T") entra a
//     observar; yo edito un archivo ajeno y mando la propuesta. Después
//     veo el impacto que mi cambio causó en MI archivo (api/cobros.py) y
//     apruebo el auto-fix de Premium que la repara.
//
// SINCRONIZACIÓN: ambos iframes corren guiones distintos pero alineados al
// MISMO epoch (Math.floor(Date.now() / TOTAL_MS) * TOTAL_MS). El visitante
// ve los dos eventos del mismo flujo a la vez aunque cada iframe haya
// cargado en un instante levemente distinto. Si el visitante llega a mitad
// de ciclo, los eventos pasados que mutan estado se aplican inmediato; los
// puramente visuales (cursor, click, toast) se omiten.
//
// Pensado para servirse en /app/?demo=1&p=tu|ana&lang=es|en y embebirse
// como dos iframes verticales en el hero de la landing.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { emitToast, __setForTutorial, getState } from "../store";
import {
  mockClearAll, mockSeedRepo, mockOpenFile, mockAnaEntra,
  mockPropuestaDeAna, mockAprobar, mockImpactoCascada,
  mockAutoFixPremium, mockLimpiarImpactos, TUT, pathsPorLang,
  mockTuEntra, mockTuSale, mockEditarDraft, mockAplicarPropuestaDeAna,
} from "./mock";

// Factor global de velocidad del demo. > 1 = más lento, más legible.
// Originalmente el demo corría a velocidad nativa (50s/ciclo) y un visitante
// nuevo no alcanzaba a leer los toasts ni a registrar los hitos antes de
// que el siguiente evento los reemplazara. Subimos a 1.4 (70s/ciclo) para
// dar tiempo de lectura sin perder el ritmo cinematográfico. Todos los
// `programar(ms, ...)`, `resaltarTarget(_, ms, ...)` y la duración del
// click visual aplican este factor automáticamente.
const SPEED_FACTOR = 1.4;
const RAW_TOTAL_MS = 50000;
const TOTAL_MS = Math.round(RAW_TOTAL_MS * SPEED_FACTOR);

type Tono = "info" | "ok" | "warn";

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
  }, Math.round(ms * SPEED_FACTOR));
}

interface CursorPos { x: number; y: number; visible: boolean; }

export function DemoLoop() {
  const { t, lang } = useI18n();
  // Persona del demo: deriva del yo del store. Si yo soy Ana, vista ANA;
  // si no, vista TU (default). La identidad la fija main.tsx según ?p=…
  // al inicializar el demoMode — acá solo la leemos del store ya cargado.
  const esAna = getState().yo?.client_id === TUT.ana.client_id;

  const [paso, setPaso] = useState<{ texto: string; tono: Tono }>({
    texto: t.demo_step_setup,
    tono: "info",
  });
  const [cursor, setCursor] = useState<CursorPos>({ x: 0, y: 0, visible: false });
  const [clicking, setClicking] = useState(false);

  useEffect(() => {
    const paths = pathsPorLang(lang);
    let cancelado = false;
    const timers: number[] = [];
    let propAna = "";
    let propFix = "";

    function decir(texto: string, tono: Tono = "info"): void {
      setPaso({ texto, tono });
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
      window.setTimeout(() => setClicking(false), Math.round(700 * SPEED_FACTOR));
    }

    function arrancarCiclo(): void {
      if (cancelado) return;
      propAna = "";
      propFix = "";

      // EPOCH del ciclo: alineado al múltiplo de TOTAL_MS más cercano hacia
      // atrás. Los dos iframes (TU y ANA) calculan el MISMO epoch porque
      // ambos miran Date.now() y dividen por la misma constante. Eso los
      // sincroniza sin postMessage ni BroadcastChannel.
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
        // Aplicar SPEED_FACTOR al timestamp del evento. Los guiones siguen
        // usando los tiempos "lógicos" (0, 2500, 7800…) y el factor hace
        // el resto — cambiar el ritmo del demo es modificar una constante.
        const adjustedMs = Math.round(ms * SPEED_FACTOR);
        const delay = (cicloStart + adjustedMs) - Date.now();
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
      // TOTAL_MS — los dos iframes nunca se desfasan más allá del jitter
      // de un solo setTimeout. Pasamos RAW_TOTAL_MS porque `programar` ya
      // multiplica por SPEED_FACTOR internamente; pasar TOTAL_MS (que ya
      // viene escalado) duplicaría el escalado.
      programar(RAW_TOTAL_MS, () => arrancarCiclo());
    }

    // ──────────────────────────────────────────────────────────────────
    // GUIÓN TU — vista del DUEÑO (?p=tu, default).
    //
    // Tomás soy yo. Soy dueño de tests/ y models/. Arranco viendo MI
    // archivo (tests/test_pago.py) — no el de Ana, porque eso confundía:
    // ambos iframes mostrando el MISMO archivo le quita sentido a la
    // dualidad. Cuando Ana se conecta y abre procesar_pago.py, yo me
    // muevo allá para revisar lo que está haciendo. Ana propone, yo
    // apruebo. El impacto cae sobre mi tests/, y yo arreglo MI tests a
    // mano (Premium solo arregla el lado de Ana, en api/).
    // ──────────────────────────────────────────────────────────────────
    function ejecutarGuionTu(
      programar: (ms: number, fn: () => void, opts?: { soloEstado?: boolean }) => void,
    ): void {
      const selFileTests = `[data-tour-id="file-${paths.tests}"]`;

      // ── 0-2s · Setup. Tomás abre SU archivo (tests/), no el de Ana.
      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.tests);
        decir(t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(1000, () => cursorEnReposo());

      // ── 3.5-5.5s · Ana se conecta y abre procesar_pago.py.
      programar(3500, () => {
        mockAnaEntra(paths.main, 1);
        decir(t.demo_step_ana_enters, "info");
        emitToast(t.demo_step_ana_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2400, "suave");
      }, { soloEstado: true });

      // ── 5.5-7.5s · Tomás (yo) cambia al archivo de Ana para revisar.
      programar(5500, () => {
        mockOpenFile(paths.main);
      }, { soloEstado: true });

      // ── 7.5-10s · Ana edita la línea 1 (rename). Peer cursor visible.
      programar(7500, () => {
        mockAnaEntra(paths.main, 1);
        decir(t.demo_step_ana_editing, "info");
        emitToast(t.demo_step_ana_editing, "ok");
      }, { soloEstado: true });

      // ── 10-13s · Propuesta llega. PropCard aparece en el Inspector.
      programar(10000, () => {
        propAna = mockPropuestaDeAna(lang);
        decir(t.demo_step_ana_proposes, "info");
        emitToast(t.demo_step_ana_proposes, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 3000, "suave");
      }, { soloEstado: true });

      // ── 13-15.5s · Cursor va al Aprobar.
      programar(13000, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 3000, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });

      // ── 15.5-17s · Click + aprobación aplicada.
      programar(15500, () => clickear());
      programar(15800, () => {
        if (propAna) mockAprobar(propAna);
        decir(t.demo_step_approved, "ok");
        emitToast(t.demo_step_approved, "ok");
      }, { soloEstado: true });
      programar(17000, () => cursorEnReposo());

      // ── 18-22s · Impacto detectado en cascada (api + tests).
      programar(18000, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(18300, () => {
        decir(t.demo_step_impact, "warn");
        emitToast(t.demo_step_impact, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 3200, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 3000, "warn");
      });

      // ── 22-25s · Cursor → tests/test_pago.py (MI archivo afectado).
      programar(22000, () => {
        resaltarTarget(selFileTests, 2800, "fuerte");
        moverCursorA(selFileTests);
      });

      // ── 25-27s · Click + abrir tests/. "Te toca arreglar a mano".
      programar(24500, () => clickear());
      programar(24800, () => {
        mockOpenFile(paths.tests);
        decir(t.demo_step_focus_impact, "info");
        emitToast(t.demo_step_focus_impact, "ok");
      }, { soloEstado: true });
      programar(26000, () => cursorEnReposo());

      // ── 28-37s · Tomás está ajustando tests/ por su lado. Mientras
      //    tanto, en el otro iframe Premium auto-arregla api/. Para que
      //    se SIENTA actividad, mostramos que Premium también está
      //    presente (visible en el sidebar), pero NO disparamos su
      //    propuesta acá — el autofix lo aprueba Ana en su iframe.
      programar(28500, () => {
        premiumEntra(paths.api, 3);
        decir(t.demo_step_premium_enters, "info");
        emitToast(t.demo_step_premium_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2400, "suave");
      }, { soloEstado: true });

      // ── 34-37s · Sincronización final. El autofix se aplicó en otro
      //    lado, los impactos se limpian para todos (es el broadcast real
      //    del producto), Premium se desconecta. Tomás ve "todo verde".
      programar(34000, () => {
        mockLimpiarImpactos();
        premiumSale();
        decir(t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });

      // ── 38-42s · Reposo final.
      programar(38000, () => decir(t.demo_step_calm, "ok"));
    }

    // ──────────────────────────────────────────────────────────────────
    // GUIÓN ANA — vista de la EDITORA (?p=ana).
    //
    // El mismo flujo, pero contado desde el otro lado. Ana no es peer:
    // Ana ES el "yo". Tomás (peer T) es quien aparece de remoto. Ana
    // edita un archivo que no es suyo, eso queda como draft local; manda
    // la propuesta y espera. Cuando Tomás aprueba (simulado), el draft se
    // aplica. Después Ana ve que su rename causó impacto en su propio
    // api/cobros.py (ella sí es dueña), y aprueba el auto-fix de Premium.
    //
    // Tiempos sincronizados con el guión TU para que ambos iframes muestren
    // el mismo "evento global" al mismo segundo del ciclo.
    // ──────────────────────────────────────────────────────────────────
    function ejecutarGuionAna(
      programar: (ms: number, fn: () => void, opts?: { soloEstado?: boolean }) => void,
    ): void {
      const selFileApi = `[data-tour-id="file-${paths.api}"]`;

      // Contenido del rename completo (mismo que PROPUESTA_ANA_* en mock.ts;
      // lo armamos acá para no exponer constantes del mock).
      const renamed = lang === "en"
        ? "def charge_payment(amount, currency):\n    if amount <= 0:\n        return None\n    payment = Payment(amount, currency)\n    return payment.charge()\n"
        : "def cobrar_pago(monto, moneda):\n    if monto <= 0:\n        return None\n    pago = Pago(monto, moneda)\n    return pago.cobrar()\n";

      // ── 0-2s · Setup. Ana abre EL archivo que va a editar.
      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(1000, () => cursorEnReposo());

      // ── 3.5-5.5s · Tomás se conecta a tests/ (su archivo). No viene a
      //    procesar_pago — está en lo suyo. Eso distingue las dos vistas:
      //    el sidebar de Ana muestra Tomás en tests/, no acá.
      programar(3500, () => {
        mockTuEntra(paths.tests, 1);
        decir(t.demo_step_tu_enters, "info");
        emitToast(t.demo_step_tu_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2400, "suave");
      }, { soloEstado: true });

      // ── 7.5-10s · Ana edita. El cambio va a DRAFT (no es dueña). El
      //    editor refleja el contenido nuevo in-flight, y el badge cuenta
      //    qué cambió en lenguaje humano ("renombras procesar_pago...").
      programar(7500, () => {
        mockEditarDraft(paths.main, renamed);
        decir(t.demo_step_ana_editing_mine, "info");
        emitToast(t.demo_step_ana_editing_mine, "ok");
      }, { soloEstado: true });

      // ── 10-13s · Ana manda la propuesta. Estado: draft sigue, marca de
      //    "enviada · esperando" en el badge. En este iframe NO aparece
      //    PropCard (las PropCard son propuestas que llegan, no que envías).
      programar(10000, () => {
        decir(t.demo_step_ana_sending, "info");
        emitToast(t.demo_step_ana_sending, "ok");
      });

      // ── 15.5-17s · Click "fantasma" sincronizado con Tomás. Refuerza la
      //    sensación de coordinación cross-iframe. El draft se aplica al
      //    archivo, el badge confirma: "Tomás aprobó".
      programar(15500, () => clickear());
      programar(15800, () => {
        mockAplicarPropuestaDeAna(paths.main, lang);
        decir(t.demo_step_tu_approved, "ok");
        emitToast(t.demo_step_tu_approved, "ok");
      }, { soloEstado: true });
      programar(17000, () => cursorEnReposo());

      // ── 18-22s · Impacto detectado. Ana causó el rename; api/cobros.py
      //    (ella dueña) y tests/test_pago.py (Tomás dueño) salen afectados.
      programar(18000, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(18300, () => {
        decir(t.demo_step_impact_mine, "warn");
        emitToast(t.demo_step_impact_mine, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 3200, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 3000, "warn");
      });

      // ── 22-25s · Cursor → api/cobros.py (SU archivo afectado).
      programar(22000, () => {
        resaltarTarget(selFileApi, 2800, "fuerte");
        moverCursorA(selFileApi);
      });

      // ── 25-27s · Click + abrir api/. "Hay que ajustar tu api".
      programar(24500, () => clickear());
      programar(24800, () => {
        mockOpenFile(paths.api);
        decir(t.demo_step_focus_impact_mine, "info");
        emitToast(t.demo_step_focus_impact_mine, "ok");
      }, { soloEstado: true });
      programar(26000, () => cursorEnReposo());

      // ── 28.5-31s · Premium entra y prepara el auto-fix.
      programar(28500, () => {
        premiumEntra(paths.api, 3);
        decir(t.demo_step_premium_enters, "info");
        emitToast(t.demo_step_premium_enters, "ok");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2400, "suave");
      }, { soloEstado: true });

      // ── 30.5-33s · Premium manda el auto-fix. Como Ana es dueña de api,
      //    la PropCard SÍ le llega — y va a aprobarla. Halo suave en
      //    propuestas para que el visitante vea DÓNDE apareció.
      programar(30500, () => {
        propFix = mockAutoFixPremium(lang);
        decir(t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 3000, "suave");
      }, { soloEstado: true });

      // ── 33-34s · Cursor → Aprobar el auto-fix.
      programar(32500, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2800, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });

      // ── 34-35s · Click + aprobado. Impactos limpios, Premium se va.
      programar(34000, () => clickear());
      programar(34300, () => {
        if (propFix) mockAprobar(propFix);
        mockLimpiarImpactos();
        premiumSale();
        mockTuSale();
        decir(t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });
      programar(35500, () => cursorEnReposo());

      // ── 38-42s · Reposo final.
      programar(38000, () => decir(t.demo_step_calm, "ok"));
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
      <DemoBadge paso={paso} label={t.demo_label} />
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

// Pildora "Demo · fase actual" fija bottom-center. Tres razones: honestidad
// (esto es demo, no real), contexto (qué está pasando), pacing (cross-fade
// del texto da feedback del bucle).
function DemoBadge({
  paso, label,
}: { paso: { texto: string; tono: Tono }; label: string }) {
  return (
    <div className="demo-badge" role="status" aria-live="polite">
      <span className="demo-badge-dot" aria-hidden />
      <span className="demo-badge-l">{label}</span>
      <span className="demo-badge-sep" aria-hidden>·</span>
      <span
        key={paso.texto}
        className={"demo-badge-r tone-" + paso.tono}
      >
        {paso.texto}
      </span>
    </div>
  );
}
