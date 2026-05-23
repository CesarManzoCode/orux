// Mock layer del tutorial: muta directamente el store del CLIENTE para
// inyectar un mini-proyecto fake (archivos, peers, ownership, propuestas,
// impacto). Nada de esto viaja al servidor — el tutorial es 100% local.
//
// Reglas:
// - El tutorial sólo arranca si el workspace está vacío (`files = {}`).
// - El cleanup (`mockClearAll`) deja todos los campos relevantes vacíos
//   otra vez, así no queda residuo cuando el usuario empieza a usar el
//   producto de verdad.
// - El "yo" real del usuario sigue siendo dueño de los archivos del
//   ejemplo (eso es lo que hace que las propuestas de Ana se le pidan
//   APROBAR a él — sin esa flag, no aparecería el botón "aceptar"
//   que el guión necesita resaltar).
//
// Los nombres `Ana` / `Orux Premium` son convenciones del guión: si el
// script cambia, actualizar acá también.
import {
  __setForTutorial,
  getState,
  type Proposal,
} from "../store";

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

// Contenido inicial del "repo" fake. Pequeño, en Python (consistente con
// la mini-demo del empty-state y con que el análisis de Orux empezó en
// Python). Sin imports pesados: tiene que leerse de un vistazo.
const FILES_BASE: Record<string, string> = {
  "procesar_pago.py":
    "def procesar_pago(monto, moneda):\n" +
    "    if monto <= 0:\n" +
    "        return None\n" +
    "    pago = Pago(monto, moneda)\n" +
    "    return pago.cobrar()\n",
  "models.py":
    "class Pago:\n" +
    "    def __init__(self, monto, moneda):\n" +
    "        self.monto = monto\n" +
    "        self.moneda = moneda\n" +
    "\n" +
    "    def cobrar(self):\n" +
    "        return {\"ok\": True}\n",
  "api/cobros.py":
    "from procesar_pago import procesar_pago\n" +
    "\n" +
    "def cobrar(req):\n" +
    "    return procesar_pago(req.monto, req.moneda)\n",
  "tests/test_pago.py":
    "from procesar_pago import procesar_pago\n" +
    "\n" +
    "def test_zero():\n" +
    "    assert procesar_pago(0, \"USD\") is None\n",
};

// El "cambio de Ana" del paso 9 del guión: renombra `procesar_pago` a
// `cobrar_pago` (pasa firma) — eso es lo que después dispara el impacto en
// `api/cobros.py` y `tests/test_pago.py`.
export const PROPUESTA_ANA = {
  path: "procesar_pago.py",
  content:
    "def cobrar_pago(monto, moneda):\n" +
    "    if monto <= 0:\n" +
    "        return None\n" +
    "    pago = Pago(monto, moneda)\n" +
    "    return pago.cobrar()\n",
};

// La auto-propuesta premium del paso 12: renombra en cascada los call sites.
export const AUTOFIX_PREMIUM = {
  path: "api/cobros.py",
  content:
    "from procesar_pago import cobrar_pago\n" +
    "\n" +
    "def cobrar(req):\n" +
    "    return cobrar_pago(req.monto, req.moneda)\n",
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

export function mockSeedRepo(): void {
  const yoId = getState().yo?.client_id ?? "tutorial:yo";
  __setForTutorial({
    files: { ...FILES_BASE },
    owners: {
      "procesar_pago.py": yoId,
      "models.py": yoId,
      "api/cobros.py": TUT.ana.client_id,
      "tests/test_pago.py": yoId,
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

export function mockPropuestaDeAna(): string {
  const id = "tutorial:prop:ana:" + Date.now();
  const proposals = { ...getState().proposals };
  proposals[id] = {
    id,
    path: PROPUESTA_ANA.path,
    author_id: TUT.ana.client_id,
    author_name: TUT.ana.name,
    content: PROPUESTA_ANA.content,
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

export function mockImpactoCascada(): void {
  // El rename de Ana impacta dos archivos consumidores. Marcamos uno como
  // impacto directo (`cadena: []`) y otro como transitivo (`cadena: [...]`)
  // para que la UI use el verde/ámbar correcto y, además, el indicador de
  // "transitivo" (premium) se vea con datos coherentes.
  const impacts = { ...getState().impacts };
  impacts["procesar_pago.py::api/cobros.py"] = {
    source_path: "procesar_pago.py",
    author_name: TUT.ana.name,
    affected_path: "api/cobros.py",
    symbols: ["procesar_pago"],
    motivos: ["rename"],
    cadena: [],
    severidades: ["alta"],
  };
  impacts["procesar_pago.py::tests/test_pago.py"] = {
    source_path: "procesar_pago.py",
    author_name: TUT.ana.name,
    affected_path: "tests/test_pago.py",
    symbols: ["procesar_pago"],
    motivos: ["rename"],
    cadena: ["procesar_pago.py", "api/cobros.py"],
    severidades: ["media"],
  };
  __setForTutorial({ impacts });
}

export function mockAutoFixPremium(): string {
  const id = "tutorial:autofix:" + Date.now();
  const proposals = { ...getState().proposals };
  proposals[id] = {
    id,
    path: AUTOFIX_PREMIUM.path,
    author_id: TUT.premium.client_id,
    author_name: TUT.premium.name,
    content: AUTOFIX_PREMIUM.content,
    seen_at: Date.now(),
  };
  // El cliente es dueño de api/cobros.py en este momento NO (es de Ana en
  // el seed). Para que el "aprobar" sea posible y se sienta inmediato, el
  // tutorial cede ese path al cliente justo antes de la propuesta — un
  // detalle simulado pero pedagógicamente claro (el premium "te resuelve el
  // problema" en tu rincón). En producción esto vendría del flujo real.
  const yoId = getState().yo?.client_id ?? "tutorial:yo";
  const owners = { ...getState().owners, [AUTOFIX_PREMIUM.path]: yoId };
  __setForTutorial({ proposals, owners });
  return id;
}

export function mockLimpiarImpactos(): void {
  __setForTutorial({ impacts: {} });
}

export function mockClearAll(): void {
  mockReset();
}
