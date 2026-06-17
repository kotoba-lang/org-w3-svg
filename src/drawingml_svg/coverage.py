from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .converter import (
    CssRule,
    NUMBER_RE,
    _collect_css,
    _collect_refs,
    _computed_style,
    _clip_path_is_supported,
    _href,
    _is_hidden,
    _length,
    _local_name,
    _marker_is_supported,
    _matrix_multiply,
    _optional_length,
    _paint_server_value,
    _parse_linear_path,
    _parse_transform,
    _root_viewbox_matrix,
    _supported_data_image,
    _svg_paint,
    _svg_text_content,
    _svg_text_length_spacing_is_supported,
    _svg_word_spacing_is_supported,
    _svg_dasharray_numbers,
    _svg_dashoffset_is_supported,
    _switch_selected_child,
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
    "clip-path",
    "clip-rule",
    "color-rendering",
    "fill-rule",
    "filter",
    "font-variant",
    "gradientTransform",
    "gradientUnits",
    "image-rendering",
    "isolation",
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
    "rotate",
    "shape-rendering",
    "spreadMethod",
    "stroke-dashoffset",
    "textLength",
    "text-rendering",
    "text-transform",
    "vector-effect",
    "word-spacing",
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
    _walk(root, css, refs, {}, _root_viewbox_matrix(root), stats, (), _viewport_size(root))
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
) -> None:
    tag = _local_name(element.tag)
    stats.total_elements += 1

    path_supported = True
    if tag == "path":
        path_supported = _path_is_supported(element.get("d", ""))

    style = _computed_style(element, css, inherited_style, ancestors)
    specified_style = _computed_style(element, css, {}, ancestors)
    hidden = _is_hidden(style)
    non_rendering_geometry = _has_non_rendering_geometry(element, style, viewport)

    use_supported = True
    if tag == "use":
        use_supported = _use_href_is_supported(element, refs)
    switch_supported = True
    if tag == "switch":
        switch_supported = _switch_selected_child(element) is not None or len(element) == 0

    if tag in IGNORED_ELEMENTS or hidden or non_rendering_geometry:
        stats.ignored_elements += 1
    elif tag in SUPPORTED_ELEMENTS and path_supported and use_supported and switch_supported:
        stats.convertible_elements += 1
    elif tag in SUPPORTED_ELEMENTS:
        stats.add_unsupported_element(_supported_element_issue(tag))
    else:
        stats.add_unsupported_element(tag)

    if hidden or non_rendering_geometry:
        return

    matrix = _matrix_multiply(inherited_matrix, _parse_transform(element.get("transform", "")))
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    _inspect_attributes(element, style, specified_style, refs, css, matrix, stats, ancestors)

    if tag == "path":
        _inspect_path(element.get("d", ""), stats)

    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is not None:
            _walk(selected, css, refs, style, matrix, stats, ancestors + (element,), child_viewport)
        return

    for child in element:
        if tag == "defs" and _local_name(child.tag) not in GRADIENT_ELEMENTS:
            stats.total_elements += 1
            stats.ignored_elements += 1
            continue
        _walk(child, css, refs, style, matrix, stats, ancestors + (element,), child_viewport)


def _inspect_attributes(
    element: ET.Element,
    style: dict[str, str],
    specified_style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    matrix: tuple[float, float, float, float, float, float],
    stats: _CoverageStats,
    ancestors: tuple[ET.Element, ...],
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
        if attr in {"gradientTransform", "gradientUnits", "spreadMethod"} and _gradient_fallback_is_supported(
            element, refs, css
        ):
            continue
        if attr == "fill-rule" and _fill_rule_has_no_effect(element, style, refs, css):
            continue
        if attr == "isolation" and _isolation_is_redundant_with_blend(element, css, style, ancestors):
            continue
        if attr == "letter-spacing" and _letter_spacing_is_supported(specified_style):
            continue
        if attr in {"lengthAdjust", "textLength"} and _text_length_spacing_is_supported(
            element, specified_style
        ):
            continue
        if attr == "mix-blend-mode" and _mix_blend_mode_has_no_effect(specified_style):
            continue
        if attr == "paint-order" and _paint_order_has_no_effect(element, style, refs, css):
            continue
        if attr == "pathLength" and _path_length_has_no_effect(specified_style):
            continue
        if attr == "rotate" and _text_rotate_is_supported(element, specified_style):
            continue
        if attr == "stroke-dashoffset" and (_stroke_dashoffset_has_no_effect(style) or _svg_dashoffset_is_supported(style)):
            continue
        if attr == "text-transform" and _text_transform_is_supported(element, specified_style):
            continue
        if attr == "word-spacing" and _word_spacing_has_no_effect(element, specified_style):
            continue
        if attr == "word-spacing" and _word_spacing_is_supported(element, specified_style):
            continue
        if specified_style.get(attr) is not None:
            stats.add_unsupported_attribute(attr)
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
    elif _local_name(element.tag) != "use" and href is not None:
        stats.add_unsupported_attribute("href")
    for attr in ("fill", "stroke"):
        value = style.get(attr)
        if value:
            match = re.match(r"^url\((?:['\"])?#([^'\")]+)(?:['\"])?\)(.*)$", value.strip())
            if match and not match.group(2).strip():
                paint_server_tag = _local_name(refs.get(match.group(1), ET.Element("")).tag)
                if paint_server_tag == "pattern":
                    color, _ = _paint_server_value(refs.get(match.group(1)), refs, style.get("color"), css)
                    if not color:
                        stats.add_unsupported_attribute(f"{attr}:pattern")
                elif paint_server_tag in {"linearGradient", "radialGradient"}:
                    color, _ = _paint_server_value(refs.get(match.group(1)), refs, style.get("color"), css)
                    if not color:
                        stats.add_unsupported_attribute(f"{attr}:paint-server")
                else:
                    stats.add_unsupported_attribute(f"{attr}:paint-server")


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
    numbers = [float(number) for number in re.findall(NUMBER_RE, value)]
    if not numbers:
        return False
    if all(number == numbers[0] for number in numbers):
        return True
    text = _svg_text_content(element) if _local_name(element.tag) == "text" else "".join(element.itertext())
    return len(text) <= 1


def _text_transform_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("text-transform")
    return value is not None and value.strip().lower() in {"none", "uppercase", "lowercase", "capitalize"}


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


def _mix_blend_mode_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("mix-blend-mode")
    return value is not None and value.strip().lower() in {"", "normal"}


def _paint_order_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
) -> bool:
    value = style.get("paint-order")
    if value is None:
        return False
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css)
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    return not (has_fill and has_stroke)


def _fill_rule_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
) -> bool:
    value = style.get("fill-rule")
    if value is None:
        return False
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css)
    return paint.fill in {None, "none"}


def _stroke_dashoffset_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("stroke-dashoffset")
    if value is None:
        return False
    parsed = _optional_length(value, "x", (0.0, 0.0))
    if parsed == 0:
        return True
    dasharray = style.get("stroke-dasharray")
    if dasharray is None or dasharray.strip().lower() in {"", "none"}:
        return True
    period = _dash_pattern_period(dasharray)
    if period and _is_multiple_of(abs(parsed), period):
        return True
    stroke = style.get("stroke")
    if stroke is None or stroke.strip().lower() in {"", "none", "transparent"}:
        return True
    stroke_width = _optional_length(style.get("stroke-width"), "x", (0.0, 0.0))
    if stroke_width == 0:
        return True
    return _alpha_is_zero(style.get("opacity")) or _alpha_is_zero(style.get("stroke-opacity"))


def _dash_pattern_period(value: str) -> float | None:
    nums = _svg_dasharray_numbers(value)
    if not nums:
        return None
    period = sum(nums) * (2 if len(nums) % 2 else 1)
    return period if period > 0 else None


def _is_multiple_of(value: float, period: float) -> bool:
    remainder = value % period
    return remainder < 1e-9 or abs(remainder - period) < 1e-9


def _alpha_is_zero(value: str | None) -> bool:
    if value is None:
        return False
    value = value.strip()
    try:
        if value.endswith("%"):
            return float(value[:-1]) <= 0
        return float(value) <= 0
    except ValueError:
        return False


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
    if tag == "switch":
        return "switch:unsupported-branch"
    return f"{tag}:unsupported-reference"
