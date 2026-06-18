# Changelog

All notable changes to this project are documented here.

This project follows a simple, human-readable changelog. Until the project reaches a stable release cadence, unreleased changes are collected under `Unreleased`.

## Unreleased

- Added OSS project guidance, including contributing, security, code of conduct, issue templates, PR template, and README status links.
- Added Dependabot configuration for GitHub Actions and Python dependency update pull requests.
- Added a release checklist covering changelog, version, local checks, PPTX smoke verification, wheel smoke checks, and GitHub release notes.
- Expanded DrawingML preset coverage for common polygons, arrows, symbols, flowchart shapes, ribbons, callouts, and action buttons.
- Added CLI `--version` support for the main command and console-script aliases.
- Strengthened CI with Python 3.11 through 3.14, analyzer fixtures, PPTX smoke generation, wheel smoke tests, and sdist metadata checks.
- Added README documentation for supported DrawingML preset geometries.
- Expanded rectangular SVG `clipPath` conversion and analyzer support to ellipse/circle, line, and two-point open path/polyline fixtures.
- Added complex SVG fixture PPTX smoke coverage to CI and the release checklist.
- Added text-level SVG `baseline-shift` `super`/`sub` conversion to DrawingML run baseline values.
- Added run-level `tspan` fill/font/outline/decoration/letter-spacing/baseline conversion to separate DrawingML text runs.
- Added run-level `tspan` word-spacing conversion using DrawingML character spacing approximation.
- Added DrawingML rich text run extraction to SVG `tspan` styles for fill/font/outline/decoration/letter-spacing/baseline round trips.
- Added first-positioned SVG `tspan` `text-anchor` fallback conversion and analyzer support.
- Added first-positioned SVG `tspan` baseline fallback conversion and analyzer support.
- Added percentage SVG `transform-origin` conversion and analyzer support for elements with a resolvable reference box.
- Added keyword SVG `transform-origin` conversion and analyzer support for elements with a resolvable reference box.
- Added SVG underline `text-decoration-style` conversion and analyzer support for dashed, dotted, double, and wavy styles.
- Added SVG `text-decoration` shorthand style extraction for supported underline styles.
- Added SVG `stroke-linejoin="miter-clip"` conversion and analyzer support as a DrawingML miter approximation.
- Refined analyzer handling for marker-only `paint-order` changes that have no visible effect without markers.
- Refined analyzer handling for `text-decoration-color` values that match the visible text fill.
- Refined analyzer handling for zero-valued SVG `kerning` attributes.
- Refined analyzer handling for `pathLength` on shapes without a visible dashed stroke.
- Refined analyzer handling for default `currentColor` text decoration colors.
- Refined analyzer handling for `text-decoration` shorthand color tokens that match visible text fill.
- Refined analyzer handling for `text-decoration` shorthand `rgb(...)` color functions that match visible text fill.
- Refined analyzer handling for additional `text-decoration` shorthand color functions such as `rgba(...)` and `hsl(...)`.
- Added analyzer reporting for unsupported visible SVG `text-decoration-thickness` values.
- Added analyzer reporting for unsupported visible SVG `text-underline-offset` and `text-decoration-skip-ink` values.
- Refined analyzer handling for no-op `auto` thickness tokens in SVG `text-decoration` shorthand.
- Refined analyzer handling for normal-equivalent SVG `font-size-adjust` values.
- Refined analyzer handling for SVG kerning attributes on single-character text.
- Refined analyzer handling for run-level `tspan` `text-anchor` values that do not create a positioned text chunk.
- Refined analyzer handling for normal-equivalent percentage SVG `font-stretch` values.
- Refined analyzer handling for zero-equivalent SVG glyph orientation angles.
- Refined analyzer handling for zero-equivalent SVG `baseline-shift` length and percentage values.

## 0.1.0

- Initial public alpha package for converting between SVG and DrawingML shape fragments.
- Included CLI commands for `svg2dml`, `dml2svg`, and SVG coverage analysis.
