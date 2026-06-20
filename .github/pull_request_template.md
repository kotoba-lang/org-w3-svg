## Summary

-

## Converter impact

- [ ] SVG to DrawingML behavior changed
- [ ] DrawingML to SVG behavior changed
- [ ] Analyzer behavior changed
- [ ] Documentation or project metadata only

## Testing

- [ ] `ruff check .`
- [ ] `npm ci`
- [ ] `npm run check:web`
- [ ] `npm run build:web`
- [ ] `git diff --exit-code docs/app.js`
- [ ] `PYTHONPATH=src python -m pytest -q`
- [ ] `PYTHONPATH=src python -m svgraph analyze examples/coverage.svg`
- [ ] `PYTHONPATH=src python -m svgraph svgraph examples/svgraph.svg > tmp/svgraph.json`
- [ ] `PYTHONPATH=src python -m svgraph svgraph-presentation examples/svgraph.svg > tmp/svgraph-presentation.json`
- [ ] `PYTHONPATH=src python examples/make_pptx.py examples/coverage.svg -o tmp/svgraph-coverage.pptx`
- [ ] `python -m zipfile --test tmp/svgraph-coverage.pptx`

## Notes

If this adds DrawingML preset support, update the "Supported DrawingML presets" section in `README.md`.
