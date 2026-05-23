// Spotlight: oscurece la pantalla salvo un rectángulo (el "target") y
// dibuja un halo pulsante alrededor. Si `clickable` está activo, el
// rectángulo absorbe el click y lo convierte en `onClick` — es como
// avanza el tutorial cuando el paso espera al usuario.
//
// El target se identifica por su `data-tour-id` en el DOM real (no por
// ref): así cualquier componente puede ser "targeteable" agregándole un
// atributo, sin tener que pasar refs hasta acá.
//
// El bounding box se relee en cada animation frame mientras el target
// está vivo: el usuario puede redimensionar el sidebar, hacer scroll,
// abrir/cerrar paneles — el halo lo sigue sin lag.
import { useEffect, useState } from "react";

interface Rect { x: number; y: number; w: number; h: number; }

function leerBBox(el: Element): Rect {
  const r = el.getBoundingClientRect();
  return { x: r.left, y: r.top, w: r.width, h: r.height };
}

export function Spotlight({
  targetId,
  clickable,
  onClick,
}: {
  targetId?: string;
  clickable?: boolean;
  onClick?: () => void;
}) {
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    if (!targetId) { setRect(null); return; }
    let raf = 0;
    let alive = true;
    function loop() {
      if (!alive) return;
      const el = document.querySelector(`[data-tour-id="${targetId}"]`);
      if (el) {
        const next = leerBBox(el);
        setRect((prev) => {
          if (
            prev && prev.x === next.x && prev.y === next.y &&
            prev.w === next.w && prev.h === next.h
          ) return prev;
          return next;
        });
      } else {
        setRect(null);
      }
      raf = requestAnimationFrame(loop);
    }
    raf = requestAnimationFrame(loop);
    return () => { alive = false; cancelAnimationFrame(raf); };
  }, [targetId]);

  // Sin target o target inexistente: backdrop pleno (no hay hueco). El bot
  // se posiciona centrado en estos casos (lo decide el Tutorial).
  if (!targetId || !rect) {
    return <div className="tut-backdrop" aria-hidden />;
  }

  const pad = 8;
  const style: React.CSSProperties = {
    left: rect.x - pad + "px",
    top: rect.y - pad + "px",
    width: rect.w + pad * 2 + "px",
    height: rect.h + pad * 2 + "px",
  };

  return (
    <>
      {/* El "cutout": el rect que queda iluminado. Su box-shadow inverso
          masivo es lo que crea el oscurecimiento de todo lo demás. */}
      <div
        className={"tut-cutout" + (clickable ? " clickable" : "")}
        style={style}
        onClick={clickable ? onClick : undefined}
        role={clickable ? "button" : undefined}
        aria-label={clickable ? "continuar tutorial" : undefined}
        tabIndex={clickable ? 0 : undefined}
        onKeyDown={
          clickable
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onClick?.();
                }
              }
            : undefined
        }
      />
      {/* Halo pulsante sobre el cutout (decorativo). pointer-events:none
          para no comer el click del cutout debajo. */}
      <div className="tut-halo" style={style} aria-hidden />
    </>
  );
}
