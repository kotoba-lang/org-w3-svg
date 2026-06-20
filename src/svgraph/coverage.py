from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .converter import (
    CssRule,
    NUMBER_RE,
    _alpha_value,
    _collect_css,
    _collect_refs,
    _computed_style,
    _css_value_tokens,
    _data_image_dimensions,
    _clip_path_is_supported,
    _dominant_baseline,
    _foreign_object_table_is_supported,
    _href,
    _is_display_none,
    _is_visibility_hidden,
    _length,
    _local_name,
    _marker_is_supported as _converter_marker_is_supported,
    _matrix_multiply,
    _optional_length,
    _paint_server_value,
    _parse_color,
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
    _transform_angle_arg,
    _transform_origin,
    _switch_selected_child,
    _url_ref,
    _viewbox_matrix,
    _viewport_size,
)

SUPPORTED_ELEMENTS = {
    "a",
    "circle",
    "ellipse",
    "foreignObject",
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
TEXT_DECORATION_LINE_TOKENS = {"none", "underline", "line-through", "overline", "blink"}
TEXT_DECORATION_STYLE_TOKENS = {"solid", "dashed", "dotted", "double", "wavy"}
TEXT_DECORATION_NOOP_THICKNESS_TOKENS = {"auto"}
SUPPORTED_TEXT_DECORATION_LINE_TOKENS = {"underline", "line-through"}
GRADIENT_ELEMENTS = {"linearGradient", "radialGradient", "stop"}
GRAPHIC_ELEMENTS_WITHOUT_TEXT_LAYOUT = {"circle", "ellipse", "image", "line", "path", "polygon", "polyline", "rect"}
RENDERING_ELEMENTS = {"circle", "ellipse", "image", "line", "path", "polygon", "polyline", "rect", "text", "tspan", "use"}
TEXT_LAYOUT_ATTRIBUTES = {
    "alignment-baseline",
    "baseline-shift",
    "direction",
    "font-feature-settings",
    "font-kerning",
    "font-size-adjust",
    "font-stretch",
    "font-variant",
    "font-variation-settings",
    "glyph-orientation-horizontal",
    "glyph-orientation-vertical",
    "kerning",
    "letter-spacing",
    "lengthAdjust",
    "rotate",
    "text-decoration",
    "text-decoration-color",
    "text-decoration-line",
    "text-decoration-skip-ink",
    "text-decoration-style",
    "text-decoration-thickness",
    "text-orientation",
    "text-transform",
    "text-underline-offset",
    "textLength",
    "unicode-bidi",
    "word-spacing",
    "writing-mode",
}

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
    "opacity",
    "overflow",
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
    "text-decoration-skip-ink",
    "text-decoration-style",
    "text-decoration-thickness",
    "text-orientation",
    "text-rendering",
    "text-transform",
    "text-underline-offset",
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
        use_supported = _use_href_is_supported(element, refs) and _use_referenced_subtree_is_supported(
            element,
            css,
            refs,
            style,
            ancestors,
            viewport,
            stats,
        )
    switch_supported = True
    if tag == "switch":
        switch_supported = _switch_selected_child(element) is not None or len(element) == 0

    matrix = _matrix_multiply(inherited_matrix, _style_transform_matrix(element, style, viewport))
    foreign_object_supported = tag != "foreignObject" or _foreign_object_table_is_supported(
        element, style, matrix, viewport
    )

    if tag in IGNORED_ELEMENTS or hidden or non_rendering_geometry or no_visible_paint:
        stats.ignored_elements += 1
    elif (
        tag in SUPPORTED_ELEMENTS
        and path_supported
        and points_supported
        and use_supported
        and switch_supported
        and foreign_object_supported
    ):
        stats.convertible_elements += 1
    elif tag in SUPPORTED_ELEMENTS:
        stats.add_unsupported_element(_supported_element_issue(tag))
    else:
        stats.add_unsupported_element(tag)

    if display_none or non_rendering_geometry or (no_visible_paint and not unresolved_paint_server):
        return

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

    if tag == "foreignObject":
        return

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
        "isolation",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "overflow",
        "paint-order",
        "shape-rendering",
        "text-rendering",
        "vector-effect",
    }
    for attr in UNSUPPORTED_ATTRIBUTES:
        if attr in no_effect_attrs and _attribute_has_no_effect(attr, specified_style):
            continue
        if attr in TEXT_LAYOUT_ATTRIBUTES and _text_layout_attribute_has_no_effect(element, specified_style, attr):
            continue
        if attr in TEXT_LAYOUT_ATTRIBUTES and not _subtree_has_visible_text(element, css, refs, style, ancestors, viewport):
            continue
        if attr == "clip-path" and (
            _clip_path_is_supported(element, style, refs, matrix)
            or _subtree_clip_path_is_supported(element, css, refs, style, matrix, ancestors, viewport)
        ):
            continue
        if attr == "clip-rule" and _clip_rule_has_no_effect(ancestors):
            continue
        if attr in {"marker", "marker-start", "marker-end"} and (
            _marker_is_supported(element, style, refs)
            or _subtree_marker_is_supported(element, css, refs, style, ancestors, viewport)
        ):
            continue
        if attr == "marker-mid" and (
            _marker_mid_has_no_effect(element, specified_style)
            or _subtree_marker_mid_has_no_effect(element, css, refs, style, ancestors, viewport)
        ):
            continue
        if attr == "font-variant" and _font_variant_is_supported(specified_style):
            continue
        if attr == "font-feature-settings" and _css_none_or_normal_has_no_effect(specified_style, attr):
            continue
        if attr == "font-kerning" and _font_kerning_has_no_effect(element, specified_style):
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
        if attr == "kerning" and _kerning_has_no_effect(element, specified_style):
            continue
        if attr in {"gradientTransform", "gradientUnits", "spreadMethod"} and (
            _gradient_fallback_is_supported(element, refs, css)
            or not _paint_server_is_referenced(element, css, refs, ancestors, viewport)
        ):
            continue
        if attr == "fill-rule" and _fill_rule_has_no_effect(element, style, refs, css, ancestors, viewport):
            continue
        if attr in {"clip-path", "filter", "isolation", "mask", "mix-blend-mode"} and not _subtree_has_visible_rendering(
            element,
            css,
            refs,
            style,
            ancestors,
            viewport,
        ):
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
        if attr == "opacity" and _opacity_is_supported_or_noop(element, specified_style, css, refs, style, ancestors, viewport):
            continue
        if attr == "overflow" and _overflow_is_supported_or_noop(element, css, refs, style, ancestors, viewport):
            continue
        if attr == "paint-order" and not _subtree_has_unsupported_paint_order(
            element,
            css,
            refs,
            style,
            ancestors,
            viewport,
        ):
            continue
        if attr == "pathLength" and _path_length_has_no_effect(element, style, refs, css, viewport):
            continue
        if attr == "preserveAspectRatio" and _preserve_aspect_ratio_is_supported_or_noop(element, specified_style, refs):
            continue
        if attr == "rotate" and _text_rotate_is_supported(element, specified_style):
            continue
        if attr == "stroke-dashoffset" and (
            _stroke_dashoffset_has_no_effect(style, viewport) or _svg_dashoffset_is_supported(style, viewport)
        ):
            continue
        if (
            attr == "stroke-linecap"
            and _stroke_linecap_is_supported_or_noop(element, style, refs, css, viewport)
            and not _subtree_has_unsupported_stroke_line_enum(
                element,
                css,
                refs,
                style,
                ancestors,
                viewport,
                "stroke-linecap",
            )
        ):
            continue
        if (
            attr == "stroke-linejoin"
            and _stroke_linejoin_is_supported_or_noop(element, style, refs, css, viewport)
            and not _subtree_has_unsupported_stroke_line_enum(
                element,
                css,
                refs,
                style,
                ancestors,
                viewport,
                "stroke-linejoin",
            )
        ):
            continue
        if (
            attr == "text-decoration"
            and specified_style.get("text-decoration-line") is not None
            and specified_style.get("text-decoration") == specified_style.get("text-decoration-line")
        ):
            continue
        if attr == "text-decoration" and _text_decoration_shorthand_is_supported_or_noop(
            style,
            refs,
            css,
            viewport,
        ):
            continue
        if attr in {
            "text-decoration",
            "text-decoration-color",
            "text-decoration-line",
            "text-decoration-skip-ink",
            "text-decoration-style",
            "text-decoration-thickness",
            "text-underline-offset",
        } and not _subtree_has_visible_text(element, css, refs, style, ancestors, viewport):
            continue
        if attr == "text-decoration-line" and _text_decoration_line_is_supported_or_noop(specified_style):
            continue
        if attr == "text-decoration-skip-ink" and _text_decoration_skip_ink_has_no_effect(specified_style):
            continue
        if attr == "text-decoration-color" and _text_decoration_color_has_no_effect(
            style, refs, css, viewport
        ):
            continue
        if attr == "text-decoration-style" and _text_decoration_style_is_supported_or_noop(specified_style):
            continue
        if attr == "text-decoration-thickness" and _text_decoration_thickness_has_no_effect(specified_style):
            continue
        if attr == "text-orientation" and _text_orientation_has_no_effect(specified_style):
            continue
        if attr == "text-transform" and _text_transform_is_supported(element, specified_style):
            continue
        if attr == "text-underline-offset" and _text_underline_offset_has_no_effect(specified_style):
            continue
        if attr == "transform-origin" and not _subtree_has_visible_rendering(
            element,
            css,
            refs,
            style,
            ancestors,
            viewport,
        ):
            continue
        if attr == "transform-origin" and (
            _transform_origin_has_no_effect(specified_style)
            or _transform_origin_is_supported(element, specified_style, viewport)
        ):
            continue
        if attr == "vector-effect" and not _subtree_has_visible_stroke(element, css, refs, style, ancestors, viewport):
            continue
        if attr == "baseline-shift" and (
            _baseline_shift_has_no_effect(specified_style)
            or _baseline_shift_is_supported(element, specified_style)
        ):
            continue
        if attr == "alignment-baseline" and (
            _alignment_baseline_is_supported_or_noop(element, specified_style)
            or _first_positioned_tspan_baseline_is_supported(
                element,
                specified_style,
                attr,
                ancestors,
                previous_siblings,
            )
        ):
            continue
        if attr == "direction" and _direction_is_supported_or_noop(element, specified_style):
            continue
        if attr == "unicode-bidi" and _unicode_bidi_has_no_effect(specified_style):
            continue
        if attr == "writing-mode" and _writing_mode_has_no_effect(specified_style):
            continue
        if attr == "dominant-baseline" and (
            _dominant_baseline_is_supported_or_noop(element, specified_style)
            or _first_positioned_tspan_baseline_is_supported(
                element,
                specified_style,
                attr,
                ancestors,
                previous_siblings,
            )
        ):
            continue
        if attr == "word-spacing" and _word_spacing_has_no_effect(element, specified_style):
            continue
        if attr == "word-spacing" and _word_spacing_is_supported(element, specified_style):
            continue
        if specified_style.get(attr) is not None:
            stats.add_unsupported_attribute(attr)
    _inspect_tspan_run_attributes(
        element,
        style,
        specified_style,
        css,
        refs,
        stats,
        ancestors,
        viewport,
        previous_siblings,
    )
    href = _href(element)
    if _local_name(element.tag) == "image":
        if not href or not _supported_data_image(href):
            stats.add_unsupported_attribute("href")
    elif _local_name(element.tag) == "use":
        if not _use_href_is_supported(element, refs):
            stats.add_unsupported_attribute("href")
    elif _local_name(element.tag) in {"linearGradient", "radialGradient"} and href is not None:
        if (
            (not href.startswith("#") or href[1:] not in refs)
            and _paint_server_is_referenced(element, css, refs, ancestors, viewport)
        ):
            stats.add_unsupported_attribute("href")
    tag = _local_name(element.tag)
    if tag == "use":
        _inspect_use_referenced_subtree_attributes(element, style, refs, css, viewport, stats)
    else:
        _inspect_visible_paint_server_channels(element, style, refs, css, viewport, stats)


def _inspect_visible_paint_server_channels(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
    stats: _CoverageStats,
) -> None:
    for attr in ("fill", "stroke"):
        value = style.get(attr)
        if not value:
            continue
        ref = _url_ref(value)
        if ref is None or ref[1].strip() or not _paint_channel_is_visible(element, style, viewport, attr):
            continue
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


def _inspect_use_referenced_paint_servers(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    ref_stack: frozenset[str] = frozenset(),
) -> None:
    ref_context = _use_reference_context(element, refs, viewport, ref_stack)
    if ref_context is None:
        return
    ref, ref_viewport, next_stack = ref_context
    _inspect_subtree_paint_servers(ref, css, refs, style, (element,), ref_viewport, stats, (), next_stack)


def _inspect_use_referenced_subtree_attributes(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    ref_stack: frozenset[str] = frozenset(),
) -> None:
    ref_context = _use_reference_context(element, refs, viewport, ref_stack)
    if ref_context is None:
        return
    ref, ref_viewport, next_stack = ref_context
    _inspect_referenced_subtree_attributes(ref, css, refs, style, (element,), ref_viewport, stats, (), next_stack)


def _inspect_referenced_subtree_attributes(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> None:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    specified_style = _computed_style(element, css, {}, ancestors, previous_siblings)
    if _is_display_none(style) or _has_non_rendering_geometry(element, style, viewport):
        return
    tag = _local_name(element.tag)
    no_visible_paint = _has_no_visible_paint(element, style, refs, css, viewport)
    unresolved_paint_server = _has_unresolved_paint_server(style, refs, css)
    if no_visible_paint and not unresolved_paint_server:
        return
    matrix = _style_transform_matrix(element, style, viewport)
    if tag == "use":
        _inspect_use_referenced_subtree_attributes(element, style, refs, css, viewport, stats, ref_stack)
        return
    if not _is_visibility_hidden(style):
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
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return
        _inspect_referenced_subtree_attributes(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            stats,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
        return
    previous_children: list[ET.Element] = []
    for child in element:
        _inspect_referenced_subtree_attributes(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            stats,
            tuple(previous_children),
            ref_stack,
        )
        previous_children.append(child)


def _inspect_subtree_paint_servers(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> None:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style) or _is_visibility_hidden(style):
        return
    tag = _local_name(element.tag)
    if tag == "use":
        _inspect_use_referenced_paint_servers(element, style, refs, css, viewport, stats, ref_stack)
        return
    if tag not in {"defs", "linearGradient", "pattern", "radialGradient", "stop"} and not _has_non_rendering_geometry(
        element, style, viewport
    ):
        _inspect_visible_paint_server_channels(element, style, refs, css, viewport, stats)
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return
        _inspect_subtree_paint_servers(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            stats,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
        return
    previous_children: list[ET.Element] = []
    for child in element:
        _inspect_subtree_paint_servers(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            stats,
            tuple(previous_children),
            ref_stack,
        )
        previous_children.append(child)


def _paint_channel_is_visible(
    element: ET.Element,
    style: dict[str, str],
    viewport: tuple[float, float],
    attr: str,
) -> bool:
    tag = _local_name(element.tag)
    if attr == "fill":
        if tag not in {"circle", "ellipse", "path", "polygon", "polyline", "rect", "text", "tspan", "use"}:
            return False
        return not _alpha_is_zero(style.get("opacity")) and not _alpha_is_zero(style.get("fill-opacity"))
    if tag not in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan", "use"}:
        return False
    stroke_width = _optional_length(style.get("stroke-width"), "diag", viewport)
    return (
        not _alpha_is_zero(style.get("opacity"))
        and not _alpha_is_zero(style.get("stroke-opacity"))
        and stroke_width != 0
    )


def _paint_server_is_referenced(
    paint_server: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
) -> bool:
    paint_server_id = paint_server.get("id")
    if not paint_server_id or not ancestors:
        return False
    return _subtree_references_paint_server(ancestors[0], paint_server_id, css, refs, {}, (), viewport)


def _subtree_references_paint_server(
    element: ET.Element,
    paint_server_id: str,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    tag = _local_name(element.tag)
    if tag == "defs":
        return False
    if tag != "svg":
        child_viewport = viewport
    elif ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    else:
        child_viewport = viewport
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return False
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_references_paint_server(
            ref,
            paint_server_id,
            css,
            refs,
            style,
            ancestors + (element,),
            ref_viewport,
            (),
            next_stack,
        )
    if (
        tag not in {"defs", "linearGradient", "pattern", "radialGradient", "stop"}
        and not _is_visibility_hidden(style)
        and not _has_non_rendering_geometry(element, style, viewport)
    ):
        for attr in ("fill", "stroke"):
            ref = _url_ref(style.get(attr))
            if (
                ref is not None
                and ref[0] == paint_server_id
                and not ref[1].strip()
                and _paint_channel_is_visible(element, style, viewport, attr)
            ):
                return True
    previous_children: list[ET.Element] = []
    for child in element:
        if _subtree_references_paint_server(
            child,
            paint_server_id,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            tuple(previous_children),
            ref_stack,
        ):
            return True
        previous_children.append(child)
    return False


def _inspect_tspan_run_attributes(
    element: ET.Element,
    style: dict[str, str],
    specified_style: dict[str, str],
    css: list[CssRule],
    refs: dict[str, ET.Element],
    stats: _CoverageStats,
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...],
) -> None:
    if _local_name(element.tag) != "tspan":
        return
    if not _tspan_position_is_supported_or_noop(element, style, css, refs, ancestors, viewport, previous_siblings):
        for attr in ("x", "y", "dx", "dy"):
            if element.get(attr) is not None and not _tspan_position_attr_has_no_effect(attr, element.get(attr, ""), viewport):
                stats.add_unsupported_attribute(attr)
    if (
        specified_style.get("text-anchor") is not None
        and not _first_positioned_tspan_text_anchor_is_supported(
            element,
            specified_style,
            ancestors,
            previous_siblings,
        )
        and not _tspan_text_anchor_has_no_effect(element, specified_style)
    ):
        stats.add_unsupported_attribute("text-anchor")


def _tspan_position_is_supported_or_noop(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    refs: dict[str, ET.Element],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...],
) -> bool:
    if not any(element.get(attr) is not None for attr in ("x", "y", "dx", "dy")):
        return True
    if not _subtree_has_visible_text(element, css, refs, style, ancestors, viewport):
        return True
    if all(
        element.get(attr) is None or _tspan_position_attr_has_no_effect(attr, element.get(attr, ""), viewport)
        for attr in ("x", "y", "dx", "dy")
    ):
        return True
    return _first_positioned_tspan_position_is_supported(
        element, ancestors, previous_siblings
    ) or _line_break_tspan_position_is_supported(element)


def _first_positioned_tspan_position_is_supported(
    element: ET.Element,
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
) -> bool:
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


def _line_break_tspan_position_is_supported(element: ET.Element) -> bool:
    return (
        element.get("x") is not None
        and element.get("dy") is not None
        and element.get("y") is None
        and element.get("dx") is None
    )


def _tspan_position_attr_has_no_effect(attr: str, value: str, viewport: tuple[float, float]) -> bool:
    if attr in {"x", "y"}:
        return False
    tokens = _css_value_tokens(value)
    if not tokens:
        return True
    axis = "x" if attr == "dx" else "y"
    return all((_optional_length(token, axis, viewport) or 0.0) == 0 for token in tokens)


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


def _tspan_text_anchor_has_no_effect(element: ET.Element, specified_style: dict[str, str]) -> bool:
    if _local_name(element.tag) != "tspan":
        return False
    value = specified_style.get("text-anchor")
    if value is None or value.strip().lower() not in {"", "start", "middle", "end"}:
        return False
    return element.get("x") is None and element.get("y") is None


def _first_positioned_tspan_baseline_is_supported(
    element: ET.Element,
    specified_style: dict[str, str],
    attr: str,
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
) -> bool:
    if _local_name(element.tag) != "tspan":
        return False
    value = specified_style.get(attr)
    if value is None or _dominant_baseline(value) is None:
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
    if tag in {"foreignObject", "rect", "image"}:
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
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, frozenset())
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return not _subtree_has_visible_rendering(ref, css, refs, style, (element,), ref_viewport, ref_stack=next_stack)
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


def _subtree_has_visible_rendering(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_visible_rendering(ref, css, refs, style, ancestors + (element,), ref_viewport, ref_stack=next_stack)
    if (
        not _is_visibility_hidden(style)
        and tag in RENDERING_ELEMENTS
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        return _subtree_has_visible_rendering(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        if _subtree_has_visible_rendering(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            tuple(previous_children),
            ref_stack,
        ):
            return True
        previous_children.append(child)
    return False


def _opacity_is_supported_or_noop(
    element: ET.Element,
    specified_style: dict[str, str],
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
) -> bool:
    value = specified_style.get("opacity")
    if value is None:
        return False
    alpha = _alpha_value(value)
    if alpha is None or alpha >= 1:
        return True
    tag = _local_name(element.tag)
    if tag in RENDERING_ELEMENTS:
        return True
    return _visible_rendering_descendant_count(element, css, refs, inherited_style, ancestors, viewport, limit=2) < 2


def _overflow_is_supported_or_noop(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
) -> bool:
    value = inherited_style.get("overflow")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "visible"}:
        return True
    if _local_name(element.tag) not in {"svg", "symbol"}:
        return True
    return not _subtree_has_visible_rendering(element, css, refs, inherited_style, ancestors, viewport)


def _visible_rendering_descendant_count(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    limit: int,
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> int:
    if limit <= 0:
        return 0
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return 0
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return 0
        ref, ref_viewport, next_stack = ref_context
        return _visible_rendering_descendant_count(
            ref,
            css,
            refs,
            style,
            ancestors + (element,),
            ref_viewport,
            limit,
            ref_stack=next_stack,
        )
    if not _is_visibility_hidden(style) and tag in RENDERING_ELEMENTS and not _has_non_rendering_geometry(
        element,
        style,
        viewport,
    ) and not _has_no_visible_paint(element, style, refs, css, viewport):
        return 1
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return 0
        return _visible_rendering_descendant_count(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            limit,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    total = 0
    previous_children: list[ET.Element] = []
    for child in element:
        total += _visible_rendering_descendant_count(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            limit - total,
            tuple(previous_children),
            ref_stack,
        )
        if total >= limit:
            return total
        previous_children.append(child)
    return total


def _subtree_clip_path_is_supported(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    inherited_matrix: tuple[float, float, float, float, float, float],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return True
    specified_style = _computed_style(element, css, {}, ancestors, previous_siblings)
    if specified_style.get("clip-path") is not None and specified_style.get("clip-path") != inherited_style.get("clip-path"):
        return not _subtree_has_visible_rendering(element, css, refs, style, ancestors, viewport, previous_siblings)
    matrix = _matrix_multiply(inherited_matrix, _style_transform_matrix(element, style, viewport))
    tag = _local_name(element.tag)
    if tag == "use":
        href = _href(element)
        if not href or not href.startswith("#") or href[1:] not in refs or href[1:] in ref_stack:
            return False
        ref = refs[href[1:]]
        use_matrix = _matrix_multiply(
            matrix,
            (1.0, 0.0, 0.0, 1.0, _length(element.get("x"), 0, "x", viewport), _length(element.get("y"), 0, "y", viewport)),
        )
        ref_viewport = viewport
        if _local_name(ref.tag) in {"svg", "symbol"}:
            use_width = _optional_length(element.get("width"), "x", viewport)
            use_height = _optional_length(element.get("height"), "y", viewport)
            use_matrix = _matrix_multiply(
                use_matrix,
                _viewbox_matrix(ref, use_width, use_height, element.get("preserveAspectRatio")),
            )
            ref_viewport = _viewport_size(ref, use_width, use_height)
        return _subtree_clip_path_is_supported(
            ref,
            css,
            refs,
            style,
            use_matrix,
            ancestors + (element,),
            ref_viewport,
            (),
            ref_stack | frozenset({href[1:]}),
        )
    if (
        not _is_visibility_hidden(style)
        and tag in RENDERING_ELEMENTS
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
    ):
        return _clip_path_is_supported(element, style, refs, matrix)
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return True
        return _subtree_clip_path_is_supported(
            selected,
            css,
            refs,
            style,
            matrix,
            ancestors + (element,),
            child_viewport,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        if not _subtree_clip_path_is_supported(
            child,
            css,
            refs,
            style,
            matrix,
            ancestors + (element,),
            child_viewport,
            tuple(previous_children),
            ref_stack,
        ):
            return False
        previous_children.append(child)
    return True


def _subtree_has_visible_fill(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    if _is_display_none(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_visible_fill(ref, css, refs, style, ancestors + (element,), ref_viewport, next_stack)
    if (
        not _is_visibility_hidden(style)
        and tag in {"circle", "ellipse", "path", "polygon", "polyline", "rect", "text", "tspan"}
        and not _has_non_rendering_geometry(element, style, viewport)
        and _has_visible_fill(element, style, refs, css, viewport)
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        selected_style = _computed_style(
            selected,
            css,
            style,
            ancestors + (element,),
            _previous_element_siblings(element, selected),
        )
        return _subtree_has_visible_fill(
            selected,
            css,
            refs,
            selected_style,
            ancestors + (element,),
            child_viewport,
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        if _subtree_has_visible_fill(
            child,
            css,
            refs,
            child_style,
            ancestors + (element,),
            child_viewport,
            ref_stack,
        ):
            return True
        previous_children.append(child)
    return False


def _subtree_has_visible_stroke(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    if _is_display_none(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_visible_stroke(ref, css, refs, style, ancestors + (element,), ref_viewport, next_stack)
    if (
        not _is_visibility_hidden(style)
        and tag in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan"}
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _stroke_has_no_effect(element, style, refs, css, viewport)
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        selected_style = _computed_style(
            selected,
            css,
            style,
            ancestors + (element,),
            _previous_element_siblings(element, selected),
        )
        return _subtree_has_visible_stroke(
            selected, css, refs, selected_style, ancestors + (element,), child_viewport, ref_stack
        )
    previous_children: list[ET.Element] = []
    for child in element:
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        if _subtree_has_visible_stroke(child, css, refs, child_style, ancestors + (element,), child_viewport, ref_stack):
            return True
        previous_children.append(child)
    return False


def _subtree_has_visible_text(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    if _is_display_none(style) or _is_visibility_hidden(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_visible_text(ref, css, refs, style, ancestors + (element,), ref_viewport, next_stack)
    if (
        tag in {"text", "tspan"}
        and _element_has_own_text(element)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        selected_style = _computed_style(
            selected,
            css,
            style,
            ancestors + (element,),
            _previous_element_siblings(element, selected),
        )
        return _subtree_has_visible_text(
            selected, css, refs, selected_style, ancestors + (element,), child_viewport, ref_stack
        )
    previous_children: list[ET.Element] = []
    for child in element:
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        if _subtree_has_visible_text(child, css, refs, child_style, ancestors + (element,), child_viewport, ref_stack):
            return True
        previous_children.append(child)
    return False


def _element_has_own_text(element: ET.Element) -> bool:
    if element.text and element.text.strip():
        return True
    return any(child.tail and child.tail.strip() for child in element)


def _subtree_marker_is_supported(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return True
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_marker_is_supported(
            ref,
            css,
            refs,
            style,
            ancestors + (element,),
            ref_viewport,
            (),
            next_stack,
        )
    if (
        not _is_visibility_hidden(style)
        and tag in RENDERING_ELEMENTS
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
    ):
        return _marker_is_supported(element, style, refs)
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return True
        return _subtree_marker_is_supported(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        if not _subtree_marker_is_supported(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            tuple(previous_children),
            ref_stack,
        ):
            return False
        previous_children.append(child)
    return True


def _subtree_marker_mid_has_no_effect(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return True
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_marker_mid_has_no_effect(
            ref,
            css,
            refs,
            style,
            ancestors + (element,),
            ref_viewport,
            (),
            next_stack,
        )
    if (
        not _is_visibility_hidden(style)
        and tag in RENDERING_ELEMENTS
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
    ):
        return _marker_mid_has_no_effect(element, style)
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return True
        return _subtree_marker_mid_has_no_effect(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        if not _subtree_marker_mid_has_no_effect(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            tuple(previous_children),
            ref_stack,
        ):
            return False
        previous_children.append(child)
    return True


def _use_reference_context(
    element: ET.Element,
    refs: dict[str, ET.Element],
    viewport: tuple[float, float],
    ref_stack: frozenset[str],
) -> tuple[ET.Element, tuple[float, float], frozenset[str]] | None:
    href = _href(element)
    if not href or not href.startswith("#") or href[1:] not in refs or href[1:] in ref_stack:
        return None
    ref = refs[href[1:]]
    ref_viewport = viewport
    if _local_name(ref.tag) in {"svg", "symbol"}:
        use_width = _optional_length(element.get("width"), "x", viewport)
        use_height = _optional_length(element.get("height"), "y", viewport)
        ref_viewport = _viewport_size(ref, use_width, use_height)
    return ref, ref_viewport, ref_stack | frozenset({href[1:]})


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


def _text_layout_attribute_has_no_effect(element: ET.Element, style: dict[str, str], attr: str) -> bool:
    if style.get(attr) is None:
        return False
    return _local_name(element.tag) in GRAPHIC_ELEMENTS_WITHOUT_TEXT_LAYOUT


def _css_none_or_normal_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    return value is not None and value.strip().lower() in {"", "normal", "none"}


def _css_auto_or_normal_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    return value is not None and value.strip().lower() in {"", "auto", "normal"}


def _font_size_adjust_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("font-size-adjust")
    return value is not None and value.strip().lower() in {"", "none", "normal"}


def _font_stretch_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("font-stretch")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "normal"}:
        return True
    return _optional_length(value, "x", (100.0, 100.0)) == 100.0


def _text_orientation_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("text-orientation")
    return value is not None and value.strip().lower() in {"", "mixed"}


def _glyph_orientation_has_no_effect(style: dict[str, str], attr: str) -> bool:
    value = style.get(attr)
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "auto"}:
        return True
    angle = _transform_angle_arg(normalized)
    if angle is None:
        return False
    remainder = angle % 360
    return min(remainder, abs(remainder - 360)) < 1e-9


def _font_kerning_has_no_effect(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("font-kerning")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "auto", "normal"}:
        return True
    return _text_has_no_kerning_pairs(element) and normalized == "none"


def _kerning_has_no_effect(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("kerning")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "auto", "normal"}:
        return True
    return _optional_length(value, "x", (0.0, 0.0)) == 0 or _text_has_no_kerning_pairs(element)


def _text_has_no_kerning_pairs(element: ET.Element) -> bool:
    tag = _local_name(element.tag)
    if tag == "text":
        text = _svg_text_content(element)
    elif tag == "tspan":
        text = "".join(element.itertext())
    else:
        return False
    return len(text) <= 1


def _baseline_shift_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("baseline-shift")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "baseline"}:
        return True
    return _zero_length_or_percentage_value(normalized)


def _zero_length_or_percentage_value(value: str) -> bool:
    match = re.fullmatch(rf"({NUMBER_RE})([a-z%]*)", value)
    if not match:
        resolved = _length(value, math.nan, "x", (100.0, 100.0))
        return math.isfinite(resolved) and resolved == 0
    unit = match.group(2)
    if unit not in {
        "",
        "%",
        "cap",
        "ch",
        "cm",
        "em",
        "ex",
        "ic",
        "in",
        "lh",
        "mm",
        "pc",
        "pt",
        "px",
        "q",
        "rem",
        "rlh",
        "vb",
        "vh",
        "vi",
        "vmax",
        "vmin",
        "vw",
    }:
        return False
    try:
        return float(match.group(1)) == 0
    except ValueError:
        return False


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


def _direction_is_supported_or_noop(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("direction")
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"", "ltr"}:
        return True
    return normalized == "rtl" and _local_name(element.tag) == "text"


def _unicode_bidi_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("unicode-bidi")
    return value is not None and value.strip().lower() in {"", "normal"}


def _writing_mode_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("writing-mode")
    return value is not None and value.strip().lower() in {"", "horizontal-tb", "lr", "lr-tb", "rl", "rl-tb"}


def _text_decoration_color_has_no_effect(
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    if not _has_visible_text_decoration(style):
        return True
    value = style.get("text-decoration-color")
    if value is None:
        return False
    if _has_only_visible_underline(style):
        color_value = style.get("color", "#000000") if value.strip().lower() == "currentcolor" else value
        decoration_color, _ = _parse_color(color_value)
        return decoration_color is not None
    paint = _svg_paint(style, refs, default_fill=True, css=css, viewport=viewport)
    if paint.fill in {None, "none"} or (paint.fill_alpha is not None and paint.fill_alpha < 1):
        return False
    color_value = style.get("color", "#000000") if value.strip().lower() == "currentcolor" else value
    decoration_color, decoration_alpha = _parse_color(color_value)
    return decoration_color == paint.fill and decoration_alpha in {None, 1.0}


def _text_decoration_style_is_supported_or_noop(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-style")
    shorthand = False
    if value is None:
        value = _text_decoration_shorthand_style(style.get("text-decoration"))
        shorthand = value is not None
    if value is None:
        return False
    if not _has_visible_text_decoration(style):
        return True
    normalized = value.strip().lower()
    if normalized in {"", "solid"}:
        return True
    if shorthand and not _text_decoration_shorthand_line_is_supported_or_noop(style.get("text-decoration")):
        return False
    return normalized in (TEXT_DECORATION_STYLE_TOKENS - {"solid"}) and _has_only_visible_underline(style)


def _text_decoration_thickness_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-thickness")
    if value is None:
        return False
    if not _has_visible_text_decoration(style) or value.strip().lower() in {"", "auto", "from-font"}:
        return True
    return _has_only_visible_underline(style) and _text_decoration_thickness_token(value)


def _text_decoration_skip_ink_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-skip-ink")
    if value is None:
        return False
    return not _has_visible_underline(style) or value.strip().lower() in {"", "auto"}


def _text_underline_offset_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("text-underline-offset")
    if value is None:
        return False
    return not _has_visible_underline(style) or value.strip().lower() in {"", "auto"}


def _text_decoration_shorthand_is_supported_or_noop(
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("text-decoration")
    if value is None:
        return False
    has_visible_decoration = _has_visible_text_decoration(style)
    if not _text_decoration_shorthand_line_is_supported_or_noop(
        value,
        allow_noop_thickness=not has_visible_decoration or _has_only_visible_underline(style),
    ):
        return False
    if not _text_decoration_shorthand_color_has_no_effect(style, refs, css, viewport):
        return False
    style_value = _text_decoration_shorthand_style(value)
    if style_value is None or style_value == "solid" or not has_visible_decoration:
        return True
    return style_value in (TEXT_DECORATION_STYLE_TOKENS - {"solid"}) and _has_only_visible_underline(style)


def _text_decoration_shorthand_line_is_supported_or_noop(
    value: str | None,
    *,
    allow_noop_thickness: bool = False,
) -> bool:
    if value is None:
        return False
    tokens = _text_decoration_tokens(value)
    known = TEXT_DECORATION_LINE_TOKENS | TEXT_DECORATION_STYLE_TOKENS | TEXT_DECORATION_NOOP_THICKNESS_TOKENS
    if allow_noop_thickness:
        known = known | {token for token in tokens if _text_decoration_thickness_token(token)}
    if any(token not in known and not _text_decoration_color_token(token) for token in tokens):
        return False
    line_tokens = {token for token in tokens if token in TEXT_DECORATION_LINE_TOKENS}
    if not line_tokens or line_tokens <= {"none"}:
        return True
    return line_tokens <= SUPPORTED_TEXT_DECORATION_LINE_TOKENS


def _text_decoration_shorthand_color_has_no_effect(
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("text-decoration")
    if value is None:
        return False
    color_tokens = [_text_decoration_color_token(part) for part in _text_decoration_tokens(value)]
    color_tokens = [token for token in color_tokens if token is not None]
    if not color_tokens:
        return True
    if len(color_tokens) > 1:
        return False
    if not _has_visible_text_decoration(style):
        return True
    if _has_only_visible_underline(style):
        color_value = style.get("color", "#000000") if color_tokens[0].lower() == "currentcolor" else color_tokens[0]
        decoration_color, _ = _parse_color(color_value)
        return decoration_color is not None
    paint = _svg_paint(style, refs, default_fill=True, css=css, viewport=viewport)
    if paint.fill in {None, "none"} or (paint.fill_alpha is not None and paint.fill_alpha < 1):
        return False
    color_value = style.get("color", "#000000") if color_tokens[0].lower() == "currentcolor" else color_tokens[0]
    decoration_color, decoration_alpha = _parse_color(color_value)
    return decoration_color == paint.fill and decoration_alpha in {None, 1.0}


def _text_decoration_color_token(value: str) -> str | None:
    normalized = value.strip().lower()
    if (
        normalized in TEXT_DECORATION_LINE_TOKENS
        or normalized in TEXT_DECORATION_STYLE_TOKENS
        or normalized in TEXT_DECORATION_NOOP_THICKNESS_TOKENS
        or _text_decoration_thickness_token(normalized)
    ):
        return None
    if normalized == "currentcolor":
        return value
    color, _ = _parse_color(value)
    return value if color is not None else None


def _text_decoration_thickness_token(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"auto", "from-font"}:
        return True
    resolved = _length(normalized, math.nan, "x", (100.0, 100.0))
    return math.isfinite(resolved) and resolved >= 0


def _text_decoration_shorthand_style(value: str | None) -> str | None:
    if value is None:
        return None
    for token in _text_decoration_tokens(value):
        if token in TEXT_DECORATION_STYLE_TOKENS:
            return token
    return None


def _text_decoration_line_is_supported_or_noop(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    tokens = {token for token in _text_decoration_tokens(value) if token in TEXT_DECORATION_LINE_TOKENS}
    if not tokens or tokens <= {"none"}:
        return True
    return tokens <= SUPPORTED_TEXT_DECORATION_LINE_TOKENS


def _has_visible_text_decoration(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    tokens = {token for token in _text_decoration_tokens(value) if token in TEXT_DECORATION_LINE_TOKENS - {"none"}}
    return bool(tokens & {"underline", "line-through"})


def _has_only_visible_underline(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    tokens = {token for token in _text_decoration_tokens(value) if token in TEXT_DECORATION_LINE_TOKENS - {"none"}}
    return "underline" in tokens and "line-through" not in tokens


def _has_visible_underline(style: dict[str, str]) -> bool:
    value = style.get("text-decoration-line", style.get("text-decoration"))
    if value is None:
        return False
    return "underline" in _text_decoration_tokens(value)


def _text_decoration_tokens(value: str) -> list[str]:
    return [token.lower() for token in _css_value_tokens(value)]


def _transform_origin_is_supported(
    element: ET.Element,
    style: dict[str, str],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("transform-origin")
    if value is None:
        return False
    return _transform_origin(value, viewport, element, style) is not None


def _transform_origin_has_no_effect(style: dict[str, str]) -> bool:
    value = style.get("transform-origin")
    if value is None:
        return False
    transform = style.get("transform")
    return transform is None or transform.strip().lower() in {"", "none"}


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
    if attr == "isolation":
        return normalized in {"", "auto"}
    if attr == "vector-effect":
        return normalized in {"none", "non-scaling-stroke"}
    return False


def _clip_rule_has_no_effect(ancestors: tuple[ET.Element, ...]) -> bool:
    return not any(_local_name(ancestor.tag) == "clipPath" for ancestor in ancestors)


def _marker_mid_has_no_effect(element: ET.Element, style: dict[str, str]) -> bool:
    value = style.get("marker-mid")
    if value is None or value.strip().lower() in {"", "none"}:
        return False
    tag = _local_name(element.tag)
    if tag == "line":
        return True
    if tag == "polyline":
        return len(_parse_points(element.get("points", ""))) <= 2
    if tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        return bool(path and len(path[0]) <= 2)
    return False


def _path_length_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("pathLength")
    if value is None:
        return False
    dasharray = style.get("stroke-dasharray")
    if dasharray is None or dasharray.strip().lower() in {"", "none"}:
        return True
    if _dash_pattern_period(dasharray, viewport) is None:
        return True
    return _stroke_has_no_effect(element, style, refs, css, viewport)


def _preserve_aspect_ratio_is_supported_or_noop(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
) -> bool:
    value = style.get("preserveAspectRatio")
    if value is None:
        return False
    tag = _local_name(element.tag)
    if tag in {"svg", "symbol"}:
        return True
    if tag == "use":
        href = _href(element)
        if not href or not href.startswith("#"):
            return False
        return _local_name(refs.get(href[1:], ET.Element("")).tag) in {"svg", "symbol"}
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
    tag = _local_name(element.tag)
    if tag == "text":
        text = _svg_text_content(element)
    elif tag == "tspan":
        text = "".join(element.itertext())
    else:
        return False
    return _svg_word_spacing_is_supported(style, text, (0.0, 0.0))


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
    normalized = " ".join(value.strip().lower().split())
    if normalized in {"normal", "fill", "fill stroke", "fill stroke markers"}:
        return True
    paint = _svg_paint(style, refs, default_fill=_local_name(element.tag) != "line", css=css, viewport=viewport)
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    if not (has_fill and has_stroke):
        return True
    if normalized in {"markers fill stroke", "fill markers stroke"}:
        return not _has_visible_marker(style)
    return False


def _has_visible_marker(style: dict[str, str]) -> bool:
    for attr in ("marker", "marker-start", "marker-mid", "marker-end"):
        value = style.get(attr)
        if value is not None and value.strip().lower() not in {"", "none"}:
            return True
    return False


def _subtree_has_unsupported_paint_order(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    if _is_display_none(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_unsupported_paint_order(ref, css, refs, style, ancestors + (element,), ref_viewport, next_stack)
    if (
        not _is_visibility_hidden(style)
        and tag in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan"}
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _has_no_visible_paint(element, style, refs, css, viewport)
        and style.get("paint-order") is not None
        and not _paint_order_has_no_effect(element, style, refs, css, viewport)
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        selected_style = _computed_style(
            selected,
            css,
            style,
            ancestors + (element,),
            _previous_element_siblings(element, selected),
        )
        return _subtree_has_unsupported_paint_order(
            selected,
            css,
            refs,
            selected_style,
            ancestors + (element,),
            child_viewport,
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        if _subtree_has_unsupported_paint_order(
            child,
            css,
            refs,
            child_style,
            ancestors + (element,),
            child_viewport,
            ref_stack,
        ):
            return True
        previous_children.append(child)
    return False


def _fill_rule_has_no_effect(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
) -> bool:
    value = style.get("fill-rule")
    if value is None:
        return False
    return not _subtree_has_visible_fill(element, css, refs, style, ancestors, viewport)


def _has_visible_fill(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    viewport: tuple[float, float],
) -> bool:
    tag = _local_name(element.tag)
    if tag in {"text", "tspan"} and not _svg_text_content(element):
        return False
    paint = _svg_paint(style, refs, default_fill=tag != "line", css=css, viewport=viewport)
    return paint.fill not in {None, "none"}


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
    if period is None:
        return True
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


def _subtree_has_unsupported_stroke_line_enum(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    attr: str,
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    if _is_display_none(style):
        return False
    tag = _local_name(element.tag)
    if tag == "use":
        ref_context = _use_reference_context(element, refs, viewport, ref_stack)
        if ref_context is None:
            return False
        ref, ref_viewport, next_stack = ref_context
        return _subtree_has_unsupported_stroke_line_enum(
            ref, css, refs, style, ancestors + (element,), ref_viewport, attr, next_stack
        )
    if (
        not _is_visibility_hidden(style)
        and tag in {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text", "tspan"}
        and not _has_non_rendering_geometry(element, style, viewport)
        and not _stroke_has_no_effect(element, style, refs, css, viewport)
        and _stroke_line_enum_is_unsupported(attr, style.get(attr))
    ):
        return True
    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return False
        selected_style = _computed_style(
            selected,
            css,
            style,
            ancestors + (element,),
            _previous_element_siblings(element, selected),
        )
        return _subtree_has_unsupported_stroke_line_enum(
            selected,
            css,
            refs,
            selected_style,
            ancestors + (element,),
            child_viewport,
            attr,
            ref_stack,
        )
    previous_children: list[ET.Element] = []
    for child in element:
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        if _subtree_has_unsupported_stroke_line_enum(
            child,
            css,
            refs,
            child_style,
            ancestors + (element,),
            child_viewport,
            attr,
            ref_stack,
        ):
            return True
        previous_children.append(child)
    return False


def _stroke_line_enum_is_unsupported(attr: str, value: str | None) -> bool:
    if value is None:
        return False
    if attr == "stroke-linecap":
        return _svg_linecap(value) is None
    return _svg_linejoin(value) is None


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
    return value.strip().lower() in {"none", "normal", "small-caps", "all-small-caps"}


def _path_is_supported(path_data: str) -> bool:
    return not path_data or _parse_linear_path(path_data) is not None


def _use_href_is_supported(element: ET.Element, refs: dict[str, ET.Element]) -> bool:
    href = _href(element)
    return bool(href and href.startswith("#") and href[1:] in refs)


def _marker_is_supported(element: ET.Element, style: dict[str, str], refs: dict[str, ET.Element]) -> bool:
    if not _converter_marker_is_supported(element, style, refs):
        return False
    return all(_marker_reference_is_arrow_like(value, refs) for value in _visible_marker_values(style))


def _visible_marker_values(style: dict[str, str]) -> list[str]:
    values: list[str] = []
    for attr in ("marker-start", "marker-end"):
        value = style[attr] if attr in style else style.get("marker")
        if value is not None and value.strip().lower() not in {"", "none"}:
            values.append(value)
    return values


def _marker_reference_is_arrow_like(value: str, refs: dict[str, ET.Element]) -> bool:
    ref = _url_ref(value)
    if ref is None or ref[1].strip():
        return False
    marker = refs.get(ref[0])
    if marker is None or _local_name(marker.tag) != "marker":
        return False
    return _marker_definition_is_arrow_like(marker)


def _marker_definition_is_arrow_like(marker: ET.Element) -> bool:
    for child in marker:
        tag = _local_name(child.tag)
        if tag == "path":
            path = _parse_linear_path(child.get("d", ""))
            if path is not None and path[1] and len(path[0]) == 3:
                return True
        elif tag in {"polygon", "polyline"}:
            points = _parse_points(child.get("points", ""))
            if len(points) == 3:
                return True
    return False


def _use_referenced_subtree_is_supported(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    ref_context = _use_reference_context(element, refs, viewport, ref_stack)
    if ref_context is None:
        return False
    ref, ref_viewport, next_stack = ref_context
    return _referenced_subtree_is_supported(
        ref,
        css,
        refs,
        inherited_style,
        ancestors + (element,),
        ref_viewport,
        stats,
        (),
        next_stack,
    )


def _referenced_subtree_is_supported(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    stats: _CoverageStats,
    previous_siblings: tuple[ET.Element, ...] = (),
    ref_stack: frozenset[str] = frozenset(),
) -> bool:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return True
    tag = _local_name(element.tag)
    if tag == "use":
        return _use_referenced_subtree_is_supported(element, css, refs, style, ancestors, viewport, stats, ref_stack)
    if _is_visibility_hidden(style) or _has_non_rendering_geometry(element, style, viewport) or _has_no_visible_paint(
        element,
        style,
        refs,
        css,
        viewport,
    ):
        return True
    if tag == "path":
        if not _path_is_supported(element.get("d", "")):
            _inspect_path(element.get("d", ""), stats)
            return False
    elif tag in {"polygon", "polyline"}:
        if len(_parse_points(element.get("points", ""))) < 2:
            return False
    elif tag == "image":
        href = _href(element)
        if not href or not _supported_data_image(href):
            return False
    elif tag == "switch":
        selected = _switch_selected_child(element)
        if selected is None:
            return len(element) == 0
        return _referenced_subtree_is_supported(
            selected,
            css,
            refs,
            style,
            ancestors + (element,),
            viewport,
            stats,
            _previous_element_siblings(element, selected),
            ref_stack,
        )
    elif tag not in SUPPORTED_ELEMENTS and tag not in IGNORED_ELEMENTS:
        return False

    child_viewport = viewport
    if tag == "svg" and ancestors:
        child_viewport = _viewport_size(
            element,
            _optional_length(element.get("width"), "x", viewport),
            _optional_length(element.get("height"), "y", viewport),
        )
    previous_children: list[ET.Element] = []
    for child in element:
        if not _referenced_subtree_is_supported(
            child,
            css,
            refs,
            style,
            ancestors + (element,),
            child_viewport,
            stats,
            tuple(previous_children),
            ref_stack,
        ):
            return False
        previous_children.append(child)
    return True


def _supported_element_issue(tag: str) -> str:
    if tag == "path":
        return "path:unsupported-command"
    if tag in {"polygon", "polyline"}:
        return f"{tag}:invalid-points"
    if tag == "foreignObject":
        return "foreignObject"
    if tag == "switch":
        return "switch:unsupported-branch"
    return f"{tag}:unsupported-reference"
