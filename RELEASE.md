# Release checklist

Use this checklist when publishing a new `drawingml-svg` release.

## Before tagging

- Confirm `CHANGELOG.md` has a dated section for the release and an empty `Unreleased` section for the next cycle.
- Confirm `pyproject.toml` has the intended version.
- Run the local checks from `CONTRIBUTING.md`.
- Regenerate and inspect the PPTX smoke fixture:

```bash
PYTHONPATH=src python examples/make_pptx.py examples/coverage.svg -o tmp/drawingml-svg-coverage.pptx
python -m zipfile --test tmp/drawingml-svg-coverage.pptx
PYTHONPATH=src python examples/make_pptx.py examples/complex.svg -o tmp/drawingml-svg-complex.pptx
python -m zipfile --test tmp/drawingml-svg-complex.pptx
```

- Build the source distribution and wheel:

```bash
python -m build --sdist --wheel -o tmp/dist
```

- Install the wheel in a clean virtual environment and run CLI smoke checks:

```bash
python -m venv tmp/release-venv
tmp/release-venv/bin/python -m pip install tmp/dist/drawingml_svg-*.whl
tmp/release-venv/bin/drawingml-svg --version
tmp/release-venv/bin/drawingml-svg analyze examples/coverage.svg
tmp/release-venv/bin/drawingml-svg svgraph examples/svgraph.svg > tmp/release-svgraph.json
tmp/release-venv/bin/drawingml-svg svgraph-presentation examples/svgraph.svg > tmp/release-svgraph-presentation.json
tmp/release-venv/bin/svg2dml examples/sample.svg -o tmp/release-smoke.xml
```

## Tag and publish

- Create an annotated tag named `vX.Y.Z`.
- Push the tag after CI passes on `main`.
- Attach the wheel and source distribution to the GitHub release.
- Include the changelog section for the release in the GitHub release notes.
