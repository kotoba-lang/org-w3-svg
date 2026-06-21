## Summary

-

## SVGraph impact

- [ ] SVGraph model or metadata changed
- [ ] SVGraph presentation/package projection changed
- [ ] SVG to DrawingML behavior changed
- [ ] DrawingML to SVG behavior changed
- [ ] PresentationML/PPTX export changed
- [ ] Analyzer behavior changed
- [ ] Browser editor or Pages artifact changed
- [ ] Documentation or project metadata only

## Testing

- [ ] `ruff check .`
- [ ] `npm ci`
- [ ] `npm run check:web`
- [ ] `npm run build:web`
- [ ] `npm run check:package`
- [ ] `git diff --exit-code docs/app.js`
- [ ] `git diff --exit-code docs/app.d.ts`
- [ ] `PYTHONPATH=src python -m pytest -q`
- [ ] `PYTHONPATH=src python -m svgraph analyze examples/coverage.svg`
- [ ] `PYTHONPATH=src python -m svgraph svgraph examples/svgraph.svg > tmp/svgraph.json`
- [ ] `PYTHONPATH=src python -m svgraph svgraph-presentation examples/svgraph.svg > tmp/svgraph-presentation.json`
- [ ] `PYTHONPATH=src python examples/make_pptx.py examples/coverage.svg -o tmp/svgraph-coverage.pptx`
- [ ] `python -m zipfile --test tmp/svgraph-coverage.pptx`

## Notes

If this adds DrawingML preset support, update the "Supported DrawingML presets" section in `README.md`.
