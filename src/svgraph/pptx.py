from __future__ import annotations

import base64
import binascii
import io
import json
import re
import zipfile
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

from .converter import EMU_PER_PX, NS_A, NS_P, svg_to_drawingml, qn
from .model import SVGraphTextStyle, svg_to_svgraph_presentation

PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SHAPE_TAGS = {qn(NS_P, "sp"), qn(NS_P, "cxnSp"), qn(NS_P, "pic"), qn(NS_P, "graphicFrame")}


def svg_to_pptx(svg_text: str, output: str | Path) -> None:
    """Convert an SVG or SVGraph presentation document to a complete .pptx package."""

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(svg_to_pptx_bytes(svg_text))


def svg_to_pptx_bytes(svg_text: str) -> bytes:
    """Convert an SVG or SVGraph presentation document to .pptx bytes."""

    slides = svg_to_slide_xmls(svg_text)
    if not slides:
        raise ValueError("input did not produce any DrawingML shapes")
    presentation = svg_to_svgraph_presentation(svg_text)
    with io.BytesIO() as buffer:
        write_pptx(
            buffer,
            slides,
            slide_size=presentation.slide_size,
            master_count=max(1, len(presentation.masters)),
            layout_count=max(1, len(presentation.layouts)),
            text_styles=presentation.text_styles,
            custom_xml=_svgraph_presentation_sidecar(presentation),
        )
        return buffer.getvalue()


def svg_to_slide_xmls(svg_text: str) -> list[bytes]:
    """Convert declared SVGraph presentation slides to PresentationML slide XML documents."""

    slide_xmls: list[bytes] = []
    slide_svgs = _split_svg_slides(svg_text)
    for index, slide_svg in enumerate(slide_svgs, start=1):
        shapes = _svgraph_presentation_shapes(slide_svg)
        if not shapes:
            if len(slide_svgs) == 1:
                raise ValueError("input did not produce any DrawingML shapes")
            raise ValueError(f"slide {index} did not produce any DrawingML shapes")
        slide_xmls.append(build_slide_xml(shapes))
    return slide_xmls


def build_slide_xml(shapes: list[ET.Element]) -> bytes:
    ET.register_namespace("a", NS_A)
    ET.register_namespace("p", PRESENTATION_NS)
    ET.register_namespace("r", REL_NS)

    slide = ET.Element(qn(PRESENTATION_NS, "sld"))
    c_sld = ET.SubElement(slide, qn(PRESENTATION_NS, "cSld"))
    sp_tree = ET.SubElement(c_sld, qn(PRESENTATION_NS, "spTree"))
    nv_grp = ET.SubElement(sp_tree, qn(PRESENTATION_NS, "nvGrpSpPr"))
    ET.SubElement(nv_grp, qn(PRESENTATION_NS, "cNvPr"), {"id": "1", "name": ""})
    ET.SubElement(nv_grp, qn(PRESENTATION_NS, "cNvGrpSpPr"))
    ET.SubElement(nv_grp, qn(PRESENTATION_NS, "nvPr"))
    grp_sp_pr = ET.SubElement(sp_tree, qn(PRESENTATION_NS, "grpSpPr"))
    xfrm = ET.SubElement(grp_sp_pr, qn(NS_A, "xfrm"))
    ET.SubElement(xfrm, qn(NS_A, "off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "ext"), {"cx": "0", "cy": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chOff"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, qn(NS_A, "chExt"), {"cx": "0", "cy": "0"})

    for shape in shapes:
        sp_tree.append(_line_shape_to_connector(shape) if _is_relation_line_shape(shape) else shape)

    ET.SubElement(slide, qn(PRESENTATION_NS, "clrMapOvr")).append(ET.Element(qn(NS_A, "masterClrMapping")))
    return ET.tostring(slide, encoding="utf-8", xml_declaration=True)


def _svgraph_presentation_shapes(slide_svg: str) -> list[ET.Element]:
    root = ET.fromstring(slide_svg)
    semantic_tables = _semantic_elements(root, "table")
    table_shapes: list[ET.Element] = []
    for table in semantic_tables:
        fragment = ET.fromstring(svg_to_drawingml(_element_svg(root, table)))
        table_shapes.extend(child for child in fragment if child.tag == qn(NS_P, "graphicFrame"))
    for table in semantic_tables:
        _remove_element(root, table)
    fragment = ET.fromstring(svg_to_drawingml(ET.tostring(root, encoding="unicode")))
    shapes = [child for child in fragment if child.tag in SHAPE_TAGS]
    _mark_relation_connectors(root, shapes)
    return shapes + table_shapes


def _semantic_elements(root: ET.Element, kind: str) -> list[ET.Element]:
    elements: list[ET.Element] = []

    def walk(element: ET.Element) -> None:
        if element.get("data-kind") == kind or element.get("data-role") == kind:
            elements.append(element)
            return
        for child in list(element):
            walk(child)

    walk(root)
    return elements


def _element_svg(root: ET.Element, element: ET.Element) -> str:
    wrapper = ET.Element(root.tag, dict(root.attrib))
    for child in list(root):
        if _local_name(child.tag) in {"defs", "style"}:
            wrapper.append(_clone(child))
    wrapper.append(_clone(element))
    return ET.tostring(wrapper, encoding="unicode")


def _remove_element(root: ET.Element, target: ET.Element) -> bool:
    for child in list(root):
        if child is target:
            root.remove(child)
            return True
        if _remove_element(child, target):
            return True
    return False


def _is_line_shape(shape: ET.Element) -> bool:
    if shape.tag != qn(NS_P, "sp"):
        return False
    c_nv_pr = shape.find(f"./{qn(NS_P, 'nvSpPr')}/{qn(NS_P, 'cNvPr')}")
    return c_nv_pr is not None and c_nv_pr.get("name") == "line"


def _is_relation_line_shape(shape: ET.Element) -> bool:
    return _is_line_shape(shape) and _internal_shape_attr(shape, "relation") == "1"


def _line_shape_to_connector(shape: ET.Element) -> ET.Element:
    connector = ET.Element(qn(NS_P, "cxnSp"))
    nv_sp_pr = shape.find(qn(NS_P, "nvSpPr"))
    if nv_sp_pr is not None:
        nv = ET.SubElement(connector, qn(NS_P, "nvCxnSpPr"))
        c_nv_pr = nv_sp_pr.find(qn(NS_P, "cNvPr"))
        if c_nv_pr is not None:
            nv.append(c_nv_pr)
        c_nv_cxn_sp_pr = ET.SubElement(nv, qn(NS_P, "cNvCxnSpPr"))
        start_id = _internal_shape_attr(shape, "start_id")
        end_id = _internal_shape_attr(shape, "end_id")
        if start_id:
            ET.SubElement(c_nv_cxn_sp_pr, qn(NS_A, "stCxn"), {"id": start_id, "idx": "0"})
        if end_id:
            ET.SubElement(c_nv_cxn_sp_pr, qn(NS_A, "endCxn"), {"id": end_id, "idx": "0"})
        ET.SubElement(nv, qn(NS_P, "nvPr"))
    sp_pr = shape.find(qn(NS_P, "spPr"))
    if sp_pr is not None:
        ln = sp_pr.find(qn(NS_A, "ln"))
        if _internal_shape_attr(shape, "relation") == "1" and ln is not None and ln.find(qn(NS_A, "headEnd")) is None:
            ET.SubElement(ln, qn(NS_A, "headEnd"), {"type": "triangle"})
        connector.append(sp_pr)
    style = shape.find(qn(NS_P, "style"))
    if style is not None:
        connector.append(style)
    return connector


def _mark_relation_connectors(root: ET.Element, shapes: list[ET.Element]) -> None:
    relation_elements = _semantic_elements(root, "relation")
    line_shapes = [shape for shape in shapes if _is_line_shape(shape)]
    candidates = [_presentation_shape_reference(shape) for shape in shapes if not _is_line_shape(shape)]
    candidates = [candidate for candidate in candidates if candidate is not None]
    for relation, line_shape in zip(relation_elements, line_shapes):
        line_shape.set("_svgraph_relation", "1")
        start = (_float_attr(relation, "x1"), _float_attr(relation, "y1"))
        end = (_float_attr(relation, "x2"), _float_attr(relation, "y2"))
        start_id = _connection_shape_id(start, candidates)
        end_id = _connection_shape_id(end, candidates)
        if start_id is not None:
            line_shape.set("_svgraph_start_id", start_id)
        if end_id is not None:
            line_shape.set("_svgraph_end_id", end_id)


def _internal_shape_attr(shape: ET.Element, name: str) -> str | None:
    return shape.get(f"_svgraph_{name}")


def _presentation_shape_reference(shape: ET.Element) -> tuple[str, float, float, float, float] | None:
    c_nv_pr = shape.find(f"./{qn(NS_P, 'nvSpPr')}/{qn(NS_P, 'cNvPr')}")
    if c_nv_pr is None:
        c_nv_pr = shape.find(f"./{qn(NS_P, 'nvPicPr')}/{qn(NS_P, 'cNvPr')}")
    if c_nv_pr is None:
        c_nv_pr = shape.find(f"./{qn(NS_P, 'nvGraphicFramePr')}/{qn(NS_P, 'cNvPr')}")
    shape_id = c_nv_pr.get("id") if c_nv_pr is not None else None
    if not shape_id:
        return None
    xfrm = shape.find(f"./{qn(NS_P, 'spPr')}/{qn(NS_A, 'xfrm')}")
    if xfrm is None:
        xfrm = shape.find(qn(NS_P, "xfrm"))
    if xfrm is None:
        return None
    off = xfrm.find(qn(NS_A, "off"))
    ext = xfrm.find(qn(NS_A, "ext"))
    if off is None or ext is None:
        return None
    x = _emu_to_px(off.get("x"))
    y = _emu_to_px(off.get("y"))
    width = _emu_to_px(ext.get("cx"))
    height = _emu_to_px(ext.get("cy"))
    if x is None or y is None or width is None or height is None:
        return None
    return shape_id, x, y, x + width, y + height


def _connection_shape_id(
    point: tuple[float | None, float | None],
    candidates: list[tuple[str, float, float, float, float]],
) -> str | None:
    x, y = point
    if x is None or y is None:
        return None
    containing = [candidate for candidate in candidates if candidate[1] - 1e-6 <= x <= candidate[3] + 1e-6 and candidate[2] - 1e-6 <= y <= candidate[4] + 1e-6]
    if containing:
        return min(containing, key=lambda candidate: (candidate[3] - candidate[1]) * (candidate[4] - candidate[2]))[0]
    return min(candidates, key=lambda candidate: _point_to_box_distance(x, y, candidate), default=(None, 0, 0, 0, 0))[0]


def _point_to_box_distance(x: float, y: float, box: tuple[str, float, float, float, float]) -> float:
    _, left, top, right, bottom = box
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return dx * dx + dy * dy


def _float_attr(element: ET.Element, name: str) -> float | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _emu_to_px(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / EMU_PER_PX
    except ValueError:
        return None


def write_pptx(
    output: str | Path | io.BytesIO,
    slide_xml: bytes | list[bytes],
    *,
    slide_size: tuple[float, float] = (960.0, 540.0),
    master_count: int = 1,
    layout_count: int = 1,
    text_styles: tuple[SVGraphTextStyle, ...] = (),
    custom_xml: str | None = None,
) -> None:
    slide_xmls = [slide_xml] if isinstance(slide_xml, bytes) else slide_xml
    master_count = max(1, master_count)
    layout_count = max(1, layout_count)
    prepared_slides: list[tuple[bytes, str]] = []
    media: list[tuple[str, bytes]] = []
    next_media_index = 1
    for index, xml in enumerate(slide_xmls, start=1):
        layout_index = min(index, layout_count)
        prepared_slide, slide_rels, slide_media, next_media_index = _prepare_slide_media(xml, next_media_index, layout_index)
        prepared_slides.append((prepared_slide, slide_rels))
        media.extend(slide_media)

    output_path = Path(output) if not isinstance(output, io.BytesIO) else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    target = output if isinstance(output, io.BytesIO) else output_path
    assert target is not None
    has_custom_xml = custom_xml is not None
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", _content_types(len(slide_xmls), master_count, layout_count, has_custom_xml))
        pptx.writestr("_rels/.rels", _root_rels(has_custom_xml))
        pptx.writestr("docProps/app.xml", _app_props(len(slide_xmls)))
        pptx.writestr("docProps/core.xml", CORE_PROPS)
        pptx.writestr("ppt/presentation.xml", _presentation(len(slide_xmls), slide_size, master_count))
        pptx.writestr("ppt/_rels/presentation.xml.rels", _presentation_rels(len(slide_xmls), master_count))
        slide_master = _slide_master(text_styles)
        for index in range(1, master_count + 1):
            layout_index = min(index, layout_count)
            pptx.writestr(f"ppt/slideMasters/slideMaster{index}.xml", slide_master)
            pptx.writestr(f"ppt/slideMasters/_rels/slideMaster{index}.xml.rels", _slide_master_rels(layout_index))
        for index in range(1, layout_count + 1):
            master_index = min(index, master_count)
            pptx.writestr(f"ppt/slideLayouts/slideLayout{index}.xml", SLIDE_LAYOUT)
            pptx.writestr(f"ppt/slideLayouts/_rels/slideLayout{index}.xml.rels", _slide_layout_rels(master_index))
        pptx.writestr("ppt/theme/theme1.xml", THEME)
        for index, (xml, rels) in enumerate(prepared_slides, start=1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", xml)
            pptx.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", rels)
        for path, data in media:
            pptx.writestr(path, data)
        if custom_xml is not None:
            pptx.writestr("customXml/item1.xml", custom_xml)


def prepare_slide_media(slide_xml: bytes) -> tuple[bytes, str, list[tuple[str, bytes]]]:
    prepared_slide, rels, media, _ = _prepare_slide_media(slide_xml, 1, 1)
    return prepared_slide, rels, media


def _prepare_slide_media(
    slide_xml: bytes,
    next_media_index: int,
    layout_index: int,
) -> tuple[bytes, str, list[tuple[str, bytes]], int]:
    root = ET.fromstring(slide_xml)
    media: list[tuple[str, bytes]] = []
    rels = [_slide_layout_rel(layout_index)]
    next_rel_id = 2
    for blip in root.findall(f".//{qn(NS_A, 'blip')}"):
        embed = blip.get(qn(REL_NS, "embed"), "")
        parsed = _parse_data_image(embed)
        if parsed is None:
            continue
        extension, data = parsed
        media_path = f"ppt/media/image{next_media_index}.{extension}"
        rel_id = f"rId{next_rel_id}"
        next_rel_id += 1
        blip.set(qn(REL_NS, "embed"), rel_id)
        rels.append(
            f'  <Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{next_media_index}.{extension}"/>'
        )
        media.append((media_path, data))
        next_media_index += 1
    rels_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n"
    rels_xml += "\n".join(rels)
    rels_xml += "\n</Relationships>"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), rels_xml, media, next_media_index


def _split_svg_slides(svg_text: str) -> list[str]:
    root = ET.fromstring(svg_text)
    slides = _declared_slide_elements(root)
    if not slides:
        return [svg_text]
    return [_slide_svg(root, slide) for slide in slides]


def _declared_slide_elements(root: ET.Element) -> list[ET.Element]:
    slides: list[ET.Element] = []

    def walk(element: ET.Element) -> None:
        if _is_slide_element(element):
            slides.append(element)
            return
        for child in list(element):
            walk(child)

    walk(root)
    return slides


def _is_slide_element(element: ET.Element) -> bool:
    return (
        element.get("data-kind") == "slide"
        or element.get("data-role") == "slide"
        or element.get("data-slide") is not None
    )


def _slide_svg(root: ET.Element, slide: ET.Element) -> str:
    if slide is root:
        return ET.tostring(root, encoding="unicode")
    root_attrs = dict(root.attrib)
    view_box = slide.get("viewBox") or root.get("viewBox")
    if view_box:
        root_attrs["viewBox"] = view_box
    wrapper = ET.Element(root.tag, root_attrs)
    for child in list(root):
        if _local_name(child.tag) in {"defs", "style"}:
            wrapper.append(_clone(child))
    if _local_name(slide.tag) == "svg":
        for child in list(slide):
            if _local_name(child.tag) != "metadata":
                wrapper.append(_clone(child))
    else:
        wrapper.append(_clone(slide))
    return ET.tostring(wrapper, encoding="unicode")


def _clone(element: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(element, encoding="utf-8"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_data_image(value: str) -> tuple[str, bytes] | None:
    match = re.fullmatch(r"data:image/(png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=\s]+)", value, flags=re.I)
    if not match:
        return None
    kind = match.group(1).lower()
    extension = "jpg" if kind in {"jpeg", "jpg"} else kind
    try:
        data = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except binascii.Error:
        return None
    return extension, data


def _content_types(
    slide_count: int,
    master_count: int = 1,
    layout_count: int = 1,
    has_custom_xml: bool = False,
) -> str:
    master_overrides = "\n".join(
        f'  <Override PartName="/ppt/slideMasters/slideMaster{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        for index in range(1, master_count + 1)
    )
    layout_overrides = "\n".join(
        f'  <Override PartName="/ppt/slideLayouts/slideLayout{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        for index in range(1, layout_count + 1)
    )
    slide_overrides = "\n".join(
        f'  <Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, slide_count + 1)
    )
    custom_xml_override = (
        '  <Override PartName="/customXml/item1.xml" ContentType="application/xml"/>'
        if has_custom_xml
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Default Extension="gif" ContentType="image/gif"/>
  <Default Extension="webp" ContentType="image/webp"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
{master_overrides}
{layout_overrides}
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
{slide_overrides}
{custom_xml_override}
</Types>"""


def _app_props(slide_count: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>SVGraph</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>{slide_count}</Slides>
</Properties>"""


def _presentation(slide_count: int, slide_size: tuple[float, float], master_count: int = 1) -> str:
    master_ids = "\n".join(
        f'    <p:sldMasterId id="{2147483647 + index}" r:id="rId{index}"/>'
        for index in range(1, master_count + 1)
    )
    slide_ids = "\n".join(
        f'    <p:sldId id="{255 + index}" r:id="rId{master_count + index}"/>'
        for index in range(1, slide_count + 1)
    )
    width, height = slide_size
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst>
{master_ids}
  </p:sldMasterIdLst>
  <p:sldIdLst>
{slide_ids}
  </p:sldIdLst>
  <p:sldSz cx="{round(width * EMU_PER_PX)}" cy="{round(height * EMU_PER_PX)}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""


def _presentation_rels(slide_count: int, master_count: int = 1) -> str:
    master_rels = "\n".join(
        f'  <Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster{index}.xml"/>'
        for index in range(1, master_count + 1)
    )
    slide_rels = "\n".join(
        f'  <Relationship Id="rId{master_count + index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, slide_count + 1)
    )
    theme_rel_id = master_count + slide_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{master_rels}
{slide_rels}
  <Relationship Id="rId{theme_rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>"""


def _root_rels(has_custom_xml: bool = False) -> str:
    custom_xml_rel = (
        '\n  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" Target="customXml/item1.xml"/>'
        if has_custom_xml
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
{custom_xml_rel}
</Relationships>"""


ROOT_RELS = _root_rels()


def _svgraph_presentation_sidecar(presentation: object) -> str:
    payload = json.dumps(asdict(presentation), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<svgraph:presentation xmlns:svgraph="https://com-junkawasaki.github.io/svgraph/schema/presentation" version="1">'
        f"<svgraph:json>{_xml_text(payload)}</svgraph:json>"
        "</svgraph:presentation>"
    )


def _xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CORE_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>SVGraph export</dc:title>
  <dc:creator>SVGraph</dc:creator>
  <cp:lastModifiedBy>SVGraph</cp:lastModifiedBy>
</cp:coreProperties>"""

def _slide_layout_rel(layout_index: int = 1) -> str:
    return f'  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout{layout_index}.xml"/>'


SLIDE_LAYOUT_REL = _slide_layout_rel()

def _slide_master_rels(layout_index: int = 1) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout{layout_index}.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


def _slide_layout_rels(master_index: int = 1) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster{master_index}.xml"/>
</Relationships>"""


SLIDE_MASTER_RELS = _slide_master_rels()
SLIDE_LAYOUT_RELS = _slide_layout_rels()


def _slide_master(text_styles: tuple[SVGraphTextStyle, ...] = ()) -> str:
    title_style = _text_style_xml("titleStyle", _text_style_for_role(text_styles, "title"))
    body_style = _text_style_xml("bodyStyle", _text_style_for_role(text_styles, "body"))
    other_style = _text_style_xml(
        "otherStyle",
        _text_style_for_role(text_styles, "other")
        or _text_style_for_role(text_styles, "lead")
        or _text_style_for_role(text_styles, "caption"),
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>{title_style}{body_style}{other_style}</p:txStyles>
</p:sldMaster>"""


def _text_style_for_role(text_styles: tuple[SVGraphTextStyle, ...], role: str) -> SVGraphTextStyle | None:
    normalized = role.lower()
    return next((style for style in text_styles if style.role.lower() == normalized), None)


def _text_style_xml(tag: str, style: SVGraphTextStyle | None) -> str:
    if style is None:
        return f"<p:{tag}/>"
    properties = style.properties
    attrs = []
    font_size = _style_number(properties.get("fontSize") or properties.get("font-size"))
    if font_size is not None:
        attrs.append(f'sz="{round(font_size * 100)}"')
    if _style_bool(properties.get("bold") or properties.get("fontWeight") or properties.get("font-weight")):
        attrs.append('b="1"')
    if _style_bool(properties.get("italic") or properties.get("fontStyle") or properties.get("font-style")):
        attrs.append('i="1"')
    font_family = properties.get("fontFamily") or properties.get("font-family")
    latin = f'<a:latin typeface="{_xml_attr(str(font_family))}"/>' if font_family else ""
    attrs_text = (" " + " ".join(attrs)) if attrs else ""
    return f"<p:{tag}><a:lvl1pPr><a:defRPr{attrs_text}>{latin}</a:defRPr></a:lvl1pPr></p:{tag}>"


def _style_number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
        if match:
            return float(match.group(1))
    return None


def _style_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value >= 600
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "bold", "bolder"} or normalized.isdigit() and int(normalized) >= 600
    return False


def _xml_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


SLIDE_MASTER = _slide_master()

SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""

THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="SVGraph">
  <a:themeElements>
    <a:clrScheme name="SVGraph">
      <a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F9FAFB"/></a:lt2>
      <a:accent1><a:srgbClr val="1D4ED8"/></a:accent1><a:accent2><a:srgbClr val="15803D"/></a:accent2>
      <a:accent3><a:srgbClr val="DC2626"/></a:accent3><a:accent4><a:srgbClr val="7C3AED"/></a:accent4>
      <a:accent5><a:srgbClr val="0891B2"/></a:accent5><a:accent6><a:srgbClr val="EA580C"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="9333EA"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="SVGraph"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="SVGraph"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>"""
