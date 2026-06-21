# Migrating to SVGraph

SVGraph is the canonical project name for the repository, Python distribution, import package, CLI, browser editor, schema, generated artifacts, and presentation metadata.

Legacy names remain only as compatibility surfaces. New code should use the SVGraph names below.

## Name Mapping

| Legacy surface | Canonical SVGraph surface |
| --- | --- |
| `com-junkawasaki/drawingml-svg` | `com-junkawasaki/svgraph` |
| `drawingml-svg` Python distribution | `svgraph` Python distribution |
| `drawingml_svg` import package | `svgraph` import package |
| `drawingml_svg.converter` | `svgraph.converter` |
| `drawingml_svg.coverage` | `svgraph.coverage` |
| `drawingml_svg.pptx` | `svgraph.pptx` |
| `drawingml_svg.svgraph` | `svgraph.model` |
| `drawingml_svg.ir.svg_to_ir()` | `svgraph.model.svg_to_svgraph()` |
| `drawingml_svg.ir.svg_to_pptx_ir()` | `svgraph.model.svg_to_svgraph_presentation()` |
| `ir` CLI command | `svgraph` CLI command |
| `pptxsvg` CLI command | `svgraph-presentation` CLI command |
| `drawingml-svg` executable | `svgraph` executable |
| `drawingml-svg-analyze` executable | `svgraph analyze` command |
| `svg2dml` executable | `svgraph svg2dml` command |
| `dml2svg` executable | `svgraph dml2svg` command |
| `svg2pptx` executable | `svgraph svg2pptx` command |

Retained legacy executable aliases emit deprecation warnings that point to their canonical SVGraph commands when used for conversions. They remain available for compatibility smoke tests and existing automation.

## Python Imports

Use the canonical package for new code:

```python
from svgraph import (
    analyze_svg,
    drawingml_to_svg,
    svg_to_drawingml,
    svg_to_pptx,
    svg_to_pptx_bytes,
    svg_to_svgraph,
    svg_to_svgraph_presentation,
)
```

The `drawingml_svg` package remains installable for existing callers, but its main modules are compatibility wrappers over `svgraph`. Those main modules re-export the canonical module `__all__` values so star imports keep the same public surface as `svgraph`. Deprecated pre-SVGraph IR APIs continue to emit `DeprecationWarning` and point callers to `svgraph.model`. The legacy `drawingml_svg.ir` module intentionally exports only pre-SVGraph `SvgIR*` aliases; import canonical `SVGraph*` types from `svgraph.model`.

## CLI

Use `svgraph` as the executable and command namespace:

```bash
svgraph svg2dml input.svg -o shape.xml
svgraph svg2pptx deck.svg -o deck.pptx
svgraph analyze input.svg
svgraph input.svg
svgraph svgraph-presentation input.svg
python -m svgraph --version
```

Legacy executable and command aliases are retained for compatibility smoke tests and existing automation, not as documentation targets for new integrations.

## Generated Artifacts

Generated files should use `svgraph` naming:

```bash
PYTHONPATH=src python examples/make_pptx.py examples/sample.svg -o tmp/svgraph-sample.pptx
svgraph examples/svgraph.svg > tmp/release-svgraph.json
svgraph svgraph-presentation examples/svgraph.svg > tmp/release-svgraph-presentation.json
```

The browser editor is published at:

```text
https://com-junkawasaki.github.io/svgraph/
```

The browser npm package is published through GitHub Packages as:

```bash
npm install @com-junkawasaki/svgraph --registry=https://npm.pkg.github.com
```

It also exposes a TypeScript/browser-runtime CLI with a Node XML DOM shim:

```bash
npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2dml input.svg -o shape.xml
npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- dml2svg shape.xml -o shape.svg
npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2pptx deck.svg -o deck.pptx
```

## Verification

Run the migration guard tests before publishing:

```bash
find src -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +
rm -rf build tmp/dist
ruff check .
npm ci
npm run check:web
npm run build:web
npm run check:package
git diff --exit-code docs/app.js
git diff --exit-code docs/app.d.ts
PYTHONPATH=src python -m pytest -q tests/test_migration.py tests/test_svgraph.py
```

The full test suite also validates that public links, package metadata, wheel and sdist artifact names, CLI smoke checks, browser editor artifacts, and packaged documentation stay on SVGraph naming.
