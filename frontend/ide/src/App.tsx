import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "./useStore";
import {
  getState, guardar, contarDrafts, resolver, seleccionar,
  subscribeToasts, emitToast, esDeOtro, type ToastTone,
} from "./store";
import { Login } from "./components/Login";
import { Lobby } from "./components/Lobby";
import { TopBar } from "./components/TopBar";
import { Rail } from "./components/Rail";
import { Sidebar } from "./components/Sidebar";
import { Tabs } from "./components/Tabs";
import { ContextBar } from "./components/ContextBar";
import { Editor } from "./components/Editor";
import { EmptyWorkspace } from "./components/EmptyWorkspace";
import { StatusBar } from "./components/StatusBar";
import { AdminModal } from "./components/AdminModal";
import { Inspector } from "./components/Inspector";
import { Splitter } from "./components/Splitter";
import { KbdHelp } from "./components/KbdHelp";
import { Tutorial } from "./tutorial/Tutorial";
import { DemoLoop } from "./tutorial/DemoLoop";
import { useI18n } from "./i18n";

// Capa 27 — Anchos redimensionables del Sidebar y el Inspector.
// Límites: dejamos respirar al editor (mínimos generosos) sin que ningún
// panel acapare la ventana (máximos contenidos).
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 520;
const SIDEBAR_DEF = 248;
const INSP_MIN = 240;
const INSP_MAX = 560;
const INSP_DEF = 312;

function leerAncho(key: string, def: number, min: number, max: number): number {
  // localStorage puede tener basura (otro origen, mano del usuario): clamp.
  const raw = localStorage.getItem(key);
  const n = raw ? parseInt(raw, 10) : NaN;
  if (!Number.isFinite(n)) return def;
  return Math.min(max, Math.max(min, n));
}

export function App() {
  const s = useStore();
  const { t } = useI18n();
  // AUDITORIA-SEGURIDAD 2026-05-25 A-FE-05 + B-FE-05: guard anti-embedding
  // del IDE real. Si la página está en un iframe y NO es modo demo, no
  // tiene sentido mostrarla — riesgo de clickjacking (un atacante embebe
  // /app/ en una página suya y superpone elementos para tunear lo que el
  // usuario cree clicar). El modo demo SÍ vive en iframe (lo embebe la
  // landing) y se identifica por `s.demoMode`. Mostramos un mensaje claro
  // y un link a abrir el IDE en pestaña nueva.
  const embeddedSinDemo = (() => {
    try {
      return window.parent !== window && !s.demoMode;
    } catch {
      // SecurityError accediendo a window.parent => estamos en iframe
      // cross-origin (lo cual es bueno) — devolvemos true igual para
      // refusar el render.
      return true;
    }
  })();
  if (embeddedSinDemo) {
    return (
      <div style={{
        padding: "2rem",
        fontFamily: "system-ui, sans-serif",
        textAlign: "center",
        color: "#e6e6e6",
        background: "#0d0d10",
        minHeight: "100vh",
      }}>
        <h1>Orux no se puede embeber así</h1>
        <p>Por seguridad, el IDE no funciona dentro de un iframe.</p>
        <p>
          <a href={location.href} target="_top" style={{ color: "#43b98a" }}>
            Abrir en una pestaña nueva
          </a>
        </p>
      </div>
    );
  }
  const [vista, setVista] = useState<"archivos" | "git">("archivos");
  const [adminOpen, setAdminOpen] = useState(false);
  // Capa 30 — Cheatsheet de atajos y toast inline. El toast es texto + ttl;
  // suficiente para confirmar "aprobada"/"rechazada" tras un atajo (cuando
  // el ojo no estaba en el botón). Mismo patrón micro que el del Hub.
  const [kbdOpen, setKbdOpen] = useState(false);
  // El toast es la única señal "no modal" que el producto se permite. Lo
  // promovimos a bus global (store::subscribeToasts) para que acciones de
  // cualquier capa puedan reusarlo: guardar (Ctrl+S), aprobar/rechazar
  // (Alt+A/R), copiar invitación, etc. El último toast gana; el timer se
  // resetea por ID para que toasts en cadena no se canibalicen.
  const [toast, setToast] = useState<{ id: number; text: string; tone: ToastTone } | null>(null);
  // Capa 26: el inspector se puede colapsar (pantallas medianas, o quien
  // quiere todo el ancho para el código). La preferencia persiste — una
  // herramienta de uso diario respeta cómo la dejaste.
  const [inspOpen, setInspOpen] = useState(
    () => localStorage.getItem("orux_insp") !== "0",
  );
  const toggleInsp = () => {
    const next = !inspOpen;
    localStorage.setItem("orux_insp", next ? "1" : "0");
    setInspOpen(next);
  };

  // Capa 27 — anchos redimensionables (Sidebar y Inspector). El ancho
  // ACTUAL vive en estado y se persiste a localStorage en cada cambio:
  // es un número (cero costo), y así el ancho sigue ahí si la pestaña
  // se cierra a mitad de arrastre.
  const [wSidebar, setWSidebar] = useState(() =>
    leerAncho("orux_w_side", SIDEBAR_DEF, SIDEBAR_MIN, SIDEBAR_MAX),
  );
  const [wInsp, setWInsp] = useState(() =>
    leerAncho("orux_w_insp", INSP_DEF, INSP_MIN, INSP_MAX),
  );
  useEffect(() => { localStorage.setItem("orux_w_side", String(wSidebar)); }, [wSidebar]);
  useEffect(() => { localStorage.setItem("orux_w_insp", String(wInsp)); }, [wInsp]);

  const onResizeSide = (dx: number) => {
    setWSidebar((w) =>
      Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, w + dx)),
    );
  };
  const onResizeInsp = (dx: number) => {
    setWInsp((w) =>
      Math.min(INSP_MAX, Math.max(INSP_MIN, w + dx)),
    );
  };

  // Si dejás de ser admin (re-init tras un clone), el modal se cierra solo.
  useEffect(() => { if (!s.esAdmin && adminOpen) setAdminOpen(false); }, [s.esAdmin, adminOpen]);

  // Tutorial guiado (OruxBot). Disparo único: la primera vez que un admin
  // entra a un workspace virgen (files vacío), y siempre que NO lo haya
  // saltado/terminado antes (flag en localStorage). Los miembros invitados
  // no lo ven en v1 — vienen con contexto de quien los invitó. El estado
  // se calcula al cambiar a fase "team": al disparar la primera vez,
  // `tutorialOn=true` se queda hasta que el componente avise `onDone`.
  const [tutorialOn, setTutorialOn] = useState(false);
  useEffect(() => {
    if (s.demoMode) return;  // demo cinematográfico — no disparar tutorial.
    if (s.fase !== "team") return;
    if (!s.esAdmin) return;
    if (Object.keys(s.files).length > 0) return;
    if (localStorage.getItem("orux_tutorial_done") === "1") return;
    setTutorialOn(true);
    // Sólo gateamos al entrar a "team" — `s.files` cambia mucho y no
    // queremos re-evaluar el trigger en cada update del store.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.fase, s.esAdmin]);
  // Estabilizar la API que pasa al Tutorial: si la pasamos como objeto
  // literal `{...}` en cada render, su referencia cambia, el useMemo del
  // guión re-construye los pasos, el useEffect de `before` ve un step
  // "nuevo", lo re-ejecuta — y como `before` muta el store, se cae en
  // loop infinito (React: Maximum update depth exceeded). Los setters
  // de useState ya son estables, así que con useMemo basta.
  const tutorialApi = useMemo(
    () => ({ setVista, setInspectorOpen: setInspOpen }),
    [],
  );

  // Capa 19: Ctrl+S / Cmd+S global = checkpoint del archivo abierto. El
  // Editor ya lo captura cuando el textarea tiene foco; este handler cubre
  // el resto (el reflejo del dev no depende de dónde esté el foco) y
  // bloquea el "guardar página" del navegador siempre.
  //
  // Capa 30: este mismo handler también canaliza los atajos de coordinación
  // (Alt+A/R/J/K y «?»). Son aceleradores del Inspector — no inventan
  // protocolo; reusan `resolver` y `seleccionar`. Reglas para no romper el
  // editor: Alt-* se ignora si el target es un campo de texto editable
  // (Alt+letra ya escribe en algunos layouts); «?» se ignora si el foco
  // está en input/textarea/contenteditable.
  useEffect(() => {
    function esCampoEditable(el: EventTarget | null): boolean {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return true;
      return el.isContentEditable;
    }
    function mostrarToast(text: string, ok = true) {
      emitToast(text, ok ? "ok" : "warn");
    }
    // Propuestas esperando MI review (yo soy dueño). Reusa la misma lógica
    // que el Inspector — sin selectores derivados nuevos para no inflar el
    // store por una feature de polish.
    function propuestasParaMi() {
      const st = getState();
      const yo = st.yo?.client_id;
      if (!yo) return [];
      return Object.values(st.proposals).filter(
        (p) => st.owners[p.path] === yo,
      );
    }
    function archivosConPropPendiente(): string[] {
      // Únicos paths con propuesta-para-mí, ordenados (estabilidad de
      // navegación: la lista no debe bailar entre Alt+J consecutivos).
      const ps = propuestasParaMi();
      return [...new Set(ps.map((p) => p.path))].sort();
    }
    function navegar(delta: 1 | -1) {
      const paths = archivosConPropPendiente();
      if (paths.length === 0) { mostrarToast(t.kbd_toast_no_targets, false); return; }
      const actual = getState().currentPath;
      const idx = actual ? paths.indexOf(actual) : -1;
      // Si el archivo abierto no está en la lista, J va al primero; K al último.
      const nextIdx = idx < 0
        ? (delta > 0 ? 0 : paths.length - 1)
        : (idx + delta + paths.length) % paths.length;
      seleccionar(paths[nextIdx]);
    }

    // Si HAY un modal abierto (AdminModal, InviteModal, KbdHelp,
    // ConfirmDialog, NuevoArchivo, LegalModal…), los aceleradores del
    // workspace no deben dispararse: Alt+A/R aprobaba propuestas "fantasma"
    // mientras el usuario tenía abierto otro flujo, y «?» re-abría
    // KbdHelp encima de otro modal. El `.modalbg` siempre está presente
    // en el DOM cuando algún modal del IDE está abierto — ModalPortal lo
    // monta en <body>, por eso un querySelector global lo detecta sin
    // tener que cablear flags por todos lados. Ctrl+S sigue funcionando
    // (no es un acelerador del workspace; el navegador lo necesita
    // bloqueado siempre, y el toast informa "nada que guardar" si aplica).
    function hayModalAbierto(): boolean {
      return document.querySelector(".modalbg") != null;
    }

    function onKey(e: KeyboardEvent) {
      // Ctrl/Cmd+S — capa 19, ahora con feedback. El usuario teclea el
      // atajo sin "ver" si pasó algo: el toast confirma qué hizo el sistema.
      // Diferenciamos:
      //   · sin archivo abierto → aviso neutro (no es error, es "nada que
      //     guardar"; mejora la sensación de respuesta).
      //   · no-dueño con draft → "propuesta enviada" (es el cambio de
      //     contrato que vive bajo Ctrl+S desde capa 28).
      //   · dueño / archivo libre → "cambios analizados" (el save dispara
      //     análisis de impacto del lado del server).
      //   · sin draft ni dirty (nada que mover) → "todo al día".
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        const st = getState();
        const path = st.currentPath;
        if (!path) {
          emitToast(t.toast_save_no_file, "warn");
          return;
        }
        const tenia_draft = st.drafts[path] != null;
        const era_de_otro = esDeOtro(path);
        const dirty = !!st.dirty[path];
        guardar(path);
        if (era_de_otro && tenia_draft) {
          emitToast(t.toast_save_proposed(path), "ok");
        } else if (dirty || tenia_draft) {
          emitToast(t.toast_save_analyzed, "ok");
        } else {
          emitToast(t.toast_save_clean, "ok");
        }
        return;
      }
      // Atajos Alt-* (sin Ctrl/Meta/Shift): aceleradores del Inspector.
      // Bloqueamos si el foco está editando texto (evita que Alt+A escriba
      // un carácter especial según layout). Los demás atajos del editor
      // (que no usan Alt) siguen funcionando dentro del textarea.
      if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        if (esCampoEditable(e.target)) return;
        if (hayModalAbierto()) return;
        const k = e.key.toLowerCase();
        if (k === "a" || k === "r") {
          const ps = propuestasParaMi();
          if (ps.length === 0) {
            e.preventDefault();
            mostrarToast(t.kbd_toast_no_props, false);
            return;
          }
          // Preferir la propuesta del archivo abierto (lo que el ojo está
          // mirando); si no hay, tomar la primera global.
          const cur = getState().currentPath;
          const target = ps.find((p) => p.path === cur) ?? ps[0];
          e.preventDefault();
          resolver(target.id, k === "a");
          mostrarToast(
            (k === "a" ? t.kbd_toast_approved : t.kbd_toast_rejected) + " · " + target.path,
            k === "a",
          );
          return;
        }
        if (k === "j" || k === "k") {
          e.preventDefault();
          navegar(k === "j" ? 1 : -1);
          return;
        }
      }
      // «?» abre la hoja de atajos. En el layout US es Shift+/, así que
      // chequeamos por `key` directamente (es independiente del layout).
      // Lo ignoramos si el foco está editando texto (no querés que abrir
      // ayuda interrumpa una búsqueda). También si ya hay un modal abierto:
      // KbdHelp encima de AdminModal/InviteModal/Confirm era apilamiento
      // ciego con doble Esc para volver — preferimos "cierra el otro antes".
      if (e.key === "?" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (esCampoEditable(e.target)) return;
        if (hayModalAbierto()) return;
        e.preventDefault();
        setKbdOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [t]);

  // Suscripción al bus de toasts (store::subscribeToasts). El timer se
  // re-evalúa por ID — si entra un toast nuevo mientras el anterior está
  // a la vista, el viejo se reemplaza limpiamente. 2.4s da tiempo para
  // leer y no fatiga. `prefers-reduced-motion` ya neutraliza la entrada
  // en CSS — acá no hace falta lógica extra.
  useEffect(() => {
    return subscribeToasts((t) => {
      setToast({ id: t.id, text: t.text, tone: t.tone });
      setTimeout(() => setToast((cur) => (cur && cur.id === t.id ? null : cur)), 2400);
    });
  }, []);

  // Pulido pre-mercado: warning al cerrar pestaña / recargar / navegar si
  // hay drafts (propuestas locales sin enviar al server). Sin esto, capa 28
  // perdía silenciosamente todo lo escrito en archivos ajenos. El mensaje
  // de `returnValue` es opcional — los navegadores modernos muestran el
  // suyo por seguridad ("¿salir del sitio?"), pero seteándolo nos
  // aseguramos que beforeunload haga el prompt.
  //
  // No incluimos `dirty` "solo del dueño" (sin draft): ese contenido YA
  // viajó al server, lo único pendiente es Ctrl+S para análisis. Perder
  // el dot no es pérdida de trabajo. Solo gateamos cuando hay drafts.
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (contarDrafts() === 0) return;
      // El standard moderno: preventDefault + setear returnValue. Mensajes
      // custom ya no se muestran (los navegadores los reemplazaron por
      // genéricos por seguridad), pero el prompt aparece.
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  // Avisos del navegador — registro de avisos ya mostrados (por id de
  // evento). Es un ref, no estado: cambiarlo no debe re-renderizar.
  const notifSeen = useRef<Set<string>>(new Set());

  // Pide permiso de notificaciones al entrar a un equipo. `requestPermission`
  // sólo abre el diálogo si la decisión está pendiente ("default"); si ya se
  // concedió o denegó, no molesta. También reinicia el registro de avisos:
  // es por-equipo (cambiar de equipo empieza de cero).
  //
  // Bypass en modo demo (?demo=1, iframe del hero de la landing): el demo
  // simula un equipo para satisfacer los gates del App, así que esta rama
  // se dispararía pidiendo permiso de notificaciones al visitante de la
  // landing — invasivo y fuera de contexto, además de que el DemoLoop crea
  // propuestas que después caerían como avisos reales del navegador.
  useEffect(() => {
    if (s.fase !== "team") return;
    if (s.demoMode) return;
    notifSeen.current.clear();
    if ("Notification" in window && Notification.permission === "default") {
      try { Notification.requestPermission().catch(() => {}); }
      catch { /* navegador sin la API */ }
    }
  }, [s.fase, s.demoMode]);

  // Avisos del navegador — dispara una notificación cuando llega algo que te
  // NECESITA (una propuesta sobre un archivo tuyo, o un impacto sobre uno
  // tuyo) y la pestaña NO está enfocada. Si estás mirando Orux no molesta:
  // ya lo ves en vivo. `notifSeen` evita re-notificar lo mismo en cada
  // render; al entrar a un equipo la pestaña está enfocada, así que las
  // propuestas pendientes que cargan en el handshake no disparan aviso.
  // En demo no aplica: el iframe vive dentro de la landing y document.hidden
  // se vuelve true en cuanto el visitante deja esa pestaña, así que el demo
  // disparaba avisos reales por las propuestas simuladas del DemoLoop.
  useEffect(() => {
    if (s.demoMode) return;
    const yo = s.yo?.client_id;
    if (!yo) return;
    const puede =
      "Notification" in window && Notification.permission === "granted";

    type Aviso = { id: string; titulo: string; cuerpo: string };
    const avisos: Aviso[] = [];
    for (const p of Object.values(s.proposals)) {
      if (s.owners[p.path] === yo && p.author_id !== yo) {
        avisos.push({
          id: "prop:" + p.id,
          titulo: t.notif_prop_title,
          cuerpo: t.notif_prop_body(p.author_name, p.path),
        });
      }
    }
    for (const im of Object.values(s.impacts)) {
      if (s.owners[im.affected_path] === yo) {
        avisos.push({
          id: "imp:" + im.source_path + "::" + im.affected_path,
          titulo: t.notif_imp_title,
          cuerpo: t.notif_imp_body(im.author_name, im.affected_path),
        });
      }
    }

    for (const a of avisos) {
      if (notifSeen.current.has(a.id)) continue;
      notifSeen.current.add(a.id);  // visto: no re-notificar en próximos renders
      if (puede && document.hidden) {
        try {
          const n = new Notification(a.titulo, { body: a.cuerpo, tag: a.id });
          n.onclick = () => { window.focus(); n.close(); };
        } catch { /* algunos navegadores restringen el constructor */ }
      }
    }
  }, [s.proposals, s.impacts, s.owners, s.yo, s.demoMode, t]);

  // La app está cerrada por dos compuertas: sin autenticar -> login;
  // autenticado pero sin equipo -> lobby (capa 15). Sólo dentro de un
  // equipo se ve el IDE, y es el de ESE equipo y de ningún otro.
  if (!s.authed) return <Login />;
  if (s.fase !== "team") return <Lobby />;

  return (
    <div className={"app" + (inspOpen ? "" : " sin-insp") + (s.demoMode ? " demo-mode" : "")}>
      {s.demoMode && <DemoLoop />}
      <TopBar inspOpen={inspOpen} toggleInsp={toggleInsp} />
      <div className="layout">
        <Rail
          vista={vista}
          setVista={setVista}
          abrirAdmin={() => setAdminOpen(true)}
        />
        <Sidebar vista={vista} width={wSidebar} />
        <Splitter
          lado="left"
          ariaLabel="redimensionar explorador"
          onResize={onResizeSide}
        />
        <main className="main isla">
          {Object.keys(s.files).length === 0 ? (
            <EmptyWorkspace onIrAGit={() => setVista("git")} />
          ) : (
            <>
              <Tabs />
              <ContextBar />
              <Editor />
            </>
          )}
        </main>
        {inspOpen && (
          <>
            <Splitter
              lado="right"
              ariaLabel="redimensionar inspector"
              onResize={onResizeInsp}
            />
            <Inspector onClose={toggleInsp} width={wInsp} />
          </>
        )}
      </div>
      <StatusBar />
      {adminOpen && s.esAdmin && <AdminModal onClose={() => setAdminOpen(false)} />}
      {kbdOpen && <KbdHelp onClose={() => setKbdOpen(false)} />}
      {tutorialOn && (
        <Tutorial api={tutorialApi} onDone={() => setTutorialOn(false)} />
      )}
      {toast && (
        <div
          className={"kbd-toast t-" + toast.tone}
          role={toast.tone === "bad" ? "alert" : "status"}
          aria-live={toast.tone === "bad" ? "assertive" : "polite"}
        >
          {toast.text}
        </div>
      )}
      {/* Modo demo: overlay invisible que captura cualquier clic/tecla del
          visitante. La animación corre desde JS (setTimeout en DemoLoop), así
          que bloquear la interacción no afecta lo que se muestra. Sin esto
          un visitante curioso podría disparar acciones reales o el modal
          de borrar archivos, rompiendo el bucle. */}
      {s.demoMode && (
        <div
          className="demo-overlay"
          aria-hidden="true"
          onClickCapture={(e) => { e.preventDefault(); e.stopPropagation(); }}
        />
      )}
    </div>
  );
}
