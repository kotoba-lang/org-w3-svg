"use strict";
const emuPerPx = 9525;
const sampleSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <metadata>{"presentation":{"slideSize":{"width":1280,"height":720},"masters":[{"id":"brand-master"}],"layouts":[{"id":"title-content","master":"brand-master"}],"guides":[{"id":"safe-left","orientation":"vertical","position":90}],"rulers":[{"id":"x","orientation":"horizontal","origin":0,"spacing":16}],"textStyles":{"title":{"fontFamily":"Aptos Display","fontSize":54,"bold":true},"lead":{"fontFamily":"Aptos","fontSize":28},"body":{"fontFamily":"Aptos","fontSize":18}}}}</metadata>
  <g id="cover" data-kind="slide" data-title="PPTXSVG Cover">
    <rect width="1280" height="720" fill="#f8fafc"/>
    <rect x="90" y="96" width="500" height="210" rx="22" fill="#ccfbf1" stroke="#0f766e" stroke-width="4"/>
    <text x="128" y="184" font-size="54" font-family="Arial" font-weight="700" fill="#134e4a">PPTXSVG</text>
    <text x="130" y="248" font-size="28" font-family="Arial" fill="#334155">SVG as editable presentation IR</text>
    <circle id="api" data-kind="service" cx="770" cy="230" r="70" fill="#dbeafe" stroke="#2563eb" stroke-width="4"/>
    <rect id="deck" data-kind="presentation" x="910" y="160" width="190" height="140" rx="16" fill="#fee2e2" stroke="#b42318" stroke-width="4"/>
    <line data-kind="relation" x1="840" y1="230" x2="910" y2="230" stroke="#475467" stroke-width="5"/>
  </g>
  <g id="table-slide" data-kind="slide" data-title="Native Table Candidate">
    <rect width="1280" height="720" fill="#ffffff"/>
    <text x="90" y="90" font-size="40" font-family="Arial" font-weight="700" fill="#17202a">Table semantics stay in IR</text>
    <g id="table" data-kind="table" transform="translate(90 150)">
      <rect data-kind="cell" data-row="0" data-col="0" width="260" height="80" fill="#e6f4f1" stroke="#0f766e"/>
      <rect data-kind="cell" data-row="0" data-col="1" x="260" width="260" height="80" fill="#e6f4f1" stroke="#0f766e"/>
      <rect data-kind="cell" data-row="1" data-col="0" y="80" width="260" height="80" fill="#ffffff" stroke="#0f766e"/>
      <rect data-kind="cell" data-row="1" data-col="1" x="260" y="80" width="260" height="80" fill="#ffffff" stroke="#0f766e"/>
    </g>
  </g>
  <g id="coverage-slide" data-kind="slide" data-title="Browser SVG Coverage" style="stroke:#334155;stroke-width:4;fill:#fde68a">
    <defs>
      <rect id="reused-chip" width="170" height="70" rx="14"/>
    </defs>
    <style>
      .accent-use { fill: #fce7f3; stroke: #be185d; stroke-width: 5; }
      g .css-circle { fill: #e0f2fe; stroke: #0369a1; stroke-width: 5; }
    </style>
    <rect width="1280" height="720" fill="#ffffff" stroke="none"/>
    <text x="90" y="90" style="font-size:40;font-family:Arial;font-weight:700;fill:#17202a">Browser SVG coverage</text>
    <polygon id="tri" points="120,170 300,170 210,315"/>
    <polyline id="zig" points="390,170 460,250 530,170 600,250" style="fill:none;stroke:#dc2626"/>
    <path id="box-path" d="M 690 170 L 900 170 L 900 315 L 690 315 Z" style="fill:#dcfce7;stroke:#15803d"/>
    <path id="curve-path" d="M 120 520 C 190 430 260 610 330 520 Q 390 445 450 520 T 570 520" style="fill:none;stroke:#ea580c;stroke-width:6"/>
    <line id="marked-line" x1="980" y1="185" x2="1130" y2="260" style="stroke:#7c3aed;stroke-width:8;marker-end:url(#arrow)"/>
    <image id="pixel" x="980" y="340" width="96" height="96" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luzQnAAAAABJRU5ErkJggg=="/>
    <circle class="css-circle" cx="1130" cy="388" r="48"/>
    <use href="#reused-chip" class="accent-use" x="360" y="400"/>
    <g transform="translate(90 390) scale(1.5)">
      <rect id="scaled" width="160" height="80" style="fill:#dbeafe;stroke:#2563eb"/>
    </g>
  </g>
</svg>`;
const state = {
    tab: "summary",
    ir: null,
    pptxsvg: null,
    webgpu: false,
};
const source = mustElement("source");
const preview = mustElement("preview");
const panel = mustElement("panel");
const fileInput = mustElement("fileInput");
function mustElement(id) {
    const element = document.getElementById(id);
    if (!element)
        throw new Error(`missing #${id}`);
    return element;
}
function localName(node) {
    return node.localName || node.nodeName.replace(/^.*:/, "");
}
function attrs(element) {
    return Object.fromEntries(Array.from(element.attributes || []).map((attr) => [attr.name, attr.value]).sort());
}
function dataAttrs(attributes) {
    return Object.fromEntries(Object.entries(attributes)
        .filter(([key]) => key.startsWith("data-"))
        .map(([key, value]) => [key.slice(5), value]));
}
function metadata(element) {
    const meta = Array.from(element.children).find((child) => localName(child) === "metadata");
    if (!meta)
        return {};
    const text = (meta.textContent || "").trim();
    if (!text)
        return {};
    try {
        return { text, json: JSON.parse(text) };
    }
    catch (_) {
        return { text };
    }
}
function dependencies(element, attributes) {
    const id = attributes.id || localName(element);
    const deps = [];
    for (const [name, value] of Object.entries(attributes)) {
        if ((name === "href" || name.endsWith(":href")) && value) {
            deps.push({ kind: "href", source: id, target: value, attribute: "href" });
        }
        for (const match of value.matchAll(/url\(\s*['"]?(#[^)'" ]+)['"]?\s*\)/g)) {
            deps.push({ kind: "paint-server", source: id, target: match[1] || "", attribute: name });
        }
    }
    return deps;
}
function nodeToIr(element, nodeId) {
    const attributes = attrs(element);
    const children = Array.from(element.children)
        .filter((child) => localName(child) !== "metadata")
        .map((child, index) => nodeToIr(child, `${nodeId}.${index}`));
    const text = Array.from(element.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => (node.textContent || "").trim())
        .filter(Boolean)
        .join(" ");
    return {
        node_id: nodeId,
        tag: localName(element),
        attributes,
        data: dataAttrs(attributes),
        metadata: metadata(element),
        dependencies: dependencies(element, attributes),
        children,
        text: text || null,
    };
}
function flatten(node) {
    return [node, ...node.children.flatMap(flatten)];
}
function viewBox(node) {
    const raw = node.attributes.viewBox;
    if (raw) {
        const values = raw.replaceAll(",", " ").split(/\s+/).map(Number).filter((value) => Number.isFinite(value));
        if (values.length === 4 && values[0] !== undefined && values[1] !== undefined && values[2] !== undefined && values[3] !== undefined) {
            return [values[0], values[1], values[2], values[3]];
        }
    }
    return [0, 0, Number(node.attributes.width) || 0, Number(node.attributes.height) || 0];
}
function nodeTitle(node) {
    if (node.data.title)
        return node.data.title;
    const meta = asObject(node.metadata.json);
    if (typeof meta.title === "string")
        return meta.title;
    const titleNode = node.children.find((child) => child.tag === "title");
    return titleNode?.text || null;
}
function isSlide(node) {
    return node.data.kind === "slide" || node.data.role === "slide" || Object.hasOwn(node.data, "slide");
}
function buildPptxsvg(root) {
    const nodes = flatten(root);
    const slides = nodes.filter(isSlide);
    const selectedSlides = slides.length ? slides : [root];
    const rootMeta = asObject(asObject(root.metadata.json).presentation);
    const rootBox = viewBox(root);
    const metaSlideSize = asObject(rootMeta.slideSize);
    const slideSize = typeof metaSlideSize.width === "number" && typeof metaSlideSize.height === "number"
        ? [metaSlideSize.width, metaSlideSize.height]
        : [rootBox[2] || 960, rootBox[3] || 540];
    const slideItems = selectedSlides.map((node, index) => ({
        slide_id: node.attributes.id || node.data.slide || `slide-${index + 1}`,
        node_id: node.node_id,
        title: nodeTitle(node),
        view_box: viewBox(node),
        data: node.data,
        metadata: node.metadata,
    }));
    const baseParts = [
        ["/ppt/presentation.xml", "presentation", null],
        ["/ppt/slideMasters/slideMaster1.xml", "slide-master", null],
        ["/ppt/slideLayouts/slideLayout1.xml", "slide-layout", null],
        ["/ppt/theme/theme1.xml", "theme", null],
    ];
    return {
        kind: "pptxsvg",
        slide_size: slideSize,
        slides: slideItems,
        parts: [
            ...baseParts.map(([part_name, kind, source_node_id]) => ({ part_name, kind, source_node_id })),
            ...slideItems.map((slide, index) => ({
                part_name: `/ppt/slides/slide${index + 1}.xml`,
                kind: "slide",
                source_node_id: slide.node_id,
            })),
        ],
        masters: templates(nodes, rootMeta.masters ?? null, "slide-master"),
        layouts: templates(nodes, rootMeta.layouts ?? null, "slide-layout"),
        guides: guides(nodes, rootMeta.guides ?? null),
        rulers: rulers(nodes, rootMeta.rulers ?? null),
        text_styles: textStyles(nodes, rootMeta.textStyles || rootMeta.text_styles || null),
        metadata: rootMeta,
    };
}
function templates(nodes, metadataItems, kind) {
    const items = Array.isArray(metadataItems) ? metadataItems : [];
    const fromMeta = items.map((item, index) => {
        const obj = asObject(item);
        return {
            template_id: String(obj.id || obj.name || `${kind}-${index + 1}`),
            kind,
            node_id: null,
            data: {},
            metadata: item,
        };
    });
    const fromNodes = nodes
        .filter((node) => node.data.kind === kind || node.data.role === kind)
        .map((node) => ({
        template_id: node.attributes.id || node.data.template || node.node_id,
        kind,
        node_id: node.node_id,
        data: node.data,
        metadata: node.metadata.json || node.metadata.text || null,
    }));
    return [...fromMeta, ...fromNodes];
}
function guides(nodes, metadataItems) {
    const items = Array.isArray(metadataItems) ? metadataItems : [];
    const fromMeta = items.map((item, index) => {
        const obj = asObject(item);
        return {
            guide_id: String(obj.id || `guide-${index + 1}`),
            orientation: String(obj.orientation || "vertical"),
            position: Number(obj.position || 0),
            unit: String(obj.unit || "px"),
            node_id: null,
        };
    });
    const fromNodes = nodes
        .filter((node) => node.data.kind === "guide" || node.data.role === "guide")
        .map((node) => ({
        guide_id: node.attributes.id || node.node_id,
        orientation: node.data.orientation || (node.attributes.y ? "horizontal" : "vertical"),
        position: Number(node.data.position || node.attributes.x || node.attributes.y || 0),
        unit: node.data.unit || "px",
        node_id: node.node_id,
    }));
    return [...fromMeta, ...fromNodes];
}
function rulers(nodes, metadataItems) {
    const items = Array.isArray(metadataItems) ? metadataItems : [];
    const fromMeta = items.map((item, index) => {
        const obj = asObject(item);
        return {
            ruler_id: String(obj.id || `ruler-${index + 1}`),
            orientation: String(obj.orientation || "horizontal"),
            origin: Number(obj.origin || 0),
            unit: String(obj.unit || "px"),
            spacing: obj.spacing == null ? null : Number(obj.spacing),
            node_id: null,
        };
    });
    const fromNodes = nodes
        .filter((node) => node.data.kind === "ruler" || node.data.role === "ruler")
        .map((node) => ({
        ruler_id: node.attributes.id || node.node_id,
        orientation: node.data.orientation || "horizontal",
        origin: Number(node.data.origin || 0),
        unit: node.data.unit || "px",
        spacing: node.data.spacing == null ? null : Number(node.data.spacing),
        node_id: node.node_id,
    }));
    return [...fromMeta, ...fromNodes];
}
function textStyles(nodes, metadataStyles) {
    const styleObj = !Array.isArray(metadataStyles) ? asObject(metadataStyles) : {};
    const fromMeta = Object.entries(styleObj).map(([role, properties]) => ({
        style_id: role,
        role,
        properties: asObject(properties),
        node_id: null,
    }));
    const fromNodes = nodes
        .filter((node) => node.data.kind === "style-template" || node.data.role === "style-template")
        .map((node) => ({
        style_id: node.attributes.id || node.data.style || node.node_id,
        role: node.data.role || node.data.style || node.attributes.id || node.node_id,
        properties: { ...node.attributes, ...node.data },
        node_id: node.node_id,
    }));
    return [...fromMeta, ...fromNodes];
}
function buildIr(svgText) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgText, "image/svg+xml");
    const error = doc.querySelector("parsererror");
    if (error)
        throw new Error((error.textContent || "").trim());
    const root = nodeToIr(doc.documentElement, "n0");
    const dependencies = flatten(root).flatMap((node) => node.dependencies);
    const presentation = buildPptxsvg(root);
    return {
        version: "0.2-web-ts",
        root,
        metadata: root.metadata,
        dependencies,
        presentation,
    };
}
function svgToPptx(svgText) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgText, "image/svg+xml");
    const error = doc.querySelector("parsererror");
    if (error)
        throw new Error((error.textContent || "").trim());
    const root = doc.documentElement;
    const ir = buildIr(svgText);
    const slides = declaredSlides(root);
    const selectedSlides = slides.length ? slides : [root];
    const slideXmls = selectedSlides.map((slide, index) => buildSlideXml(slide, index + 1));
    return writePptx(slideXmls, ir.presentation.slide_size);
}
function declaredSlides(root) {
    const result = [];
    const walk = (element) => {
        if (isSlideElement(element)) {
            result.push(element);
            return;
        }
        for (const child of Array.from(element.children)) {
            if (localName(child) !== "metadata")
                walk(child);
        }
    };
    walk(root);
    return result;
}
function isSlideElement(element) {
    return element.getAttribute("data-kind") === "slide" || element.getAttribute("data-role") === "slide" || element.hasAttribute("data-slide");
}
function buildSlideXml(slide, slideIndex) {
    const shapes = extractShapes(slide);
    markRelationConnectors(shapes);
    const body = shapes.map((shape) => shapeToXml(shape)).join("");
    return xmlDecl(`<p:sld xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>${body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`);
}
function extractShapes(root) {
    const shapes = [];
    const css = collectCss(root);
    const refs = collectRefs(root);
    let nextId = 2;
    const walk = (element, matrix, inheritedStyle, refStack) => {
        const tag = localName(element);
        if (tag === "metadata" || tag === "defs" || tag === "style")
            return;
        const ownMatrix = multiply(matrix, transformMatrix(element.getAttribute("transform")));
        const ownStyle = computedStyle(element, inheritedStyle, css);
        if (tag === "use") {
            const href = element.getAttribute("href") || element.getAttribute("xlink:href") || "";
            const refId = href.startsWith("#") ? href.slice(1) : "";
            const ref = refs.get(refId);
            if (ref && !refStack.has(refId)) {
                const useMatrix = multiply(ownMatrix, [1, 0, 0, 1, num(element, "x"), num(element, "y")]);
                walk(ref, useMatrix, ownStyle, new Set([...refStack, refId]));
            }
            return;
        }
        if (tag === "g" && (element.getAttribute("data-kind") === "table" || element.getAttribute("data-role") === "table")) {
            const table = tableFromGroup(element, ownMatrix, nextId, ownStyle, css);
            if (table) {
                shapes.push(table);
                nextId += 1;
            }
            return;
        }
        const shape = elementToShape(element, ownMatrix, ownStyle, nextId);
        if (shape) {
            shapes.push(shape);
            nextId += 1;
        }
        for (const child of Array.from(element.children))
            walk(child, ownMatrix, ownStyle, refStack);
    };
    const rootStyle = computedStyle(root, {}, css);
    for (const child of Array.from(root.children))
        walk(child, [1, 0, 0, 1, 0, 0], rootStyle, new Set());
    return shapes;
}
function elementToShape(element, matrix, style, id) {
    const tag = localName(element);
    const data = dataAttrs(attrs(element));
    const name = element.getAttribute("id") || tag;
    if (tag === "rect") {
        const box = transformedBox(matrix, num(element, "x"), num(element, "y"), num(element, "width"), num(element, "height"));
        return {
            id,
            kind: "rect",
            name,
            data,
            x: box.x,
            y: box.y,
            width: box.width,
            height: box.height,
            rx: num(element, "rx"),
            fill: style.fill ?? "#000000",
            stroke: style.stroke ?? null,
            strokeWidth: style.strokeWidth ?? 1,
        };
    }
    if (tag === "circle" || tag === "ellipse") {
        const cx = num(element, "cx");
        const cy = num(element, "cy");
        const rx = tag === "circle" ? num(element, "r") : num(element, "rx");
        const ry = tag === "circle" ? num(element, "r") : num(element, "ry");
        const box = transformedBox(matrix, cx - rx, cy - ry, rx * 2, ry * 2);
        return {
            id,
            kind: "ellipse",
            name,
            data,
            x: box.x,
            y: box.y,
            width: box.width,
            height: box.height,
            fill: style.fill ?? "#000000",
            stroke: style.stroke ?? null,
            strokeWidth: style.strokeWidth ?? 1,
        };
    }
    if (tag === "line") {
        const [x1, y1] = point(matrix, num(element, "x1"), num(element, "y1"));
        const [x2, y2] = point(matrix, num(element, "x2"), num(element, "y2"));
        return {
            id,
            kind: "line",
            name,
            data,
            x1,
            y1,
            x2,
            y2,
            stroke: style.stroke ?? "#111827",
            strokeWidth: style.strokeWidth ?? 1,
            relation: data.kind === "relation" || data.role === "relation",
            startId: null,
            endId: null,
            markerStart: style.markerStart ?? false,
            markerEnd: style.markerEnd ?? false,
        };
    }
    if (tag === "text") {
        const fontSize = style.fontSize ?? 18;
        const [x, y] = point(matrix, num(element, "x"), num(element, "y"));
        return {
            id,
            kind: "text",
            name,
            data,
            x,
            y: y - fontSize,
            width: Math.max(80, (element.textContent || "").trim().length * fontSize * 0.62),
            height: fontSize * 1.35,
            text: (element.textContent || "").trim(),
            fill: style.fill ?? "#111827",
            fontSize,
            fontFamily: style.fontFamily || "Aptos",
            bold: ["bold", "700", "800", "900"].includes(style.fontWeight || ""),
        };
    }
    if (tag === "polygon" || tag === "polyline") {
        const points = parsePoints(element.getAttribute("points") || "").map(([x, y]) => point(matrix, x, y));
        if (points.length >= 2) {
            return {
                id,
                kind: "freeform",
                name,
                data,
                points,
                closed: tag === "polygon",
                fill: tag === "polygon" ? (style.fill ?? "#000000") : null,
                stroke: style.stroke ?? "#111827",
                strokeWidth: style.strokeWidth ?? 1,
                markerStart: style.markerStart ?? false,
                markerEnd: style.markerEnd ?? false,
            };
        }
    }
    if (tag === "path") {
        const parsed = parseBasicPath(element.getAttribute("d") || "", matrix);
        if (parsed && parsed.points.length >= 2) {
            return {
                id,
                kind: "freeform",
                name,
                data,
                points: parsed.points,
                closed: parsed.closed,
                fill: parsed.closed ? (style.fill ?? "#000000") : null,
                stroke: style.stroke ?? "#111827",
                strokeWidth: style.strokeWidth ?? 1,
                markerStart: style.markerStart ?? false,
                markerEnd: style.markerEnd ?? false,
            };
        }
    }
    if (tag === "image") {
        const href = element.getAttribute("href") || element.getAttribute("xlink:href") || "";
        if (supportedDataImage(href)) {
            const box = transformedBox(matrix, num(element, "x"), num(element, "y"), num(element, "width"), num(element, "height"));
            return {
                id,
                kind: "image",
                name,
                data,
                x: box.x,
                y: box.y,
                width: box.width,
                height: box.height,
                href,
            };
        }
    }
    return null;
}
function tableFromGroup(group, matrix, id, inheritedStyle, css = []) {
    const rects = Array.from(group.querySelectorAll("rect")).filter((rect) => rect.getAttribute("data-kind") === "cell" || rect.getAttribute("data-role") === "cell");
    if (!rects.length)
        return null;
    const cells = rects.map((rect) => {
        const style = computedStyle(rect, inheritedStyle, css);
        const [x, y] = point(matrix, num(rect, "x"), num(rect, "y"));
        return {
            row: Number(rect.getAttribute("data-row") || 0),
            col: Number(rect.getAttribute("data-col") || 0),
            x,
            y,
            width: num(rect, "width"),
            height: num(rect, "height"),
            fill: style.fill ?? "#ffffff",
        };
    });
    const xEdges = edges(cells.flatMap((cell) => [cell.x, cell.x + cell.width]));
    const yEdges = edges(cells.flatMap((cell) => [cell.y, cell.y + cell.height]));
    if (xEdges.length < 2 || yEdges.length < 2)
        return null;
    const minX = xEdges[0] || 0;
    const minY = yEdges[0] || 0;
    const tableCells = cells.map((cell) => ({
        row: cell.row,
        col: cell.col,
        text: "",
        fill: cell.fill,
    }));
    return {
        id,
        kind: "table",
        name: group.getAttribute("id") || "table",
        data: dataAttrs(attrs(group)),
        x: minX,
        y: minY,
        columns: xEdges.slice(1).map((edge, index) => edge - (xEdges[index] || 0)),
        rows: yEdges.slice(1).map((edge, index) => edge - (yEdges[index] || 0)),
        cells: tableCells,
    };
}
function markRelationConnectors(shapes) {
    const boxes = shapes.filter((shape) => ["rect", "ellipse", "text", "freeform"].includes(shape.kind));
    for (const line of shapes.filter((shape) => shape.kind === "line" && shape.relation)) {
        line.startId = nearestShapeId(line.x1, line.y1, boxes);
        line.endId = nearestShapeId(line.x2, line.y2, boxes);
    }
}
function nearestShapeId(x, y, shapes) {
    if (!shapes.length)
        return null;
    return shapes
        .map((shape) => {
        const box = shapeBox(shape);
        const dx = Math.max(box.x - x, 0, x - (box.x + box.width));
        const dy = Math.max(box.y - y, 0, y - (box.y + box.height));
        return { id: shape.id, distance: dx * dx + dy * dy };
    })
        .sort((a, b) => a.distance - b.distance)[0]?.id ?? null;
}
function shapeBox(shape) {
    if (shape.kind === "freeform") {
        const xs = shape.points.map(([x]) => x);
        const ys = shape.points.map(([, y]) => y);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
    }
    return { x: shape.x, y: shape.y, width: shape.width, height: shape.height };
}
function shapeToXml(shape) {
    if (shape.kind === "rect")
        return rectXml(shape);
    if (shape.kind === "ellipse")
        return ellipseXml(shape);
    if (shape.kind === "line")
        return shape.relation ? connectorXml(shape) : lineXml(shape);
    if (shape.kind === "text")
        return textXml(shape);
    if (shape.kind === "freeform")
        return freeformXml(shape);
    if (shape.kind === "image")
        return imageXml(shape);
    return tableXml(shape);
}
function rectXml(shape) {
    return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, shape.rx ? "roundRect" : "rect", fillXml(shape.fill) + lineStyleXml(shape.stroke, shape.strokeWidth), "");
}
function ellipseXml(shape) {
    return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, "ellipse", fillXml(shape.fill) + lineStyleXml(shape.stroke, shape.strokeWidth), "");
}
function lineXml(shape) {
    const x = Math.min(shape.x1, shape.x2);
    const y = Math.min(shape.y1, shape.y2);
    const width = Math.max(Math.abs(shape.x2 - shape.x1), 1);
    const height = Math.max(Math.abs(shape.y2 - shape.y1), 1);
    return spXml(shape.id, shape.name, x, y, width, height, "line", `<a:noFill/>${lineStyleXml(shape.stroke, shape.strokeWidth, { head: shape.markerEnd, tail: shape.markerStart })}`, "");
}
function connectorXml(shape) {
    const x = Math.min(shape.x1, shape.x2);
    const y = Math.min(shape.y1, shape.y2);
    const width = Math.max(Math.abs(shape.x2 - shape.x1), 1);
    const height = Math.max(Math.abs(shape.y2 - shape.y1), 1);
    const cxn = `${shape.startId ? `<a:stCxn id="${shape.startId}" idx="0"/>` : ""}${shape.endId ? `<a:endCxn id="${shape.endId}" idx="0"/>` : ""}`;
    return `<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvCxnSpPr>${cxn}</p:cNvCxnSpPr><p:nvPr/></p:nvCxnSpPr><p:spPr><a:xfrm><a:off x="${emu(x)}" y="${emu(y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>${lineStyleXml(shape.stroke, shape.strokeWidth, { head: true, tail: shape.markerStart })}</p:spPr></p:cxnSp>`;
}
function textXml(shape) {
    const body = `<p:txBody><a:bodyPr wrap="none"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="${Math.round(shape.fontSize * 100)}"${shape.bold ? ' b="1"' : ""}>${solidColorXml(shape.fill)}<a:latin typeface="${xml(shape.fontFamily)}"/></a:rPr><a:t>${xml(shape.text)}</a:t></a:r></a:p></p:txBody>`;
    return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, "rect", "<a:noFill/><a:ln><a:noFill/></a:ln>", body);
}
function tableXml(shape) {
    const grid = shape.columns.map((width) => `<a:gridCol w="${emu(width)}"/>`).join("");
    const rows = shape.rows
        .map((height, rowIndex) => {
        const cells = shape.columns
            .map((_, colIndex) => {
            const cell = shape.cells.find((item) => item.row === rowIndex && item.col === colIndex);
            return `<a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p>${cell?.text ? `<a:r><a:t>${xml(cell.text)}</a:t></a:r>` : ""}</a:p></a:txBody><a:tcPr>${fillXml(cell?.fill || "#ffffff")}</a:tcPr></a:tc>`;
        })
            .join("");
        return `<a:tr h="${emu(height)}">${cells}</a:tr>`;
    })
        .join("");
    return `<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="${emu(shape.x)}" y="${emu(shape.y)}"/><a:ext cx="${emu(shape.columns.reduce((a, b) => a + b, 0))}" cy="${emu(shape.rows.reduce((a, b) => a + b, 0))}"/></p:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"><a:tbl><a:tblPr firstRow="1" bandRow="1"/><a:tblGrid>${grid}</a:tblGrid>${rows}</a:tbl></a:graphicData></a:graphic></p:graphicFrame>`;
}
function freeformXml(shape) {
    const box = shapeBox(shape);
    const width = Math.max(box.width, 1);
    const height = Math.max(box.height, 1);
    const local = shape.points.map(([x, y]) => [emu(x - box.x), emu(y - box.y)]);
    const [first, ...rest] = local;
    if (!first)
        return "";
    const commands = [`<a:moveTo><a:pt x="${first[0]}" y="${first[1]}"/></a:moveTo>`]
        .concat(rest.map(([x, y]) => `<a:lnTo><a:pt x="${x}" y="${y}"/></a:lnTo>`))
        .concat(shape.closed ? ["<a:close/>"] : [])
        .join("");
    const geom = `<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/><a:pathLst><a:path w="${emu(width)}" h="${emu(height)}">${commands}</a:path></a:pathLst></a:custGeom>`;
    return `<p:sp><p:nvSpPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="${emu(box.x)}" y="${emu(box.y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm>${geom}${fillXml(shape.fill)}${lineStyleXml(shape.stroke, shape.strokeWidth, { head: shape.markerEnd, tail: shape.markerStart })}</p:spPr></p:sp>`;
}
function imageXml(shape) {
    return `<p:pic><p:nvPicPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="${xml(shape.href)}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="${emu(shape.x)}" y="${emu(shape.y)}"/><a:ext cx="${emu(shape.width)}" cy="${emu(shape.height)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>`;
}
function spXml(id, name, x, y, width, height, prst, style, body) {
    return `<p:sp><p:nvSpPr><p:cNvPr id="${id}" name="${xml(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="${emu(x)}" y="${emu(y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm><a:prstGeom prst="${prst}"><a:avLst/></a:prstGeom>${style}</p:spPr>${body}</p:sp>`;
}
function fillXml(color) {
    return color ? `<a:solidFill><a:srgbClr val="${hex(color)}"/></a:solidFill>` : "<a:noFill/>";
}
function solidColorXml(color) {
    return color ? `<a:solidFill><a:srgbClr val="${hex(color)}"/></a:solidFill>` : "";
}
function lineStyleXml(color, width, arrows = {}) {
    if (!color || width <= 0)
        return "<a:ln><a:noFill/></a:ln>";
    return `<a:ln w="${emu(width)}"><a:solidFill><a:srgbClr val="${hex(color)}"/></a:solidFill>${arrows.tail ? '<a:tailEnd type="triangle"/>' : ""}${arrows.head ? '<a:headEnd type="triangle"/>' : ""}</a:ln>`;
}
function writePptx(slideXmls, slideSize) {
    const files = {
        "[Content_Types].xml": contentTypes(slideXmls.length),
        "_rels/.rels": rootRels,
        "docProps/app.xml": appProps(slideXmls.length),
        "docProps/core.xml": coreProps,
        "ppt/presentation.xml": presentationXml(slideXmls.length, slideSize),
        "ppt/_rels/presentation.xml.rels": presentationRels(slideXmls.length),
        "ppt/slideMasters/slideMaster1.xml": slideMaster,
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": slideMasterRels,
        "ppt/slideLayouts/slideLayout1.xml": slideLayout,
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": slideLayoutRels,
        "ppt/theme/theme1.xml": themeXml,
    };
    let nextMediaIndex = 1;
    slideXmls.forEach((slide, index) => {
        const prepared = prepareSlideMedia(slide, nextMediaIndex);
        nextMediaIndex += Object.keys(prepared.media).length;
        files[`ppt/slides/slide${index + 1}.xml`] = prepared.xml;
        files[`ppt/slides/_rels/slide${index + 1}.xml.rels`] = prepared.rels;
        Object.assign(files, prepared.media);
    });
    return zipStore(files);
}
function prepareSlideMedia(slideXml, firstMediaIndex) {
    const media = {};
    const relationships = [slideLayoutRel];
    let nextRelId = 2;
    let nextMediaIndex = firstMediaIndex;
    const xml = slideXml.replace(/r:embed="(data:image\/(png|jpeg|jpg|gif|webp);base64,([^"]+))"/gi, (_match, _uri, kind, payload) => {
        const extension = kind.toLowerCase() === "jpeg" ? "jpg" : kind.toLowerCase();
        const relId = `rId${nextRelId}`;
        const path = `ppt/media/image${nextMediaIndex}.${extension}`;
        media[path] = base64Bytes(payload);
        relationships.push(`<Relationship Id="${relId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image${nextMediaIndex}.${extension}"/>`);
        nextRelId += 1;
        nextMediaIndex += 1;
        return `r:embed="${relId}"`;
    });
    return {
        xml,
        rels: xmlDecl(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${relationships.join("")}</Relationships>`),
        media,
    };
}
function base64Bytes(value) {
    const binary = atob(value.replace(/\s+/g, ""));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
}
function zipStore(files) {
    const encoder = new TextEncoder();
    const chunks = [];
    const central = [];
    let offset = 0;
    for (const [name, content] of Object.entries(files)) {
        const nameBytes = encoder.encode(name);
        const data = typeof content === "string" ? encoder.encode(content) : content;
        const crc = crc32(data);
        const local = concat([
            u32(0x04034b50),
            u16(20),
            u16(0),
            u16(0),
            u16(0),
            u16(0),
            u32(crc),
            u32(data.length),
            u32(data.length),
            u16(nameBytes.length),
            u16(0),
            nameBytes,
            data,
        ]);
        chunks.push(local);
        central.push(concat([
            u32(0x02014b50),
            u16(20),
            u16(20),
            u16(0),
            u16(0),
            u16(0),
            u16(0),
            u32(crc),
            u32(data.length),
            u32(data.length),
            u16(nameBytes.length),
            u16(0),
            u16(0),
            u16(0),
            u16(0),
            u32(0),
            u32(offset),
            nameBytes,
        ]));
        offset += local.length;
    }
    const centralOffset = offset;
    const centralData = concat(central);
    const end = concat([u32(0x06054b50), u16(0), u16(0), u16(central.length), u16(central.length), u32(centralData.length), u32(centralOffset), u16(0)]);
    return concat([...chunks, centralData, end]);
}
function crc32(data) {
    let crc = 0xffffffff;
    for (const byte of data) {
        crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 0xff];
    }
    return (crc ^ 0xffffffff) >>> 0;
}
const crcTable = Array.from({ length: 256 }, (_, index) => {
    let c = index;
    for (let k = 0; k < 8; k += 1)
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
});
function u16(value) {
    return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}
function u32(value) {
    return new Uint8Array([value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]);
}
function concat(chunks) {
    const output = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
    let offset = 0;
    for (const chunk of chunks) {
        output.set(chunk, offset);
        offset += chunk.length;
    }
    return output;
}
function render() {
    try {
        const text = source.value;
        state.ir = buildIr(text);
        state.pptxsvg = state.ir.presentation;
        preview.innerHTML = text;
    }
    catch (error) {
        preview.innerHTML = "";
        state.ir = null;
        state.pptxsvg = null;
        panel.innerHTML = `<div class="notice">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
        return;
    }
    renderPanel();
}
function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}
function renderPanel() {
    if (!state.ir || !state.pptxsvg)
        return;
    const nodes = flatten(state.ir.root);
    const semantic = nodes.filter((node) => Object.keys(node.data).length > 0).length;
    const deps = state.ir.dependencies.length;
    const templatesCount = state.pptxsvg.masters.length + state.pptxsvg.layouts.length + state.pptxsvg.text_styles.length;
    if (state.tab === "summary") {
        panel.innerHTML = `
      <div class="metrics">
        <div class="metric"><strong>${nodes.length}</strong><span>SVG IR nodes</span></div>
        <div class="metric"><strong>${state.pptxsvg.slides.length}</strong><span>PPTXSVG slides</span></div>
        <div class="metric"><strong>${semantic}</strong><span>semantic nodes</span></div>
        <div class="metric"><strong>${templatesCount}</strong><span>templates</span></div>
        <div class="metric"><strong>${deps}</strong><span>dependencies</span></div>
        <div class="metric"><strong>${state.pptxsvg.guides.length + state.pptxsvg.rulers.length}</strong><span>guides/rulers</span></div>
      </div>
      <div class="list">
        ${nodes.slice(0, 12).map((node) => `<div class="item"><div class="item-title">${escapeHtml(node.node_id)} · ${escapeHtml(node.tag)}</div><div class="item-meta">${escapeHtml(JSON.stringify(node.data))}</div></div>`).join("")}
      </div>`;
    }
    else if (state.tab === "slides") {
        panel.innerHTML = `<div class="list">${state.pptxsvg.slides.map((slide) => `<div class="item"><div class="item-title">${escapeHtml(slide.slide_id)}${slide.title ? ` · ${escapeHtml(slide.title)}` : ""}</div><div class="item-meta">${escapeHtml(slide.node_id)} · viewBox ${slide.view_box.join(" ")}</div></div>`).join("")}</div>`;
    }
    else if (state.tab === "assistant") {
        panel.innerHTML = `
      <div class="notice">Web LLM integration is designed as a local WebGPU worker. Conversion is deterministic and runs fully in this page.</div>
      <div class="status"><span class="dot ${state.webgpu ? "ok" : ""}"></span>${state.webgpu ? "WebGPU available" : "WebGPU unavailable or blocked"}</div>
      <pre style="margin-top:12px">${escapeHtml(JSON.stringify({
            backendPolicy: state.webgpu ? "webgpu" : "wasm-or-disabled",
            allowedOps: ["mark-slide", "set-data", "set-metadata", "mark-table", "bind-relation"],
            model: "onnx-community/gemma-4-e2b-it-ONNX"
        }, null, 2))}</pre>`;
    }
    else {
        panel.innerHTML = `<pre>${escapeHtml(JSON.stringify(state.ir, null, 2))}</pre>`;
    }
}
function downloadText(name, value) {
    downloadBlob(name, new Blob([value], { type: "application/json;charset=utf-8" }));
}
function downloadBlob(name, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
}
document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        state.tab = tab.dataset.tab || "summary";
        document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
        renderPanel();
    });
});
mustElement("openBtn").addEventListener("click", () => fileInput.click());
mustElement("sampleBtn").addEventListener("click", () => {
    source.value = sampleSvg;
    render();
});
mustElement("downloadIrBtn").addEventListener("click", () => {
    if (state.ir)
        downloadText("pptxsvg-ir.json", JSON.stringify(state.ir, null, 2));
});
mustElement("downloadPptxsvgBtn").addEventListener("click", () => {
    if (state.pptxsvg)
        downloadText("pptxsvg.json", JSON.stringify(state.pptxsvg, null, 2));
});
mustElement("downloadPptxBtn").addEventListener("click", () => {
    const bytes = svgToPptx(source.value);
    const data = new Uint8Array(bytes.byteLength);
    data.set(bytes);
    downloadBlob("pptxsvg-web.pptx", new Blob([data], { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" }));
});
fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file)
        return;
    source.value = await file.text();
    render();
});
source.addEventListener("input", render);
async function checkWebGpu() {
    const nav = navigator;
    if (!nav.gpu) {
        state.webgpu = false;
        renderPanel();
        return;
    }
    try {
        state.webgpu = Boolean(await nav.gpu.requestAdapter());
    }
    catch (_) {
        state.webgpu = false;
    }
    renderPanel();
}
source.value = sampleSvg;
render();
void checkWebGpu();
function asObject(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return {};
    return value;
}
function num(element, name, fallback = 0) {
    const value = Number(element.getAttribute(name));
    return Number.isFinite(value) ? value : fallback;
}
function computedStyle(element, inherited, css = []) {
    const cssDeclarations = matchingCssDeclarations(element, css);
    const inlineDeclarations = styleDeclarations(element.getAttribute("style"));
    const value = (name) => inlineDeclarations[name] ?? element.getAttribute(name) ?? cssDeclarations[name] ?? null;
    const next = { ...inherited };
    const fill = value("fill");
    const stroke = value("stroke");
    const strokeWidth = value("stroke-width");
    const fontSize = value("font-size");
    const fontFamily = value("font-family");
    const fontWeight = value("font-weight");
    const marker = value("marker");
    const markerStart = value("marker-start");
    const markerEnd = value("marker-end");
    if (fill != null)
        next.fill = normalizePaint(fill);
    if (stroke != null)
        next.stroke = normalizePaint(stroke);
    if (strokeWidth != null)
        next.strokeWidth = parseLength(strokeWidth, next.strokeWidth ?? 1);
    if (fontSize != null)
        next.fontSize = parseLength(fontSize, next.fontSize ?? 18);
    if (fontFamily != null)
        next.fontFamily = fontFamily.replace(/^['"]|['"]$/g, "");
    if (fontWeight != null)
        next.fontWeight = fontWeight;
    if (marker != null) {
        const enabled = marker !== "none";
        next.markerStart = enabled;
        next.markerEnd = enabled;
    }
    if (markerStart != null)
        next.markerStart = markerStart !== "none";
    if (markerEnd != null)
        next.markerEnd = markerEnd !== "none";
    return next;
}
function collectCss(root) {
    const rules = [];
    let order = 0;
    for (const style of Array.from(root.querySelectorAll("style"))) {
        const text = style.textContent || "";
        for (const match of text.matchAll(/([^{}]+)\{([^{}]+)\}/g)) {
            const selectorText = (match[1] || "").trim();
            const body = match[2] || "";
            if (!selectorText || selectorText.startsWith("@"))
                continue;
            for (const selector of selectorText.split(",").map((item) => item.trim()).filter(Boolean)) {
                rules.push({ selector, declarations: styleDeclarations(body), order });
                order += 1;
            }
        }
    }
    return rules;
}
function collectRefs(root) {
    const refs = new Map();
    const walk = (element) => {
        const id = element.getAttribute("id");
        if (id)
            refs.set(id, element);
        for (const child of Array.from(element.children))
            walk(child);
    };
    walk(root);
    return refs;
}
function matchingCssDeclarations(element, css) {
    const declarations = {};
    for (const rule of css) {
        if (!matchesSelector(element, rule.selector))
            continue;
        Object.assign(declarations, rule.declarations);
    }
    return declarations;
}
function matchesSelector(element, selector) {
    try {
        return element.matches(selector);
    }
    catch (_) {
        return false;
    }
}
function styleDeclarations(style) {
    if (!style)
        return {};
    return Object.fromEntries(style
        .split(";")
        .map((entry) => entry.split(":"))
        .filter((parts) => parts.length >= 2 && Boolean(parts[0]?.trim()))
        .map(([name, ...value]) => [name.trim(), value.join(":").trim()]));
}
function normalizePaint(value) {
    const trimmed = value.trim();
    if (!trimmed || trimmed === "none" || trimmed === "transparent")
        return null;
    return trimmed;
}
function parseLength(value, fallback = 0) {
    if (!value)
        return fallback;
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}
function supportedDataImage(value) {
    return /^data:image\/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/i.test(value);
}
function edges(values) {
    return [...new Set(values.map((value) => Math.round(value * 1000) / 1000))].sort((a, b) => a - b);
}
function transformMatrix(value) {
    if (!value)
        return [1, 0, 0, 1, 0, 0];
    let matrix = [1, 0, 0, 1, 0, 0];
    for (const match of value.matchAll(/(matrix|translate|scale|rotate)\(([^)]*)\)/g)) {
        const kind = match[1];
        const args = (match[2] || "").replaceAll(",", " ").trim().split(/\s+/).map(Number).filter((item) => Number.isFinite(item));
        let next = [1, 0, 0, 1, 0, 0];
        if (kind === "matrix" && args.length >= 6) {
            next = [args[0], args[1], args[2], args[3], args[4], args[5]];
        }
        else if (kind === "translate") {
            next = [1, 0, 0, 1, args[0] || 0, args[1] || 0];
        }
        else if (kind === "scale") {
            next = [args[0] ?? 1, 0, 0, args[1] ?? args[0] ?? 1, 0, 0];
        }
        else if (kind === "rotate") {
            const angle = ((args[0] || 0) * Math.PI) / 180;
            const cos = Math.cos(angle);
            const sin = Math.sin(angle);
            const cx = args[1] || 0;
            const cy = args[2] || 0;
            next = multiply(multiply([1, 0, 0, 1, cx, cy], [cos, sin, -sin, cos, 0, 0]), [1, 0, 0, 1, -cx, -cy]);
        }
        matrix = multiply(matrix, next);
    }
    return matrix;
}
function multiply(a, b) {
    return [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]];
}
function point(m, x, y) {
    return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}
function transformedBox(matrix, x, y, width, height) {
    const points = [point(matrix, x, y), point(matrix, x + width, y), point(matrix, x + width, y + height), point(matrix, x, y + height)];
    const xs = points.map(([px]) => px);
    const ys = points.map(([, py]) => py);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
}
function parsePoints(value) {
    const numbers = value.replaceAll(",", " ").trim().split(/\s+/).map(Number).filter((item) => Number.isFinite(item));
    const points = [];
    for (let index = 0; index + 1 < numbers.length; index += 2) {
        points.push([numbers[index], numbers[index + 1]]);
    }
    return points;
}
function parseBasicPath(value, matrix) {
    const tokens = value.match(/[MmLlHhVvCcSsQqTtZz]|[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[eE][-+]?\d+)?/g) || [];
    const points = [];
    let command = "";
    let index = 0;
    let x = 0;
    let y = 0;
    let start = null;
    let lastCubicControl = null;
    let lastQuadControl = null;
    let closed = false;
    const nextNumber = () => {
        const token = tokens[index++];
        return token == null ? null : Number(token);
    };
    const nextPoint = (relative) => {
        const nx = nextNumber();
        const ny = nextNumber();
        if (nx == null || ny == null || !Number.isFinite(nx) || !Number.isFinite(ny))
            return null;
        return relative ? [x + nx, y + ny] : [nx, ny];
    };
    const pushPoint = (raw) => {
        const transformed = point(matrix, raw[0], raw[1]);
        if (!start)
            start = transformed;
        points.push(transformed);
    };
    while (index < tokens.length) {
        const token = tokens[index];
        if (/^[A-Za-z]$/.test(token)) {
            command = token;
            index += 1;
        }
        if (!/[MmLlHhVvCcSsQqTtZz]/.test(command))
            return null;
        if (command === "Z" || command === "z") {
            closed = true;
            if (start)
                points.push(start);
            continue;
        }
        if (command === "H" || command === "h") {
            const nx = nextNumber();
            if (nx == null)
                return null;
            x = command === "h" ? x + nx : nx;
            pushPoint([x, y]);
            lastCubicControl = null;
            lastQuadControl = null;
        }
        else if (command === "V" || command === "v") {
            const ny = nextNumber();
            if (ny == null)
                return null;
            y = command === "v" ? y + ny : ny;
            pushPoint([x, y]);
            lastCubicControl = null;
            lastQuadControl = null;
        }
        else if (command === "M" || command === "m" || command === "L" || command === "l") {
            const next = nextPoint(command === "m" || command === "l");
            if (!next)
                return null;
            [x, y] = next;
            pushPoint([x, y]);
            if (command === "M")
                command = "L";
            if (command === "m")
                command = "l";
            lastCubicControl = null;
            lastQuadControl = null;
        }
        else if (command === "C" || command === "c") {
            const c1 = nextPoint(command === "c");
            const c2 = nextPoint(command === "c");
            const end = nextPoint(command === "c");
            if (!c1 || !c2 || !end)
                return null;
            for (const curve of cubicPoints([x, y], c1, c2, end))
                pushPoint(curve);
            [x, y] = end;
            lastCubicControl = c2;
            lastQuadControl = null;
        }
        else if (command === "S" || command === "s") {
            const c1 = lastCubicControl ? [x * 2 - lastCubicControl[0], y * 2 - lastCubicControl[1]] : [x, y];
            const c2 = nextPoint(command === "s");
            const end = nextPoint(command === "s");
            if (!c2 || !end)
                return null;
            for (const curve of cubicPoints([x, y], c1, c2, end))
                pushPoint(curve);
            [x, y] = end;
            lastCubicControl = c2;
            lastQuadControl = null;
        }
        else if (command === "Q" || command === "q") {
            const control = nextPoint(command === "q");
            const end = nextPoint(command === "q");
            if (!control || !end)
                return null;
            for (const curve of quadraticPoints([x, y], control, end))
                pushPoint(curve);
            [x, y] = end;
            lastQuadControl = control;
            lastCubicControl = null;
        }
        else if (command === "T" || command === "t") {
            const control = lastQuadControl ? [x * 2 - lastQuadControl[0], y * 2 - lastQuadControl[1]] : [x, y];
            const end = nextPoint(command === "t");
            if (!end)
                return null;
            for (const curve of quadraticPoints([x, y], control, end))
                pushPoint(curve);
            [x, y] = end;
            lastQuadControl = control;
            lastCubicControl = null;
        }
    }
    return points.length >= 2 ? { points, closed } : null;
}
function cubicPoints(start, c1, c2, end) {
    const points = [];
    for (let step = 1; step <= 12; step += 1) {
        const t = step / 12;
        const u = 1 - t;
        points.push([
            u ** 3 * start[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * end[0],
            u ** 3 * start[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * end[1],
        ]);
    }
    return points;
}
function quadraticPoints(start, control, end) {
    const points = [];
    for (let step = 1; step <= 8; step += 1) {
        const t = step / 8;
        const u = 1 - t;
        points.push([
            u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
            u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
        ]);
    }
    return points;
}
function emu(value) {
    return Math.round(value * emuPerPx);
}
function hex(value) {
    if (value.startsWith("#")) {
        const raw = value.slice(1);
        if (raw.length === 3)
            return raw.split("").map((char) => char + char).join("").toUpperCase();
        return raw.slice(0, 6).toUpperCase();
    }
    return "111827";
}
function xml(value) {
    return escapeHtml(value);
}
function xmlDecl(body) {
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${body}`;
}
const nsA = "http://schemas.openxmlformats.org/drawingml/2006/main";
const nsP = "http://schemas.openxmlformats.org/presentationml/2006/main";
const nsR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
function contentTypes(slideCount) {
    const slides = Array.from({ length: slideCount }, (_, index) => `  <Override PartName="/ppt/slides/slide${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join("\n");
    return xmlDecl(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="gif" ContentType="image/gif"/><Default Extension="webp" ContentType="image/webp"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>${slides}</Types>`);
}
function appProps(slideCount) {
    return xmlDecl(`<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>drawingml-svg web</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>${slideCount}</Slides></Properties>`);
}
function presentationXml(slideCount, [width, height]) {
    const ids = Array.from({ length: slideCount }, (_, index) => `<p:sldId id="${256 + index}" r:id="rId${index + 2}"/>`).join("");
    return xmlDecl(`<p:presentation xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>${ids}</p:sldIdLst><p:sldSz cx="${emu(width)}" cy="${emu(height)}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>`);
}
function presentationRels(slideCount) {
    const slides = Array.from({ length: slideCount }, (_, index) => `<Relationship Id="rId${index + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${index + 1}.xml"/>`).join("");
    return xmlDecl(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>${slides}<Relationship Id="rId${slideCount + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>`);
}
const rootRels = xmlDecl(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`);
const coreProps = xmlDecl(`<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>PPTXSVG web export</dc:title><dc:creator>drawingml-svg web</dc:creator><cp:lastModifiedBy>drawingml-svg web</cp:lastModifiedBy></cp:coreProperties>`);
const slideLayoutRel = `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>`;
const slideMasterRels = xmlDecl(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>`);
const slideLayoutRels = xmlDecl(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`);
const slideMaster = xmlDecl(`<p:sldMaster xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>`);
const slideLayout = xmlDecl(`<p:sldLayout xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>`);
const themeXml = xmlDecl(`<a:theme xmlns:a="${nsA}" name="drawingml-svg web"><a:themeElements><a:clrScheme name="drawingml-svg"><a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F9FAFB"/></a:lt2><a:accent1><a:srgbClr val="1D4ED8"/></a:accent1><a:accent2><a:srgbClr val="15803D"/></a:accent2><a:accent3><a:srgbClr val="DC2626"/></a:accent3><a:accent4><a:srgbClr val="7C3AED"/></a:accent4><a:accent5><a:srgbClr val="0891B2"/></a:accent5><a:accent6><a:srgbClr val="EA580C"/></a:accent6><a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="9333EA"/></a:folHlink></a:clrScheme><a:fontScheme name="drawingml-svg"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="drawingml-svg"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>`);
