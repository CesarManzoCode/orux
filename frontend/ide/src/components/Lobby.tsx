// La "Lobby" original (autenticado, sin equipo) se rediseñó como
// dashboard real (Hub.tsx, 2026-05-19). Este shim mantiene el import
// existente del App con el componente nuevo detrás — el contrato de
// store (s.fase === "lobby" → <Lobby/>) sigue igual.
export { Hub as Lobby } from "./Hub";
