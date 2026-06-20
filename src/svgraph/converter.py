from __future__ import annotations

import base64
import binascii
import colorsys
import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Iterable
from xml.dom import minidom
from xml.etree import ElementTree as ET

EMU_PER_PX = 9525

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_SVG = "http://www.w3.org/2000/svg"

ET.register_namespace("a", NS_A)
ET.register_namespace("p", NS_P)
ET.register_namespace("r", NS_R)
ET.register_namespace("", NS_SVG)

NUMBER_RE = r"[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[eE][-+]?\d+)?"
TEXT_DECORATION_LINE_TOKENS = {"none", "underline", "line-through", "overline", "blink"}
TEXT_DECORATION_STYLE_TOKENS = {"solid", "dashed", "dotted", "double", "wavy"}


def qn(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


@dataclass(frozen=True)
class Paint:
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float | None = None
    fill_alpha: float | None = None
    stroke_alpha: float | None = None
    stroke_linecap: str | None = None
    stroke_linejoin: str | None = None
    stroke_dasharray: str | None = None
    stroke_miterlimit: float | None = None
    stroke_compound: str | None = None
    marker_start: str | None = None
    marker_end: str | None = None


@dataclass(frozen=True)
class TextRun:
    text: str
    paint: Paint
    break_before: bool = False
    font_size: float | None = None
    font_weight: str | None = None
    font_style: str | None = None
    font_family: str | None = None
    font_variant: str | None = None
    text_decoration: str | None = None
    text_decoration_style: str | None = None
    text_decoration_color: str | None = None
    text_decoration_alpha: float | None = None
    text_decoration_thickness: float | None = None
    text_baseline_shift: str | None = None
    letter_spacing: float | None = None


@dataclass(frozen=True)
class Shape:
    kind: str
    x: float
    y: float
    width: float
    height: float
    paint: Paint
    flip_h: bool = False
    flip_v: bool = False
    points: tuple[tuple[float, float], ...] = ()
    closed: bool = False
    text: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    font_style: str | None = None
    font_family: str | None = None
    font_variant: str | None = None
    text_decoration: str | None = None
    text_decoration_style: str | None = None
    text_decoration_color: str | None = None
    text_decoration_alpha: float | None = None
    text_decoration_thickness: float | None = None
    text_anchor: str | None = None
    text_baseline: str | None = None
    text_direction: str | None = None
    text_wrap: str | None = None
    text_baseline_shift: str | None = None
    letter_spacing: float | None = None
    rx: float | None = None
    ry: float | None = None
    image_href: str | None = None
    image_src_rect: tuple[int, int, int, int] | None = None
    rotation: float | None = None
    text_runs: tuple[TextRun, ...] = ()
    table_border_left: Paint | None = None
    table_border_right: Paint | None = None
    table_border_top: Paint | None = None
    table_border_bottom: Paint | None = None


@dataclass(frozen=True)
class SvgTable:
    x: float
    y: float
    columns: tuple[float, ...]
    rows: tuple[float, ...]
    cells: tuple[tuple["SvgTableCell", ...], ...]


@dataclass(frozen=True)
class SvgTableCell:
    rect: Shape | None
    text: Shape | None = None
    column_span: int = 1
    row_span: int = 1
    h_merge: bool = False
    v_merge: bool = False
    border_left: Paint | None = None
    border_right: Paint | None = None
    border_top: Paint | None = None
    border_bottom: Paint | None = None


CssDeclaration = tuple[str, bool]
CssRule = tuple[str, dict[str, CssDeclaration], tuple[int, int, int], int]


def svg_to_drawingml(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    container = ET.Element(qn(NS_P, "spTree"))
    nv_grp = ET.SubElement(container, qn(NS_P, "nvGrpSpPr"))
    ET.SubElement(nv_grp, qn(NS_P, "cNvPr"), {"id": "1", "name": "SVGraph Group"})
    ET.SubElement(nv_grp, qn(NS_P, "cNvGrpSpPr"))
    ET.SubElement(nv_grp, qn(NS_P, "nvPr"))
    grp_sp_pr = ET.SubElement(container, qn(NS_P, "grpSpPr"))
    xfrm = ET.SubElement(grp_sp_pr, qn(NS_A, "xfrm"))
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "ext"), {"cx": "0", "cy": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chOff"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chExt"), {"cx": "0", "cy": "0"})

    shapes = list(_svg_shapes(root))
    table, shapes = _extract_svg_table(shapes)
    index = 2
    if table is not None:
        container.append(_svg_table_to_dml(table, index))
        index += 1
    for offset, shape in enumerate(shapes, start=index):
        container.append(_shape_to_dml(shape, offset))

    return _pretty_xml(container)


def drawingml_to_svg(drawingml_text: str) -> str:
    root = ET.fromstring(drawingml_text)
    shapes = list(_dml_shapes(root))
    bounds = [_shape_bounds(shape) for shape in shapes]
    min_x = min((left for left, _, _, _ in bounds), default=0.0)
    min_y = min((top for _, top, _, _ in bounds), default=0.0)
    max_x = max((right for _, _, right, _ in bounds), default=0.0)
    max_y = max((bottom for _, _, _, bottom in bounds), default=0.0)
    view_x = min(0.0, min_x)
    view_y = min(0.0, min_y)
    width = max_x - view_x
    height = max_y - view_y
    svg = ET.Element(
        qn(NS_SVG, "svg"),
        {
            "viewBox": f"{_fmt(view_x)} {_fmt(view_y)} {_fmt(width)} {_fmt(height)}",
            "width": _fmt(width),
            "height": _fmt(height),
        },
    )
    _append_svg_marker_defs(svg, shapes)
    for shape in shapes:
        svg.append(_shape_to_svg(shape))
    return _pretty_xml(svg)


def _svg_shapes(root: ET.Element) -> Iterable[Shape]:
    css = _collect_css(root)
    refs = _collect_refs(root)
    yield from _svg_shapes_walk(root, css, refs, {}, _root_viewbox_matrix(root), set(), (), _viewport_size(root), ())


def _svg_shapes_walk(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    inherited_matrix: tuple[float, float, float, float, float, float],
    ref_stack: set[str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
    previous_siblings: tuple[ET.Element, ...],
) -> Iterable[Shape]:
    tag = _local_name(element.tag)
    if tag in {"defs", "style"}:
        return

    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    if _is_display_none(style):
        return
    visibility_hidden = _is_visibility_hidden(style)
    matrix = _matrix_multiply(inherited_matrix, _style_transform_matrix(element, style, viewport))
    child_viewport = viewport
    if tag == "svg" and ancestors:
        svg_width = _optional_length(element.get("width"), "x", viewport)
        svg_height = _optional_length(element.get("height"), "y", viewport)
        matrix = _matrix_multiply(
            matrix,
            _parse_transform(f"translate({_length(element.get('x'), 0, 'x', viewport)} {_length(element.get('y'), 0, 'y', viewport)})"),
        )
        matrix = _matrix_multiply(matrix, _viewbox_matrix(element, svg_width, svg_height))
        child_viewport = _viewport_size(element, svg_width, svg_height)
    if tag == "use":
        href = _href(element)
        if href and href.startswith("#") and href[1:] in refs and href[1:] not in ref_stack:
            ref = refs[href[1:]]
            use_matrix = _matrix_multiply(
                matrix,
                _parse_transform(f"translate({_length(element.get('x'), 0, 'x', viewport)} {_length(element.get('y'), 0, 'y', viewport)})"),
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
            yield from _svg_shapes_walk(ref, css, refs, style, use_matrix, ref_stack | {href[1:]}, ancestors + (element,), ref_viewport, ())
        return
    if tag == "switch":
        selected = _switch_selected_child(element)
        if selected is not None:
            previous_children = _previous_element_siblings(element, selected)
            yield from _svg_shapes_walk(selected, css, refs, style, matrix, ref_stack, ancestors + (element,), child_viewport, previous_children)
        return
    if tag == "foreignObject" and not visibility_hidden:
        foreign_table_shapes = _svg_foreign_object_table_shapes(element, style, css, refs, matrix, viewport)
        if foreign_table_shapes:
            yield from foreign_table_shapes
            return

    shape = None if visibility_hidden else _svg_shape_from_element(element, tag, style, matrix, refs, viewport, css, ancestors)
    if shape is not None:
        shape = _apply_rect_clip(shape, style, refs, matrix)
    if shape is not None and not _shape_has_visible_content(shape):
        shape = None
    if shape is not None:
        yield shape

    previous_children: list[ET.Element] = []
    for child in element:
        yield from _svg_shapes_walk(child, css, refs, style, matrix, ref_stack, ancestors + (element,), child_viewport, tuple(previous_children))
        previous_children.append(child)


def _svg_shape_from_element(
    element: ET.Element,
    tag: str,
    style: dict[str, str],
    matrix: tuple[float, float, float, float, float, float],
    refs: dict[str, ET.Element] | None = None,
    viewport: tuple[float, float] = (0.0, 0.0),
    css: list[CssRule] | None = None,
    ancestors: tuple[ET.Element, ...] = (),
) -> Shape | None:
    refs = refs or {}
    css = css or []
    paint = _svg_paint(style, refs, default_fill=tag != "line", css=css, viewport=viewport)
    scaled_paint = _scale_paint(paint, _stroke_transform_scale(style, matrix))
    plain_paint = _paint_without_markers(scaled_paint)
    if tag == "rect":
        x = _geometry_length(element, style, "x", 0, "x", viewport)
        y = _geometry_length(element, style, "y", 0, "y", viewport)
        width = _geometry_length(element, style, "width", 0, "x", viewport)
        height = _geometry_length(element, style, "height", 0, "y", viewport)
        if width <= 0 or height <= 0:
            return None
        rx = _optional_nonnegative_geometry_length(element, style, "rx", "x", viewport)
        ry = _optional_nonnegative_geometry_length(element, style, "ry", "y", viewport)
        if rx is None and ry is None:
            rx = ry = 0.0
        elif rx is None:
            rx = ry
        elif ry is None:
            ry = rx
        shape = _transformed_rect_shape(x, y, width, height, rx, ry, matrix, plain_paint)
        if shape is not None:
            return shape
        return _freeform_shape(_transform_points(_rect_points(x, y, width, height), matrix), plain_paint, closed=True)
    if tag == "circle":
        cx = _geometry_length(element, style, "cx", 0, "x", viewport)
        cy = _geometry_length(element, style, "cy", 0, "y", viewport)
        r = _geometry_length(element, style, "r", 0, "diag", viewport)
        if r <= 0:
            return None
        return _ellipse_shape(cx, cy, r, r, plain_paint, matrix)
    if tag == "ellipse":
        cx = _geometry_length(element, style, "cx", 0, "x", viewport)
        cy = _geometry_length(element, style, "cy", 0, "y", viewport)
        rx = _geometry_length(element, style, "rx", 0, "x", viewport)
        ry = _geometry_length(element, style, "ry", 0, "y", viewport)
        if rx <= 0 or ry <= 0:
            return None
        return _ellipse_shape(cx, cy, rx, ry, plain_paint, matrix)
    if tag == "line":
        p1 = _apply_matrix(
            matrix,
            (
                _geometry_length(element, style, "x1", 0, "x", viewport),
                _geometry_length(element, style, "y1", 0, "y", viewport),
            ),
        )
        p2 = _apply_matrix(
            matrix,
            (
                _geometry_length(element, style, "x2", 0, "x", viewport),
                _geometry_length(element, style, "y2", 0, "y", viewport),
            ),
        )
        return Shape(
            "line",
            min(p1[0], p2[0]),
            min(p1[1], p2[1]),
            abs(p2[0] - p1[0]),
            abs(p2[1] - p1[1]),
            scaled_paint,
            flip_h=p2[0] < p1[0],
            flip_v=p2[1] < p1[1],
        )
    if tag in {"polygon", "polyline"}:
        points = _transform_points(_parse_points(element.get("points", "")), matrix)
        return _freeform_shape(points, plain_paint if tag == "polygon" else scaled_paint, closed=tag == "polygon") if points else None
    if tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        if path:
            points, closed = path
            return _freeform_shape(_transform_points(points, matrix), plain_paint if closed else scaled_paint, closed=closed)
    if tag == "text":
        text = _svg_text_content(element, style, css, ancestors)
        if text:
            font_size = _svg_font_size(style.get("font-size")) * _matrix_scale(matrix)
            text_runs = _svg_text_runs(element, style, css, refs, ancestors, matrix, viewport)
            x, y = _apply_matrix(matrix, _svg_text_position(element, viewport))
            text_length = _svg_text_length(style, text, viewport)
            natural_width = max(font_size * max(len(line) for line in text.split("\n")) * 0.9, font_size * 2)
            width = text_length or natural_width + _svg_word_spacing_extra(style, text, viewport)
            anchor = _svg_text_anchor(element, style, css, ancestors)
            if anchor == "middle":
                x -= width / 2
            elif anchor == "end":
                x -= width
            baseline = _svg_text_baseline(element, style, css, ancestors)
            height = font_size * 1.4 * len(text.split("\n"))
            if baseline == "middle":
                y -= height / 2
            elif baseline == "text-after-edge":
                y -= height
            else:
                y -= font_size
            decoration_color, decoration_alpha = _text_decoration_color(style)
            return Shape(
                "text",
                x,
                y,
                width,
                height,
                _text_paint(style, refs, css, _stroke_transform_scale(style, matrix), viewport),
                text=text,
                font_size=font_size,
                font_weight=style.get("font-weight"),
                font_style=style.get("font-style"),
                font_family=_font_family(style.get("font-family")),
                font_variant=_font_variant(style.get("font-variant")),
                text_decoration=style.get("text-decoration"),
                text_decoration_style=_text_decoration_style(
                    style.get("text-decoration-style"),
                    style.get("text-decoration"),
                ),
                text_decoration_color=decoration_color,
                text_decoration_alpha=decoration_alpha,
                text_decoration_thickness=_text_decoration_thickness(style, viewport),
                text_anchor=anchor,
                text_baseline=baseline,
                text_direction=_text_direction(style.get("direction")),
                text_baseline_shift=_baseline_shift(style.get("baseline-shift")),
                letter_spacing=_svg_text_effective_letter_spacing(style, text, font_size, viewport),
                rotation=_svg_text_rotation(element, style, css, ancestors),
                text_runs=text_runs,
            )
    if tag == "image":
        href = _href(element)
        if href and _supported_data_image(href):
            x = _geometry_length(element, style, "x", 0, "x", viewport)
            y = _geometry_length(element, style, "y", 0, "y", viewport)
            width = _geometry_length(element, style, "width", 0, "x", viewport)
            height = _geometry_length(element, style, "height", 0, "y", viewport)
            if width <= 0 or height <= 0:
                return None
            x, y, width, height, src_rect = _image_preserve_aspect_ratio_rect(
                x,
                y,
                width,
                height,
                href,
                style.get("preserveAspectRatio"),
            )
            return _transformed_image_shape(x, y, width, height, matrix, href, _image_alpha(style), src_rect)
    return None


def _svg_foreign_object_table_shapes(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
    viewport: tuple[float, float],
) -> tuple[Shape, ...]:
    table = _foreign_object_table(element)
    if table is None:
        return ()
    x = _geometry_length(element, style, "x", 0, "x", viewport)
    y = _geometry_length(element, style, "y", 0, "y", viewport)
    width = _geometry_length(element, style, "width", 0, "x", viewport)
    height = _geometry_length(element, style, "height", 0, "y", viewport)
    transformed = _transformed_rect_shape(x, y, width, height, 0, 0, matrix, Paint(fill="none", stroke="none"))
    if transformed is None or transformed.rotation is not None or transformed.flip_h or transformed.flip_v:
        return ()
    grid = _html_table_grid(table)
    if width <= 0 or height <= 0 or not grid:
        return ()
    rows, column_count = grid
    if column_count <= 0:
        return ()
    scale_x = transformed.width / width
    scale_y = transformed.height / height
    table_style = _html_table_cell_style(element, table, css, style)
    table_width = _html_table_element_size(table, "width", width) or width
    table_height = _html_table_element_size(table, "height", height) or height
    caption = _html_table_caption(table)
    caption_style = _html_table_cell_style(element, caption, css, style) if caption is not None else {}
    caption_text = _html_table_cell_text(caption) if caption is not None else ""
    caption_height = _html_table_caption_height(caption_text, caption_style, table_height)
    grid_height = max(0.0, table_height - caption_height)
    table_x = _html_table_x_offset(table, width, table_width)
    table_y = _html_table_y_offset(table)
    caption_side = _html_table_caption_side(caption_style)
    grid_y = table_y + caption_height if caption_text and caption_side == "top" else table_y
    spacing_x, spacing_y = _html_table_border_spacing(table_style, table_width, grid_height or table_height)
    if _html_table_has_spans(rows):
        spacing_x = spacing_y = 0.0
    row_total = max(0.0, grid_height or table_height)
    column_total = table_width
    if spacing_x > 0 or spacing_y > 0:
        row_total = max(0.0, row_total - spacing_y * (len(rows) + 1))
        column_total = max(0.0, column_total - spacing_x * (column_count + 1))
    row_heights = _html_table_row_heights(table, len(rows), row_total or grid_height or table_height)
    row_edges = [0.0]
    for row_height in row_heights:
        row_edges.append(row_edges[-1] + row_height)
    column_widths = _html_table_column_widths(table, column_count, column_total or table_width)
    column_edges = [0.0]
    for column_width in column_widths:
        column_edges.append(column_edges[-1] + column_width)
    column_backgrounds = _html_table_column_backgrounds(element, table, column_count, css)
    shapes: list[Shape] = []
    if caption_text:
        caption_y = table_y if caption_side == "top" else table_y + grid_height
        shapes.append(
            _html_table_caption_shape(
                caption,
                caption_text,
                caption_style,
                transformed.x + table_x * scale_x,
                transformed.y + caption_y * scale_y,
                table_width * scale_x,
                caption_height * scale_y,
                css,
                max(scale_x, scale_y),
            )
        )
    if spacing_x > 0 or spacing_y > 0:
        return tuple(
            shapes
            + list(
                _html_table_spaced_table_shapes(
                    element,
                    table,
                    rows,
                    column_widths,
                    row_heights,
                    column_backgrounds,
                    transformed.x + table_x * scale_x,
                    transformed.y + grid_y * scale_y,
                    spacing_x,
                    spacing_y,
                    scale_x,
                    scale_y,
                    css,
                    style,
                )
            )
        )
    for row_index, row in enumerate(rows):
        for column_index, cell, column_span, row_span in row:
            end_column = min(column_count, column_index + column_span)
            end_row = min(len(rows), row_index + row_span)
            cell_x = transformed.x + (table_x + column_edges[column_index]) * scale_x
            cell_y = transformed.y + (grid_y + row_edges[row_index]) * scale_y
            cell_width = (column_edges[end_column] - column_edges[column_index]) * scale_x
            cell_height = (row_edges[end_row] - row_edges[row_index]) * scale_y
            cell_style = _html_table_cell_style(element, cell, css, style)
            fill, fill_alpha = _html_table_cell_background_fill(
                element,
                table,
                cell,
                column_backgrounds[column_index] if column_index < len(column_backgrounds) else (),
                css,
            )
            stroke, stroke_alpha = _html_border_stroke(cell_style)
            border_left, border_right, border_top, border_bottom = _html_table_cell_border_paints(cell_style)
            shapes.append(
                Shape(
                    "rect",
                    cell_x,
                    cell_y,
                    cell_width,
                    cell_height,
                    Paint(
                        fill=fill or "#ffffff",
                        stroke=stroke or "#000000",
                        stroke_width=_html_border_width(cell_style),
                        fill_alpha=fill_alpha,
                        stroke_alpha=stroke_alpha,
                        stroke_dasharray=_html_border_dasharray(cell_style),
                        stroke_compound=_html_border_compound(cell_style),
                    ),
                    table_border_left=border_left,
                    table_border_right=border_right,
                    table_border_top=border_top,
                    table_border_bottom=border_bottom,
                )
            )
            text = _html_table_cell_text(cell)
            if text:
                left_inset, top_inset, right_inset, bottom_inset = _html_padding_insets(
                    cell_style,
                    scale_x,
                    scale_y,
                    cell_width,
                    cell_height,
                )
                font_size = _svg_font_size(cell_style.get("font-size")) * max(scale_x, scale_y)
                text_fill, text_fill_alpha = _html_text_fill(cell_style)
                shapes.append(
                    Shape(
                        "text",
                        cell_x + left_inset,
                        cell_y + top_inset,
                        max(0.0, cell_width - left_inset - right_inset),
                        max(0.0, cell_height - top_inset - bottom_inset),
                        Paint(fill=text_fill or "#000000", stroke="none", fill_alpha=text_fill_alpha),
                        text=text,
                        font_size=font_size,
                        font_weight=cell_style.get("font-weight") or ("bold" if _local_name(cell.tag) == "th" else None),
                        font_style=cell_style.get("font-style"),
                        font_family=_font_family(cell_style.get("font-family")),
                        font_variant=_font_variant(cell_style.get("font-variant")),
                        text_anchor=_html_table_cell_text_anchor(cell, cell_style),
                        text_baseline=_html_vertical_align(cell_style) or "middle",
                        text_direction=_text_direction(cell_style.get("direction")),
                        text_wrap=_html_text_wrap(cell_style),
                        letter_spacing=_svg_letter_spacing(cell_style, (0.0, 0.0)),
                        text_runs=_html_table_cell_text_runs(cell, css, cell_style, max(scale_x, scale_y)),
                    )
                )
    return tuple(shapes)


def _foreign_object_table(element: ET.Element) -> ET.Element | None:
    tables = [descendant for descendant in element.iter() if descendant is not element and _local_name(descendant.tag) == "table"]
    return tables[0] if len(tables) == 1 else None


def _html_table_caption(table: ET.Element) -> ET.Element | None:
    return next((child for child in table if _local_name(child.tag) == "caption"), None)


def _html_table_caption_side(style: dict[str, str]) -> str:
    return "bottom" if (style.get("caption-side") or "").strip().lower() == "bottom" else "top"


def _html_table_caption_height(text: str, style: dict[str, str], table_height: float) -> float:
    if not text or table_height <= 0:
        return 0.0
    return min(max(1.0, _svg_font_size(style.get("font-size")) * 1.4), table_height / 3)


def _html_table_caption_shape(
    caption: ET.Element | None,
    text: str,
    style: dict[str, str],
    x: float,
    y: float,
    width: float,
    height: float,
    css: list[CssRule],
    scale: float,
) -> Shape:
    fill, fill_alpha = _html_text_fill(style)
    return Shape(
        "text",
        x,
        y,
        width,
        height,
        Paint(fill=fill or "#000000", stroke="none", fill_alpha=fill_alpha),
        text=text,
        font_size=_svg_font_size(style.get("font-size")) * scale,
        font_weight=style.get("font-weight"),
        font_style=style.get("font-style"),
        font_family=_font_family(style.get("font-family")),
        font_variant=_font_variant(style.get("font-variant")),
        text_anchor=_html_text_anchor(style) or "middle",
        text_baseline="middle",
        text_direction=_text_direction(style.get("direction")),
        text_wrap=_html_text_wrap(style),
        letter_spacing=_svg_letter_spacing(style, (0.0, 0.0)),
        text_runs=_html_table_cell_text_runs(caption, css, style, scale) if caption is not None else (),
    )


def _html_table_cell_style(
    foreign_object: ET.Element,
    cell: ET.Element,
    css: list[CssRule],
    inherited_style: dict[str, str],
) -> dict[str, str]:
    path = _element_path(foreign_object, cell)
    if not path:
        return _computed_style(cell, css, inherited_style, (foreign_object,), ())
    style = inherited_style
    for index, node in enumerate(path[1:], start=1):
        parent = path[index - 1]
        style = _computed_style(
            node,
            css,
            style,
            tuple(path[:index]),
            _previous_element_siblings(parent, node),
        )
    return style


def _html_table_cell_text(cell: ET.Element) -> str:
    raw = _html_text_with_breaks(cell)
    lines = [" ".join(line.split()) for line in raw.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _html_table_cell_text_runs(
    cell: ET.Element,
    css: list[CssRule],
    inherited_style: dict[str, str],
    scale: float,
) -> tuple[TextRun, ...]:
    runs: list[TextRun] = []
    _append_html_text_runs(cell, css, inherited_style, (), (), scale, runs, False)
    if not runs:
        return ()
    if len(runs) == 1 and not runs[0].break_before:
        default_run = _html_text_run(runs[0].text, inherited_style, scale, False)
        if runs[0] == default_run:
            return ()
    return tuple(runs)


def _append_html_text_runs(
    element: ET.Element,
    css: list[CssRule],
    style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
    scale: float,
    runs: list[TextRun],
    break_before: bool,
) -> bool:
    text = _html_text_segment(element.text or "")
    if text:
        runs.append(_html_text_run(text, style, scale, break_before))
        break_before = False
    previous_children: list[ET.Element] = []
    for child in element:
        child_tag = _local_name(child.tag)
        if child_tag == "br":
            break_before = True
        else:
            child_style = _html_inline_style(child, css, style, ancestors + (element,), tuple(previous_children))
            if child_tag in {"div", "p", "li"} and runs:
                break_before = True
            break_before = _append_html_text_runs(
                child,
                css,
                child_style,
                ancestors + (element,),
                tuple(previous_children),
                scale,
                runs,
                break_before,
            )
            if child_tag in {"div", "p", "li"}:
                break_before = True
        tail = _html_text_segment(child.tail or "")
        if tail:
            runs.append(_html_text_run(tail, style, scale, break_before))
            break_before = False
        previous_children.append(child)
    return break_before


def _html_inline_style(
    element: ET.Element,
    css: list[CssRule],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...],
) -> dict[str, str]:
    style = _computed_style(element, css, inherited_style, ancestors, previous_siblings)
    tag = _local_name(element.tag)
    if tag in {"b", "strong"} and style.get("font-weight", "normal").strip().lower() == "normal":
        style["font-weight"] = "bold"
    if tag in {"i", "em"} and style.get("font-style", "normal").strip().lower() == "normal":
        style["font-style"] = "italic"
    if tag == "u":
        _add_html_text_decoration(style, "underline")
    if tag in {"s", "strike", "del"}:
        _add_html_text_decoration(style, "line-through")
    if tag == "sup":
        style["baseline-shift"] = "super"
    if tag == "sub":
        style["baseline-shift"] = "sub"
    if style.get("baseline-shift") is None:
        baseline_shift = _html_inline_baseline_shift(style.get("vertical-align"))
        if baseline_shift is not None:
            style["baseline-shift"] = baseline_shift
    return style


def _html_inline_baseline_shift(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in {"super", "sub"} else None


def _add_html_text_decoration(style: dict[str, str], decoration: str) -> None:
    current = style.get("text-decoration", "")
    tokens = _text_decoration_line_tokens(current)
    if decoration not in tokens:
        style["text-decoration"] = f"{current} {decoration}".strip()


def _html_text_run(text: str, style: dict[str, str], scale: float, break_before: bool) -> TextRun:
    fill, fill_alpha = _html_text_fill(style)
    decoration_color, decoration_alpha = _text_decoration_color(style)
    return TextRun(
        text=text,
        paint=Paint(fill=fill or "#000000", stroke="none", fill_alpha=fill_alpha),
        break_before=break_before,
        font_size=_svg_font_size(style.get("font-size")) * scale,
        font_weight=style.get("font-weight"),
        font_style=style.get("font-style"),
        font_family=_font_family(style.get("font-family")),
        font_variant=_font_variant(style.get("font-variant")),
        text_decoration=style.get("text-decoration"),
        text_decoration_style=_text_decoration_style(style.get("text-decoration-style"), style.get("text-decoration")),
        text_decoration_color=decoration_color,
        text_decoration_alpha=decoration_alpha,
        text_decoration_thickness=_text_decoration_thickness(style, (0.0, 0.0)),
        text_baseline_shift=_baseline_shift(style.get("baseline-shift")),
        letter_spacing=_svg_letter_spacing(style, (0.0, 0.0)),
    )


def _html_text_segment(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text)
    return normalized if normalized.strip() else ""


def _html_text_with_breaks(element: ET.Element) -> str:
    parts = [element.text or ""]
    for child in element:
        child_tag = _local_name(child.tag)
        if child_tag == "br":
            parts.append("\n")
        else:
            if child_tag in {"div", "p", "li"} and "".join(parts).strip() and not "".join(parts).endswith("\n"):
                parts.append("\n")
            parts.append(_html_text_with_breaks(child))
            if child_tag in {"div", "p", "li"}:
                parts.append("\n")
        parts.append(child.tail or "")
    return "".join(parts)


def _element_path(root: ET.Element, target: ET.Element) -> tuple[ET.Element, ...]:
    if root is target:
        return (root,)
    for child in root:
        child_path = _element_path(child, target)
        if child_path:
            return (root, *child_path)
    return ()


def _html_table_grid(table: ET.Element) -> tuple[list[list[tuple[int, ET.Element, int, int]]], int] | None:
    source_rows = [
        [cell for cell in row if _local_name(cell.tag) in {"td", "th"}]
        for row in table.iter()
        if _local_name(row.tag) == "tr"
    ]
    source_rows = [row for row in source_rows if row]
    if not source_rows:
        return None
    occupied: dict[tuple[int, int], bool] = {}
    rows: list[list[tuple[int, ET.Element, int, int]]] = []
    column_count = 0
    for row_index, source_row in enumerate(source_rows):
        row_cells: list[tuple[int, ET.Element, int, int]] = []
        column_index = 0
        for cell in source_row:
            while occupied.get((row_index, column_index), False):
                column_index += 1
            column_span = max(1, _dml_int(cell.get("colspan"), 1) or 1)
            row_span = max(1, _dml_int(cell.get("rowspan"), 1) or 1)
            row_cells.append((column_index, cell, column_span, row_span))
            for occupied_row in range(row_index, row_index + row_span):
                for occupied_column in range(column_index, column_index + column_span):
                    occupied[(occupied_row, occupied_column)] = True
            column_index += column_span
            column_count = max(column_count, column_index)
        rows.append(row_cells)
    if any(row_index + row_span > len(rows) for row_index, row in enumerate(rows) for _, _, _, row_span in row):
        return None
    if any(
        len({column for column in range(column_count) if occupied.get((row_index, column), False)}) != column_count
        for row_index in range(len(rows))
    ):
        return None
    return rows, column_count


def _html_table_has_spans(rows: list[list[tuple[int, ET.Element, int, int]]]) -> bool:
    return any(column_span > 1 or row_span > 1 for row in rows for _, _, column_span, row_span in row)


def _html_table_row_heights(table: ET.Element, row_count: int, total_height: float) -> tuple[float, ...]:
    specs: list[float | None] = []
    for row in table.iter():
        if _local_name(row.tag) != "tr" or not any(_local_name(cell.tag) in {"td", "th"} for cell in row):
            continue
        style_height = _parse_style(row.get("style", "")).get("height")
        height = _html_table_size_value(style_height, total_height)
        if height is None:
            height = _html_table_size_value(row.get("height"), total_height)
        specs.append(height)
        if len(specs) >= row_count:
            break
    return _html_table_sizes(specs, row_count, total_height)


def _html_table_column_widths(table: ET.Element, column_count: int, total_width: float) -> tuple[float, ...]:
    specs: list[float | None] = []
    for child in table:
        tag = _local_name(child.tag)
        if tag == "colgroup":
            col_elements = [col for col in child if _local_name(col.tag) == "col"]
        elif tag == "col":
            col_elements = [child]
        else:
            col_elements = []
        for col in col_elements:
            width = _html_table_col_width(col, total_width)
            span = max(1, _dml_int(col.get("span"), 1) or 1)
            specs.extend(width for _ in range(span))
            if len(specs) >= column_count:
                break
        if len(specs) >= column_count:
            break
    if not specs:
        specs = _html_table_first_row_column_widths(table, column_count, total_width)
    return _html_table_sizes(specs, column_count, total_width)


def _html_table_column_backgrounds(
    foreign_object: ET.Element,
    table: ET.Element,
    column_count: int,
    css: list[CssRule],
) -> tuple[tuple[tuple[str, float | None], ...], ...]:
    backgrounds: list[tuple[tuple[str, float | None], ...]] = []
    for child in table:
        tag = _local_name(child.tag)
        if tag == "colgroup":
            colgroup_fill = _html_element_background_fill(foreign_object, child, css)
            col_elements = [col for col in child if _local_name(col.tag) == "col"]
        elif tag == "col":
            colgroup_fill = (None, None)
            col_elements = [child]
        else:
            continue
        for col in col_elements:
            layers = tuple(
                (fill, alpha)
                for fill, alpha in (
                    _html_element_background_fill(foreign_object, col, css),
                    colgroup_fill,
                )
                if fill is not None
            )
            span = max(1, _dml_int(col.get("span"), 1) or 1)
            backgrounds.extend(layers for _ in range(span))
            if len(backgrounds) >= column_count:
                break
        if len(backgrounds) >= column_count:
            break
    if len(backgrounds) < column_count:
        backgrounds.extend(() for _ in range(column_count - len(backgrounds)))
    return tuple(backgrounds[:column_count])


def _html_table_element_size(table: ET.Element, axis: str, total_size: float) -> float | None:
    style_size = _parse_style(table.get("style", "")).get(axis)
    size = _html_table_size_value(style_size, total_size)
    if size is not None:
        return size
    return _html_table_size_value(table.get(axis), total_size)


def _html_table_x_offset(table: ET.Element, foreign_object_width: float, table_width: float) -> float:
    extra = max(0.0, foreign_object_width - table_width)
    style = _parse_style(table.get("style", ""))
    margin_left = _html_margin_side(style, "left")
    margin_right = _html_margin_side(style, "right")
    if margin_left == "auto" and margin_right == "auto":
        return extra / 2
    if margin_left == "auto":
        return extra
    if isinstance(margin_left, float):
        return margin_left
    align = (style.get("text-align") or table.get("align") or "").strip().lower()
    if align in {"center", "middle"}:
        return extra / 2
    if align in {"right", "end"}:
        return extra
    return 0.0


def _html_table_y_offset(table: ET.Element) -> float:
    margin_top = _html_margin_side(_parse_style(table.get("style", "")), "top")
    return margin_top if isinstance(margin_top, float) else 0.0


def _html_margin_side(style: dict[str, str], side: str) -> float | str | None:
    value = style.get(f"margin-{side}")
    if value is None:
        value = _html_margin_shorthand_side(style.get("margin"), side)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "auto":
        return "auto"
    length = _html_first_length(normalized)
    return max(0.0, length) if length is not None else None


def _html_margin_shorthand_side(value: str | None, side: str) -> str | None:
    if value is None:
        return None
    tokens = _css_value_tokens(value)[:4]
    if not tokens:
        return None
    if len(tokens) == 1:
        top = right = bottom = left = tokens[0]
    elif len(tokens) == 2:
        top = bottom = tokens[0]
        right = left = tokens[1]
    elif len(tokens) == 3:
        top, right, bottom = tokens
        left = right
    else:
        top, right, bottom, left = tokens
    return {"top": top, "right": right, "bottom": bottom, "left": left}.get(side)


def _html_table_first_row_column_widths(table: ET.Element, column_count: int, total_width: float) -> list[float | None]:
    specs: list[float | None] = []
    for row in table.iter():
        if _local_name(row.tag) != "tr":
            continue
        for cell in row:
            if _local_name(cell.tag) not in {"td", "th"}:
                continue
            width = _html_table_cell_width(cell, total_width)
            column_span = max(1, _dml_int(cell.get("colspan"), 1) or 1)
            column_width = width / column_span if width is not None else None
            specs.extend(column_width for _ in range(column_span))
            if len(specs) >= column_count:
                return specs
        if specs:
            return specs
    return specs


def _html_table_sizes(specs: list[float | None], count: int, total_size: float) -> tuple[float, ...]:
    if count <= 0:
        return ()
    specs = specs[:count]
    if len(specs) < count:
        specs.extend([None] * (count - len(specs)))
    fixed_sum = sum(size for size in specs if size is not None)
    missing = sum(1 for size in specs if size is None)
    if fixed_sum <= 0:
        return tuple(total_size / count for _ in range(count))
    if missing:
        fallback = (total_size - fixed_sum) / missing if fixed_sum < total_size else total_size / count
        sizes = tuple(size if size is not None and size > 0 else fallback for size in specs)
        size_sum = sum(sizes)
        scale = total_size / size_sum if size_sum > 0 else 1.0
        return tuple(size * scale for size in sizes)
    scale = total_size / fixed_sum if fixed_sum > 0 else 1.0
    return tuple(size * scale for size in specs if size is not None)


def _html_table_border_spacing(
    style: dict[str, str],
    table_width: float,
    table_height: float,
) -> tuple[float, float]:
    if (style.get("border-collapse") or "").strip().lower() == "collapse":
        return 0.0, 0.0
    value = style.get("border-spacing")
    if value is None:
        return 0.0, 0.0
    tokens = _css_value_tokens(value)
    if not tokens:
        return 0.0, 0.0
    horizontal = _html_first_length(tokens[0])
    vertical = _html_first_length(tokens[1]) if len(tokens) > 1 else horizontal
    spacing_x = max(0.0, horizontal if horizontal is not None else 0.0)
    spacing_y = max(0.0, vertical if vertical is not None else 0.0)
    return (
        _html_table_fit_spacing(spacing_x, table_width),
        _html_table_fit_spacing(spacing_y, table_height),
    )


def _html_table_fit_spacing(spacing: float, total_size: float) -> float:
    if spacing <= 0 or total_size <= 0:
        return 0.0
    return min(spacing, total_size / 3)


def _html_table_spaced_table_shapes(
    foreign_object: ET.Element,
    table: ET.Element,
    rows: list[list[tuple[int, ET.Element, int, int]]],
    column_widths: tuple[float, ...],
    row_heights: tuple[float, ...],
    column_backgrounds: tuple[tuple[tuple[str, float | None], ...], ...],
    x: float,
    y: float,
    spacing_x: float,
    spacing_y: float,
    scale_x: float,
    scale_y: float,
    css: list[CssRule],
    inherited_style: dict[str, str],
) -> tuple[Shape, ...]:
    table_fill, table_fill_alpha = _html_element_background_fill(foreign_object, table, css)
    cells = {
        (row_index, column_index): cell
        for row_index, row in enumerate(rows)
        for column_index, cell, _, _ in row
    }
    x_tracks = _html_table_spaced_tracks(column_widths, spacing_x)
    y_tracks = _html_table_spaced_tracks(row_heights, spacing_y)
    shapes: list[Shape] = []
    for top, bottom, row_index in y_tracks:
        for left, right, column_index in x_tracks:
            width = (right - left) * scale_x
            height = (bottom - top) * scale_y
            if width <= 0 or height <= 0:
                continue
            if row_index is None or column_index is None:
                shapes.append(
                    Shape(
                        "rect",
                        x + left * scale_x,
                        y + top * scale_y,
                        width,
                        height,
                        Paint(fill=table_fill or "none", stroke="none", stroke_width=0.0, fill_alpha=table_fill_alpha),
                    )
                )
                continue
            cell = cells.get((row_index, column_index))
            if cell is None:
                continue
            cell_x = x + left * scale_x
            cell_y = y + top * scale_y
            cell_style = _html_table_cell_style(foreign_object, cell, css, inherited_style)
            fill, fill_alpha = _html_table_cell_background_fill(
                foreign_object,
                table,
                cell,
                column_backgrounds[column_index] if column_index < len(column_backgrounds) else (),
                css,
            )
            stroke, stroke_alpha = _html_border_stroke(cell_style)
            border_left, border_right, border_top, border_bottom = _html_table_cell_border_paints(cell_style)
            shapes.append(
                Shape(
                    "rect",
                    cell_x,
                    cell_y,
                    width,
                    height,
                    Paint(
                        fill=fill or "#ffffff",
                        stroke=stroke or "#000000",
                        stroke_width=_html_border_width(cell_style),
                        fill_alpha=fill_alpha,
                        stroke_alpha=stroke_alpha,
                        stroke_dasharray=_html_border_dasharray(cell_style),
                        stroke_compound=_html_border_compound(cell_style),
                    ),
                    table_border_left=border_left,
                    table_border_right=border_right,
                    table_border_top=border_top,
                    table_border_bottom=border_bottom,
                )
            )
            text = _html_table_cell_text(cell)
            if not text:
                continue
            left_inset, top_inset, right_inset, bottom_inset = _html_padding_insets(
                cell_style,
                scale_x,
                scale_y,
                width,
                height,
            )
            font_size = _svg_font_size(cell_style.get("font-size")) * max(scale_x, scale_y)
            text_fill, text_fill_alpha = _html_text_fill(cell_style)
            shapes.append(
                Shape(
                    "text",
                    cell_x + left_inset,
                    cell_y + top_inset,
                    max(0.0, width - left_inset - right_inset),
                    max(0.0, height - top_inset - bottom_inset),
                    Paint(fill=text_fill or "#000000", stroke="none", fill_alpha=text_fill_alpha),
                    text=text,
                    font_size=font_size,
                    font_weight=cell_style.get("font-weight") or ("bold" if _local_name(cell.tag) == "th" else None),
                    font_style=cell_style.get("font-style"),
                    font_family=_font_family(cell_style.get("font-family")),
                    font_variant=_font_variant(cell_style.get("font-variant")),
                    text_anchor=_html_table_cell_text_anchor(cell, cell_style),
                    text_baseline=_html_vertical_align(cell_style) or "middle",
                    text_direction=_text_direction(cell_style.get("direction")),
                    text_wrap=_html_text_wrap(cell_style),
                    letter_spacing=_svg_letter_spacing(cell_style, (0.0, 0.0)),
                    text_runs=_html_table_cell_text_runs(cell, css, cell_style, max(scale_x, scale_y)),
                )
            )
    return tuple(shapes)


def _html_table_spaced_tracks(sizes: tuple[float, ...], spacing: float) -> tuple[tuple[float, float, int | None], ...]:
    tracks: list[tuple[float, float, int | None]] = []
    offset = 0.0
    if spacing > 0:
        tracks.append((offset, offset + spacing, None))
        offset += spacing
    for index, size in enumerate(sizes):
        tracks.append((offset, offset + size, index))
        offset += size
        if spacing > 0:
            tracks.append((offset, offset + spacing, None))
            offset += spacing
    return tuple(tracks)


def _html_table_col_width(col: ET.Element, total_width: float) -> float | None:
    style_width = _parse_style(col.get("style", "")).get("width")
    width = _html_table_size_value(style_width, total_width)
    if width is not None:
        return width
    return _html_table_size_value(col.get("width"), total_width)


def _html_table_cell_width(cell: ET.Element, total_width: float) -> float | None:
    style_width = _parse_style(cell.get("style", "")).get("width")
    width = _html_table_size_value(style_width, total_width)
    if width is not None:
        return width
    return _html_table_size_value(cell.get("width"), total_width)


def _html_table_size_value(value: str | None, total_size: float) -> float | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    if not stripped:
        return None
    if stripped.endswith("%"):
        percent = _num(stripped[:-1], math.nan)
        return max(0.0, total_size * percent / 100) if math.isfinite(percent) else None
    width = _html_first_length(stripped)
    return max(0.0, width) if width is not None else None


def _html_background_color(style: dict[str, str]) -> str | None:
    return _html_color(style.get("background-color")) or _html_first_color(style.get("background"))


def _html_background_fill(style: dict[str, str]) -> tuple[str | None, float | None]:
    color, alpha = _html_color_value(style.get("background-color"))
    if color is not None:
        return color, alpha
    return _html_first_color_value(style.get("background"))


def _html_table_cell_background_fill(
    foreign_object: ET.Element,
    table: ET.Element,
    cell: ET.Element,
    column_backgrounds: tuple[tuple[str, float | None], ...],
    css: list[CssRule],
) -> tuple[str | None, float | None]:
    path = _element_path(foreign_object, cell)
    row = next((ancestor for ancestor in reversed(path[:-1]) if _local_name(ancestor.tag) == "tr"), None)
    row_group = next(
        (
            ancestor
            for ancestor in reversed(path[:-1])
            if _local_name(ancestor.tag) in {"thead", "tbody", "tfoot"}
        ),
        None,
    )
    candidates = [
        _html_element_background_fill(foreign_object, element, css)
        for element in (cell, row, row_group)
        if element is not None
    ]
    candidates.extend(column_backgrounds)
    candidates.append(_html_element_background_fill(foreign_object, table, css))
    for fill, alpha in candidates:
        if fill is not None:
            return fill, alpha
    return None, None


def _html_element_background_fill(
    foreign_object: ET.Element,
    element: ET.Element,
    css: list[CssRule],
) -> tuple[str | None, float | None]:
    path = _element_path(foreign_object, element)
    if path:
        ancestors = tuple(path[:-1])
        previous_siblings = _previous_element_siblings(path[-2], element) if len(path) > 1 else ()
    else:
        ancestors = (foreign_object,)
        previous_siblings = ()
    return _html_background_fill(_computed_style(element, css, {}, ancestors, previous_siblings))


def _html_border_color(style: dict[str, str]) -> str | None:
    color, _ = _html_border_stroke(style)
    return color


def _html_border_stroke(style: dict[str, str]) -> tuple[str | None, float | None]:
    if _html_border_is_none(style):
        return "none", None
    color, alpha = _html_first_color_value(style.get("border-color"))
    if color is not None:
        return color, alpha
    return _html_first_color_value(style.get("border"))


def _html_border_width(style: dict[str, str]) -> float:
    if _html_border_is_none(style):
        return 0.0
    border_width = style.get("border-width")
    if border_width:
        width = _html_first_length(border_width)
        return max(0.0, width if width is not None else 1.0)
    border = style.get("border")
    if border:
        width = _html_first_length(border)
        return max(0.0, width if width is not None else 1.0)
    return 1.0


def _html_border_dasharray(style: dict[str, str]) -> str | None:
    tokens = _html_border_style_tokens(style)
    if "dotted" in tokens:
        return "1 1"
    if "dashed" in tokens:
        return "3 3"
    return None


def _html_border_compound(style: dict[str, str]) -> str | None:
    tokens = _html_border_style_tokens(style)
    return "dbl" if "double" in tokens else None


def _html_table_cell_border_paints(style: dict[str, str]) -> tuple[Paint, Paint, Paint, Paint]:
    return (
        _html_border_side_paint(style, "left"),
        _html_border_side_paint(style, "right"),
        _html_border_side_paint(style, "top"),
        _html_border_side_paint(style, "bottom"),
    )


def _html_border_side_paint(style: dict[str, str], side: str) -> Paint:
    side_style = _html_border_side_style(style, side)
    stroke, stroke_alpha = _html_border_stroke(side_style)
    return Paint(
        fill="none",
        stroke=stroke or "#000000",
        stroke_width=_html_border_width(side_style),
        stroke_alpha=stroke_alpha,
        stroke_dasharray=_html_border_dasharray(side_style),
        stroke_compound=_html_border_compound(side_style),
    )


def _html_border_side_style(style: dict[str, str], side: str) -> dict[str, str]:
    side_prefix = f"border-{side}"
    side_shorthand = style.get(side_prefix)
    if side_shorthand is None:
        effective = {
            key: value
            for key in ("border", "border-style", "border-width", "border-color")
            if (value := style.get(key)) is not None
        }
    else:
        effective = {"border": side_shorthand}
    for suffix, property_name in (
        ("style", "border-style"),
        ("width", "border-width"),
        ("color", "border-color"),
    ):
        if (value := style.get(f"{side_prefix}-{suffix}")) is not None:
            effective[property_name] = value
    return effective


def _html_border_style_tokens(style: dict[str, str]) -> list[str]:
    return [
        token.strip(",").lower()
        for value in (style.get("border-style"), style.get("border"))
        if value
        for token in _css_value_tokens(value)
    ]


def _html_padding_insets(
    style: dict[str, str],
    scale_x: float,
    scale_y: float,
    cell_width: float,
    cell_height: float,
) -> tuple[float, float, float, float]:
    default = 4.0 * max(scale_x, scale_y)
    if not any(key in style for key in ("padding", "padding-left", "padding-top", "padding-right", "padding-bottom")):
        inset = min(default, cell_width / 4, cell_height / 4)
        return inset, inset, inset, inset
    top, right, bottom, left = _html_padding_sides(style)
    left_inset = min(max(0.0, left * scale_x), cell_width)
    right_inset = min(max(0.0, right * scale_x), max(0.0, cell_width - left_inset))
    top_inset = min(max(0.0, top * scale_y), cell_height)
    bottom_inset = min(max(0.0, bottom * scale_y), max(0.0, cell_height - top_inset))
    return left_inset, top_inset, right_inset, bottom_inset


def _html_padding_sides(style: dict[str, str]) -> tuple[float, float, float, float]:
    shorthand = _html_padding_shorthand(style.get("padding"))
    top, right, bottom, left = shorthand or (0.0, 0.0, 0.0, 0.0)
    top = _html_padding_side(style.get("padding-top"), top)
    right = _html_padding_side(style.get("padding-right"), right)
    bottom = _html_padding_side(style.get("padding-bottom"), bottom)
    left = _html_padding_side(style.get("padding-left"), left)
    return top, right, bottom, left


def _html_padding_shorthand(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    lengths = [_html_padding_side(token, 0.0) for token in _css_value_tokens(value)[:4]]
    if not lengths:
        return None
    if len(lengths) == 1:
        top = right = bottom = left = lengths[0]
    elif len(lengths) == 2:
        top = bottom = lengths[0]
        right = left = lengths[1]
    elif len(lengths) == 3:
        top, right, bottom = lengths
        left = right
    else:
        top, right, bottom, left = lengths
    return top, right, bottom, left


def _html_padding_side(value: str | None, default: float) -> float:
    if value is None:
        return default
    length = _html_first_length(value)
    return max(0.0, length if length is not None else default)


def _html_text_color(style: dict[str, str]) -> str | None:
    return _html_color(style.get("color"))


def _html_text_fill(style: dict[str, str]) -> tuple[str | None, float | None]:
    return _html_color_value(style.get("color"))


def _html_text_anchor(style: dict[str, str]) -> str | None:
    value = style.get("text-align")
    if value is None:
        return None
    normalized = value.strip().lower()
    return {
        "center": "middle",
        "middle": "middle",
        "right": "end",
        "end": "end",
        "left": "start",
        "start": "start",
    }.get(normalized)


def _html_table_cell_text_anchor(cell: ET.Element, style: dict[str, str]) -> str | None:
    anchor = _html_text_anchor(style)
    if anchor is not None:
        return anchor
    return "middle" if _local_name(cell.tag) == "th" else None


def _html_vertical_align(style: dict[str, str]) -> str | None:
    value = style.get("vertical-align")
    if value is None:
        return None
    normalized = value.strip().lower()
    return {
        "top": "text-before-edge",
        "text-top": "text-before-edge",
        "middle": "middle",
        "center": "middle",
        "bottom": "text-after-edge",
        "text-bottom": "text-after-edge",
    }.get(normalized)


def _html_text_wrap(style: dict[str, str]) -> str | None:
    white_space = " ".join((style.get("white-space") or "").strip().lower().split())
    return "none" if white_space in {"nowrap", "pre", "pre-line", "pre-wrap"} else None


def _html_color(value: str | None) -> str | None:
    color, _ = _parse_color(value)
    return color


def _html_color_value(value: str | None) -> tuple[str | None, float | None]:
    return _parse_color(value)


def _html_first_color(value: str | None) -> str | None:
    color, _ = _html_first_color_value(value)
    return color


def _html_first_color_value(value: str | None) -> tuple[str | None, float | None]:
    if not value:
        return None, None
    for token in _css_value_tokens(value):
        color, alpha = _html_color_value(token.strip(","))
        if color is not None:
            return color, alpha
    return None, None



def _html_first_length(value: str) -> float | None:
    for token in _css_value_tokens(value):
        token = token.strip(",").lower()
        if token in {"thin", "medium", "thick"}:
            return {"thin": 1.0, "medium": 3.0, "thick": 5.0}[token]
        if re.fullmatch(r"(?:calc\(.+\)|[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[eE][-+]?\d+)?(?:px|pt|pc|in|cm|mm|q)?)", token):
            return _num(token, 0.0)
    return None


def _html_border_is_none(style: dict[str, str]) -> bool:
    values = [style.get("border-style"), style.get("border")]
    return any(token.strip(",").lower() in {"none", "hidden"} for value in values if value for token in _css_value_tokens(value))


def _foreign_object_table_is_supported(
    element: ET.Element,
    style: dict[str, str],
    matrix: tuple[float, float, float, float, float, float],
    viewport: tuple[float, float],
) -> bool:
    table = _foreign_object_table(element)
    if table is None:
        return False
    width = _geometry_length(element, style, "width", 0, "x", viewport)
    height = _geometry_length(element, style, "height", 0, "y", viewport)
    if width <= 0 or height <= 0 or _html_table_grid(table) is None:
        return False
    x = _geometry_length(element, style, "x", 0, "x", viewport)
    y = _geometry_length(element, style, "y", 0, "y", viewport)
    transformed = _transformed_rect_shape(x, y, width, height, 0, 0, matrix, Paint(fill="none", stroke="none"))
    return transformed is not None and transformed.rotation is None and not transformed.flip_h and not transformed.flip_v


def _geometry_length(
    element: ET.Element,
    style: dict[str, str],
    attr: str,
    default: float,
    axis: str,
    viewport: tuple[float, float],
) -> float:
    return _length(style.get(attr, element.get(attr)), default, axis, viewport)


def _optional_nonnegative_geometry_length(
    element: ET.Element,
    style: dict[str, str],
    attr: str,
    axis: str,
    viewport: tuple[float, float],
) -> float | None:
    value = style.get(attr, element.get(attr))
    if value is None:
        return None
    parsed = _length(value, math.nan, axis, viewport)
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _shape_has_visible_content(shape: Shape) -> bool:
    if shape.kind == "image":
        return shape.paint.fill_alpha is None or shape.paint.fill_alpha > 0
    paint = shape.paint
    has_fill = paint.fill not in {None, "none"}
    has_stroke = paint.stroke not in {None, "none"} and (paint.stroke_width or 0) > 0
    return has_fill or has_stroke


def _dml_shapes(root: ET.Element) -> Iterable[Shape]:
    yield from _dml_shapes_walk(root, _identity_matrix())


def _dml_shapes_walk(
    element: ET.Element,
    matrix: tuple[float, float, float, float, float, float],
) -> Iterable[Shape]:
    tag = _local_name(element.tag)
    if tag == "grpSp":
        matrix = _matrix_multiply(matrix, _dml_group_matrix(element))
        for child in element:
            yield from _dml_shapes_walk(child, matrix)
        return
    if tag == "graphicFrame":
        for shape in _dml_table_shapes(element):
            yield _transform_dml_shape(shape, matrix)
        return
    shape = _dml_shape_from_element(element)
    if shape is not None:
        yield _transform_dml_shape(shape, matrix)
        return
    for child in element:
        yield from _dml_shapes_walk(child, matrix)


def _dml_table_shapes(element: ET.Element) -> Iterable[Shape]:
    table = element.find(f".//{qn(NS_A, 'tbl')}")
    if table is None:
        return ()
    x, y, width, height, _, _, _ = _dml_xfrm(element.find(qn(NS_P, "xfrm")))
    grid_widths = [_px(_dml_int(col.get("w"), 0) or 0) for col in table.findall(f"{qn(NS_A, 'tblGrid')}/{qn(NS_A, 'gridCol')}")]
    rows = table.findall(qn(NS_A, "tr"))
    row_heights = [_px(_dml_int(row.get("h"), 0) or 0) for row in rows]
    if not rows or not grid_widths:
        return ()
    total_grid_width = sum(grid_widths)
    total_row_height = sum(row_heights)
    scale_x = width / total_grid_width if width > 0 and total_grid_width > 0 else 1.0
    scale_y = height / total_row_height if height > 0 and total_row_height > 0 else 1.0
    shapes: list[Shape] = []
    top = y
    for row_index, (row, row_height) in enumerate(zip(rows, row_heights, strict=False)):
        left = x
        cells = row.findall(qn(NS_A, "tc"))
        column_index = 0
        for cell in cells:
            if column_index >= len(grid_widths):
                break
            column_span, row_span = _dml_table_cell_span(cell)
            if _dml_table_cell_is_merge_continuation(cell):
                if _dml_bool_attr(cell, "vMerge") and not _dml_bool_attr(cell, "hMerge"):
                    left += sum(grid_widths[column_index : column_index + column_span]) * scale_x
                    column_index += column_span
                continue
            end_column = min(len(grid_widths), column_index + column_span)
            end_row = min(len(row_heights), row_index + row_span)
            cell_width = sum(grid_widths[column_index:end_column]) * scale_x
            cell_height = sum(row_heights[row_index:end_row]) * scale_y or row_height * scale_y
            cell_fill, fill_alpha = _dml_table_cell_fill(cell)
            shapes.append(
                Shape(
                    "rect",
                    left,
                    top,
                    cell_width,
                    cell_height,
                    Paint(fill=cell_fill, stroke="none", fill_alpha=fill_alpha),
                )
            )
            shapes.extend(_dml_table_cell_border_shapes(cell, left, top, cell_width, cell_height))
            text = _dml_table_cell_text(cell)
            if text:
                left_inset, top_inset, right_inset, bottom_inset = _dml_table_cell_text_insets(
                    cell, scale_x, scale_y
                )
                text_properties = _dml_table_cell_text_run_property_candidates(cell)
                shapes.append(
                    Shape(
                        "text",
                        left + left_inset,
                        top + top_inset,
                        max(0.0, cell_width - left_inset - right_inset),
                        max(0.0, cell_height - top_inset - bottom_inset),
                        _dml_table_cell_text_paint(cell),
                        text=text,
                        font_size=_dml_font_size_from_properties(text_properties),
                        font_weight=_dml_font_weight_from_properties(text_properties),
                        font_style=_dml_font_style_from_properties(text_properties),
                        font_family=_dml_font_family_from_properties(text_properties),
                        font_variant=_dml_font_variant_from_properties(text_properties),
                        text_decoration=_dml_text_decoration_from_properties(text_properties),
                        text_decoration_style=_dml_text_decoration_style_from_properties(text_properties),
                        text_decoration_color=_dml_text_decoration_color_from_properties(text_properties),
                        text_decoration_alpha=_dml_text_decoration_alpha_from_properties(text_properties),
                        text_decoration_thickness=_dml_text_decoration_thickness_from_properties(text_properties),
                        text_anchor=_dml_table_cell_text_anchor(cell),
                        text_direction=_dml_table_cell_text_direction(cell),
                        text_wrap=_dml_table_cell_text_wrap(cell),
                        text_baseline=_dml_table_cell_text_baseline(cell) or "middle",
                        text_baseline_shift=_dml_text_baseline_shift_from_properties(text_properties),
                        letter_spacing=_dml_letter_spacing_from_properties(text_properties),
                        text_runs=_dml_table_cell_text_runs(cell),
                )
            )
            left += cell_width
            column_index = end_column
        top += row_height * scale_y
    return tuple(shapes)


def _dml_table_cell_text_insets(cell: ET.Element, scale_x: float, scale_y: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = _dml_text_insets(cell)
    return left * scale_x, top * scale_y, right * scale_x, bottom * scale_y


def _dml_table_cell_span(cell: ET.Element) -> tuple[int, int]:
    column_span = max(1, _dml_int(cell.get("gridSpan"), 1) or 1)
    row_span = max(1, _dml_int(cell.get("rowSpan"), 1) or 1)
    return column_span, row_span


def _dml_table_cell_is_merge_continuation(cell: ET.Element) -> bool:
    return _dml_bool_attr(cell, "hMerge") or _dml_bool_attr(cell, "vMerge")


def _dml_bool_attr(element: ET.Element, attr: str) -> bool:
    value = element.get(attr)
    return value is not None and value.strip().lower() not in {"", "0", "false", "none"}


def _dml_table_cell_text(cell: ET.Element) -> str:
    tx_body = cell.find(qn(NS_A, "txBody"))
    if tx_body is None:
        return ""
    paragraphs = tx_body.findall(qn(NS_A, "p"))
    return "\n".join(_dml_paragraph_text(tx_body, paragraph, index + 1) for index, paragraph in enumerate(paragraphs))


def _dml_table_cell_text_runs(cell: ET.Element) -> tuple[TextRun, ...]:
    tx_body = cell.find(qn(NS_A, "txBody"))
    if tx_body is None:
        return ()
    return _dml_text_runs_from_body(cell, tx_body, Paint(fill="#000000", stroke="none"))


def _dml_table_cell_fill(cell: ET.Element) -> tuple[str | None, float | None]:
    fill = cell.find(f"{qn(NS_A, 'tcPr')}/{qn(NS_A, 'solidFill')}")
    if fill is None:
        return "none", None
    return _dml_color(fill), _dml_alpha(fill)


def _dml_table_cell_border_shapes(
    cell: ET.Element,
    left: float,
    top: float,
    width: float,
    height: float,
) -> tuple[Shape, ...]:
    border_specs = (
        ("lnL", left, top, left, top + height),
        ("lnR", left + width, top, left + width, top + height),
        ("lnT", left, top, left + width, top),
        ("lnB", left, top + height, left + width, top + height),
    )
    return tuple(
        Shape(
            "line",
            min(x1, x2),
            min(y1, y2),
            abs(x2 - x1),
            abs(y2 - y1),
            paint,
            flip_h=x2 < x1,
            flip_v=y2 < y1,
        )
        for tag, x1, y1, x2, y2 in border_specs
        if (paint := _dml_table_cell_border_paint(cell, tag)) is not None
    )


def _dml_table_cell_border_paint(cell: ET.Element, tag: str) -> Paint | None:
    tc_pr = cell.find(qn(NS_A, "tcPr"))
    if tc_pr is None:
        return Paint(fill="none", stroke="#000000", stroke_width=1.0)
    line = tc_pr.find(qn(NS_A, tag))
    if line is None:
        return Paint(fill="none", stroke="#000000", stroke_width=1.0)
    color = _dml_line_color(line)
    if color == "none":
        return None
    return Paint(
        fill="none",
        stroke=color or "#000000",
        stroke_width=_dml_line_width(line) or 1.0,
        stroke_alpha=_dml_line_alpha(line),
        stroke_linecap=_dml_linecap(line.get("cap")),
        stroke_linejoin=_dml_linejoin(line),
        stroke_dasharray=_dml_dasharray(line),
        stroke_miterlimit=_dml_miterlimit(line),
    )


def _dml_table_cell_text_paint(cell: ET.Element) -> Paint:
    r_pr, def_r_pr, end_para_r_pr = _dml_table_cell_text_run_property_candidates(cell)
    shape_paint = Paint(fill="#000000", stroke="none")
    ln = _dml_text_line_properties(r_pr, def_r_pr, end_para_r_pr)
    fill, fill_alpha = _dml_text_fill(cell, r_pr, def_r_pr, end_para_r_pr, shape_paint)
    return Paint(
        fill=fill or "#000000",
        stroke=_dml_line_color(ln) if ln is not None else shape_paint.stroke,
        stroke_width=_dml_line_width(ln) if ln is not None else shape_paint.stroke_width,
        fill_alpha=fill_alpha,
        stroke_alpha=_dml_line_alpha(ln) if ln is not None else shape_paint.stroke_alpha,
        stroke_linecap=_dml_linecap(ln.get("cap")) if ln is not None else shape_paint.stroke_linecap,
        stroke_linejoin=_dml_linejoin(ln) if ln is not None else shape_paint.stroke_linejoin,
        stroke_dasharray=_dml_dasharray(ln) if ln is not None else shape_paint.stroke_dasharray,
        stroke_miterlimit=_dml_miterlimit(ln) if ln is not None else shape_paint.stroke_miterlimit,
    )


def _dml_table_cell_text_run_property_candidates(
    cell: ET.Element,
) -> tuple[ET.Element | None, ET.Element | None, ET.Element | None]:
    p_pr = cell.find(f"{qn(NS_A, 'txBody')}/{qn(NS_A, 'p')}/{qn(NS_A, 'pPr')}")
    return (
        cell.find(f".//{qn(NS_A, 'rPr')}"),
        _dml_table_cell_default_text_run_properties(cell, p_pr),
        cell.find(f".//{qn(NS_A, 'endParaRPr')}"),
    )


def _dml_table_cell_default_text_run_properties(
    cell: ET.Element,
    p_pr: ET.Element | None,
) -> ET.Element | None:
    def_r_pr = p_pr.find(qn(NS_A, "defRPr")) if p_pr is not None else None
    if def_r_pr is not None:
        return def_r_pr
    tx_body = cell.find(qn(NS_A, "txBody"))
    if tx_body is None:
        return None
    list_p_pr = _dml_list_style_paragraph_properties(tx_body, p_pr)
    return list_p_pr.find(qn(NS_A, "defRPr")) if list_p_pr is not None else None


def _dml_table_cell_text_anchor(cell: ET.Element) -> str | None:
    p_pr = _dml_table_cell_paragraph_properties(cell, lambda item: item.get("algn") is not None)
    if p_pr is None:
        return None
    return {"ctr": "middle", "r": "end", "l": "start"}.get(p_pr.get("algn", ""))


def _dml_table_cell_text_direction(cell: ET.Element) -> str | None:
    p_pr = _dml_table_cell_paragraph_properties(cell, lambda item: item.get("rtl") is not None)
    if p_pr is None:
        return None
    return "rtl" if p_pr.get("rtl") in {"1", "true"} else None


def _dml_table_cell_paragraph_properties(
    cell: ET.Element,
    predicate: Callable[[ET.Element], bool],
) -> ET.Element | None:
    tx_body = cell.find(qn(NS_A, "txBody"))
    p_pr = tx_body.find(f"{qn(NS_A, 'p')}/{qn(NS_A, 'pPr')}") if tx_body is not None else None
    if p_pr is not None and predicate(p_pr):
        return p_pr
    if tx_body is not None:
        list_p_pr = _dml_list_style_paragraph_properties(tx_body, p_pr)
        if list_p_pr is not None and predicate(list_p_pr):
            return list_p_pr
    return None


def _dml_table_cell_text_baseline(cell: ET.Element) -> str | None:
    body_pr = cell.find(f"{qn(NS_A, 'txBody')}/{qn(NS_A, 'bodyPr')}")
    if body_pr is None:
        return None
    return {"ctr": "middle", "b": "text-after-edge", "t": "text-before-edge"}.get(body_pr.get("anchor", ""))


def _dml_table_cell_text_wrap(cell: ET.Element) -> str | None:
    body_pr = cell.find(f"{qn(NS_A, 'txBody')}/{qn(NS_A, 'bodyPr')}")
    if body_pr is None:
        return None
    return "none" if body_pr.get("wrap") == "none" else None


def _dml_shape_from_element(element: ET.Element) -> Shape | None:
    tag = _local_name(element.tag)
    if tag == "pic":
        return _dml_picture_shape(element)
    if tag not in {"sp", "cxnSp"}:
        return None
    sp_pr = element.find(qn(NS_P, "spPr"))
    if sp_pr is None:
        sp_pr = element.find(qn(NS_A, "spPr"))
    if sp_pr is None:
        return None
    text = _dml_text(element)
    if text is not None:
        xfrm = sp_pr.find(qn(NS_A, "xfrm"))
        x, y, width, height, flip_h, flip_v, rotation = _dml_xfrm(xfrm)
        left_inset, top_inset, right_inset, bottom_inset = _dml_text_insets(element)
        x += left_inset
        y += top_inset
        width = max(0.0, width - left_inset - right_inset)
        height = max(0.0, height - top_inset - bottom_inset)
        return Shape(
            "text",
            x,
            y,
            width,
            height,
            _dml_text_paint(element, sp_pr),
            flip_h,
            flip_v,
            text=text,
            font_size=_dml_font_size(element),
            font_weight=_dml_font_weight(element),
            font_style=_dml_font_style(element),
            font_family=_dml_font_family(element),
            font_variant=_dml_font_variant(element),
            text_decoration=_dml_text_decoration(element),
            text_decoration_style=_dml_text_decoration_style(element),
            text_decoration_color=_dml_text_decoration_color(element),
            text_decoration_alpha=_dml_text_decoration_alpha(element),
            text_decoration_thickness=_dml_text_decoration_thickness(element),
            text_anchor=_dml_text_anchor(element),
            text_baseline=_dml_text_baseline(element),
            text_direction=_dml_text_direction(element),
            text_baseline_shift=_dml_text_baseline_shift(element),
            letter_spacing=_dml_letter_spacing(element),
            rotation=rotation,
            text_runs=_dml_text_runs(element, sp_pr),
        )
    cust = sp_pr.find(qn(NS_A, "custGeom"))
    if cust is not None:
        xfrm = sp_pr.find(qn(NS_A, "xfrm"))
        x, y, width, height, flip_h, flip_v, rotation = _dml_xfrm(xfrm)
        points, closed = _dml_custom_points(cust, x, y)
        if points:
            return Shape(
                "freeform",
                x,
                y,
                width,
                height,
                _dml_paint(sp_pr, element),
                flip_h,
                flip_v,
                tuple(points),
                closed,
                rotation=rotation,
            )
        return None
    prst = sp_pr.find(qn(NS_A, "prstGeom"))
    if prst is None:
        return None
    prst_name = prst.get("prst", "")
    xfrm = sp_pr.find(qn(NS_A, "xfrm"))
    x, y, width, height, flip_h, flip_v, rotation = _dml_xfrm(xfrm)
    preset_points = _dml_preset_points(prst_name, x, y, width, height)
    if preset_points:
        return Shape(
            "freeform",
            x,
            y,
            width,
            height,
            _dml_paint(sp_pr, element),
            flip_h,
            flip_v,
            tuple(preset_points),
            True,
            rotation=rotation,
        )
    kind = _dml_kind_to_shape(prst_name)
    if kind is None:
        return None
    radius = min(width, height) / 6 if kind == "roundRect" else None
    return Shape(kind, x, y, width, height, _dml_paint(sp_pr, element), flip_h, flip_v, rx=radius, ry=radius, rotation=rotation)


def _shape_to_dml(shape: Shape, shape_id: int) -> ET.Element:
    if shape.kind == "image":
        return _image_to_dml(shape, shape_id)
    sp = ET.Element(qn(NS_P, "sp"))
    nv_sp_pr = ET.SubElement(sp, qn(NS_P, "nvSpPr"))
    ET.SubElement(nv_sp_pr, qn(NS_P, "cNvPr"), {"id": str(shape_id), "name": shape.kind})
    ET.SubElement(nv_sp_pr, qn(NS_P, "cNvSpPr"))
    ET.SubElement(nv_sp_pr, qn(NS_P, "nvPr"))
    sp_pr = ET.SubElement(sp, qn(NS_P, "spPr"))
    xfrm_attrs = {}
    if shape.flip_h:
        xfrm_attrs["flipH"] = "1"
    if shape.flip_v:
        xfrm_attrs["flipV"] = "1"
    if shape.rotation is not None:
        xfrm_attrs["rot"] = str(round(shape.rotation * 60000))
    xfrm = ET.SubElement(sp_pr, qn(NS_A, "xfrm"), xfrm_attrs)
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": str(_emu(shape.x)), "y": str(_emu(shape.y))})
    ET.SubElement(
        xfrm,
        qn(NS_A, "ext"),
        {"cx": str(_emu(shape.width)), "cy": str(_emu(shape.height))},
    )
    if shape.kind == "freeform":
        _append_custom_geometry(sp_pr, shape)
    else:
        prst_geom = ET.SubElement(sp_pr, qn(NS_A, "prstGeom"), {"prst": _shape_kind_to_dml(shape.kind)})
        ET.SubElement(prst_geom, qn(NS_A, "avLst"))
    if shape.kind == "text":
        ET.SubElement(sp_pr, qn(NS_A, "noFill"))
        ln = ET.SubElement(sp_pr, qn(NS_A, "ln"))
        ET.SubElement(ln, qn(NS_A, "noFill"))
    else:
        _append_dml_paint(sp_pr, shape.paint)
    if shape.kind == "text":
        _append_text_body(sp, shape)
    return sp


def _shape_to_svg(shape: Shape) -> ET.Element:
    attrs = _svg_paint_attrs(shape.paint)
    if shape.kind == "image":
        attrs = {
            "href": shape.image_href or "",
            "x": _fmt(shape.x),
            "y": _fmt(shape.y),
            "width": _fmt(shape.width),
            "height": _fmt(shape.height),
        }
        if shape.paint.fill_alpha is not None and shape.paint.fill_alpha < 1:
            attrs["opacity"] = _fmt(shape.paint.fill_alpha)
        preserve_aspect_ratio = _svg_image_preserve_aspect_ratio(shape)
        if preserve_aspect_ratio is not None:
            attrs["preserveAspectRatio"] = preserve_aspect_ratio
        transform = _svg_image_transform(shape)
        if transform:
            attrs["transform"] = transform
        return ET.Element(qn(NS_SVG, "image"), attrs)
    if shape.kind in {"rect", "roundRect"}:
        attrs.update(
            {
                "x": _fmt(shape.x),
                "y": _fmt(shape.y),
                "width": _fmt(shape.width),
                "height": _fmt(shape.height),
            }
        )
        if shape.kind == "roundRect":
            if shape.rx is not None:
                attrs["rx"] = _fmt(shape.rx)
            if shape.ry is not None:
                attrs["ry"] = _fmt(shape.ry)
        transform = _svg_shape_transform(shape)
        if transform:
            attrs["transform"] = transform
        return ET.Element(qn(NS_SVG, "rect"), attrs)
    if shape.kind == "ellipse":
        attrs.update(
            {
                "cx": _fmt(shape.x + shape.width / 2),
                "cy": _fmt(shape.y + shape.height / 2),
                "rx": _fmt(shape.width / 2),
                "ry": _fmt(shape.height / 2),
            }
        )
        transform = _svg_shape_transform(shape)
        if transform:
            attrs["transform"] = transform
        return ET.Element(qn(NS_SVG, "ellipse"), attrs)
    if shape.kind == "line":
        attrs.update(_line_points(shape))
        attrs.setdefault("fill", "none")
        transform = _svg_line_transform(shape)
        if transform:
            attrs["transform"] = transform
        return ET.Element(qn(NS_SVG, "line"), attrs)
    if shape.kind == "freeform":
        attrs["points"] = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in shape.points)
        transform = _svg_shape_transform(shape)
        if transform:
            attrs["transform"] = transform
        tag = "polygon" if shape.closed else "polyline"
        return ET.Element(qn(NS_SVG, tag), attrs)
    if shape.kind == "text":
        attrs.update({"x": _fmt(_svg_text_x(shape)), "y": _fmt(_svg_text_y(shape))})
        if shape.font_size:
            attrs["font-size"] = _fmt(shape.font_size)
        if shape.font_weight:
            attrs["font-weight"] = shape.font_weight
        if shape.font_style:
            attrs["font-style"] = shape.font_style
        if shape.font_family:
            attrs["font-family"] = shape.font_family
        if shape.font_variant:
            attrs["font-variant"] = shape.font_variant
        if shape.text_decoration:
            attrs["text-decoration"] = shape.text_decoration
        if shape.text_decoration_style:
            attrs["text-decoration-style"] = shape.text_decoration_style
        if shape.text_decoration_color:
            attrs["text-decoration-color"] = _color_with_alpha(shape.text_decoration_color, shape.text_decoration_alpha)
        if shape.text_decoration_thickness is not None:
            attrs["text-decoration-thickness"] = _fmt(shape.text_decoration_thickness)
        if shape.text_anchor:
            attrs["text-anchor"] = shape.text_anchor
        if shape.text_baseline:
            attrs["dominant-baseline"] = shape.text_baseline
        if shape.text_direction:
            attrs["direction"] = shape.text_direction
        if shape.text_wrap == "none":
            attrs["white-space"] = "nowrap"
        if shape.text_baseline_shift:
            attrs["baseline-shift"] = shape.text_baseline_shift
        if shape.letter_spacing is not None:
            attrs["letter-spacing"] = _fmt(shape.letter_spacing)
        transform = _svg_shape_transform(shape) if shape.flip_h or shape.flip_v else None
        if transform:
            attrs["transform"] = transform
        elif shape.rotation is not None:
            attrs["rotate"] = _fmt(shape.rotation)
        element = ET.Element(qn(NS_SVG, "text"), attrs)
        if shape.text_runs:
            for text_run in shape.text_runs:
                tspan_attrs = _svg_tspan_attrs(text_run)
                if text_run.break_before:
                    tspan_attrs["x"] = attrs["x"]
                    tspan_attrs["dy"] = _fmt(text_run.font_size or shape.font_size or shape.height / 1.4)
                tspan = ET.SubElement(element, qn(NS_SVG, "tspan"), tspan_attrs)
                tspan.text = text_run.text
        else:
            lines = (shape.text or "").split("\n")
            element.text = lines[0] if lines else ""
            for index, line in enumerate(lines[1:], start=1):
                tspan = ET.SubElement(
                    element,
                    qn(NS_SVG, "tspan"),
                    {"x": attrs["x"], "dy": _fmt(shape.font_size or shape.height / max(len(lines), 1) / 1.4)},
                )
                tspan.text = line
        return element
    raise ValueError(f"unsupported shape kind: {shape.kind}")


def _svg_tspan_attrs(text_run: TextRun) -> dict[str, str]:
    attrs = _svg_paint_attrs(text_run.paint)
    if text_run.font_size:
        attrs["font-size"] = _fmt(text_run.font_size)
    if text_run.font_weight:
        attrs["font-weight"] = text_run.font_weight
    if text_run.font_style:
        attrs["font-style"] = text_run.font_style
    if text_run.font_family:
        attrs["font-family"] = text_run.font_family
    if text_run.font_variant:
        attrs["font-variant"] = text_run.font_variant
    if text_run.text_decoration:
        attrs["text-decoration"] = text_run.text_decoration
    if text_run.text_decoration_style:
        attrs["text-decoration-style"] = text_run.text_decoration_style
    if text_run.text_decoration_color:
        attrs["text-decoration-color"] = _color_with_alpha(text_run.text_decoration_color, text_run.text_decoration_alpha)
    if text_run.text_decoration_thickness is not None:
        attrs["text-decoration-thickness"] = _fmt(text_run.text_decoration_thickness)
    if text_run.text_baseline_shift:
        attrs["baseline-shift"] = text_run.text_baseline_shift
    if text_run.letter_spacing is not None:
        attrs["letter-spacing"] = _fmt(text_run.letter_spacing)
    return attrs


def _image_to_dml(shape: Shape, shape_id: int) -> ET.Element:
    pic = ET.Element(qn(NS_P, "pic"))
    nv_pic_pr = ET.SubElement(pic, qn(NS_P, "nvPicPr"))
    ET.SubElement(nv_pic_pr, qn(NS_P, "cNvPr"), {"id": str(shape_id), "name": "image"})
    ET.SubElement(nv_pic_pr, qn(NS_P, "cNvPicPr"))
    ET.SubElement(nv_pic_pr, qn(NS_P, "nvPr"))
    blip_fill = ET.SubElement(pic, qn(NS_P, "blipFill"))
    blip = ET.SubElement(blip_fill, qn(NS_A, "blip"), {qn(NS_R, "embed"): shape.image_href or ""})
    if shape.paint.fill_alpha is not None and shape.paint.fill_alpha < 1:
        ET.SubElement(blip, qn(NS_A, "alphaModFix"), {"amt": str(round(max(0.0, min(shape.paint.fill_alpha, 1.0)) * 100000))})
    if shape.image_src_rect is not None:
        left, top, right, bottom = shape.image_src_rect
        attrs = {key: str(value) for key, value in (("l", left), ("t", top), ("r", right), ("b", bottom)) if value}
        if attrs:
            ET.SubElement(blip_fill, qn(NS_A, "srcRect"), attrs)
    stretch = ET.SubElement(blip_fill, qn(NS_A, "stretch"))
    ET.SubElement(stretch, qn(NS_A, "fillRect"))
    sp_pr = ET.SubElement(pic, qn(NS_P, "spPr"))
    xfrm_attrs = {}
    if shape.flip_h:
        xfrm_attrs["flipH"] = "1"
    if shape.flip_v:
        xfrm_attrs["flipV"] = "1"
    if shape.rotation is not None:
        xfrm_attrs["rot"] = str(round(shape.rotation * 60000))
    xfrm = ET.SubElement(sp_pr, qn(NS_A, "xfrm"), xfrm_attrs)
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": str(_emu(shape.x)), "y": str(_emu(shape.y))})
    ET.SubElement(xfrm, qn(NS_A, "ext"), {"cx": str(_emu(shape.width)), "cy": str(_emu(shape.height))})
    prst = ET.SubElement(sp_pr, qn(NS_A, "prstGeom"), {"prst": "rect"})
    ET.SubElement(prst, qn(NS_A, "avLst"))
    return pic


def _dml_picture_shape(element: ET.Element) -> Shape | None:
    sp_pr = element.find(qn(NS_P, "spPr"))
    blip = element.find(f".//{qn(NS_A, 'blip')}")
    if sp_pr is None or blip is None:
        return None
    href = blip.get(qn(NS_R, "embed"))
    if not href:
        return None
    x, y, width, height, flip_h, flip_v, rotation = _dml_xfrm(sp_pr.find(qn(NS_A, "xfrm")))
    src_rect = _dml_src_rect(element.find(f".//{qn(NS_A, 'srcRect')}"))
    return Shape(
        "image",
        x,
        y,
        width,
        height,
        Paint(fill_alpha=_dml_blip_alpha(blip)),
        flip_h,
        flip_v,
        image_href=href,
        image_src_rect=src_rect,
        rotation=rotation,
    )


def _dml_src_rect(element: ET.Element | None) -> tuple[int, int, int, int] | None:
    if element is None:
        return None
    values = tuple(_optional_int(element.get(attr)) or 0 for attr in ("l", "t", "r", "b"))
    return values if any(values) else None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _transformed_image_shape(
    x: float,
    y: float,
    width: float,
    height: float,
    matrix: tuple[float, float, float, float, float, float],
    href: str,
    alpha: float | None,
    src_rect: tuple[int, int, int, int] | None = None,
) -> Shape:
    paint = Paint(fill_alpha=alpha)
    points = _transform_points(_rect_points(x, y, width, height), matrix)
    p0, p1, p2, p3 = points
    ux = (p1[0] - p0[0], p1[1] - p0[1])
    vy = (p3[0] - p0[0], p3[1] - p0[1])
    transformed_width = math.hypot(*ux)
    transformed_height = math.hypot(*vy)
    dot = ux[0] * vy[0] + ux[1] * vy[1]
    determinant = ux[0] * vy[1] - ux[1] * vy[0]
    tolerance = max(transformed_width * transformed_height, 1.0) * 1e-9
    if transformed_width > 0 and transformed_height > 0 and abs(dot) <= tolerance and abs(determinant) > tolerance:
        center_x = sum(px for px, _ in points) / 4
        center_y = sum(py for _, py in points) / 4
        rotation = math.degrees(math.atan2(ux[1], ux[0])) % 360
        if abs(rotation) < 1e-9 or abs(rotation - 360) < 1e-9:
            rotation = 0.0
        return Shape(
            "image",
            center_x - transformed_width / 2,
            center_y - transformed_height / 2,
            transformed_width,
            transformed_height,
            paint,
            flip_v=determinant < 0,
            image_href=href,
            image_src_rect=src_rect,
            rotation=rotation or None,
        )

    min_x = min(px for px, _ in points)
    min_y = min(py for _, py in points)
    max_x = max(px for px, _ in points)
    max_y = max(py for _, py in points)
    return Shape("image", min_x, min_y, max_x - min_x, max_y - min_y, paint, image_href=href, image_src_rect=src_rect)


def _svg_shape_transform(shape: Shape) -> str | None:
    transforms = []
    center_x = shape.x + shape.width / 2
    center_y = shape.y + shape.height / 2
    if shape.rotation is not None:
        transforms.append(f"rotate({_fmt(shape.rotation)} {_fmt(center_x)} {_fmt(center_y)})")
    if shape.flip_h or shape.flip_v:
        sx = -1 if shape.flip_h else 1
        sy = -1 if shape.flip_v else 1
        transforms.append(f"translate({_fmt(center_x)} {_fmt(center_y)}) scale({sx} {sy}) translate({_fmt(-center_x)} {_fmt(-center_y)})")
    return " ".join(transforms) or None


def _svg_image_transform(shape: Shape) -> str | None:
    return _svg_shape_transform(shape)


def _svg_image_preserve_aspect_ratio(shape: Shape) -> str | None:
    if shape.image_src_rect is None:
        return None
    left, top, right, bottom = shape.image_src_rect
    x_align = _svg_crop_alignment(left, right, "x")
    y_align = _svg_crop_alignment(top, bottom, "y")
    if x_align is None or y_align is None:
        return None
    return f"{x_align}{y_align} slice"


def _svg_crop_alignment(before: int, after: int, axis: str) -> str | None:
    if before == 0 and after == 0:
        return "xMid" if axis == "x" else "YMid"
    if before == 0:
        return "xMin" if axis == "x" else "YMin"
    if after == 0:
        return "xMax" if axis == "x" else "YMax"
    return "xMid" if axis == "x" else "YMid"


def _svg_line_transform(shape: Shape) -> str | None:
    if shape.rotation is None:
        return None
    center_x = shape.x + shape.width / 2
    center_y = shape.y + shape.height / 2
    return f"rotate({_fmt(shape.rotation)} {_fmt(center_x)} {_fmt(center_y)})"


def _shape_bounds(shape: Shape) -> tuple[float, float, float, float]:
    if shape.kind == "line":
        line = _line_points(shape)
        points = [(float(line["x1"]), float(line["y1"])), (float(line["x2"]), float(line["y2"]))]
        if shape.rotation is not None:
            points = [_rotate_point(point, shape.rotation, shape.x + shape.width / 2, shape.y + shape.height / 2) for point in points]
    elif shape.kind == "freeform":
        points = list(shape.points)
        points = _apply_shape_transform(points, shape)
    else:
        points = _rect_points(shape.x, shape.y, shape.width, shape.height)
        if shape.rotation is not None or shape.flip_h or shape.flip_v:
            points = _apply_shape_transform(points, shape)
    min_x = min((x for x, _ in points), default=0.0)
    min_y = min((y for _, y in points), default=0.0)
    max_x = max((x for x, _ in points), default=0.0)
    max_y = max((y for _, y in points), default=0.0)
    return min_x, min_y, max_x, max_y


def _apply_shape_transform(points: list[tuple[float, float]], shape: Shape) -> list[tuple[float, float]]:
    center_x = shape.x + shape.width / 2
    center_y = shape.y + shape.height / 2
    transformed = points
    if shape.rotation is not None:
        transformed = [_rotate_point(point, shape.rotation, center_x, center_y) for point in transformed]
    if shape.flip_h or shape.flip_v:
        transformed = [
            (
                center_x - (x - center_x) if shape.flip_h else x,
                center_y - (y - center_y) if shape.flip_v else y,
            )
            for x, y in transformed
        ]
    return transformed


def _rotate_point(point: tuple[float, float], degrees: float, center_x: float, center_y: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    x, y = point
    dx = x - center_x
    dy = y - center_y
    return center_x + dx * cos_a - dy * sin_a, center_y + dx * sin_a + dy * cos_a


def _append_svg_marker_defs(svg: ET.Element, shapes: list[Shape]) -> None:
    if not any(shape.paint.marker_start or shape.paint.marker_end for shape in shapes):
        return
    defs = ET.SubElement(svg, qn(NS_SVG, "defs"))
    marker = ET.SubElement(
        defs,
        qn(NS_SVG, "marker"),
        {
            "id": "svgraph-arrow",
            "viewBox": "0 0 10 10",
            "refX": "10",
            "refY": "5",
            "markerWidth": "6",
            "markerHeight": "6",
            "orient": "auto-start-reverse",
        },
    )
    ET.SubElement(marker, qn(NS_SVG, "path"), {"d": "M0 0 L10 5 L0 10 Z", "fill": "context-stroke"})


def _line_points(shape: Shape) -> dict[str, str]:
    x1 = shape.x + shape.width if shape.flip_h else shape.x
    x2 = shape.x if shape.flip_h else shape.x + shape.width
    y1 = shape.y + shape.height if shape.flip_v else shape.y
    y2 = shape.y if shape.flip_v else shape.y + shape.height
    return {"x1": _fmt(x1), "y1": _fmt(y1), "x2": _fmt(x2), "y2": _fmt(y2)}


def _extract_svg_table(shapes: list[Shape]) -> tuple[SvgTable | None, list[Shape]]:
    rects = [shape for shape in shapes if _svg_table_rect_candidate(shape)]
    if not rects:
        return _extract_svg_line_table(shapes)
    if len(rects) < 2 or len(rects) != sum(1 for shape in shapes if shape.kind == "rect"):
        return None, shapes

    x_edges = _svg_table_edges([(rect.x, rect.x + rect.width) for rect in rects])
    y_edges = _svg_table_edges([(rect.y, rect.y + rect.height) for rect in rects])
    if len(x_edges) < 2 or len(y_edges) < 2:
        return None, shapes

    columns = tuple(x_edges[index + 1] - x_edges[index] for index in range(len(x_edges) - 1))
    rows = tuple(y_edges[index + 1] - y_edges[index] for index in range(len(y_edges) - 1))
    if any(size <= 0 for size in columns + rows):
        return None, shapes

    row_count = len(rows)
    column_count = len(columns)
    origins: dict[tuple[int, int], tuple[Shape, int, int]] = {}
    occupancy: list[list[tuple[int, int] | None]] = [[None for _ in range(column_count)] for _ in range(row_count)]
    for rect in rects:
        column = _svg_table_edge_index(x_edges, rect.x)
        row = _svg_table_edge_index(y_edges, rect.y)
        right = _svg_table_edge_index(x_edges, rect.x + rect.width)
        bottom = _svg_table_edge_index(y_edges, rect.y + rect.height)
        if column is None or row is None or right is None or bottom is None:
            return None, shapes
        if right <= column or bottom <= row:
            return None, shapes
        origin = (row, column)
        if origin in origins:
            return None, shapes
        origins[origin] = (rect, right - column, bottom - row)
        for occupied_row in range(row, bottom):
            for occupied_column in range(column, right):
                if occupancy[occupied_row][occupied_column] is not None:
                    return None, shapes
                occupancy[occupied_row][occupied_column] = origin
    if any(origin is None for row in occupancy for origin in row):
        return None, shapes

    text_map: dict[tuple[int, int], Shape] = {}
    consumed_texts: set[int] = set()
    for index, shape in enumerate(shapes):
        if not _svg_table_text_candidate(shape):
            continue
        center_x = shape.x + shape.width / 2
        center_y = shape.y + shape.height / 2
        column = _svg_table_interval_index(x_edges, center_x)
        row = _svg_table_interval_index(y_edges, center_y)
        if row is None or column is None:
            continue
        key = occupancy[row][column]
        if key is None:
            continue
        if key in text_map:
            return None, shapes
        text_map[key] = shape
        consumed_texts.add(index)

    grid_lines = _svg_table_rect_grid_lines(shapes, x_edges, y_edges, origins)
    border_paints = _svg_table_grid_border_paints(grid_lines, x_edges, y_edges) if grid_lines else None
    table_rows: list[tuple[SvgTableCell, ...]] = []
    for row in range(row_count):
        table_cells = []
        for column in range(column_count):
            origin = occupancy[row][column]
            if origin is None:
                return None, shapes
            if origin == (row, column):
                rect, column_span, row_span = origins[origin]
                borders = _svg_table_cell_grid_borders(border_paints, row, column) if border_paints is not None else ()
                if borders:
                    rect = _svg_table_rect_with_border_paint(rect, borders[0])
                else:
                    borders = _svg_table_rect_borders(rect)
                table_cells.append(
                    SvgTableCell(
                        rect,
                        text_map.get(origin),
                        column_span=column_span,
                        row_span=row_span,
                        border_left=borders[0] if borders else None,
                        border_right=borders[1] if borders else None,
                        border_top=borders[2] if borders else None,
                        border_bottom=borders[3] if borders else None,
                    )
                )
            else:
                table_cells.append(
                    SvgTableCell(
                        None,
                        h_merge=column > origin[1],
                        v_merge=row > origin[0],
                    )
                )
        table_rows.append(tuple(table_cells))
    cells = tuple(table_rows)
    table = SvgTable(x_edges[0], y_edges[0], columns, rows, cells)
    consumed_rects = {id(rect) for rect, _, _ in origins.values()}
    consumed_lines = {id(line) for line in grid_lines}
    remaining = [
        shape
        for index, shape in enumerate(shapes)
        if id(shape) not in consumed_rects and id(shape) not in consumed_lines and index not in consumed_texts
    ]
    return table, remaining


def _svg_table_rect_candidate(shape: Shape) -> bool:
    return (
        shape.kind == "rect"
        and shape.width > 0
        and shape.height > 0
        and shape.rotation is None
        and not shape.flip_h
        and not shape.flip_v
    )


def _svg_table_text_candidate(shape: Shape) -> bool:
    return shape.kind == "text" and shape.rotation is None and not shape.flip_h and not shape.flip_v


def _svg_table_rect_grid_lines(
    shapes: list[Shape],
    x_edges: tuple[float, ...],
    y_edges: tuple[float, ...],
    origins: dict[tuple[int, int], tuple[Shape, int, int]],
) -> tuple[Shape, ...]:
    column_count = len(x_edges) - 1
    row_count = len(y_edges) - 1
    if len(origins) != column_count * row_count:
        return ()
    if any(column_span != 1 or row_span != 1 for _, column_span, row_span in origins.values()):
        return ()
    lines = [shape for shape in shapes if shape.kind == "line"]
    if not lines or any(not _svg_table_line_candidate(line) for line in lines):
        return ()
    verticals = [line for line in lines if _svg_table_vertical_line(line)]
    horizontals = [line for line in lines if _svg_table_horizontal_line(line)]
    if len(verticals) + len(horizontals) != len(lines):
        return ()
    if not _svg_table_lines_cover_edges(verticals, x_edges, y_edges[0], y_edges[-1], "vertical"):
        return ()
    if not _svg_table_lines_cover_edges(horizontals, y_edges, x_edges[0], x_edges[-1], "horizontal"):
        return ()
    return tuple(lines)


def _svg_table_rect_with_border_paint(rect: Shape, border: Paint) -> Shape:
    paint = Paint(
        fill=rect.paint.fill,
        stroke=border.stroke,
        stroke_width=border.stroke_width,
        fill_alpha=rect.paint.fill_alpha,
        stroke_alpha=border.stroke_alpha,
        stroke_linecap=border.stroke_linecap,
        stroke_linejoin=border.stroke_linejoin,
        stroke_dasharray=border.stroke_dasharray,
        stroke_miterlimit=border.stroke_miterlimit,
        stroke_compound=border.stroke_compound,
    )
    return replace(rect, paint=paint)


def _svg_table_rect_borders(rect: Shape) -> tuple[Paint, Paint, Paint, Paint] | tuple[()]:
    if (
        rect.table_border_left is not None
        and rect.table_border_right is not None
        and rect.table_border_top is not None
        and rect.table_border_bottom is not None
    ):
        return (
            rect.table_border_left,
            rect.table_border_right,
            rect.table_border_top,
            rect.table_border_bottom,
        )
    return ()


def _svg_table_grid_border_paints(
    lines: Iterable[Shape],
    x_edges: tuple[float, ...],
    y_edges: tuple[float, ...],
) -> tuple[dict[int, Paint], dict[int, Paint]] | None:
    verticals: dict[int, Paint] = {}
    horizontals: dict[int, Paint] = {}
    for line in lines:
        if _svg_table_vertical_line(line):
            index = _svg_table_edge_index(x_edges, line.x)
            if index is None:
                return None
            verticals[index] = _svg_table_line_border_paint(line)
        elif _svg_table_horizontal_line(line):
            index = _svg_table_edge_index(y_edges, line.y)
            if index is None:
                return None
            horizontals[index] = _svg_table_line_border_paint(line)
        else:
            return None
    if any(index not in verticals for index in range(len(x_edges))):
        return None
    if any(index not in horizontals for index in range(len(y_edges))):
        return None
    return verticals, horizontals


def _svg_table_cell_grid_borders(
    border_paints: tuple[dict[int, Paint], dict[int, Paint]],
    row: int,
    column: int,
) -> tuple[Paint, Paint, Paint, Paint]:
    verticals, horizontals = border_paints
    return verticals[column], verticals[column + 1], horizontals[row], horizontals[row + 1]


def _svg_table_line_border_paint(line: Shape) -> Paint:
    return Paint(
        fill="none",
        stroke=line.paint.stroke,
        stroke_width=line.paint.stroke_width,
        stroke_alpha=line.paint.stroke_alpha,
        stroke_linecap=line.paint.stroke_linecap,
        stroke_linejoin=line.paint.stroke_linejoin,
        stroke_dasharray=line.paint.stroke_dasharray,
        stroke_miterlimit=line.paint.stroke_miterlimit,
    )


def _extract_svg_line_table(shapes: list[Shape]) -> tuple[SvgTable | None, list[Shape]]:
    if any(shape.kind not in {"line", "text"} for shape in shapes):
        return None, shapes
    lines = [shape for shape in shapes if shape.kind == "line"]
    if len(lines) < 4 or any(not _svg_table_line_candidate(line) for line in lines):
        return None, shapes
    verticals = [line for line in lines if _svg_table_vertical_line(line)]
    horizontals = [line for line in lines if _svg_table_horizontal_line(line)]
    if len(verticals) < 3 or len(horizontals) < 3 or len(verticals) + len(horizontals) != len(lines):
        return None, shapes

    x_edges = _svg_table_edges((line.x, line.x) for line in verticals)
    y_edges = _svg_table_edges((line.y, line.y) for line in horizontals)
    if len(x_edges) < 3 or len(y_edges) < 3:
        return None, shapes
    x_min, x_max = x_edges[0], x_edges[-1]
    y_min, y_max = y_edges[0], y_edges[-1]
    if not _svg_table_lines_cover_edges(verticals, x_edges, y_min, y_max, "vertical"):
        return None, shapes
    if not _svg_table_lines_cover_edges(horizontals, y_edges, x_min, x_max, "horizontal"):
        return None, shapes

    columns = tuple(x_edges[index + 1] - x_edges[index] for index in range(len(x_edges) - 1))
    rows = tuple(y_edges[index + 1] - y_edges[index] for index in range(len(y_edges) - 1))
    if any(size <= 0 for size in columns + rows):
        return None, shapes

    border_paints = _svg_table_grid_border_paints(lines, x_edges, y_edges)
    if border_paints is None:
        return None, shapes
    paint = _svg_table_line_grid_paint(lines)
    text_map: dict[tuple[int, int], Shape] = {}
    consumed_texts: set[int] = set()
    for index, shape in enumerate(shapes):
        if not _svg_table_text_candidate(shape):
            continue
        center_x = shape.x + shape.width / 2
        center_y = shape.y + shape.height / 2
        column = _svg_table_interval_index(x_edges, center_x)
        row = _svg_table_interval_index(y_edges, center_y)
        if row is None or column is None:
            continue
        key = (row, column)
        if key in text_map:
            return None, shapes
        text_map[key] = shape
        consumed_texts.add(index)

    rows_out: list[tuple[SvgTableCell, ...]] = []
    for row in range(len(rows)):
        cells_out = []
        for column in range(len(columns)):
            left_border, right_border, top_border, bottom_border = _svg_table_cell_grid_borders(
                border_paints, row, column
            )
            cells_out.append(
                SvgTableCell(
                    Shape(
                        "rect",
                        x_edges[column],
                        y_edges[row],
                        columns[column],
                        rows[row],
                        paint,
                    ),
                    text_map.get((row, column)),
                    border_left=left_border,
                    border_right=right_border,
                    border_top=top_border,
                    border_bottom=bottom_border,
                )
            )
        rows_out.append(tuple(cells_out))
    cells = tuple(rows_out)
    table = SvgTable(x_min, y_min, columns, rows, cells)
    consumed_lines = {id(line) for line in lines}
    remaining = [shape for index, shape in enumerate(shapes) if id(shape) not in consumed_lines and index not in consumed_texts]
    return table, remaining


def _svg_table_line_candidate(shape: Shape) -> bool:
    return (
        shape.rotation is None
        and shape.paint.stroke not in {None, "none"}
        and (_svg_table_vertical_line(shape) or _svg_table_horizontal_line(shape))
    )


def _svg_table_vertical_line(shape: Shape) -> bool:
    return _close(shape.width, 0.0, 1e-6) and shape.height > 0


def _svg_table_horizontal_line(shape: Shape) -> bool:
    return _close(shape.height, 0.0, 1e-6) and shape.width > 0


def _svg_table_lines_cover_edges(
    lines: list[Shape],
    edges: tuple[float, ...],
    start: float,
    end: float,
    orientation: str,
) -> bool:
    for edge in edges:
        if not any(_svg_table_line_covers_edge(line, edge, start, end, orientation) for line in lines):
            return False
    return True


def _svg_table_line_covers_edge(
    line: Shape,
    edge: float,
    start: float,
    end: float,
    orientation: str,
) -> bool:
    if orientation == "vertical":
        return _close(line.x, edge, 1e-6) and _close(line.y, start, 1e-6) and _close(line.y + line.height, end, 1e-6)
    return _close(line.y, edge, 1e-6) and _close(line.x, start, 1e-6) and _close(line.x + line.width, end, 1e-6)


def _svg_table_line_grid_paint(lines: list[Shape]) -> Paint:
    line = next((shape for shape in lines if shape.paint.stroke not in {None, "none"}), lines[0])
    return Paint(
        fill="none",
        stroke=line.paint.stroke,
        stroke_width=line.paint.stroke_width,
        stroke_alpha=line.paint.stroke_alpha,
        stroke_linecap=line.paint.stroke_linecap,
        stroke_linejoin=line.paint.stroke_linejoin,
        stroke_dasharray=line.paint.stroke_dasharray,
        stroke_miterlimit=line.paint.stroke_miterlimit,
    )


def _svg_table_edges(ranges: Iterable[tuple[float, float]]) -> tuple[float, ...]:
    edges: list[float] = []
    for start, end in ranges:
        for value in (start, end):
            if not any(_close(value, edge, 1e-6) for edge in edges):
                edges.append(value)
    return tuple(sorted(edges))


def _svg_table_edge_index(edges: tuple[float, ...], value: float) -> int | None:
    for index, edge in enumerate(edges):
        if _close(value, edge, 1e-6):
            return index
    return None


def _svg_table_interval_index(edges: tuple[float, ...], value: float) -> int | None:
    for index, (start, end) in enumerate(zip(edges, edges[1:])):
        if start - 1e-6 <= value <= end + 1e-6:
            return index
    return None


def _svg_table_to_dml(table: SvgTable, shape_id: int) -> ET.Element:
    frame = ET.Element(qn(NS_P, "graphicFrame"))
    nv = ET.SubElement(frame, qn(NS_P, "nvGraphicFramePr"))
    ET.SubElement(nv, qn(NS_P, "cNvPr"), {"id": str(shape_id), "name": "Table"})
    ET.SubElement(nv, qn(NS_P, "cNvGraphicFramePr"))
    ET.SubElement(nv, qn(NS_P, "nvPr"))
    xfrm = ET.SubElement(frame, qn(NS_P, "xfrm"))
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": str(_emu(table.x)), "y": str(_emu(table.y))})
    ET.SubElement(xfrm, qn(NS_A, "ext"), {"cx": str(_emu(sum(table.columns))), "cy": str(_emu(sum(table.rows)))})
    graphic = ET.SubElement(frame, qn(NS_A, "graphic"))
    graphic_data = ET.SubElement(
        graphic,
        qn(NS_A, "graphicData"),
        {"uri": "http://schemas.openxmlformats.org/drawingml/2006/table"},
    )
    tbl = ET.SubElement(graphic_data, qn(NS_A, "tbl"))
    tbl_pr = ET.SubElement(tbl, qn(NS_A, "tblPr"), {"firstRow": "0", "bandRow": "0"})
    ET.SubElement(tbl_pr, qn(NS_A, "tableStyleId")).text = "{00000000-0000-0000-0000-000000000000}"
    grid = ET.SubElement(tbl, qn(NS_A, "tblGrid"))
    for width in table.columns:
        ET.SubElement(grid, qn(NS_A, "gridCol"), {"w": str(_emu(width))})
    for row_height, row in zip(table.rows, table.cells):
        tr = ET.SubElement(tbl, qn(NS_A, "tr"), {"h": str(_emu(row_height))})
        for cell in row:
            _append_svg_table_cell(tr, cell)
    return frame


def _append_svg_table_cell(parent: ET.Element, cell: SvgTableCell) -> None:
    attrs = {}
    if cell.column_span > 1:
        attrs["gridSpan"] = str(cell.column_span)
    if cell.row_span > 1:
        attrs["rowSpan"] = str(cell.row_span)
    if cell.h_merge:
        attrs["hMerge"] = "1"
    if cell.v_merge:
        attrs["vMerge"] = "1"
    tc = ET.SubElement(parent, qn(NS_A, "tc"), attrs)
    _append_svg_table_cell_text_body(tc, cell.rect, cell.text)
    tc_pr = ET.SubElement(tc, qn(NS_A, "tcPr"))
    if cell.rect is not None:
        _append_svg_table_cell_fill(tc_pr, cell.rect.paint)
        _append_svg_table_cell_borders(tc_pr, cell)


def _append_svg_table_cell_text_body(parent: ET.Element, rect: Shape | None, text: Shape | None) -> None:
    tx_body = ET.SubElement(parent, qn(NS_A, "txBody"))
    attrs = _svg_table_cell_text_inset_attrs(rect, text)
    body_anchor = _text_baseline_to_dml(text.text_baseline if text is not None else None)
    if body_anchor:
        attrs["anchor"] = body_anchor
    if text is not None and text.text_wrap == "none":
        attrs["wrap"] = "none"
    ET.SubElement(tx_body, qn(NS_A, "bodyPr"), attrs)
    ET.SubElement(tx_body, qn(NS_A, "lstStyle"))
    paragraph = ET.SubElement(tx_body, qn(NS_A, "p"))
    paragraph_attrs = _paragraph_attrs(text.text_anchor if text is not None else None, text.text_direction if text is not None else None)
    if paragraph_attrs:
        ET.SubElement(paragraph, qn(NS_A, "pPr"), paragraph_attrs)
    if text is not None:
        _append_shape_text_runs(paragraph, text)
    ET.SubElement(paragraph, qn(NS_A, "endParaRPr"))


def _svg_table_cell_text_inset_attrs(rect: Shape | None, text: Shape | None) -> dict[str, str]:
    attrs = {"lIns": "0", "rIns": "0", "tIns": "0", "bIns": "0"}
    if rect is None or text is None:
        return attrs
    attrs["lIns"] = str(_emu(max(0.0, text.x - rect.x)))
    attrs["rIns"] = str(_emu(max(0.0, rect.x + rect.width - text.x - text.width)))
    attrs["tIns"] = str(_emu(max(0.0, text.y - rect.y)))
    attrs["bIns"] = str(_emu(max(0.0, rect.y + rect.height - text.y - text.height)))
    return attrs


def _append_shape_text_runs(parent: ET.Element, shape: Shape) -> None:
    if shape.text_runs:
        for text_run in shape.text_runs:
            if text_run.break_before:
                ET.SubElement(parent, qn(NS_A, "br"))
            _append_text_run(parent, text_run)
        return
    text_run = TextRun(
        text=shape.text or "",
        paint=shape.paint,
        font_size=shape.font_size,
        font_weight=shape.font_weight,
        font_style=shape.font_style,
        font_family=shape.font_family,
        font_variant=shape.font_variant,
        text_decoration=shape.text_decoration,
        text_decoration_style=shape.text_decoration_style,
        text_decoration_color=shape.text_decoration_color,
        text_decoration_alpha=shape.text_decoration_alpha,
        text_decoration_thickness=shape.text_decoration_thickness,
        text_baseline_shift=shape.text_baseline_shift,
        letter_spacing=shape.letter_spacing,
    )
    lines = text_run.text.split("\n")
    _append_text_run(parent, replace(text_run, text=lines[0] if lines else ""))
    for line in lines[1:]:
        ET.SubElement(parent, qn(NS_A, "br"))
        _append_text_run(parent, replace(text_run, text=line))


def _append_svg_table_cell_fill(parent: ET.Element, paint: Paint) -> None:
    if paint.fill == "none":
        ET.SubElement(parent, qn(NS_A, "noFill"))
    elif paint.fill:
        fill = ET.SubElement(parent, qn(NS_A, "solidFill"))
        color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": paint.fill.removeprefix("#").upper()})
        _append_alpha(color, paint.fill_alpha)


def _append_svg_table_cell_borders(parent: ET.Element, cell: SvgTableCell) -> None:
    fallback = cell.rect.paint if cell.rect is not None else Paint(stroke="none")
    for tag, paint in (
        ("lnL", cell.border_left or fallback),
        ("lnR", cell.border_right or fallback),
        ("lnT", cell.border_top or fallback),
        ("lnB", cell.border_bottom or fallback),
    ):
        attrs = {"w": str(_emu(paint.stroke_width if paint.stroke_width is not None else 1.0))}
        if paint.stroke_linecap:
            attrs["cap"] = _svg_linecap_to_dml(paint.stroke_linecap)
        if paint.stroke_compound:
            attrs["cmpd"] = paint.stroke_compound
        ln = ET.SubElement(parent, qn(NS_A, tag), attrs)
        if paint.stroke == "none":
            ET.SubElement(ln, qn(NS_A, "noFill"))
        elif paint.stroke:
            fill = ET.SubElement(ln, qn(NS_A, "solidFill"))
            color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": paint.stroke.removeprefix("#").upper()})
            _append_alpha(color, paint.stroke_alpha)
            _append_dml_dash(ln, paint.stroke_dasharray, paint.stroke_width)
            _append_dml_join(ln, paint.stroke_linejoin, paint.stroke_miterlimit)
        else:
            ET.SubElement(ln, qn(NS_A, "noFill"))


def _svg_text_x(shape: Shape) -> float:
    if shape.text_anchor == "middle":
        return shape.x + shape.width / 2
    if shape.text_anchor == "end":
        return shape.x + shape.width
    return shape.x


def _svg_text_y(shape: Shape) -> float:
    if shape.text_baseline == "middle":
        return shape.y + shape.height / 2
    if shape.text_baseline == "text-after-edge":
        return shape.y + shape.height
    return shape.y + (shape.font_size or shape.height / 1.4)


def _svg_paint(
    style: dict[str, str],
    refs: dict[str, ET.Element] | None = None,
    default_fill: bool = True,
    css: list[CssRule] | None = None,
    viewport: tuple[float, float] = (0.0, 0.0),
) -> Paint:
    refs = refs or {}
    css = css or []
    fill, fill_color_alpha = _paint_value(style.get("fill"), refs, style.get("color"), css)
    stroke, stroke_color_alpha = _paint_value(style.get("stroke"), refs, style.get("color"), css)
    if fill is None:
        fill = "#000000" if default_fill else "none"
    if stroke is None:
        stroke = "none"
    parsed_stroke_width = _svg_stroke_width(style, viewport)
    if parsed_stroke_width == 0:
        stroke = "none"
    fill_alpha = _combined_alpha(_alpha(style, "fill"), fill_color_alpha)
    stroke_alpha = _combined_alpha(_alpha(style, "stroke"), stroke_color_alpha)
    if fill_alpha is not None and fill_alpha <= 0:
        fill = "none"
    if stroke_alpha is not None and stroke_alpha <= 0:
        stroke = "none"
    if stroke not in {None, "none"} and parsed_stroke_width is None:
        parsed_stroke_width = 1.0
    stroke_linecap = _svg_linecap(style.get("stroke-linecap"))
    if stroke not in {None, "none"} and not stroke_linecap:
        stroke_linecap = "butt"
    stroke_linejoin = _svg_linejoin(style.get("stroke-linejoin"))
    if stroke not in {None, "none"} and not stroke_linejoin:
        stroke_linejoin = "miter"
    stroke_miterlimit = _optional_num(style.get("stroke-miterlimit"))
    if stroke_miterlimit is not None and stroke_miterlimit < 1:
        stroke_miterlimit = None
    if stroke_linejoin == "miter" and stroke_miterlimit is None:
        stroke_miterlimit = 4.0
    return Paint(
        fill=fill,
        stroke=stroke,
        stroke_width=parsed_stroke_width,
        fill_alpha=fill_alpha,
        stroke_alpha=stroke_alpha,
        stroke_linecap=stroke_linecap,
        stroke_linejoin=stroke_linejoin,
        stroke_dasharray=_svg_effective_dasharray(style, viewport),
        stroke_miterlimit=stroke_miterlimit,
        marker_start=_svg_marker_value(_svg_marker_style_value(style, "marker-start"), refs),
        marker_end=_svg_marker_value(_svg_marker_style_value(style, "marker-end"), refs),
    )


def _paint_without_markers(paint: Paint) -> Paint:
    return Paint(
        fill=paint.fill,
        stroke=paint.stroke,
        stroke_width=paint.stroke_width,
        fill_alpha=paint.fill_alpha,
        stroke_alpha=paint.stroke_alpha,
        stroke_linecap=paint.stroke_linecap,
        stroke_linejoin=paint.stroke_linejoin,
        stroke_dasharray=paint.stroke_dasharray,
        stroke_miterlimit=paint.stroke_miterlimit,
        stroke_compound=paint.stroke_compound,
    )


def _scale_paint(paint: Paint, scale: float) -> Paint:
    if _close(scale, 1.0):
        return paint
    return Paint(
        fill=paint.fill,
        stroke=paint.stroke,
        stroke_width=paint.stroke_width * scale if paint.stroke_width is not None else None,
        fill_alpha=paint.fill_alpha,
        stroke_alpha=paint.stroke_alpha,
        stroke_linecap=paint.stroke_linecap,
        stroke_linejoin=paint.stroke_linejoin,
        stroke_dasharray=_scale_dasharray(paint.stroke_dasharray, scale),
        stroke_miterlimit=paint.stroke_miterlimit,
        stroke_compound=paint.stroke_compound,
        marker_start=paint.marker_start,
        marker_end=paint.marker_end,
    )


def _scale_dasharray(value: str | None, scale: float) -> str | None:
    if value in {None, "", "none"}:
        return value
    nums = _svg_dasharray_numbers(value)
    if nums is None:
        return value
    return " ".join(_fmt(number * scale) for number in nums)


def _stroke_transform_scale(style: dict[str, str], matrix: tuple[float, float, float, float, float, float]) -> float:
    if " ".join(style.get("vector-effect", "").strip().lower().split()) == "non-scaling-stroke":
        return 1.0
    return _matrix_scale(matrix)


def _svg_marker_value(value: str | None, refs: dict[str, ET.Element]) -> str | None:
    if not value or value == "none":
        return None
    ref = _url_ref(value)
    if ref is None or ref[1].strip():
        return None
    marker_id = ref[0]
    marker = refs.get(marker_id)
    if marker is None or _local_name(marker.tag) != "marker":
        return None
    return marker_id


def _svg_marker_style_value(style: dict[str, str], attr: str) -> str | None:
    return style[attr] if attr in style else style.get("marker")


def _text_paint(
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule] | None = None,
    stroke_scale: float = 1.0,
    viewport: tuple[float, float] = (0.0, 0.0),
) -> Paint:
    return _scale_paint(_paint_without_markers(_svg_paint(style, refs, css=css, viewport=viewport)), stroke_scale)


def _svg_stroke_width(style: dict[str, str], viewport: tuple[float, float] = (0.0, 0.0)) -> float | None:
    value = style.get("stroke-width")
    if value in {None, "", "none"}:
        return None
    parsed = _length(value, 1, "diag", viewport)
    if parsed < 0:
        return None
    return parsed


def _font_family(value: str | None) -> str | None:
    if not value:
        return None
    first = _css_function_args(value)[0].strip()
    return first.strip("\"'") or None


def _dml_paint(sp_pr: ET.Element, element: ET.Element | None = None) -> Paint:
    fill = None
    solid_fill = sp_pr.find(qn(NS_A, "solidFill"))
    grad_fill = sp_pr.find(qn(NS_A, "gradFill"))
    pattern_fill = sp_pr.find(qn(NS_A, "pattFill"))
    no_fill = sp_pr.find(qn(NS_A, "noFill"))
    if solid_fill is not None:
        fill = _dml_color(solid_fill)
        fill_alpha = _dml_alpha(solid_fill)
    elif grad_fill is not None:
        fill, fill_alpha = _dml_gradient_fill(grad_fill)
    elif pattern_fill is not None:
        fill, fill_alpha = _dml_pattern_fill(pattern_fill)
    elif no_fill is not None:
        fill = "none"
        fill_alpha = None
    else:
        fill, fill_alpha = _dml_style_color(element, "fillRef")
        if fill is None:
            fill_alpha = None

    style_stroke, style_stroke_alpha = _dml_style_color(element, "lnRef")

    stroke = style_stroke
    stroke_alpha = style_stroke_alpha
    if style_stroke is None:
        stroke_alpha = None
    stroke_width = None
    stroke_linecap = None
    stroke_linejoin = None
    stroke_dasharray = None
    stroke_miterlimit = None
    marker_start = None
    marker_end = None
    ln = sp_pr.find(qn(NS_A, "ln"))
    if ln is not None:
        stroke_width = _dml_line_width(ln)
        stroke_linecap = _dml_linecap(ln.get("cap"))
        stroke_linejoin = _dml_linejoin(ln)
        stroke_dasharray = _dml_dasharray(ln)
        stroke_miterlimit = _dml_miterlimit(ln)
        marker_start = _dml_line_arrow(ln.find(qn(NS_A, "tailEnd")))
        marker_end = _dml_line_arrow(ln.find(qn(NS_A, "headEnd")))
        line_color = _dml_line_color(ln)
        if line_color is not None:
            stroke = line_color
            stroke_alpha = _dml_line_alpha(ln)
    return Paint(
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width,
        fill_alpha=fill_alpha,
        stroke_alpha=stroke_alpha,
        stroke_linecap=stroke_linecap,
        stroke_linejoin=stroke_linejoin,
        stroke_dasharray=stroke_dasharray,
        stroke_miterlimit=stroke_miterlimit,
        marker_start=marker_start,
        marker_end=marker_end,
    )


def _dml_style_color(element: ET.Element | None, tag: str) -> tuple[str | None, float | None]:
    if element is None:
        return None, None
    style = element.find(qn(NS_P, "style"))
    if style is None:
        style = element.find(qn(NS_A, "style"))
    if style is None:
        return None, None
    ref = style.find(qn(NS_A, tag))
    if ref is None:
        return None, None
    return _dml_color(ref), _dml_alpha(ref)


def _dml_text_paint(element: ET.Element, sp_pr: ET.Element) -> Paint:
    r_pr = _dml_text_run_properties(element)
    def_r_pr = _dml_default_text_run_properties(element)
    end_para_r_pr = _dml_end_paragraph_text_run_properties(element)
    ln = _dml_text_line_properties(r_pr, def_r_pr, end_para_r_pr)
    shape_paint = _dml_paint(sp_pr, element)
    fill, fill_alpha = _dml_text_fill(element, r_pr, def_r_pr, end_para_r_pr, shape_paint)
    return Paint(
        fill=fill,
        stroke=_dml_line_color(ln) if ln is not None else shape_paint.stroke,
        stroke_width=_dml_line_width(ln) if ln is not None else shape_paint.stroke_width,
        fill_alpha=fill_alpha,
        stroke_alpha=_dml_line_alpha(ln) if ln is not None else shape_paint.stroke_alpha,
        stroke_linecap=_dml_linecap(ln.get("cap")) if ln is not None else shape_paint.stroke_linecap,
        stroke_linejoin=_dml_linejoin(ln) if ln is not None else shape_paint.stroke_linejoin,
        stroke_dasharray=_dml_dasharray(ln) if ln is not None else shape_paint.stroke_dasharray,
        stroke_miterlimit=_dml_miterlimit(ln) if ln is not None else shape_paint.stroke_miterlimit,
    )


def _dml_text_fill(
    element: ET.Element,
    r_pr: ET.Element | None,
    def_r_pr: ET.Element | None,
    end_para_r_pr: ET.Element | None,
    shape_paint: Paint,
) -> tuple[str | None, float | None]:
    source = _dml_text_fill_properties(r_pr)
    if source is None:
        source = _dml_text_fill_properties(def_r_pr)
    if source is None:
        source = _dml_text_fill_properties(end_para_r_pr)
    if source is None:
        font_fill, font_alpha = _dml_style_color(element, "fontRef")
        if font_fill is not None:
            return font_fill, font_alpha
        return shape_paint.fill, shape_paint.fill_alpha
    if source.find(qn(NS_A, "noFill")) is not None:
        return "none", None
    solid_fill = source.find(qn(NS_A, "solidFill"))
    if solid_fill is not None:
        return _dml_color(solid_fill), _dml_alpha(solid_fill)
    grad_fill = source.find(qn(NS_A, "gradFill"))
    if grad_fill is not None:
        return _dml_gradient_fill(grad_fill)
    pattern_fill = source.find(qn(NS_A, "pattFill"))
    if pattern_fill is not None:
        return _dml_pattern_fill(pattern_fill)
    return shape_paint.fill, shape_paint.fill_alpha


def _dml_text_fill_properties(element: ET.Element | None) -> ET.Element | None:
    if element is None:
        return None
    for tag in ("noFill", "solidFill", "gradFill", "pattFill"):
        if element.find(qn(NS_A, tag)) is not None:
            return element
    return None


def _dml_text_line_properties(
    r_pr: ET.Element | None,
    def_r_pr: ET.Element | None,
    end_para_r_pr: ET.Element | None = None,
) -> ET.Element | None:
    if r_pr is not None and r_pr.find(qn(NS_A, "ln")) is not None:
        return r_pr.find(qn(NS_A, "ln"))
    if def_r_pr is not None and def_r_pr.find(qn(NS_A, "ln")) is not None:
        return def_r_pr.find(qn(NS_A, "ln"))
    if end_para_r_pr is not None and end_para_r_pr.find(qn(NS_A, "ln")) is not None:
        return end_para_r_pr.find(qn(NS_A, "ln"))
    return None


def _append_dml_paint(parent: ET.Element, paint: Paint) -> None:
    if paint.fill == "none":
        ET.SubElement(parent, qn(NS_A, "noFill"))
    elif paint.fill:
        fill = ET.SubElement(parent, qn(NS_A, "solidFill"))
        color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": paint.fill.removeprefix("#").upper()})
        _append_alpha(color, paint.fill_alpha)

    if paint.stroke == "none":
        attrs = {}
        if paint.stroke_width is not None:
            attrs["w"] = str(_emu(max(0.0, paint.stroke_width)))
        ln = ET.SubElement(parent, qn(NS_A, "ln"), attrs)
        ET.SubElement(ln, qn(NS_A, "noFill"))
    elif paint.stroke or paint.stroke_width:
        attrs = {}
        if paint.stroke_width:
            attrs["w"] = str(_emu(paint.stroke_width))
        if paint.stroke_linecap:
            attrs["cap"] = _svg_linecap_to_dml(paint.stroke_linecap)
        if paint.stroke_compound:
            attrs["cmpd"] = paint.stroke_compound
        ln = ET.SubElement(parent, qn(NS_A, "ln"), attrs)
        if paint.stroke:
            solid = ET.SubElement(ln, qn(NS_A, "solidFill"))
            color = ET.SubElement(solid, qn(NS_A, "srgbClr"), {"val": paint.stroke.removeprefix("#").upper()})
            _append_alpha(color, paint.stroke_alpha)
        _append_dml_dash(ln, paint.stroke_dasharray, paint.stroke_width)
        _append_dml_join(ln, paint.stroke_linejoin, paint.stroke_miterlimit)
        _append_dml_arrow(ln, "tailEnd", paint.marker_start)
        _append_dml_arrow(ln, "headEnd", paint.marker_end)


def _append_custom_geometry(parent: ET.Element, shape: Shape) -> None:
    custom = ET.SubElement(parent, qn(NS_A, "custGeom"))
    ET.SubElement(custom, qn(NS_A, "avLst"))
    ET.SubElement(custom, qn(NS_A, "gdLst"))
    ET.SubElement(custom, qn(NS_A, "ahLst"))
    ET.SubElement(custom, qn(NS_A, "cxnLst"))
    rect = ET.SubElement(custom, qn(NS_A, "rect"))
    rect.attrib.update({"l": "l", "t": "t", "r": "r", "b": "b"})
    path_lst = ET.SubElement(custom, qn(NS_A, "pathLst"))
    path = ET.SubElement(path_lst, qn(NS_A, "path"), {"w": str(_emu(shape.width)), "h": str(_emu(shape.height))})
    for index, (x, y) in enumerate(shape.points):
        command = "moveTo" if index == 0 else "lnTo"
        node = ET.SubElement(path, qn(NS_A, command))
        ET.SubElement(node, qn(NS_A, "pt"), {"x": str(_emu(x - shape.x)), "y": str(_emu(y - shape.y))})
    if shape.closed:
        ET.SubElement(path, qn(NS_A, "close"))


def _append_text_body(parent: ET.Element, shape: Shape) -> None:
    tx_body = ET.SubElement(parent, qn(NS_P, "txBody"))
    body_pr_attrs = {"wrap": "none", "lIns": "0", "rIns": "0", "tIns": "0", "bIns": "0"}
    body_anchor = _text_baseline_to_dml(shape.text_baseline)
    if body_anchor:
        body_pr_attrs["anchor"] = body_anchor
    ET.SubElement(tx_body, qn(NS_A, "bodyPr"), body_pr_attrs)
    ET.SubElement(tx_body, qn(NS_A, "lstStyle"))
    paragraph = ET.SubElement(tx_body, qn(NS_A, "p"))
    paragraph_attrs = _paragraph_attrs(shape.text_anchor, shape.text_direction)
    if paragraph_attrs:
        ET.SubElement(paragraph, qn(NS_A, "pPr"), paragraph_attrs)
    if shape.text_runs:
        for text_run in shape.text_runs:
            if text_run.break_before:
                ET.SubElement(paragraph, qn(NS_A, "br"))
            _append_text_run(paragraph, text_run)
    else:
        text_run = TextRun(
            text=shape.text or "",
            paint=shape.paint,
            font_size=shape.font_size,
            font_weight=shape.font_weight,
            font_style=shape.font_style,
            font_family=shape.font_family,
            font_variant=shape.font_variant,
            text_decoration=shape.text_decoration,
            text_decoration_style=shape.text_decoration_style,
            text_decoration_color=shape.text_decoration_color,
            text_decoration_alpha=shape.text_decoration_alpha,
            text_decoration_thickness=shape.text_decoration_thickness,
            text_baseline_shift=shape.text_baseline_shift,
            letter_spacing=shape.letter_spacing,
        )
        lines = text_run.text.split("\n")
        _append_text_run(paragraph, replace(text_run, text=lines[0] if lines else ""))
        for line in lines[1:]:
            ET.SubElement(paragraph, qn(NS_A, "br"))
            _append_text_run(paragraph, replace(text_run, text=line))
    ET.SubElement(paragraph, qn(NS_A, "endParaRPr"))


def _append_text_run(parent: ET.Element, text_run: TextRun) -> None:
    run = ET.SubElement(parent, qn(NS_A, "r"))
    r_pr = ET.SubElement(run, qn(NS_A, "rPr"), _text_run_attrs(text_run))
    _append_text_run_properties(r_pr, text_run)
    ET.SubElement(run, qn(NS_A, "t")).text = text_run.text


def _text_run_attrs(text_run: TextRun) -> dict[str, str]:
    attrs = {}
    if text_run.font_size:
        attrs["sz"] = str(round(text_run.font_size * 100))
    if _is_bold(text_run.font_weight):
        attrs["b"] = "1"
    if _is_italic(text_run.font_style):
        attrs["i"] = "1"
    if text_run.font_variant == "small-caps":
        attrs["cap"] = "small"
    elif text_run.font_variant == "all-small-caps":
        attrs["cap"] = "all"
    underline = _dml_underline_value(text_run.text_decoration, text_run.text_decoration_style)
    if underline:
        attrs["u"] = underline
    if _has_text_decoration(text_run.text_decoration, "line-through"):
        attrs["strike"] = "sngStrike"
    if text_run.text_baseline_shift == "super":
        attrs["baseline"] = "30000"
    elif text_run.text_baseline_shift == "sub":
        attrs["baseline"] = "-25000"
    if text_run.letter_spacing is not None:
        attrs["spc"] = str(round(text_run.letter_spacing * 0.75 * 100))
    return attrs


def _append_text_run_properties(r_pr: ET.Element, text_run: TextRun) -> None:
    paint = text_run.paint
    if paint.fill and paint.fill != "none":
        fill = ET.SubElement(r_pr, qn(NS_A, "solidFill"))
        color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": paint.fill.removeprefix("#").upper()})
        _append_alpha(color, paint.fill_alpha)
    if paint.stroke and paint.stroke != "none":
        attrs = {}
        if paint.stroke_width is not None:
            attrs["w"] = str(_emu(paint.stroke_width))
        if paint.stroke_linecap:
            attrs["cap"] = _svg_linecap_to_dml(paint.stroke_linecap)
        if paint.stroke_compound:
            attrs["cmpd"] = paint.stroke_compound
        ln = ET.SubElement(r_pr, qn(NS_A, "ln"), attrs)
        solid = ET.SubElement(ln, qn(NS_A, "solidFill"))
        color = ET.SubElement(solid, qn(NS_A, "srgbClr"), {"val": paint.stroke.removeprefix("#").upper()})
        _append_alpha(color, paint.stroke_alpha)
        _append_dml_dash(ln, paint.stroke_dasharray, paint.stroke_width)
        _append_dml_join(ln, paint.stroke_linejoin, paint.stroke_miterlimit)
    if text_run.text_decoration_color and _has_text_decoration(text_run.text_decoration, "underline"):
        u_fill = ET.SubElement(r_pr, qn(NS_A, "uFill"))
        fill = ET.SubElement(u_fill, qn(NS_A, "solidFill"))
        color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": text_run.text_decoration_color.removeprefix("#").upper()})
        _append_alpha(color, text_run.text_decoration_alpha)
    if text_run.text_decoration_thickness is not None and _has_text_decoration(text_run.text_decoration, "underline"):
        ET.SubElement(r_pr, qn(NS_A, "uLn"), {"w": str(_emu(text_run.text_decoration_thickness))})
    if text_run.font_family:
        ET.SubElement(r_pr, qn(NS_A, "latin"), {"typeface": text_run.font_family})


def _dml_color(parent: ET.Element) -> str | None:
    srgb = parent.find(qn(NS_A, "srgbClr"))
    if srgb is not None and srgb.get("val"):
        return _apply_dml_luminance_modifiers(f"#{srgb.get('val', '').lower()}", srgb)
    scrgb = parent.find(qn(NS_A, "scrgbClr"))
    if scrgb is not None:
        return _dml_scrgb_color(scrgb)
    hsl = parent.find(qn(NS_A, "hslClr"))
    if hsl is not None:
        return _dml_hsl_color(hsl)
    scheme = parent.find(qn(NS_A, "schemeClr"))
    if scheme is not None and scheme.get("val"):
        return _dml_scheme_color(scheme)
    system = parent.find(qn(NS_A, "sysClr"))
    if system is not None and system.get("lastClr"):
        return _apply_dml_luminance_modifiers(f"#{system.get('lastClr', '').lower()}", system)
    preset = parent.find(qn(NS_A, "prstClr"))
    if preset is not None and preset.get("val"):
        return _dml_preset_color(preset)
    return None


def _dml_gradient_fill(element: ET.Element) -> tuple[str | None, float | None]:
    stops = []
    for stop in element.findall(f"{qn(NS_A, 'gsLst')}/{qn(NS_A, 'gs')}"):
        color = _dml_color(stop)
        rgb = _hex_to_rgb(color or "")
        if rgb is not None:
            alpha = _dml_alpha(stop)
            stops.append((*rgb, 1.0 if alpha is None else alpha))
    if not stops:
        return None, None
    count = len(stops)
    rgb_avg = tuple(round(sum(stop[index] for stop in stops) / count) for index in range(3))
    alpha_avg = sum(stop[3] for stop in stops) / count
    return _rgb_to_hex(rgb_avg), alpha_avg if alpha_avg < 1 else None


def _dml_pattern_fill(element: ET.Element) -> tuple[str | None, float | None]:
    colors = []
    for tag in ("fgClr", "bgClr"):
        color_element = element.find(qn(NS_A, tag))
        if color_element is None:
            continue
        color = _dml_color(color_element)
        rgb = _hex_to_rgb(color or "")
        if rgb is not None:
            alpha = _dml_alpha(color_element)
            colors.append((*rgb, 1.0 if alpha is None else alpha))
    if not colors:
        return None, None
    count = len(colors)
    rgb_avg = tuple(round(sum(color[index] for color in colors) / count) for index in range(3))
    alpha_avg = sum(color[3] for color in colors) / count
    return _rgb_to_hex(rgb_avg), alpha_avg if alpha_avg < 1 else None


def _dml_scrgb_color(element: ET.Element) -> str | None:
    if element.get("r") is None or element.get("g") is None or element.get("b") is None:
        return None
    channels = (
        round(_dml_percentage(element.get("r"), 0) * 255),
        round(_dml_percentage(element.get("g"), 0) * 255),
        round(_dml_percentage(element.get("b"), 0) * 255),
    )
    color = _rgb_to_hex(tuple(max(0, min(255, channel)) for channel in channels))
    return _apply_dml_luminance_modifiers(color, element)


def _dml_hsl_color(element: ET.Element) -> str | None:
    if element.get("hue") is None or element.get("sat") is None or element.get("lum") is None:
        return None
    hue = (_dml_float(element.get("hue"), 0) or 0) / 60000 % 360
    saturation = _dml_percentage(element.get("sat"), 0)
    luminance = _dml_percentage(element.get("lum"), 0)
    red, green, blue = colorsys.hls_to_rgb(hue / 360, luminance, saturation)
    color = _rgb_to_hex((round(red * 255), round(green * 255), round(blue * 255)))
    return _apply_dml_luminance_modifiers(color, element)


def _dml_scheme_color(element: ET.Element) -> str | None:
    color = {
        "accent1": "#4472c4",
        "accent2": "#ed7d31",
        "accent3": "#a5a5a5",
        "accent4": "#ffc000",
        "accent5": "#5b9bd5",
        "accent6": "#70ad47",
        "bg1": "#ffffff",
        "bg2": "#e7e6e6",
        "dk1": "#000000",
        "dk2": "#44546a",
        "folHlink": "#954f72",
        "hlink": "#0563c1",
        "lt1": "#ffffff",
        "lt2": "#e7e6e6",
        "tx1": "#000000",
        "tx2": "#44546a",
    }.get(element.get("val", ""))
    if color is None:
        return None
    return _apply_dml_luminance_modifiers(color, element)


def _dml_preset_color(element: ET.Element) -> str | None:
    color = {
        "aliceBlue": "#f0f8ff",
        "antiqueWhite": "#faebd7",
        "aqua": "#00ffff",
        "aquamarine": "#7fffd4",
        "azure": "#f0ffff",
        "beige": "#f5f5dc",
        "bisque": "#ffe4c4",
        "black": "#000000",
        "blanchedAlmond": "#ffebcd",
        "blue": "#0000ff",
        "blueViolet": "#8a2be2",
        "brown": "#a52a2a",
        "burlyWood": "#deb887",
        "cadetBlue": "#5f9ea0",
        "chartreuse": "#7fff00",
        "chocolate": "#d2691e",
        "coral": "#ff7f50",
        "cornflowerBlue": "#6495ed",
        "cornsilk": "#fff8dc",
        "crimson": "#dc143c",
        "cyan": "#00ffff",
        "dkBlue": "#00008b",
        "dkCyan": "#008b8b",
        "dkGoldenrod": "#b8860b",
        "dkGray": "#a9a9a9",
        "dkGreen": "#006400",
        "dkGrey": "#a9a9a9",
        "dkKhaki": "#bdb76b",
        "dkMagenta": "#8b008b",
        "dkOliveGreen": "#556b2f",
        "dkOrange": "#ff8c00",
        "dkOrchid": "#9932cc",
        "dkRed": "#8b0000",
        "dkSalmon": "#e9967a",
        "dkSeaGreen": "#8fbc8f",
        "dkSlateBlue": "#483d8b",
        "dkSlateGray": "#2f4f4f",
        "dkSlateGrey": "#2f4f4f",
        "dkTurquoise": "#00ced1",
        "dkViolet": "#9400d3",
        "dkYellow": "#808000",
        "deepPink": "#ff1493",
        "deepSkyBlue": "#00bfff",
        "dimGray": "#696969",
        "dimGrey": "#696969",
        "dodgerBlue": "#1e90ff",
        "firebrick": "#b22222",
        "floralWhite": "#fffaf0",
        "forestGreen": "#228b22",
        "fuchsia": "#ff00ff",
        "gainsboro": "#dcdcdc",
        "ghostWhite": "#f8f8ff",
        "gold": "#ffd700",
        "goldenrod": "#daa520",
        "gray": "#808080",
        "green": "#008000",
        "greenYellow": "#adff2f",
        "grey": "#808080",
        "honeydew": "#f0fff0",
        "hotPink": "#ff69b4",
        "indianRed": "#cd5c5c",
        "indigo": "#4b0082",
        "ivory": "#fffff0",
        "khaki": "#f0e68c",
        "lavender": "#e6e6fa",
        "lavenderBlush": "#fff0f5",
        "lawnGreen": "#7cfc00",
        "lemonChiffon": "#fffacd",
        "ltBlue": "#add8e6",
        "ltCoral": "#f08080",
        "ltCyan": "#e0ffff",
        "ltGoldenrodYellow": "#fafad2",
        "ltGray": "#d3d3d3",
        "ltGreen": "#90ee90",
        "ltGrey": "#d3d3d3",
        "ltPink": "#ffb6c1",
        "ltSalmon": "#ffa07a",
        "ltSeaGreen": "#20b2aa",
        "ltSkyBlue": "#87cefa",
        "ltSlateGray": "#778899",
        "ltSlateGrey": "#778899",
        "ltSteelBlue": "#b0c4de",
        "ltYellow": "#ffffe0",
        "lime": "#00ff00",
        "limeGreen": "#32cd32",
        "linen": "#faf0e6",
        "magenta": "#ff00ff",
        "medAquamarine": "#66cdaa",
        "medBlue": "#0000cd",
        "medOrchid": "#ba55d3",
        "medPurple": "#9370db",
        "medSeaGreen": "#3cb371",
        "medSlateBlue": "#7b68ee",
        "medSpringGreen": "#00fa9a",
        "medTurquoise": "#48d1cc",
        "medVioletRed": "#c71585",
        "midnightBlue": "#191970",
        "mintCream": "#f5fffa",
        "mistyRose": "#ffe4e1",
        "moccasin": "#ffe4b5",
        "navajoWhite": "#ffdead",
        "navy": "#000080",
        "oldLace": "#fdf5e6",
        "olive": "#808000",
        "oliveDrab": "#6b8e23",
        "orange": "#ffa500",
        "orangeRed": "#ff4500",
        "orchid": "#da70d6",
        "paleGoldenrod": "#eee8aa",
        "paleGreen": "#98fb98",
        "paleTurquoise": "#afeeee",
        "paleVioletRed": "#db7093",
        "papayaWhip": "#ffefd5",
        "peachPuff": "#ffdab9",
        "peru": "#cd853f",
        "pink": "#ffc0cb",
        "plum": "#dda0dd",
        "powderBlue": "#b0e0e6",
        "purple": "#800080",
        "red": "#ff0000",
        "rosyBrown": "#bc8f8f",
        "royalBlue": "#4169e1",
        "saddleBrown": "#8b4513",
        "salmon": "#fa8072",
        "sandyBrown": "#f4a460",
        "seaGreen": "#2e8b57",
        "seaShell": "#fff5ee",
        "sienna": "#a0522d",
        "silver": "#c0c0c0",
        "skyBlue": "#87ceeb",
        "slateBlue": "#6a5acd",
        "slateGray": "#708090",
        "slateGrey": "#708090",
        "snow": "#fffafa",
        "springGreen": "#00ff7f",
        "steelBlue": "#4682b4",
        "tan": "#d2b48c",
        "teal": "#008080",
        "thistle": "#d8bfd8",
        "tomato": "#ff6347",
        "turquoise": "#40e0d0",
        "violet": "#ee82ee",
        "wheat": "#f5deb3",
        "white": "#ffffff",
        "whiteSmoke": "#f5f5f5",
        "yellow": "#ffff00",
        "yellowGreen": "#9acd32",
    }.get(element.get("val", ""))
    if color is None:
        return None
    return _apply_dml_luminance_modifiers(color, element)


def _apply_dml_luminance_modifiers(color: str, element: ET.Element) -> str | None:
    parsed = _hex_to_rgb(color)
    if parsed is None:
        return None
    rgb = list(parsed)
    shade = element.find(qn(NS_A, "shade"))
    tint = element.find(qn(NS_A, "tint"))
    lum_mod = element.find(qn(NS_A, "lumMod"))
    lum_off = element.find(qn(NS_A, "lumOff"))
    if shade is not None and shade.get("val") is not None:
        factor = _dml_percentage(shade.get("val"), 100000)
        rgb = [round(channel * factor) for channel in rgb]
    if tint is not None and tint.get("val") is not None:
        factor = _dml_percentage(tint.get("val"), 100000)
        rgb = [round(channel + (255 - channel) * factor) for channel in rgb]
    if lum_mod is not None and lum_mod.get("val") is not None:
        factor = _dml_percentage(lum_mod.get("val"), 100000)
        rgb = [round(channel * factor) for channel in rgb]
    if lum_off is not None and lum_off.get("val") is not None:
        offset = _dml_percentage(lum_off.get("val"), 0)
        rgb = [round(channel + (255 - channel) * offset) for channel in rgb]
    return _rgb_to_hex(tuple(max(0, min(255, channel)) for channel in rgb))


def _dml_percentage(value: str | None, default: int) -> float:
    try:
        result = int(value or default) / 100000
    except (OverflowError, ValueError):
        return default / 100000
    return result if math.isfinite(result) else default / 100000


def _dml_int(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _dml_float(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        number = float(value)
    except ValueError:
        return default
    return number if math.isfinite(number) else default


def _dml_alpha(parent: ET.Element) -> float | None:
    alpha = parent.find(f".//{qn(NS_A, 'alpha')}")
    result = None
    if alpha is not None and alpha.get("val"):
        value = _dml_int(alpha.get("val"))
        if value is not None:
            result = value / 100000
    alpha_mod = parent.find(f".//{qn(NS_A, 'alphaMod')}")
    if alpha_mod is not None and alpha_mod.get("amt"):
        value = _dml_int(alpha_mod.get("amt"))
        if value is not None:
            result = (1.0 if result is None else result) * value / 100000
    return result


def _dml_blip_alpha(blip: ET.Element) -> float | None:
    alpha_mod_fix = blip.find(qn(NS_A, "alphaModFix"))
    if alpha_mod_fix is not None and alpha_mod_fix.get("amt") is not None:
        value = _dml_int(alpha_mod_fix.get("amt"))
        return value / 100000 if value is not None else None
    return _dml_alpha(blip)


def _dml_line_width(ln: ET.Element | None) -> float | None:
    if ln is None or ln.get("w") is None:
        return None
    value = _dml_int(ln.get("w"))
    return _px(value) if value is not None else None


def _dml_line_color(ln: ET.Element | None) -> str | None:
    if ln is None:
        return None
    if ln.find(qn(NS_A, "noFill")) is not None:
        return "none"
    solid_line = ln.find(qn(NS_A, "solidFill"))
    if solid_line is not None:
        return _dml_color(solid_line)
    grad_line = ln.find(qn(NS_A, "gradFill"))
    if grad_line is not None:
        return _dml_gradient_fill(grad_line)[0]
    pattern_line = ln.find(qn(NS_A, "pattFill"))
    if pattern_line is not None:
        return _dml_pattern_fill(pattern_line)[0]
    return None


def _dml_line_alpha(ln: ET.Element | None) -> float | None:
    if ln is None:
        return None
    solid_line = ln.find(qn(NS_A, "solidFill"))
    if solid_line is not None:
        return _dml_alpha(solid_line)
    grad_line = ln.find(qn(NS_A, "gradFill"))
    if grad_line is not None:
        return _dml_gradient_fill(grad_line)[1]
    pattern_line = ln.find(qn(NS_A, "pattFill"))
    if pattern_line is not None:
        return _dml_pattern_fill(pattern_line)[1]
    return None


def _append_alpha(color: ET.Element, alpha: float | None) -> None:
    if alpha is None or alpha >= 1:
        return
    ET.SubElement(color, qn(NS_A, "alpha"), {"val": str(round(max(0.0, min(alpha, 1.0)) * 100000))})


def _color_with_alpha(color: str, alpha: float | None) -> str:
    if alpha is None or alpha >= 1:
        return color
    value = round(max(0.0, min(alpha, 1.0)) * 255)
    return f"{color}{value:02x}"


def _svg_linecap_to_dml(value: str) -> str:
    return {"butt": "flat", "round": "rnd", "square": "sq"}.get(value, "flat")


def _svg_linecap(value: str | None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    return normalized if normalized in {"butt", "round", "square"} else None


def _svg_linejoin(value: str | None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    if normalized == "miter-clip":
        return "miter"
    return normalized if normalized in {"bevel", "miter", "round"} else None


def _dml_linecap(value: str | None) -> str | None:
    return {"flat": "butt", "rnd": "round", "sq": "square"}.get(value or "")


def _append_dml_arrow(ln: ET.Element, tag: str, value: str | None) -> None:
    if value:
        ET.SubElement(ln, qn(NS_A, tag), {"type": "triangle"})


def _dml_line_arrow(element: ET.Element | None) -> str | None:
    if element is not None and element.get("type") not in {None, "none"}:
        return "svgraph-arrow"
    return None


def _append_dml_join(ln: ET.Element, value: str | None, miterlimit: float | None = None) -> None:
    if value == "round":
        ET.SubElement(ln, qn(NS_A, "round"))
    elif value == "bevel":
        ET.SubElement(ln, qn(NS_A, "bevel"))
    elif value == "miter":
        attrs = {}
        if miterlimit is not None:
            attrs["lim"] = str(round(max(1.0, miterlimit) * 100000))
        ET.SubElement(ln, qn(NS_A, "miter"), attrs)


def _dml_linejoin(ln: ET.Element) -> str | None:
    if ln.find(qn(NS_A, "round")) is not None:
        return "round"
    if ln.find(qn(NS_A, "bevel")) is not None:
        return "bevel"
    if ln.find(qn(NS_A, "miter")) is not None:
        return "miter"
    return None


def _dml_miterlimit(ln: ET.Element) -> float | None:
    miter = ln.find(qn(NS_A, "miter"))
    if miter is None or miter.get("lim") is None:
        return None
    value = _dml_int(miter.get("lim"))
    return value / 100000 if value is not None else None


def _append_dml_dash(ln: ET.Element, value: str | None, stroke_width: float | None = None) -> None:
    if not value or value == "none":
        return
    nums = _svg_dasharray_numbers(value)
    if nums and sum(nums) <= 0:
        return
    if nums and stroke_width and stroke_width > 0:
        if len(nums) % 2 == 1:
            nums = nums * 2
        custom = ET.SubElement(ln, qn(NS_A, "custDash"))
        for dash, space in zip(nums[0::2], nums[1::2], strict=False):
            ET.SubElement(
                custom,
                qn(NS_A, "ds"),
                {
                    "d": str(round(max(0.0, dash) / stroke_width * 100000)),
                    "sp": str(round(max(0.0, space) / stroke_width * 100000)),
                },
            )
        return
    dash = _svg_dasharray_to_dml(value)
    if dash:
        ET.SubElement(ln, qn(NS_A, "prstDash"), {"val": dash})


def _svg_effective_dasharray(style: dict[str, str], viewport: tuple[float, float] = (0.0, 0.0)) -> str | None:
    dasharray = style.get("stroke-dasharray")
    if dasharray is None:
        return None
    nums = _svg_dasharray_numbers(dasharray, viewport)
    if nums is None:
        return dasharray
    offset = _optional_length(style.get("stroke-dashoffset"), "diag", viewport)
    if offset is None or offset == 0:
        if _svg_dasharray_needs_resolution(dasharray):
            return " ".join(_fmt(number) for number in nums)
        return dasharray
    shifted = _svg_dasharray_with_offset(dasharray, offset, viewport)
    if shifted is None:
        return " ".join(_fmt(number) for number in nums)
    return " ".join(_fmt(number) for number in shifted)


def _svg_dashoffset_is_supported(style: dict[str, str], viewport: tuple[float, float] = (0.0, 0.0)) -> bool:
    offset = _optional_length(style.get("stroke-dashoffset"), "diag", viewport)
    dasharray = style.get("stroke-dasharray")
    return (
        offset is not None
        and offset != 0
        and dasharray is not None
        and _svg_dasharray_with_offset(dasharray, offset, viewport) is not None
    )


def _svg_dasharray_with_offset(value: str, offset: float, viewport: tuple[float, float] = (0.0, 0.0)) -> list[float] | None:
    nums = _svg_dasharray_numbers(value, viewport)
    if not nums or sum(nums) <= 0:
        return None
    if len(nums) % 2 == 1:
        nums = nums * 2
    period = sum(nums)
    if period <= 0:
        return None
    offset = offset % period
    if _close(offset, 0):
        return nums

    cursor = 0.0
    for index, length in enumerate(nums):
        end = cursor + length
        if offset < end or _close(offset, end):
            if _close(offset, end):
                cursor = end
                continue
            if index % 2 == 1:
                remaining_gap = end - offset
                if _close(remaining_gap, 0):
                    cursor = end
                    continue
                shifted = [0.0, remaining_gap, *nums[index + 1 :], *nums[:index]]
                consumed_gap = offset - cursor
                if not _close(consumed_gap, 0):
                    shifted.append(consumed_gap)
                if len(shifted) % 2 == 1:
                    shifted.append(0.0)
                return shifted
            remaining = end - offset
            if _close(remaining, 0):
                cursor = end
                continue
            shifted = [remaining, *nums[index + 1 :], *nums[:index]]
            consumed = offset - cursor
            if not _close(consumed, 0):
                shifted.append(consumed)
            if len(shifted) % 2 == 1:
                shifted.append(0.0)
            return shifted
        cursor = end
    return None


def _close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(left - right) < tolerance


def _svg_dasharray_numbers(value: str, viewport: tuple[float, float] = (0.0, 0.0)) -> list[float] | None:
    parts = _svg_dasharray_parts(value)
    if not parts:
        return None
    nums = []
    for part in parts:
        number = _length(part, math.nan, "diag", viewport)
        if math.isnan(number) or number < 0:
            return None
        nums.append(number)
    return nums


def _svg_dasharray_parts(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    paren_depth = 0
    for char in value.strip():
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        if (char.isspace() or char == ",") and paren_depth == 0:
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _svg_dasharray_needs_resolution(value: str) -> bool:
    return any(
        "%" in part or re.match(r"(?:calc|min|max|clamp)\(", part.strip(), flags=re.I)
        for part in _svg_dasharray_parts(value)
    )


def _svg_dasharray_to_dml(value: str) -> str | None:
    nums = _svg_dasharray_numbers(value)
    if not nums:
        return None
    if sum(nums) <= 0:
        return None
    if len(nums) == 1:
        return "dot"
    on, off = nums[0], nums[1]
    if on <= off * 1.5:
        return "dash"
    return "lgDash"


def _dml_dasharray(ln: ET.Element) -> str | None:
    custom = ln.find(qn(NS_A, "custDash"))
    if custom is not None:
        raw_width = _dml_int(ln.get("w"))
        width = _px(raw_width) if raw_width is not None else None
        if width:
            values = []
            for item in custom.findall(qn(NS_A, "ds")):
                dash = _dml_int(item.get("d"), 0)
                space = _dml_int(item.get("sp"), 0)
                values.append(_fmt((dash or 0) / 100000 * width))
                values.append(_fmt((space or 0) / 100000 * width))
            return " ".join(values) or None
    dash = ln.find(qn(NS_A, "prstDash"))
    if dash is None:
        return None
    return {
        "dash": "4 3",
        "dashDot": "4 3 1 3",
        "dot": "1 3",
        "lgDash": "8 3",
        "lgDashDot": "8 3 1 3",
        "lgDashDotDot": "8 3 1 3 1 3",
        "sysDash": "3 1",
        "sysDashDot": "3 1 1 1",
        "sysDashDotDot": "3 1 1 1 1 1",
        "sysDot": "1 1",
    }.get(dash.get("val", ""))


def _dml_text(element: ET.Element) -> str | None:
    tx_body = element.find(qn(NS_P, "txBody"))
    if tx_body is None:
        return None
    paragraphs = tx_body.findall(qn(NS_A, "p"))
    if not paragraphs:
        return ""
    text = "\n".join(_dml_paragraph_text(tx_body, paragraph, index + 1) for index, paragraph in enumerate(paragraphs))
    return text if text else ""


def _dml_paragraph_text(tx_body: ET.Element, paragraph: ET.Element, number: int) -> str:
    parts = []
    bullet = _dml_paragraph_bullet(tx_body, paragraph, number)
    if bullet is not None:
        parts.append(f"{bullet} ")
    for node in paragraph:
        if node.tag == qn(NS_A, "br"):
            parts.append("\n")
            continue
        if node.tag == qn(NS_A, "tab"):
            parts.append("\t")
            continue
        text_node = node.find(qn(NS_A, "t"))
        if text_node is not None:
            parts.append(text_node.text or "")
    return "".join(parts)


def _dml_text_runs(element: ET.Element, sp_pr: ET.Element) -> tuple[TextRun, ...]:
    tx_body = element.find(qn(NS_P, "txBody"))
    if tx_body is None:
        return ()
    return _dml_text_runs_from_body(element, tx_body, _dml_paint(sp_pr, element))


def _dml_text_runs_from_body(
    element: ET.Element,
    tx_body: ET.Element,
    shape_paint: Paint,
) -> tuple[TextRun, ...]:
    paragraphs = tx_body.findall(qn(NS_A, "p"))
    if not paragraphs:
        return ()
    runs: list[TextRun] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        p_pr = paragraph.find(qn(NS_A, "pPr"))
        def_r_pr = _dml_paragraph_default_run_properties(tx_body, p_pr)
        end_para_r_pr = paragraph.find(qn(NS_A, "endParaRPr"))
        paragraph_first_r_pr = _dml_first_paragraph_run_properties(paragraph)
        previous_r_pr = paragraph_first_r_pr
        pending_break = paragraph_index > 0
        bullet = _dml_paragraph_bullet(tx_body, paragraph, paragraph_index + 1)
        if bullet is not None:
            runs.append(
                _dml_text_run_from_properties(
                    element,
                    f"{bullet} ",
                    pending_break,
                    paragraph_first_r_pr,
                    def_r_pr,
                    end_para_r_pr,
                    shape_paint,
                )
            )
            pending_break = False
        for node in paragraph:
            if node.tag == qn(NS_A, "br"):
                pending_break = True
                continue
            if node.tag == qn(NS_A, "tab"):
                runs.append(
                    _dml_text_run_from_properties(
                        element,
                        "\t",
                        pending_break,
                        previous_r_pr,
                        def_r_pr,
                        end_para_r_pr,
                        shape_paint,
                    )
                )
                pending_break = False
                continue
            if _local_name(node.tag) not in {"r", "fld"}:
                continue
            text_node = node.find(qn(NS_A, "t"))
            if text_node is None:
                continue
            text = text_node.text or ""
            if not text:
                continue
            r_pr = node.find(qn(NS_A, "rPr"))
            runs.append(
                _dml_text_run_from_properties(
                    element,
                    text,
                    pending_break,
                    r_pr,
                    def_r_pr,
                    end_para_r_pr,
                    shape_paint,
                )
            )
            previous_r_pr = r_pr
            pending_break = False
    if len(runs) <= 1 or len({_text_run_style_key(run) for run in runs}) <= 1:
        return ()
    return tuple(runs)


def _dml_first_paragraph_run_properties(paragraph: ET.Element) -> ET.Element | None:
    for node in paragraph:
        if _local_name(node.tag) in {"r", "fld"}:
            r_pr = node.find(qn(NS_A, "rPr"))
            if r_pr is not None:
                return r_pr
    return None


def _dml_text_run_from_properties(
    element: ET.Element,
    text: str,
    break_before: bool,
    r_pr: ET.Element | None,
    def_r_pr: ET.Element | None,
    end_para_r_pr: ET.Element | None,
    shape_paint: Paint,
) -> TextRun:
    candidates = (r_pr, def_r_pr, end_para_r_pr)
    ln = _dml_text_line_properties(r_pr, def_r_pr, end_para_r_pr)
    fill, fill_alpha = _dml_text_fill(element, r_pr, def_r_pr, end_para_r_pr, shape_paint)
    return TextRun(
        text=text,
        paint=Paint(
            fill=fill,
            stroke=_dml_line_color(ln) if ln is not None else shape_paint.stroke,
            stroke_width=_dml_line_width(ln) if ln is not None else shape_paint.stroke_width,
            fill_alpha=fill_alpha,
            stroke_alpha=_dml_line_alpha(ln) if ln is not None else shape_paint.stroke_alpha,
            stroke_linecap=_dml_linecap(ln.get("cap")) if ln is not None else shape_paint.stroke_linecap,
            stroke_linejoin=_dml_linejoin(ln) if ln is not None else shape_paint.stroke_linejoin,
            stroke_dasharray=_dml_dasharray(ln) if ln is not None else shape_paint.stroke_dasharray,
            stroke_miterlimit=_dml_miterlimit(ln) if ln is not None else shape_paint.stroke_miterlimit,
        ),
        break_before=break_before,
        font_size=_dml_font_size_from_properties(candidates),
        font_weight=_dml_font_weight_from_properties(candidates),
        font_style=_dml_font_style_from_properties(candidates),
        font_family=_dml_font_family_from_properties(candidates),
        font_variant=_dml_font_variant_from_properties(candidates),
        text_decoration=_dml_text_decoration_from_properties(candidates),
        text_decoration_style=_dml_text_decoration_style_from_properties(candidates),
        text_decoration_color=_dml_text_decoration_color_from_properties(candidates),
        text_decoration_alpha=_dml_text_decoration_alpha_from_properties(candidates),
        text_decoration_thickness=_dml_text_decoration_thickness_from_properties(candidates),
        text_baseline_shift=_dml_text_baseline_shift_from_properties(candidates),
        letter_spacing=_dml_letter_spacing_from_properties(candidates),
    )


def _dml_paragraph_default_run_properties(tx_body: ET.Element, p_pr: ET.Element | None) -> ET.Element | None:
    def_r_pr = p_pr.find(qn(NS_A, "defRPr")) if p_pr is not None else None
    if def_r_pr is not None:
        return def_r_pr
    list_p_pr = _dml_list_style_paragraph_properties(tx_body, p_pr)
    return list_p_pr.find(qn(NS_A, "defRPr")) if list_p_pr is not None else None


def _text_run_style_key(run: TextRun) -> tuple[object, ...]:
    paint = run.paint
    return (
        paint.fill,
        paint.stroke,
        paint.stroke_width,
        paint.fill_alpha,
        paint.stroke_alpha,
        paint.stroke_linecap,
        paint.stroke_linejoin,
        paint.stroke_dasharray,
        paint.stroke_miterlimit,
        paint.stroke_compound,
        run.font_size,
        run.font_weight,
        run.font_style,
        run.font_family,
        run.font_variant,
        run.text_decoration,
        run.text_baseline_shift,
        run.letter_spacing,
    )


def _dml_paragraph_bullet(tx_body: ET.Element, paragraph: ET.Element, number: int) -> str | None:
    p_pr = paragraph.find(qn(NS_A, "pPr"))
    if p_pr is not None and p_pr.find(qn(NS_A, "buNone")) is not None:
        return None
    bullet = p_pr.find(qn(NS_A, "buChar")) if p_pr is not None else None
    if bullet is not None and bullet.get("char"):
        return bullet.get("char")
    auto_number = p_pr.find(qn(NS_A, "buAutoNum")) if p_pr is not None else None
    if auto_number is None:
        list_p_pr = _dml_list_style_paragraph_properties(tx_body, p_pr)
        if list_p_pr is not None and list_p_pr.find(qn(NS_A, "buNone")) is not None:
            return None
        bullet = list_p_pr.find(qn(NS_A, "buChar")) if list_p_pr is not None else None
        if bullet is not None and bullet.get("char"):
            return bullet.get("char")
        auto_number = list_p_pr.find(qn(NS_A, "buAutoNum")) if list_p_pr is not None else None
    return _dml_auto_number_bullet(auto_number, number)


def _dml_auto_number_bullet(element: ET.Element | None, number: int) -> str | None:
    if element is None:
        return None
    start = _dml_int(element.get("startAt"), 1) or 1
    value = start + number - 1
    lower_alpha = _alpha_number(value)
    upper_alpha = lower_alpha.upper()
    lower_roman = _roman_number(value)
    upper_roman = lower_roman.upper()
    return {
        "arabicPeriod": f"{value}.",
        "arabicParenR": f"{value})",
        "arabicParenBoth": f"({value})",
        "arabicPlain": str(value),
        "alphaLcPeriod": f"{lower_alpha}.",
        "alphaUcPeriod": f"{upper_alpha}.",
        "alphaLcParenR": f"{lower_alpha})",
        "alphaUcParenR": f"{upper_alpha})",
        "alphaLcParenBoth": f"({lower_alpha})",
        "alphaUcParenBoth": f"({upper_alpha})",
        "romanLcPeriod": f"{lower_roman}.",
        "romanUcPeriod": f"{upper_roman}.",
        "romanLcParenR": f"{lower_roman})",
        "romanUcParenR": f"{upper_roman})",
        "romanLcParenBoth": f"({lower_roman})",
        "romanUcParenBoth": f"({upper_roman})",
    }.get(element.get("type", ""), f"{value}.")


def _alpha_number(value: int) -> str:
    if value <= 0:
        return str(value)
    letters = []
    while value > 0:
        value -= 1
        letters.append(chr(ord("a") + value % 26))
        value //= 26
    return "".join(reversed(letters))


def _roman_number(value: int) -> str:
    if value <= 0 or value > 3999:
        return str(value)
    numerals = (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    )
    parts = []
    for amount, numeral in numerals:
        count, value = divmod(value, amount)
        parts.append(numeral * count)
    return "".join(parts)


def _dml_text_run_properties(element: ET.Element) -> ET.Element | None:
    return element.find(f".//{qn(NS_A, 'rPr')}")


def _dml_default_text_run_properties(element: ET.Element) -> ET.Element | None:
    return element.find(f".//{qn(NS_A, 'defRPr')}")


def _dml_end_paragraph_text_run_properties(element: ET.Element) -> ET.Element | None:
    return element.find(f".//{qn(NS_A, 'endParaRPr')}")


def _dml_text_property(
    element: ET.Element,
    predicate: Callable[[ET.Element], bool],
) -> ET.Element | None:
    r_pr = _dml_text_run_properties(element)
    if r_pr is not None and predicate(r_pr):
        return r_pr
    def_r_pr = _dml_default_text_run_properties(element)
    if def_r_pr is not None and predicate(def_r_pr):
        return def_r_pr
    end_para_r_pr = _dml_end_paragraph_text_run_properties(element)
    if end_para_r_pr is not None and predicate(end_para_r_pr):
        return end_para_r_pr
    return None


def _dml_text_property_from_candidates(
    candidates: Iterable[ET.Element | None],
    predicate: Callable[[ET.Element], bool],
) -> ET.Element | None:
    for candidate in candidates:
        if candidate is not None and predicate(candidate):
            return candidate
    return None


def _dml_font_weight(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("b") is not None)
    return _dml_font_weight_value(r_pr)


def _dml_font_weight_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("b") is not None)
    return _dml_font_weight_value(r_pr)


def _dml_font_weight_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is not None and r_pr.get("b") in {"1", "true"}:
        return "bold"
    return None


def _dml_font_size(element: ET.Element) -> float | None:
    r_pr = _dml_text_property(element, lambda item: item.get("sz") is not None)
    return _dml_font_size_value(r_pr)


def _dml_font_size_from_properties(candidates: Iterable[ET.Element | None]) -> float | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("sz") is not None)
    return _dml_font_size_value(r_pr)


def _dml_font_size_value(r_pr: ET.Element | None) -> float | None:
    if r_pr is not None and r_pr.get("sz"):
        try:
            return int(r_pr.get("sz", "0")) / 100
        except ValueError:
            return None
    return None


def _dml_font_style(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("i") is not None)
    return _dml_font_style_value(r_pr)


def _dml_font_style_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("i") is not None)
    return _dml_font_style_value(r_pr)


def _dml_font_style_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is not None and r_pr.get("i") in {"1", "true"}:
        return "italic"
    return None


def _dml_font_family(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, _dml_has_typeface)
    return _dml_font_family_value(r_pr)


def _dml_font_family_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, _dml_has_typeface)
    return _dml_font_family_value(r_pr)


def _dml_font_family_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is not None:
        return _dml_typeface(r_pr)
    return None


def _dml_has_typeface(element: ET.Element) -> bool:
    return _dml_typeface(element) is not None


def _dml_typeface(element: ET.Element) -> str | None:
    for tag in ("latin", "ea", "cs", "sym"):
        font = element.find(qn(NS_A, tag))
        if font is not None and font.get("typeface"):
            return font.get("typeface")
    return None


def _dml_font_variant(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("cap") is not None)
    return _dml_font_variant_value(r_pr)


def _dml_font_variant_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("cap") is not None)
    return _dml_font_variant_value(r_pr)


def _dml_font_variant_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is not None:
        if r_pr.get("cap") == "small":
            return "small-caps"
        if r_pr.get("cap") == "all":
            return "all-small-caps"
    return None


def _dml_text_baseline_shift(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("baseline") is not None)
    return _dml_text_baseline_shift_value(r_pr)


def _dml_text_baseline_shift_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("baseline") is not None)
    return _dml_text_baseline_shift_value(r_pr)


def _dml_text_baseline_shift_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is None or r_pr.get("baseline") is None:
        return None
    try:
        baseline = int(r_pr.get("baseline", "0"))
    except ValueError:
        return None
    if baseline >= 30000:
        return "super"
    if baseline <= -25000:
        return "sub"
    return None


def _dml_letter_spacing(element: ET.Element) -> float | None:
    r_pr = _dml_text_property(element, lambda item: item.get("spc") is not None)
    return _dml_letter_spacing_value(r_pr)


def _dml_letter_spacing_from_properties(candidates: Iterable[ET.Element | None]) -> float | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("spc") is not None)
    return _dml_letter_spacing_value(r_pr)


def _dml_letter_spacing_value(r_pr: ET.Element | None) -> float | None:
    if r_pr is None or r_pr.get("spc") is None:
        return None
    try:
        return int(r_pr.get("spc", "0")) / 100 / 0.75
    except ValueError:
        return None


def _dml_text_decoration(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("u") is not None or item.get("strike") is not None)
    return _dml_text_decoration_value(r_pr)


def _dml_text_decoration_style(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.get("u") is not None)
    return _dml_text_decoration_style_value(r_pr)


def _dml_text_decoration_color(element: ET.Element) -> str | None:
    r_pr = _dml_text_property(element, lambda item: item.find(qn(NS_A, "uFill")) is not None)
    return _dml_text_decoration_color_value(r_pr)


def _dml_text_decoration_alpha(element: ET.Element) -> float | None:
    r_pr = _dml_text_property(element, lambda item: item.find(qn(NS_A, "uFill")) is not None)
    return _dml_text_decoration_alpha_value(r_pr)


def _dml_text_decoration_thickness(element: ET.Element) -> float | None:
    r_pr = _dml_text_property(element, lambda item: item.find(qn(NS_A, "uLn")) is not None)
    return _dml_text_decoration_thickness_value(r_pr)


def _dml_text_decoration_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(
        candidates,
        lambda item: item.get("u") is not None or item.get("strike") is not None,
    )
    return _dml_text_decoration_value(r_pr)


def _dml_text_decoration_style_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.get("u") is not None)
    return _dml_text_decoration_style_value(r_pr)


def _dml_text_decoration_color_from_properties(candidates: Iterable[ET.Element | None]) -> str | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.find(qn(NS_A, "uFill")) is not None)
    return _dml_text_decoration_color_value(r_pr)


def _dml_text_decoration_alpha_from_properties(candidates: Iterable[ET.Element | None]) -> float | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.find(qn(NS_A, "uFill")) is not None)
    return _dml_text_decoration_alpha_value(r_pr)


def _dml_text_decoration_thickness_from_properties(candidates: Iterable[ET.Element | None]) -> float | None:
    r_pr = _dml_text_property_from_candidates(candidates, lambda item: item.find(qn(NS_A, "uLn")) is not None)
    return _dml_text_decoration_thickness_value(r_pr)


def _dml_text_decoration_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is None:
        return None
    values = []
    if r_pr.get("u") and r_pr.get("u") != "none":
        values.append("underline")
    if r_pr.get("strike") and r_pr.get("strike") != "noStrike":
        values.append("line-through")
    return " ".join(values) or None


def _dml_text_decoration_style_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is None:
        return None
    return {
        "dash": "dashed",
        "dashHeavy": "dashed",
        "dbl": "double",
        "dotted": "dotted",
        "dottedHeavy": "dotted",
        "wavy": "wavy",
        "wavyDbl": "wavy",
        "wavyHeavy": "wavy",
    }.get(r_pr.get("u", ""))


def _dml_text_decoration_color_value(r_pr: ET.Element | None) -> str | None:
    if r_pr is None:
        return None
    u_fill = r_pr.find(qn(NS_A, "uFill"))
    if u_fill is None:
        return None
    solid_fill = u_fill.find(qn(NS_A, "solidFill"))
    return _dml_color(solid_fill) if solid_fill is not None else None


def _dml_text_decoration_alpha_value(r_pr: ET.Element | None) -> float | None:
    if r_pr is None:
        return None
    u_fill = r_pr.find(qn(NS_A, "uFill"))
    if u_fill is None:
        return None
    solid_fill = u_fill.find(qn(NS_A, "solidFill"))
    return _dml_alpha(solid_fill) if solid_fill is not None else None


def _dml_text_decoration_thickness_value(r_pr: ET.Element | None) -> float | None:
    if r_pr is None:
        return None
    return _dml_line_width(r_pr.find(qn(NS_A, "uLn")))


def _dml_text_anchor(element: ET.Element) -> str | None:
    p_pr = _dml_paragraph_properties(element, lambda item: item.get("algn") is not None)
    if p_pr is None:
        return None
    return {"ctr": "middle", "r": "end", "l": "start"}.get(p_pr.get("algn", ""))


def _dml_paragraph_properties(
    element: ET.Element,
    predicate: Callable[[ET.Element], bool],
) -> ET.Element | None:
    tx_body = element.find(qn(NS_P, "txBody"))
    p_pr = tx_body.find(f"{qn(NS_A, 'p')}/{qn(NS_A, 'pPr')}") if tx_body is not None else None
    if p_pr is None:
        p_pr = element.find(f".//{qn(NS_A, 'pPr')}")
    if p_pr is not None and predicate(p_pr):
        return p_pr
    if tx_body is not None:
        list_p_pr = _dml_list_style_paragraph_properties(tx_body, p_pr)
        if list_p_pr is not None and predicate(list_p_pr):
            return list_p_pr
    return None


def _dml_list_style_paragraph_properties(tx_body: ET.Element, p_pr: ET.Element | None) -> ET.Element | None:
    level = _dml_paragraph_level(p_pr)
    return tx_body.find(f"{qn(NS_A, 'lstStyle')}/{qn(NS_A, f'lvl{level + 1}pPr')}")


def _dml_paragraph_level(p_pr: ET.Element | None) -> int:
    if p_pr is None or p_pr.get("lvl") is None:
        return 0
    level = _dml_int(p_pr.get("lvl"), 0) or 0
    return max(0, min(level, 8))


def _text_anchor_to_dml(value: str | None) -> str | None:
    return {"middle": "ctr", "end": "r", "start": "l"}.get(value or "")


def _paragraph_attrs(text_anchor: str | None, text_direction: str | None) -> dict[str, str]:
    attrs = {}
    paragraph_align = _text_anchor_to_dml(text_anchor)
    if paragraph_align:
        attrs["algn"] = paragraph_align
    if text_direction == "rtl":
        attrs["rtl"] = "1"
    return attrs


def _text_anchor(value: str | None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    return normalized if normalized in {"middle", "end", "start"} else None


def _text_direction(value: str | None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    return normalized if normalized == "rtl" else None


def _dml_text_direction(element: ET.Element) -> str | None:
    p_pr = _dml_paragraph_properties(element, lambda item: item.get("rtl") is not None)
    if p_pr is None:
        return None
    return "rtl" if p_pr.get("rtl") in {"1", "true"} else None


def _dml_text_baseline(element: ET.Element) -> str | None:
    body_pr = element.find(f".//{qn(NS_A, 'bodyPr')}")
    if body_pr is None:
        return None
    return {"ctr": "middle", "b": "text-after-edge", "t": "text-before-edge"}.get(body_pr.get("anchor", ""))


def _text_baseline_to_dml(value: str | None) -> str | None:
    return {"middle": "ctr", "central": "ctr", "text-after-edge": "b", "text-before-edge": "t", "hanging": "t"}.get(value or "")


def _dominant_baseline(value: str | None) -> str | None:
    value = value.strip().lower() if value is not None else None
    if value in {"middle", "central"}:
        return "middle"
    if value in {"text-after-edge", "ideographic"}:
        return "text-after-edge"
    if value in {"text-before-edge", "hanging"}:
        return "text-before-edge"
    return None


def _svg_text_content(
    element: ET.Element,
    style: dict[str, str] | None = None,
    css: list[CssRule] | None = None,
    ancestors: tuple[ET.Element, ...] = (),
) -> str:
    style = style or {}
    css = css or []
    preserve_space = _xml_space_preserve(element)
    if not any(_local_name(child.tag) == "tspan" for child in element):
        text = "".join(element.itertext())
        text = text if preserve_space else text.strip()
        return _apply_text_transform(text, style.get("text-transform"))
    lines = []
    leading = element.text or ""
    if not preserve_space:
        leading = leading.strip()
    if leading:
        lines.append(_apply_text_transform(leading, style.get("text-transform")))
    previous_children: list[ET.Element] = []
    for child in element:
        if _local_name(child.tag) == "tspan":
            child_preserve_space = preserve_space or _xml_space_preserve(child)
            child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children)) if css else _presentation_style(child, style)
            text = "".join(child.itertext())
            if not child_preserve_space:
                text = text.strip()
            if text:
                lines.append(_apply_text_transform(text, child_style.get("text-transform")))
        previous_children.append(child)
    return "\n".join(lines)


def _svg_text_runs(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    refs: dict[str, ET.Element],
    ancestors: tuple[ET.Element, ...],
    matrix: tuple[float, float, float, float, float, float],
    viewport: tuple[float, float],
) -> tuple[TextRun, ...]:
    if not any(_local_name(child.tag) == "tspan" for child in element):
        return ()
    preserve_space = _xml_space_preserve(element)
    scale = _matrix_scale(matrix)
    runs: list[TextRun] = []
    leading = element.text or ""
    if not preserve_space:
        leading = leading.strip()
    if leading:
        runs.append(_svg_text_run(leading, style, refs, css, scale, viewport, False))
    previous_children: list[ET.Element] = []
    for child in element:
        if _local_name(child.tag) == "tspan":
            child_preserve_space = preserve_space or _xml_space_preserve(child)
            child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
            text = "".join(child.itertext())
            if not child_preserve_space:
                text = text.strip()
            if text:
                runs.append(_svg_text_run(text, child_style, refs, css, scale, viewport, bool(runs)))
        previous_children.append(child)
    return tuple(runs)


def _svg_text_run(
    text: str,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    css: list[CssRule],
    scale: float,
    viewport: tuple[float, float],
    break_before: bool,
) -> TextRun:
    font_size = _svg_font_size(style.get("font-size")) * scale
    text = _apply_text_transform(text, style.get("text-transform"))
    decoration_color, decoration_alpha = _text_decoration_color(style)
    return TextRun(
        text=text,
        paint=_text_paint(style, refs, css, _stroke_transform_scale(style, (scale, 0, 0, scale, 0, 0)), viewport),
        break_before=break_before,
        font_size=font_size,
        font_weight=style.get("font-weight"),
        font_style=style.get("font-style"),
        font_family=_font_family(style.get("font-family")),
        font_variant=_font_variant(style.get("font-variant")),
        text_decoration=style.get("text-decoration"),
        text_decoration_style=_text_decoration_style(style.get("text-decoration-style"), style.get("text-decoration")),
        text_decoration_color=decoration_color,
        text_decoration_alpha=decoration_alpha,
        text_decoration_thickness=_text_decoration_thickness(style, viewport),
        text_baseline_shift=_baseline_shift(style.get("baseline-shift")),
        letter_spacing=_svg_text_effective_letter_spacing(style, text, font_size, viewport),
    )


def _svg_font_size(value: str | None) -> float:
    if value is None:
        return 16.0
    keyword_sizes = {
        "xx-small": 9.0,
        "x-small": 10.0,
        "small": 13.0,
        "medium": 16.0,
        "large": 18.0,
        "x-large": 24.0,
        "xx-large": 32.0,
    }
    normalized = value.strip().lower()
    if normalized in keyword_sizes:
        return keyword_sizes[normalized]
    return _num(value, 16)


def _presentation_style(element: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    style = dict(inherited)
    value = element.get("text-transform")
    if value is not None:
        style["text-transform"] = value
    for key, (value, _) in _parse_style_declarations(element.get("style", "")).items():
        if key == "text-transform":
            style[key] = value
    return style


def _apply_text_transform(text: str, value: str | None) -> str:
    if value is None:
        return text
    normalized = value.strip().lower()
    if normalized == "uppercase":
        return text.upper()
    if normalized == "lowercase":
        return text.lower()
    if normalized == "capitalize":
        return re.sub(r"(^|[\s\-_])(\S)", lambda match: match.group(1) + match.group(2).upper(), text)
    return text


def _xml_space_preserve(element: ET.Element) -> bool:
    return element.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve" or element.get("xml:space") == "preserve"


def _svg_text_position(element: ET.Element, viewport: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    x = _optional_length(element.get("x"), "x", viewport)
    y = _optional_length(element.get("y"), "y", viewport)
    dx = _first_optional_length(element.get("dx"), "x", viewport)
    dy = _first_optional_length(element.get("dy"), "y", viewport)
    if x is not None and y is not None:
        return x + (dx or 0.0), y + (dy or 0.0)
    for child in element:
        if _local_name(child.tag) != "tspan":
            continue
        if x is None:
            x = _optional_length(child.get("x"), "x", viewport)
        if y is None:
            y = _optional_length(child.get("y"), "y", viewport)
        if dx is None:
            dx = _first_optional_length(child.get("dx"), "x", viewport)
        if dy is None:
            dy = _first_optional_length(child.get("dy"), "y", viewport)
        if x is not None and y is not None:
            break
    return (x or 0.0) + (dx or 0.0), (y or 0.0) + (dy or 0.0)


def _svg_text_anchor(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    ancestors: tuple[ET.Element, ...],
) -> str | None:
    anchor = _text_anchor(style.get("text-anchor"))
    if anchor is not None:
        return anchor
    if element.get("x") is not None or element.get("y") is not None:
        return None
    if (element.text or "").strip():
        return None
    previous_children: list[ET.Element] = []
    for child in element:
        if _local_name(child.tag) != "tspan":
            previous_children.append(child)
            continue
        if not "".join(child.itertext()).strip():
            previous_children.append(child)
            continue
        if child.get("x") is None or child.get("y") is None:
            return None
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        return _text_anchor(child_style.get("text-anchor"))
    return None


def _svg_text_baseline(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    ancestors: tuple[ET.Element, ...],
) -> str | None:
    baseline = _dominant_baseline(style.get("dominant-baseline")) or _dominant_baseline(
        style.get("alignment-baseline")
    )
    if baseline is not None:
        return baseline
    if element.get("x") is not None or element.get("y") is not None:
        return None
    if (element.text or "").strip():
        return None
    previous_children: list[ET.Element] = []
    for child in element:
        if _local_name(child.tag) != "tspan":
            previous_children.append(child)
            continue
        if not "".join(child.itertext()).strip():
            previous_children.append(child)
            continue
        if child.get("x") is None or child.get("y") is None:
            return None
        child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
        return _dominant_baseline(child_style.get("dominant-baseline")) or _dominant_baseline(
            child_style.get("alignment-baseline")
        )
    return None


def _first_optional_length(value: str | None, axis: str, viewport: tuple[float, float]) -> float | None:
    if value is None:
        return None
    first = re.split(r"[\s,]+", value.strip(), maxsplit=1)[0]
    return _optional_length(first or None, axis, viewport)


def _svg_text_rotation(
    element: ET.Element,
    style: dict[str, str],
    css: list[CssRule],
    ancestors: tuple[ET.Element, ...],
) -> float | None:
    rotation = _single_svg_rotation(style.get("rotate"), _svg_text_content(element))
    if rotation is not None:
        return rotation
    previous_children: list[ET.Element] = []
    for child in element:
        if _local_name(child.tag) == "tspan":
            child_style = _computed_style(child, css, style, ancestors + (element,), tuple(previous_children))
            rotation = _single_svg_rotation(child_style.get("rotate"), "".join(child.itertext()))
            if rotation is not None:
                return rotation
        previous_children.append(child)
    return None


def _single_svg_rotation(value: str | None, text: str | None = None) -> float | None:
    if value is None:
        return None
    numbers = _svg_rotation_values(value)
    if not numbers:
        return None
    if any(number != numbers[0] for number in numbers) and (text is None or len(text) > 1):
        return None
    return numbers[0]


def _svg_rotation_values(value: str) -> list[float] | None:
    parts = [part for part in re.split(r"[\s,]+", value.strip()) if part]
    if not parts:
        return None
    numbers = []
    for part in parts:
        angle = _transform_angle_arg(part)
        if angle is None:
            return None
        numbers.append(angle)
    return numbers


def _svg_letter_spacing(style: dict[str, str], viewport: tuple[float, float]) -> float | None:
    value = style.get("letter-spacing")
    if value is None or value.strip().lower() == "normal":
        return None
    return _optional_length(value, "x", viewport)


def _svg_text_effective_letter_spacing(
    style: dict[str, str],
    text: str,
    font_size: float,
    viewport: tuple[float, float],
) -> float | None:
    letter_spacing = _svg_letter_spacing(style, viewport)
    if letter_spacing is not None:
        return letter_spacing
    text_length_spacing = _svg_text_length_letter_spacing(style, text, font_size, viewport)
    if text_length_spacing is not None:
        return text_length_spacing
    return _svg_word_spacing_letter_spacing(style, text, viewport)


def _svg_text_length(style: dict[str, str], text: str, viewport: tuple[float, float]) -> float | None:
    if not _svg_text_length_spacing_is_supported(style, text, viewport):
        return None
    return _optional_length(style.get("textLength"), "x", viewport)


def _svg_text_length_letter_spacing(
    style: dict[str, str],
    text: str,
    font_size: float,
    viewport: tuple[float, float],
) -> float | None:
    text_length = _svg_text_length(style, text, viewport)
    if text_length is None:
        return None
    line = text.strip()
    natural_width = font_size * len(line) * 0.9
    return (text_length - natural_width) / (len(line) - 1)


def _svg_text_length_spacing_is_supported(style: dict[str, str], text: str, viewport: tuple[float, float]) -> bool:
    text_length = style.get("textLength")
    if text_length is None or "%" in text_length:
        return False
    if not _svg_spacing_is_unspecified_or_normal(style.get("letter-spacing")):
        return False
    if (style.get("lengthAdjust") or "spacing").strip().lower() not in {"spacing", "spacingandglyphs"}:
        return False
    line = text.strip()
    return "\n" not in text and len(line) > 1 and _optional_length(style.get("textLength"), "x", viewport) is not None


def _svg_word_spacing_extra(style: dict[str, str], text: str, viewport: tuple[float, float]) -> float:
    word_spacing = _svg_word_spacing(style, text, viewport)
    return word_spacing * _svg_word_gap_count(text) if word_spacing is not None else 0.0


def _svg_word_spacing_letter_spacing(
    style: dict[str, str],
    text: str,
    viewport: tuple[float, float],
) -> float | None:
    if not _svg_word_spacing_is_supported(style, text, viewport):
        return None
    return _svg_word_spacing_extra(style, text, viewport) / (len(text.strip()) - 1)


def _svg_word_spacing(style: dict[str, str], text: str, viewport: tuple[float, float]) -> float | None:
    if not _svg_word_spacing_is_supported(style, text, viewport):
        return None
    return _optional_length(style.get("word-spacing"), "x", viewport)


def _svg_word_spacing_is_supported(style: dict[str, str], text: str, viewport: tuple[float, float]) -> bool:
    value = style.get("word-spacing")
    if value is None:
        return False
    if value.strip().lower() == "normal":
        return False
    if not _svg_spacing_is_unspecified_or_normal(style.get("letter-spacing")):
        return False
    if style.get("textLength") is not None:
        return False
    line = text.strip()
    return (
        "\n" not in text
        and len(line) > 1
        and _svg_word_gap_count(line) > 0
        and _optional_length(value, "x", viewport) is not None
    )


def _svg_spacing_is_unspecified_or_normal(value: str | None) -> bool:
    return value is None or value.strip().lower() in {"", "normal"}


def _svg_word_gap_count(text: str) -> int:
    return len(re.findall(r"[ \t\f\v]+", text.strip()))


def _font_variant(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"small-caps", "all-small-caps"}:
        return normalized
    return None


def _baseline_shift(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"super", "sub"}:
        return normalized
    return None


def _is_bold(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized == "bold":
        return True
    try:
        return int(normalized) >= 600
    except ValueError:
        return False


def _is_italic(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized == "italic" or normalized.startswith("oblique")


def _has_text_decoration(value: str | None, decoration: str) -> bool:
    if value is None:
        return False
    return decoration in _text_decoration_line_tokens(value)


def _text_decoration_style(value: str | None, text_decoration: str | None = None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    if not normalized and text_decoration is not None:
        normalized = _text_decoration_style_token(text_decoration) or ""
    return normalized if normalized in {"dashed", "dotted", "double", "solid", "wavy"} else None


def _text_decoration_color(style: dict[str, str]) -> tuple[str | None, float | None]:
    if not _has_text_decoration(style.get("text-decoration"), "underline"):
        return None, None
    value = style.get("text-decoration-color")
    if value is None:
        value = _text_decoration_color_token(style.get("text-decoration"))
    if value is None:
        return None, None
    if value.strip().lower() == "currentcolor":
        value = style.get("color", "#000000")
    return _parse_color(value)


def _text_decoration_thickness(style: dict[str, str], viewport: tuple[float, float]) -> float | None:
    if not _has_text_decoration(style.get("text-decoration"), "underline"):
        return None
    if _has_text_decoration(style.get("text-decoration"), "line-through"):
        return None
    value = style.get("text-decoration-thickness")
    if value is None:
        value = _text_decoration_thickness_token(style.get("text-decoration"))
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "auto", "from-font"}:
        return None
    thickness = _length(normalized, math.nan, "diag", viewport)
    return max(0.0, thickness) if math.isfinite(thickness) else None


def _text_decoration_line_tokens(value: str) -> set[str]:
    return {part.lower() for part in re.split(r"\s+", value.strip()) if part.lower() in TEXT_DECORATION_LINE_TOKENS}


def _text_decoration_style_token(value: str) -> str | None:
    for part in _css_value_tokens(value):
        normalized = part.lower()
        if normalized in TEXT_DECORATION_STYLE_TOKENS:
            return normalized
    return None


def _text_decoration_color_token(value: str | None) -> str | None:
    if value is None:
        return None
    for part in _css_value_tokens(value):
        normalized = part.lower()
        if (
            normalized in TEXT_DECORATION_LINE_TOKENS
            or normalized in TEXT_DECORATION_STYLE_TOKENS
            or normalized in {"auto", "from-font"}
            or _html_first_length(normalized) is not None
        ):
            continue
        if normalized == "currentcolor":
            return part
        color, _ = _parse_color(part)
        if color is not None:
            return part
    return None


def _text_decoration_thickness_token(value: str | None) -> str | None:
    if value is None:
        return None
    for part in _css_value_tokens(value):
        normalized = part.lower()
        if normalized in {"auto", "from-font"}:
            return part
        if (
            normalized in TEXT_DECORATION_LINE_TOKENS
            or normalized in TEXT_DECORATION_STYLE_TOKENS
            or normalized == "currentcolor"
            or _parse_color(part)[0] is not None
        ):
            continue
        if _html_first_length(normalized) is not None:
            return part
    return None


def _dml_underline_value(text_decoration: str | None, text_decoration_style: str | None = None) -> str | None:
    if not _has_text_decoration(text_decoration, "underline"):
        return None
    return {
        "dashed": "dash",
        "dotted": "dotted",
        "double": "dbl",
        "wavy": "wavy",
    }.get(text_decoration_style or "", "sng")


def _dml_custom_points(cust: ET.Element, x: float, y: float) -> tuple[list[tuple[float, float]], bool]:
    points: list[tuple[float, float]] = []
    closed = False
    path_lst = cust.find(qn(NS_A, "pathLst"))
    if path_lst is None:
        return points, closed
    for child in path_lst.iter():
        tag = _local_name(child.tag)
        if tag in {"moveTo", "lnTo"}:
            pt = child.find(qn(NS_A, "pt"))
            point = _dml_path_point(pt, x, y) if pt is not None else None
            if point is not None:
                points.append(point)
        elif tag == "quadBezTo" and points:
            bezier_points = _dml_path_points(child, x, y)
            if len(bezier_points) >= 2:
                points.extend(_quadratic_points(points[-1], bezier_points[0], bezier_points[1]))
        elif tag == "cubicBezTo" and points:
            bezier_points = _dml_path_points(child, x, y)
            if len(bezier_points) >= 3:
                points.extend(_cubic_points(points[-1], bezier_points[0], bezier_points[1], bezier_points[2]))
        elif tag == "close":
            closed = True
    return points, closed


def _dml_path_points(element: ET.Element, x: float, y: float) -> list[tuple[float, float]]:
    points = []
    for pt in element.findall(qn(NS_A, "pt")):
        point = _dml_path_point(pt, x, y)
        if point is not None:
            points.append(point)
    return points


def _dml_path_point(pt: ET.Element, x: float, y: float) -> tuple[float, float] | None:
    point_x = _dml_int(pt.get("x"))
    point_y = _dml_int(pt.get("y"))
    if point_x is None or point_y is None:
        return None
    return x + _px(point_x), y + _px(point_y)


def _transformed_rect_shape(
    x: float,
    y: float,
    width: float,
    height: float,
    rx: float,
    ry: float,
    matrix: tuple[float, float, float, float, float, float],
    paint: Paint,
) -> Shape | None:
    points = _transform_points(_rect_points(x, y, width, height), matrix)
    p0, p1, _, p3 = points
    ux = (p1[0] - p0[0], p1[1] - p0[1])
    vy = (p3[0] - p0[0], p3[1] - p0[1])
    transformed_width = math.hypot(*ux)
    transformed_height = math.hypot(*vy)
    dot = ux[0] * vy[0] + ux[1] * vy[1]
    determinant = ux[0] * vy[1] - ux[1] * vy[0]
    tolerance = max(transformed_width * transformed_height, 1.0) * 1e-9
    if transformed_width <= 0 or transformed_height <= 0 or abs(dot) > tolerance or abs(determinant) <= tolerance:
        return None
    sx = transformed_width / width
    sy = transformed_height / height
    transformed_rx = min(rx * sx, transformed_width / 2) if rx else None
    transformed_ry = min(ry * sy, transformed_height / 2) if ry else None
    center_x = sum(px for px, _ in points) / 4
    center_y = sum(py for _, py in points) / 4
    rotation = math.degrees(math.atan2(ux[1], ux[0])) % 360
    if abs(rotation) < 1e-9 or abs(rotation - 360) < 1e-9:
        rotation = 0.0
    return Shape(
        "roundRect" if transformed_rx or transformed_ry else "rect",
        center_x - transformed_width / 2,
        center_y - transformed_height / 2,
        transformed_width,
        transformed_height,
        paint,
        rx=transformed_rx,
        ry=transformed_ry,
        rotation=rotation or None,
    )


def _transformed_ellipse_shape(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    matrix: tuple[float, float, float, float, float, float],
    paint: Paint,
) -> Shape | None:
    left = _apply_matrix(matrix, (cx - rx, cy))
    right = _apply_matrix(matrix, (cx + rx, cy))
    top = _apply_matrix(matrix, (cx, cy - ry))
    bottom = _apply_matrix(matrix, (cx, cy + ry))
    center = _apply_matrix(matrix, (cx, cy))
    horizontal = (right[0] - left[0], right[1] - left[1])
    vertical = (bottom[0] - top[0], bottom[1] - top[1])
    transformed_width = math.hypot(*horizontal)
    transformed_height = math.hypot(*vertical)
    dot = horizontal[0] * vertical[0] + horizontal[1] * vertical[1]
    determinant = horizontal[0] * vertical[1] - horizontal[1] * vertical[0]
    tolerance = max(transformed_width * transformed_height, 1.0) * 1e-9
    if transformed_width <= 0 or transformed_height <= 0 or abs(dot) > tolerance or abs(determinant) <= tolerance:
        return None
    rotation = math.degrees(math.atan2(horizontal[1], horizontal[0])) % 360
    if abs(rotation) < 1e-9 or abs(rotation - 360) < 1e-9:
        rotation = 0.0
    return Shape(
        "ellipse",
        center[0] - transformed_width / 2,
        center[1] - transformed_height / 2,
        transformed_width,
        transformed_height,
        paint,
        rotation=rotation or None,
    )


def _svg_paint_attrs(paint: Paint) -> dict[str, str]:
    attrs: dict[str, str] = {}
    if paint.fill:
        attrs["fill"] = paint.fill
    if paint.stroke:
        attrs["stroke"] = paint.stroke
    if paint.stroke_width is not None:
        attrs["stroke-width"] = _fmt(paint.stroke_width)
    if paint.stroke_linecap:
        attrs["stroke-linecap"] = paint.stroke_linecap
    if paint.stroke_linejoin:
        attrs["stroke-linejoin"] = paint.stroke_linejoin
    if paint.stroke_dasharray:
        attrs["stroke-dasharray"] = paint.stroke_dasharray
    if paint.stroke_miterlimit is not None:
        attrs["stroke-miterlimit"] = _fmt(paint.stroke_miterlimit)
    if paint.marker_start:
        attrs["marker-start"] = f"url(#{paint.marker_start})"
    if paint.marker_end:
        attrs["marker-end"] = f"url(#{paint.marker_end})"
    if paint.fill_alpha is not None and paint.fill_alpha < 1:
        attrs["fill-opacity"] = _fmt(paint.fill_alpha)
    if paint.stroke_alpha is not None and paint.stroke_alpha < 1:
        attrs["stroke-opacity"] = _fmt(paint.stroke_alpha)
    return attrs


def _dml_xfrm(xfrm: ET.Element | None) -> tuple[float, float, float, float, bool, bool, float | None]:
    if xfrm is None:
        return 0.0, 0.0, 0.0, 0.0, False, False, None
    off = xfrm.find(qn(NS_A, "off"))
    ext = xfrm.find(qn(NS_A, "ext"))
    x = _px(_dml_int(off.get("x"), 0) or 0) if off is not None else 0.0
    y = _px(_dml_int(off.get("y"), 0) or 0) if off is not None else 0.0
    width = _px(_dml_int(ext.get("cx"), 0) or 0) if ext is not None else 0.0
    height = _px(_dml_int(ext.get("cy"), 0) or 0) if ext is not None else 0.0
    rotation_value = _dml_float(xfrm.get("rot")) if xfrm.get("rot") is not None else None
    rotation = rotation_value / 60000 if rotation_value is not None else None
    return x, y, width, height, xfrm.get("flipH") in {"1", "true"}, xfrm.get("flipV") in {"1", "true"}, rotation


def _dml_group_matrix(element: ET.Element) -> tuple[float, float, float, float, float, float]:
    grp_sp_pr = element.find(qn(NS_P, "grpSpPr"))
    if grp_sp_pr is None:
        grp_sp_pr = element.find(qn(NS_A, "grpSpPr"))
    xfrm = grp_sp_pr.find(qn(NS_A, "xfrm")) if grp_sp_pr is not None else None
    if xfrm is None:
        return _identity_matrix()
    off = xfrm.find(qn(NS_A, "off"))
    ext = xfrm.find(qn(NS_A, "ext"))
    ch_off = xfrm.find(qn(NS_A, "chOff"))
    ch_ext = xfrm.find(qn(NS_A, "chExt"))
    x = _px(_dml_int(off.get("x"), 0) or 0) if off is not None else 0.0
    y = _px(_dml_int(off.get("y"), 0) or 0) if off is not None else 0.0
    width = _px(_dml_int(ext.get("cx"), 0) or 0) if ext is not None else 0.0
    height = _px(_dml_int(ext.get("cy"), 0) or 0) if ext is not None else 0.0
    child_x = _px(_dml_int(ch_off.get("x"), 0) or 0) if ch_off is not None else 0.0
    child_y = _px(_dml_int(ch_off.get("y"), 0) or 0) if ch_off is not None else 0.0
    child_width = _px(_dml_int(ch_ext.get("cx"), 0) or 0) if ch_ext is not None else width
    child_height = _px(_dml_int(ch_ext.get("cy"), 0) or 0) if ch_ext is not None else height
    scale_x = width / child_width if child_width else 1.0
    scale_y = height / child_height if child_height else 1.0
    matrix = (scale_x, 0.0, 0.0, scale_y, x - child_x * scale_x, y - child_y * scale_y)
    if xfrm.get("flipH") in {"1", "true"}:
        matrix = _matrix_multiply((-1.0, 0.0, 0.0, 1.0, x * 2 + width, 0.0), matrix)
    if xfrm.get("flipV") in {"1", "true"}:
        matrix = _matrix_multiply((1.0, 0.0, 0.0, -1.0, 0.0, y * 2 + height), matrix)
    rotation_value = _dml_float(xfrm.get("rot")) if xfrm.get("rot") is not None else None
    if rotation_value:
        angle = math.radians(rotation_value / 60000)
        center_x = x + width / 2
        center_y = y + height / 2
        rotation = (math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle), 0.0, 0.0)
        matrix = _matrix_multiply(
            _matrix_multiply((1.0, 0.0, 0.0, 1.0, center_x, center_y), rotation),
            _matrix_multiply((1.0, 0.0, 0.0, 1.0, -center_x, -center_y), matrix),
        )
    return matrix


def _transform_dml_shape(shape: Shape, matrix: tuple[float, float, float, float, float, float]) -> Shape:
    if _is_identity_matrix(matrix):
        return shape
    if shape.kind == "line":
        return _transform_dml_line_shape(shape, matrix)
    if shape.kind == "freeform":
        return _transform_dml_freeform_shape(shape, matrix)
    return _transform_dml_box_shape(shape, matrix)


def _transform_dml_box_shape(shape: Shape, matrix: tuple[float, float, float, float, float, float]) -> Shape:
    points = _transform_points(_rect_points(shape.x, shape.y, shape.width, shape.height), matrix)
    p0, p1, _, p3 = points
    ux = (p1[0] - p0[0], p1[1] - p0[1])
    vy = (p3[0] - p0[0], p3[1] - p0[1])
    width = math.hypot(*ux)
    height = math.hypot(*vy)
    if width <= 0 or height <= 0:
        return shape
    center_x = sum(px for px, _ in points) / 4
    center_y = sum(py for _, py in points) / 4
    rotation = math.degrees(math.atan2(ux[1], ux[0])) % 360
    determinant = ux[0] * vy[1] - ux[1] * vy[0]
    if abs(rotation) < 1e-9 or abs(rotation - 360) < 1e-9:
        rotation = 0.0
    if shape.rotation is not None:
        rotation = (rotation + shape.rotation) % 360
        if abs(rotation) < 1e-9 or abs(rotation - 360) < 1e-9:
            rotation = 0.0
    scale = _matrix_scale(matrix)
    return replace(
        shape,
        x=center_x - width / 2,
        y=center_y - height / 2,
        width=width,
        height=height,
        paint=_scale_paint(shape.paint, scale),
        font_size=shape.font_size * scale if shape.font_size is not None else None,
        letter_spacing=shape.letter_spacing * scale if shape.letter_spacing is not None else None,
        rx=min(shape.rx * scale, width / 2) if shape.rx is not None else None,
        ry=min(shape.ry * scale, height / 2) if shape.ry is not None else None,
        flip_v=shape.flip_v ^ (determinant < 0),
        rotation=rotation or None,
    )


def _transform_dml_line_shape(shape: Shape, matrix: tuple[float, float, float, float, float, float]) -> Shape:
    points = _transform_points(
        [
            (shape.x + shape.width if shape.flip_h else shape.x, shape.y + shape.height if shape.flip_v else shape.y),
            (shape.x if shape.flip_h else shape.x + shape.width, shape.y if shape.flip_v else shape.y + shape.height),
        ],
        matrix,
    )
    (x1, y1), (x2, y2) = points
    return replace(
        shape,
        x=min(x1, x2),
        y=min(y1, y2),
        width=abs(x2 - x1),
        height=abs(y2 - y1),
        paint=_scale_paint(shape.paint, _matrix_scale(matrix)),
        flip_h=x1 > x2,
        flip_v=y1 > y2,
    )


def _transform_dml_freeform_shape(shape: Shape, matrix: tuple[float, float, float, float, float, float]) -> Shape:
    points = _transform_points(shape.points, matrix)
    transformed = _freeform_shape(points, _scale_paint(shape.paint, _matrix_scale(matrix)), shape.closed)
    return replace(transformed, rotation=shape.rotation)


def _dml_text_insets(element: ET.Element) -> tuple[float, float, float, float]:
    body_pr = element.find(f".//{qn(NS_A, 'bodyPr')}")
    if body_pr is None:
        return 0.0, 0.0, 0.0, 0.0
    left = _dml_int(body_pr.get("lIns"), 0) or 0
    top = _dml_int(body_pr.get("tIns"), 0) or 0
    right = _dml_int(body_pr.get("rIns"), 0) or 0
    bottom = _dml_int(body_pr.get("bIns"), 0) or 0
    return _px(left), _px(top), _px(right), _px(bottom)


def _shape_kind_to_dml(kind: str) -> str:
    return {"rect": "rect", "roundRect": "roundRect", "ellipse": "ellipse", "line": "line", "text": "rect"}[kind]


def _dml_kind_to_shape(kind: str) -> str | None:
    return {
        "rect": "rect",
        "flowChartProcess": "rect",
        "roundRect": "roundRect",
        "flowChartTerminator": "roundRect",
        "flowChartAlternateProcess": "roundRect",
        "ellipse": "ellipse",
        "oval": "ellipse",
        "flowChartConnector": "ellipse",
        "line": "line",
        "straightConnector1": "line",
    }.get(kind)


def _regular_polygon_points(sides: int, x: float, y: float, width: float, height: float) -> list[tuple[float, float]]:
    center_x = x + width / 2
    center_y = y + height / 2
    radius_x = width / 2
    radius_y = height / 2
    return [
        (
            center_x + math.cos(-math.pi / 2 + 2 * math.pi * index / sides) * radius_x,
            center_y + math.sin(-math.pi / 2 + 2 * math.pi * index / sides) * radius_y,
        )
        for index in range(sides)
    ]


def _regular_star_points(points: int, x: float, y: float, width: float, height: float, inner_scale: float = 0.55) -> list[tuple[float, float]]:
    center_x = x + width / 2
    center_y = y + height / 2
    radius_x = width / 2
    radius_y = height / 2
    return [
        (
            center_x + math.cos(-math.pi / 2 + math.pi * index / points) * radius_x * (inner_scale if index % 2 else 1),
            center_y + math.sin(-math.pi / 2 + math.pi * index / points) * radius_y * (inner_scale if index % 2 else 1),
        )
        for index in range(points * 2)
    ]


def _ellipse_arc_points(
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
    start_degrees: float,
    end_degrees: float,
    segments: int = 12,
) -> list[tuple[float, float]]:
    return [
        (
            center_x + math.cos(math.radians(start_degrees + (end_degrees - start_degrees) * index / segments)) * radius_x,
            center_y + math.sin(math.radians(start_degrees + (end_degrees - start_degrees) * index / segments)) * radius_y,
        )
        for index in range(segments + 1)
    ]


def _dml_preset_points(kind: str, x: float, y: float, width: float, height: float) -> list[tuple[float, float]]:
    if width <= 0 or height <= 0:
        return []
    left = x
    center_x = x + width / 2
    right = x + width
    top = y
    center_y = y + height / 2
    bottom = y + height
    quarter_x = x + width / 4
    three_quarter_x = x + width * 3 / 4
    quarter_y = y + height / 4
    three_quarter_y = y + height * 3 / 4
    arrow_shaft_top = y + height * 0.4
    arrow_shaft_bottom = y + height * 0.6
    arrow_head_x = x + width * 0.65
    arrow_head_y = y + height * 0.65
    if kind == "triangle":
        return [(center_x, top), (right, bottom), (left, bottom)]
    if kind == "flowChartExtract":
        return [(center_x, top), (right, bottom), (left, bottom)]
    if kind == "flowChartMerge":
        return [(left, top), (right, top), (center_x, bottom)]
    if kind == "rtTriangle":
        return [(left, top), (right, bottom), (left, bottom)]
    if kind in {"diamond", "flowChartDecision", "flowChartSort"}:
        return [(center_x, top), (right, center_y), (center_x, bottom), (left, center_y)]
    if kind == "flowChartCollate":
        return [(left, top), (right, top), (center_x, center_y), (right, bottom), (left, bottom), (center_x, center_y)]
    if kind in {"parallelogram", "flowChartData", "flowChartInputOutput"}:
        return [(quarter_x, top), (right, top), (three_quarter_x, bottom), (left, bottom)]
    if kind in {"trapezoid", "flowChartManualInput"}:
        return [(quarter_x, top), (three_quarter_x, top), (right, bottom), (left, bottom)]
    if kind == "nonIsoscelesTrapezoid":
        return [(x + width * 0.18, top), (right, top), (x + width * 0.82, bottom), (left, bottom)]
    if kind == "flowChartManualOperation":
        return [(left, top), (right, top), (three_quarter_x, bottom), (quarter_x, bottom)]
    if kind == "flowChartDocument":
        return [
            (left, top),
            (right, top),
            (right, y + height * 0.82),
            (three_quarter_x, bottom),
            (center_x, y + height * 0.88),
            (quarter_x, bottom),
            (left, y + height * 0.82),
        ]
    if kind == "flowChartPunchedCard":
        return [(x + width * 0.18, top), (right, top), (right, bottom), (left, bottom), (left, y + height * 0.18)]
    if kind == "flowChartPunchedTape":
        return [
            (left, y + height * 0.12),
            (quarter_x, top),
            (center_x, y + height * 0.12),
            (three_quarter_x, top),
            (right, y + height * 0.12),
            (right, y + height * 0.88),
            (three_quarter_x, bottom),
            (center_x, y + height * 0.88),
            (quarter_x, bottom),
            (left, y + height * 0.88),
        ]
    if kind == "flowChartDelay":
        return [(left, top), (x + width * 0.7, top), (right, center_y), (x + width * 0.7, bottom), (left, bottom)]
    if kind == "flowChartStoredData":
        return [(x + width * 0.15, top), (right, top), (right, bottom), (x + width * 0.15, bottom), (left, center_y)]
    if kind == "flowChartDisplay":
        return [(left, top), (x + width * 0.8, top), (right, center_y), (x + width * 0.8, bottom), (left, bottom), (x + width * 0.15, center_y)]
    if kind in {"flowChartOr", "flowChartSummingJunction"}:
        return _regular_polygon_points(12, x, y, width, height)
    if kind == "pentagon":
        return [(center_x, top), (right, y + height * 0.38), (x + width * 0.81, bottom), (x + width * 0.19, bottom), (left, y + height * 0.38)]
    if kind in {"hexagon", "flowChartPreparation"}:
        return [(quarter_x, top), (three_quarter_x, top), (right, center_y), (three_quarter_x, bottom), (quarter_x, bottom), (left, center_y)]
    if kind == "heptagon":
        return _regular_polygon_points(7, x, y, width, height)
    if kind == "octagon":
        return [
            (quarter_x, top),
            (three_quarter_x, top),
            (right, quarter_y),
            (right, three_quarter_y),
            (three_quarter_x, bottom),
            (quarter_x, bottom),
            (left, three_quarter_y),
            (left, quarter_y),
        ]
    if kind == "pie":
        return [(center_x, center_y), *_ellipse_arc_points(center_x, center_y, width / 2, height / 2, -90, 0)]
    if kind == "chord":
        return _ellipse_arc_points(center_x, center_y, width / 2, height / 2, -90, 90)
    if kind == "blockArc":
        outer = _ellipse_arc_points(center_x, center_y, width / 2, height / 2, -90, 0)
        inner = _ellipse_arc_points(center_x, center_y, width * 0.28, height * 0.28, 0, -90)
        return [*outer, *inner]
    if kind == "decagon":
        return _regular_polygon_points(10, x, y, width, height)
    if kind == "dodecagon":
        return _regular_polygon_points(12, x, y, width, height)
    if kind == "bevel":
        bevel_x = x + width * 0.18
        bevel_y = y + height * 0.18
        return [
            (bevel_x, top),
            (right - width * 0.18, top),
            (right, bevel_y),
            (right, bottom - height * 0.18),
            (right - width * 0.18, bottom),
            (bevel_x, bottom),
            (left, bottom - height * 0.18),
            (left, bevel_y),
        ]
    if kind == "snip1Rect":
        return [(left, top), (three_quarter_x, top), (right, quarter_y), (right, bottom), (left, bottom)]
    if kind == "snip2SameRect":
        return [(quarter_x, top), (right, top), (right, three_quarter_y), (three_quarter_x, bottom), (left, bottom), (left, quarter_y)]
    if kind == "snip2DiagRect":
        return [(left, top), (three_quarter_x, top), (right, quarter_y), (right, bottom), (quarter_x, bottom), (left, three_quarter_y)]
    if kind == "flowChartOffpageConnector":
        return [(left, top), (right, top), (right, three_quarter_y), (center_x, bottom), (left, three_quarter_y)]
    if kind == "chevron":
        return [(left, top), (three_quarter_x, top), (right, center_y), (three_quarter_x, bottom), (left, bottom), (quarter_x, center_y)]
    if kind == "homePlate":
        return [(left, top), (three_quarter_x, top), (right, center_y), (three_quarter_x, bottom), (left, bottom)]
    if kind == "foldedCorner":
        return [(left, top), (three_quarter_x, top), (right, quarter_y), (right, bottom), (left, bottom)]
    if kind == "corner":
        return [(left, top), (right, top), (right, quarter_y), (quarter_x, quarter_y), (quarter_x, bottom), (left, bottom)]
    if kind == "halfFrame":
        return [(left, top), (right, top), (right, quarter_y), (quarter_x, quarter_y), (quarter_x, bottom), (left, bottom)]
    if kind == "diagStripe":
        return [(left, bottom), (quarter_x, bottom), (right, top), (three_quarter_x, top)]
    if kind == "plaque":
        return [
            (x + width * 0.2, top),
            (x + width * 0.8, top),
            (right, y + height * 0.2),
            (right, y + height * 0.8),
            (x + width * 0.8, bottom),
            (x + width * 0.2, bottom),
            (left, y + height * 0.8),
            (left, y + height * 0.2),
        ]
    if kind in {
        "actionButtonBackPrevious",
        "actionButtonBeginning",
        "actionButtonBlank",
        "actionButtonDocument",
        "actionButtonEnd",
        "actionButtonForwardNext",
        "actionButtonHelp",
        "actionButtonHome",
        "actionButtonInformation",
        "actionButtonMovie",
        "actionButtonReturn",
        "actionButtonSound",
    }:
        radius_x = width * 0.12
        radius_y = height * 0.12
        return [
            (x + radius_x, top),
            (right - radius_x, top),
            (right, y + radius_y),
            (right, bottom - radius_y),
            (right - radius_x, bottom),
            (x + radius_x, bottom),
            (left, bottom - radius_y),
            (left, y + radius_y),
        ]
    if kind == "funnel":
        return [
            (left, top),
            (right, top),
            (x + width * 0.62, y + height * 0.58),
            (x + width * 0.62, bottom),
            (x + width * 0.38, bottom),
            (x + width * 0.38, y + height * 0.58),
        ]
    if kind == "wedgeRectCallout":
        return [
            (left, top),
            (right, top),
            (right, y + height * 0.68),
            (x + width * 0.62, y + height * 0.68),
            (x + width * 0.42, bottom),
            (x + width * 0.48, y + height * 0.68),
            (left, y + height * 0.68),
        ]
    if kind == "wedgeRoundRectCallout":
        return [
            (x + width * 0.12, top),
            (x + width * 0.88, top),
            (right, y + height * 0.12),
            (right, y + height * 0.68),
            (x + width * 0.62, y + height * 0.68),
            (x + width * 0.42, bottom),
            (x + width * 0.48, y + height * 0.68),
            (x + width * 0.12, y + height * 0.68),
            (left, y + height * 0.56),
            (left, y + height * 0.12),
        ]
    if kind == "wedgeEllipseCallout":
        return [
            (center_x, top),
            (x + width * 0.85, y + height * 0.08),
            (right, y + height * 0.34),
            (x + width * 0.88, y + height * 0.58),
            (x + width * 0.62, y + height * 0.68),
            (x + width * 0.42, bottom),
            (x + width * 0.48, y + height * 0.68),
            (x + width * 0.18, y + height * 0.64),
            (left, y + height * 0.38),
            (x + width * 0.12, y + height * 0.12),
        ]
    if kind == "ribbon":
        return [
            (left, y + height * 0.18),
            (x + width * 0.2, y + height * 0.3),
            (x + width * 0.2, top),
            (x + width * 0.8, top),
            (x + width * 0.8, y + height * 0.3),
            (right, y + height * 0.18),
            (x + width * 0.9, center_y),
            (right, y + height * 0.82),
            (x + width * 0.8, y + height * 0.7),
            (x + width * 0.8, bottom),
            (x + width * 0.2, bottom),
            (x + width * 0.2, y + height * 0.7),
            (left, y + height * 0.82),
            (x + width * 0.1, center_y),
        ]
    if kind == "ribbon2":
        return [
            (left, y + height * 0.32),
            (x + width * 0.2, y + height * 0.2),
            (x + width * 0.2, top),
            (x + width * 0.8, top),
            (x + width * 0.8, y + height * 0.2),
            (right, y + height * 0.32),
            (x + width * 0.9, center_y),
            (right, y + height * 0.68),
            (x + width * 0.8, y + height * 0.8),
            (x + width * 0.8, bottom),
            (x + width * 0.2, bottom),
            (x + width * 0.2, y + height * 0.8),
            (left, y + height * 0.68),
            (x + width * 0.1, center_y),
        ]
    if kind == "leftRightRibbon":
        return [
            (left, top),
            (x + width * 0.18, y + height * 0.22),
            (x + width * 0.18, y + height * 0.08),
            (x + width * 0.82, y + height * 0.08),
            (x + width * 0.82, y + height * 0.22),
            (right, top),
            (x + width * 0.9, center_y),
            (right, bottom),
            (x + width * 0.82, y + height * 0.78),
            (x + width * 0.82, y + height * 0.92),
            (x + width * 0.18, y + height * 0.92),
            (x + width * 0.18, y + height * 0.78),
            (left, bottom),
            (x + width * 0.1, center_y),
        ]
    if kind == "leftBracket":
        return [(right, top), (left, top), (left, bottom), (right, bottom), (right, three_quarter_y), (quarter_x, three_quarter_y), (quarter_x, quarter_y), (right, quarter_y)]
    if kind == "rightBracket":
        return [(left, top), (right, top), (right, bottom), (left, bottom), (left, three_quarter_y), (three_quarter_x, three_quarter_y), (three_quarter_x, quarter_y), (left, quarter_y)]
    if kind == "leftBrace":
        return [
            (right, top),
            (center_x, top),
            (quarter_x, quarter_y),
            (center_x, center_y),
            (quarter_x, three_quarter_y),
            (center_x, bottom),
            (right, bottom),
            (three_quarter_x, three_quarter_y),
            (right, center_y),
            (three_quarter_x, quarter_y),
        ]
    if kind == "rightBrace":
        return [
            (left, top),
            (center_x, top),
            (three_quarter_x, quarter_y),
            (center_x, center_y),
            (three_quarter_x, three_quarter_y),
            (center_x, bottom),
            (left, bottom),
            (quarter_x, three_quarter_y),
            (left, center_y),
            (quarter_x, quarter_y),
        ]
    if kind in {"plus", "mathPlus"}:
        return [
            (x + width * 0.35, top),
            (x + width * 0.65, top),
            (x + width * 0.65, y + height * 0.35),
            (right, y + height * 0.35),
            (right, y + height * 0.65),
            (x + width * 0.65, y + height * 0.65),
            (x + width * 0.65, bottom),
            (x + width * 0.35, bottom),
            (x + width * 0.35, y + height * 0.65),
            (left, y + height * 0.65),
            (left, y + height * 0.35),
            (x + width * 0.35, y + height * 0.35),
        ]
    if kind == "mathMinus":
        return [(left, arrow_shaft_top), (right, arrow_shaft_top), (right, arrow_shaft_bottom), (left, arrow_shaft_bottom)]
    if kind == "mathMultiply":
        return [
            (x + width * 0.2, top),
            (center_x, y + height * 0.3),
            (x + width * 0.8, top),
            (right, y + height * 0.2),
            (x + width * 0.7, center_y),
            (right, y + height * 0.8),
            (x + width * 0.8, bottom),
            (center_x, y + height * 0.7),
            (x + width * 0.2, bottom),
            (left, y + height * 0.8),
            (x + width * 0.3, center_y),
            (left, y + height * 0.2),
        ]
    if kind == "heart":
        return [
            (center_x, bottom),
            (left, y + height * 0.45),
            (x + width * 0.08, y + height * 0.18),
            (x + width * 0.32, top),
            (center_x, y + height * 0.2),
            (x + width * 0.68, top),
            (x + width * 0.92, y + height * 0.18),
            (right, y + height * 0.45),
        ]
    if kind == "lightningBolt":
        return [
            (x + width * 0.58, top),
            (x + width * 0.18, y + height * 0.55),
            (x + width * 0.46, y + height * 0.55),
            (x + width * 0.36, bottom),
            (x + width * 0.82, y + height * 0.4),
            (x + width * 0.54, y + height * 0.4),
        ]
    if kind == "teardrop":
        return [
            (center_x, top),
            (x + width * 0.82, y + height * 0.08),
            (right, y + height * 0.38),
            (x + width * 0.88, y + height * 0.72),
            (center_x, bottom),
            (x + width * 0.18, y + height * 0.72),
            (left, y + height * 0.38),
            (x + width * 0.18, y + height * 0.12),
        ]
    if kind == "sun":
        return _regular_star_points(16, x, y, width, height, 0.72)
    if kind == "moon":
        outer = _ellipse_arc_points(center_x, center_y, width / 2, height / 2, -90, 270, 16)
        inner = _ellipse_arc_points(x + width * 0.62, center_y, width * 0.34, height * 0.42, 270, -90, 16)
        return [*outer, *inner]
    if kind == "cloud":
        return [
            (x + width * 0.15, y + height * 0.62),
            (x + width * 0.08, y + height * 0.48),
            (x + width * 0.2, y + height * 0.36),
            (x + width * 0.34, y + height * 0.38),
            (x + width * 0.42, y + height * 0.22),
            (x + width * 0.62, y + height * 0.2),
            (x + width * 0.72, y + height * 0.35),
            (x + width * 0.86, y + height * 0.36),
            (x + width * 0.96, y + height * 0.52),
            (x + width * 0.88, y + height * 0.7),
            (x + width * 0.62, y + height * 0.76),
            (x + width * 0.38, y + height * 0.74),
            (x + width * 0.22, y + height * 0.74),
        ]
    if kind == "star4":
        return [
            (center_x, top),
            (x + width * 0.6, y + height * 0.4),
            (right, center_y),
            (x + width * 0.6, y + height * 0.6),
            (center_x, bottom),
            (x + width * 0.4, y + height * 0.6),
            (left, center_y),
            (x + width * 0.4, y + height * 0.4),
        ]
    if kind == "star5":
        return [
            (center_x, top),
            (x + width * 0.62, y + height * 0.38),
            (right, y + height * 0.38),
            (x + width * 0.69, y + height * 0.59),
            (x + width * 0.81, bottom),
            (center_x, y + height * 0.72),
            (x + width * 0.19, bottom),
            (x + width * 0.31, y + height * 0.59),
            (left, y + height * 0.38),
            (x + width * 0.38, y + height * 0.38),
        ]
    if kind == "star6":
        return [
            (center_x, top),
            (x + width * 0.6, y + height * 0.33),
            (x + width * 0.93, quarter_y),
            (x + width * 0.7, center_y),
            (x + width * 0.93, three_quarter_y),
            (x + width * 0.6, y + height * 0.67),
            (center_x, bottom),
            (x + width * 0.4, y + height * 0.67),
            (x + width * 0.07, three_quarter_y),
            (x + width * 0.3, center_y),
            (x + width * 0.07, quarter_y),
            (x + width * 0.4, y + height * 0.33),
        ]
    if kind == "star8":
        return [
            (center_x, top),
            (x + width * 0.58, y + height * 0.32),
            (x + width * 0.85, y + height * 0.15),
            (x + width * 0.68, y + height * 0.42),
            (right, center_y),
            (x + width * 0.68, y + height * 0.58),
            (x + width * 0.85, y + height * 0.85),
            (x + width * 0.58, y + height * 0.68),
            (center_x, bottom),
            (x + width * 0.42, y + height * 0.68),
            (x + width * 0.15, y + height * 0.85),
            (x + width * 0.32, y + height * 0.58),
            (left, center_y),
            (x + width * 0.32, y + height * 0.42),
            (x + width * 0.15, y + height * 0.15),
            (x + width * 0.42, y + height * 0.32),
        ]
    if kind == "star10":
        return [
            (center_x, top),
            (x + width * 0.56, y + height * 0.36),
            (x + width * 0.79, y + height * 0.1),
            (x + width * 0.68, y + height * 0.43),
            (right, y + height * 0.35),
            (x + width * 0.7, y + height * 0.55),
            (x + width * 0.98, y + height * 0.65),
            (x + width * 0.64, y + height * 0.63),
            (x + width * 0.65, y + height * 0.95),
            (center_x, y + height * 0.7),
            (x + width * 0.35, y + height * 0.95),
            (x + width * 0.36, y + height * 0.63),
            (x + width * 0.02, y + height * 0.65),
            (x + width * 0.3, y + height * 0.55),
            (left, y + height * 0.35),
            (x + width * 0.32, y + height * 0.43),
            (x + width * 0.21, y + height * 0.1),
            (x + width * 0.44, y + height * 0.36),
        ]
    if kind == "star12":
        return _regular_star_points(12, x, y, width, height)
    if kind == "star16":
        return _regular_star_points(16, x, y, width, height)
    if kind == "irregularSeal1":
        return _regular_star_points(16, x, y, width, height, 0.62)
    if kind == "irregularSeal2":
        return _regular_star_points(24, x, y, width, height, 0.68)
    if kind == "rightArrow":
        return [(left, quarter_y), (arrow_head_x, quarter_y), (arrow_head_x, top), (right, center_y), (arrow_head_x, bottom), (arrow_head_x, three_quarter_y), (left, three_quarter_y)]
    if kind == "notchedRightArrow":
        return [(left, quarter_y), (arrow_head_x, quarter_y), (arrow_head_x, top), (right, center_y), (arrow_head_x, bottom), (arrow_head_x, three_quarter_y), (left, three_quarter_y), (quarter_x, center_y)]
    if kind == "leftArrow":
        return [(right, quarter_y), (x + width * 0.35, quarter_y), (x + width * 0.35, top), (left, center_y), (x + width * 0.35, bottom), (x + width * 0.35, three_quarter_y), (right, three_quarter_y)]
    if kind == "upArrow":
        return [(quarter_x, bottom), (quarter_x, y + height * 0.35), (left, y + height * 0.35), (center_x, top), (right, y + height * 0.35), (three_quarter_x, y + height * 0.35), (three_quarter_x, bottom)]
    if kind == "downArrow":
        return [(quarter_x, top), (quarter_x, arrow_head_y), (left, arrow_head_y), (center_x, bottom), (right, arrow_head_y), (three_quarter_x, arrow_head_y), (three_quarter_x, top)]
    if kind == "leftRightArrow":
        return [
            (left, center_y),
            (quarter_x, top),
            (quarter_x, quarter_y),
            (three_quarter_x, quarter_y),
            (three_quarter_x, top),
            (right, center_y),
            (three_quarter_x, bottom),
            (three_quarter_x, three_quarter_y),
            (quarter_x, three_quarter_y),
            (quarter_x, bottom),
        ]
    if kind == "upDownArrow":
        return [
            (center_x, top),
            (right, quarter_y),
            (three_quarter_x, quarter_y),
            (three_quarter_x, three_quarter_y),
            (right, three_quarter_y),
            (center_x, bottom),
            (left, three_quarter_y),
            (quarter_x, three_quarter_y),
            (quarter_x, quarter_y),
            (left, quarter_y),
        ]
    if kind == "quadArrow":
        return [
            (center_x, top),
            (three_quarter_x, quarter_y),
            (x + width * 0.6, quarter_y),
            (x + width * 0.6, arrow_shaft_top),
            (three_quarter_x, arrow_shaft_top),
            (right, center_y),
            (three_quarter_x, arrow_shaft_bottom),
            (x + width * 0.6, arrow_shaft_bottom),
            (x + width * 0.6, three_quarter_y),
            (three_quarter_x, three_quarter_y),
            (center_x, bottom),
            (quarter_x, three_quarter_y),
            (x + width * 0.4, three_quarter_y),
            (x + width * 0.4, arrow_shaft_bottom),
            (quarter_x, arrow_shaft_bottom),
            (left, center_y),
            (quarter_x, arrow_shaft_top),
            (x + width * 0.4, arrow_shaft_top),
            (x + width * 0.4, quarter_y),
            (quarter_x, quarter_y),
        ]
    if kind == "leftRightUpArrow":
        return [
            (center_x, top),
            (right, quarter_y),
            (three_quarter_x, quarter_y),
            (three_quarter_x, arrow_shaft_top),
            (right, arrow_shaft_top),
            (right, arrow_shaft_bottom),
            (three_quarter_x, arrow_shaft_bottom),
            (three_quarter_x, bottom),
            (quarter_x, bottom),
            (quarter_x, arrow_shaft_bottom),
            (left, arrow_shaft_bottom),
            (left, arrow_shaft_top),
            (quarter_x, arrow_shaft_top),
            (quarter_x, quarter_y),
            (left, quarter_y),
        ]
    if kind == "bentUpArrow":
        return [
            (x + width * 0.55, bottom),
            (x + width * 0.55, quarter_y),
            (x + width * 0.35, quarter_y),
            (x + width * 0.7, top),
            (right, quarter_y),
            (x + width * 0.8, quarter_y),
            (x + width * 0.8, bottom),
        ]
    if kind == "bentArrow":
        return [
            (left, top),
            (x + width * 0.55, top),
            (x + width * 0.55, arrow_shaft_top),
            (arrow_head_x, arrow_shaft_top),
            (arrow_head_x, quarter_y),
            (right, center_y),
            (arrow_head_x, three_quarter_y),
            (arrow_head_x, arrow_shaft_bottom),
            (x + width * 0.35, arrow_shaft_bottom),
            (x + width * 0.35, bottom),
            (left, bottom),
        ]
    if kind == "uturnArrow":
        return [
            (center_x, top),
            (right, quarter_y),
            (x + width * 0.7, quarter_y),
            (x + width * 0.7, bottom),
            (x + width * 0.45, bottom),
            (x + width * 0.45, quarter_y),
            (quarter_x, quarter_y),
            (quarter_x, y + height * 0.08),
            (left, center_y),
            (quarter_x, y + height * 0.92),
            (quarter_x, three_quarter_y),
            (center_x, three_quarter_y),
        ]
    if kind == "leftUpArrow":
        return [
            (center_x, top),
            (three_quarter_x, quarter_y),
            (x + width * 0.6, quarter_y),
            (x + width * 0.6, bottom),
            (x + width * 0.4, bottom),
            (x + width * 0.4, arrow_shaft_bottom),
            (quarter_x, arrow_shaft_bottom),
            (quarter_x, three_quarter_y),
            (left, center_y),
            (quarter_x, quarter_y),
            (quarter_x, arrow_shaft_top),
            (x + width * 0.4, arrow_shaft_top),
            (x + width * 0.4, quarter_y),
            (quarter_x, quarter_y),
        ]
    return []


def _freeform_shape(points: list[tuple[float, float]], paint: Paint, closed: bool) -> Shape:
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    return Shape(
        "freeform",
        min_x,
        min_y,
        max(max_x - min_x, 0),
        max(max_y - min_y, 0),
        paint,
        points=tuple(points),
        closed=closed,
    )


def _parse_points(value: str) -> list[tuple[float, float]]:
    numbers = [float(match) for match in re.findall(NUMBER_RE, value)]
    if len(numbers) < 4 or len(numbers) % 2:
        return []
    if not all(math.isfinite(number) for number in numbers):
        return []
    return list(zip(numbers[0::2], numbers[1::2], strict=False))


def _parse_linear_path(value: str) -> tuple[list[tuple[float, float]], bool] | None:
    tokens = re.findall(rf"[A-Za-z]|{NUMBER_RE}", value)
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    start: tuple[float, float] | None = None
    last_cubic_control: tuple[float, float] | None = None
    last_quad_control: tuple[float, float] | None = None
    closed = False
    index = 0
    command = ""
    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[A-Za-z]", token):
            command = token
            index += 1
            if command in {"Z", "z"}:
                closed = True
                if start is not None and points and points[-1] != start:
                    points.append(start)
                continue
        if command in {"M", "m", "L", "l"}:
            if index + 1 >= len(tokens) or re.fullmatch(r"[A-Za-z]", tokens[index]) or re.fullmatch(r"[A-Za-z]", tokens[index + 1]):
                return None
            x = float(tokens[index])
            y = float(tokens[index + 1])
            index += 2
            if command.islower():
                x += current[0]
                y += current[1]
            current = (x, y)
            if command in {"M", "m"} and start is None:
                start = current
                command = "l" if command == "m" else "L"
            points.append(current)
            last_cubic_control = None
            last_quad_control = None
        elif command in {"H", "h"}:
            if index >= len(tokens) or re.fullmatch(r"[A-Za-z]", tokens[index]):
                return None
            x = float(tokens[index]) + (current[0] if command == "h" else 0)
            current = (x, current[1])
            points.append(current)
            last_cubic_control = None
            last_quad_control = None
            index += 1
        elif command in {"V", "v"}:
            if index >= len(tokens) or re.fullmatch(r"[A-Za-z]", tokens[index]):
                return None
            y = float(tokens[index]) + (current[1] if command == "v" else 0)
            current = (current[0], y)
            points.append(current)
            last_cubic_control = None
            last_quad_control = None
            index += 1
        elif command in {"C", "c"}:
            if index + 5 >= len(tokens) or any(re.fullmatch(r"[A-Za-z]", tokens[index + offset]) for offset in range(6)):
                return None
            raw = [float(tokens[index + offset]) for offset in range(6)]
            if command == "c":
                c1 = (current[0] + raw[0], current[1] + raw[1])
                c2 = (current[0] + raw[2], current[1] + raw[3])
                end = (current[0] + raw[4], current[1] + raw[5])
            else:
                c1 = (raw[0], raw[1])
                c2 = (raw[2], raw[3])
                end = (raw[4], raw[5])
            points.extend(_cubic_points(current, c1, c2, end))
            current = end
            last_cubic_control = c2
            last_quad_control = None
            index += 6
        elif command in {"S", "s"}:
            if index + 3 >= len(tokens) or any(re.fullmatch(r"[A-Za-z]", tokens[index + offset]) for offset in range(4)):
                return None
            raw = [float(tokens[index + offset]) for offset in range(4)]
            c1 = (
                current[0] * 2 - last_cubic_control[0],
                current[1] * 2 - last_cubic_control[1],
            ) if last_cubic_control is not None else current
            if command == "s":
                c2 = (current[0] + raw[0], current[1] + raw[1])
                end = (current[0] + raw[2], current[1] + raw[3])
            else:
                c2 = (raw[0], raw[1])
                end = (raw[2], raw[3])
            points.extend(_cubic_points(current, c1, c2, end))
            current = end
            last_cubic_control = c2
            last_quad_control = None
            index += 4
        elif command in {"Q", "q"}:
            if index + 3 >= len(tokens) or any(re.fullmatch(r"[A-Za-z]", tokens[index + offset]) for offset in range(4)):
                return None
            raw = [float(tokens[index + offset]) for offset in range(4)]
            if command == "q":
                control = (current[0] + raw[0], current[1] + raw[1])
                end = (current[0] + raw[2], current[1] + raw[3])
            else:
                control = (raw[0], raw[1])
                end = (raw[2], raw[3])
            points.extend(_quadratic_points(current, control, end))
            current = end
            last_quad_control = control
            last_cubic_control = None
            index += 4
        elif command in {"T", "t"}:
            if index + 1 >= len(tokens) or any(re.fullmatch(r"[A-Za-z]", tokens[index + offset]) for offset in range(2)):
                return None
            raw = [float(tokens[index + offset]) for offset in range(2)]
            control = (
                current[0] * 2 - last_quad_control[0],
                current[1] * 2 - last_quad_control[1],
            ) if last_quad_control is not None else current
            if command == "t":
                end = (current[0] + raw[0], current[1] + raw[1])
            else:
                end = (raw[0], raw[1])
            points.extend(_quadratic_points(current, control, end))
            current = end
            last_quad_control = control
            last_cubic_control = None
            index += 2
        elif command in {"A", "a"}:
            if index + 6 >= len(tokens) or any(re.fullmatch(r"[A-Za-z]", tokens[index + offset]) for offset in range(7)):
                return None
            raw = [float(tokens[index + offset]) for offset in range(7)]
            rx, ry, angle, large_arc, sweep = raw[:5]
            end = (raw[5], raw[6])
            if command == "a":
                end = (current[0] + end[0], current[1] + end[1])
            points.extend(_arc_points(current, rx, ry, angle, bool(round(large_arc)), bool(round(sweep)), end))
            current = end
            last_quad_control = None
            last_cubic_control = None
            index += 7
        else:
            return None
    if len(points) < 2:
        return None
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in points):
        return None
    if closed and points[-1] == points[0]:
        points = points[:-1]
    return points, closed


def _cubic_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    segments: int = 16,
) -> list[tuple[float, float]]:
    result = []
    for step in range(1, segments + 1):
        t = step / segments
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        result.append((x, y))
    return result


def _quadratic_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    segments: int = 12,
) -> list[tuple[float, float]]:
    result = []
    for step in range(1, segments + 1):
        t = step / segments
        mt = 1 - t
        x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
        y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
        result.append((x, y))
    return result


def _arc_points(
    start: tuple[float, float],
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc: bool,
    sweep: bool,
    end: tuple[float, float],
    max_segments: int = 32,
) -> list[tuple[float, float]]:
    if rx == 0 or ry == 0 or start == end:
        return [end]
    rx = abs(rx)
    ry = abs(ry)
    phi = math.radians(x_axis_rotation % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    dx = (start[0] - end[0]) / 2
    dy = (start[1] - end[1]) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    radius_scale = (x1p**2) / (rx**2) + (y1p**2) / (ry**2)
    if radius_scale > 1:
        scale = math.sqrt(radius_scale)
        rx *= scale
        ry *= scale

    sign = -1 if large_arc == sweep else 1
    numerator = max(rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2, 0)
    denominator = rx**2 * y1p**2 + ry**2 * x1p**2
    coef = sign * math.sqrt(numerator / denominator) if denominator else 0
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    cx = cos_phi * cxp - sin_phi * cyp + (start[0] + end[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (start[1] + end[1]) / 2

    start_angle = _vector_angle((1, 0), ((x1p - cxp) / rx, (y1p - cyp) / ry))
    delta_angle = _vector_angle(
        ((x1p - cxp) / rx, (y1p - cyp) / ry),
        ((-x1p - cxp) / rx, (-y1p - cyp) / ry),
    )
    if not sweep and delta_angle > 0:
        delta_angle -= math.tau
    elif sweep and delta_angle < 0:
        delta_angle += math.tau

    segments = max(4, min(max_segments, math.ceil(abs(delta_angle) / (math.pi / 12))))
    result = []
    for step in range(1, segments + 1):
        theta = start_angle + delta_angle * step / segments
        x = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + cx
        y = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + cy
        result.append((x, y))
    return result


def _vector_angle(u: tuple[float, float], v: tuple[float, float]) -> float:
    dot = u[0] * v[0] + u[1] * v[1]
    det = u[0] * v[1] - u[1] * v[0]
    return math.atan2(det, dot)


def _parse_style(style: str) -> dict[str, str]:
    return {key: value for key, (value, _) in _parse_style_declarations(style).items()}


def _parse_style_declarations(style: str) -> dict[str, CssDeclaration]:
    result: dict[str, CssDeclaration] = {}
    for item in _css_declaration_list(style):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        key = key.strip()
        if not key.startswith("--"):
            key = key.lower()
        normalized, important = _normalize_css_value_with_importance(value)
        if key == "font":
            for font_key, font_value in _parse_font_shorthand(normalized).items():
                if font_key not in result or important or not result[font_key][1]:
                    result[font_key] = (font_value, important)
            continue
        if key not in result or important or not result[key][1]:
            result[key] = (normalized, important)
    return result


def _css_declaration_list(style: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    paren_depth = 0
    for char in style:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        if char == ";" and paren_depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    items.append("".join(current))
    return items


def _normalize_css_value(value: str) -> str:
    return _normalize_css_value_with_importance(value)[0]


def _normalize_css_value_with_importance(value: str) -> CssDeclaration:
    stripped = value.strip()
    important = bool(re.search(r"\s*!important\s*$", stripped, flags=re.I))
    if important:
        stripped = re.sub(r"\s*!important\s*$", "", stripped, flags=re.I).strip()
    return stripped, important


def _parse_font_shorthand(value: str) -> dict[str, str]:
    tokens = _css_value_tokens(value)
    if not tokens:
        return {}
    result: dict[str, str] = {}
    size_index: int | None = None
    skip_next_oblique_angle = False
    for index, token in enumerate(tokens):
        if skip_next_oblique_angle:
            skip_next_oblique_angle = False
            if _font_angle_token_is_supported(token):
                continue
        size = token.split("/", 1)[0]
        if _font_size_token_is_supported(size):
            size_index = index
            result["font-size"] = size
            break
        normalized = token.strip().lower()
        if normalized in {"italic", "oblique"} or normalized.startswith("oblique "):
            result["font-style"] = "oblique" if normalized.startswith("oblique") else normalized
            skip_next_oblique_angle = normalized == "oblique"
        elif normalized in {"small-caps", "all-small-caps"}:
            result["font-variant"] = normalized
        elif _font_weight_token_is_supported(normalized):
            result["font-weight"] = normalized
    if size_index is None:
        return {}
    result.setdefault("font-style", "normal")
    result.setdefault("font-variant", "normal")
    result.setdefault("font-weight", "normal")
    family = " ".join(tokens[size_index + 1 :]).strip()
    if family:
        result["font-family"] = family
    return result


def _font_size_token_is_supported(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"xx-small", "x-small", "small", "medium", "large", "x-large", "xx-large"}:
        return True
    if not re.search(r"[a-z%]", normalized):
        return normalized == "0"
    return math.isfinite(_length(value, math.nan, "x", (0.0, 0.0)))


def _font_angle_token_is_supported(value: str) -> bool:
    return _transform_angle_arg(value) is not None and any(value.strip().lower().endswith(unit) for unit in ("deg", "rad", "grad", "turn"))


def _font_weight_token_is_supported(value: str) -> bool:
    if value in {"normal", "bold", "bolder", "lighter"}:
        return True
    try:
        weight = int(value)
    except ValueError:
        return False
    return 1 <= weight <= 1000


def _css_value_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    paren_depth = 0
    for char in value:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        if char.isspace() and paren_depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _collect_css(root: ET.Element) -> list[CssRule]:
    css: list[CssRule] = []
    order = 0
    for element in root.iter():
        if _local_name(element.tag) != "style":
            continue
        text = "".join(element.itertext())
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        order = _collect_css_rules(text, css, order)
    return css


def _collect_css_rules(text: str, css: list[CssRule], order: int) -> int:
    for selector, body in _css_rule_blocks(text):
        selector = selector.strip()
        if selector.lower().startswith("@media"):
            if _media_query_applies(selector[6:].strip()):
                order = _collect_css_rules(body, css, order)
            continue
        if selector.startswith("@"):
            continue
        declarations = _parse_style_declarations(body)
        for item in _selector_list(selector):
            key = item.strip()
            if key:
                css.append((key, declarations, _selector_specificity(key), order))
                order += 1
    return order


def _css_rule_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        selector = text[index:start].strip()
        depth = 1
        quote: str | None = None
        end = start + 1
        while end < len(text):
            char = text[end]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        if depth == 0 and selector:
            blocks.append((selector, text[start + 1 : end]))
        index = end + 1
    return blocks


def _media_query_applies(query: str) -> bool:
    normalized = " ".join(query.strip().lower().split())
    if not normalized:
        return True
    queries = [item.strip() for item in normalized.split(",")]
    return any(_single_media_query_applies(query) for query in queries)


def _single_media_query_applies(query: str) -> bool:
    if query.startswith("only "):
        query = query[5:].strip()
    if query.startswith("not "):
        return not _single_media_query_applies(query[4:].strip())
    return query in {"all", "screen"} or query.startswith("all and ") or query.startswith("screen and ")


def _collect_refs(root: ET.Element) -> dict[str, ET.Element]:
    refs = {}
    for element in root.iter():
        element_id = element.get("id")
        if element_id:
            refs[element_id] = element
    return refs


def _root_viewbox_matrix(root: ET.Element) -> tuple[float, float, float, float, float, float]:
    return _viewbox_matrix(root)


def _viewport_size(
    element: ET.Element,
    width_override: float | None = None,
    height_override: float | None = None,
) -> tuple[float, float]:
    view_box = element.get("viewBox")
    if view_box:
        numbers = [float(match) for match in re.findall(NUMBER_RE, view_box)]
        if len(numbers) == 4 and numbers[2] > 0 and numbers[3] > 0:
            return width_override if width_override is not None else numbers[2], height_override if height_override is not None else numbers[3]
    width = width_override if width_override is not None else _num(element.get("width"), 0)
    height = height_override if height_override is not None else _num(element.get("height"), 0)
    return width, height


def _viewbox_matrix(
    element: ET.Element,
    width_override: float | None = None,
    height_override: float | None = None,
    preserve_aspect_ratio_override: str | None = None,
) -> tuple[float, float, float, float, float, float]:
    view_box = element.get("viewBox")
    if not view_box:
        return _identity_matrix()
    numbers = [float(match) for match in re.findall(NUMBER_RE, view_box)]
    if len(numbers) != 4 or numbers[2] == 0 or numbers[3] == 0:
        return _identity_matrix()
    min_x, min_y, view_width, view_height = numbers
    width = width_override if width_override is not None else _num(element.get("width"), view_width)
    height = height_override if height_override is not None else _num(element.get("height"), view_height)
    sx = width / view_width
    sy = height / view_height
    align, meet_or_slice = _preserve_aspect_ratio(
        preserve_aspect_ratio_override if preserve_aspect_ratio_override is not None else element.get("preserveAspectRatio")
    )
    if align == "none":
        return _matrix_multiply((sx, 0, 0, sy, 0, 0), (1, 0, 0, 1, -min_x, -min_y))

    scale = max(sx, sy) if meet_or_slice == "slice" else min(sx, sy)
    extra_x = width - view_width * scale
    extra_y = height - view_height * scale
    offset_x = _alignment_offset(align[1:4], extra_x)
    offset_y = _alignment_offset(align[5:8], extra_y)
    return _matrix_multiply(
        (1, 0, 0, 1, offset_x, offset_y),
        _matrix_multiply((scale, 0, 0, scale, 0, 0), (1, 0, 0, 1, -min_x, -min_y)),
    )


def _preserve_aspect_ratio(value: str | None) -> tuple[str, str]:
    parts = (value or "xMidYMid meet").split()
    if parts and parts[0].lower() == "defer":
        parts = parts[1:]
    align_token = parts[0] if parts else "xMidYMid"
    if align_token.lower() == "none":
        return "none", "meet"
    alignments = {value.lower(): value for value in (f"x{x}Y{y}" for x in ("Min", "Mid", "Max") for y in ("Min", "Mid", "Max"))}
    align = alignments.get(align_token.lower(), "xMidYMid")
    meet_or_slice = parts[1].lower() if len(parts) > 1 and parts[1].lower() in {"meet", "slice"} else "meet"
    return align, meet_or_slice


def _image_preserve_aspect_ratio_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    href: str,
    value: str | None,
) -> tuple[float, float, float, float, tuple[int, int, int, int] | None]:
    if value is None:
        return x, y, width, height, None
    align, meet_or_slice = _preserve_aspect_ratio(value)
    if align == "none":
        return x, y, width, height, None
    intrinsic = _data_image_dimensions(href)
    if intrinsic is None:
        return x, y, width, height, None
    image_width, image_height = intrinsic
    if image_width <= 0 or image_height <= 0:
        return x, y, width, height, None
    if meet_or_slice == "slice":
        return x, y, width, height, _image_slice_src_rect(image_width, image_height, width, height, align)

    scale = min(width / image_width, height / image_height)
    rendered_width = image_width * scale
    rendered_height = image_height * scale
    return (
        x + _alignment_offset(align[1:4], width - rendered_width),
        y + _alignment_offset(align[5:8], height - rendered_height),
        rendered_width,
        rendered_height,
        None,
    )


def _image_slice_src_rect(
    image_width: float,
    image_height: float,
    viewport_width: float,
    viewport_height: float,
    align: str,
) -> tuple[int, int, int, int] | None:
    image_aspect = image_width / image_height
    viewport_aspect = viewport_width / viewport_height
    if math.isclose(image_aspect, viewport_aspect, rel_tol=1e-9, abs_tol=1e-9):
        return None
    if image_aspect > viewport_aspect:
        crop = 1.0 - viewport_aspect / image_aspect
        before, after = _aligned_crop(crop, align[1:4])
        return round(before * 100000), 0, round(after * 100000), 0
    crop = 1.0 - image_aspect / viewport_aspect
    before, after = _aligned_crop(crop, align[5:8])
    return 0, round(before * 100000), 0, round(after * 100000)


def _aligned_crop(total: float, alignment: str) -> tuple[float, float]:
    if alignment == "Min":
        return 0.0, total
    if alignment == "Max":
        return total, 0.0
    half = total / 2
    return half, half


def _alignment_offset(axis: str, extra: float) -> float:
    if axis == "Mid":
        return extra / 2
    if axis == "Max":
        return extra
    return 0.0


def _computed_style(
    element: ET.Element,
    css: list[CssRule],
    inherited: dict[str, str],
    ancestors: tuple[ET.Element, ...] = (),
    previous_siblings: tuple[ET.Element, ...] = (),
) -> dict[str, str]:
    style = dict(inherited)
    style.pop("transform", None)
    style.pop("transform-origin", None)
    css_priorities: dict[str, tuple[int, tuple[int, int, int, int], int]] = {}

    def apply_declaration(key: str, value: str, important: bool, specificity: tuple[int, int, int, int], order: int) -> None:
        priority = (1 if important else 0, specificity, order)
        if priority >= css_priorities.get(key, (-1, (-1, -1, -1, -1), -1)):
            style[key] = value
            css_priorities[key] = priority

    for attr in (
        "fill",
        "fill-opacity",
        "opacity",
        "stroke",
        "stroke-opacity",
        "stop-color",
        "stop-opacity",
        "stroke-width",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "font",
        "font-size",
        "font-family",
        "font-feature-settings",
        "font-kerning",
        "font-size-adjust",
        "font-stretch",
        "font-weight",
        "font-style",
        "font-variant",
        "font-variation-settings",
        "glyph-orientation-horizontal",
        "glyph-orientation-vertical",
        "gradientTransform",
        "gradientUnits",
        "kerning",
        "letter-spacing",
        "lengthAdjust",
        "text-decoration",
        "text-decoration-color",
        "text-decoration-line",
        "text-decoration-skip-ink",
        "text-decoration-style",
        "text-decoration-thickness",
        "text-anchor",
        "text-align",
        "text-orientation",
        "text-transform",
        "text-underline-offset",
        "textLength",
        "baseline-shift",
        "dominant-baseline",
        "alignment-baseline",
        "direction",
        "unicode-bidi",
        "color",
        "display",
        "visibility",
        "clip-path",
        "clip-rule",
        "color-rendering",
        "fill-rule",
        "filter",
        "image-rendering",
        "isolation",
        "marker",
        "marker-start",
        "marker-mid",
        "marker-end",
        "mask",
        "mix-blend-mode",
        "overflow",
        "border-collapse",
        "border-spacing",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "paint-order",
        "pathLength",
        "preserveAspectRatio",
        "rotate",
        "shape-rendering",
        "spreadMethod",
        "vector-effect",
        "text-rendering",
        "transform",
        "transform-origin",
        "vertical-align",
        "white-space",
        "writing-mode",
        "word-spacing",
    ):
        if element.get(attr) is not None:
            if attr == "font":
                for font_key, font_value in _parse_font_shorthand(element.get(attr, "")).items():
                    apply_declaration(font_key, font_value, False, (0, 0, 0, 0), -1)
            else:
                apply_declaration(attr, element.get(attr, ""), False, (0, 0, 0, 0), -1)

    for attr, style_key in (
        ("align", "text-align"),
        ("valign", "vertical-align"),
        ("bgcolor", "background-color"),
        ("border", "border"),
        ("bordercolor", "border-color"),
        ("cellpadding", "padding"),
        ("cellspacing", "border-spacing"),
    ):
        if element.get(attr) is not None:
            apply_declaration(style_key, element.get(attr, ""), False, (0, 0, 0, 0), -1)

    if _local_name(element.tag) == "font":
        if element.get("face") is not None:
            apply_declaration("font-family", element.get("face", ""), False, (0, 0, 0, 0), -1)
        if element.get("size") is not None:
            apply_declaration("font-size", _html_font_tag_size(element.get("size", "")), False, (0, 0, 0, 0), -1)
    if element.get("nowrap") is not None:
        apply_declaration("white-space", "nowrap", False, (0, 0, 0, 0), -1)

    for selector, declarations, specificity, order in css:
        if _selector_matches(selector, element, ancestors, previous_siblings):
            css_specificity = (0, *specificity)
            for key, (value, important) in declarations.items():
                apply_declaration(key, value, important, css_specificity, order)

    for key, (value, important) in _parse_style_declarations(element.get("style", "")).items():
        apply_declaration(key, value, important, (1, 0, 0, 0), 1_000_000)
    for key, value in tuple(style.items()):
        normalized = value.strip().lower()
        if normalized in {"inherit", "unset"}:
            if key in inherited:
                style[key] = inherited[key]
            else:
                style.pop(key)
        elif normalized == "initial":
            style.pop(key)
    for key, value in tuple(style.items()):
        style[key] = _resolve_css_vars(value, style)
    if style.get("font-size") is not None:
        style["font-size"] = _resolve_font_size_value(style.get("font-size"), inherited.get("font-size"))
    if style.get("text-decoration") is None and style.get("text-decoration-line") is not None:
        style["text-decoration"] = style["text-decoration-line"]
    if style.get("fill", "").strip().lower() == "currentcolor":
        style["fill"] = style.get("color", "#000000")
    if style.get("stroke", "").strip().lower() == "currentcolor":
        style["stroke"] = style.get("color", "#000000")
    _resolve_context_paint_values(style, inherited)
    return style


def _resolve_context_paint_values(style: dict[str, str], inherited: dict[str, str]) -> None:
    context_paints = {
        "context-fill": inherited.get("fill"),
        "context-stroke": inherited.get("stroke"),
    }
    for key in ("fill", "stroke"):
        context_value = context_paints.get(style.get(key, "").strip().lower())
        if context_value is not None:
            style[key] = context_value


def _html_font_tag_size(value: str) -> str:
    normalized = value.strip()
    if re.fullmatch(r"[+-]?\d+", normalized):
        index = int(normalized)
        if normalized.startswith(("+", "-")):
            index += 3
        legacy_sizes = {
            1: "10px",
            2: "13px",
            3: "16px",
            4: "18px",
            5: "24px",
            6: "32px",
            7: "48px",
        }
        return legacy_sizes[min(7, max(1, index))]
    return value


def _previous_element_siblings(parent: ET.Element, element: ET.Element) -> tuple[ET.Element, ...]:
    siblings = []
    for child in parent:
        if child is element:
            break
        siblings.append(child)
    return tuple(siblings)


def _resolve_font_size_value(value: str | None, inherited_value: str | None) -> str:
    if value is None:
        return "16"
    stripped = value.strip()
    lower = stripped.lower()
    inherited_size = _svg_font_size(inherited_value)
    try:
        if lower.endswith("%"):
            return _fmt(_finite_float(lower[:-1]) / 100 * inherited_size)
        if lower.endswith("rem"):
            return _fmt(_finite_float(lower[:-3]) * 16)
        if lower.endswith("em"):
            return _fmt(_finite_float(lower[:-2]) * inherited_size)
    except ValueError:
        return stripped
    return stripped


def _is_hidden(style: dict[str, str]) -> bool:
    return _is_display_none(style) or _is_visibility_hidden(style)


def _is_display_none(style: dict[str, str]) -> bool:
    display = " ".join(style.get("display", "").strip().lower().split())
    return display == "none"


def _is_visibility_hidden(style: dict[str, str]) -> bool:
    visibility = " ".join(style.get("visibility", "").strip().lower().split())
    return visibility in {"hidden", "collapse"}


def _apply_rect_clip(
    shape: Shape,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
) -> Shape | None:
    if shape.kind not in {"rect", "roundRect", "ellipse", "line", "freeform", "text", "image"}:
        return shape
    clip_bounds = _rect_clip_bounds(shape, style, refs, matrix)
    if clip_bounds is None:
        return shape
    clip_x, clip_y, clip_width, clip_height = clip_bounds
    if shape.kind == "line":
        clipped_line = _clip_line_to_rect(shape, clip_x, clip_y, clip_width, clip_height)
        if clipped_line is None:
            return None
        (line_x1, line_y1), (line_x2, line_y2) = clipped_line
        return Shape(
            kind=shape.kind,
            x=min(line_x1, line_x2),
            y=min(line_y1, line_y2),
            width=abs(line_x2 - line_x1),
            height=abs(line_y2 - line_y1),
            paint=shape.paint,
            flip_h=line_x2 < line_x1,
            flip_v=line_y2 < line_y1,
        )
    if shape.kind == "freeform":
        if shape.closed or len(shape.points) != 2:
            return shape
        clipped_line = _clip_segment_to_rect(shape.points[0], shape.points[1], clip_x, clip_y, clip_width, clip_height)
        if clipped_line is None:
            return None
        return _freeform_shape([clipped_line[0], clipped_line[1]], shape.paint, closed=False)
    x1 = max(shape.x, clip_x)
    y1 = max(shape.y, clip_y)
    x2 = min(shape.x + shape.width, clip_x + clip_width)
    y2 = min(shape.y + shape.height, clip_y + clip_height)
    if x2 <= x1 or y2 <= y1:
        return None
    return Shape(
        kind=shape.kind,
        x=x1,
        y=y1,
        width=x2 - x1,
        height=y2 - y1,
        paint=shape.paint,
        flip_h=shape.flip_h,
        flip_v=shape.flip_v,
        points=shape.points,
        closed=shape.closed,
        text=shape.text,
        font_size=shape.font_size,
        font_weight=shape.font_weight,
        font_style=shape.font_style,
        font_family=shape.font_family,
        font_variant=shape.font_variant,
        text_decoration=shape.text_decoration,
        text_decoration_style=shape.text_decoration_style,
        text_decoration_color=shape.text_decoration_color,
        text_decoration_alpha=shape.text_decoration_alpha,
        text_decoration_thickness=shape.text_decoration_thickness,
        text_anchor=shape.text_anchor,
        text_baseline=shape.text_baseline,
        text_direction=shape.text_direction,
        text_wrap=shape.text_wrap,
        text_baseline_shift=shape.text_baseline_shift,
        letter_spacing=shape.letter_spacing,
        rx=min(shape.rx or 0, (x2 - x1) / 2) if shape.rx is not None else None,
        ry=min(shape.ry or 0, (y2 - y1) / 2) if shape.ry is not None else None,
        image_href=shape.image_href,
        image_src_rect=shape.image_src_rect,
        rotation=shape.rotation,
        text_runs=shape.text_runs,
    )


def _clip_line_to_rect(
    shape: Shape,
    clip_x: float,
    clip_y: float,
    clip_width: float,
    clip_height: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x1 = shape.x + shape.width if shape.flip_h else shape.x
    x2 = shape.x if shape.flip_h else shape.x + shape.width
    y1 = shape.y + shape.height if shape.flip_v else shape.y
    y2 = shape.y if shape.flip_v else shape.y + shape.height
    return _clip_segment_to_rect((x1, y1), (x2, y2), clip_x, clip_y, clip_width, clip_height)


def _clip_segment_to_rect(
    point1: tuple[float, float],
    point2: tuple[float, float],
    clip_x: float,
    clip_y: float,
    clip_width: float,
    clip_height: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x1, y1 = point1
    x2, y2 = point2
    dx = x2 - x1
    dy = y2 - y1
    start = 0.0
    end = 1.0
    left = clip_x
    right = clip_x + clip_width
    top = clip_y
    bottom = clip_y + clip_height
    for edge_delta, edge_distance in (
        (-dx, x1 - left),
        (dx, right - x1),
        (-dy, y1 - top),
        (dy, bottom - y1),
    ):
        if _close(edge_delta, 0):
            if edge_distance < 0:
                return None
            continue
        ratio = edge_distance / edge_delta
        if edge_delta < 0:
            start = max(start, ratio)
        else:
            end = min(end, ratio)
        if start > end:
            return None
    clipped_x1 = x1 + start * dx
    clipped_y1 = y1 + start * dy
    clipped_x2 = x1 + end * dx
    clipped_y2 = y1 + end * dy
    if _close(clipped_x1, clipped_x2) and _close(clipped_y1, clipped_y2):
        return None
    return (clipped_x1, clipped_y1), (clipped_x2, clipped_y2)


def _rect_clip_bounds(
    shape: Shape | None,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float] | None:
    clip_path = style.get("clip-path")
    if not clip_path or clip_path == "none":
        return None
    ref = _url_ref(clip_path)
    if ref is None or ref[1].strip():
        return None
    clip = refs.get(ref[0])
    if clip is None or _local_name(clip.tag) != "clipPath":
        return None
    units = _clip_path_units(clip)
    if units not in {"userSpaceOnUse", "objectBoundingBox"}:
        return None
    rect = next((child for child in clip if _local_name(child.tag) == "rect"), None)
    if rect is None:
        return None
    x = _num(rect.get("x"), 0)
    y = _num(rect.get("y"), 0)
    width = _num(rect.get("width"), 0)
    height = _num(rect.get("height"), 0)
    if width <= 0 or height <= 0:
        return None
    if units == "objectBoundingBox":
        if shape is None or clip.get("transform") is not None or rect.get("transform") is not None:
            return None
        return (
            shape.x + x * shape.width,
            shape.y + y * shape.height,
            width * shape.width,
            height * shape.height,
        )
    clip_matrix = _matrix_multiply(matrix, _parse_transform(clip.get("transform", "")))
    clip_matrix = _matrix_multiply(clip_matrix, _parse_transform(rect.get("transform", "")))
    points = _transform_points(_rect_points(x, y, width, height), clip_matrix)
    xs = {round(px, 9) for px, _ in points}
    ys = {round(py, 9) for _, py in points}
    if len(xs) != 2 or len(ys) != 2:
        return None
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    return min_x, min_y, max_x - min_x, max_y - min_y


def _clip_path_is_supported(
    element: ET.Element,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
) -> bool:
    clip_path = style.get("clip-path")
    if not clip_path or clip_path == "none":
        return True
    tag = _local_name(element.tag)
    if tag == "polyline":
        points = _parse_points(element.get("points", ""))
        if len(points) != 2:
            return False
    elif tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        if path is None:
            return False
        points, closed = path
        if closed or len(points) != 2:
            return False
    elif tag not in {"rect", "circle", "ellipse", "line", "text", "image"}:
        return False
    return _rect_clip_bounds(None, style, refs, matrix) is not None or _rect_clip_path_has_object_bbox_rect(style, refs)


def _rect_clip_path_has_object_bbox_rect(style: dict[str, str], refs: dict[str, ET.Element]) -> bool:
    clip_path = style.get("clip-path")
    if not clip_path or clip_path == "none":
        return False
    ref = _url_ref(clip_path)
    if ref is None or ref[1].strip():
        return False
    clip = refs.get(ref[0])
    if clip is None or _local_name(clip.tag) != "clipPath" or _clip_path_units(clip) != "objectBoundingBox":
        return False
    if clip.get("transform") is not None:
        return False
    rect = next((child for child in clip if _local_name(child.tag) == "rect"), None)
    return rect is not None and rect.get("transform") is None and _num(rect.get("width"), 0) > 0 and _num(rect.get("height"), 0) > 0


def _clip_path_units(clip: ET.Element) -> str:
    normalized = clip.get("clipPathUnits", "userSpaceOnUse").strip().lower()
    return {"userspaceonuse": "userSpaceOnUse", "objectboundingbox": "objectBoundingBox"}.get(normalized, "")


def _marker_is_supported(element: ET.Element, style: dict[str, str], refs: dict[str, ET.Element]) -> bool:
    marker_values = [_svg_marker_style_value(style, "marker-start"), _svg_marker_style_value(style, "marker-end")]
    if not any(value and value != "none" for value in marker_values):
        return True
    tag = _local_name(element.tag)
    if tag == "line":
        return all(_svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none")
    if tag == "polyline":
        points = _parse_points(element.get("points", ""))
        has_unsupported_mid_marker = style.get("marker") not in {None, "none"} and len(points) > 2 and style.get("marker-mid") is None
        return not has_unsupported_mid_marker and all(_svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none")
    if tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        has_unsupported_mid_marker = bool(path and style.get("marker") not in {None, "none"} and len(path[0]) > 2 and style.get("marker-mid") is None)
        return bool(path and not path[1] and not has_unsupported_mid_marker) and all(
            _svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none"
        )
    return False


def _selector_matches(
    selector: str,
    element: ET.Element,
    ancestors: tuple[ET.Element, ...],
    previous_siblings: tuple[ET.Element, ...] = (),
) -> bool:
    if selector.strip() == ":root":
        return not ancestors
    parts = _selector_parts(selector)
    if not parts or parts[-1] in {">", "+", "~"}:
        return False
    if not _simple_selector_matches(parts[-1], element):
        return False

    ancestor_index = len(ancestors) - 1
    sibling_index = len(previous_siblings) - 1
    require_direct = False
    require_adjacent = False
    require_sibling = False
    index = len(parts) - 2
    while index >= 0:
        part = parts[index]
        if part == ">":
            require_direct = True
            index -= 1
            continue
        if part == "+":
            require_adjacent = True
            index -= 1
            continue
        if part == "~":
            require_sibling = True
            index -= 1
            continue
        if require_adjacent:
            if sibling_index < 0 or not _simple_selector_matches(part, previous_siblings[sibling_index]):
                return False
            sibling_index -= 1
            require_adjacent = False
            index -= 1
            continue
        elif require_sibling:
            while sibling_index >= 0 and not _simple_selector_matches(part, previous_siblings[sibling_index]):
                sibling_index -= 1
            if sibling_index < 0:
                return False
            sibling_index -= 1
            require_sibling = False
            index -= 1
            continue
        elif part in {"+", "~"}:
            return False
        if require_direct:
            if ancestor_index < 0 or not _simple_selector_matches(part, ancestors[ancestor_index]):
                return False
            ancestor_index -= 1
            require_direct = False
        else:
            while ancestor_index >= 0 and not _simple_selector_matches(part, ancestors[ancestor_index]):
                ancestor_index -= 1
            if ancestor_index < 0:
                return False
            ancestor_index -= 1
        index -= 1
    return True


def _selector_specificity(selector: str) -> tuple[int, int, int]:
    selector_without_pseudos = _selector_without_supported_pseudo_classes(selector)
    selector_without_attrs = _selector_without_attribute_selectors(selector_without_pseudos)
    selector_without_attrs = selector_without_attrs.replace(":root", "")
    if ":" in selector_without_attrs:
        return (0, 0, 0)
    id_count = len(re.findall(r"#[A-Za-z_][\w:-]*", selector_without_pseudos))
    class_count = len(re.findall(r"\.[A-Za-z_][\w:-]*", selector_without_pseudos)) + len(
        re.findall(r"\[[^\]]+\]", selector_without_pseudos)
    )
    element_count = 0
    for part in (part for part in _selector_parts(selector_without_pseudos) if part not in {">", "+", "~"}):
        if part == "*":
            continue
        first_modifier = min([index for index in (part.find("."), part.find("#"), part.find("[")) if index >= 0], default=-1)
        tag = part[:first_modifier] if first_modifier > 0 else ("" if first_modifier == 0 else part)
        if tag and re.fullmatch(r"[A-Za-z_][\w:-]*", tag):
            element_count += 1
    is_specificity = _selector_pseudo_specificity(selector, "is")
    not_specificity = _selector_pseudo_specificity(selector, "not")
    id_count += is_specificity[0] + not_specificity[0]
    class_count += is_specificity[1] + not_specificity[1]
    element_count += is_specificity[2] + not_specificity[2]
    return id_count, class_count, element_count


def _selector_parts(selector: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    attribute_depth = 0
    paren_depth = 0
    for char in selector.strip():
        if char == "[":
            attribute_depth += 1
        elif char == "]" and attribute_depth:
            attribute_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        if attribute_depth == 0 and paren_depth == 0 and char in {" ", ">", "+", "~"}:
            if current:
                parts.append("".join(current))
                current = []
            if char in {">", "+", "~"}:
                parts.append(char)
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _selector_list(selector: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    attribute_depth = 0
    paren_depth = 0
    quote: str | None = None
    for char in selector:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "[":
            attribute_depth += 1
        elif char == "]" and attribute_depth:
            attribute_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        if char == "," and attribute_depth == 0 and paren_depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _simple_selector_matches(selector: str, element: ET.Element) -> bool:
    selector = selector.strip()
    not_selectors = _selector_pseudo_arguments(selector, "not")
    if any(_simple_selector_matches(not_selector, element) for not_selector in not_selectors):
        return False
    is_selectors = _selector_pseudo_arguments(selector, "is")
    if is_selectors and not any(_simple_selector_matches(is_selector, element) for is_selector in is_selectors):
        return False
    where_selectors = _selector_pseudo_arguments(selector, "where")
    if where_selectors and not any(_simple_selector_matches(where_selector, element) for where_selector in where_selectors):
        return False
    selector = _selector_without_supported_pseudo_classes(selector)
    if not selector.strip():
        return True
    selector_without_attrs = _selector_without_attribute_selectors(selector)
    if not selector or any(mark in selector_without_attrs for mark in ("+", "~", ":")):
        return False
    tag = _local_name(element.tag)
    element_id = element.get("id")
    element_classes = set(element.get("class", "").split())
    if selector == "*":
        return True
    attributes = re.findall(r"\[([^\]]+)\]", selector)
    if "[" in selector_without_attrs or "]" in selector_without_attrs:
        return False
    first_modifier = min([index for index in (selector_without_attrs.find("."), selector_without_attrs.find("#")) if index >= 0], default=-1)
    selector_tag = selector_without_attrs[:first_modifier] if first_modifier > 0 else ("" if first_modifier == 0 else selector_without_attrs)
    remainder = selector_without_attrs[first_modifier:] if first_modifier >= 0 else ""
    selector_ids = re.findall(r"#([A-Za-z_][\w:-]*)", remainder)
    selector_classes = re.findall(r"\.([A-Za-z_][\w:-]*)", remainder)
    if len(selector_ids) > 1:
        return False
    if selector_tag and selector_tag != "*" and selector_tag != tag:
        return False
    if selector_ids and selector_ids[0] != element_id:
        return False
    return all(selector_class in element_classes for selector_class in selector_classes) and all(
        _attribute_selector_matches(attribute, element) for attribute in attributes
    )


def _selector_without_attribute_selectors(selector: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", selector)


def _selector_without_supported_pseudo_classes(selector: str) -> str:
    for name in ("not", "is", "where"):
        selector = _strip_selector_pseudo(selector, name)
    return selector


def _selector_pseudo_arguments(selector: str, name: str) -> list[str]:
    args: list[str] = []
    for body in _selector_pseudo_bodies(selector, name):
        args.extend(item.strip() for item in _selector_list(body) if item.strip())
    return args


def _selector_pseudo_specificity(selector: str, name: str) -> tuple[int, int, int]:
    max_specificity = (0, 0, 0)
    for argument in _selector_pseudo_arguments(selector, name):
        max_specificity = max(max_specificity, _selector_specificity(argument))
    return max_specificity


def _strip_selector_pseudo(selector: str, name: str) -> str:
    token = f":{name}("
    result: list[str] = []
    index = 0
    while index < len(selector):
        if selector[index : index + len(token)].lower() == token:
            end = _selector_function_end(selector, index + len(token) - 1)
            if end is not None:
                index = end + 1
                continue
        result.append(selector[index])
        index += 1
    return "".join(result)


def _selector_pseudo_bodies(selector: str, name: str) -> list[str]:
    token = f":{name}("
    bodies: list[str] = []
    index = 0
    while index < len(selector):
        if selector[index : index + len(token)].lower() == token:
            body_start = index + len(token)
            end = _selector_function_end(selector, body_start - 1)
            if end is not None:
                bodies.append(selector[body_start:end])
                index = end + 1
                continue
        index += 1
    return bodies


def _selector_function_end(selector: str, open_paren_index: int) -> int | None:
    depth = 0
    quote: str | None = None
    for index in range(open_paren_index, len(selector)):
        char = selector[index]
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _resolve_css_vars(value: str, style: dict[str, str]) -> str:
    resolved = value
    for _ in range(8):
        next_value = _resolve_one_css_var(resolved, style)
        if next_value == resolved:
            return resolved
        resolved = next_value
    return resolved


def _resolve_one_css_var(value: str, style: dict[str, str]) -> str:
    start = value.find("var(")
    if start < 0:
        return value
    index = start + 4
    depth = 1
    quote: str | None = None
    while index < len(value):
        char = value[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    if depth != 0:
        return value
    body = value[start + 4 : index]
    name, fallback = _split_css_var_body(body)
    replacement = style.get(name.strip())
    if replacement is None:
        replacement = fallback.strip() if fallback is not None else f"var({body})"
    return value[:start] + replacement + value[index + 1 :]


def _split_css_var_body(body: str) -> tuple[str, str | None]:
    depth = 0
    quote: str | None = None
    for index, char in enumerate(body):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            return body[:index], body[index + 1 :]
    return body, None


def _attribute_selector_matches(selector: str, element: ET.Element) -> bool:
    match = re.fullmatch(
        r"\s*([A-Za-z_][\w:-]*)(?:\s*([~|^$*]?=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"']+))(?:\s+([iIsS]))?)?\s*",
        selector,
    )
    if not match:
        return False
    name = match.group(1)
    operator = match.group(2)
    expected = next((group for group in match.groups()[2:5] if group is not None), None)
    modifier = match.group(6)
    actual = _attribute_value(element, name)
    if actual is None:
        return False
    if expected is None:
        return operator is None
    if modifier is not None and modifier.lower() == "i":
        actual = actual.lower()
        expected = expected.lower()
    if operator == "=":
        return actual == expected
    if operator == "~=":
        return expected in actual.split()
    if operator == "|=":
        return actual == expected or actual.startswith(f"{expected}-")
    if operator == "^=":
        return actual.startswith(expected)
    if operator == "$=":
        return actual.endswith(expected)
    if operator == "*=":
        return expected in actual
    return False


def _attribute_value(element: ET.Element, name: str) -> str | None:
    value = element.get(name)
    if value is not None:
        return value
    for attr, attr_value in element.attrib.items():
        if _local_name(attr) == name:
            return attr_value
    return None


def _href(element: ET.Element) -> str | None:
    return element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")


def _url_ref(value: str | None) -> tuple[str, str] | None:
    if value is None:
        return None
    match = re.match(r"^url\(\s*(?:['\"])?\s*#([^'\"\)\s]+)\s*(?:['\"])?\s*\)(.*)$", value.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _switch_selected_child(element: ET.Element) -> ET.Element | None:
    return next((child for child in element if _switch_child_is_supported(child)), None)


def _switch_child_is_supported(element: ET.Element) -> bool:
    for attr in ("requiredExtensions", "requiredFeatures", "requiredFormats"):
        if element.get(attr, "").strip():
            return False
    return not element.get("systemLanguage", "").strip()


def _supported_data_image(value: str) -> bool:
    return _data_image_bytes(value) is not None


def _data_image_dimensions(value: str) -> tuple[int, int] | None:
    data = _data_image_bytes(value)
    if data is None:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _webp_dimensions(data)
    return None


def _data_image_bytes(value: str) -> bytes | None:
    match = re.match(r"^data:image/(?:png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=\s]+)$", value, flags=re.I)
    if not match:
        return None
    try:
        data = base64.b64decode(re.sub(r"\s+", "", match.group(1)), validate=True)
    except binascii.Error:
        return None
    return data or None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        while marker == 0xFF and index < len(data):
            marker = data[index]
            index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if segment_length < 7:
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    chunk_type = data[12:16]
    chunk_size = int.from_bytes(data[16:20], "little")
    payload = data[20 : 20 + chunk_size]
    if len(payload) < chunk_size:
        return None
    if chunk_type == b"VP8X":
        if len(payload) < 10:
            return None
        return int.from_bytes(payload[4:7], "little") + 1, int.from_bytes(payload[7:10], "little") + 1
    if chunk_type == b"VP8L":
        if len(payload) < 5 or payload[0] != 0x2F:
            return None
        bits = int.from_bytes(payload[1:5], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk_type == b"VP8 ":
        if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
            return None
        return int.from_bytes(payload[6:8], "little") & 0x3FFF, int.from_bytes(payload[8:10], "little") & 0x3FFF
    return None


def _alpha(style: dict[str, str], channel: str) -> float | None:
    values = []
    if style.get("opacity") is not None:
        values.append(_clamped_num(style.get("opacity"), 1.0))
    channel_value = style.get(f"{channel}-opacity")
    if channel_value is not None:
        values.append(_clamped_num(channel_value, 1.0))
    if not values:
        return None
    alpha = 1.0
    for value in values:
        alpha *= value
    return alpha


def _image_alpha(style: dict[str, str]) -> float | None:
    if style.get("opacity") is None:
        return None
    return _clamped_num(style.get("opacity"), 1.0)


def _combined_alpha(*values: float | None) -> float | None:
    alpha = 1.0
    seen = False
    for value in values:
        if value is None:
            continue
        alpha *= value
        seen = True
    return alpha if seen else None


def _clamped_num(value: str | None, default: float) -> float:
    parsed = _alpha_value(value)
    if parsed is None:
        parsed = float(default)
    return max(0.0, min(parsed, 1.0))


def _alpha_value(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.endswith("%"):
        try:
            return _finite_float(stripped[:-1]) / 100
        except ValueError:
            return None
    lower = stripped.lower()
    if lower.startswith("calc(") and stripped.endswith(")"):
        return _calc_length(stripped[5:-1], "x", (1.0, 1.0), allow_percent=True)
    function_result = _css_length_function(stripped, "x", (1.0, 1.0), allow_percent=True)
    if function_result is not None:
        return function_result
    try:
        return _finite_float(stripped)
    except ValueError:
        return None


def _identity_matrix() -> tuple[float, float, float, float, float, float]:
    return 1.0, 0.0, 0.0, 1.0, 0.0, 0.0


def _is_identity_matrix(matrix: tuple[float, float, float, float, float, float]) -> bool:
    return all(abs(a - b) < 1e-9 for a, b in zip(matrix, _identity_matrix(), strict=True))


def _matrix_multiply(
    left: tuple[float, float, float, float, float, float],
    right: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _parse_transform(value: str) -> tuple[float, float, float, float, float, float]:
    matrix = _identity_matrix()
    for raw_name, raw_args in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", value):
        name = raw_name.lower()
        raw_values = _transform_arguments(raw_args)
        item = _identity_matrix()
        if name == "matrix" and len(raw_values) >= 6:
            numbers = [_transform_number_arg(item) for item in raw_values]
            if any(item is None for item in numbers):
                continue
            numbers = [item for item in numbers if item is not None]
            item = tuple(numbers[:6])  # type: ignore[assignment]
        elif name == "translate":
            lengths = [_transform_length_arg(raw_values[index]) for index in range(min(len(raw_values), 2))]
            if any(length is None for length in lengths):
                continue
            item = (1.0, 0.0, 0.0, 1.0, lengths[0] if lengths else 0.0, lengths[1] if len(lengths) > 1 else 0.0)
        elif name == "scale":
            numbers = [_transform_number_arg(item) for item in raw_values]
            if any(item is None for item in numbers):
                continue
            numbers = [item for item in numbers if item is not None]
            sx = numbers[0] if numbers else 1.0
            sy = numbers[1] if len(numbers) > 1 else sx
            item = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate":
            angle_degrees = _transform_angle_arg(raw_values[0]) if raw_values else 0.0
            if angle_degrees is None:
                continue
            angle = math.radians(angle_degrees)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            rotation = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(raw_values) >= 3:
                cx = _transform_length_arg(raw_values[1])
                cy = _transform_length_arg(raw_values[2])
                if cx is None or cy is None:
                    continue
                item = _matrix_multiply(
                    _matrix_multiply((1.0, 0.0, 0.0, 1.0, cx, cy), rotation),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
            else:
                item = rotation
        elif name == "skewx" and raw_values:
            angle_degrees = _transform_angle_arg(raw_values[0])
            if angle_degrees is None:
                continue
            item = (1.0, 0.0, math.tan(math.radians(angle_degrees)), 1.0, 0.0, 0.0)
        elif name == "skewy" and raw_values:
            angle_degrees = _transform_angle_arg(raw_values[0])
            if angle_degrees is None:
                continue
            item = (1.0, math.tan(math.radians(angle_degrees)), 0.0, 1.0, 0.0, 0.0)
        matrix = _matrix_multiply(matrix, item)
    return matrix


def _style_transform_matrix(
    element: ET.Element,
    style: dict[str, str],
    viewport: tuple[float, float],
) -> tuple[float, float, float, float, float, float]:
    matrix = _parse_transform(style.get("transform", ""))
    origin = _transform_origin(style.get("transform-origin"), viewport, element, style)
    if origin is None:
        return matrix
    return _matrix_multiply(
        _matrix_multiply((1.0, 0.0, 0.0, 1.0, origin[0], origin[1]), matrix),
        (1.0, 0.0, 0.0, 1.0, -origin[0], -origin[1]),
    )


def _transform_origin(
    value: str | None,
    viewport: tuple[float, float],
    element: ET.Element | None = None,
    style: dict[str, str] | None = None,
) -> tuple[float, float] | None:
    if value is None:
        return None
    parts = _css_value_tokens(value)
    parts = _transform_origin_parts(parts)
    if parts is None:
        return None
    reference_box = _element_reference_box(element, style or {}, viewport) if element is not None else None
    x = _origin_length(parts[0], "x", viewport, reference_box)
    y = _origin_length(parts[1], "y", viewport, reference_box)
    if x is None or y is None:
        return None
    if len(parts) == 3:
        z = _absolute_origin_length(parts[2], "x", viewport)
        if z is None or not _close(z, 0):
            return None
    return x, y


def _transform_origin_parts(parts: list[str]) -> tuple[str, str] | tuple[str, str, str] | None:
    if len(parts) not in {1, 2, 3}:
        return None
    normalized = [part.strip().lower() for part in parts]
    z_part = parts[2] if len(parts) == 3 else None
    xy_parts = normalized[:2]
    if len(xy_parts) == 1:
        value = xy_parts[0]
        if value in {"left", "right"}:
            resolved = (_origin_keyword_to_percentage(value), "50%")
        elif value in {"top", "bottom"}:
            resolved = ("50%", _origin_keyword_to_percentage(value))
        elif value == "center":
            resolved = ("50%", "50%")
        else:
            resolved = (parts[0], "50%")
    else:
        first, second = xy_parts
        first_axis = _origin_keyword_axis(first)
        second_axis = _origin_keyword_axis(second)
        if first_axis is not None and first_axis == second_axis:
            return None
        if first_axis == "y" or second_axis == "x":
            resolved = (_origin_keyword_to_percentage(second), _origin_keyword_to_percentage(first))
        else:
            resolved = (_origin_keyword_to_percentage(first), _origin_keyword_to_percentage(second))
    if z_part is not None:
        return resolved[0], resolved[1], z_part
    return resolved


def _origin_keyword_axis(value: str) -> str | None:
    if value in {"left", "right"}:
        return "x"
    if value in {"top", "bottom"}:
        return "y"
    return None


def _origin_keyword_to_percentage(value: str) -> str:
    return {
        "left": "0%",
        "top": "0%",
        "center": "50%",
        "right": "100%",
        "bottom": "100%",
    }.get(value, value)


def _origin_length(
    value: str,
    axis: str,
    viewport: tuple[float, float],
    reference_box: tuple[float, float, float, float] | None,
) -> float | None:
    stripped = value.strip()
    if stripped.endswith("%"):
        if reference_box is None:
            return None
        try:
            percent = _finite_float(stripped[:-1]) / 100
        except ValueError:
            return None
        offset = reference_box[0] if axis == "x" else reference_box[1]
        size = reference_box[2] if axis == "x" else reference_box[3]
        return offset + percent * size
    return _absolute_origin_length(stripped, axis, viewport)


def _absolute_origin_length(value: str, axis: str, viewport: tuple[float, float]) -> float | None:
    stripped = value.strip()
    lower = stripped.lower()
    if "%" in stripped:
        return None
    length_re = rf"{NUMBER_RE}(?:px|pt|pc|in|cm|mm|q)?"
    if not re.fullmatch(length_re, lower) and not re.match(r"^(?:calc|min|max|clamp)\(", lower):
        return None
    return _optional_length(stripped, axis, viewport)


def _element_reference_box(
    element: ET.Element | None,
    style: dict[str, str],
    viewport: tuple[float, float],
) -> tuple[float, float, float, float] | None:
    if element is None:
        return None
    tag = _local_name(element.tag)
    if tag in {"rect", "image"}:
        x = _geometry_length(element, style, "x", 0, "x", viewport)
        y = _geometry_length(element, style, "y", 0, "y", viewport)
        width = _geometry_length(element, style, "width", 0, "x", viewport)
        height = _geometry_length(element, style, "height", 0, "y", viewport)
        return (x, y, width, height) if width >= 0 and height >= 0 else None
    if tag == "circle":
        cx = _geometry_length(element, style, "cx", 0, "x", viewport)
        cy = _geometry_length(element, style, "cy", 0, "y", viewport)
        r = _geometry_length(element, style, "r", 0, "diag", viewport)
        return (cx - r, cy - r, r * 2, r * 2) if r >= 0 else None
    if tag == "ellipse":
        cx = _geometry_length(element, style, "cx", 0, "x", viewport)
        cy = _geometry_length(element, style, "cy", 0, "y", viewport)
        rx = _geometry_length(element, style, "rx", 0, "x", viewport)
        ry = _geometry_length(element, style, "ry", 0, "y", viewport)
        return (cx - rx, cy - ry, rx * 2, ry * 2) if rx >= 0 and ry >= 0 else None
    if tag == "line":
        x1 = _geometry_length(element, style, "x1", 0, "x", viewport)
        y1 = _geometry_length(element, style, "y1", 0, "y", viewport)
        x2 = _geometry_length(element, style, "x2", 0, "x", viewport)
        y2 = _geometry_length(element, style, "y2", 0, "y", viewport)
        return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    if tag in {"polygon", "polyline"}:
        points = _parse_points(element.get("points", ""))
    elif tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        points = path[0] if path else []
    else:
        return None
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _transform_arguments(value: str) -> list[str]:
    return re.findall(rf"{NUMBER_RE}(?:[A-Za-z%]+)?", value)


def _transform_number_arg(value: str) -> float | None:
    try:
        if re.search(r"[A-Za-z%]", value):
            return None
        return _finite_float(value)
    except ValueError:
        return None


def _transform_length_arg(value: str) -> float | None:
    number = _num(value, math.nan)
    return number if math.isfinite(number) else None


def _transform_angle_arg(value: str) -> float | None:
    value = value.strip().lower()
    try:
        if value.endswith("turn"):
            number = _finite_float(value[:-4]) * 360
        elif value.endswith("grad"):
            number = _finite_float(value[:-4]) * 0.9
        elif value.endswith("rad"):
            number = math.degrees(_finite_float(value[:-3]))
        elif value.endswith("deg"):
            number = _finite_float(value[:-3])
        else:
            number = _finite_float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _apply_matrix(
    matrix: tuple[float, float, float, float, float, float],
    point: tuple[float, float],
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    x, y = point
    return a * x + c * y + e, b * x + d * y + f


def _transform_points(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    matrix: tuple[float, float, float, float, float, float],
) -> list[tuple[float, float]]:
    return [_apply_matrix(matrix, point) for point in points]


def _matrix_scale(matrix: tuple[float, float, float, float, float, float]) -> float:
    a, b, c, d, _, _ = matrix
    sx = math.hypot(a, b)
    sy = math.hypot(c, d)
    return (sx + sy) / 2 if sx and sy else sx or sy or 1.0


def _rect_points(x: float, y: float, width: float, height: float) -> list[tuple[float, float]]:
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]


def _ellipse_shape(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    paint: Paint,
    matrix: tuple[float, float, float, float, float, float],
) -> Shape:
    shape = _transformed_ellipse_shape(cx, cy, rx, ry, matrix, paint)
    if shape is not None:
        return shape
    points = [
        _apply_matrix(matrix, (cx + math.cos(index / 32 * math.tau) * rx, cy + math.sin(index / 32 * math.tau) * ry))
        for index in range(32)
    ]
    return _freeform_shape(points, paint, closed=True)


NAMED_COLORS = {
    "black": "#000000",
    "blue": "#0000ff",
    "cyan": "#00ffff",
    "gray": "#808080",
    "green": "#008000",
    "grey": "#808080",
    "lime": "#00ff00",
    "magenta": "#ff00ff",
    "orange": "#ffa500",
    "purple": "#800080",
    "red": "#ff0000",
    "transparent": "none",
    "white": "#ffffff",
    "yellow": "#ffff00",
}


def _paint_value(
    value: str | None,
    refs: dict[str, ET.Element],
    current_color: str | None = None,
    css: list[CssRule] | None = None,
) -> tuple[str | None, float | None]:
    if value is None:
        return None, None
    stripped = value.strip()
    ref = _url_ref(stripped)
    if ref is not None:
        color, alpha = _paint_server_value(refs.get(ref[0]), refs, current_color, css or [])
        if color:
            return color, alpha
        fallback = ref[1].strip()
        if fallback:
            return _parse_color(fallback)
        return None, None
    return _parse_color(stripped)


def _paint_server_value(
    element: ET.Element | None,
    refs: dict[str, ET.Element],
    current_color: str | None = None,
    css: list[CssRule] | None = None,
) -> tuple[str | None, float | None]:
    colors = _paint_server_colors(element, refs, current_color, css or [], set())
    if not colors:
        return None, None
    if _local_name(element.tag) == "radialGradient":
        return colors[-1]
    rgba = []
    for color, alpha in colors:
        rgb = _hex_to_rgb(color)
        if rgb is not None:
            rgba.append((*rgb, 1.0 if alpha is None else alpha))
    if not rgba:
        return None, None
    count = len(rgba)
    rgb_avg = tuple(round(sum(item[index] for item in rgba) / count) for index in range(3))
    alpha_avg = sum(item[3] for item in rgba) / count
    return _rgb_to_hex(rgb_avg), alpha_avg if alpha_avg < 1 else None


def _paint_server_colors(
    element: ET.Element | None,
    refs: dict[str, ET.Element],
    current_color: str | None,
    css: list[CssRule],
    seen: set[str],
) -> list[tuple[str, float | None]]:
    if element is None:
        return []
    tag = _local_name(element.tag)
    element_id = element.get("id")
    if element_id:
        if element_id in seen:
            return []
        seen = seen | {element_id}
    if tag == "pattern":
        return _pattern_colors(element, refs, current_color, css, seen)
    if tag not in {"linearGradient", "radialGradient"}:
        return []
    colors: list[tuple[str, float | None]] = []
    href = _href(element)
    if href and href.startswith("#"):
        colors.extend(_paint_server_colors(refs.get(href[1:]), refs, current_color, css, seen))
    colors.extend(_gradient_stops(element, current_color, css))
    return colors


def _pattern_colors(
    element: ET.Element,
    refs: dict[str, ET.Element],
    current_color: str | None,
    css: list[CssRule],
    seen: set[str],
) -> list[tuple[str, float | None]]:
    pattern_style = _computed_style(element, css, {}, ())
    return _pattern_child_colors(element, refs, current_color, css, pattern_style, (element,), seen)


def _pattern_child_colors(
    parent: ET.Element,
    refs: dict[str, ET.Element],
    current_color: str | None,
    css: list[CssRule],
    inherited_style: dict[str, str],
    ancestors: tuple[ET.Element, ...],
    seen: set[str],
) -> list[tuple[str, float | None]]:
    colors = []
    previous_children: list[ET.Element] = []
    for child in parent:
        tag = _local_name(child.tag)
        style = _computed_style(child, css, inherited_style, ancestors, tuple(previous_children))
        if _is_hidden(style):
            previous_children.append(child)
            continue
        if tag in {"g", "svg", "a"}:
            colors.extend(_pattern_child_colors(child, refs, current_color, css, style, ancestors + (child,), seen))
            previous_children.append(child)
            continue
        if tag in {"rect", "circle", "ellipse", "path", "polygon", "polyline", "text", "tspan", "line"}:
            if tag != "line":
                colors.extend(_pattern_paint_colors(style.get("fill", "#000000"), refs, current_color, css, seen, style, "fill"))
            colors.extend(_pattern_paint_colors(style.get("stroke"), refs, current_color, css, seen, style, "stroke"))
        colors.extend(_pattern_child_colors(child, refs, current_color, css, style, ancestors + (child,), seen))
        previous_children.append(child)
    return colors


def _pattern_paint_colors(
    value: str | None,
    refs: dict[str, ET.Element],
    current_color: str | None,
    css: list[CssRule],
    seen: set[str],
    style: dict[str, str],
    channel: str,
) -> list[tuple[str, float | None]]:
    if value is None:
        return []
    value = (current_color or "black") if _is_current_color(value) else value
    ref = _url_ref(value)
    if ref is not None:
        colors = _paint_server_colors(refs.get(ref[0]), refs, current_color, css, seen)
        fallback = ref[1].strip()
        if colors:
            return colors
        if not fallback:
            return []
        color, color_alpha = _parse_color(fallback)
    else:
        color, color_alpha = _parse_color(value)
    if not color or color == "none":
        return []
    alpha = _combined_alpha(_alpha(style, channel), color_alpha)
    if alpha is not None and alpha <= 0:
        return []
    return [(color, alpha)]


def _gradient_stops(element: ET.Element, current_color: str | None = None, css: list[CssRule] | None = None) -> list[tuple[str, float | None]]:
    stops = []
    gradient_style = _computed_style(element, css or [], {}, ())
    previous_stops: list[ET.Element] = []
    for stop in element:
        if _local_name(stop.tag) != "stop":
            previous_stops.append(stop)
            continue
        style = _computed_style(stop, css or [], gradient_style, (element,), tuple(previous_stops))
        stop_color = style.get("stop-color", "black")
        if _is_current_color(stop_color):
            stop_color = style.get("color") or element.get("color") or current_color or "black"
        color, color_alpha = _parse_color(stop_color)
        if color and color != "none":
            stop_alpha = _combined_alpha(_clamped_num(stop.get("stop-opacity", style.get("stop-opacity")), 1.0), color_alpha)
            stops.append((color, stop_alpha))
        previous_stops.append(stop)
    return stops


def _parse_color(value: str | None) -> tuple[str | None, float | None]:
    if value is None:
        return None, None
    value = value.strip()
    if value == "":
        return None, None
    lower = value.lower()
    if lower == "none":
        return "none", None
    if lower in NAMED_COLORS:
        return NAMED_COLORS[lower], 0.0 if lower == "transparent" else None
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        return "#" + "".join(ch * 2 for ch in value[1:]).lower(), None
    if re.fullmatch(r"#[0-9a-fA-F]{4}", value):
        rgba = "".join(ch * 2 for ch in value[1:])
        alpha = int(rgba[6:8], 16) / 255
        return f"#{rgba[:6].lower()}", alpha
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower(), None
    if re.fullmatch(r"#[0-9a-fA-F]{8}", value):
        rgb = value[1:7]
        alpha = int(value[7:9], 16) / 255
        return f"#{rgb.lower()}", alpha
    rgb_match = re.fullmatch(r"rgba?\(([^)]+)\)", value, flags=re.I)
    if rgb_match:
        parts = [part.strip() for part in re.split(r"[,\s/]+", rgb_match.group(1)) if part.strip()]
        if len(parts) >= 3:
            try:
                rgb = tuple(_css_channel(part) for part in parts[:3])
                alpha = _css_alpha(parts[3]) if len(parts) >= 4 else None
                return _rgb_to_hex(rgb), alpha
            except ValueError:
                return None, None
    hsl_match = re.fullmatch(r"hsla?\(([^)]+)\)", value, flags=re.I)
    if hsl_match:
        parts = [part.strip() for part in re.split(r"[,\s/]+", hsl_match.group(1)) if part.strip()]
        if len(parts) >= 3:
            try:
                rgb = _hsl_to_rgb(parts[0], parts[1], parts[2])
                alpha = _css_alpha(parts[3]) if len(parts) >= 4 else None
                return _rgb_to_hex(rgb), alpha
            except ValueError:
                return None, None
    return None, None


def _is_current_color(value: str | None) -> bool:
    return value is not None and value.strip().lower() == "currentcolor"


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return None
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(value, 255)):02x}" for value in rgb)


def _css_channel(value: str) -> int:
    if value.endswith("%"):
        number = _finite_float(value[:-1])
        return round(max(0.0, min(number, 100.0)) * 2.55)
    number = _finite_float(value)
    return round(max(0.0, min(number, 255.0)))


def _css_alpha(value: str) -> float:
    if value.endswith("%"):
        return max(0.0, min(_finite_float(value[:-1]) / 100, 1.0))
    return max(0.0, min(_finite_float(value), 1.0))


def _hsl_to_rgb(hue_value: str, saturation_value: str, lightness_value: str) -> tuple[int, int, int]:
    hue = _css_hue_degrees(hue_value) % 360 / 360
    saturation = _css_alpha(saturation_value)
    lightness = _css_alpha(lightness_value)

    if saturation == 0:
        channel = round(lightness * 255)
        return channel, channel, channel

    q = lightness * (1 + saturation) if lightness < 0.5 else lightness + saturation - lightness * saturation
    p = 2 * lightness - q

    def channel(offset: float) -> int:
        t = (hue + offset) % 1
        if t < 1 / 6:
            value = p + (q - p) * 6 * t
        elif t < 1 / 2:
            value = q
        elif t < 2 / 3:
            value = p + (q - p) * (2 / 3 - t) * 6
        else:
            value = p
        return round(value * 255)

    return channel(1 / 3), channel(0), channel(-1 / 3)


def _css_hue_degrees(value: str) -> float:
    if value.endswith("turn"):
        return _finite_float(value[:-4]) * 360
    if value.endswith("rad"):
        return math.degrees(_finite_float(value[:-3]))
    if value.endswith("deg"):
        return _finite_float(value[:-3])
    return _finite_float(value)


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(value)
    return number


def _num(value: str | None, default: float) -> float:
    if value is None:
        return float(default)
    stripped = value.strip()
    if stripped.lower().startswith("calc(") and stripped.endswith(")"):
        result = _calc_length(stripped[5:-1], "x", (0.0, 0.0), allow_percent=False)
        return result if result is not None else float(default)
    function_result = _css_length_function(stripped, "x", (0.0, 0.0), allow_percent=False)
    if function_result is not None:
        return function_result
    scale = 1.0
    for suffix, unit_scale in (
        ("px", 1.0),
        ("pt", 96 / 72),
        ("pc", 16.0),
        ("in", 96.0),
        ("cm", 96 / 2.54),
        ("mm", 96 / 25.4),
        ("q", 96 / 101.6),
    ):
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            scale = unit_scale
            break
    try:
        number = float(stripped) * scale
    except ValueError:
        return float(default)
    return number if math.isfinite(number) else float(default)


def _optional_num(value: str | None) -> float | None:
    if value is None:
        return None
    return _num(value, 0)


def _length(value: str | None, default: float, axis: str, viewport: tuple[float, float]) -> float:
    if value is None:
        return float(default)
    stripped = value.strip()
    if stripped.lower().startswith("calc(") and stripped.endswith(")"):
        result = _calc_length(stripped[5:-1], axis, viewport, allow_percent=True)
        return result if result is not None else float(default)
    function_result = _css_length_function(stripped, axis, viewport, allow_percent=True)
    if function_result is not None:
        return function_result
    if stripped.endswith("%"):
        try:
            number = float(stripped[:-1]) / 100 * _percentage_basis(axis, viewport)
        except ValueError:
            return float(default)
        return number if math.isfinite(number) else float(default)
    return _num(value, default)


def _optional_length(value: str | None, axis: str, viewport: tuple[float, float]) -> float | None:
    if value is None:
        return None
    return _length(value, 0, axis, viewport)


def _percentage_basis(axis: str, viewport: tuple[float, float]) -> float:
    if axis == "x":
        return viewport[0]
    if axis == "y":
        return viewport[1]
    return math.hypot(viewport[0], viewport[1]) / math.sqrt(2)


def _calc_length(body: str, axis: str, viewport: tuple[float, float], allow_percent: bool) -> float | None:
    terms = _calc_additive_terms(body)
    if not terms:
        return None
    total = 0.0
    for sign, value in terms:
        number = _calc_product(value, axis, viewport, allow_percent)
        if number is None:
            return None
        total += sign * number
    return total if math.isfinite(total) else None


def _calc_product(body: str, axis: str, viewport: tuple[float, float], allow_percent: bool) -> float | None:
    factors = _calc_multiplicative_terms(body)
    if not factors:
        return None
    total = _calc_factor(factors[0][1], axis, viewport, allow_percent)
    if total is None:
        return None
    for operator, value in factors[1:]:
        number = _calc_factor(value, axis, viewport, allow_percent)
        if number is None:
            return None
        if operator == "*":
            total *= number
        else:
            if number == 0:
                return None
            total /= number
    return total if math.isfinite(total) else None


def _calc_factor(value: str, axis: str, viewport: tuple[float, float], allow_percent: bool) -> float | None:
    value = value.strip()
    if not value:
        return None
    if value[0] in {"+", "-"}:
        number = _calc_factor(value[1:], axis, viewport, allow_percent)
        if number is None:
            return None
        return -number if value[0] == "-" else number
    inner = _strip_enclosing_parens(value)
    if inner is not None:
        return _calc_length(inner, axis, viewport, allow_percent)
    if value.lower().startswith("calc(") and value.endswith(")"):
        return _calc_length(value[5:-1], axis, viewport, allow_percent)
    if value.endswith("%"):
        if not allow_percent:
            return None
        try:
            return _finite_float(value[:-1]) / 100 * _percentage_basis(axis, viewport)
        except ValueError:
            return None
    function_result = _css_length_function(value, axis, viewport, allow_percent)
    if function_result is not None:
        return function_result
    number = _num(value, math.nan)
    return number if math.isfinite(number) else None


def _css_length_function(value: str, axis: str, viewport: tuple[float, float], allow_percent: bool) -> float | None:
    match = re.fullmatch(r"(min|max|clamp)\((.*)\)", value.strip(), flags=re.I)
    if not match:
        return None
    name = match.group(1).lower()
    args = _css_function_args(match.group(2))
    values = [_css_length_function_arg(arg, axis, viewport, allow_percent) for arg in args]
    if any(item is None for item in values):
        return None
    numbers = [item for item in values if item is not None]
    if name == "min" and len(numbers) >= 1:
        return min(numbers)
    if name == "max" and len(numbers) >= 1:
        return max(numbers)
    if name == "clamp" and len(numbers) == 3:
        return max(numbers[0], min(numbers[1], numbers[2]))
    return None


def _css_length_function_arg(value: str, axis: str, viewport: tuple[float, float], allow_percent: bool) -> float | None:
    value = value.strip()
    if value.endswith("%") and not allow_percent:
        return None
    result = _length(value, math.nan, axis, viewport) if allow_percent else _num(value, math.nan)
    return result if math.isfinite(result) else None


def _css_function_args(body: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for char in body:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char == "," and depth == 0:
            args.append("".join(current))
            current = []
            continue
        current.append(char)
    args.append("".join(current))
    return args


def _calc_additive_terms(body: str) -> list[tuple[float, str]]:
    terms: list[tuple[float, str]] = []
    current: list[str] = []
    sign = 1.0
    depth = 0
    quote: str | None = None
    for index, char in enumerate(body):
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if (
            char in {"+", "-"}
            and depth == 0
            and not _calc_sign_is_exponent(body, index)
            and not _calc_sign_is_unary(body, index)
        ):
            if current:
                terms.append((sign, "".join(current)))
                current = []
            sign = -1.0 if char == "-" else 1.0
            continue
        current.append(char)
    if current:
        terms.append((sign, "".join(current)))
    return terms


def _calc_multiplicative_terms(body: str) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    current: list[str] = []
    operator = "*"
    depth = 0
    quote: str | None = None
    for char in body:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char in {"*", "/"} and depth == 0:
            if not current:
                return []
            terms.append((operator, "".join(current)))
            current = []
            operator = char
            continue
        current.append(char)
    if current:
        terms.append((operator, "".join(current)))
    return terms


def _calc_sign_is_exponent(body: str, index: int) -> bool:
    return index > 0 and body[index - 1] in {"e", "E"}


def _calc_sign_is_unary(body: str, index: int) -> bool:
    previous = body[:index].rstrip()
    return not previous or previous[-1] in {"(", "*", "/"}


def _strip_enclosing_parens(value: str) -> str | None:
    if not (value.startswith("(") and value.endswith(")")):
        return None
    depth = 0
    quote: str | None = None
    for index, char in enumerate(value):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(value) - 1:
                return None
    return value[1:-1] if depth == 0 else None


def _emu(px: float) -> int:
    return round(px * EMU_PER_PX)


def _px(emu: int) -> float:
    return emu / EMU_PER_PX


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _pretty_xml(element: ET.Element) -> str:
    rough = ET.tostring(element, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")
