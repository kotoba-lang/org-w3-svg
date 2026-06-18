from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .converter import (
    CssRule,
    _alpha_value,
    _collect_css,
    _collect_refs,
    _computed_style,
    _data_image_dimensions,
    _clip_path_is_supported,
    _dominant_baseline,
    _href,
    _is_display_none,
    _is_visibility_hidden,
    _length,
    _local_name,
    _marker_is_supported,
    _matrix_multiply,
    _optional_length,
    _paint_server_value,
    _parse_linear_path,
    _parse_points,
    _preserve_aspect_ratio,
    _previous_element_siblings,
    _root_viewbox_matrix,
    _style_transform_matrix,
    _supported_data_image,
    _svg_paint,
    _svg_text_content,
    _svg_text_length_spacing_is_supported,
    _svg_word_spacing_is_supported,
    _svg_dasharray_numbers,
    _svg_dashoffset_is_supported,
    _svg_linecap,
    _svg_linejoin,
    _svg_rotation_values,
    _transform_origin,
    _switch_selected_child,
    _url_ref,
    _viewport_size,
)

SUPPORTED_ELEMENTS = {
    "a",
    "circle",
    "ellipse",
    "g",
    "image",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "style",
    "switch",
    "use",
    "svg",
    "symbol",
    "text",
    "tspan",
}

IGNORED_ELEMENTS = {"defs", "desc", "linearGradient", "metadata", "pattern", "radialGradient", "stop", "title"}
GRADIENT_ELEMENTS = {"linearGradient", "radialGradient", "stop"}

UNSUPPORTED_ATTRIBUTES = {
    "alignment-baseline",
    "direction",
    "clip-path",
    "clip-rule",
    "color-rendering",
    "fill-rule",
    "filter",
    "font-feature-settings",
    "font-kerning",
    "font-size-adjust",
    "font-stretch",
    "font-variant",
    "font-variation-settings",
    "glyph-orientation-horizontal",
    "glyph-orientation-vertical",
    "gradientTransform",
    "gradientUnits",
    "image-rendering",
    "isolation",
    "kerning",
    "letter-spacing",
    "lengthAdjust",
    "marker",
    "marker-end",
    "marker-mid",
    "marker-start",
    "mask",
    "mix-blend-mode",
    "paint-order",
    "pathLength",
    "preserveAspectRatio",
    "rotate",
    "shape-rendering",
    "spreadMethod",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "textLength",
    "text-decoration",
    "text-decoration-color",
    "text-decoration-line",
    "text-decoration-style",
    "text-orientation",
    "text-rendering",
    "text-transform",
    "transform-origin",
    "unicode-bidi",
    "vector-effect",
    "word-spacing",
    "writing-mode",
    "baseline-shift",
    "dominant-baseline",
}


@dataclass(frozen=True)
class SvgCoverage:
    total_elements: int
    convertible_elements: int
    ignored_elements: int
    unsupported_elements: dict[str, int]
    unsupported_attributes: dict[str, int]
    unsupported_path_commands: dict[str, int]
    estimated_element_coverage: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def analyze_svg(svg_text: str) -> SvgCoverage:
    root = ET.fromstring(svg_text)
    css = _collect_css(root)
    refs = _collect_refs(root)
    stats = _CoverageStats()
    _walk(root, css, refs, {}, _root_viewbox_matrix(root), stats, (), _viewport_size(root), ())
    measurable = max(stats.total_elements - stats.ignored_elements, 0)
    coverage = stats.convertible_elements / measurable if measurable else 1.0
    return SvgCoverage(
        total_elements=stats.total_elements,
        convertible_elements=stats.convertible_elements,
        ignored_elements=stats.ignored_elements,
        unsupported_elements=dict(sorted(stats.unsupported_elements.items())),
        unsupported_attributes=dict(sorted(stats.unsupported_attributes.items())),
        unsupported_path_commands=dict(sorted(stats.unsupported_path_commands.items())),
        estimated_element_coverage=round(coverage, 4),
    )


@dataclass
class _CoverageStats:
    total_elements: int = 0
    convertible_elements: int = 0
    ignored_elements: int = 0
    unsupported_elements: dict[str, int] | None = None
    unsupported_attributes: dict[str, int] | None = None
    unsupported_path_commands: dict[str, int] | None = None

    def __post_init__(self) -> None:
        self.unsupported_elements = {}
        self.unsupported_attributes = {}
        self.unsupported_path_commands = {}

    def add_unsupported_element(self, tag: str) -> None:
        assert self.unsupported_elements is not None
        self.unsupported_elements[tag] = self.unsupported_elements.get(tag, 0) + 1

    def add_unsupported_attribute(self, attr: str) -> None:
        assert self.unsupported_attributes is not None
        self.unsupported_attributes[attr] = self.unsupported_attributes.get(attr, 0) + 1

    def add_unsupported_path_command(self, command: str) -> None:
        assert self.unsupported_path_commands is not None
        self.unsupported_path_commands[command] = self.unsupported_path_commands.get(command, 0) + 1


def _walk(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    inherited_matrix: tuple[float, float, float, float, float, float],
    stats: _CoverageStats,
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...],
) -> None:
    tag = _local_name(element.tag)
    stats.total_elements += 1

    path_supported = True
    if tag == "path":
        path_supported = _path_is_supported(element.get("d", ""))
    points_supported = True
    if tag in {"polygon", "polyline"}:
        points_supported = len(_parse_points(element.get("points", ""))) >= 2

    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    specified_style = _computed_style(element, css, {}, ancestors, previous_siblings)
    display_none = _is_display_none(style)
    visibility_hidden = _is_visibility_hidden(style)
    hidden = display_none or visibility_hidden
    non_rendering_geometry = _has_non_rendering_geometry(element, style, viewport)
    no_visible_paint = _has_no_visible_paint(element, style, refs, css, viewport)
    unresolved_paint_server = _has_unresolved_paint_server(style, refs, css)

    use_supported = True
    if tag == "use":
        use_supported = _use_href_is_supported(element, refs)
    switch_supported = True
    if tag == "switch":
        switch_supported = _switch_selected_child(element) is not None or len(element) == 0

    if tag in IGNORED_ELEMENTS or hidden or non_rendering_geometry or no_visible_paint:
        stats.ignored_elements += 1
    elif tag in SUPPORTED_ELEMENTS and path_supported and points_supported and use_supported and switch_supported:
        stats.convertible_elements += 1
    elif tag in SUPPORTED_ELEMENTS:
        stats.add_unsupported_element(_supported_element_issue(tag))
    else:
        stats.add_unsupported_element(tag)

    if display_none or non_rendering_geometry or (no_visible_paint and not unresolved_paint_server):
        return

    matrix = _matrix_multiply(inherited_matrix, _style_transform_matrix(style, viewport))
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if not visibility_hidden:
        _inspect_attributes(
            element,
            style,
            specified_style,
            refs,
            css,
            matrix,
            stats,
            ancestors,
            viewport,
            previous_siblings,
        )

    if tag == "path" and not visibility_hidden:
        _inspect_path(element.get("d", ""), stats)

    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is not None:
            previous_children = _previous_element_siblings(element, selected)
            _walk(selected, css, refs, style, matrix, stats, ancestors + (element,), child_viewport, previous_children)
        return

    previous_children: list[ET.Element] = []
    for child in element:
        if tag == "defs" and _local_name(child.tag) not in GRADIENT_ELEMENTS:
            stats.total_elements += 1
            stats.ignored_elements += 1
            previous_children.append(child)
            continue
        _walk(child, css, refs, style, matrix, stats, ancestors + (element,), child_viewport, tuple(previous_children))
        previous_children.append(child)


def _inspect_attributes(
    element: ET.Element,
    style: dict[str, str],
    specified_style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    matrix: tuple[float, float, float, float, float, float],
    stats: _CoverageStats,
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...],
) -> None:
    no_effect_attrs = {
        "clip-path",
        "clip-rule",
        "color-rendering",
        "fill-rule",
        "filter",
        "image-rendering",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "paint-order",
        "shape-rendering",
        "text-rendering",
        "vector-effect",
    }
    for attr in UNSUPPORTED_ATTRIBUTES:
        if attr in no_effect_attrs and _attribute_has_no_effect(attr, specified_style):
            continue
        if attr == "clip-path" and _clip_path_is_supported(element, style, refs, matrix):
            continue
        if attr == "clip-rule" and _clip_rule_has_no_effect(ancestors):
            continue
        if attr in {"marker", "marker-start", "marker-end"} and _marker_is_supported(element, style, refs):
            continue
        if attr == "font-variant" and _font_variant_is_supported(specified_style):
            continue
        if attr == "font-feature-settings" and _css_none_or_normal_has_no_effect(specified_style, attr):
            continue
        if attr == "font-kerning" and _css_auto_or_normal_has_no_effect(specified_style, attr):
            continue
        if attr == "font-size-adjust" and _font_size_adjust_has_no_effect(specified_style):
            continue
        if attr == "font-stretch" and _font_stretch_has_no_effect(specified_style):
            continue
        if attr == "font-variation-settings" and _css_none_or_normal_has_no_effect(specified_style, attr):
            continue
        if attr in {"glyph-orientation-horizontal", "glyph-orientation-vertical"} and _glyph_orientation_has_no_effect(
            specified_style, attr
        ):
            continue
        if attr == "kerning" and _css_auto_or_normal_has_no_effect(specified_style, attr):
            continue
        if attr in {"gradientTransform", "gradientUnits", "spreadMethod"} and _gradient_fallback_is_supported(
            element, refs, css
        ):
            continue
        if attr == "fill-rule" and _fill_rule_has_no_effect(element, style, refs, css, viewport):
            continue
        if attr == "isolation" and _isolation_is_redundant_with_blend(element, css, style, ancestors):
            continue
        if attr == "letter-spacing" and _letter_spacing_is_supported(specified_style):
            continue
        if attr in {"lengthAdjust", "textLength"} and _text_length_spacing_is_supported(
            element, specified_style
        ):
            continue
        if attr == "mix-blend-mode" and _mix_blend_mode_has_no_effect(element, specified_style, style, refs, css, viewport):
            continue
        if attr == "paint-order" and _paint_order_has_no_effect(element, style, refs, css, viewport):
            continue
        if attr == "pathLength" and _path_length_has_no_effect(specified_style):
            continue
        if attr == "preserveAspectRatio" and _preserve_aspect_ratio_is_supported_or_noop(element, specified_style):
            continue
        if attr == "rotate" and _text_rotate_is_supported(element, specified_style):
            continue
        if attr == "stroke-dashoffset" and (
            _stroke_dashoffset_has_no_effect(style, viewport) or _svg_dashoffset_is_supported(style, viewport)
        ):
            continue
        if attr == "stroke-linecap" and _stroke_linecap_is_supported_or_noop(element, style, refs, css, viewport):
            continue
        if attr == "stroke-linejoin" and _stroke_linejoin_is_supported_or_noop(element, style, refs, css, viewport):
            continue
        if (
            attr == "text-decoration"
            and specified_style.get("text-decoration-line") is not None
            and specified_style.get("text-decoration") == specified_style.get("text-decoration-line")
        ):
            continue
        if attr == "text-decoration" and _text_decoration_line_is_supported_or_noop(specified_style):
            continue
        if attr == "text-decoration-line" and _text_decoration_line_is_supported_or_noop(specified_style):
            continue
        if attr == "text-decoration-color" and _text_decoration_color_has_no_effect(specified_style):
            continue
        if attr == "text-decoration-style" and _text_decoration_style_is_supported_or_noop(specified_style):
            continue
        if attr == "text-orientation" and _text_orientation_has_no_effect(specified_style):
            continue
        if attr == "text-transform" and _text_transform_is_supported(element, specified_style):
            continue
        if attr == "transform-origin" and _transform_origin_is_supported(specified_style, viewport):
            continue
        if attr == "baseline-shift" and (
            _baseline_shift_has_no_effect(specified_style)
            or _baseline_shift_is_supported(element, specified_style)
        ):
            continue
        if attr == "alignment-baseline" and _alignment_baseline_is_supported_or_noop(element, specified_style):
            continue
        if attr == "direction" and _direction_has_no_effect(specified_style):
            continue
        if attr == "unicode-bidi" and _unicode_bidi_has_no_effect(specified_style):
            continue
        if attr == "writing-mode" and _writing_mode_has_no_effect(specified_style):
            continue
        if attr == "dominant-baseline" and _dominant_baseline_is_supported_or_noop(element, specified_style):
            continue
        if attr == "word-spacing" and _word_spacing_has_no_effect(element, specified_style):
            continue
        if attr == "word-spacing" and _word_spacing_is_supported(element, specified_style):
            continue
        if specified_style.get(attr) is not None:
            stats.add_unsupported_attribute(attr)
    _inspect_tspan_run_attributes(element, specified_style, stats, ancestors, previous_siblings)
    href = _href(element)
    if _local_name(element.tag) == "image":
        if not href or not _supported_data_image(href):
            stats.add_unsupported_attribute("href")
    elif _local_name(element.tag) == "use":
        if not _use_href_is_supported(element, refs):
            stats.add_unsupported_attribute("href")
    elif _local_name(element.tag) in {"linearGradient", "radialGradient"} and href is not None:
        if not href.startswith("#") or href[1:] not in refs:
            stats.add_unsupported_attribute("href")
    for attr in ("fill", "stroke"):
        value = style.get(attr)
        if value:
            ref = _url_ref(value)
            if ref is not None and not ref[1].strip():
                paint_server_tag = _local_name(refs.get(ref[0], ET.Element("")).tag)
                if paint_server_tag == "pattern":
                    color, _ = _paint_server_value(refs.get(ref[0]), refs, style.get("color"), css)
                    if not color:
                        stats.add_unsupported_attribute(f"{attr}:pattern")
                elif paint_server_tag in {"linearGradient", "radialGradient"}:
                    color, _ = _paint_server_value(refs.get(ref[0]), refs, style.get("color"), css)
                    if not color:
                        stats.add_unsupported_attribute(f"{attr}:paint-server")
                else:
                    stats.add_unsupported_attribute(f"{attr}:paint-server")


def _inspect_tspan_run_attributes(
    element: ET.Element,
    specified_style: dict[str, str],
    stats: _CoverageStats,
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
) -> None:
    if _local_name(element.tag) != "tspan":
        return
    if specified_style.get("text-anchor") is not None and not _first_positioned_tspan_text_anchor_is_supported(
        element,
        specified_style,
        ancestors,
        previous_siblings,
    ):
        stats.add_unsupported_attribute("text-anchor")
    if _word_spacing_is_supported(element, specified_style):
        stats.add_unsupported_attribute("word-spacing")


def _first_positioned_tspan_text_anchor_is_supported(
    element: ET.Element,
    specified_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
) -> bool:
    if _local_name(element.tag) != "tspan":
        return False
    value = specified_style.get("text-anchor")
    if value is None or value.strip().lower() not in {"start", "middle", "end"}:
        return False
    parent = ancestors[-1] if ancestors else None
    if parent is None or _local_name(parent.tag) != "text":
        return False
    if parent.get("x") is not None or parent.get("y") is not None:
        return False
    if (parent.text or "").strip():
        return False
    if element.get("x") is None or element.get("y") is None:
        return False
    return not any(_local_name(sibling.tag) == "tspan" and "".join(sibling.itertext()).strip() for sibling in previous_siblings)


def _inspect_path(path_data: str, stats: _CoverageStats) -> None:
    if not path_data:
        return
    if _parse_linear_path(path_data) is not None:
        return
    supported = set("MmLlHhVvZzCcSsQqTtAa")
    for command in path_data:
        if command.isalpha() and command not in supported:
            stats.add_unsupported_path_command(command)


def _has_non_rendering_geometry(element: ET.Element, style: dict[str, str], viewport: tuple[float, float]) -> bool:
    tag = _local_name(element.tag)
    if tag in {"rect", "image"}:
        return _geometry_length(element, style, "width", "x", viewport) <= 0 or _geometry_length(
            element, style, "height", "y", viewport
        ) <= 0
    if tag == "circle":
        return _geometry_length(element, style, "r", "diag", viewport) <= 0
    if tag == "ellipse":
        return _geometry_length(element, style, "rx", "x", viewport) <= 0 or _geometry_length(
            element, style, "ry", "y", viewport
        ) <= 0
    return False


def _has_no_visible_paint(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    tag = _local_name(element.tag)
    if tag == "image":
        return _alpha_is_zero(style.get("opacity"))
    if tag not in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan"}:
        return False
    if tag in {"text", "tspan"} and not _svg_text_content(element):
        return True
    paint = _svg_paint(style, refs, default_fill=tag != "line", css=css, viewport=viewport)
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    return not (has_fill or has_stroke)


def _has_unresolved_paint_server(style: dict[str, str], refs: dict[str, ET.Element], css: list[CssRule]) -> bool:
    for attr in ("fill", "stroke"):
        value = style.get(attr)
        if not value:
            continue
        ref = _url_ref(value)
        if ref is None or ref[1].strip():
            continue
        color, _ = _paint_server_value(refs.get(ref[0]), refs, style.get("color"), css)
        if not color:
            return True
    return False


def _geometry_length(element: ET.Element, style: dict[str, str], attr: str, axis: str, viewport: tuple[float, float]) -> float:
    return _length(style.get(attr, element.get(attr)), 0, axis, viewport)


def _gradient_fallback_is_supported(element: ET.Element, refs: dict[str, ET.Element], css: list[CssRule]) -> bool:
    if _local_name(element.tag) not in {"linearGradient", "radialGradient"}:
        return False
    color, _ = _paint_server_value(element, refs, element.get("color"), css)
    return bool(color)


def _isolation_is_redundant_with_blend(
    element: ET.Element,
    css: list[CssRule],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
) -> bool:
    if _local_name(element.tag) not in {"g", "svg", "a"}:
        return False
    value = inherited_style.get("isolation")
    if value is None or value.strip().lower() not in {"isolate", "auto"}:
        return False
    return any(_subtree_has_blend(child, css, inherited_style, ancestors + (element,)) for child in element)


def _subtree_has_blend(
    element: ET.Element,
    css: list[CssRule],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors)
    blend = style.get("mix-blend-mode")
    if blend is not None and blend.strip().lower() not in {"", "normal"}:
        return True
    return any(_subtree_has_blend(child, css, style, ancestors + (element,)) for child in element)


def _text_rotate_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    if _local_name(element.tag) not in {"text", "tspan"}:
        return False
    value = style.get("rotate")
    if value is None:
        return False
    numbers = _svg_rotation_values(value)
    if not numbers:
        return False
    if all(number == numbers[0] for number in numbers):
        return True
    text = _svg_text_content(element) if _local_name(element.tag) == "text" else "".join(element.itertext())
    return len(text) <= 1


def _text_transform_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("text-transform")
    return value is not None and value.strip().lower() in {"normal", "none", "uppercase", "lowercase", "capitalize"}


def _css_none_or_normal_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    return value is not None and value.strip().lower() in {"", "normal", "none"}


def _css_auto_or_normal_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    return value is not None and value.strip().lower() in {"", "auto", "normal"}


def _font_size_adjust_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("font-size-adjust")
    return value is not None and value.strip().lower() in {"", "none"}


def _font_stretch_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("font-stretch")
    return value is not None and value.strip().lower() in {"", "normal", "100%"}


def _text_orientation_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("text-orientation")
    return value is not None and value.strip().lower() in {"", "mixed"}


def _glyph_orientation_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"", "auto", "0", "0deg", "0grad", "0rad", "0turn"}


def _baseline_shift_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("baseline-shift")
    if value is None:
        return False
    return value.strip().lower() in {"", "baseline", "0", "0px", "0pt", "0pc", "0in", "0cm", "0mm", "0q"}


def _baseline_shift_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("baseline-shift")
    if value is None or _local_name(element.tag) not in {"text", "tspan"}:
        return False
    return value.strip().lower() in {"super", "sub"}


def _alignment_baseline_is_supported_or_noop(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("alignment-baseline")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "auto", "baseline", "alphabetic"}:
        return True
    if _local_name(element.tag) != "text":
        return False
    return _dominant_baseline(value) is not None


def _dominant_baseline_is_supported_or_noop(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("dominant-baseline")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "auto", "baseline", "alphabetic"}:
        return True
    if _local_name(element.tag) != "text":
        return False
    return _dominant_baseline(value) is not None


def _direction_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("direction")
    return value is not None and value.strip().lower() in {"", "ltr"}


def _unicode_bidi_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("unicode-bidi")
    return value is not None and value.strip().lower() in {"", "normal"}


def _writing_mode_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("writing-mode")
    return value is not None and value.strip().lower() in {"", "horizontal-tb", "lr", "lr-tb", "rl", "rl-tb"}


def _text_decoration_color_has_no_effect(style: dict[str, str]) -> bool:
    return not _has_visible_text_decoration(style)


def _text_decoration_style_is_supported_or_noop(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-style")
    if value is None:
        return False
    if not _has_visible_text_decoration(style):
        return True
    return value.strip().lower() in {"", "solid"}


def _text_decoration_line_is_supported_or_noop(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    tokens = set(value.strip().lower().split())
    if not tokens or tokens <= {"none"}:
        return True
    return tokens <= {"underline", "line-through"}


def _has_visible_text_decoration(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    tokens = set(value.strip().lower().split())
    return bool(tokens & {"underline", "line-through"})


def _transform_origin_is_supported(style: dict[str, str], viewport: tuple[float, float]) -> bool:
    value = style.get("transform-origin")
    if value is None:
        return False
    return _transform_origin(value, viewport) is not None


def _letter_spacing_is_supported(style: dict[str, str]) -> bool:
    value = style.get("letter-spacing")
    if value is None:
        return False
    if value.strip().lower() == "normal":
        return True
    return _optional_length(value, "x", (0.0, 0.0)) is not None


def _text_length_spacing_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    if _local_name(element.tag) != "text":
        return False
    return _svg_text_length_spacing_is_supported(style, _svg_text_content(element), (0.0, 0.0))


def _attribute_has_no_effect(attr: str, style: dict[str, str]) -> bool:
    value = style.get(attr)
    if value is None:
        return False
    normalized = " ".join(value.strip().lower().split())
    if attr in {"clip-path", "filter", "marker", "marker-end", "marker-mid", "marker-start", "mask"}:
        return normalized == "none"
    if attr in {"clip-rule", "fill-rule"}:
        return normalized == "nonzero"
    if attr == "paint-order":
        return normalized in {"normal", "fill", "fill stroke", "fill stroke markers"}
    if attr in {"color-rendering", "image-rendering", "shape-rendering", "text-rendering"}:
        return normalized in {
            "auto",
            "crisp-edges",
            "crispedges",
            "geometricprecision",
            "optimizelegibility",
            "optimizequality",
            "optimizespeed",
            "pixelated",
        }
    if attr == "vector-effect":
        return normalized in {"none", "non-scaling-stroke"}
    return False


def _clip_rule_has_no_effect(ancestors: tuple[ET.Element, ...]) -> bool:
    return not any(_local_name(ancestor.tag) == "clipPath" for ancestor in ancestors)


def _path_length_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("pathLength")
    if value is None:
        return False
    dasharray = style.get("stroke-dasharray")
    return dasharray is None or dasharray.strip().lower() in {"", "none"}


def _preserve_aspect_ratio_is_supported_or_noop(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("preserveAspectRatio")
    if value is None:
        return False
    tag = _local_name(element.tag)
    if tag in {"svg", "symbol"}:
        return True
    if tag == "image":
        align, _ = _preserve_aspect_ratio(value)
        return align == "none" or _data_image_dimensions(_href(element) or "") is not None
    return False


def _word_spacing_has_no_effect(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("word-spacing")
    if value is None:
        return False
    if value.strip().lower() == "normal":
        return True
    if _optional_length(value, "x", (0.0, 0.0)) == 0:
        return True
    if _local_name(element.tag) == "text":
        return not re.search(r"[ \t\f\v]", _svg_text_content(element))
    if _local_name(element.tag) == "tspan":
        return not re.search(r"[ \t\f\v]", "".join(element.itertext()))
    return False


def _word_spacing_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    if _local_name(element.tag) != "text":
        return False
    return _svg_word_spacing_is_supported(style, _svg_text_content(element), (0.0, 0.0))


def _mix_blend_mode_has_no_effect(
    element: ET.Element,
    specified_style: dict[str, str],
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = specified_style.get("mix-blend-mode")
    if value is None:
        return False
    if value.strip().lower() in {"", "normal"}:
        return True
    tag = _local_name(element.tag)
    if tag == "image":
        return _alpha_is_zero(style.get("opacity"))
    if tag not in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan"}:
        return False
    paint = _svg_paint(style, refs, default_fill=tag != "line", css=css, viewport=viewport)
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    return not (has_fill or has_stroke)


def _paint_order_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("paint-order")
    if value is None:
        return False
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css, viewport=viewport)
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    return not (has_fill and has_stroke)


def _fill_rule_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("fill-rule")
    if value is None:
        return False
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css, viewport=viewport)
    return paint.fill in {None, "none"}


def _stroke_dashoffset_has_no_effect(style: dict[str, str], viewport: tuple[float, float]) -> bool:
    value = style.get("stroke-dashoffset")
    if value is None:
        return False
    parsed = _optional_length(value, "diag", viewport)
    if parsed == 0:
        return True
    dasharray = style.get("stroke-dasharray")
    if dasharray is None or dasharray.strip().lower() in {"", "none"}:
        return True
    period = _dash_pattern_period(dasharray, viewport)
    if period and _is_multiple_of(abs(parsed), period):
        return True
    stroke = style.get("stroke")
    if stroke is None or stroke.strip().lower() in {"", "none", "transparent"}:
        return True
    stroke_width = _optional_length(style.get("stroke-width"), "diag", viewport)
    if stroke_width == 0:
        return True
    return _alpha_is_zero(style.get("opacity")) or _alpha_is_zero(style.get("stroke-opacity"))


def _stroke_linecap_is_supported_or_noop(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("stroke-linecap")
    if value is None:
        return False
    return _stroke_has_no_effect(element, style, refs, css, viewport) or _svg_linecap(value) is not None


def _stroke_linejoin_is_supported_or_noop(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("stroke-linejoin")
    if value is None:
        return False
    return _stroke_has_no_effect(element, style, refs, css, viewport) or _svg_linejoin(value) is not None


def _stroke_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css, viewport=viewport)
    return paint.stroke in {None, "none"} or (paint.stroke_width or 0) <= 0


def _dash_pattern_period(value: str, viewport: tuple[float, float]) -> float | None:
    nums = _svg_dasharray_numbers(value, viewport)
    if not nums:
        return None
    period = sum(nums) * (2 if len(nums) % 2 else 1)
    return period if period > 0 else None


def _is_multiple_of(value: float, period: float) -> bool:
    remainder = value % period
    return remainder < 1e-9 or abs(remainder - period) < 1e-9


def _alpha_is_zero(value: str | None) -> bool:
    alpha = _alpha_value(value)
    return alpha is not None and alpha <= 0


def _font_variant_is_supported(style: dict[str, str]) -> bool:
    value = style.get("font-variant")
    if value is None:
        return False
    return value.strip().lower() in {"normal", "small-caps", "all-small-caps"}


def _path_is_supported(path_data: str) -> bool:
    return not path_data or _parse_linear_path(path_data) is not None


def _use_href_is_supported(element: ET.Element, refs: dict[str, ET.Element]) -> bool:
    href = _href(element)
    return bool(href and href.startswith("#") and href[1:] in refs)


def _supported_element_issue(tag: str) -> str:
    if tag == "path":
        return "path:unsupported-command"
    if tag in {"polygon", "polyline"}:
        return f"{tag}:invalid-points"
    if tag == "switch":
        return "switch:unsupported-branch"
    return f"{tag}:unsupported-reference"
