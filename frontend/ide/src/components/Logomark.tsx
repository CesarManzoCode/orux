// Logomark de marca — la figura hexafoil del logo de Orux (seis lentes
// interlazadas con simetría rotacional 6×). Solo la marca, sin wordmark:
// el texto "Orux" se compone aparte donde corresponde. Coherente con el
// gradiente plateado/acero de la dirección de arte "Infraestructura".
//
// useId() le da un id único al <linearGradient> en cada instancia: si
// salen dos logos en la misma página (TopBar + Hub mismo render, etc.),
// referencias `url(#...)` duplicadas dejarían de funcionar en algunos
// navegadores. Esto lo evita sin pensarlo.
import { useId } from "react";

export function Logomark({
  size = 18,
  className,
}: {
  size?: number;
  className?: string;
}) {
  const id = useId();
  const gradId = `lm-silver-${id}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="45%" stopColor="#C8C8CC" />
          <stop offset="100%" stopColor="#6E6E72" />
        </linearGradient>
      </defs>
      <g
        transform="translate(24,24)"
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth="2.2"
        strokeLinejoin="round"
      >
        <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        <g transform="rotate(60)">
          <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        </g>
        <g transform="rotate(120)">
          <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        </g>
        <g transform="rotate(180)">
          <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        </g>
        <g transform="rotate(240)">
          <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        </g>
        <g transform="rotate(300)">
          <path d="M0 -16 Q8.7 -5.8 0 0 Q-8.7 -5.8 0 -16 Z" />
        </g>
        <circle cx="0" cy="0" r="1.9" fill={`url(#${gradId})`} stroke="none" />
      </g>
    </svg>
  );
}
