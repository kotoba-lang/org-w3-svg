# Release checklist

Use this checklist when publishing a new `svgraph` release.

## Before tagging

- Confirm `CHANGELOG.md` has a dated section for the release and an empty `Unreleased` section for the next cycle.
- Confirm `pyproject.toml` and `package.json` have the intended version.
- Confirm the public GitHub repository and Pages URL are the canonical SVGraph locations:

```bash
gh repo view com-junkawasaki/svgraph --json nameWithOwner,isPrivate,visibility,url,homepageUrl,defaultBranchRef,repositoryTopics
```

Expected values:

```text
nameWithOwner: com-junkawasaki/svgraph
isPrivate: false
visibility: PUBLIC
url: https://github.com/com-junkawasaki/svgraph
homepageUrl: https://com-junkawasaki.github.io/svgraph/
defaultBranchRef.name: main
repositoryTopics: drawingml, ooxml, pptx, presentationml, svg, svgraph, web-editor
```

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
find src -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +
rm -rf build tmp/dist
python -m pip install -e ".[dev]"
python -m build --sdist --wheel -o tmp/dist
test -f tmp/dist/svgraph-*.tar.gz
test -f tmp/dist/svgraph-*.whl
python - <<'PY'
import glob
import json
import tarfile
import tomllib
import zipfile

wheel_path = glob.glob("tmp/dist/svgraph-*.whl")[0]
sdist_path = glob.glob("tmp/dist/svgraph-*.tar.gz")[0]
with zipfile.ZipFile(wheel_path) as wheel:
    wheel_names = set(wheel.namelist())
    metadata_name = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
    wheel_metadata = wheel.read(metadata_name).decode("utf-8")
for expected in [
    "drawingml_svg/__init__.py",
    "drawingml_svg/cli.py",
    "drawingml_svg/converter.py",
    "drawingml_svg/coverage.py",
    "drawingml_svg/ir.py",
    "drawingml_svg/pptx.py",
    "drawingml_svg/py.typed",
    "drawingml_svg/svgraph.py",
    "svgraph/__init__.py",
    "svgraph/__main__.py",
    "svgraph/cli.py",
    "svgraph/converter.py",
    "svgraph/coverage.py",
    "svgraph/model.py",
    "svgraph/pptx.py",
    "svgraph/py.typed",
]:
    assert expected in wheel_names
assert "Name: svgraph" in wheel_metadata
assert "Summary: Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, and browser-only web editing." in wheel_metadata
assert "Keywords: drawingml,svg,svgraph,presentationml,ooxml,pptx,web,converter" in wheel_metadata
assert "Project-URL: Documentation, https://com-junkawasaki.github.io/svgraph/" in wheel_metadata
with tarfile.open(sdist_path) as sdist:
    names = set(sdist.getnames())
    root = next(name for name in names if name.endswith("/pyproject.toml")).rsplit("/", 1)[0]
    pyproject = tomllib.loads(sdist.extractfile(f"{root}/pyproject.toml").read().decode("utf-8"))
    web_package = json.loads(sdist.extractfile(f"{root}/package.json").read().decode("utf-8"))
    web_lock = json.loads(sdist.extractfile(f"{root}/package-lock.json").read().decode("utf-8"))
assert pyproject["project"]["name"] == "svgraph"
assert pyproject["project"]["description"] == "Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, and browser-only web editing."
assert {"svg", "svgraph", "drawingml", "presentationml", "pptx", "web"} <= set(pyproject["project"]["keywords"])
assert web_package["name"] == "svgraph-web"
assert web_package["version"] == pyproject["project"]["version"]
assert web_package["description"] == "Browser-only SVGraph editor and SVG to PresentationML/PPTX converter."
assert {"svg", "svgraph", "presentationml", "pptx", "web"} <= set(web_package["keywords"])
assert web_package["homepage"] == "https://com-junkawasaki.github.io/svgraph/"
assert web_package["private"] is True
assert web_package["license"] == "MIT"
assert web_lock["name"] == web_package["name"]
assert web_lock["version"] == web_package["version"]
assert web_lock["packages"][""]["name"] == web_package["name"]
assert web_lock["packages"][""]["version"] == web_package["version"]
assert web_lock["packages"][""]["license"] == web_package["license"]
for expected in [
    "README.md",
    "LICENSE",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "MIGRATION.md",
    "RELEASE.md",
    "SECURITY.md",
    "package.json",
    "package-lock.json",
    "tsconfig.web.json",
    "docs/.nojekyll",
    "docs/adr/0001-svgraph.md",
    "docs/index.html",
    "docs/app.js",
    "docs/svgraph-web-editor.md",
    "examples/__init__.py",
    "examples/complex.svg",
    "examples/coverage.svg",
    "examples/make_pptx.py",
    "examples/sample.svg",
    "examples/svgraph.svg",
    "web/app.ts",
    "src/drawingml_svg/__init__.py",
    "src/drawingml_svg/cli.py",
    "src/drawingml_svg/converter.py",
    "src/drawingml_svg/coverage.py",
    "src/drawingml_svg/ir.py",
    "src/drawingml_svg/pptx.py",
    "src/drawingml_svg/py.typed",
    "src/drawingml_svg/svgraph.py",
    "src/svgraph/__init__.py",
    "src/svgraph/__main__.py",
    "src/svgraph/cli.py",
    "src/svgraph/converter.py",
    "src/svgraph/coverage.py",
    "src/svgraph/model.py",
    "src/svgraph/pptx.py",
    "src/svgraph/py.typed",
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
tmp/release-venv/bin/svg2dml --version
tmp/release-venv/bin/svg2pptx --version
tmp/release-venv/bin/dml2svg --version
tmp/release-venv/bin/drawingml-svg-analyze --version
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
