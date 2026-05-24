// Mock layer del tutorial y del demo cinematográfico: muta directamente el
// store del CLIENTE para inyectar un mini-proyecto fake (archivos, peers,
// ownership, propuestas, impacto). Nada de esto viaja al servidor.
//
// Reglas:
// - El tutorial sólo arranca si el workspace está vacío (`files = {}`).
//   El demo (?demo=1) arranca siempre — el bypass del main.tsx ya garantiza
//   que no hay sesión real.
// - El cleanup (`mockClearAll`) deja todos los campos relevantes vacíos
//   otra vez, así no queda residuo cuando el usuario empieza a usar el
//   producto de verdad.
// - El "yo" real del usuario sigue siendo dueño de los archivos del
//   ejemplo (eso es lo que hace que las propuestas de Ana se le pidan
//   APROBAR a él — sin esa flag, no aparecería el botón "aceptar"
//   que el guión necesita resaltar).
//
// i18n del contenido — capa 36b: los archivos del workspace fake se sirven
// en español o inglés según el idioma activo. Cambia: nombres de archivos
// (procesar_pago.py ↔ process_payment.py, api/cobros.py ↔ api/charges.py),
// identificadores (monto/amount, moneda/currency, Pago/Payment, cobrar/
// charge) y la propuesta de Ana (cobrar_pago / charge_payment). Sin esto,
// un visitante anglosajón ve código español y se siente extranjero antes
// de leer una sola palabra del producto.
//
// Los nombres `Ana` / `Orux Premium` son convenciones del guión: si el
// script cambia, actualizar acá también.
import {
  __setForTutorial,
  getState,
  type Proposal,
} from "../store";
import type { Lang } from "../i18n";

export const TUT = {
  ana: {
    client_id: "tutorial:ana",
    name: "Ana",
    color: "#62a8f0",
  },
  premium: {
    client_id: "tutorial:premium-bot",
    name: "Orux Premium",
  },
} as const;

// Paths del mini-proyecto fake. Distintos por idioma para que un dev EN no
// vea identificadores españoles en el sidebar (y viceversa). Los selectores
// del DemoLoop construyen `[data-tour-id="file-${path}"]` con estos valores.
export interface PathsDemo {
  main: string;
  models: string;
  api: string;
  tests: string;
}
const PATHS_ES: PathsDemo = {
  main:   "procesar_pago.py",
  models: "models.py",
  api:    "api/cobros.py",
  tests:  "tests/test_pago.py",
};
const PATHS_EN: PathsDemo = {
  main:   "process_payment.py",
  models: "models.py",
  api:    "api/charges.py",
  tests:  "tests/test_payment.py",
};
export function pathsPorLang(lang: Lang): PathsDemo {
  return lang === "en" ? PATHS_EN : PATHS_ES;
}

// Contenido inicial del "repo" fake (ES). Pequeño, en Python: el análisis
// de Orux empezó en Python, y un snippet de payments se lee de un vistazo.
const FILES_ES: Record<string, string> = {
  [PATHS_ES.main]:
    "def procesar_pago(monto, moneda):\n" +
    "    if monto <= 0:\n" +
    "        return None\n" +
    "    pago = Pago(monto, moneda)\n" +
    "    return pago.cobrar()\n",
  [PATHS_ES.models]:
    "class Pago:\n" +
    "    def __init__(self, monto, moneda):\n" +
    "        self.monto = monto\n" +
    "        self.moneda = moneda\n" +
    "\n" +
    "    def cobrar(self):\n" +
    "        return {\"ok\": True}\n",
  [PATHS_ES.api]:
    "from procesar_pago import procesar_pago\n" +
    "\n" +
    "def cobrar(req):\n" +
    "    return procesar_pago(req.monto, req.moneda)\n",
  [PATHS_ES.tests]:
    "from procesar_pago import procesar_pago\n" +
    "\n" +
    "def test_zero():\n" +
    "    assert procesar_pago(0, \"USD\") is None\n",
};
// Mismo proyecto en inglés. Identificadores traducidos (amount, currency,
// Payment, charge). La estructura es 1:1 con la versión ES para que el
// flujo del demo sea idéntico.
const FILES_EN: Record<string, string> = {
  [PATHS_EN.main]:
    "def process_payment(amount, currency):\n" +
    "    if amount <= 0:\n" +
    "        return None\n" +
    "    payment = Payment(amount, currency)\n" +
    "    return payment.charge()\n",
  [PATHS_EN.models]:
    "class Payment:\n" +
    "    def __init__(self, amount, currency):\n" +
    "        self.amount = amount\n" +
    "        self.currency = currency\n" +
    "\n" +
    "    def charge(self):\n" +
    "        return {\"ok\": True}\n",
  [PATHS_EN.api]:
    "from process_payment import process_payment\n" +
    "\n" +
    "def charge(req):\n" +
    "    return process_payment(req.amount, req.currency)\n",
  [PATHS_EN.tests]:
    "from process_payment import process_payment\n" +
    "\n" +
    "def test_zero():\n" +
    "    assert process_payment(0, \"USD\") is None\n",
};

// El "cambio de Ana" del paso 9 del guión / fase de propuesta del demo:
// renombra `procesar_pago` a `cobrar_pago` (cambia firma) — eso es lo que
// dispara el impacto en los call sites.
const PROPUESTA_ANA_ES = {
  path: PATHS_ES.main,
  content:
    "def cobrar_pago(monto, moneda):\n" +
    "    if monto <= 0:\n" +
    "        return None\n" +
    "    pago = Pago(monto, moneda)\n" +
    "    return pago.cobrar()\n",
};
const PROPUESTA_ANA_EN = {
  path: PATHS_EN.main,
  content:
    "def charge_payment(amount, currency):\n" +
    "    if amount <= 0:\n" +
    "        return None\n" +
    "    payment = Payment(amount, currency)\n" +
    "    return payment.charge()\n",
};

// La auto-propuesta premium del paso 12 / fase auto-fix del demo: renombra
// el call site en cascada.
const AUTOFIX_PREMIUM_ES = {
  path: PATHS_ES.api,
  content:
    "from procesar_pago import cobrar_pago\n" +
    "\n" +
    "def cobrar(req):\n" +
    "    return cobrar_pago(req.monto, req.moneda)\n",
};
const AUTOFIX_PREMIUM_EN = {
  path: PATHS_EN.api,
  content:
    "from process_payment import charge_payment\n" +
    "\n" +
    "def charge(req):\n" +
    "    return charge_payment(req.amount, req.currency)\n",
};

export function mockReset(): void {
  __setForTutorial({
    files: {},
    currentPath: null,
    owners: {},
    peers: {},
    proposals: {},
    impacts: {},
    dirty: {},
    drafts: {},
    actividad: [],
  });
}

export function mockSeedRepo(lang: Lang = "es"): void {
  const yoId = getState().yo?.client_id ?? "tutorial:yo";
  const paths = pathsPorLang(lang);
  const files = lang === "en" ? FILES_EN : FILES_ES;
  __setForTutorial({
    files: { ...files },
    owners: {
      [paths.main]:   yoId,
      [paths.models]: yoId,
      [paths.api]:    TUT.ana.client_id,
      [paths.tests]:  yoId,
    },
    currentPath: null,
  });
}

export function mockOpenFile(path: string): void {
  __setForTutorial({ currentPath: path });
}

export function mockAnaEntra(path: string, line = 4): void {
  // Ana aparece en la lista de peers, posada sobre el archivo abierto: eso
  // es lo que ilumina los avatares "live" en el FileTree y en el Inspector.
  const peers = { ...getState().peers };
  peers[TUT.ana.client_id] = { ...TUT.ana, path, line };
  __setForTutorial({ peers });
}

export function mockPropuestaDeAna(lang: Lang = "es"): string {
  const id = "tutorial:prop:ana:" + Date.now();
  const proposals = { ...getState().proposals };
  const prop = lang === "en" ? PROPUESTA_ANA_EN : PROPUESTA_ANA_ES;
  proposals[id] = {
    id,
    path: prop.path,
    author_id: TUT.ana.client_id,
    author_name: TUT.ana.name,
    content: prop.content,
    seen_at: Date.now(),
  };
  __setForTutorial({ proposals });
  return id;
}

// Aplica una propuesta: copia su `content` al archivo y limpia esa
// propuesta del store (efecto idéntico al "approve" real del producto).
export function mockAprobar(proposalId: string): void {
  const st = getState();
  const p = st.proposals[proposalId];
  if (!p) return;
  const proposals: Record<string, Proposal> = {};
  for (const [pid, q] of Object.entries(st.proposals)) {
    if (pid !== proposalId) proposals[pid] = q;
  }
  __setForTutorial({
    files: { ...st.files, [p.path]: p.content },
    proposals,
  });
}

export function mockImpactoCascada(lang: Lang = "es"): void {
  // El rename de Ana impacta dos archivos consumidores. Marcamos uno como
  // impacto directo (`cadena: []`) y otro como transitivo (`cadena: [...]`)
  // para que la UI use el verde/ámbar correcto y, además, el indicador de
  // "transitivo" (premium) se vea con datos coherentes.
  const paths = pathsPorLang(lang);
  const sym = lang === "en" ? "process_payment" : "procesar_pago";
  const impacts = { ...getState().impacts };
  impacts[paths.main + "::" + paths.api] = {
    source_path: paths.main,
    author_name: TUT.ana.name,
    affected_path: paths.api,
    symbols: [sym],
    motivos: ["rename"],
    cadena: [],
    severidades: ["alta"],
  };
  impacts[paths.main + "::" + paths.tests] = {
    source_path: paths.main,
    author_name: TUT.ana.name,
    affected_path: paths.tests,
    symbols: [sym],
    motivos: ["rename"],
    cadena: [paths.main, paths.api],
    severidades: ["media"],
  };
  __setForTutorial({ impacts });
}

export function mockAutoFixPremium(lang: Lang = "es"): string {
  const id = "tutorial:autofix:" + Date.now();
  const proposals = { ...getState().proposals };
  const auto = lang === "en" ? AUTOFIX_PREMIUM_EN : AUTOFIX_PREMIUM_ES;
  proposals[id] = {
    id,
    path: auto.path,
    author_id: TUT.premium.client_id,
    author_name: TUT.premium.name,
    content: auto.content,
    seen_at: Date.now(),
  };
  // El cliente es dueño de api/cobros.py en este momento NO (es de Ana en
  // el seed). Para que el "aprobar" sea posible y se sienta inmediato, el
  // tutorial cede ese path al cliente justo antes de la propuesta — un
  // detalle simulado pero pedagógicamente claro (el premium "te resuelve el
  // problema" en tu rincón). En producción esto vendría del flujo real.
  const yoId = getState().yo?.client_id ?? "tutorial:yo";
  const owners = { ...getState().owners, [auto.path]: yoId };
  __setForTutorial({ proposals, owners });
  return id;
}

export function mockLimpiarImpactos(): void {
  __setForTutorial({ impacts: {} });
}

export function mockClearAll(): void {
  mockReset();
}
