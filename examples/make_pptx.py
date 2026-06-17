from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from drawingml_svg import svg_to_drawingml
from drawingml_svg.converter import NS_A, NS_P, qn

PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_pptx.py")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("drawingml-svg-sample.pptx"))
    args = parser.parse_args(argv)

    try:
        svg_text = args.input.read_text(encoding="utf-8")
        sp_tree_fragment = ET.fromstring(svg_to_drawingml(svg_text))
    except (ET.ParseError, OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    shapes = [
        child
        for child in sp_tree_fragment
        if child.tag in {qn(NS_P, "sp"), qn(NS_P, "cxnSp"), qn(NS_P, "pic")}
    ]
    if not shapes:
        parser.exit(1, f"{parser.prog}: error: input did not produce any DrawingML shapes\n")

    slide_xml = build_slide_xml(shapes)
    write_pptx(args.output, slide_xml)
    return 0


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
        sp_tree.append(shape)

    ET.SubElement(slide, qn(PRESENTATION_NS, "clrMapOvr")).append(
        ET.Element(qn(NS_A, "masterClrMapping"))
    )
    return ET.tostring(slide, encoding="utf-8", xml_declaration=True)


def write_pptx(output: Path, slide_xml: bytes) -> None:
    slide_xml, slide_rels, media = prepare_slide_media(slide_xml)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", CONTENT_TYPES)
        pptx.writestr("_rels/.rels", ROOT_RELS)
        pptx.writestr("docProps/app.xml", APP_PROPS)
        pptx.writestr("docProps/core.xml", CORE_PROPS)
        pptx.writestr("ppt/presentation.xml", PRESENTATION)
        pptx.writestr("ppt/_rels/presentation.xml.rels", PRESENTATION_RELS)
        pptx.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS)
        pptx.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS)
        pptx.writestr("ppt/theme/theme1.xml", THEME)
        pptx.writestr("ppt/slides/slide1.xml", slide_xml)
        pptx.writestr("ppt/slides/_rels/slide1.xml.rels", slide_rels)
        for path, data in media:
            pptx.writestr(path, data)


def prepare_slide_media(slide_xml: bytes) -> tuple[bytes, str, list[tuple[str, bytes]]]:
    root = ET.fromstring(slide_xml)
    media: list[tuple[str, bytes]] = []
    rels = [SLIDE_LAYOUT_REL]
    next_rel_id = 2
    for index, blip in enumerate(root.findall(f".//{qn(NS_A, 'blip')}"), start=1):
        embed = blip.get(qn(REL_NS, "embed"), "")
        parsed = _parse_data_image(embed)
        if parsed is None:
            continue
        extension, data = parsed
        media_path = f"ppt/media/image{index}.{extension}"
        rel_id = f"rId{next_rel_id}"
        next_rel_id += 1
        blip.set(qn(REL_NS, "embed"), rel_id)
        rels.append(
            f'  <Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{index}.{extension}"/>'
        )
        media.append((media_path, data))
    rels_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n"
    rels_xml += "\n".join(rels)
    rels_xml += "\n</Relationships>"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), rels_xml, media


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


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
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
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

APP_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>drawingml-svg</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>1</Slides>
</Properties>"""

CORE_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>drawingml-svg sample</dc:title>
  <dc:creator>drawingml-svg</dc:creator>
  <cp:lastModifiedBy>drawingml-svg</cp:lastModifiedBy>
</cp:coreProperties>"""

PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="9144000" cy="5143500" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""

PRESENTATION_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>"""

SLIDE_LAYOUT_REL = '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'

SLIDE_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{SLIDE_LAYOUT_REL}
</Relationships>"""

SLIDE_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""

SLIDE_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""

SLIDE_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>"""

SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""

THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="drawingml-svg">
  <a:themeElements>
    <a:clrScheme name="drawingml-svg">
      <a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F9FAFB"/></a:lt2>
      <a:accent1><a:srgbClr val="1D4ED8"/></a:accent1><a:accent2><a:srgbClr val="15803D"/></a:accent2>
      <a:accent3><a:srgbClr val="DC2626"/></a:accent3><a:accent4><a:srgbClr val="7C3AED"/></a:accent4>
      <a:accent5><a:srgbClr val="0891B2"/></a:accent5><a:accent6><a:srgbClr val="EA580C"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="9333EA"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="drawingml-svg"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="drawingml-svg"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
