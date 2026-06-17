# drawingml-svg

`drawingml-svg` is a small, dependency-free converter between SVG and DrawingML shape fragments.

It targets the practical subset needed for generated Office graphics and simple round-trips:

- SVG: `rect`, `circle`, `ellipse`, `line`, `polygon`, `polyline`, linear/quadratic/cubic/arc `path`, `text`, simple `tspan`
- DrawingML: preset geometry shapes, custom geometry paths, and text boxes under `p:sp`
- Geometry: position, size, rounded rectangles, line endpoints, horizontal/vertical flips for lines
- Images: embedded SVG `image` elements with base64 data URI sources
- Paint: solid fill, stroke color, stroke width, line cap/join/miter/dash, fill/stroke alpha, CSS color functions, named colors, gradient fallback
- Styling: inline presentation attributes, inline `style`, simple `<style>` rules for element/class/id, compound class, child, and descendant selectors
- Line markers: `marker-start` and `marker-end` arrow markers are converted to DrawingML line arrows
- Coordinate systems: root and symbol `viewBox` normalization with `preserveAspectRatio` support
- Visibility: `display:none` and `visibility:hidden` are skipped during conversion and analysis
- Clipping: rectangular `clipPath` on `rect` and `text` is converted as bounding-box intersection, including `userSpaceOnUse` and `objectBoundingBox` units
- Transforms: inherited `transform` on elements and groups for `matrix`, `translate`, `scale`, `rotate`, `skewX`, `skewY`
- Reuse: local `defs`/`use` expansion for referenced shapes, groups, and basic `symbol viewBox` scaling
- Text: basic font size, weight, italic style, anchor, first-`tspan` positioning fallback, and multi-line `tspan` extraction

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
```

## License

MIT
