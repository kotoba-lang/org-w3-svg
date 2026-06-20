from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .converter import _href, _local_name


IRI_RE = re.compile(r"url\(\s*['\"]?(#[^)'\"]+)['\"]?\s*\)")
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass(frozen=True)
class SvgraphDocument:
    kind: str
    version: str
    root: "SvgraphNode"
    metadata: dict[str, object]
    dependencies: tuple["SvgraphDependency", ...]
    presentation: "SvgraphPresentation"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SvgraphNode:
    node_id: str
    tag: str
    attributes: dict[str, str]
    data: dict[str, str]
    metadata: dict[str, object]
    dependencies: tuple["SvgraphDependency", ...]
    children: tuple["SvgraphNode", ...]
    text: str | None = None


@dataclass(frozen=True)
class SvgraphDependency:
    kind: str
    source: str
    target: str
    attribute: str | None = None


@dataclass(frozen=True)
class SvgraphPresentation:
    kind: str
    slide_size: tuple[float, float]
    slides: tuple["SvgraphSlide", ...]
    parts: tuple["SvgraphPackagePart", ...]
    masters: tuple["SvgraphTemplate", ...]
    layouts: tuple["SvgraphTemplate", ...]
    guides: tuple["SvgraphGuide", ...]
    rulers: tuple["SvgraphRuler", ...]
    text_styles: tuple["SvgraphTextStyle", ...]
    metadata: dict[str, object]


@dataclass(frozen=True)
class SvgraphSlide:
    slide_id: str
    node_id: str
    title: str | None
    view_box: tuple[float, float, float, float]
    data: dict[str, str]
    metadata: dict[str, object]


@dataclass(frozen=True)
class SvgraphPackagePart:
    part_name: str
    content_type: str
    kind: str
    source_node_id: str | None = None


@dataclass(frozen=True)
class SvgraphTemplate:
    template_id: str
    kind: str
    node_id: str | None
    data: dict[str, str]
    metadata: dict[str, object]


@dataclass(frozen=True)
class SvgraphGuide:
    guide_id: str
    orientation: str
    position: float
    unit: str
    node_id: str | None = None


@dataclass(frozen=True)
class SvgraphRuler:
    ruler_id: str
    orientation: str
    origin: float
    unit: str
    spacing: float | None = None
    node_id: str | None = None


@dataclass(frozen=True)
class SvgraphTextStyle:
    style_id: str
    role: str
    properties: dict[str, object]
    node_id: str | None = None


# Backward-compatible type aliases for the pre-SVGraph API names.
SvgIRDocument = SvgraphDocument
SvgIRNode = SvgraphNode
SvgIRDependency = SvgraphDependency
SvgIRPresentation = SvgraphPresentation
SvgIRSlide = SvgraphSlide
SvgIRPackagePart = SvgraphPackagePart
SvgIRTemplate = SvgraphTemplate
SvgIRGuide = SvgraphGuide
SvgIRRuler = SvgraphRuler
SvgIRTextStyle = SvgraphTextStyle


def svg_to_ir(svg_text: str) -> SvgraphDocument:
    """Parse SVG into a metadata-preserving IR for downstream emitters."""

    root = ET.fromstring(svg_text)
    root_node = _node_to_ir(root, "n0")
    return SvgraphDocument(
        kind="svgraph",
        version="0.1",
        root=root_node,
        metadata=root_node.metadata,
        dependencies=_collect_node_dependencies(root_node),
        presentation=_presentation_ir(root_node),
    )


def svg_to_svgraph(svg_text: str) -> SvgraphDocument:
    """Parse SVG into SVGraph, the metadata-preserving SVG graph IR."""

    return svg_to_ir(svg_text)


def svg_to_pptx_ir(svg_text: str) -> SvgraphPresentation:
    """Parse SVG into the presentation/package view of SVGraph."""

    return svg_to_ir(svg_text).presentation


def svg_ir_to_json(svg_text: str) -> str:
    return json.dumps(svg_to_ir(svg_text).to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def svg_svgraph_to_json(svg_text: str) -> str:
    return json.dumps(svg_to_svgraph(svg_text).to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def svg_pptx_ir_to_json(svg_text: str) -> str:
    return json.dumps(asdict(svg_to_pptx_ir(svg_text)), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _node_to_ir(element: ET.Element, node_id: str) -> SvgraphNode:
    tag = _local_name(element.tag)
    attributes = _attributes(element)
    data = _data_attributes(attributes)
    metadata = _metadata(element)
    dependencies = _dependencies(element, attributes)
    child_elements = [child for child in list(element) if _local_name(child.tag) != "metadata"]
    children = tuple(_node_to_ir(child, f"{node_id}.{index}") for index, child in enumerate(child_elements))
    text = element.text.strip() if element.text and element.text.strip() else None
    return SvgraphNode(
        node_id=node_id,
        tag=tag,
        attributes=attributes,
        data=data,
        metadata=metadata,
        dependencies=dependencies,
        children=children,
        text=text,
    )


def _attributes(element: ET.Element) -> dict[str, str]:
    return {str(_local_name(name)): value for name, value in sorted(element.attrib.items())}


def _data_attributes(attributes: dict[str, str]) -> dict[str, str]:
    return {name[5:]: value for name, value in attributes.items() if name.startswith("data-")}


def _metadata(element: ET.Element) -> dict[str, object]:
    result: dict[str, object] = {}
    for child in list(element):
        if _local_name(child.tag) != "metadata":
            continue
        text = "".join(child.itertext()).strip()
        if text:
            result["text"] = text
            parsed = _json_metadata(text)
            if parsed is not None:
                result["json"] = parsed
        xml_children = [grandchild for grandchild in list(child)]
        if xml_children:
            result["xml"] = "".join(ET.tostring(grandchild, encoding="unicode") for grandchild in xml_children)
    return result


def _json_metadata(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _dependencies(element: ET.Element, attributes: dict[str, str]) -> tuple[SvgraphDependency, ...]:
    tag = _local_name(element.tag)
    source = attributes.get("id", tag)
    deps: list[SvgraphDependency] = []
    href = _href(element)
    if href:
        deps.append(SvgraphDependency("href", source, href, "href"))
    for name, value in attributes.items():
        if name == "href":
            continue
        if value.startswith("#") and not HEX_COLOR_RE.match(value):
            deps.append(SvgraphDependency("reference", source, value, name))
        for match in IRI_RE.finditer(value):
            deps.append(SvgraphDependency("paint-server", source, match.group(1), name))
    return tuple(deps)


def _collect_node_dependencies(node: SvgraphNode) -> tuple[SvgraphDependency, ...]:
    deps = list(node.dependencies)
    for child in node.children:
        deps.extend(_collect_node_dependencies(child))
    return tuple(deps)


def _presentation_ir(root: SvgraphNode) -> SvgraphPresentation:
    slides = _declared_slides(root)
    if not slides:
        slides = (root,)
    slide_irs = tuple(_slide_ir(node, index) for index, node in enumerate(slides, start=1))
    metadata = _presentation_metadata(root.metadata)
    masters = _templates(root, metadata, "masters", "slide-master")
    layouts = _templates(root, metadata, "layouts", "slide-layout")
    return SvgraphPresentation(
        kind="pptxsvg",
        slide_size=_slide_size(root, slide_irs[0].view_box),
        slides=slide_irs,
        parts=_package_parts(slide_irs, masters, layouts),
        masters=masters,
        layouts=layouts,
        guides=_guides(root, metadata),
        rulers=_rulers(root, metadata),
        text_styles=_text_styles(root, metadata),
        metadata=metadata,
    )


def _declared_slides(node: SvgraphNode) -> tuple[SvgraphNode, ...]:
    slides: list[SvgraphNode] = []
    _collect_declared_slides(node, slides)
    return tuple(slides)


def _collect_declared_slides(node: SvgraphNode, slides: list[SvgraphNode]) -> None:
    if _is_slide_node(node):
        slides.append(node)
        return
    for child in node.children:
        _collect_declared_slides(child, slides)


def _is_slide_node(node: SvgraphNode) -> bool:
    return (
        node.data.get("kind") == "slide"
        or node.data.get("role") == "slide"
        or "slide" in node.data
        or node.attributes.get("data-kind") == "slide"
        or node.attributes.get("data-role") == "slide"
    )


def _slide_ir(node: SvgraphNode, index: int) -> SvgraphSlide:
    view_box = _view_box(node)
    return SvgraphSlide(
        slide_id=node.attributes.get("id") or node.data.get("slide") or f"slide-{index}",
        node_id=node.node_id,
        title=_title(node),
        view_box=view_box,
        data=node.data,
        metadata=node.metadata,
    )


def _nodes_by_kind(root: SvgraphNode, kind: str) -> tuple[SvgraphNode, ...]:
    nodes: list[SvgraphNode] = []
    _collect_nodes_by_kind(root, kind, nodes)
    return tuple(nodes)


def _collect_nodes_by_kind(node: SvgraphNode, kind: str, nodes: list[SvgraphNode]) -> None:
    if node.data.get("kind") == kind or node.data.get("role") == kind:
        nodes.append(node)
    for child in node.children:
        _collect_nodes_by_kind(child, kind, nodes)


def _templates(root: SvgraphNode, metadata: dict[str, object], metadata_key: str, kind: str) -> tuple[SvgraphTemplate, ...]:
    templates: list[SvgraphTemplate] = []
    for index, entry in enumerate(_list_metadata(metadata, metadata_key), start=1):
        if isinstance(entry, dict):
            template_id = str(entry.get("id") or entry.get("name") or f"{kind}-{index}")
            templates.append(SvgraphTemplate(template_id, kind, None, {}, entry))
    for node in _nodes_by_kind(root, kind):
        templates.append(
            SvgraphTemplate(
                node.attributes.get("id") or node.data.get("template") or node.node_id,
                kind,
                node.node_id,
                node.data,
                node.metadata,
            )
        )
    return tuple(templates)


def _guides(root: SvgraphNode, metadata: dict[str, object]) -> tuple[SvgraphGuide, ...]:
    guides: list[SvgraphGuide] = []
    for index, entry in enumerate(_list_metadata(metadata, "guides"), start=1):
        if not isinstance(entry, dict):
            continue
        position = _number(entry.get("position"))
        if position is None:
            continue
        guides.append(
            SvgraphGuide(
                str(entry.get("id") or f"guide-{index}"),
                str(entry.get("orientation") or "vertical"),
                position,
                str(entry.get("unit") or "px"),
            )
        )
    for node in _nodes_by_kind(root, "guide"):
        position = _number(node.data.get("position") or node.attributes.get("x") or node.attributes.get("y"))
        if position is None:
            continue
        guides.append(
            SvgraphGuide(
                node.attributes.get("id") or node.node_id,
                node.data.get("orientation") or ("horizontal" if "y" in node.attributes else "vertical"),
                position,
                node.data.get("unit") or "px",
                node.node_id,
            )
        )
    return tuple(guides)


def _rulers(root: SvgraphNode, metadata: dict[str, object]) -> tuple[SvgraphRuler, ...]:
    rulers: list[SvgraphRuler] = []
    for index, entry in enumerate(_list_metadata(metadata, "rulers"), start=1):
        if not isinstance(entry, dict):
            continue
        origin = _number(entry.get("origin")) or 0.0
        rulers.append(
            SvgraphRuler(
                str(entry.get("id") or f"ruler-{index}"),
                str(entry.get("orientation") or "horizontal"),
                origin,
                str(entry.get("unit") or "px"),
                _number(entry.get("spacing")),
            )
        )
    for node in _nodes_by_kind(root, "ruler"):
        rulers.append(
            SvgraphRuler(
                node.attributes.get("id") or node.node_id,
                node.data.get("orientation") or "horizontal",
                _number(node.data.get("origin")) or 0.0,
                node.data.get("unit") or "px",
                _number(node.data.get("spacing")),
                node.node_id,
            )
        )
    return tuple(rulers)


def _text_styles(root: SvgraphNode, metadata: dict[str, object]) -> tuple[SvgraphTextStyle, ...]:
    styles: list[SvgraphTextStyle] = []
    raw_styles = metadata.get("textStyles") or metadata.get("text_styles")
    if isinstance(raw_styles, dict):
        for role, properties in raw_styles.items():
            if isinstance(properties, dict):
                styles.append(SvgraphTextStyle(str(role), str(role), properties))
    for index, entry in enumerate(_list_metadata(metadata, "textStyles"), start=1):
        if isinstance(entry, dict):
            role = str(entry.get("role") or entry.get("id") or f"text-style-{index}")
            styles.append(SvgraphTextStyle(str(entry.get("id") or role), role, entry))
    for node in _nodes_by_kind(root, "style-template"):
        role = node.data.get("role") or node.data.get("style") or node.attributes.get("id") or node.node_id
        styles.append(SvgraphTextStyle(node.attributes.get("id") or role, role, {**node.attributes, **node.data}, node.node_id))
    return tuple(styles)


def _list_metadata(metadata: dict[str, object], key: str) -> list[object]:
    value = metadata.get(key)
    return value if isinstance(value, list) else []


def _package_parts(
    slides: tuple[SvgraphSlide, ...],
    masters: tuple[SvgraphTemplate, ...] = (),
    layouts: tuple[SvgraphTemplate, ...] = (),
) -> tuple[SvgraphPackagePart, ...]:
    parts = [
        SvgraphPackagePart(
            part_name="/ppt/presentation.xml",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
            kind="presentation",
        ),
    ]
    for index, master in enumerate(masters or (None,), start=1):
        parts.append(
            SvgraphPackagePart(
                part_name=f"/ppt/slideMasters/slideMaster{index}.xml",
                content_type="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
                kind="slide-master",
                source_node_id=master.node_id if master is not None else None,
            )
        )
    for index, layout in enumerate(layouts or (None,), start=1):
        parts.append(
            SvgraphPackagePart(
                part_name=f"/ppt/slideLayouts/slideLayout{index}.xml",
                content_type="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
                kind="slide-layout",
                source_node_id=layout.node_id if layout is not None else None,
            )
        )
    parts.append(
        SvgraphPackagePart(
            part_name="/ppt/theme/theme1.xml",
            content_type="application/vnd.openxmlformats-officedocument.theme+xml",
            kind="theme",
        )
    )
    for index, slide in enumerate(slides, start=1):
        parts.append(
            SvgraphPackagePart(
                part_name=f"/ppt/slides/slide{index}.xml",
                content_type="application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
                kind="slide",
                source_node_id=slide.node_id,
            )
        )
    return tuple(parts)


def _slide_size(root: SvgraphNode, fallback_view_box: tuple[float, float, float, float]) -> tuple[float, float]:
    metadata = _presentation_metadata(root.metadata)
    slide_size = metadata.get("slideSize")
    if isinstance(slide_size, dict):
        width = _number(slide_size.get("width"))
        height = _number(slide_size.get("height"))
        if width is not None and height is not None:
            return (width, height)
    if isinstance(slide_size, list | tuple) and len(slide_size) >= 2:
        width = _number(slide_size[0])
        height = _number(slide_size[1])
        if width is not None and height is not None:
            return (width, height)
    view_box = _view_box(root)
    if view_box[2] > 0 and view_box[3] > 0:
        return (view_box[2], view_box[3])
    return (fallback_view_box[2], fallback_view_box[3])


def _presentation_metadata(metadata: dict[str, object]) -> dict[str, object]:
    parsed = metadata.get("json")
    if not isinstance(parsed, dict):
        return {}
    presentation = parsed.get("presentation")
    return presentation if isinstance(presentation, dict) else {}


def _view_box(node: SvgraphNode) -> tuple[float, float, float, float]:
    raw = node.attributes.get("viewBox")
    if raw:
        values = [_number(part) for part in raw.replace(",", " ").split()]
        if len(values) == 4 and all(value is not None for value in values):
            return (values[0] or 0.0, values[1] or 0.0, values[2] or 0.0, values[3] or 0.0)
    width = _number(node.attributes.get("width")) or 0.0
    height = _number(node.attributes.get("height")) or 0.0
    return (0.0, 0.0, width, height)


def _title(node: SvgraphNode) -> str | None:
    if "title" in node.data:
        return node.data["title"]
    if isinstance(node.metadata.get("json"), dict):
        title = node.metadata["json"].get("title")  # type: ignore[index]
        if isinstance(title, str):
            return title
    for child in node.children:
        if child.tag == "title" and child.text:
            return child.text
    return None


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.match(r"\s*([-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[eE][-+]?\d+)?)", value)
    if not match:
        return None
    return float(match.group(1))
