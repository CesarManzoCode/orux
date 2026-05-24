// Guión del tutorial — la *narrativa*. Cada Step define qué dice el bot,
// dónde apunta el spotlight, si el usuario tiene que hacer clic para
// avanzar (`click`) o avanza solo después de un tiempo (`say`), y qué
// side-effect del `mock` se dispara antes/después.
//
// Cadencia objetivo: <60s totales (~9 "say" + 4 "click" del usuario).
//
// Regla de click: cuando un step `click` define `after`, el click NO se
// propaga al target real (el `after` hace el efecto en el mock). Cuando
// NO define `after`, el click sí se propaga al target (delega en la app
// real — usado para el paso "abrir panel git", donde dejamos que el
// `setVista` real del Rail haga el cambio).
import type { Lang, Traducciones } from "../i18n";
import {
  mockSeedRepo, mockOpenFile, mockAnaEntra,
  mockPropuestaDeAna, mockAprobar, mockImpactoCascada,
  mockAutoFixPremium, mockLimpiarImpactos, pathsPorLang,
} from "./mock";

export type StepMode = "say" | "click";
export type StepSide = "centro" | "izq" | "der" | "abajo" | "arriba";

export interface Step {
  id: string;
  mode: StepMode;
  text: (t: Traducciones) => string;
  target?: string;
  wait?: number;
  side?: StepSide;
  before?: () => void;
  after?: () => void;
}

// API que el orquestador inyecta al guión. Acá viven los cambios de UI
// que NO viven en el store (el sidebar `vista` es estado local de App).
export interface TutorialAPI {
  setVista: (v: "archivos" | "git") => void;
  setInspectorOpen: (open: boolean) => void;
}

// IDs de propuestas vivas — los necesitamos para aprobarlas en el paso
// correspondiente. Closure simple.
let propAna = "";
let propAutoFix = "";

export function construirGuion(api: TutorialAPI, lang: Lang = "es"): Step[] {
  const paths = pathsPorLang(lang);
  return [
    {
      id: "hello",
      mode: "say",
      text: (t) => t.tut_hello,
      wait: 3600,
    },
    {
      id: "intro",
      mode: "say",
      text: (t) => t.tut_intro,
      wait: 7000,
    },
    {
      id: "skip-hint",
      mode: "say",
      text: (t) => t.tut_skip_hint,
      wait: 6500,
    },
    // ── Paso 4: abrir el panel git desde el rail. SIN `after`: el click se
    // propaga al botón real y `setVista("git")` corre desde el Rail. ──
    {
      id: "open-git",
      mode: "click",
      text: (t) => t.tut_open_git,
      target: "rail-git",
      side: "der",
    },
    // ── Paso 5: clonar (mock siembra el repo + vuelve a vista archivos
    // para que el FileTree quede visible para los pasos siguientes). ──
    {
      id: "clone",
      mode: "click",
      text: (t) => t.tut_clone,
      target: "git-clone",
      side: "der",
      after: () => {
        mockSeedRepo(lang);
        api.setVista("archivos");
      },
    },
    {
      id: "code-here",
      mode: "say",
      text: (t) => t.tut_code_here,
      target: "files-tree",
      side: "der",
      wait: 4500,
    },
    // ── Paso 7: abrir el archivo principal. CON `after`: no propagamos
    // el click al <li> real (que dispararía `seleccionar` al WebSocket). ──
    {
      id: "open-file",
      mode: "click",
      text: (t) => t.tut_open_file,
      target: "file-" + paths.main,
      side: "der",
      after: () => { mockOpenFile(paths.main); },
    },
    // ── Paso 8: Ana entra al mismo archivo. Pulso vivo en el inspector. ──
    {
      id: "ana-joins",
      mode: "say",
      text: (t) => t.tut_ana_joins,
      target: "inspector-presencia",
      side: "izq",
      wait: 6000,
      before: () => { mockAnaEntra(paths.main, 4); },
    },
    // ── Paso 9: propuesta de Ana llega al inspector. ──
    {
      id: "ana-proposes",
      mode: "say",
      text: (t) => t.tut_ana_proposes,
      target: "inspector-propuestas",
      side: "izq",
      wait: 6000,
      before: () => { propAna = mockPropuestaDeAna(lang); },
    },
    // ── Paso 10: usuario aprueba. ──
    {
      id: "accept-prop",
      mode: "click",
      text: (t) => t.tut_accept_prop,
      target: "prop-accept",
      side: "izq",
      after: () => { if (propAna) mockAprobar(propAna); },
    },
    // ── Paso 11: impacto detectado en cascada. Cambiamos el archivo
    // abierto a uno AFECTADO (api/cobros.py) para que la sección
    // "impacto" renderice el listado con datos (su filtro es por
    // `affected_path === currentPath`). ──
    {
      id: "impact",
      mode: "say",
      text: (t) => t.tut_impact,
      target: "inspector-impacto",
      side: "izq",
      wait: 7500,
      before: () => {
        mockImpactoCascada(lang);
        mockOpenFile(paths.api);
      },
    },
    // ── Paso 12: auto-fix premium aparece como propuesta. ──
    {
      id: "autofix",
      mode: "say",
      text: (t) => t.tut_autofix,
      target: "inspector-propuestas",
      side: "izq",
      wait: 6500,
      before: () => { propAutoFix = mockAutoFixPremium(lang); },
    },
    // ── Paso 13: aprobar el auto-fix → limpia impactos. ──
    {
      id: "accept-fix",
      mode: "click",
      text: (t) => t.tut_accept_fix,
      target: "prop-accept",
      side: "izq",
      after: () => {
        if (propAutoFix) mockAprobar(propAutoFix);
        mockLimpiarImpactos();
      },
    },
    // ── Cierre: el bot pide confirmación con un CTA (no auto-avanza). ──
    {
      id: "close",
      mode: "say",
      text: (t) => t.tut_close,
      wait: 8000,
    },
  ];
}
