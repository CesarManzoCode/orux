// Demo cinemático del IDE para la landing: corre el flujo del tutorial en
// bucle infinito mutando el store real con las funciones de mock. Encima
// renderiza un cursor "tú/you" simulado, halos sobre los targets antes de
// cada click, y un badge "Demo · fase actual" abajo del centro. Todo para
// que el visitante entienda qué pasa y qué cursor representa quién:
//
//   - Cursores de peers REALES (Ana, Premium): aparecen DENTRO del editor
//     como rayas verticales con etiqueta + en el sidebar como badge circular
//     con la inicial. Igual que en el producto real.
//
//   - Cursor del visitante (este componente): flecha de mouse con etiqueta
//     "tú" / "you" debajo. Aparece SOLO antes de cada interacción decisoria
//     (aprobar propuestas, cambiar de archivo) y desaparece al terminar.
//     Cada aparición = una decisión humana en el flujo.
//
// Pensado para servirse en /app/?demo=1&lang=es|en y embebirse como iframe
// en el hero de la landing.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { emitToast, __setForTutorial, getState } from "../store";
import {
  mockClearAll, mockSeedRepo, mockOpenFile, mockAnaEntra,
  mockPropuestaDeAna, mockAprobar, mockImpactoCascada,
  mockAutoFixPremium, mockLimpiarImpactos, TUT, pathsPorLang,
} from "./mock";

const TOTAL_MS = 50000;

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
  }, ms);
}

interface CursorPos { x: number; y: number; visible: boolean; }

export function DemoLoop() {
  const { t, lang } = useI18n();
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

    function programar(ms: number, fn: () => void): void {
      const id = window.setTimeout(() => {
        if (!cancelado) fn();
      }, ms);
      timers.push(id);
    }

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
      window.setTimeout(() => setClicking(false), 700);
    }

    function ciclo(): void {
      if (cancelado) return;
      propAna = "";
      propFix = "";

      // ── Setup (0–1s): el IDE se monta con seed; cursor entra a los 500ms.
      programar(0, () => {
        mockClearAll();
        mockSeedRepo(lang);
        mockOpenFile(paths.main);
        decir(t.demo_step_setup, "info");
      });
      programar(500, () => cursorEnReposo());

      // ── Ana entra y "edita" (cursor de peer moviéndose por las líneas).
      //    Resaltamos la sección Presencia del Inspector para que el visitante
      //    sepa DÓNDE mirar el cambio.
      programar(2500, () => {
        mockAnaEntra(paths.main, 1);
        decir(t.demo_step_ana_enters, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2200, "suave");
      });
      programar(3600, () => mockAnaEntra(paths.main, 2));
      programar(4700, () => mockAnaEntra(paths.main, 4));
      programar(5800, () => mockAnaEntra(paths.main, 5));
      programar(6900, () => mockAnaEntra(paths.main, 4));
      programar(7800, () => {
        decir(t.demo_step_ana_editing, "info");
        emitToast(t.demo_step_ana_editing, "ok");
      });

      // ── Propuesta de Ana: resaltamos la sección Propuestas mientras
      //    aparece la PropCard. La PropCard misma trae su propia animación
      //    de entrada (demo-prop-in), el halo apunta dónde mirar.
      programar(10500, () => {
        propAna = mockPropuestaDeAna(lang);
        decir(t.demo_step_ana_proposes, "info");
        emitToast(t.demo_step_ana_proposes, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2600, "suave");
      });

      // ── Cursor va al [aprobar], halo FUERTE en el botón, click.
      programar(13500, () => {
        resaltarTarget('[data-tour-id="prop-accept"]', 2600, "fuerte");
        moverCursorA('[data-tour-id="prop-accept"]');
      });
      programar(15500, () => clickear());
      programar(15800, () => {
        if (propAna) mockAprobar(propAna);
        decir(t.demo_step_approved, "ok");
        emitToast(t.demo_step_approved, "ok");
      });
      programar(16800, () => cursorEnReposo());

      // ── Impacto en cascada: resaltado WARN (ámbar) sobre la sección
      //    Impacto Y sobre el sidebar (donde aparecen los chips rojos al
      //    lado de los archivos afectados).
      programar(19500, () => mockImpactoCascada(lang));
      programar(20100, () => {
        decir(t.demo_step_impact, "warn");
        emitToast(t.demo_step_impact, "warn");
        resaltarTarget('[data-tour-id="inspector-impacto"]', 2800, "warn");
        resaltarTarget('[data-tour-id="files-tree"]', 2600, "warn");
      });

      // ── Cursor investiga: va al archivo afectado en el sidebar.
      const selFileApi = `[data-tour-id="file-${paths.api}"]`;
      programar(22500, () => {
        resaltarTarget(selFileApi, 2400, "fuerte");
        moverCursorA(selFileApi);
      });
      programar(24500, () => clickear());
      programar(24800, () => {
        mockOpenFile(paths.api);
        decir(t.demo_step_focus_impact, "info");
      });
      programar(25800, () => cursorEnReposo());

      // ── Premium entra y manda auto-fix.
      programar(28000, () => {
        premiumEntra(paths.api, 3);
        decir(t.demo_step_premium_enters, "info");
        resaltarTarget('[data-tour-id="inspector-presencia"]', 2000, "suave");
      });
      programar(29800, () => mockAnaEntra(paths.api, 1));
      programar(31800, () => {
        propFix = mockAutoFixPremium(lang);
        decir(t.demo_step_autofix, "info");
        emitToast(t.demo_step_autofix, "ok");
        resaltarTarget('[data-tour-id="inspector-propuestas"]', 2600, "suave");
      });

      // ── Cursor al [aprobar] del auto-fix, halo, click.
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
      });
      programar(38100, () => cursorEnReposo());

      // ── Pausa final en "todo en orden" antes de reiniciar.
      programar(41000, () => decir(t.demo_step_calm, "ok"));

      programar(TOTAL_MS, () => ciclo());
    }

    ciclo();

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
    // Re-disparar al cambiar lang: el contenido y los paths son distintos,
    // así que el bucle anterior se desmonta limpio y arranca con el nuevo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  return (
    <>
      <DemoCursor pos={cursor} clicking={clicking} label={t.demo_cursor_label} />
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
