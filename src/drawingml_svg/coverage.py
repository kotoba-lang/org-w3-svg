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
    _local_name,
    _marker_is_supported,
    _matrix_multiply,
    _optional_length,
    _parse_linear_path,
    _parse_transform,
    _root_viewbox_matrix,
    _supported_data_image,
    _switch_selected_child,
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

IGNORED_ELEMENTS = {"defs", "desc", "linearGradient", "metadata", "radialGradient", "stop", "title"}
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
    "text-rendering",
    "textLength",
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
    _walk(root, css, refs, {}, _root_viewbox_matrix(root), stats, ())
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
) -> None:
    tag = _local_name(element.tag)
    stats.total_elements += 1

    path_supported = True
    if tag == "path":
        path_supported = _path_is_supported(element.get("d", ""))

    style = _computed_style(element, css, inherited_style, ancestors)
    specified_style = _computed_style(element, css, {}, ancestors)
    hidden = _is_hidden(style)

    use_supported = True
    if tag == "use":
        use_supported = _use_href_is_supported(element, refs)
    switch_supported = True
    if tag == "switch":
        switch_supported = _switch_selected_child(element) is not None or len(element) == 0

    if tag in IGNORED_ELEMENTS or hidden:
        stats.ignored_elements += 1
    elif tag in SUPPORTED_ELEMENTS and path_supported and use_supported and switch_supported:
        stats.convertible_elements += 1
    elif tag in SUPPORTED_ELEMENTS:
        stats.add_unsupported_element(_supported_element_issue(tag))
    else:
        stats.add_unsupported_element(tag)

    matrix = _matrix_multiply(inherited_matrix, _parse_transform(element.get("transform", "")))
    _inspect_attributes(element, style, specified_style, refs, matrix, stats)

    if tag == "path":
        _inspect_path(element.get("d", ""), stats)

    if hidden:
        return
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is not None:
            _walk(selected, css, refs, style, matrix, stats, ancestors + (element,))
        return

    for child in element:
        if tag == "defs" and _local_name(child.tag) not in GRADIENT_ELEMENTS:
            stats.total_elements += 1
            stats.ignored_elements += 1
            continue
        _walk(child, css, refs, style, matrix, stats, ancestors + (element,))


def _inspect_attributes(
    element: ET.Element,
    style: dict[str, str],
    specified_style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
    stats: _CoverageStats,
) -> None:
    for attr in UNSUPPORTED_ATTRIBUTES:
        if attr == "clip-path" and _clip_path_is_supported(element, style, refs, matrix):
            continue
        if attr in {"marker-start", "marker-end"} and _marker_is_supported(element, style, refs):
            continue
        if attr == "font-variant" and _font_variant_is_supported(specified_style):
            continue
        if attr == "letter-spacing" and _letter_spacing_is_supported(specified_style):
            continue
        if attr == "rotate" and _text_rotate_is_supported(element, specified_style):
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
            if (
                match
                and not match.group(2).strip()
                and _local_name(refs.get(match.group(1), ET.Element("")).tag) not in {"linearGradient", "radialGradient"}
            ):
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


def _text_rotate_is_supported(element: ET.Element, style: dict[str, str]) -> bool:
    if _local_name(element.tag) not in {"text", "tspan"}:
        return False
    value = style.get("rotate")
    return value is not None and len(re.findall(NUMBER_RE, value)) == 1


def _letter_spacing_is_supported(style: dict[str, str]) -> bool:
    value = style.get("letter-spacing")
    if value is None:
        return False
    if value.strip().lower() == "normal":
        return True
    return _optional_length(value, "x", (0.0, 0.0)) is not None


def _font_variant_is_supported(style: dict[str, str]) -> bool:
    value = style.get("font-variant")
    if value is None:
        return False
    return value.strip().lower() in {"normal", "small-caps"}


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
