# drawingml-svg

`drawingml-svg` is a small, dependency-free converter between SVG and DrawingML shape fragments.

It targets the practical subset needed for generated Office graphics and simple round-trips:

- SVG: `rect`, `circle`, `ellipse`, `line`, `polygon`, `polyline`, linear/quadratic/cubic/arc `path`, `text`, simple `tspan`, link/group containers, and basic `switch` fallback selection
- DrawingML: preset geometry shapes, custom geometry paths, and text boxes under `p:sp`
- Geometry: position, size, percent geometry lengths, rounded rectangles, transformed line endpoints, horizontal/vertical flips for lines
- Images: embedded SVG `image` elements with base64 data URI sources
- Paint: SVG default fill/stroke/stroke-width/line-cap/line-join/miterlimit values, solid fill, stroke color, stroke width including zero-width no-line strokes, line cap/join/miter/custom dash, fill/stroke alpha including fully transparent no-fill/no-line paint, short/long alpha hex colors, CSS rgb/hsl color functions, named colors, `currentColor`, paint-server fallback colors, linear/radial gradient fallback
- Styling: inline presentation attributes, inline `style`, simple `<style>` rules for element/class/id, compound class, attribute selectors (`=`, `~=`, `|=`, `^=`, `$=`, `*=`), child, and descendant selectors, CSS specificity, and `!important` cascade priority
- Line markers: `marker-start` and `marker-end` arrow markers are converted to DrawingML line arrows
- Coordinate systems: root, nested SVG, and symbol `viewBox` normalization with `preserveAspectRatio` support
- Visibility: `display:none` and `visibility:hidden` are skipped during conversion and analysis
- Clipping: rectangular `clipPath` on `rect` and `text` is converted as bounding-box intersection, including `userSpaceOnUse` and `objectBoundingBox` units
- Analysis: unsupported visual/layout attributes such as filters, masks, fill/clip rules, paint order, vector effects, multi-value text rotation, text/path length adjustments, unsupported markers, and unresolved paint servers are reported
- Transforms: inherited `transform` on elements and groups for `matrix`, `translate`, `scale`, `rotate`, `skewX`, `skewY`
- Reuse: local `defs`/`use` expansion for referenced shapes, groups, and basic `symbol viewBox` scaling, with unsupported missing/external use references reported by the analyzer
- Text: basic font size, weight, italic style, font family, underline/strike decoration, horizontal/vertical anchor, `xml:space="preserve"`, single-value `rotate`, `dx`/`dy` positioning, first-`tspan` positioning fallback, and multi-line `tspan` extraction

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
