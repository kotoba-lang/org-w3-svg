# drawingml-svg

`drawingml-svg` is a small, dependency-free converter between SVG and DrawingML shape fragments.

It targets the practical subset needed for generated Office graphics and simple round-trips:

- SVG: `rect`, `circle`, `ellipse`, `line`, `polygon`, `polyline`, linear/quadratic/cubic/arc `path`, `text`, simple `tspan`, link/group containers, and basic `switch` fallback selection
- DrawingML: preset geometry shapes, custom geometry paths including line/quadratic/cubic segments, and text boxes under `p:sp`, with invalid numeric DrawingML attributes ignored where possible
- Geometry: position, size, CSS geometry properties, percent geometry lengths, rounded rectangles, transformed line endpoints, horizontal/vertical flips for lines, and DrawingML line/custom-geometry transform round-trips
- Images: embedded SVG `image` elements with valid base64 PNG/JPEG/GIF/WebP data URI sources, opacity, and legacy `xlink:href`
- Paint: SVG default fill/stroke/stroke-width/line-cap/line-join/miterlimit values, transform-scaled shape and text-outline strokes, `vector-effect="non-scaling-stroke"`, solid fill, stroke color, stroke width including zero-width no-line strokes and percentage widths, line cap/join/miter/custom dash, DrawingML preset dash fallback, DrawingML RGB/scheme color fallback with luminance modifiers, dash-offset approximation for offsets that start inside a dash segment, fill/stroke alpha including fully transparent no-fill/no-line paint, short/long alpha hex colors, CSS rgb/hsl color functions, named colors, `currentColor`, `context-fill`/`context-stroke`, inherited paint values, paint-server fallback colors, CSS-colored linear/radial gradient fallback, and representative pattern fallback colors
- Styling: inline presentation attributes, inline `style`, simple `<style>` rules for element/class/id, compound class, attribute selectors (`=`, `~=`, `|=`, `^=`, `$=`, `*=`), child, and descendant selectors, CSS specificity, `inherit`/`initial`/`unset`, and `!important` cascade priority
- Line markers: `marker-start`, `marker-end`, and `marker` shorthand arrow markers are converted to DrawingML line arrows for lines and open two-end paths/polylines
- Coordinate systems: root, nested SVG, and symbol `viewBox` normalization with `preserveAspectRatio` support
- Visibility: `display:none` and `visibility:hidden` are skipped during conversion and analysis
- Clipping: rectangular `clipPath` on `rect`, `text`, and embedded `image` is converted as bounding-box intersection, including `userSpaceOnUse` and `objectBoundingBox` units
- Analysis: unsupported visual/layout attributes such as filters, masks, blend/isolation, fill/clip rules, paint order, unsupported vector effects, word spacing conflicts, dash offsets that cannot be approximated, multi-value text rotation, unsupported text/path length adjustments, unsupported markers, and unresolved paint servers are reported, while default no-op values and rendering quality hints are ignored
- Transforms: inherited SVG `transform` on elements and groups for `matrix`, `translate`, `scale`, `rotate`, `skewX`, `skewY`, plus DrawingML rotation/flip output as SVG transforms for supported shapes
- Reuse: local `defs`/`use` expansion for referenced shapes, groups, and basic `symbol viewBox` scaling, including legacy `xlink:href`, with unsupported missing/external use references reported by the analyzer
- Text: basic font size, weight, italic style, font family, `small-caps` and `all-small-caps` font variants, inherited and per-`tspan` `text-transform`, text fill/no-fill, text outline color/width/cap/join/dash/miter, underline/strike decoration, horizontal/vertical anchor, `xml:space="preserve"`, single-value `rotate`, `letter-spacing`, simple `word-spacing`, `textLength` spacing adjustment, approximate `spacingAndGlyphs`, `dx`/`dy` positioning, first-`tspan` positioning fallback, multi-line `tspan` extraction, and multiple DrawingML paragraph extraction

The converter accepts fragments, not complete `.pptx` or `.docx` packages. It is intended as a reusable core that can later be wrapped by OOXML package readers/writers.

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
```

`dml2svg` and `svg2dml` are also installed as aliases.

## PPTX smoke test

The repository includes a small example that embeds converted DrawingML shapes into a one-slide `.pptx` package:

```bash
PYTHONPATH=src python examples/make_pptx.py examples/sample.svg -o tmp/drawingml-svg-sample.pptx
```

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
