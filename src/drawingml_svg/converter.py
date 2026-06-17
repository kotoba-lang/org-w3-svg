from __future__ import annotations

import re
import math
from dataclasses import dataclass
from typing import Iterable
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
    marker_start: str | None = None
    marker_end: str | None = None


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
    text_decoration: str | None = None
    text_anchor: str | None = None
    text_baseline: str | None = None
    rx: float | None = None
    ry: float | None = None
    image_href: str | None = None


CssDeclaration = tuple[str, bool]
CssRule = tuple[str, dict[str, CssDeclaration], tuple[int, int, int], int]


def svg_to_drawingml(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    container = ET.Element(qn(NS_P, "spTree"))
    nv_grp = ET.SubElement(container, qn(NS_P, "nvGrpSpPr"))
    ET.SubElement(nv_grp, qn(NS_P, "cNvPr"), {"id": "1", "name": "DrawingML SVG Group"})
    ET.SubElement(nv_grp, qn(NS_P, "cNvGrpSpPr"))
    ET.SubElement(nv_grp, qn(NS_P, "nvPr"))
    grp_sp_pr = ET.SubElement(container, qn(NS_P, "grpSpPr"))
    xfrm = ET.SubElement(grp_sp_pr, qn(NS_A, "xfrm"))
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "ext"), {"cx": "0", "cy": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chOff"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chExt"), {"cx": "0", "cy": "0"})

    for index, shape in enumerate(_svg_shapes(root), start=2):
        container.append(_shape_to_dml(shape, index))

    return _pretty_xml(container)


def drawingml_to_svg(drawingml_text: str) -> str:
    root = ET.fromstring(drawingml_text)
    shapes = list(_dml_shapes(root))
    width = max((shape.x + shape.width for shape in shapes), default=0.0)
    height = max((shape.y + shape.height for shape in shapes), default=0.0)
    svg = ET.Element(
        qn(NS_SVG, "svg"),
        {
            "viewBox": f"0 0 {_fmt(width)} {_fmt(height)}",
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
    yield from _svg_shapes_walk(root, css, refs, {}, _root_viewbox_matrix(root), set(), (), _viewport_size(root))


def _svg_shapes_walk(
    element: ET.Element,
    css: list[CssRule],
    refs: dict[str, ET.Element],
    inherited_style: dict[str, str],
    inherited_matrix: tuple[float, float, float, float, float, float],
    ref_stack: set[str],
    ancestors: tuple[ET.Element, ...],
    viewport: tuple[float, float],
) -> Iterable[Shape]:
    tag = _local_name(element.tag)
    if tag in {"defs", "style"}:
        return

    style = _computed_style(element, css, inherited_style, ancestors)
    if _is_hidden(style):
        return
    matrix = _matrix_multiply(inherited_matrix, _parse_transform(element.get("transform", "")))
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
                    _viewbox_matrix(ref, use_width, use_height),
                )
                ref_viewport = _viewport_size(ref, use_width, use_height)
            yield from _svg_shapes_walk(ref, css, refs, style, use_matrix, ref_stack | {href[1:]}, ancestors + (element,), ref_viewport)
        return

    shape = _svg_shape_from_element(element, tag, style, matrix, refs, viewport)
    if shape is not None:
        shape = _apply_rect_clip(shape, style, refs, matrix)
    if shape is not None:
        yield shape

    for child in element:
        yield from _svg_shapes_walk(child, css, refs, style, matrix, ref_stack, ancestors + (element,), child_viewport)


def _svg_shape_from_element(
    element: ET.Element,
    tag: str,
    style: dict[str, str],
    matrix: tuple[float, float, float, float, float, float],
    refs: dict[str, ET.Element] | None = None,
    viewport: tuple[float, float] = (0.0, 0.0),
) -> Shape | None:
    refs = refs or {}
    paint = _svg_paint(style, refs, default_fill=tag != "line")
    plain_paint = _paint_without_markers(paint)
    if tag == "rect":
        x = _length(element.get("x"), 0, "x", viewport)
        y = _length(element.get("y"), 0, "y", viewport)
        width = _length(element.get("width"), 0, "x", viewport)
        height = _length(element.get("height"), 0, "y", viewport)
        rx = _length(element.get("rx"), _length(element.get("ry"), 0, "y", viewport), "x", viewport)
        ry = _length(element.get("ry"), rx, "y", viewport)
        if _is_identity_matrix(matrix):
            return Shape("roundRect" if rx or ry else "rect", x, y, width, height, plain_paint, rx=rx or None, ry=ry or None)
        points = _transform_points(_rect_points(x, y, width, height), matrix)
        return _freeform_shape(points, plain_paint, closed=True)
    if tag == "circle":
        cx = _length(element.get("cx"), 0, "x", viewport)
        cy = _length(element.get("cy"), 0, "y", viewport)
        r = _length(element.get("r"), 0, "diag", viewport)
        return _ellipse_shape(cx, cy, r, r, plain_paint, matrix)
    if tag == "ellipse":
        cx = _length(element.get("cx"), 0, "x", viewport)
        cy = _length(element.get("cy"), 0, "y", viewport)
        rx = _length(element.get("rx"), 0, "x", viewport)
        ry = _length(element.get("ry"), 0, "y", viewport)
        return _ellipse_shape(cx, cy, rx, ry, plain_paint, matrix)
    if tag == "line":
        p1 = _apply_matrix(matrix, (_length(element.get("x1"), 0, "x", viewport), _length(element.get("y1"), 0, "y", viewport)))
        p2 = _apply_matrix(matrix, (_length(element.get("x2"), 0, "x", viewport), _length(element.get("y2"), 0, "y", viewport)))
        if _is_identity_matrix(matrix):
            return Shape(
                "line",
                min(p1[0], p2[0]),
                min(p1[1], p2[1]),
                abs(p2[0] - p1[0]),
                abs(p2[1] - p1[1]),
                paint,
                flip_h=p2[0] < p1[0],
                flip_v=p2[1] < p1[1],
            )
        return _freeform_shape([p1, p2], paint, closed=False)
    if tag in {"polygon", "polyline"}:
        points = _transform_points(_parse_points(element.get("points", "")), matrix)
        return _freeform_shape(points, plain_paint if tag == "polygon" else paint, closed=tag == "polygon") if points else None
    if tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        if path:
            points, closed = path
            return _freeform_shape(_transform_points(points, matrix), plain_paint if closed else paint, closed=closed)
    if tag == "text":
        text = _svg_text_content(element)
        if text:
            font_size = _num(style.get("font-size"), 16) * _matrix_scale(matrix)
            x, y = _apply_matrix(matrix, _svg_text_position(element, viewport))
            width = max(font_size * max(len(line) for line in text.split("\n")) * 0.9, font_size * 2)
            anchor = style.get("text-anchor")
            if anchor == "middle":
                x -= width / 2
            elif anchor == "end":
                x -= width
            baseline = _dominant_baseline(style.get("dominant-baseline"))
            height = font_size * 1.4 * len(text.split("\n"))
            if baseline == "middle":
                y -= height / 2
            elif baseline == "text-after-edge":
                y -= height
            else:
                y -= font_size
            return Shape(
                "text",
                x,
                y,
                width,
                height,
                _text_paint(style, refs),
                text=text,
                font_size=font_size,
                font_weight=style.get("font-weight"),
                font_style=style.get("font-style"),
                font_family=_font_family(style.get("font-family")),
                text_decoration=style.get("text-decoration"),
                text_anchor=anchor,
                text_baseline=baseline,
            )
    if tag == "image":
        href = _href(element)
        if href and _supported_data_image(href):
            x = _length(element.get("x"), 0, "x", viewport)
            y = _length(element.get("y"), 0, "y", viewport)
            width = _length(element.get("width"), 0, "x", viewport)
            height = _length(element.get("height"), 0, "y", viewport)
            points = _transform_points(_rect_points(x, y, width, height), matrix)
            min_x = min(px for px, _ in points)
            min_y = min(py for _, py in points)
            max_x = max(px for px, _ in points)
            max_y = max(py for _, py in points)
            return Shape("image", min_x, min_y, max_x - min_x, max_y - min_y, Paint(), image_href=href)
    return None


def _dml_shapes(root: ET.Element) -> Iterable[Shape]:
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag == "pic":
            image = _dml_picture_shape(element)
            if image is not None:
                yield image
            continue
        if tag not in {"sp", "cxnSp"}:
            continue
        sp_pr = element.find(qn(NS_P, "spPr"))
        if sp_pr is None:
            sp_pr = element.find(qn(NS_A, "spPr"))
        if sp_pr is None:
            continue
        text = _dml_text(element)
        if text is not None:
            xfrm = sp_pr.find(qn(NS_A, "xfrm"))
            x, y, width, height, flip_h, flip_v = _dml_xfrm(xfrm)
            yield Shape(
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
                text_decoration=_dml_text_decoration(element),
                text_anchor=_dml_text_anchor(element),
                text_baseline=_dml_text_baseline(element),
            )
            continue
        cust = sp_pr.find(qn(NS_A, "custGeom"))
        if cust is not None:
            xfrm = sp_pr.find(qn(NS_A, "xfrm"))
            x, y, width, height, flip_h, flip_v = _dml_xfrm(xfrm)
            points, closed = _dml_custom_points(cust, x, y)
            if points:
                yield Shape("freeform", x, y, width, height, _dml_paint(sp_pr), flip_h, flip_v, tuple(points), closed)
            continue
        prst = sp_pr.find(qn(NS_A, "prstGeom"))
        if prst is None:
            continue
        kind = _dml_kind_to_shape(prst.get("prst", ""))
        if kind is None:
            continue
        xfrm = sp_pr.find(qn(NS_A, "xfrm"))
        x, y, width, height, flip_h, flip_v = _dml_xfrm(xfrm)
        radius = min(width, height) / 6 if kind == "roundRect" else None
        yield Shape(kind, x, y, width, height, _dml_paint(sp_pr), flip_h, flip_v, rx=radius, ry=radius)


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
        return ET.Element(
            qn(NS_SVG, "image"),
            {
                "href": shape.image_href or "",
                "x": _fmt(shape.x),
                "y": _fmt(shape.y),
                "width": _fmt(shape.width),
                "height": _fmt(shape.height),
            },
        )
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
        return ET.Element(qn(NS_SVG, "ellipse"), attrs)
    if shape.kind == "line":
        attrs.update(_line_points(shape))
        attrs.setdefault("fill", "none")
        return ET.Element(qn(NS_SVG, "line"), attrs)
    if shape.kind == "freeform":
        attrs["points"] = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in shape.points)
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
        if shape.text_decoration:
            attrs["text-decoration"] = shape.text_decoration
        if shape.text_anchor:
            attrs["text-anchor"] = shape.text_anchor
        if shape.text_baseline:
            attrs["dominant-baseline"] = shape.text_baseline
        element = ET.Element(qn(NS_SVG, "text"), attrs)
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


def _image_to_dml(shape: Shape, shape_id: int) -> ET.Element:
    pic = ET.Element(qn(NS_P, "pic"))
    nv_pic_pr = ET.SubElement(pic, qn(NS_P, "nvPicPr"))
    ET.SubElement(nv_pic_pr, qn(NS_P, "cNvPr"), {"id": str(shape_id), "name": "image"})
    ET.SubElement(nv_pic_pr, qn(NS_P, "cNvPicPr"))
    ET.SubElement(nv_pic_pr, qn(NS_P, "nvPr"))
    blip_fill = ET.SubElement(pic, qn(NS_P, "blipFill"))
    ET.SubElement(blip_fill, qn(NS_A, "blip"), {qn(NS_R, "embed"): shape.image_href or ""})
    stretch = ET.SubElement(blip_fill, qn(NS_A, "stretch"))
    ET.SubElement(stretch, qn(NS_A, "fillRect"))
    sp_pr = ET.SubElement(pic, qn(NS_P, "spPr"))
    xfrm = ET.SubElement(sp_pr, qn(NS_A, "xfrm"))
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
    x, y, width, height, flip_h, flip_v = _dml_xfrm(sp_pr.find(qn(NS_A, "xfrm")))
    return Shape("image", x, y, width, height, Paint(), flip_h, flip_v, image_href=href)


def _append_svg_marker_defs(svg: ET.Element, shapes: list[Shape]) -> None:
    if not any(shape.paint.marker_start or shape.paint.marker_end for shape in shapes):
        return
    defs = ET.SubElement(svg, qn(NS_SVG, "defs"))
    marker = ET.SubElement(
        defs,
        qn(NS_SVG, "marker"),
        {
            "id": "drawingml-svg-arrow",
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


def _svg_paint(style: dict[str, str], refs: dict[str, ET.Element] | None = None, default_fill: bool = True) -> Paint:
    refs = refs or {}
    fill, fill_color_alpha = _paint_value(style.get("fill"), refs, style.get("color"))
    stroke, stroke_color_alpha = _paint_value(style.get("stroke"), refs, style.get("color"))
    if fill is None:
        fill = "#000000" if default_fill else "none"
    if stroke is None:
        stroke = "none"
    stroke_width = style.get("stroke-width")
    parsed_stroke_width = _num(stroke_width, 1) if stroke_width not in {None, "", "none"} else None
    if parsed_stroke_width is not None and parsed_stroke_width <= 0:
        stroke = "none"
    fill_alpha = _combined_alpha(_alpha(style, "fill"), fill_color_alpha)
    stroke_alpha = _combined_alpha(_alpha(style, "stroke"), stroke_color_alpha)
    if fill_alpha is not None and fill_alpha <= 0:
        fill = "none"
    if stroke_alpha is not None and stroke_alpha <= 0:
        stroke = "none"
    if stroke not in {None, "none"} and parsed_stroke_width is None:
        parsed_stroke_width = 1.0
    stroke_linecap = style.get("stroke-linecap")
    if stroke not in {None, "none"} and not stroke_linecap:
        stroke_linecap = "butt"
    stroke_linejoin = style.get("stroke-linejoin")
    if stroke not in {None, "none"} and not stroke_linejoin:
        stroke_linejoin = "miter"
    stroke_miterlimit = _optional_num(style.get("stroke-miterlimit"))
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
        stroke_dasharray=style.get("stroke-dasharray"),
        stroke_miterlimit=stroke_miterlimit,
        marker_start=_svg_marker_value(style.get("marker-start"), refs),
        marker_end=_svg_marker_value(style.get("marker-end"), refs),
    )


def _paint_without_markers(paint: Paint) -> Paint:
    return Paint(
        paint.fill,
        paint.stroke,
        paint.stroke_width,
        paint.fill_alpha,
        paint.stroke_alpha,
        paint.stroke_linecap,
        paint.stroke_linejoin,
        paint.stroke_dasharray,
        paint.stroke_miterlimit,
    )


def _svg_marker_value(value: str | None, refs: dict[str, ET.Element]) -> str | None:
    if not value or value == "none":
        return None
    match = re.fullmatch(r"url\((?:['\"])?#([^'\")]+)(?:['\"])?\)", value.strip())
    if not match:
        return None
    marker_id = match.group(1)
    marker = refs.get(marker_id)
    if marker is None or _local_name(marker.tag) != "marker":
        return None
    return marker_id


def _text_paint(style: dict[str, str], refs: dict[str, ET.Element]) -> Paint:
    fill, color_alpha = _paint_value(style.get("fill"), refs, style.get("color"))
    return Paint(fill=fill or "#000000", fill_alpha=_combined_alpha(_alpha(style, "fill"), color_alpha))


def _font_family(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    return first.strip("\"'") or None


def _dml_paint(sp_pr: ET.Element) -> Paint:
    fill = None
    solid_fill = sp_pr.find(qn(NS_A, "solidFill"))
    no_fill = sp_pr.find(qn(NS_A, "noFill"))
    if solid_fill is not None:
        fill = _dml_color(solid_fill)
        fill_alpha = _dml_alpha(solid_fill)
    elif no_fill is not None:
        fill = "none"
        fill_alpha = None
    else:
        fill_alpha = None

    stroke = None
    stroke_width = None
    stroke_alpha = None
    stroke_linecap = None
    stroke_linejoin = None
    stroke_dasharray = None
    stroke_miterlimit = None
    marker_start = None
    marker_end = None
    ln = sp_pr.find(qn(NS_A, "ln"))
    if ln is not None:
        stroke_width = _px(int(ln.get("w", "0"))) if ln.get("w") else None
        stroke_linecap = _dml_linecap(ln.get("cap"))
        stroke_linejoin = _dml_linejoin(ln)
        stroke_dasharray = _dml_dasharray(ln)
        stroke_miterlimit = _dml_miterlimit(ln)
        marker_start = _dml_line_arrow(ln.find(qn(NS_A, "tailEnd")))
        marker_end = _dml_line_arrow(ln.find(qn(NS_A, "headEnd")))
        no_line = ln.find(qn(NS_A, "noFill"))
        solid_line = ln.find(qn(NS_A, "solidFill"))
        if no_line is not None:
            stroke = "none"
        elif solid_line is not None:
            stroke = _dml_color(solid_line)
            stroke_alpha = _dml_alpha(solid_line)
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


def _dml_text_paint(element: ET.Element, sp_pr: ET.Element) -> Paint:
    r_pr = element.find(f".//{qn(NS_A, 'rPr')}")
    solid_fill = r_pr.find(qn(NS_A, "solidFill")) if r_pr is not None else None
    if solid_fill is not None:
        return Paint(fill=_dml_color(solid_fill), fill_alpha=_dml_alpha(solid_fill))
    return _dml_paint(sp_pr)


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
    paragraph_align = _text_anchor_to_dml(shape.text_anchor)
    if paragraph_align:
        ET.SubElement(paragraph, qn(NS_A, "pPr"), {"algn": paragraph_align})
    run = ET.SubElement(paragraph, qn(NS_A, "r"))
    r_pr_attrs = {}
    if shape.font_size:
        r_pr_attrs["sz"] = str(round(shape.font_size * 100))
    if _is_bold(shape.font_weight):
        r_pr_attrs["b"] = "1"
    if _is_italic(shape.font_style):
        r_pr_attrs["i"] = "1"
    if _has_text_decoration(shape.text_decoration, "underline"):
        r_pr_attrs["u"] = "sng"
    if _has_text_decoration(shape.text_decoration, "line-through"):
        r_pr_attrs["strike"] = "sngStrike"
    r_pr = ET.SubElement(run, qn(NS_A, "rPr"), r_pr_attrs)
    _append_text_run_properties(r_pr, shape)
    lines = (shape.text or "").split("\n")
    ET.SubElement(run, qn(NS_A, "t")).text = lines[0] if lines else ""
    for line in lines[1:]:
        ET.SubElement(paragraph, qn(NS_A, "br"))
        br_run = ET.SubElement(paragraph, qn(NS_A, "r"))
        br_r_pr = ET.SubElement(br_run, qn(NS_A, "rPr"), r_pr_attrs)
        _append_text_run_properties(br_r_pr, shape)
        ET.SubElement(br_run, qn(NS_A, "t")).text = line
    ET.SubElement(paragraph, qn(NS_A, "endParaRPr"))


def _append_text_run_properties(r_pr: ET.Element, shape: Shape) -> None:
    if shape.paint.fill and shape.paint.fill != "none":
        fill = ET.SubElement(r_pr, qn(NS_A, "solidFill"))
        color = ET.SubElement(fill, qn(NS_A, "srgbClr"), {"val": shape.paint.fill.removeprefix("#").upper()})
        _append_alpha(color, shape.paint.fill_alpha)
    if shape.font_family:
        ET.SubElement(r_pr, qn(NS_A, "latin"), {"typeface": shape.font_family})


def _dml_color(parent: ET.Element) -> str | None:
    srgb = parent.find(qn(NS_A, "srgbClr"))
    if srgb is not None and srgb.get("val"):
        return f"#{srgb.get('val', '').lower()}"
    scheme = parent.find(qn(NS_A, "schemeClr"))
    if scheme is not None and scheme.get("val"):
        return scheme.get("val")
    return None


def _dml_alpha(parent: ET.Element) -> float | None:
    alpha = parent.find(f".//{qn(NS_A, 'alpha')}")
    if alpha is not None and alpha.get("val"):
        return int(alpha.get("val", "100000")) / 100000
    return None


def _append_alpha(color: ET.Element, alpha: float | None) -> None:
    if alpha is None or alpha >= 1:
        return
    ET.SubElement(color, qn(NS_A, "alpha"), {"val": str(round(max(0.0, min(alpha, 1.0)) * 100000))})


def _svg_linecap_to_dml(value: str) -> str:
    return {"butt": "flat", "round": "rnd", "square": "sq"}.get(value, "flat")


def _dml_linecap(value: str | None) -> str | None:
    return {"flat": "butt", "rnd": "round", "sq": "square"}.get(value or "")


def _append_dml_arrow(ln: ET.Element, tag: str, value: str | None) -> None:
    if value:
        ET.SubElement(ln, qn(NS_A, tag), {"type": "triangle"})


def _dml_line_arrow(element: ET.Element | None) -> str | None:
    if element is not None and element.get("type") not in {None, "none"}:
        return "drawingml-svg-arrow"
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
    return int(miter.get("lim", "0")) / 100000


def _append_dml_dash(ln: ET.Element, value: str | None, stroke_width: float | None = None) -> None:
    if not value or value == "none":
        return
    nums = _svg_dasharray_numbers(value)
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


def _svg_dasharray_numbers(value: str) -> list[float] | None:
    parts = [part for part in re.split(r"[\s,]+", value.strip()) if part]
    if not parts:
        return None
    nums = []
    for part in parts:
        number = _num(part, math.nan)
        if math.isnan(number):
            return None
        nums.append(number)
    return nums


def _svg_dasharray_to_dml(value: str) -> str | None:
    nums = _svg_dasharray_numbers(value)
    if not nums:
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
        width = _px(int(ln.get("w", "0"))) if ln.get("w") else None
        if width:
            values = []
            for item in custom.findall(qn(NS_A, "ds")):
                values.append(_fmt(int(item.get("d", "0")) / 100000 * width))
                values.append(_fmt(int(item.get("sp", "0")) / 100000 * width))
            return " ".join(values) or None
    dash = ln.find(qn(NS_A, "prstDash"))
    if dash is None:
        return None
    return {"dot": "1 3", "dash": "4 3", "lgDash": "8 3"}.get(dash.get("val", ""))


def _dml_text(element: ET.Element) -> str | None:
    tx_body = element.find(qn(NS_P, "txBody"))
    if tx_body is None:
        return None
    parts = []
    paragraph = tx_body.find(qn(NS_A, "p"))
    if paragraph is None:
        return ""
    for node in paragraph:
        if node.tag == qn(NS_A, "br"):
            parts.append("\n")
        else:
            text_node = node.find(qn(NS_A, "t"))
            if text_node is not None:
                parts.append(text_node.text or "")
    text = "".join(parts)
    return text if text else ""


def _dml_font_weight(element: ET.Element) -> str | None:
    r_pr = element.find(f".//{qn(NS_A, 'rPr')}")
    if r_pr is not None and r_pr.get("b") in {"1", "true"}:
        return "bold"
    return None


def _dml_font_size(element: ET.Element) -> float | None:
    r_pr = element.find(f".//{qn(NS_A, 'rPr')}")
    if r_pr is not None and r_pr.get("sz"):
        try:
            return int(r_pr.get("sz", "0")) / 100
        except ValueError:
            return None
    return None


def _dml_font_style(element: ET.Element) -> str | None:
    r_pr = element.find(f".//{qn(NS_A, 'rPr')}")
    if r_pr is not None and r_pr.get("i") in {"1", "true"}:
        return "italic"
    return None


def _dml_font_family(element: ET.Element) -> str | None:
    latin = element.find(f".//{qn(NS_A, 'rPr')}/{qn(NS_A, 'latin')}")
    if latin is not None:
        return latin.get("typeface")
    return None


def _dml_text_decoration(element: ET.Element) -> str | None:
    r_pr = element.find(f".//{qn(NS_A, 'rPr')}")
    if r_pr is None:
        return None
    values = []
    if r_pr.get("u") and r_pr.get("u") != "none":
        values.append("underline")
    if r_pr.get("strike") and r_pr.get("strike") != "noStrike":
        values.append("line-through")
    return " ".join(values) or None


def _dml_text_anchor(element: ET.Element) -> str | None:
    p_pr = element.find(f".//{qn(NS_A, 'pPr')}")
    if p_pr is None:
        return None
    return {"ctr": "middle", "r": "end", "l": "start"}.get(p_pr.get("algn", ""))


def _text_anchor_to_dml(value: str | None) -> str | None:
    return {"middle": "ctr", "end": "r", "start": "l"}.get(value or "")


def _dml_text_baseline(element: ET.Element) -> str | None:
    body_pr = element.find(f".//{qn(NS_A, 'bodyPr')}")
    if body_pr is None:
        return None
    return {"ctr": "middle", "b": "text-after-edge", "t": "text-before-edge"}.get(body_pr.get("anchor", ""))


def _text_baseline_to_dml(value: str | None) -> str | None:
    return {"middle": "ctr", "central": "ctr", "text-after-edge": "b", "text-before-edge": "t", "hanging": "t"}.get(value or "")


def _dominant_baseline(value: str | None) -> str | None:
    if value in {"middle", "central"}:
        return "middle"
    if value in {"text-after-edge", "ideographic"}:
        return "text-after-edge"
    if value in {"text-before-edge", "hanging"}:
        return "text-before-edge"
    return None


def _svg_text_content(element: ET.Element) -> str:
    if not any(_local_name(child.tag) == "tspan" for child in element):
        return "".join(element.itertext()).strip()
    lines = []
    leading = (element.text or "").strip()
    if leading:
        lines.append(leading)
    for child in element:
        if _local_name(child.tag) == "tspan":
            text = "".join(child.itertext()).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def _svg_text_position(element: ET.Element, viewport: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    x = _optional_length(element.get("x"), "x", viewport)
    y = _optional_length(element.get("y"), "y", viewport)
    if x is not None and y is not None:
        return x, y
    for child in element:
        if _local_name(child.tag) != "tspan":
            continue
        if x is None:
            x = _optional_length(child.get("x"), "x", viewport)
        if y is None:
            y = _optional_length(child.get("y"), "y", viewport)
        if x is not None and y is not None:
            break
    return x or 0.0, y or 0.0


def _is_bold(value: str | None) -> bool:
    if value is None:
        return False
    if value.lower() == "bold":
        return True
    try:
        return int(value) >= 600
    except ValueError:
        return False


def _is_italic(value: str | None) -> bool:
    return value is not None and value.lower() in {"italic", "oblique"}


def _has_text_decoration(value: str | None, decoration: str) -> bool:
    if value is None:
        return False
    return decoration in {part.lower() for part in re.split(r"\s+", value.strip())}


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
            if pt is not None:
                points.append((x + _px(int(pt.get("x", "0"))), y + _px(int(pt.get("y", "0")))))
        elif tag == "close":
            closed = True
    return points, closed


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


def _dml_xfrm(xfrm: ET.Element | None) -> tuple[float, float, float, float, bool, bool]:
    if xfrm is None:
        return 0.0, 0.0, 0.0, 0.0, False, False
    off = xfrm.find(qn(NS_A, "off"))
    ext = xfrm.find(qn(NS_A, "ext"))
    x = _px(int(off.get("x", "0"))) if off is not None else 0.0
    y = _px(int(off.get("y", "0"))) if off is not None else 0.0
    width = _px(int(ext.get("cx", "0"))) if ext is not None else 0.0
    height = _px(int(ext.get("cy", "0"))) if ext is not None else 0.0
    return x, y, width, height, xfrm.get("flipH") in {"1", "true"}, xfrm.get("flipV") in {"1", "true"}


def _shape_kind_to_dml(kind: str) -> str:
    return {"rect": "rect", "roundRect": "roundRect", "ellipse": "ellipse", "line": "line", "text": "rect"}[kind]


def _dml_kind_to_shape(kind: str) -> str | None:
    return {"rect": "rect", "roundRect": "roundRect", "ellipse": "ellipse", "line": "line"}.get(kind)


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
    if len(numbers) < 4:
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
    for item in style.split(";"):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        key = key.strip()
        normalized, important = _normalize_css_value_with_importance(value)
        if key not in result or important or not result[key][1]:
            result[key] = (normalized, important)
    return result


def _normalize_css_value(value: str) -> str:
    return _normalize_css_value_with_importance(value)[0]


def _normalize_css_value_with_importance(value: str) -> CssDeclaration:
    stripped = value.strip()
    important = bool(re.search(r"\s*!important\s*$", stripped, flags=re.I))
    if important:
        stripped = re.sub(r"\s*!important\s*$", "", stripped, flags=re.I).strip()
    return stripped, important


def _collect_css(root: ET.Element) -> list[CssRule]:
    css: list[CssRule] = []
    order = 0
    for element in root.iter():
        if _local_name(element.tag) != "style":
            continue
        text = "".join(element.itertext())
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]+)\}", text):
            declarations = _parse_style_declarations(body)
            for item in selector.split(","):
                key = item.strip()
                if key:
                    css.append((key, declarations, _selector_specificity(key), order))
                    order += 1
    return css


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
    align, meet_or_slice = _preserve_aspect_ratio(element.get("preserveAspectRatio"))
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
    if parts and parts[0] == "defer":
        parts = parts[1:]
    align = parts[0] if parts else "xMidYMid"
    if align == "none":
        return "none", "meet"
    if not re.fullmatch(r"x(?:Min|Mid|Max)Y(?:Min|Mid|Max)", align):
        align = "xMidYMid"
    meet_or_slice = parts[1] if len(parts) > 1 and parts[1] in {"meet", "slice"} else "meet"
    return align, meet_or_slice


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
) -> dict[str, str]:
    style = dict(inherited)
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
        "stroke-width",
        "stroke-dasharray",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "font-size",
        "font-family",
        "font-weight",
        "font-style",
        "text-decoration",
        "text-anchor",
        "dominant-baseline",
        "color",
        "display",
        "visibility",
        "clip-path",
        "marker-start",
        "marker-mid",
        "marker-end",
    ):
        if element.get(attr) is not None:
            apply_declaration(attr, element.get(attr, ""), False, (0, 0, 0, 0), -1)

    for selector, declarations, specificity, order in css:
        if _selector_matches(selector, element, ancestors):
            css_specificity = (0, *specificity)
            for key, (value, important) in declarations.items():
                apply_declaration(key, value, important, css_specificity, order)

    for key, (value, important) in _parse_style_declarations(element.get("style", "")).items():
        apply_declaration(key, value, important, (1, 0, 0, 0), 1_000_000)
    if style.get("fill") == "currentColor":
        style["fill"] = style.get("color", "#000000")
    if style.get("stroke") == "currentColor":
        style["stroke"] = style.get("color", "#000000")
    return style


def _is_hidden(style: dict[str, str]) -> bool:
    return style.get("display") == "none" or style.get("visibility") in {"hidden", "collapse"}


def _apply_rect_clip(
    shape: Shape,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
) -> Shape | None:
    if shape.kind not in {"rect", "roundRect", "text"}:
        return shape
    clip_bounds = _rect_clip_bounds(shape, style, refs, matrix)
    if clip_bounds is None:
        return shape
    clip_x, clip_y, clip_width, clip_height = clip_bounds
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
        text_decoration=shape.text_decoration,
        text_anchor=shape.text_anchor,
        text_baseline=shape.text_baseline,
        rx=min(shape.rx or 0, (x2 - x1) / 2) if shape.rx is not None else None,
        ry=min(shape.ry or 0, (y2 - y1) / 2) if shape.ry is not None else None,
    )


def _rect_clip_bounds(
    shape: Shape | None,
    style: dict[str, str],
    refs: dict[str, ET.Element],
    matrix: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float] | None:
    clip_path = style.get("clip-path")
    if not clip_path or clip_path == "none":
        return None
    match = re.fullmatch(r"url\((?:['\"])?#([^'\")]+)(?:['\"])?\)", clip_path.strip())
    if not match:
        return None
    clip = refs.get(match.group(1))
    if clip is None or _local_name(clip.tag) != "clipPath":
        return None
    units = clip.get("clipPathUnits", "userSpaceOnUse")
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
    if _local_name(element.tag) not in {"rect", "text"}:
        return False
    return _rect_clip_bounds(None, style, refs, matrix) is not None or _rect_clip_path_has_object_bbox_rect(style, refs)


def _rect_clip_path_has_object_bbox_rect(style: dict[str, str], refs: dict[str, ET.Element]) -> bool:
    clip_path = style.get("clip-path")
    if not clip_path or clip_path == "none":
        return False
    match = re.fullmatch(r"url\((?:['\"])?#([^'\")]+)(?:['\"])?\)", clip_path.strip())
    if not match:
        return False
    clip = refs.get(match.group(1))
    if clip is None or _local_name(clip.tag) != "clipPath" or clip.get("clipPathUnits") != "objectBoundingBox":
        return False
    if clip.get("transform") is not None:
        return False
    rect = next((child for child in clip if _local_name(child.tag) == "rect"), None)
    return rect is not None and rect.get("transform") is None and _num(rect.get("width"), 0) > 0 and _num(rect.get("height"), 0) > 0


def _marker_is_supported(element: ET.Element, style: dict[str, str], refs: dict[str, ET.Element]) -> bool:
    marker_values = [style.get("marker-start"), style.get("marker-end")]
    if not any(value and value != "none" for value in marker_values):
        return True
    tag = _local_name(element.tag)
    if tag == "line":
        return all(_svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none")
    if tag == "polyline":
        return all(_svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none")
    if tag == "path":
        path = _parse_linear_path(element.get("d", ""))
        return bool(path and not path[1]) and all(_svg_marker_value(value, refs) is not None for value in marker_values if value and value != "none")
    return False


def _selector_matches(selector: str, element: ET.Element, ancestors: tuple[ET.Element, ...]) -> bool:
    parts = re.findall(r">|[^ >]+", selector.strip())
    if not parts or parts[-1] == ">":
        return False
    if not _simple_selector_matches(parts[-1], element):
        return False

    ancestor_index = len(ancestors) - 1
    require_direct = False
    index = len(parts) - 2
    while index >= 0:
        part = parts[index]
        if part == ">":
            require_direct = True
            index -= 1
            continue
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
    selector_without_attrs = _selector_without_attribute_selectors(selector)
    if any(mark in selector_without_attrs for mark in ("+", "~", ":")):
        return (0, 0, 0)
    id_count = len(re.findall(r"#[A-Za-z_][\w:-]*", selector))
    class_count = len(re.findall(r"\.[A-Za-z_][\w:-]*", selector)) + len(re.findall(r"\[[^\]]+\]", selector))
    element_count = 0
    for part in re.findall(r"[^ >]+", selector.strip()):
        if part == "*":
            continue
        first_modifier = min([index for index in (part.find("."), part.find("#"), part.find("[")) if index >= 0], default=-1)
        tag = part[:first_modifier] if first_modifier > 0 else ("" if first_modifier == 0 else part)
        if tag and re.fullmatch(r"[A-Za-z_][\w:-]*", tag):
            element_count += 1
    return id_count, class_count, element_count


def _simple_selector_matches(selector: str, element: ET.Element) -> bool:
    selector = selector.strip()
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


def _attribute_selector_matches(selector: str, element: ET.Element) -> bool:
    match = re.fullmatch(
        r"\s*([A-Za-z_][\w:-]*)(?:\s*([~|^$*]?=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"']+)))?\s*",
        selector,
    )
    if not match:
        return False
    name = match.group(1)
    operator = match.group(2)
    expected = next((group for group in match.groups()[2:] if group is not None), None)
    actual = _attribute_value(element, name)
    if actual is None:
        return False
    if expected is None:
        return operator is None
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


def _supported_data_image(value: str) -> bool:
    return bool(re.match(r"^data:image/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", value, flags=re.I))


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
    return max(0.0, min(_num(value, default), 1.0))


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
    for name, raw_args in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", value):
        args = [float(item) for item in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", raw_args)]
        item = _identity_matrix()
        if name == "matrix" and len(args) >= 6:
            item = tuple(args[:6])  # type: ignore[assignment]
        elif name == "translate":
            item = (1.0, 0.0, 0.0, 1.0, args[0] if args else 0.0, args[1] if len(args) > 1 else 0.0)
        elif name == "scale":
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            item = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate":
            angle = math.radians(args[0] if args else 0.0)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            rotation = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                item = _matrix_multiply(
                    _matrix_multiply((1.0, 0.0, 0.0, 1.0, cx, cy), rotation),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
            else:
                item = rotation
        elif name == "skewX" and args:
            item = (1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and args:
            item = (1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
        matrix = _matrix_multiply(matrix, item)
    return matrix


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
    if _is_identity_matrix(matrix):
        return Shape("ellipse", cx - rx, cy - ry, rx * 2, ry * 2, paint)
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


def _paint_value(value: str | None, refs: dict[str, ET.Element], current_color: str | None = None) -> tuple[str | None, float | None]:
    if value is None:
        return None, None
    stripped = value.strip()
    match = re.match(r"^url\((?:['\"])?#([^'\")]+)(?:['\"])?\)(.*)$", stripped)
    if match:
        color, alpha = _paint_server_value(refs.get(match.group(1)), refs, current_color)
        if color:
            return color, alpha
        fallback = match.group(2).strip()
        if fallback:
            return _parse_color(fallback)
        return None, None
    return _parse_color(stripped)


def _paint_server_value(element: ET.Element | None, refs: dict[str, ET.Element], current_color: str | None = None) -> tuple[str | None, float | None]:
    if element is None:
        return None, None
    tag = _local_name(element.tag)
    if tag not in {"linearGradient", "radialGradient"}:
        return None, None
    inherited_colors: list[tuple[str, float | None]] = []
    href = _href(element)
    if href and href.startswith("#"):
        color, alpha = _paint_server_value(refs.get(href[1:]), refs, current_color)
        if color:
            inherited_colors.append((color, alpha))
    colors = inherited_colors + _gradient_stops(element, current_color)
    if not colors:
        return None, None
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


def _gradient_stops(element: ET.Element, current_color: str | None = None) -> list[tuple[str, float | None]]:
    stops = []
    for stop in element:
        if _local_name(stop.tag) != "stop":
            continue
        style = _parse_style(stop.get("style", ""))
        stop_color = stop.get("stop-color", style.get("stop-color", "black"))
        if stop_color == "currentColor":
            stop_color = style.get("color") or element.get("color") or current_color or "black"
        color, color_alpha = _parse_color(stop_color)
        if color and color != "none":
            stop_alpha = _combined_alpha(_clamped_num(stop.get("stop-opacity", style.get("stop-opacity")), 1.0), color_alpha)
            stops.append((color, stop_alpha))
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
            rgb = tuple(_css_channel(part) for part in parts[:3])
            alpha = _css_alpha(parts[3]) if len(parts) >= 4 else None
            return _rgb_to_hex(rgb), alpha
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


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return None
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(value, 255)):02x}" for value in rgb)


def _css_channel(value: str) -> int:
    if value.endswith("%"):
        return round(max(0.0, min(float(value[:-1]), 100.0)) * 2.55)
    return round(max(0.0, min(float(value), 255.0)))


def _css_alpha(value: str) -> float:
    if value.endswith("%"):
        return max(0.0, min(float(value[:-1]) / 100, 1.0))
    return max(0.0, min(float(value), 1.0))


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
        return float(value[:-4]) * 360
    if value.endswith("rad"):
        return math.degrees(float(value[:-3]))
    if value.endswith("deg"):
        return float(value[:-3])
    return float(value)


def _num(value: str | None, default: float) -> float:
    if value is None:
        return float(default)
    stripped = value.strip()
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
        return float(stripped) * scale
    except ValueError:
        return float(default)


def _optional_num(value: str | None) -> float | None:
    if value is None:
        return None
    return _num(value, 0)


def _length(value: str | None, default: float, axis: str, viewport: tuple[float, float]) -> float:
    if value is None:
        return float(default)
    stripped = value.strip()
    if stripped.endswith("%"):
        try:
            return float(stripped[:-1]) / 100 * _percentage_basis(axis, viewport)
        except ValueError:
            return float(default)
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
