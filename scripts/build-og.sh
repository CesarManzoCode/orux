#!/usr/bin/env bash
# Genera frontend/landing/public/og.png a partir de primitivas ImageMagick.
#
# Por qué no uso el SVG (frontend/landing/og.svg) directamente: ImageMagick
# delegate de SVG en este host pide el binario `rsvg-convert` que no está
# instalado. Las primitivas built-in (cairo/pangocairo) sí funcionan, así
# que armamos la imagen en pasos. El SVG queda como artefacto editable
# para v2; este script es la fuente de verdad del PNG actual.
#
# Dirección de arte: "Infraestructura / Sala de control" (ver landing/css/
# base.css). Acero #5d7fa6 + base #070809; verde --live SOLO donde hay
# vida coordinada (un dot, no decoración).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/frontend/landing/public/og.png"

ARGS=(-size 1200x630 xc:'#070809')

# --- Grid sutil de fondo (rejilla estructural) ---
# Hairlines casi imperceptibles cada 60px — dan textura tipo plano
# arquitectónico sin chillar. Mismo --hair de base.css.
ARGS+=(-strokewidth 1 -stroke '#14161c' -fill none)
for x in 60 120 180 240 300 360 420 480 540 600 660 720 780 840 900 960 1020 1080 1140; do
  ARGS+=(-draw "line $x,0 $x,630")
done
for y in 60 120 180 240 300 360 420 480 540 600; do
  ARGS+=(-draw "line 0,$y 1200,$y")
done

# Ejes mayores (un punto más visibles) — la columna que divide marca de chips
# y dos horizontales que enmarcan la zona central. Sigue siendo subliminal.
ARGS+=(-stroke '#1a1e26')
ARGS+=(-draw 'line 0,200 1200,200')
ARGS+=(-draw 'line 0,430 1200,430')
ARGS+=(-draw 'line 680,0 680,630')

# --- Top-right: badge "EN VIVO" ---
# El ÚNICO verde de la imagen. Pinta lo que es la marca: "vivo / coordinado".
# Es chico y a la derecha para que no compita con la marca.
ARGS+=(-stroke none)
ARGS+=(-fill '#43b98a' -draw 'circle 900,52 900,57')
ARGS+=(-stroke '#43b98a' -strokewidth 1 -fill none -draw 'circle 900,52 900,61')
ARGS+=(-stroke none -fill '#747a89' -font Liberation-Sans-Bold -pointsize 13)
ARGS+=(-kerning 2.6)
ARGS+=(-annotate +918+57 'EN VIVO · ORUX.SPACE')
ARGS+=(-kerning 0)

# --- Wordmark Orux (columna izquierda, top) ---
# Tinta sólida + tracking apretado: autoridad por escala, no por color.
ARGS+=(-stroke none -fill '#edeff3' -font Liberation-Sans-Bold -pointsize 138)
ARGS+=(-kerning -4)
ARGS+=(-annotate +78+325 'Orux')
ARGS+=(-kerning 0)

# Underline acero — micro-marca de identidad, no decoración
ARGS+=(-fill '#5d7fa6' -draw 'rectangle 80,348 162,352')

# --- Tagline (dos líneas) + subtitle ---
ARGS+=(-fill '#a9afbc' -font Liberation-Sans -pointsize 28)
ARGS+=(-annotate +80+406 'Coordinación de código en tiempo real')
ARGS+=(-annotate +80+446 'sobre Git.')
ARGS+=(-fill '#747a89' -pointsize 19)
ARGS+=(-annotate +80+500 'Para equipos de 2 a 50 devs.')

# --- Columna derecha: las tres preguntas que resuelve ---
# Mismo copy que og:title ("Quién toca qué. De quién es. Qué rompe.")
# en 3 chips minimalistas con los colores de significado de la marca:
# peer (azul) = otra persona, steel (acero) = identidad/ownership,
# risk (ámbar) = impacto/algo a revisar.

# Chip 1: peer (azul "otra persona")
ARGS+=(-fill '#0e1014' -stroke '#20242c' -strokewidth 1)
ARGS+=(-draw 'roundrectangle 740,212 1120,272 8,8')
ARGS+=(-stroke none -fill '#6ea8e6' -draw 'circle 770,242 770,247')
ARGS+=(-fill '#edeff3' -font Liberation-Sans-Bold -pointsize 23)
ARGS+=(-annotate +795+250 'Quién toca qué.')

# Chip 2: steel (acero identidad)
ARGS+=(-fill '#0e1014' -stroke '#20242c' -strokewidth 1)
ARGS+=(-draw 'roundrectangle 740,292 1120,352 8,8')
ARGS+=(-stroke none -fill '#5d7fa6' -draw 'circle 770,322 770,327')
ARGS+=(-fill '#edeff3' -font Liberation-Sans-Bold -pointsize 23)
ARGS+=(-annotate +795+330 'De quién es.')

# Chip 3: risk (ámbar impacto)
ARGS+=(-fill '#0e1014' -stroke '#20242c' -strokewidth 1)
ARGS+=(-draw 'roundrectangle 740,372 1120,432 8,8')
ARGS+=(-stroke none -fill '#d6a341' -draw 'circle 770,402 770,407')
ARGS+=(-fill '#edeff3' -font Liberation-Sans-Bold -pointsize 23)
ARGS+=(-annotate +795+410 'Qué rompe.')

# --- Pie: eyebrow técnico monoespaciado ---
ARGS+=(-fill '#747a89' -font Liberation-Mono-Bold -pointsize 13)
ARGS+=(-kerning 2.6)
ARGS+=(-annotate +80+588 'CAPA DE COORDINACIÓN · MULTI-LENGUAJE · SELF-HOSTABLE')
ARGS+=(-kerning 0)

# --- Strip metadata + write ---
ARGS+=(-strip)

magick "${ARGS[@]}" "$OUT"
echo "[og] generado: $OUT"
identify "$OUT"
