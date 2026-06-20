# Release checklist

Use this checklist when publishing a new `svgraph` release.

## Before tagging

- Confirm `CHANGELOG.md` has a dated section for the release and an empty `Unreleased` section for the next cycle.
- Confirm `pyproject.toml` and `package.json` have the intended version.
- Confirm the public GitHub repository and Pages URL are the canonical SVGraph locations:

```bash
gh repo view com-junkawasaki/svgraph --json nameWithOwner,description,isPrivate,visibility,url,homepageUrl,defaultBranchRef,repositoryTopics,licenseInfo
```

Expected values:

```text
nameWithOwner: com-junkawasaki/svgraph
description: SVG presentation graph toolkit for SVGraph, DrawingML, and PPTX conversion
isPrivate: false
visibility: PUBLIC
url: https://github.com/com-junkawasaki/svgraph
homepageUrl: https://com-junkawasaki.github.io/svgraph/
defaultBranchRef.name: main
repositoryTopics: drawingml, ooxml, pptx, presentationml, svg, svgraph, web-editor
licenseInfo.key: mit
licenseInfo.name: MIT License
```

- Smoke the published Pages site after deployment:

```bash
python - <<'PY'
from urllib.request import urlopen

html = urlopen("https://com-junkawasaki.github.io/svgraph/", timeout=20).read().decode("utf-8")
app_js = urlopen("https://com-junkawasaki.github.io/svgraph/app.js", timeout=20).read().decode("utf-8")
for expected in [
    "<title>SVGraph Editor</title>",
    'name="description"',
    'property="og:title" content="SVGraph Editor"',
    'property="og:url" content="https://com-junkawasaki.github.io/svgraph/"',
    'name="twitter:title" content="SVGraph Editor"',
    "https://com-junkawasaki.github.io/svgraph/",
    "Download SVG",
    "Download SVGraph",
    "Download Sidecar",
]:
    assert expected in html
for expected in [
    "SVGraph",
    "downloadSVGraphBtn",
    "svgraph-source.svg",
    "svgraph-sidecar.json",
    "svgraph-web.pptx",
]:
    assert expected in app_js
for forbidden in [
    "PPTX" + "SVG",
    "pptx" + "svg",
    "drawingml-" + "svg-web",
    "download" + "IrBtn",
    "download" + "Pptxsvg",
]:
    assert forbidden not in html
    assert forbidden not in app_js
PY
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
assert "License-Expression: MIT" in wheel_metadata
assert "License-File: LICENSE" in wheel_metadata
assert "Project-URL: Homepage, https://github.com/com-junkawasaki/svgraph" in wheel_metadata
assert "Project-URL: Repository, https://github.com/com-junkawasaki/svgraph" in wheel_metadata
assert "Project-URL: Documentation, https://com-junkawasaki.github.io/svgraph/" in wheel_metadata
assert "Project-URL: Issues, https://github.com/com-junkawasaki/svgraph/issues" in wheel_metadata
with tarfile.open(sdist_path) as sdist:
    names = set(sdist.getnames())
    root = next(name for name in names if name.endswith("/pyproject.toml")).rsplit("/", 1)[0]
    pyproject = tomllib.loads(sdist.extractfile(f"{root}/pyproject.toml").read().decode("utf-8"))
    web_package = json.loads(sdist.extractfile(f"{root}/package.json").read().decode("utf-8"))
    web_lock = json.loads(sdist.extractfile(f"{root}/package-lock.json").read().decode("utf-8"))
assert pyproject["project"]["name"] == "svgraph"
assert pyproject["project"]["description"] == "Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, and browser-only web editing."
assert {"svg", "svgraph", "drawingml", "presentationml", "pptx", "web"} <= set(pyproject["project"]["keywords"])
assert pyproject["project"]["urls"] == {
    "Homepage": "https://github.com/com-junkawasaki/svgraph",
    "Repository": "https://github.com/com-junkawasaki/svgraph",
    "Documentation": "https://com-junkawasaki.github.io/svgraph/",
    "Issues": "https://github.com/com-junkawasaki/svgraph/issues",
}
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
expected_version="svgraph $(tmp/release-venv/bin/python - <<'PY'
from importlib.metadata import version

print(version("svgraph"))
PY
)"
for command in \
  "tmp/release-venv/bin/python -m svgraph" \
  "tmp/release-venv/bin/svgraph" \
  "tmp/release-venv/bin/drawingml-svg" \
  "tmp/release-venv/bin/svg2dml" \
  "tmp/release-venv/bin/svg2pptx" \
  "tmp/release-venv/bin/dml2svg" \
  "tmp/release-venv/bin/drawingml-svg-analyze"
do
  actual_version="$($command --version)"
  test "$actual_version" = "$expected_version"
done
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
python - <<'PY'
import json
from pathlib import Path

presentation = json.loads(Path("tmp/release-svgraph-presentation.json").read_text(encoding="utf-8"))
part_types = {part["kind"]: part["content_type"] for part in presentation["parts"]}
assert presentation["kind"] == "svgraph-presentation"
assert presentation["slide_size"] == [1280.0, 720.0]
assert part_types["presentation"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
assert part_types["slide-master"] == "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"
assert part_types["slide-layout"] == "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"
assert part_types["theme"] == "application/vnd.openxmlformats-officedocument.theme+xml"
assert any(
    part["kind"] == "slide"
    and part["content_type"] == "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
    for part in presentation["parts"]
)
PY
tmp/release-venv/bin/svgraph svg2dml examples/sample.svg -o tmp/release-smoke.xml
tmp/release-venv/bin/svgraph svg2pptx examples/sample.svg -o tmp/release-smoke.pptx
python -m zipfile --test tmp/release-smoke.pptx
tmp/release-venv/bin/python - <<'PY'
import io
import zipfile

from svgraph.pptx import svg_to_pptx_bytes

svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <metadata>{"presentation":{"masters":[{"id":"brand"}],"layouts":[{"id":"title"}]}}</metadata>
  <g data-kind="slide-master"/>
  <g data-kind="slide-layout"/>
  <g data-kind="slide"><rect width="100" height="80"/></g>
  <g data-kind="slide"><ellipse cx="100" cy="80" rx="50" ry="30"/></g>
</svg>"""
with zipfile.ZipFile(io.BytesIO(svg_to_pptx_bytes(svg))) as pptx:
    assert pptx.testzip() is None
    names = set(pptx.namelist())
    assert "ppt/slideMasters/slideMaster2.xml" in names
    assert "ppt/slideLayouts/slideLayout2.xml" in names
    assert 'Target="../slideLayouts/slideLayout2.xml"' in pptx.read("ppt/slides/_rels/slide2.xml.rels").decode("utf-8")
PY
```

## Tag and publish

- Create an annotated tag named `vX.Y.Z`.
- Push the tag after CI passes on `main`.
- Attach the wheel and source distribution to the GitHub release.
- Include the changelog section for the release in the GitHub release notes.
