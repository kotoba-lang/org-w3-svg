from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .converter import (
    CssRule,
    _collect_css,
    _collect_refs,
    _computed_style,
    _clip_path_is_supported,
    _is_hidden,
    _local_name,
    _marker_is_supported,
    _matrix_multiply,
    _parse_linear_path,
    _parse_transform,
    _root_viewbox_matrix,
    _supported_data_image,
)

SUPPORTED_ELEMENTS = {
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
    "use",
    "svg",
    "symbol",
    "text",
    "tspan",
}

IGNORED_ELEMENTS = {"defs", "desc", "metadata", "title"}

UNSUPPORTED_ATTRIBUTES = {
    "clip-path",
    "filter",
    "marker-end",
    "marker-mid",
    "marker-start",
    "mask",
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
    hidden = _is_hidden(style)

    if tag in IGNORED_ELEMENTS or hidden:
        stats.ignored_elements += 1
    elif tag in SUPPORTED_ELEMENTS and path_supported:
        stats.convertible_elements += 1
    elif tag in SUPPORTED_ELEMENTS:
        stats.add_unsupported_element(f"{tag}:unsupported-command")
    else:
        stats.add_unsupported_element(tag)

    matrix = _matrix_multiply(inherited_matrix, _parse_transform(element.get("transform", "")))
    _inspect_attributes(element, style, refs, matrix, stats)

    if tag == "path":
        _inspect_path(element.get("d", ""), stats)

    if tag == "defs" or hidden:
        return

    for child in element:
        _walk(child, css, refs, style, matrix, stats, ancestors + (element,))


def _inspect_attributes(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
    stats: _CoverageStats,
) -> None:
    for attr in UNSUPPORTED_ATTRIBUTES:
        if attr == "clip-path" and _clip_path_is_supported(element, style, refs, matrix):
            continue
        if attr in {"marker-start", "marker-end"} and _marker_is_supported(element, style, refs):
            continue
        if element.get(attr) is not None or style.get(attr) is not None:
            stats.add_unsupported_attribute(attr)
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
    if _local_name(element.tag) == "image":
        if not href or not _supported_data_image(href):
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


def _path_is_supported(path_data: str) -> bool:
    return not path_data or _parse_linear_path(path_data) is not None
