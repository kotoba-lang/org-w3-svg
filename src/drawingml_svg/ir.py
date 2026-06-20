"""Legacy import path and pre-SVGraph aliases."""

import warnings

from .svgraph import (
    SVGraphDependency,
    SVGraphDocument,
    SVGraphGuide,
    SVGraphNode,
    SVGraphPackagePart,
    SVGraphPresentation,
    SVGraphRuler,
    SVGraphSlide,
    SVGraphTemplate,
    SVGraphTextStyle,
    svg_svgraph_presentation_to_json,
    svg_svgraph_to_json,
    svg_to_svgraph,
    svg_to_svgraph_presentation,
)

SvgIRDocument = SVGraphDocument
SvgIRNode = SVGraphNode
SvgIRDependency = SVGraphDependency
SvgIRPresentation = SVGraphPresentation
SvgIRSlide = SVGraphSlide
SvgIRPackagePart = SVGraphPackagePart
SvgIRTemplate = SVGraphTemplate
SvgIRGuide = SVGraphGuide
SvgIRRuler = SVGraphRuler
SvgIRTextStyle = SVGraphTextStyle


def svg_to_ir(svg_text: str) -> SVGraphDocument:
    """Legacy alias for :func:`drawingml_svg.svgraph.svg_to_svgraph`."""

    _warn_legacy("svg_to_ir()", "drawingml_svg.svgraph.svg_to_svgraph()")
    return svg_to_svgraph(svg_text)


def svg_to_pptx_ir(svg_text: str) -> SVGraphPresentation:
    """Legacy alias for :func:`drawingml_svg.svgraph.svg_to_svgraph_presentation`."""

    _warn_legacy("svg_to_pptx_ir()", "drawingml_svg.svgraph.svg_to_svgraph_presentation()")
    return svg_to_svgraph_presentation(svg_text)


def svg_ir_to_json(svg_text: str) -> str:
    _warn_legacy("svg_ir_to_json()", "drawingml_svg.svgraph.svg_svgraph_to_json()")
    return svg_svgraph_to_json(svg_text)


def svg_pptx_ir_to_json(svg_text: str) -> str:
    _warn_legacy("svg_pptx_ir_to_json()", "drawingml_svg.svgraph.svg_svgraph_presentation_to_json()")
    return svg_svgraph_presentation_to_json(svg_text)


def _warn_legacy(name: str, replacement: str) -> None:
    warnings.warn(
        f"{name} is deprecated; use {replacement}.",
        DeprecationWarning,
        stacklevel=2,
    )


__all__ = [
    "SVGraphDependency",
    "SVGraphDocument",
    "SVGraphGuide",
    "SVGraphNode",
    "SVGraphPackagePart",
    "SVGraphPresentation",
    "SVGraphRuler",
    "SVGraphSlide",
    "SVGraphTemplate",
    "SVGraphTextStyle",
    "SvgIRDependency",
    "SvgIRDocument",
    "SvgIRGuide",
    "SvgIRNode",
    "SvgIRPackagePart",
    "SvgIRPresentation",
    "SvgIRRuler",
    "SvgIRSlide",
    "SvgIRTemplate",
    "SvgIRTextStyle",
    "svg_ir_to_json",
    "svg_pptx_ir_to_json",
    "svg_svgraph_presentation_to_json",
    "svg_svgraph_to_json",
    "svg_to_ir",
    "svg_to_pptx_ir",
    "svg_to_svgraph",
    "svg_to_svgraph_presentation",
]
