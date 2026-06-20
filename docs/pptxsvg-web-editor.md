# PPTXSVG Web Editor Design

## Goal

Build a browser-based editor for `pptxsvg`: an SVG-first presentation format where SVG remains the editable source of truth, `svg_to_ir()` exposes semantic structure, and `svg_to_pptx_ir()` provides the package-level plan for `.pptx` export.

The app should support:

- editing SVG visually and structurally
- editing metadata, `data-*`, dependencies, and slide semantics through the SVG IR
- previewing slide boundaries and package parts
- exporting PresentationML/PPTX from deterministic emitters
- running local Web LLM inference in the browser for semantic assistance, not for final conversion correctness

Current implementation status:

- `web/app.ts` is the TypeScript browser runtime.
- GitHub Pages loads the compiled `docs/app.js`.
- The browser can export `.pptx` without Python for the PPTXSVG MVP subset: multi-slide SVG groups, editable rect/ellipse/line/text shapes, polygon/polyline/quadratic/cubic path custom geometry, embedded data URI images, marker arrows, local `defs`/`use`, simple selector styles, inline style/inherited paint, basic transforms, relation connectors, and semantic tables.
- The Python converter remains the fuller reference implementation for complex SVG features such as paths, images, advanced CSS, clipping, markers, and richer table extraction.

## Product Shape

The first screen is the editor, not a landing page.

Primary panes:

- Canvas: live SVG rendering with slide overlays, selection handles, guides, connectors, and table/cell hints.
- Structure: SVG IR tree, node ids, `id`, `data-kind`, `data-role`, `data-bind`, dependencies, and warnings.
- Properties: geometry, paint, text, metadata, accessibility, table semantics, and slide settings.
- Slides: `pptxsvg` slide list, slide size, titles, notes, and package part mapping.
- Assistant: local WebGPU LLM panel for semantic suggestions and batch edits.
- Export: DrawingML fragment, PresentationML package plan, `.pptx`, SVG, and sidecar JSON.

## Architecture

```text
Browser UI
  |
  |-- SVG document model
  |     |-- raw SVG text
  |     |-- DOM tree
  |     |-- SvgIRDocument JSON
  |     |-- SvgIRPresentation JSON
  |
  |-- Workers
  |     |-- parser/analyzer worker
  |     |-- conversion/export worker
  |     |-- web-llm worker
  |
  |-- Storage
        |-- IndexedDB documents
        |-- IndexedDB model cache
        |-- File System Access API exports
```

The editor should not let the LLM directly mutate the raw document. LLM output is always a proposed patch against IR-level commands, then validated by deterministic code before applying.

## Core Data Model

Client-side state should keep four synchronized layers:

1. Raw SVG source.
2. Parsed SVG DOM.
3. `SvgIRDocument`.
4. `SvgIRPresentation`.

The app treats SVG as canonical. IR is derived and cached. UI actions should preferably emit structured edit operations and then serialize back to SVG:

```json
{
  "op": "set-data",
  "node_id": "n0.3.1",
  "name": "kind",
  "value": "table"
}
```

Recommended operation groups:

- `set-attribute`
- `set-style`
- `set-data`
- `set-metadata`
- `move-node`
- `group-nodes`
- `mark-slide`
- `mark-table`
- `mark-cell`
- `bind-relation`
- `set-reading-order`

Every operation should be reversible for undo/redo.

## PPTXSVG Workflow

### Import

1. User opens `.svg` or pastes SVG.
2. Parser validates XML and normalizes namespaces.
3. Analyzer reports unsupported visual features.
4. IR builder extracts metadata, `data-*`, dependencies, and `pptxsvg` presentation view.
5. UI overlays slide boundaries.

### Edit

1. Visual edits update SVG attributes.
2. Semantic edits update `data-*` or `<metadata>`.
3. Slide edits update `data-kind="slide"`, `data-title`, `viewBox`, or presentation metadata.
4. Table edits update semantic markers such as `data-kind="table"`, `data-kind="cell"`, `data-row`, and `data-col`.

### Preview

1. SVG preview uses browser rendering.
2. PPTX preview uses deterministic IR-to-PresentationML preview logic.
3. Warnings distinguish visual fallback from semantic loss.

### Export

Export targets:

- `svg`: canonical source.
- `ir.json`: full SVG IR.
- `pptxsvg.json`: presentation/package projection.
- `drawingml.xml`: current fragment converter output.
- `pptx`: full package emitter output.

The `.pptx` exporter should consume `SvgIRPresentation.parts` and generate package relationships, content types, presentation properties, slide XML, theme, layouts, and optional custom XML sidecar.

## Web LLM Integration

The Web LLM should run in a dedicated worker. Based on the referenced WebGPU browser guide, the default path should use Transformers.js with `device: "webgpu"` when `navigator.gpu` is available, and cache model files locally in browser storage after the first download.

Minimal worker loading shape:

```ts
import { pipeline } from "@huggingface/transformers";

const generator = await pipeline(
  "text-generation",
  "onnx-community/gemma-4-e2b-it-ONNX",
  {
    device: "webgpu",
    dtype: "q4",
  },
);
```

The app should support backend policy:

- `webgpu`: preferred for local text generation.
- `wasm`: fallback for small classification or environments without WebGPU.
- `disabled`: enterprise/privacy mode where AI is off.
- `remote`: optional future server-side provider, never required for core editing.

LLM responsibilities:

- infer likely slide titles from SVG text
- classify nodes into `data-kind` / `data-role`
- suggest slide boundaries
- detect table-like grids and propose table semantics
- infer relations between shapes and connectors
- generate speaker notes from visible text
- explain unsupported coverage warnings
- propose batch rename/group/order operations

LLM non-responsibilities:

- final SVG parsing
- final PresentationML generation
- security decisions
- applying edits without user approval
- silently rasterizing unsupported content

## Assistant Patch Protocol

Prompt context should be compact and IR-based:

```json
{
  "task": "suggest-slide-boundaries",
  "slide_size": [1280, 720],
  "nodes": [
    {"node_id": "n0.1", "tag": "g", "id": "cover", "text": "Quarterly Review"},
    {"node_id": "n0.2", "tag": "g", "id": "system", "children": 12}
  ],
  "constraints": {
    "output": "json-patch-ops",
    "allowed_ops": ["mark-slide", "set-data", "set-metadata"]
  }
}
```

Assistant output must be validated against a strict schema:

```json
{
  "summary": "Found two likely slides.",
  "ops": [
    {"op": "mark-slide", "node_id": "n0.1", "title": "Quarterly Review"},
    {"op": "mark-slide", "node_id": "n0.2", "title": "System"}
  ],
  "confidence": 0.82
}
```

The UI then shows a diff before applying.

## Security And Privacy

- Do not execute script from imported SVG.
- Sanitize SVG before preview; disable external resource loading by default.
- Keep local LLM prompts on-device unless the user enables a remote provider.
- Store documents and model cache in IndexedDB with clear user controls.
- Warn before exporting metadata/custom XML that may contain private information.
- Maintain a visible provenance panel for generated suggestions.

## Performance

The article notes that initial WebGPU model download can be hundreds of MB to multiple GB depending on quantization, with later loads served from local cache. Design implications:

- lazy-load the model only when the assistant panel is opened
- prefer quantized models for browser use
- stream tokens into the assistant panel
- keep parsing/conversion in separate workers so the canvas remains responsive
- cap prompt context to selected slide/subtree unless the user requests whole-deck analysis

## UI States

Important states:

- WebGPU unavailable
- model downloading
- model cached
- model loading
- generating
- low memory / model load failed
- patch pending review
- patch rejected by validator
- conversion warnings
- export succeeded

## Roadmap

### Phase 1: IR Editor

- SVG load/save
- IR tree view
- `pptxsvg` slide list
- analyzer warnings
- metadata/data-* inspector

### Phase 2: Deterministic Preview And Export

- DrawingML fragment export
- package part preview
- minimal `.pptx` emitter
- sidecar custom XML export

### Phase 3: Local Web LLM Assistant

- WebGPU capability check
- Transformers.js worker
- model cache UI
- slide-boundary suggestion
- table/relation inference
- schema-validated patch review

### Phase 4: Advanced Authoring

- table editor
- connector graph editor
- reading order and notes
- theme/layout editor
- round-trip `.pptx` package inspection

## Implementation Recommendation

Use a TypeScript frontend with:

- Vite or Next.js for the app shell
- React for editor UI
- Zustand or Redux Toolkit for undoable document state
- Web Workers for parsing/export and LLM
- IndexedDB through a typed wrapper
- SVG canvas as the primary editable surface
- WASM/Python package only for tests/build tooling, not runtime parsing in the browser

Keep `drawingml-svg` as the conversion core and publish the IR schema as stable JSON so the web editor, CLI, and future package emitter share the same contract.
