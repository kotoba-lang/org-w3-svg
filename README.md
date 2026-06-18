# drawingml-svg

[![CI](https://github.com/com-junkawasaki/drawingml-svg/actions/workflows/ci.yml/badge.svg)](https://github.com/com-junkawasaki/drawingml-svg/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`drawingml-svg` is a small, dependency-free converter between SVG and DrawingML shape fragments.

It targets the practical subset needed for generated Office graphics and simple round-trips:

- SVG: `rect`, `circle`, `ellipse`, `line`, `polygon`, `polyline`, linear/quadratic/cubic/arc `path`, simple rect/text, line/text, and rect-background/line-border grids including merged cells and individual grid-line paint/cap/dash/join as native DrawingML tables, `text`, simple `tspan`, link/group containers, and basic `switch` fallback selection
- DrawingML: preset geometry shapes including common polygon, arrow, symbol, and flowchart presets, custom geometry paths including line/quadratic/cubic segments, native table cells, simple merged cells, cell text insets/anchors/list-style alignment/default runs, and individual table cell borders with line paint/cap/dash/join/miter/alpha under `p:graphicFrame` as editable SVG rectangles/lines/text, and text boxes under `p:sp`, with invalid numeric DrawingML attributes ignored where possible
- Geometry: position, size, CSS geometry properties, percent geometry lengths, rounded rectangles, transformed line endpoints, horizontal/vertical flips for lines, and DrawingML line/custom-geometry transform round-trips
- Images: embedded SVG `image` elements with valid base64 PNG/JPEG/GIF/WebP data URI sources, opacity, and legacy `xlink:href`
- Paint: SVG default fill/stroke/stroke-width/line-cap/line-join/miterlimit values including `miter-clip` as a miter approximation, transform-scaled shape and text-outline strokes, `vector-effect="non-scaling-stroke"`, solid fill, stroke color, stroke width including zero-width no-line strokes and percentage widths, line cap/join/miter/custom dash including percentage dash values, DrawingML preset dash fallback, DrawingML RGB/scheme color fallback with luminance modifiers, dash-offset approximation for offsets that start inside dash or gap segments, fill/stroke alpha including fully transparent no-fill/no-line paint, short/long alpha hex colors, CSS rgb/hsl color functions, named colors, `currentColor`, `context-fill`/`context-stroke`, inherited paint values, paint-server fallback colors, CSS-colored linear/radial gradient fallback, and representative pattern fallback colors
- Styling: inline presentation attributes, inline `style`, simple `<style>` rules for element/class/id, compound class, attribute selectors (`=`, `~=`, `|=`, `^=`, `$=`, `*=`), child, and descendant selectors, CSS specificity, `inherit`/`initial`/`unset`, and `!important` cascade priority
- Line markers: `marker-start`, `marker-end`, and `marker` shorthand arrow markers are converted to DrawingML line arrows for lines and open two-end paths/polylines
- Coordinate systems: root, nested SVG, and symbol `viewBox` normalization with `preserveAspectRatio` support
- Visibility: `display:none` is skipped as a subtree, while `visibility:hidden`/`collapse` hide the current element and still allow visible descendants
- Clipping: rectangular `clipPath` on `rect`/rounded `rect`, `circle`/`ellipse`, `line`, two-point open `polyline`/`path`, `text`, and embedded `image` is converted as bounding-box or segment intersection, including `userSpaceOnUse` and `objectBoundingBox` units
- Analysis: unsupported visual/layout attributes such as filters, masks, blend/isolation, fill/clip rules, visible paint order changes, unsupported vector effects, unsupported stroke line cap/join values, word spacing conflicts, dash offsets that cannot be approximated, visible text decoration color/style/thickness/underline offset/skip-ink differences, multi-value text rotation, unsupported text/path length adjustments, unsupported text layout/direction/typography controls, unsupported markers, and unresolved paint servers are reported, while default no-op values, normal-equivalent `font-stretch` percentages, zero-equivalent glyph orientation angles and baseline shifts, zero or single-character kerning, non-positioned run-level `tspan` anchors, marker-only paint order changes without markers, matching text decoration colors including default `currentColor`, `pathLength` without a visible dashed stroke, and rendering quality hints are ignored
- Transforms: SVG `transform` attributes and CSS `transform` properties on elements and groups for `matrix`, `translate`, `scale`, `rotate`, `skewX`, `skewY`, absolute-length, keyword, and reference-box percentage CSS `transform-origin`, plus DrawingML rotation/flip output as SVG transforms for supported shapes
- Reuse: local `defs`/`use` expansion for referenced shapes, groups, and basic `symbol viewBox` scaling, including legacy `xlink:href`, with unsupported missing/external use references reported by the analyzer
- Text: basic font size, weight, italic style, font family, `small-caps` and `all-small-caps` font variants, inherited and per-`tspan` `text-transform`, run-level `tspan` fill/font/outline/decoration/letter-spacing/word-spacing/baseline styling, DrawingML rich text runs as SVG `tspan` styles, text fill/no-fill, text outline color/width/cap/join/dash/miter, underline/strike decoration including `text-decoration-line`, `text-decoration` shorthand, and dashed/dotted/double/wavy underline styles, horizontal/vertical anchor including supported first-`tspan` `text-anchor`/baseline and `alignment-baseline` fallbacks, text-level `baseline-shift` `super`/`sub`, `xml:space="preserve"`, single-value `rotate` including CSS angle units, `letter-spacing`, simple `word-spacing`, `textLength` spacing adjustment, approximate `spacingAndGlyphs`, `dx`/`dy` positioning, first-`tspan` positioning fallback, multi-line `tspan` extraction, and multiple DrawingML paragraph extraction

The converter accepts fragments, not complete `.pptx` or `.docx` packages. It is intended as a reusable core that can later be wrapped by OOXML package readers/writers.

## Project links

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Release checklist: [RELEASE.md](RELEASE.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Issue tracker: <https://github.com/com-junkawasaki/drawingml-svg/issues>

## Install

```bash
pip install -e .
```

## CLI

```bash
# SVG -> DrawingML
drawingml-svg svg2dml input.svg -o shape.xml

# DrawingML -> SVG
drawingml-svg dml2svg shape.xml -o shape.svg

# stdin/stdout
cat input.svg | drawingml-svg svg2dml > shape.xml

# coverage / maturity report
drawingml-svg analyze input.svg

# installed package version
drawingml-svg --version
```

`dml2svg` and `svg2dml` are also installed as aliases.

## PPTX smoke test

The repository includes examples that embed converted DrawingML shapes into one-slide `.pptx` packages:

```bash
PYTHONPATH=src python examples/make_pptx.py examples/sample.svg -o tmp/drawingml-svg-sample.pptx
PYTHONPATH=src python examples/make_pptx.py examples/coverage.svg -o tmp/drawingml-svg-coverage.pptx
PYTHONPATH=src python examples/make_pptx.py examples/complex.svg -o tmp/drawingml-svg-complex.pptx
```

## Supported DrawingML presets

`dml2svg` currently preserves these DrawingML preset geometries as editable SVG shapes. Curved presets are converted to editable polygon approximations where SVG does not have a matching primitive:

- Basic primitives: `ellipse`, `line`, `oval`, `rect`, `roundRect`, `straightConnector1`
- Common polygons and corners: `bevel`, `corner`, `decagon`, `diagStripe`, `diamond`, `dodecagon`, `foldedCorner`, `halfFrame`, `heptagon`, `hexagon`, `homePlate`, `nonIsoscelesTrapezoid`, `octagon`, `parallelogram`, `pentagon`, `plaque`, `rtTriangle`, `snip1Rect`, `snip2DiagRect`, `snip2SameRect`, `trapezoid`, `triangle`
- Arc-like shapes: `blockArc`, `chord`, `pie`
- Arrows: `bentArrow`, `bentUpArrow`, `chevron`, `downArrow`, `leftArrow`, `leftRightArrow`, `leftRightUpArrow`, `leftUpArrow`, `notchedRightArrow`, `quadArrow`, `rightArrow`, `upArrow`, `upDownArrow`, `uturnArrow`
- Ribbons and callouts: `funnel`, `leftRightRibbon`, `ribbon`, `ribbon2`, `wedgeEllipseCallout`, `wedgeRectCallout`, `wedgeRoundRectCallout`
- Action buttons: `actionButtonBackPrevious`, `actionButtonBeginning`, `actionButtonBlank`, `actionButtonDocument`, `actionButtonEnd`, `actionButtonForwardNext`, `actionButtonHelp`, `actionButtonHome`, `actionButtonInformation`, `actionButtonMovie`, `actionButtonReturn`, `actionButtonSound`
- Symbols, stars, and math shapes: `cloud`, `heart`, `irregularSeal1`, `irregularSeal2`, `leftBrace`, `leftBracket`, `lightningBolt`, `mathMinus`, `mathMultiply`, `mathPlus`, `moon`, `plus`, `rightBrace`, `rightBracket`, `star4`, `star5`, `star6`, `star8`, `star10`, `star12`, `star16`, `sun`, `teardrop`
- Flowchart shapes: `flowChartAlternateProcess`, `flowChartCollate`, `flowChartConnector`, `flowChartData`, `flowChartDecision`, `flowChartDelay`, `flowChartDisplay`, `flowChartDocument`, `flowChartExtract`, `flowChartInputOutput`, `flowChartManualInput`, `flowChartManualOperation`, `flowChartMerge`, `flowChartOffpageConnector`, `flowChartOr`, `flowChartPreparation`, `flowChartProcess`, `flowChartPunchedCard`, `flowChartPunchedTape`, `flowChartSort`, `flowChartStoredData`, `flowChartSummingJunction`, `flowChartTerminator`

## Python API

```python
from drawingml_svg import drawingml_to_svg, svg_to_drawingml

dml = svg_to_drawingml("<svg viewBox='0 0 100 50'><rect x='5' y='5' width='40' height='20'/></svg>")
svg = drawingml_to_svg(dml)
```

```python
from drawingml_svg import analyze_svg

report = analyze_svg(svg_text).to_dict()
```

## Scope

This is intentionally conservative. Unsupported SVG elements are skipped, and unsupported DrawingML shapes are ignored. Cubic SVG paths and transformed non-rectilinear primitives are approximated as editable DrawingML polylines. The current unit conversion uses Office's common 96 DPI mapping:

```text
1 px = 9525 EMU
1 pt = 1.3333 px
1 pc = 16 px
1 in = 96 px
1 cm = 37.7953 px
1 mm = 3.7795 px
1 q = 0.9449 px
```

## License

MIT
