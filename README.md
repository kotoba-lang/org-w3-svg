# svg

`kotoba-lang/svg` is the EDN-first Clojure/ClojureScript substrate for SVG
documents.

It is intentionally separate from the SVG-era browser/Office converter restored
as `com-junkawasaki/svgraph`. This repo keeps SVG as small portable data:
Hiccup-like vectors, plain EDN maps, deterministic rendering, and light
validation helpers that other kotoba libraries can consume without Node,
Python, browser APIs, or Office-specific dependencies.

## Usage

```clojure
(require '[svg.core :as svg])

(def doc
  (svg/svg {:viewBox "0 0 120 40"}
    [:rect {:x 0 :y 0 :width 120 :height 40 :fill "#111827"}]
    [:text {:x 12 :y 25 :fill "white"} "kotoba"]))

(svg/render doc)
;; => "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 120 40\">..."
```

## Scope

- EDN shape: `[:tag {:attr value} child ...]`
- Deterministic XML rendering with escaping
- `style` map rendering
- namespace normalization for root `svg`
- basic tree walking and element validation

Out of scope: DrawingML, PPTX, browser editor, SVGraph presentation IR, and
Office causal sidecars. Those live in `com-junkawasaki/svgraph` and
`com-junkawasaki/office-causal`.

## Test

```bash
clojure -M:test
```

## License

MIT
