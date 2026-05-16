import { useSyncExternalStore } from "react";
import { subscribe, getState, type State } from "./store";

// Suscripción al store. Re-render global ante cualquier cambio: la app es
// chica y el estado es un espejo compartido; optimizar selectores sería
// complejidad para un problema que no existe (mismo criterio que el resto
// del proyecto).
export function useStore(): State {
  return useSyncExternalStore(subscribe, getState);
}
