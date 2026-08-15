# UI overhaul docket — five design languages

A design exploration, deliberately **without touching the app**. Each language ships as a
self-contained HTML demo beside this file — open them straight in a browser (`file://`
works; nothing is fetched) and compare against the live viewer. All five draw the same
fake dish with the same fake panels, so the only variable is the language.

## Ground rules the exploration honours

1. **The dish renderer is not on the table.** `viewer/dish.js` + `worm.js` painters are
   the product; every language below styles the *chrome around* the plate and, at most,
   proposes one more painter/theme in the existing `PAINTERS`/`THEMES` registries — the
   same seam the three current looks already share. Reuse is the design constraint, not
   an aspiration.
2. **The theme surface is already declared.** `style.css` custom properties (surfaces,
   text roles, series colours) + `themes.js` (plate, grid, egg, field tints per look).
   A chrome overhaul is: one alternate property sheet, one palette entry, font stack,
   and border/radius/shadow policy. Panels, stats and controls inherit.
3. **No new dependencies, no webfonts.** System font stacks only, like everything else
   in `web/`. Each demo names its stack.
4. **Both dishes and the museum wear it.** A language that only works for the reference
   animal fails the arena's amber warnings and the museum's long-form reading; each demo
   shows a Track B accent treatment.

## The five languages

| # | demo | thesis | one line |
|---|---|---|---|
| 1 | `01-monograph.html` | **The Monograph** | a 19th-century zoology plate: paper, ink, serifs, figure captions — the worm as engraving |
| 2 | `02-cathode.html` | **Cathode** | a lab oscilloscope: one phosphor, scanlines, afterglow — every number a trace |
| 3 | `03-poster.html` | **Poster** | Bauhaus/Swiss: flat primaries, thick ink outlines, hard shadows, huge type — the dish as artwork |
| 4 | `04-observatory.html` | **The Observatory** | deep-space glass: luminous plate, frosted floating panels, bloom — instrument cluster at night |
| 5 | `05-fieldnotes.html` | **Field Notes** | a hobbyist's notebook: kraft paper, index cards, tape, handwriting in the margins — the labor-of-love made visible |

Orthogonality, stated: light-serif-archival (1) vs dark-mono-instrument (2) vs
flat-loud-geometric (3) vs dark-soft-dimensional (4) vs warm-handmade-personal (5).
They disagree about theme (light/dark), type (serif/mono/grotesk/humanist/hand),
edges (hairline/glow/ink-slab/blur/sketch), and mood (reverent/technical/confident/
ambient/affectionate) — five corners of the space rather than five tints of one corner.

## Per-language notes

**1 · The Monograph** — for the project's Track A soul: the reconstruction as scholarship.
Costs: light theme needs the existing `#dish[data-plate="light"]` chrome-inversion path
(already built for cartoon/realistic); the digital painter's curvature tints want an
ink-safe diverging ramp. Adoption S/M. Risk: long sessions on paper-white; keep the
dark dishes available per-plate as today.

**2 · Cathode** — for the instrument feel: the viewer as a scope you *operate*. Single
accent discipline makes state legible (anything not-green is an alarm). Costs: one
palette + a phosphor painter (afterglow = the trail layer it already has). Adoption S.
Risk: monochrome fights the three-field overlay — fields would need intensity coding.

**3 · Poster** — for delight and screenshots; the arena especially (dynasty colours are
already flat and loud). Costs: border/shadow policy + a flat painter; the panels take it
free. Adoption M. Risk: heavy ink around dense panels (302 dots) needs restraint.

**4 · The Observatory** — the current look's natural evolution: keep the dark data-first
soul, add depth and light. Costs: property sheet only (blur, glows, gradients); zero
painter work. Adoption S. Risk: backdrop-filter cost on low-end machines — needs the
same performance care the field cache got.

**5 · Field Notes** — the repo's voice (a labor of love) as an interface. Museum and
specimen shelf wear it best of all five. Costs: hand-font stacks are the weakest part of
the no-webfont rule (platform variance); card rotation/tape are cheap CSS. Adoption M.
Risk: whimsy vs data density — panels stay ruled-paper plain, only the frame is warm.

## Recommendation (one reviewer's, to be argued with)

Ship **4 (Observatory)** as the default evolution — smallest distance, biggest felt
upgrade, zero painter risk. Offer **1 (Monograph)** as the light theme rather than a
plain inversion. Let the **museum + specimen shelf** wear **5 (Field Notes)** — the
document pages are where its warmth pays and its density risk vanishes. Keep **2** and
**3** as palettes in `themes.js`'s registry if they earn fans: Cathode is one palette
entry; Poster is the arena's natural party dress.

## If one is adopted, the work is

1. A property sheet (`:root` custom properties) + `themes.js` palette entry.
2. Border/radius/shadow/typography policy applied in `style.css` — the components
   already read the variables.
3. At most one painter added to `PAINTERS` (Cathode/Poster only).
4. `tools/smoke_web.mjs` contrast + layout passes at all viewports, per usual.
