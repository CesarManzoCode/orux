// OruxBot: la presencia que conduce el tutorial. No es un "personaje" ni
// una mascota — es el logomark de la marca, flotando con un glow suave,
// y una burbuja al lado donde el texto aparece con typewriter. La idea
// es que se sienta como una presencia del producto, no como Clippy.
//
// Posicionamiento: el `pos` viene del orquestador. Si hay target, el
// orquestador calcula el lado del bot respecto al bbox del target; si
// no hay target, va centrado. Esta separación deja al bot tonto: él
// sólo dibuja.
import { useEffect, useState } from "react";
import { Logomark } from "../components/Logomark";

export interface BotPos {
  // Posición fija en viewport. Usamos top/left calculados.
  top: number;
  left: number;
  // Anclaje horizontal y vertical del *propio* bot — define qué punto del
  // bot se posa en {top, left}. Default top-left.
  anchor?: "tl" | "tr" | "bl" | "br" | "center";
}

export function OruxBot({
  text,
  pos,
  ctaLabel,
  onCta,
}: {
  text: string;
  pos: BotPos;
  ctaLabel?: string;
  onCta?: () => void;
}) {
  // Typewriter — revela char por char. Velocidad ~42 chars/s: rápido para
  // no aburrir, lento como para que el ojo lo siga. La key del setState
  // depende de `text`: cuando el orquestador cambia el paso, el efecto se
  // recrea y empieza el typewriter de cero (no se mezclan textos).
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    if (!text) return;
    let i = 0;
    const id = window.setInterval(() => {
      i++;
      setShown(i);
      if (i >= text.length) window.clearInterval(id);
    }, 24);
    return () => window.clearInterval(id);
  }, [text]);

  const style: React.CSSProperties = { top: pos.top + "px", left: pos.left + "px" };
  const anchorClass = "a-" + (pos.anchor ?? "tl");

  return (
    <div className={"tut-bot " + anchorClass} style={style}>
      <span className="tut-bot-mark">
        <span className="tut-bot-glow" aria-hidden />
        <Logomark size={32} />
      </span>
      <div className="tut-bot-bubble" role="status" aria-live="polite">
        <p className="tut-bot-tx">
          {text.slice(0, shown)}
          {shown < text.length && <span className="tut-bot-cursor" aria-hidden />}
        </p>
        {ctaLabel && onCta && (
          <button
            type="button"
            className="tut-bot-cta"
            onClick={onCta}
            autoFocus
          >
            {ctaLabel}
          </button>
        )}
      </div>
    </div>
  );
}
