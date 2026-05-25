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
    // ──────────────────────────────────────────────────────────────────
    function ejecutarGuionTu(
      programar: (ms: number, fn: () => void, opts?: { soloEstado?: boolean }) => void,
    ): void {
      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(500, () => cursorEnReposo());

      // Ana entra y "edita" (cursor de peer moviéndose por las líneas).
      // Resaltamos la sección Presencia del Inspector para que el visitante
      // sepa DÓNDE mirar el cambio.
      programar(2500, () => {
        mockAnaEntra(paths.main, 1);
        decir(t.demo_step_ana_enters, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2200, "suave");
      }, { soloEstado: true });
      programar(3600, () => mockAnaEntra(paths.main, 2), { soloEstado: true });
      programar(4700, () => mockAnaEntra(paths.main, 4), { soloEstado: true });
      programar(5800, () => mockAnaEntra(paths.main, 5), { soloEstado: true });
      programar(6900, () => mockAnaEntra(paths.main, 4), { soloEstado: true });
      programar(7800, () => {
        decir(t.demo_step_ana_editing, "info");
        emitToast(t.demo_step_ana_editing, "ok");
      });

      // Propuesta de Ana: resaltamos la sección Propuestas mientras aparece
      // la PropCard. La PropCard misma trae su propia animación de entrada
      // (demo-prop-in); el halo apunta dónde mirar.
      programar(10500, () => {
        propAna = mockPropuestaDeAna(lang);
        decir(t.demo_step_ana_proposes, "info");
        emitToast(t.demo_step_ana_proposes, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2600, "suave");
      }, { soloEstado: true });

      // Cursor va al [aprobar], halo FUERTE en el botón, click.
      programar(13500, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2600, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(15500, () => clickear());
      programar(15800, () => {
        if (propAna) mockAprobar(propAna);
        decir(t.demo_step_approved, "ok");
        emitToast(t.demo_step_approved, "ok");
      }, { soloEstado: true });
      programar(16800, () => cursorEnReposo());

      // Impacto en cascada: resaltado WARN (ámbar) sobre la sección Impacto
      // Y sobre el sidebar (donde aparecen los chips rojos al lado de los
      // archivos afectados).
      programar(19500, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(20100, () => {
        decir(t.demo_step_impact, "warn");
        emitToast(t.demo_step_impact, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 2800, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 2600, "warn");
      });

      // Cursor investiga: va al archivo afectado en el sidebar.
      const selFileApi = `[data-tour-id="file-${paths.api}"]`;
      programar(22500, () => {
        resaltarTarget(selFileApi, 2400, "fuerte");
        moverCursorA(selFileApi);
      });
      programar(24500, () => clickear());
      programar(24800, () => {
        mockOpenFile(paths.api);
        decir(t.demo_step_focus_impact, "info");
      }, { soloEstado: true });
      programar(25800, () => cursorEnReposo());

      // Premium entra y manda auto-fix.
      programar(28000, () => {
        premiumEntra(paths.api, 3);
        decir(t.demo_step_premium_enters, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2000, "suave");
      }, { soloEstado: true });
      programar(29800, () => mockAnaEntra(paths.api, 1), { soloEstado: true });
      programar(31800, () => {
        propFix = mockAutoFixPremium(lang);
        decir(t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2600, "suave");
      }, { soloEstado: true });

      // Cursor al [aprobar] del auto-fix, halo, click.
      programar(34800, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2600, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(36800, () => clickear());
      programar(37100, () => {
        if (propFix) mockAprobar(propFix);
        mockLimpiarImpactos();
        premiumSale();
        decir(t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });
      programar(38100, () => cursorEnReposo());

      // Pausa final en "todo en orden" antes de reiniciar.
      programar(41000, () => decir(t.demo_step_calm, "ok"));
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
      const propuestaContenido = paths.main; // referencia explícita
      // El contenido final del rename viene de mock.ts (PROPUESTA_ANA_*).
      // Acá no lo importamos: usamos mockAplicarPropuestaDeAna que lo lee
      // del módulo. Para el draft (in-flight), aplicamos el MISMO contenido
      // — el visitante ve el archivo "editado" mientras espera aprobación.

      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(t.demo_step_setup, "info");
      }, { soloEstado: true });
      programar(500, () => cursorEnReposo());

      // Tomás (peer T) entra. Aparece en el sidebar y en el Inspector.
      // Resaltamos la sección Presencia para que el visitante sepa que la
      // identidad del otro lado del flujo cambió a "Tomás".
      programar(2500, () => {
        mockTuEntra(paths.main, 1);
        decir(t.demo_step_tu_enters, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2200, "suave");
      }, { soloEstado: true });
      programar(3600, () => mockTuEntra(paths.main, 2), { soloEstado: true });
      programar(4700, () => mockTuEntra(paths.main, 4), { soloEstado: true });

      // Ana edita: el cambio va a DRAFT porque no es dueña. Un solo paso
      // por simplicidad (mockEditarDraft aplica el contenido completo del
      // rename — visualmente el editor mostrará la propuesta in-flight).
      programar(5800, () => {
        // Aplicamos el contenido del rename a drafts. Usamos el mismo
        // contenido que la propuesta final para que el editor lo refleje.
        // Lo armamos manualmente acá para no exponer constantes del mock.
        const renamed = lang === "en"
          ? "def charge_payment(amount, currency):\n    if amount <= 0:\n        return None\n    payment = Payment(amount, currency)\n    return payment.charge()\n"
          : "def cobrar_pago(monto, moneda):\n    if monto <= 0:\n        return None\n    pago = Pago(monto, moneda)\n    return pago.cobrar()\n";
        mockEditarDraft(paths.main, renamed);
      }, { soloEstado: true });
      programar(6900, () => {
        decir(t.demo_step_ana_editing_mine, "info");
        emitToast(t.demo_step_ana_editing_mine, "ok");
      });

      // Ana manda la propuesta (Ctrl+S simulado). Estado: el draft sigue
      // ahí, pero ahora marcado como "enviada · esperando aprobación".
      // En este iframe NO aparece PropCard (las PropCard son para
      // propuestas que llegan, no que envías). El badge del paso lo dice.
      programar(10500, () => {
        decir(t.demo_step_ana_sending, "info");
        emitToast(t.demo_step_ana_sending, "ok");
      });

      // Click "fantasma": pulse visual que coincide con el momento en que
      // Tomás clickea Aprobar en su iframe. Refuerza la sensación de
      // sincronización entre las dos vistas. Sin cursor target — el click
      // representa el botón que Ana NO toca, pero que se activa.
      programar(15500, () => clickear());
      programar(15800, () => {
        // El dueño aprobó: el draft se aplica al archivo, se limpia.
        mockAplicarPropuestaDeAna(paths.main, lang);
        decir(t.demo_step_tu_approved, "ok");
        emitToast(t.demo_step_tu_approved, "ok");
        // El nombre referencia el path arriba pero no es necesario; mantenemos
        // la simetría con el guión TU.
        void propuestaContenido;
      }, { soloEstado: true });
      programar(16800, () => cursorEnReposo());

      // El impacto también se ve en este iframe: Ana causó el rename, los
      // call sites afectados aparecen en el sidebar. Como ella SÍ es dueña
      // de api/cobros.py, el chip de impacto le habla a ella.
      programar(19500, () => mockImpactoCascada(lang), { soloEstado: true });
      programar(20100, () => {
        decir(t.demo_step_impact_mine, "warn");
        emitToast(t.demo_step_impact_mine, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 2800, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 2600, "warn");
      });

      // Cursor investiga: Ana abre su archivo afectado (api/cobros.py).
      const selFileApi = `[data-tour-id="file-${paths.api}"]`;
      programar(22500, () => {
        resaltarTarget(selFileApi, 2400, "fuerte");
        moverCursorA(selFileApi);
      });
      programar(24500, () => clickear());
      programar(24800, () => {
        mockOpenFile(paths.api);
        decir(t.demo_step_focus_impact_mine, "info");
      }, { soloEstado: true });
      programar(25800, () => cursorEnReposo());

      // Mientras Ana mira su api, Tomás se mueve a tests/ (en su iframe lo
      // ven explícito; acá lo reflejamos como peer movement).
      programar(28000, () => {
        mockTuEntra(paths.tests, 3);
        decir(t.demo_step_tu_in_tests, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2000, "suave");
      }, { soloEstado: true });
      programar(29800, () => mockTuEntra(paths.tests, 4), { soloEstado: true });

      // Premium entra y manda auto-fix de api/cobros.py — Ana ES dueña,
      // por eso la propuesta SÍ le llega como PropCard. Ella va a aprobar.
      programar(31800, () => {
        premiumEntra(paths.api, 3);
        propFix = mockAutoFixPremium(lang);
        decir(t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2600, "suave");
      }, { soloEstado: true });

      // Cursor al [aprobar] del auto-fix, halo, click.
      programar(34800, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2600, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(36800, () => clickear());
      programar(37100, () => {
        if (propFix) mockAprobar(propFix);
        mockLimpiarImpactos();
        premiumSale();
        mockTuSale();
        decir(t.demo_step_resolved, "ok");
        emitToast(t.demo_step_resolved, "ok");
      }, { soloEstado: true });
      programar(38100, () => cursorEnReposo());

      // Pausa final.
      programar(41000, () => decir(t.demo_step_calm, "ok"));
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
