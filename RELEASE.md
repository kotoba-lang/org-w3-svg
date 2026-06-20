# Release checklist

Use this checklist when publishing a new `svgraph` release.

## Before tagging

- Confirm `CHANGELOG.md` has a dated section for the release and an empty `Unreleased` section for the next cycle.
- Confirm `pyproject.toml` and `package.json` have the intended version.
- Run the local checks from `CONTRIBUTING.md`.
- Rebuild the browser editor artifact and confirm the committed Pages output is current:

```bash
npm ci
npm run check:web
npm run build:web
git diff --exit-code docs/app.js
```

- Regenerate and inspect the PPTX smoke fixture:

```bash
PYTHONPATH=src python examples/make_pptx.py examples/coverage.svg -o tmp/svgraph-coverage.pptx
python -m zipfile --test tmp/svgraph-coverage.pptx
PYTHONPATH=src python examples/make_pptx.py examples/complex.svg -o tmp/svgraph-complex.pptx
python -m zipfile --test tmp/svgraph-complex.pptx
```

- Build the source distribution and wheel:

```bash
python -m build --sdist --wheel -o tmp/dist
test -f tmp/dist/svgraph-*.tar.gz
test -f tmp/dist/svgraph-*.whl
python - <<'PY'
import glob
import tarfile
import zipfile

wheel_path = glob.glob("tmp/dist/svgraph-*.whl")[0]
sdist_path = glob.glob("tmp/dist/svgraph-*.tar.gz")[0]
with zipfile.ZipFile(wheel_path) as wheel:
    metadata_name = next(name for name in wheel.namelist() if name.endswith(".dist-info/METADATA"))
    wheel_metadata = wheel.read(metadata_name).decode("utf-8")
assert "Name: svgraph" in wheel_metadata
assert "Summary: Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, and browser-only web editing." in wheel_metadata
assert "Keywords: drawingml,svg,svgraph,presentationml,ooxml,pptx,web,converter" in wheel_metadata
with tarfile.open(sdist_path) as sdist:
    names = set(sdist.getnames())
root = next(name for name in names if name.endswith("/pyproject.toml")).rsplit("/", 1)[0]
for expected in [
    "docs/index.html",
    "docs/app.js",
    "docs/.nojekyll",
    "docs/svgraph-web-editor.md",
    "examples/__init__.py",
    "examples/complex.svg",
    "examples/coverage.svg",
    "examples/make_pptx.py",
    "examples/sample.svg",
    "examples/svgraph.svg",
    "web/app.ts",
    "package.json",
    "package-lock.json",
    "tsconfig.web.json",
]:
    assert f"{root}/{expected}" in names
PY
```

- Install the wheel in a clean virtual environment and run CLI smoke checks:

```bash
python -m venv tmp/release-venv
tmp/release-venv/bin/python -m pip install tmp/dist/svgraph-*.whl
tmp/release-venv/bin/python -m svgraph --version
tmp/release-venv/bin/svgraph --version
tmp/release-venv/bin/drawingml-svg --version
tmp/release-venv/bin/python - <<'PY'
import svgraph
from svgraph import svg_to_svgraph, svg_to_svgraph_presentation

assert svgraph.svg_to_svgraph is svg_to_svgraph
assert svgraph.svg_to_svgraph_presentation is svg_to_svgraph_presentation
assert "svg_to_svgraph" in svgraph.__all__
assert "svg_to_" + "ir" not in svgraph.__all__
assert svg_to_svgraph("<svg><rect data-kind='table'/></svg>").kind == "svgraph"
PY
tmp/release-venv/bin/svgraph analyze examples/coverage.svg
tmp/release-venv/bin/svgraph examples/svgraph.svg > tmp/release-svgraph.json
tmp/release-venv/bin/drawingml-svg examples/svgraph.svg > tmp/release-legacy-svgraph.json
tmp/release-venv/bin/svgraph svgraph-presentation examples/svgraph.svg > tmp/release-svgraph-presentation.json
tmp/release-venv/bin/svgraph svg2dml examples/sample.svg -o tmp/release-smoke.xml
tmp/release-venv/bin/svgraph svg2pptx examples/sample.svg -o tmp/release-smoke.pptx
python -m zipfile --test tmp/release-smoke.pptx
```

## Tag and publish

- Create an annotated tag named `vX.Y.Z`.
- Push the tag after CI passes on `main`.
- Attach the wheel and source distribution to the GitHub release.
- Include the changelog section for the release in the GitHub release notes.
