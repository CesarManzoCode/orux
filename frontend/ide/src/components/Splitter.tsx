import { useRef, useState } from "react";
import type { PointerEvent as RPointerEvent } from "react";

// Capa 27 — Splitter de IDE de toda la vida. Un divisor angosto entre
// dos paneles que el usuario arrastra para redimensionar. Tres ideas:
//
//  1) `setPointerCapture` enclava el cursor al divisor: si el ratón se
//     sale del div mientras arrastra, los eventos siguen viniendo acá.
//     Es la API moderna que reemplaza al viejo "addEventListener en
//     window + cleanup". Cero leaks.
//
//  2) Durante el drag bloqueamos `userSelect` en el body para que no se
//     pinte el texto del editor al pasar por encima — un detalle que
//     separa "se siente nativo" de "se siente web".
//
//  3) El ancho lo decide el PADRE (App.tsx) y lo persiste a localStorage.
//     Acá solo emitimos el delta en píxeles; quien sabe qué hacer con él
//     es el padre (clamp a min/max, persistir, etc.). Una sola fuente
//     de verdad.
export function Splitter({
  onResize,
  // "left": arrastrar a la DERECHA agranda al panel de la izquierda
  //         (caso del divisor entre Sidebar y Main).
  // "right": arrastrar a la IZQUIERDA agranda al panel de la derecha
  //          (caso del divisor entre Main e Inspector).
  lado,
  ariaLabel,
}: {
  onResize: (deltaPx: number) => void;
  lado: "left" | "right";
  ariaLabel: string;
}) {
  const [arr, setArr] = useState(false);
  const inicio = useRef(0);

  function onDown(e: RPointerEvent<HTMLDivElement>) {
    inicio.current = e.clientX;
    e.currentTarget.setPointerCapture(e.pointerId);
    setArr(true);
    // Mientras arrastrás: no se pinta texto y el cursor es col-resize
    // GLOBAL (si soltás fuera del divisor, igual se ve consistente).
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  }

  function onMove(e: RPointerEvent<HTMLDivElement>) {
    if (!arr) return;
    const dx = e.clientX - inicio.current;
    inicio.current = e.clientX;
    // Signo según el lado: para el inspector (lado="right"), arrastrar a
    // la izquierda (dx negativo) debe AGRANDAR — invertimos.
    onResize(lado === "left" ? dx : -dx);
  }

  function onUp(e: RPointerEvent<HTMLDivElement>) {
    if (!arr) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    setArr(false);
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
  }

  return (
    <div
      className={"splitter" + (arr ? " arr" : "")}
      role="separator"
      aria-orientation="vertical"
      aria-label={ariaLabel}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    />
  );
}
