# Contexto del proyecto

Este directorio contiene el proyecto **laidea** (nombre temporal). El README.md tiene la visión completa. Léelo primero antes de hacer cualquier cosa.

## Qué estamos construyendo

Un editor colaborativo en tiempo real sobre Git para equipos de 2 a 50 devs. Capa de coordinación que previene colisiones, detecta impacto semántico de cambios automáticamente, y distribuye el conocimiento del proyecto para que el líder no sea el cuello de botella.

No reemplaza Git, GitHub, ni IDEs. No es Replit. No es governance corporativo.

## Tesis

> Misma seguridad que el flujo actual (branches, PRs, reviews, merges), sin la ceremonia. El sistema sabe sin que nadie le pregunte.

Lo que vendemos al dev: "Toca lo que necesites. El sistema se encarga de que nada se rompa."

Lo que NO vendemos: ownership, enforcement, permisos, control, vigilancia. El ownership es implementación interna (el diferencial del coche), no es lo que se vende.

## Estado actual

Fase muy temprana. Solo existe la idea escrita en `README.md`. No hay código, no hay arquitectura, no hay stack decidido. El usuario explícitamente pidió no escribir código todavía.

## Principios para colaborar en este proyecto

- **No escribir código hasta que se pida explícitamente.** Estamos en fase de idea.
- **No proponer stack ni arquitectura todavía.** El usuario lo dirá cuando sea momento.
- **Idioma: español.** Toda comunicación y todo artefacto en español por ahora.
- **Construcción por capas.** El orden importa: estado compartido → edición en tiempo real → ownership → análisis semántico → notificaciones → integración Git. No se añade una capa hasta que la anterior funcione.
- **Riesgo crítico identificado: feature soup.** Resistir la tentación de proponer muchas features. Una capa increíble vale más que veinte mediocres.
- **El núcleo es la coordinación semántica, no el editor.** El editor es vehículo.

## Decisiones ya tomadas

- Plataforma fase 1: web app.
- Plataforma fase 2: ir al entorno del dev (plugins de VSCode, JetBrains).
- Sobre Git: integración, no reemplazo. `git clone` debe bastar.
- Sin modo offline. Estado compartido en tiempo real es la base.
- Público objetivo inicial: equipos nuevos sin inercia, open source que empieza, founders técnicos 2-3 personas.
- Decisor de adopción: líder del equipo (CTO, tech lead, founder técnico).

## Qué falta definir (no decidir todavía sin que el usuario lo pida)

- Stack técnico.
- Solución para el estado compartido en tiempo real (investigar CRDTs, OT, Yjs, ShareDB cuando toque).
- Primer lenguaje a soportar para análisis semántico (probablemente TypeScript).
- Modelo de negocio y pricing.
- Nombre real del producto.

## Cómo se debe sentir el producto

- "Misma vida, menos dolor."
- Live collaborative review, no governance corporativo.
- Multiplayer semantic coding.
- El dev no se siente bloqueado antes de intentar.
- El owner no siente que invadieron su código.
- Editar primero. Negociar después. Aplicar al final.
