// Portalea cualquier modal a document.body. Por qué importa:
// si el modal se renderiza dentro de un padre con animation/transform/
// backdrop-filter (e.g. la animación fade-in del topbar la primera vez
// que se monta), el padre se vuelve "containing block" y el
// position:fixed del .modalbg deja de cubrir el viewport — el modal
// aparece recortado dentro del topbar. Llevándolo a <body> escapamos
// ese trap para siempre, sin importar dónde se monte el modal en el árbol.
// SSR-safe vía typeof document (la app es client-only hoy, pero sin coste).
import { type ReactNode } from "react";
import { createPortal } from "react-dom";

export function ModalPortal({ children }: { children: ReactNode }) {
  if (typeof document === "undefined") return null;
  return createPortal(children, document.body);
}
