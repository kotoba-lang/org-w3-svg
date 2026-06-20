const emuPerPx = 9525;

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

type SvgIrNode = {
  node_id: string;
  tag: string;
  attributes: Record<string, string>;
  data: Record<string, string>;
  metadata: { text?: string; json?: JsonValue };
  dependencies: Dependency[];
  children: SvgIrNode[];
  text: string | null;
};

type Dependency = {
  kind: string;
  source: string;
  target: string;
  attribute: string;
};

type PptxSvgIr = {
  kind: "pptxsvg";
  slide_size: [number, number];
  slides: SlideIr[];
  parts: PartIr[];
  masters: TemplateIr[];
  layouts: TemplateIr[];
  guides: GuideIr[];
  rulers: RulerIr[];
  text_styles: TextStyleIr[];
  metadata: Record<string, JsonValue>;
};

type SlideIr = {
  slide_id: string;
  node_id: string;
  title: string | null;
  view_box: [number, number, number, number];
  data: Record<string, string>;
  metadata: { text?: string; json?: JsonValue };
};

type PartIr = {
  part_name: string;
  kind: string;
  source_node_id: string | null;
};

type TemplateIr = {
  template_id: string;
  kind: string;
  node_id: string | null;
  data: Record<string, string>;
  metadata: JsonValue;
};

type GuideIr = {
  guide_id: string;
  orientation: string;
  position: number;
  unit: string;
  node_id: string | null;
};

type RulerIr = {
  ruler_id: string;
  orientation: string;
  origin: number;
  unit: string;
  spacing: number | null;
  node_id: string | null;
};

type TextStyleIr = {
  style_id: string;
  role: string;
  properties: Record<string, JsonValue>;
  node_id: string | null;
};

type FullIr = {
  version: string;
  root: SvgIrNode;
  metadata: { text?: string; json?: JsonValue };
  dependencies: Dependency[];
  presentation: PptxSvgIr;
};

type Shape =
  | RectShape
  | EllipseShape
  | LineShape
  | TextShape
  | TableShape
  | FreeformShape
  | ImageShape;

type BaseShape = {
  id: number;
  kind: string;
  name: string;
  data: Record<string, string>;
};

type Box = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type RectShape = BaseShape & {
  kind: "rect";
  x: number;
  y: number;
  width: number;
  height: number;
  rx: number;
  fill: string | null;
  fillAlpha: number | null;
  stroke: string | null;
  strokeAlpha: number | null;
  strokeWidth: number;
  strokeLineCap: string | null;
  strokeLineJoin: string | null;
  strokeDasharray: string | null;
};

type EllipseShape = BaseShape & {
  kind: "ellipse";
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string | null;
  fillAlpha: number | null;
  stroke: string | null;
  strokeAlpha: number | null;
  strokeWidth: number;
  strokeLineCap: string | null;
  strokeLineJoin: string | null;
  strokeDasharray: string | null;
};

type LineShape = BaseShape & {
  kind: "line";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  stroke: string | null;
  strokeAlpha: number | null;
  strokeWidth: number;
  strokeLineCap: string | null;
  strokeLineJoin: string | null;
  strokeDasharray: string | null;
  relation: boolean;
  startId: number | null;
  endId: number | null;
  markerStart: boolean;
  markerEnd: boolean;
};

type TextShape = BaseShape & {
  kind: "text";
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  fill: string | null;
  fontSize: number;
  fontFamily: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  runs: TextRun[];
};

type TextRun = {
  text: string;
  fill: string | null;
  fillAlpha: number | null;
  fontSize: number;
  fontFamily: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
};

type FreeformShape = BaseShape & {
  kind: "freeform";
  points: [number, number][];
  closed: boolean;
  fill: string | null;
  fillAlpha: number | null;
  stroke: string | null;
  strokeAlpha: number | null;
  strokeWidth: number;
  strokeLineCap: string | null;
  strokeLineJoin: string | null;
  strokeDasharray: string | null;
  markerStart: boolean;
  markerEnd: boolean;
};

type ImageShape = BaseShape & {
  kind: "image";
  x: number;
  y: number;
  width: number;
  height: number;
  href: string;
};

type TableShape = BaseShape & {
  kind: "table";
  x: number;
  y: number;
  columns: number[];
  rows: number[];
  cells: TableCell[];
};

type TableCell = {
  row: number;
  col: number;
  text: string;
  fill: string | null;
};

type Matrix = [number, number, number, number, number, number];

type SvgStyle = {
  fill?: string | null;
  fillAlpha?: number | null;
  stroke?: string | null;
  strokeAlpha?: number | null;
  strokeWidth?: number;
  color?: string | null;
  strokeLineCap?: string | null;
  strokeLineJoin?: string | null;
  strokeDasharray?: string | null;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string;
  fontStyle?: string;
  textDecoration?: string;
  markerStart?: boolean;
  markerEnd?: boolean;
  clipPath?: string | null;
};

type CssRule = {
  selector: string;
  declarations: Record<string, string>;
  order: number;
};

type PreparedSlide = {
  xml: string;
  rels: string;
  media: Record<string, Uint8Array>;
};

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
      <clipPath id="bar-clip"><rect x="960" y="500" width="150" height="70"/></clipPath>
      <clipPath id="bbox-clip" clipPathUnits="objectBoundingBox"><rect x="0.15" y="0.15" width="0.7" height="0.7"/></clipPath>
      <linearGradient id="linear-fallback"><stop offset="0" stop-color="#ef4444"/><stop offset="1" stop-color="#3b82f6"/></linearGradient>
      <radialGradient id="radial-fallback"><stop offset="0" stop-color="#fef08a"/><stop offset="1" stop-color="#16a34a"/></radialGradient>
      <pattern id="pattern-fallback" width="12" height="12" patternUnits="userSpaceOnUse">
        <rect width="12" height="12" fill="#f97316"/>
        <circle cx="6" cy="6" r="4" fill="#22c55e"/>
      </pattern>
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
    <path id="arc-path" d="M 640 520 A 90 55 0 0 1 820 520 A 90 55 0 0 1 640 520" style="fill:#fef3c7;stroke:#a16207;stroke-width:5"/>
    <line id="marked-line" x1="980" y1="185" x2="1130" y2="260" style="stroke:#7c3aed;stroke-width:8;marker-end:url(#arrow)"/>
    <image id="pixel" x="980" y="340" width="96" height="96" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luzQnAAAAABJRU5ErkJggg=="/>
    <circle class="css-circle" cx="1130" cy="388" r="48"/>
    <rect id="clipped-bar" x="930" y="500" width="250" height="70" style="fill:#fecaca;stroke:#991b1b;clip-path:url(#bar-clip)"/>
    <ellipse id="bbox-clipped-ellipse" cx="1090" cy="560" rx="80" ry="50" style="fill:#ede9fe;stroke:#6d28d9;clip-path:url(#bbox-clip)"/>
    <rect id="css-colors" x="740" y="615" width="120" height="50" style="color:orange;fill:currentColor;stroke:hsl(210 100% 50%)"/>
    <rect id="alpha-shape" x="580" y="615" width="120" height="50" style="fill:rgba(239,68,68,0.5);stroke:#2563ebcc;stroke-width:6;fill-opacity:0.8;stroke-opacity:0.5"/>
    <line id="dash-line" x1="120" y1="650" x2="300" y2="650" style="stroke:#0f766e;stroke-width:8;stroke-dasharray:18 10;stroke-linecap:round;stroke-linejoin:bevel"/>
    <text id="rich-text" x="330" y="660" style="font-size:24;font-family:Arial;fill:#111827">Rich <tspan style="fill:#dc2626;font-weight:700">red</tspan><tspan style="fill:#2563eb;font-style:italic;text-decoration:underline"> blue</tspan></text>
    <rect id="gradient-fill" x="900" y="615" width="120" height="50" style="fill:url(#linear-fallback);stroke:url(#radial-fallback)"/>
    <circle id="pattern-fill" cx="1080" cy="640" r="32" style="fill:url(#pattern-fallback);stroke:#334155"/>
    <use href="#reused-chip" class="accent-use" x="360" y="400"/>
    <g transform="translate(90 390) scale(1.5)">
      <rect id="scaled" width="160" height="80" style="fill:#dbeafe;stroke:#2563eb"/>
    </g>
  </g>
</svg>`;

const state: {
  tab: string;
  ir: FullIr | null;
  pptxsvg: PptxSvgIr | null;
  webgpu: boolean;
} = {
  tab: "summary",
  ir: null,
  pptxsvg: null,
  webgpu: false,
};

const source = mustElement<HTMLTextAreaElement>("source");
const preview = mustElement<HTMLElement>("preview");
const panel = mustElement<HTMLElement>("panel");
const fileInput = mustElement<HTMLInputElement>("fileInput");

function mustElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id}`);
  return element as T;
}

function localName(node: Element): string {
  return node.localName || node.nodeName.replace(/^.*:/, "");
}

function attrs(element: Element): Record<string, string> {
  return Object.fromEntries(Array.from(element.attributes || []).map((attr) => [attr.name, attr.value]).sort());
}

function dataAttrs(attributes: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(attributes)
      .filter(([key]) => key.startsWith("data-"))
      .map(([key, value]) => [key.slice(5), value]),
  );
}

function metadata(element: Element): { text?: string; json?: JsonValue } {
  const meta = Array.from(element.children).find((child) => localName(child) === "metadata");
  if (!meta) return {};
  const text = (meta.textContent || "").trim();
  if (!text) return {};
  try {
    return { text, json: JSON.parse(text) as JsonValue };
  } catch (_) {
    return { text };
  }
}

function dependencies(element: Element, attributes: Record<string, string>): Dependency[] {
  const id = attributes.id || localName(element);
  const deps: Dependency[] = [];
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

function nodeToIr(element: Element, nodeId: string): SvgIrNode {
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

function flatten(node: SvgIrNode): SvgIrNode[] {
  return [node, ...node.children.flatMap(flatten)];
}

function viewBox(node: SvgIrNode): [number, number, number, number] {
  const raw = node.attributes.viewBox;
  if (raw) {
    const values = raw.replaceAll(",", " ").split(/\s+/).map(Number).filter((value) => Number.isFinite(value));
    if (values.length === 4 && values[0] !== undefined && values[1] !== undefined && values[2] !== undefined && values[3] !== undefined) {
      return [values[0], values[1], values[2], values[3]];
    }
  }
  return [0, 0, Number(node.attributes.width) || 0, Number(node.attributes.height) || 0];
}

function nodeTitle(node: SvgIrNode): string | null {
  if (node.data.title) return node.data.title;
  const meta = asObject(node.metadata.json);
  if (typeof meta.title === "string") return meta.title;
  const titleNode = node.children.find((child) => child.tag === "title");
  return titleNode?.text || null;
}

function isSlide(node: SvgIrNode): boolean {
  return node.data.kind === "slide" || node.data.role === "slide" || Object.hasOwn(node.data, "slide");
}

function buildPptxsvg(root: SvgIrNode): PptxSvgIr {
  const nodes = flatten(root);
  const slides = nodes.filter(isSlide);
  const selectedSlides = slides.length ? slides : [root];
  const rootMeta = asObject(asObject(root.metadata.json).presentation);
  const rootBox = viewBox(root);
  const metaSlideSize = asObject(rootMeta.slideSize);
  const slideSize: [number, number] =
    typeof metaSlideSize.width === "number" && typeof metaSlideSize.height === "number"
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
  const baseParts: [string, string, string | null][] = [
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

function templates(nodes: SvgIrNode[], metadataItems: JsonValue, kind: string): TemplateIr[] {
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

function guides(nodes: SvgIrNode[], metadataItems: JsonValue): GuideIr[] {
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

function rulers(nodes: SvgIrNode[], metadataItems: JsonValue): RulerIr[] {
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

function textStyles(nodes: SvgIrNode[], metadataStyles: JsonValue): TextStyleIr[] {
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

function buildIr(svgText: string): FullIr {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgText, "image/svg+xml");
  const error = doc.querySelector("parsererror");
  if (error) throw new Error((error.textContent || "").trim());
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

function svgToPptx(svgText: string): Uint8Array {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgText, "image/svg+xml");
  const error = doc.querySelector("parsererror");
  if (error) throw new Error((error.textContent || "").trim());
  const root = doc.documentElement;
  const ir = buildIr(svgText);
  const slides = declaredSlides(root);
  const selectedSlides = slides.length ? slides : [root];
  const slideXmls = selectedSlides.map((slide, index) => buildSlideXml(slide, index + 1));
  return writePptx(slideXmls, ir.presentation.slide_size);
}

function declaredSlides(root: Element): Element[] {
  const result: Element[] = [];
  const walk = (element: Element) => {
    if (isSlideElement(element)) {
      result.push(element);
      return;
    }
    for (const child of Array.from(element.children)) {
      if (localName(child) !== "metadata") walk(child);
    }
  };
  walk(root);
  return result;
}

function isSlideElement(element: Element): boolean {
  return element.getAttribute("data-kind") === "slide" || element.getAttribute("data-role") === "slide" || element.hasAttribute("data-slide");
}

function buildSlideXml(slide: Element, slideIndex: number): string {
  const shapes = extractShapes(slide);
  markRelationConnectors(shapes);
  const body = shapes.map((shape) => shapeToXml(shape)).join("");
  return xmlDecl(`<p:sld xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>${body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`);
}

function extractShapes(root: Element): Shape[] {
  const shapes: Shape[] = [];
  const css = collectCss(root);
  const refs = collectRefs(root);
  let nextId = 2;
  const walk = (element: Element, matrix: Matrix, inheritedStyle: SvgStyle, refStack: Set<string>) => {
    const tag = localName(element);
    if (tag === "metadata" || tag === "defs" || tag === "style") return;
    const ownMatrix = multiply(matrix, transformMatrix(element.getAttribute("transform")));
    const ownStyle = computedStyle(element, inheritedStyle, css, refs);
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
    const rawShape = elementToShape(element, ownMatrix, ownStyle, nextId);
    const clip = rectClipBounds(rawShape, ownStyle, refs, ownMatrix);
    const shape = applyClip(rawShape, clip);
    if (shape) {
      shapes.push(shape);
      nextId += 1;
    }
    for (const child of Array.from(element.children)) walk(child, ownMatrix, ownStyle, refStack);
  };
  const rootStyle = computedStyle(root, {}, css, refs);
  for (const child of Array.from(root.children)) walk(child, [1, 0, 0, 1, 0, 0], rootStyle, new Set());
  return shapes;
}

function elementToShape(element: Element, matrix: Matrix, style: SvgStyle, id: number): Shape | null {
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
      fillAlpha: style.fillAlpha ?? null,
      stroke: style.stroke ?? null,
      strokeAlpha: style.strokeAlpha ?? null,
      strokeWidth: style.strokeWidth ?? 1,
      ...strokeStyle(style),
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
      fillAlpha: style.fillAlpha ?? null,
      stroke: style.stroke ?? null,
      strokeAlpha: style.strokeAlpha ?? null,
      strokeWidth: style.strokeWidth ?? 1,
      ...strokeStyle(style),
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
      strokeAlpha: style.strokeAlpha ?? null,
      strokeWidth: style.strokeWidth ?? 1,
      ...strokeStyle(style),
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
    const runs = textRuns(element, style);
    const text = runs.map((run) => run.text).join("").trim();
    return {
      id,
      kind: "text",
      name,
      data,
      x,
      y: y - fontSize,
      width: Math.max(80, text.length * fontSize * 0.62),
      height: fontSize * 1.35,
      text,
      fill: style.fill ?? "#111827",
      fontSize,
      fontFamily: style.fontFamily || "Aptos",
      bold: ["bold", "700", "800", "900"].includes(style.fontWeight || ""),
      italic: isItalic(style),
      underline: hasUnderline(style),
      runs,
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
        fillAlpha: tag === "polygon" ? (style.fillAlpha ?? null) : null,
        stroke: style.stroke ?? "#111827",
        strokeAlpha: style.strokeAlpha ?? null,
        strokeWidth: style.strokeWidth ?? 1,
        ...strokeStyle(style),
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
        fill: style.fill ?? (parsed.closed ? "#000000" : null),
        fillAlpha: style.fill ? (style.fillAlpha ?? null) : parsed.closed ? (style.fillAlpha ?? null) : null,
        stroke: style.stroke ?? "#111827",
        strokeAlpha: style.strokeAlpha ?? null,
        strokeWidth: style.strokeWidth ?? 1,
        ...strokeStyle(style),
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

function tableFromGroup(group: Element, matrix: Matrix, id: number, inheritedStyle: SvgStyle, css: CssRule[] = []): TableShape | null {
  const rects = Array.from(group.querySelectorAll("rect")).filter((rect) => rect.getAttribute("data-kind") === "cell" || rect.getAttribute("data-role") === "cell");
  if (!rects.length) return null;
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
  if (xEdges.length < 2 || yEdges.length < 2) return null;
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

function textRuns(element: Element, inheritedStyle: SvgStyle): TextRun[] {
  const runs: TextRun[] = [];
  const append = (text: string, style: SvgStyle) => {
    if (!text) return;
    runs.push({
      text,
      fill: style.fill ?? "#111827",
      fillAlpha: style.fillAlpha ?? null,
      fontSize: style.fontSize ?? inheritedStyle.fontSize ?? 18,
      fontFamily: style.fontFamily || inheritedStyle.fontFamily || "Aptos",
      bold: ["bold", "700", "800", "900"].includes(style.fontWeight || ""),
      italic: isItalic(style),
      underline: hasUnderline(style),
    });
  };
  for (const node of Array.from(element.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) {
      append(node.textContent || "", inheritedStyle);
    } else if (node.nodeType === Node.ELEMENT_NODE && localName(node as Element) === "tspan") {
      const style = computedStyle(node as Element, inheritedStyle);
      append((node.textContent || ""), style);
    }
  }
  if (!runs.length) append(element.textContent || "", inheritedStyle);
  const first = runs.findIndex((run) => run.text.trim());
  let last = -1;
  for (let index = runs.length - 1; index >= 0; index -= 1) {
    if (runs[index]?.text.trim()) {
      last = index;
      break;
    }
  }
  if (first < 0 || last < 0) return [];
  return runs.slice(first, last + 1).map((run, index, sliced) => ({
    ...run,
    text: index === 0 ? run.text.trimStart() : index === sliced.length - 1 ? run.text.trimEnd() : run.text,
  })).filter((run) => run.text.length > 0);
}

function isItalic(style: SvgStyle): boolean {
  const value = (style.fontStyle || "").trim().toLowerCase();
  return value === "italic" || value.startsWith("oblique");
}

function hasUnderline(style: SvgStyle): boolean {
  return (style.textDecoration || "").toLowerCase().split(/\s+/).includes("underline");
}

function markRelationConnectors(shapes: Shape[]): void {
  const boxes = shapes.filter((shape): shape is RectShape | EllipseShape | TextShape | FreeformShape => ["rect", "ellipse", "text", "freeform"].includes(shape.kind));
  for (const line of shapes.filter((shape): shape is LineShape => shape.kind === "line" && shape.relation)) {
    line.startId = nearestShapeId(line.x1, line.y1, boxes);
    line.endId = nearestShapeId(line.x2, line.y2, boxes);
  }
}

function nearestShapeId(x: number, y: number, shapes: (RectShape | EllipseShape | TextShape | FreeformShape)[]): number | null {
  if (!shapes.length) return null;
  return shapes
    .map((shape) => {
      const box = shapeBox(shape);
      const dx = Math.max(box.x - x, 0, x - (box.x + box.width));
      const dy = Math.max(box.y - y, 0, y - (box.y + box.height));
      return { id: shape.id, distance: dx * dx + dy * dy };
    })
    .sort((a, b) => a.distance - b.distance)[0]?.id ?? null;
}

function shapeBox(shape: RectShape | EllipseShape | TextShape | FreeformShape): Box {
  if (shape.kind === "freeform") {
    const xs = shape.points.map(([x]) => x);
    const ys = shape.points.map(([, y]) => y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
  }
  return { x: shape.x, y: shape.y, width: shape.width, height: shape.height };
}

function rectClipBounds(shape: Shape | null, style: SvgStyle, refs: Map<string, Element>, matrix: Matrix): Box | null {
  if (!style.clipPath || style.clipPath === "none") return null;
  const refId = urlRef(style.clipPath);
  if (!refId) return null;
  const clip = refs.get(refId);
  if (!clip || localName(clip) !== "clipPath") return null;
  const units = (clip.getAttribute("clipPathUnits") || "userSpaceOnUse").toLowerCase();
  const rect = Array.from(clip.children).find((child) => localName(child) === "rect");
  if (!rect) return null;
  const width = num(rect, "width");
  const height = num(rect, "height");
  if (width <= 0 || height <= 0) return null;
  if (units === "objectboundingbox") {
    const box = clipTargetBox(shape);
    if (!box || clip.getAttribute("transform") || rect.getAttribute("transform")) return null;
    return {
      x: box.x + num(rect, "x") * box.width,
      y: box.y + num(rect, "y") * box.height,
      width: width * box.width,
      height: height * box.height,
    };
  }
  if (units !== "userspaceonuse") return null;
  const clipMatrix = multiply(multiply(matrix, transformMatrix(clip.getAttribute("transform"))), transformMatrix(rect.getAttribute("transform")));
  const box = transformedBox(clipMatrix, num(rect, "x"), num(rect, "y"), width, height);
  return box.width > 0 && box.height > 0 ? box : null;
}

function clipTargetBox(shape: Shape | null): Box | null {
  if (!shape) return null;
  if (shape.kind === "rect" || shape.kind === "ellipse" || shape.kind === "text" || shape.kind === "image") {
    return { x: shape.x, y: shape.y, width: shape.width, height: shape.height };
  }
  if (shape.kind === "line") {
    const x = Math.min(shape.x1, shape.x2);
    const y = Math.min(shape.y1, shape.y2);
    return { x, y, width: Math.abs(shape.x2 - shape.x1), height: Math.abs(shape.y2 - shape.y1) };
  }
  if (shape.kind === "freeform") return shapeBox(shape);
  return null;
}

function applyClip(shape: Shape | null, clip: Box | null): Shape | null {
  if (!shape || !clip) return shape;
  if (shape.kind === "rect") {
    const box = intersectBox(shape, clip);
    return box ? { ...shape, ...box, rx: Math.min(shape.rx, box.width / 2, box.height / 2) } : null;
  }
  if (shape.kind === "ellipse" || shape.kind === "text" || shape.kind === "image") {
    const box = intersectBox(shape, clip);
    return box ? { ...shape, ...box } : null;
  }
  if (shape.kind === "line") {
    const clipped = clipSegmentToBox([shape.x1, shape.y1], [shape.x2, shape.y2], clip);
    return clipped ? { ...shape, x1: clipped[0][0], y1: clipped[0][1], x2: clipped[1][0], y2: clipped[1][1] } : null;
  }
  if (shape.kind === "freeform") {
    const bounds = shapeBox(shape);
    if (!intersectBox(bounds, clip)) return null;
    if (!shape.closed && shape.points.length === 2) {
      const clipped = clipSegmentToBox(shape.points[0]!, shape.points[1]!, clip);
      return clipped ? { ...shape, points: clipped } : null;
    }
    return { ...shape, points: shape.points.map(([x, y]) => [clamp(x, clip.x, clip.x + clip.width), clamp(y, clip.y, clip.y + clip.height)]) };
  }
  return shape;
}

function intersectBox(a: Box, b: Box): Box | null {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);
  if (x2 <= x1 || y2 <= y1) return null;
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

function clipSegmentToBox(start: [number, number], end: [number, number], box: Box): [[number, number], [number, number]] | null {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  let t0 = 0;
  let t1 = 1;
  const checks: [number, number][] = [
    [-dx, start[0] - box.x],
    [dx, box.x + box.width - start[0]],
    [-dy, start[1] - box.y],
    [dy, box.y + box.height - start[1]],
  ];
  for (const [p, q] of checks) {
    if (p === 0 && q < 0) return null;
    if (p === 0) continue;
    const r = q / p;
    if (p < 0) t0 = Math.max(t0, r);
    else t1 = Math.min(t1, r);
    if (t0 > t1) return null;
  }
  return [
    [start[0] + t0 * dx, start[1] + t0 * dy],
    [start[0] + t1 * dx, start[1] + t1 * dy],
  ];
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function urlRef(value: string): string | null {
  const match = value.match(/^url\(\s*['"]?#([^'")\s]+)['"]?\s*\)$/);
  return match?.[1] ?? null;
}

function shapeToXml(shape: Shape): string {
  if (shape.kind === "rect") return rectXml(shape);
  if (shape.kind === "ellipse") return ellipseXml(shape);
  if (shape.kind === "line") return shape.relation ? connectorXml(shape) : lineXml(shape);
  if (shape.kind === "text") return textXml(shape);
  if (shape.kind === "freeform") return freeformXml(shape);
  if (shape.kind === "image") return imageXml(shape);
  return tableXml(shape);
}

function rectXml(shape: RectShape): string {
  return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, shape.rx ? "roundRect" : "rect", fillXml(shape.fill, shape.fillAlpha) + lineStyleXml(shape.stroke, shape.strokeWidth, lineOptions(shape)), "");
}

function ellipseXml(shape: EllipseShape): string {
  return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, "ellipse", fillXml(shape.fill, shape.fillAlpha) + lineStyleXml(shape.stroke, shape.strokeWidth, lineOptions(shape)), "");
}

function lineXml(shape: LineShape): string {
  const x = Math.min(shape.x1, shape.x2);
  const y = Math.min(shape.y1, shape.y2);
  const width = Math.max(Math.abs(shape.x2 - shape.x1), 1);
  const height = Math.max(Math.abs(shape.y2 - shape.y1), 1);
  return spXml(shape.id, shape.name, x, y, width, height, "line", `<a:noFill/>${lineStyleXml(shape.stroke, shape.strokeWidth, lineOptions(shape, { head: shape.markerEnd, tail: shape.markerStart }))}`, "");
}

function connectorXml(shape: LineShape): string {
  const x = Math.min(shape.x1, shape.x2);
  const y = Math.min(shape.y1, shape.y2);
  const width = Math.max(Math.abs(shape.x2 - shape.x1), 1);
  const height = Math.max(Math.abs(shape.y2 - shape.y1), 1);
  const cxn = `${shape.startId ? `<a:stCxn id="${shape.startId}" idx="0"/>` : ""}${shape.endId ? `<a:endCxn id="${shape.endId}" idx="0"/>` : ""}`;
  return `<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvCxnSpPr>${cxn}</p:cNvCxnSpPr><p:nvPr/></p:nvCxnSpPr><p:spPr><a:xfrm><a:off x="${emu(x)}" y="${emu(y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>${lineStyleXml(shape.stroke, shape.strokeWidth, lineOptions(shape, { head: true, tail: shape.markerStart }))}</p:spPr></p:cxnSp>`;
}

function textXml(shape: TextShape): string {
  const runs = (shape.runs.length ? shape.runs : [{
    text: shape.text,
    fill: shape.fill,
    fillAlpha: null,
    fontSize: shape.fontSize,
    fontFamily: shape.fontFamily,
    bold: shape.bold,
    italic: shape.italic,
    underline: shape.underline,
  }]).map(textRunXml).join("");
  const body = `<p:txBody><a:bodyPr wrap="none"/><a:lstStyle/><a:p>${runs}</a:p></p:txBody>`;
  return spXml(shape.id, shape.name, shape.x, shape.y, shape.width, shape.height, "rect", "<a:noFill/><a:ln><a:noFill/></a:ln>", body);
}

function textRunXml(run: TextRun): string {
  const attrs = ` lang="en-US" sz="${Math.round(run.fontSize * 100)}"${run.bold ? ' b="1"' : ""}${run.italic ? ' i="1"' : ""}${run.underline ? ' u="sng"' : ""}`;
  return `<a:r><a:rPr${attrs}>${solidColorXml(run.fill, run.fillAlpha)}<a:latin typeface="${xml(run.fontFamily)}"/></a:rPr><a:t>${xml(run.text)}</a:t></a:r>`;
}

function tableXml(shape: TableShape): string {
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

function freeformXml(shape: FreeformShape): string {
  const box = shapeBox(shape);
  const width = Math.max(box.width, 1);
  const height = Math.max(box.height, 1);
  const local = shape.points.map(([x, y]) => [emu(x - box.x), emu(y - box.y)]);
  const [first, ...rest] = local;
  if (!first) return "";
  const commands = [`<a:moveTo><a:pt x="${first[0]}" y="${first[1]}"/></a:moveTo>`]
    .concat(rest.map(([x, y]) => `<a:lnTo><a:pt x="${x}" y="${y}"/></a:lnTo>`))
    .concat(shape.closed ? ["<a:close/>"] : [])
    .join("");
  const geom = `<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/><a:pathLst><a:path w="${emu(width)}" h="${emu(height)}">${commands}</a:path></a:pathLst></a:custGeom>`;
  return `<p:sp><p:nvSpPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="${emu(box.x)}" y="${emu(box.y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm>${geom}${fillXml(shape.fill, shape.fillAlpha)}${lineStyleXml(shape.stroke, shape.strokeWidth, lineOptions(shape, { head: shape.markerEnd, tail: shape.markerStart }))}</p:spPr></p:sp>`;
}

function imageXml(shape: ImageShape): string {
  return `<p:pic><p:nvPicPr><p:cNvPr id="${shape.id}" name="${xml(shape.name)}"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="${xml(shape.href)}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="${emu(shape.x)}" y="${emu(shape.y)}"/><a:ext cx="${emu(shape.width)}" cy="${emu(shape.height)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>`;
}

function spXml(id: number, name: string, x: number, y: number, width: number, height: number, prst: string, style: string, body: string): string {
  return `<p:sp><p:nvSpPr><p:cNvPr id="${id}" name="${xml(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="${emu(x)}" y="${emu(y)}"/><a:ext cx="${emu(width)}" cy="${emu(height)}"/></a:xfrm><a:prstGeom prst="${prst}"><a:avLst/></a:prstGeom>${style}</p:spPr>${body}</p:sp>`;
}

function fillXml(color: string | null, alpha: number | null = null): string {
  return color ? `<a:solidFill><a:srgbClr val="${hex(color)}">${alphaXml(alpha)}</a:srgbClr></a:solidFill>` : "<a:noFill/>";
}

function solidColorXml(color: string | null, alpha: number | null = null): string {
  return color ? `<a:solidFill><a:srgbClr val="${hex(color)}">${alphaXml(alpha)}</a:srgbClr></a:solidFill>` : "";
}

function lineStyleXml(color: string | null, width: number, options: LineOptions = {}): string {
  if (!color || width <= 0) return "<a:ln><a:noFill/></a:ln>";
  const cap = options.cap ? ` cap="${xml(options.cap)}"` : "";
  return `<a:ln w="${emu(width)}"${cap}><a:solidFill><a:srgbClr val="${hex(color)}">${alphaXml(options.alpha)}</a:srgbClr></a:solidFill>${dashXml(options.dasharray, width)}${joinXml(options.join)}${options.tail ? '<a:tailEnd type="triangle"/>' : ""}${options.head ? '<a:headEnd type="triangle"/>' : ""}</a:ln>`;
}

type LineOptions = {
  head?: boolean;
  tail?: boolean;
  cap?: string | null;
  join?: string | null;
  dasharray?: string | null;
  alpha?: number | null;
};

function lineOptions(shape: { strokeLineCap: string | null; strokeLineJoin: string | null; strokeDasharray: string | null; strokeAlpha?: number | null }, arrows: { head?: boolean; tail?: boolean } = {}): LineOptions {
  return { ...arrows, cap: svgLineCapToDml(shape.strokeLineCap), join: shape.strokeLineJoin, dasharray: shape.strokeDasharray, alpha: shape.strokeAlpha ?? null };
}

function dashXml(value: string | null | undefined, strokeWidth: number): string {
  if (!value || value === "none") return "";
  const nums = dasharrayNumbers(value);
  if (!nums || nums.reduce((sum, item) => sum + item, 0) <= 0) return "";
  if (strokeWidth > 0) {
    const even = nums.length % 2 === 1 ? nums.concat(nums) : nums;
    const parts: string[] = [];
    for (let index = 0; index + 1 < even.length; index += 2) {
      parts.push(`<a:ds d="${Math.round(Math.max(0, even[index]!) / strokeWidth * 100000)}" sp="${Math.round(Math.max(0, even[index + 1]!) / strokeWidth * 100000)}"/>`);
    }
    return `<a:custDash>${parts.join("")}</a:custDash>`;
  }
  return "";
}

function joinXml(value: string | null | undefined): string {
  if (value === "round") return "<a:round/>";
  if (value === "bevel") return "<a:bevel/>";
  if (value === "miter") return "<a:miter/>";
  return "";
}

function svgLineCapToDml(value: string | null | undefined): string | null {
  if (value === "round") return "rnd";
  if (value === "square") return "sq";
  if (value === "butt") return "flat";
  return null;
}

function alphaXml(value: number | null | undefined): string {
  if (value == null || value >= 1) return "";
  return `<a:alpha val="${Math.round(clamp(value, 0, 1) * 100000)}"/>`;
}

function writePptx(slideXmls: string[], slideSize: [number, number]): Uint8Array {
  const files: Record<string, string | Uint8Array> = {
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

function prepareSlideMedia(slideXml: string, firstMediaIndex: number): PreparedSlide {
  const media: Record<string, Uint8Array> = {};
  const relationships = [slideLayoutRel];
  let nextRelId = 2;
  let nextMediaIndex = firstMediaIndex;
  const xml = slideXml.replace(/r:embed="(data:image\/(png|jpeg|jpg|gif|webp);base64,([^"]+))"/gi, (_match, _uri: string, kind: string, payload: string) => {
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

function base64Bytes(value: string): Uint8Array {
  const binary = atob(value.replace(/\s+/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function zipStore(files: Record<string, string | Uint8Array>): Uint8Array {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
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
    central.push(
      concat([
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
      ]),
    );
    offset += local.length;
  }
  const centralOffset = offset;
  const centralData = concat(central);
  const end = concat([u32(0x06054b50), u16(0), u16(0), u16(central.length), u16(central.length), u32(centralData.length), u32(centralOffset), u16(0)]);
  return concat([...chunks, centralData, end]);
}

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 0xff]!;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

const crcTable = Array.from({ length: 256 }, (_, index) => {
  let c = index;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function u32(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]);
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function render(): void {
  try {
    const text = source.value;
    state.ir = buildIr(text);
    state.pptxsvg = state.ir.presentation;
    preview.innerHTML = text;
  } catch (error) {
    preview.innerHTML = "";
    state.ir = null;
    state.pptxsvg = null;
    panel.innerHTML = `<div class="notice">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
    return;
  }
  renderPanel();
}

function escapeHtml(value: unknown): string {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}

function renderPanel(): void {
  if (!state.ir || !state.pptxsvg) return;
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
  } else if (state.tab === "slides") {
    panel.innerHTML = `<div class="list">${state.pptxsvg.slides.map((slide) => `<div class="item"><div class="item-title">${escapeHtml(slide.slide_id)}${slide.title ? ` · ${escapeHtml(slide.title)}` : ""}</div><div class="item-meta">${escapeHtml(slide.node_id)} · viewBox ${slide.view_box.join(" ")}</div></div>`).join("")}</div>`;
  } else if (state.tab === "assistant") {
    panel.innerHTML = `
      <div class="notice">Web LLM integration is designed as a local WebGPU worker. Conversion is deterministic and runs fully in this page.</div>
      <div class="status"><span class="dot ${state.webgpu ? "ok" : ""}"></span>${state.webgpu ? "WebGPU available" : "WebGPU unavailable or blocked"}</div>
      <pre style="margin-top:12px">${escapeHtml(JSON.stringify({
        backendPolicy: state.webgpu ? "webgpu" : "wasm-or-disabled",
        allowedOps: ["mark-slide", "set-data", "set-metadata", "mark-table", "bind-relation"],
        model: "onnx-community/gemma-4-e2b-it-ONNX"
      }, null, 2))}</pre>`;
  } else {
    panel.innerHTML = `<pre>${escapeHtml(JSON.stringify(state.ir, null, 2))}</pre>`;
  }
}

function downloadText(name: string, value: string): void {
  downloadBlob(name, new Blob([value], { type: "application/json;charset=utf-8" }));
}

function downloadBlob(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

document.querySelectorAll<HTMLButtonElement>(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    state.tab = tab.dataset.tab || "summary";
    document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
    renderPanel();
  });
});

mustElement<HTMLButtonElement>("openBtn").addEventListener("click", () => fileInput.click());
mustElement<HTMLButtonElement>("sampleBtn").addEventListener("click", () => {
  source.value = sampleSvg;
  render();
});
mustElement<HTMLButtonElement>("downloadIrBtn").addEventListener("click", () => {
  if (state.ir) downloadText("pptxsvg-ir.json", JSON.stringify(state.ir, null, 2));
});
mustElement<HTMLButtonElement>("downloadPptxsvgBtn").addEventListener("click", () => {
  if (state.pptxsvg) downloadText("pptxsvg.json", JSON.stringify(state.pptxsvg, null, 2));
});
mustElement<HTMLButtonElement>("downloadPptxBtn").addEventListener("click", () => {
  const bytes = svgToPptx(source.value);
  const data = new Uint8Array(bytes.byteLength);
  data.set(bytes);
  downloadBlob("pptxsvg-web.pptx", new Blob([data], { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" }));
});
fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  source.value = await file.text();
  render();
});
source.addEventListener("input", render);

async function checkWebGpu(): Promise<void> {
  const nav = navigator as Navigator & { gpu?: { requestAdapter: () => Promise<unknown> } };
  if (!nav.gpu) {
    state.webgpu = false;
    renderPanel();
    return;
  }
  try {
    state.webgpu = Boolean(await nav.gpu.requestAdapter());
  } catch (_) {
    state.webgpu = false;
  }
  renderPanel();
}

source.value = sampleSvg;
render();
void checkWebGpu();

function asObject(value: JsonValue | undefined): Record<string, JsonValue> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value;
}

function num(element: Element, name: string, fallback = 0): number {
  const value = Number(element.getAttribute(name));
  return Number.isFinite(value) ? value : fallback;
}

function computedStyle(element: Element, inherited: SvgStyle, css: CssRule[] = [], refs: Map<string, Element> = new Map()): SvgStyle {
  const cssDeclarations = matchingCssDeclarations(element, css);
  const inlineDeclarations = styleDeclarations(element.getAttribute("style"));
  const value = (name: string): string | null => inlineDeclarations[name] ?? element.getAttribute(name) ?? cssDeclarations[name] ?? null;
  const next: SvgStyle = { ...inherited };
  const color = value("color");
  const fill = value("fill");
  const stroke = value("stroke");
  const opacity = value("opacity");
  const fillOpacity = value("fill-opacity");
  const strokeOpacity = value("stroke-opacity");
  const strokeWidth = value("stroke-width");
  const strokeLineCap = value("stroke-linecap");
  const strokeLineJoin = value("stroke-linejoin");
  const strokeDasharray = value("stroke-dasharray");
  const fontSize = value("font-size");
  const fontFamily = value("font-family");
  const fontWeight = value("font-weight");
  const fontStyle = value("font-style");
  const textDecoration = value("text-decoration-line") ?? value("text-decoration");
  const clipPath = value("clip-path");
  const marker = value("marker");
  const markerStart = value("marker-start");
  const markerEnd = value("marker-end");
  if (color != null) next.color = parseCssColor(color, next);
  const opacityAlpha = parseAlpha(opacity);
  const fillPaint = fill != null ? normalizePaintValue(fill, refs, next) : null;
  const strokePaint = stroke != null ? normalizePaintValue(stroke, refs, next) : null;
  if (fillPaint) {
    next.fill = fillPaint.color;
    next.fillAlpha = combinedAlpha(opacityAlpha, parseAlpha(fillOpacity), fillPaint.alpha);
  } else if (fill != null) {
    next.fill = null;
    next.fillAlpha = null;
  } else if (opacityAlpha != null || fillOpacity != null) {
    next.fillAlpha = combinedAlpha(opacityAlpha, parseAlpha(fillOpacity), next.fillAlpha);
  }
  if (strokePaint) {
    next.stroke = strokePaint.color;
    next.strokeAlpha = combinedAlpha(opacityAlpha, parseAlpha(strokeOpacity), strokePaint.alpha);
  } else if (stroke != null) {
    next.stroke = null;
    next.strokeAlpha = null;
  } else if (opacityAlpha != null || strokeOpacity != null) {
    next.strokeAlpha = combinedAlpha(opacityAlpha, parseAlpha(strokeOpacity), next.strokeAlpha);
  }
  if (strokeWidth != null) next.strokeWidth = parseLength(strokeWidth, next.strokeWidth ?? 1);
  if (strokeLineCap != null) next.strokeLineCap = normalizeStrokeLineCap(strokeLineCap);
  if (strokeLineJoin != null) next.strokeLineJoin = normalizeStrokeLineJoin(strokeLineJoin);
  if (strokeDasharray != null) next.strokeDasharray = normalizeStrokeDasharray(strokeDasharray);
  if (fontSize != null) next.fontSize = parseLength(fontSize, next.fontSize ?? 18);
  if (fontFamily != null) next.fontFamily = fontFamily.replace(/^['"]|['"]$/g, "");
  if (fontWeight != null) next.fontWeight = fontWeight;
  if (fontStyle != null) next.fontStyle = fontStyle;
  if (textDecoration != null) next.textDecoration = textDecoration;
  if (clipPath != null) next.clipPath = clipPath.trim();
  if (marker != null) {
    const enabled = marker !== "none";
    next.markerStart = enabled;
    next.markerEnd = enabled;
  }
  if (markerStart != null) next.markerStart = markerStart !== "none";
  if (markerEnd != null) next.markerEnd = markerEnd !== "none";
  return next;
}

function collectCss(root: Element): CssRule[] {
  const rules: CssRule[] = [];
  let order = 0;
  for (const style of Array.from(root.querySelectorAll("style"))) {
    const text = style.textContent || "";
    for (const match of text.matchAll(/([^{}]+)\{([^{}]+)\}/g)) {
      const selectorText = (match[1] || "").trim();
      const body = match[2] || "";
      if (!selectorText || selectorText.startsWith("@")) continue;
      for (const selector of selectorText.split(",").map((item) => item.trim()).filter(Boolean)) {
        rules.push({ selector, declarations: styleDeclarations(body), order });
        order += 1;
      }
    }
  }
  return rules;
}

function collectRefs(root: Element): Map<string, Element> {
  const refs = new Map<string, Element>();
  const walk = (element: Element) => {
    const id = element.getAttribute("id");
    if (id) refs.set(id, element);
    for (const child of Array.from(element.children)) walk(child);
  };
  walk(root);
  return refs;
}

function matchingCssDeclarations(element: Element, css: CssRule[]): Record<string, string> {
  const declarations: Record<string, string> = {};
  for (const rule of css) {
    if (!matchesSelector(element, rule.selector)) continue;
    Object.assign(declarations, rule.declarations);
  }
  return declarations;
}

function matchesSelector(element: Element, selector: string): boolean {
  try {
    return element.matches(selector);
  } catch (_) {
    return false;
  }
}

function styleDeclarations(style: string | null): Record<string, string> {
  if (!style) return {};
  return Object.fromEntries(
    style
      .split(";")
      .map((entry) => entry.split(":"))
      .filter((parts): parts is [string, string] => parts.length >= 2 && Boolean(parts[0]?.trim()))
      .map(([name, ...value]) => [name.trim(), value.join(":").trim()]),
  );
}

function strokeStyle(style: SvgStyle): { strokeLineCap: string | null; strokeLineJoin: string | null; strokeDasharray: string | null } {
  return {
    strokeLineCap: style.strokeLineCap ?? null,
    strokeLineJoin: style.strokeLineJoin ?? null,
    strokeDasharray: style.strokeDasharray ?? null,
  };
}

function normalizeStrokeLineCap(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  return ["butt", "round", "square"].includes(normalized) ? normalized : null;
}

function normalizeStrokeLineJoin(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  if (normalized === "miter-clip") return "miter";
  return ["miter", "round", "bevel"].includes(normalized) ? normalized : null;
}

function normalizeStrokeDasharray(value: string): string | null {
  const normalized = value.trim();
  if (!normalized || normalized === "none") return null;
  return dasharrayNumbers(normalized) ? normalized : null;
}

function dasharrayNumbers(value: string): number[] | null {
  const parts = value.replaceAll(",", " ").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return null;
  const nums = parts.map((part) => Number.parseFloat(part));
  return nums.every((item) => Number.isFinite(item) && item >= 0) ? nums : null;
}

function normalizePaint(value: string, refs: Map<string, Element> = new Map(), style: SvgStyle = {}): string | null {
  return normalizePaintValue(value, refs, style)?.color ?? null;
}

function normalizePaintValue(value: string, refs: Map<string, Element> = new Map(), style: SvgStyle = {}): { color: string; alpha: number | null } | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "none" || trimmed === "transparent") return null;
  const ref = paintUrlRef(trimmed);
  if (ref) {
    const server = paintServerColor(ref.id, refs, style);
    if (server) return { color: server, alpha: cssColorAlpha(server) };
    return normalizePaintValue(ref.fallback, refs, style);
  }
  const color = parseCssColor(trimmed, style) ?? trimmed;
  return { color, alpha: cssColorAlpha(trimmed) };
}

function paintServerColor(id: string, refs: Map<string, Element>, style: SvgStyle, seen: Set<string> = new Set()): string | null {
  if (seen.has(id)) return null;
  const element = refs.get(id);
  if (!element) return null;
  const tag = localName(element);
  if (tag === "pattern") return averageColor(patternColors(element, refs, {}, new Set([...seen, id])));
  if (tag !== "linearGradient" && tag !== "radialGradient") return null;
  const nextSeen = new Set([...seen, id]);
  const href = element.getAttribute("href") || element.getAttribute("xlink:href") || "";
  const inheritedStops = href.startsWith("#") ? gradientStops(refs.get(href.slice(1)), refs, style, nextSeen) : [];
  const stops = inheritedStops.concat(gradientStops(element, refs, style, nextSeen));
  if (!stops.length) return null;
  if (tag === "radialGradient") return stops[stops.length - 1] ?? null;
  const rgb = stops.map(hexToRgb).filter((item): item is [number, number, number] => Boolean(item));
  if (!rgb.length) return null;
  const count = rgb.length;
  return rgbToHex([
    Math.round(rgb.reduce((sum, item) => sum + item[0], 0) / count),
    Math.round(rgb.reduce((sum, item) => sum + item[1], 0) / count),
    Math.round(rgb.reduce((sum, item) => sum + item[2], 0) / count),
  ]);
}

function patternColors(element: Element, refs: Map<string, Element>, inheritedStyle: SvgStyle, seen: Set<string>): string[] {
  const colors: string[] = [];
  for (const child of Array.from(element.children)) {
    const tag = localName(child);
    if (tag === "g" || tag === "svg" || tag === "a") {
      colors.push(...patternColors(child, refs, inheritedStyle, seen));
      continue;
    }
    if (!["rect", "circle", "ellipse", "path", "polygon", "polyline", "text", "tspan", "line"].includes(tag)) continue;
    const style = simpleElementStyle(child, inheritedStyle, refs, seen);
    if (tag !== "line" && style.fill) colors.push(style.fill);
    if (style.stroke) colors.push(style.stroke);
    colors.push(...patternColors(child, refs, style, seen));
  }
  return colors;
}

function simpleElementStyle(element: Element, inheritedStyle: SvgStyle, refs: Map<string, Element>, seen: Set<string>): SvgStyle {
  const declarations = styleDeclarations(element.getAttribute("style"));
  const value = (name: string): string | null => declarations[name] ?? element.getAttribute(name) ?? null;
  const fill = value("fill");
  const stroke = value("stroke");
  const next: SvgStyle = { ...inheritedStyle };
  if (fill != null) next.fill = normalizePatternPaint(fill, refs, next, seen);
  if (stroke != null) next.stroke = normalizePatternPaint(stroke, refs, next, seen);
  return next;
}

function normalizePatternPaint(value: string, refs: Map<string, Element>, style: SvgStyle, seen: Set<string>): string | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "none" || trimmed === "transparent") return null;
  const ref = paintUrlRef(trimmed);
  if (ref) {
    const targetId = ref.id;
    return seen.has(targetId) ? normalizePaint(ref.fallback, refs, style) : paintServerColor(targetId, refs, style, seen) ?? normalizePaint(ref.fallback, refs, style);
  }
  return normalizeStopColor(trimmed, style);
}

function averageColor(colors: string[]): string | null {
  const rgb = colors.map(hexToRgb).filter((item): item is [number, number, number] => Boolean(item));
  if (!rgb.length) return null;
  const count = rgb.length;
  return rgbToHex([
    Math.round(rgb.reduce((sum, item) => sum + item[0], 0) / count),
    Math.round(rgb.reduce((sum, item) => sum + item[1], 0) / count),
    Math.round(rgb.reduce((sum, item) => sum + item[2], 0) / count),
  ]);
}

function gradientStops(element: Element | undefined, refs: Map<string, Element>, style: SvgStyle, seen: Set<string>): string[] {
  if (!element) return [];
  const tag = localName(element);
  if (tag !== "linearGradient" && tag !== "radialGradient") return [];
  const colors: string[] = [];
  const href = element.getAttribute("href") || element.getAttribute("xlink:href") || "";
  if (href.startsWith("#")) {
    const inherited = refs.get(href.slice(1));
    const inheritedId = inherited?.getAttribute("id") || "";
    if (inherited && inheritedId && !seen.has(inheritedId)) colors.push(...gradientStops(inherited, refs, style, new Set([...seen, inheritedId])));
  }
  for (const stop of Array.from(element.children)) {
    if (localName(stop) !== "stop") continue;
    const declarations = styleDeclarations(stop.getAttribute("style"));
    const color = declarations["stop-color"] ?? stop.getAttribute("stop-color") ?? "#000000";
    const normalized = normalizeStopColor(color, style);
    if (normalized) colors.push(normalized);
  }
  return colors;
}

function normalizeStopColor(value: string, style: SvgStyle): string | null {
  return parseCssColor(value, style);
}

function parseCssColor(value: string | null, style: SvgStyle = {}): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  if (lower === "none" || lower === "transparent") return null;
  if (lower === "currentcolor") return style.color ?? style.fill ?? style.stroke ?? "#000000";
  if (lower in namedColors) return namedColors[lower] ?? null;
  if (/^#[0-9a-f]{3}$/i.test(trimmed)) return `#${trimmed.slice(1).split("").map((char) => char + char).join("")}`;
  if (/^#[0-9a-f]{4}$/i.test(trimmed)) return `#${trimmed.slice(1, 4).split("").map((char) => char + char).join("")}`;
  if (/^#[0-9a-f]{6}$/i.test(trimmed)) return trimmed.slice(0, 7);
  if (/^#[0-9a-f]{8}$/i.test(trimmed)) return trimmed.slice(0, 7);
  const rgb = parseRgbFunction(trimmed);
  if (rgb) return rgbToHex(rgb);
  const hsl = parseHslFunction(trimmed);
  if (hsl) return rgbToHex(hsl);
  return null;
}

function cssColorAlpha(value: string | null): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^#[0-9a-f]{4}$/i.test(trimmed)) return Number.parseInt(trimmed.slice(4, 5).repeat(2), 16) / 255;
  if (/^#[0-9a-f]{8}$/i.test(trimmed)) return Number.parseInt(trimmed.slice(7, 9), 16) / 255;
  const functionMatch = trimmed.match(/^(?:rgba|hsla?)\(([^)]+)\)$/i);
  if (!functionMatch) return null;
  const parts = colorFunctionParts(functionMatch[1] || "");
  return parts.length >= 4 ? parseAlpha(parts[3]!) : null;
}

function parseAlpha(value: string | null): number | null {
  if (value == null) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return cssAlpha(trimmed);
}

function combinedAlpha(...values: (number | null | undefined)[]): number | null {
  let alpha = 1;
  let seen = false;
  for (const value of values) {
    if (value == null) continue;
    alpha *= clamp(value, 0, 1);
    seen = true;
  }
  return seen ? alpha : null;
}

const namedColors: Record<string, string | null> = {
  black: "#000000",
  blue: "#0000ff",
  cyan: "#00ffff",
  gray: "#808080",
  green: "#008000",
  grey: "#808080",
  lime: "#00ff00",
  magenta: "#ff00ff",
  orange: "#ffa500",
  purple: "#800080",
  red: "#ff0000",
  transparent: null,
  white: "#ffffff",
  yellow: "#ffff00",
};

function parseRgbFunction(value: string): [number, number, number] | null {
  const match = value.match(/^rgba?\(([^)]+)\)$/i);
  if (!match) return null;
  const parts = colorFunctionParts(match[1] || "");
  if (parts.length < 3) return null;
  return [cssChannel(parts[0]!), cssChannel(parts[1]!), cssChannel(parts[2]!)];
}

function parseHslFunction(value: string): [number, number, number] | null {
  const match = value.match(/^hsla?\(([^)]+)\)$/i);
  if (!match) return null;
  const parts = colorFunctionParts(match[1] || "");
  if (parts.length < 3) return null;
  return hslToRgb(parts[0]!, cssAlpha(parts[1]!), cssAlpha(parts[2]!));
}

function colorFunctionParts(value: string): string[] {
  return value.replaceAll(",", " ").replace("/", " ").trim().split(/\s+/).filter(Boolean);
}

function cssChannel(value: string): number {
  if (value.endsWith("%")) return Math.round(clamp(Number.parseFloat(value) || 0, 0, 100) * 2.55);
  return Math.round(clamp(Number.parseFloat(value) || 0, 0, 255));
}

function cssAlpha(value: string): number {
  if (value.endsWith("%")) return clamp((Number.parseFloat(value) || 0) / 100, 0, 1);
  return clamp(Number.parseFloat(value) || 0, 0, 1);
}

function hslToRgb(hueValue: string, saturation: number, lightness: number): [number, number, number] {
  const hue = cssHueDegrees(hueValue) / 360;
  if (saturation === 0) {
    const channel = Math.round(lightness * 255);
    return [channel, channel, channel];
  }
  const q = lightness < 0.5 ? lightness * (1 + saturation) : lightness + saturation - lightness * saturation;
  const p = 2 * lightness - q;
  const channel = (offset: number) => {
    const t = (hue + offset + 1) % 1;
    const value = t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p;
    return Math.round(value * 255 + 1e-9);
  };
  return [channel(1 / 3), channel(0), channel(-1 / 3)];
}

function cssHueDegrees(value: string): number {
  const number = Number.parseFloat(value) || 0;
  if (value.endsWith("turn")) return number * 360;
  if (value.endsWith("rad")) return (number * 180) / Math.PI;
  if (value.endsWith("grad")) return number * 0.9;
  return number;
}

function paintUrlRef(value: string): { id: string; fallback: string } | null {
  const match = value.match(/^url\(\s*['"]?#([^'")\s]+)['"]?\s*\)\s*(.*)$/);
  return match ? { id: match[1]!, fallback: match[2]?.trim() || "" } : null;
}

function hexToRgb(value: string): [number, number, number] | null {
  const normalized = normalizeStopColor(value, {});
  if (!normalized) return null;
  const raw = normalized.slice(1);
  return [Number.parseInt(raw.slice(0, 2), 16), Number.parseInt(raw.slice(2, 4), 16), Number.parseInt(raw.slice(4, 6), 16)];
}

function rgbToHex(rgb: [number, number, number]): string {
  return `#${rgb.map((value) => clamp(Math.round(value), 0, 255).toString(16).padStart(2, "0")).join("")}`;
}

function parseLength(value: string | null, fallback = 0): number {
  if (!value) return fallback;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function supportedDataImage(value: string): boolean {
  return /^data:image\/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/i.test(value);
}

function edges(values: number[]): number[] {
  return [...new Set(values.map((value) => Math.round(value * 1000) / 1000))].sort((a, b) => a - b);
}

function transformMatrix(value: string | null): Matrix {
  if (!value) return [1, 0, 0, 1, 0, 0];
  let matrix: Matrix = [1, 0, 0, 1, 0, 0];
  for (const match of value.matchAll(/(matrix|translate|scale|rotate)\(([^)]*)\)/g)) {
    const kind = match[1];
    const args = (match[2] || "").replaceAll(",", " ").trim().split(/\s+/).map(Number).filter((item) => Number.isFinite(item));
    let next: Matrix = [1, 0, 0, 1, 0, 0];
    if (kind === "matrix" && args.length >= 6) {
      next = [args[0]!, args[1]!, args[2]!, args[3]!, args[4]!, args[5]!];
    } else if (kind === "translate") {
      next = [1, 0, 0, 1, args[0] || 0, args[1] || 0];
    } else if (kind === "scale") {
      next = [args[0] ?? 1, 0, 0, args[1] ?? args[0] ?? 1, 0, 0];
    } else if (kind === "rotate") {
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

function multiply(a: Matrix, b: Matrix): Matrix {
  return [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]];
}

function point(m: Matrix, x: number, y: number): [number, number] {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

function transformedBox(matrix: Matrix, x: number, y: number, width: number, height: number): { x: number; y: number; width: number; height: number } {
  const points = [point(matrix, x, y), point(matrix, x + width, y), point(matrix, x + width, y + height), point(matrix, x, y + height)];
  const xs = points.map(([px]) => px);
  const ys = points.map(([, py]) => py);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
}

function parsePoints(value: string): [number, number][] {
  const numbers = value.replaceAll(",", " ").trim().split(/\s+/).map(Number).filter((item) => Number.isFinite(item));
  const points: [number, number][] = [];
  for (let index = 0; index + 1 < numbers.length; index += 2) {
    points.push([numbers[index]!, numbers[index + 1]!]);
  }
  return points;
}

function parseBasicPath(value: string, matrix: Matrix): { points: [number, number][]; closed: boolean } | null {
  const tokens = value.match(/[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[eE][-+]?\d+)?/g) || [];
  const points: [number, number][] = [];
  let command = "";
  let index = 0;
  let x = 0;
  let y = 0;
  let start: [number, number] | null = null;
  let lastCubicControl: [number, number] | null = null;
  let lastQuadControl: [number, number] | null = null;
  let closed = false;
  const nextNumber = () => {
    const token = tokens[index++];
    return token == null ? null : Number(token);
  };
  const nextPoint = (relative: boolean): [number, number] | null => {
    const nx = nextNumber();
    const ny = nextNumber();
    if (nx == null || ny == null || !Number.isFinite(nx) || !Number.isFinite(ny)) return null;
    return relative ? [x + nx, y + ny] : [nx, ny];
  };
  const pushPoint = (raw: [number, number]) => {
    const transformed = point(matrix, raw[0], raw[1]);
    if (!start) start = transformed;
    points.push(transformed);
  };
  while (index < tokens.length) {
    const token = tokens[index]!;
    if (/^[A-Za-z]$/.test(token)) {
      command = token;
      index += 1;
    }
    if (!/[MmLlHhVvCcSsQqTtAaZz]/.test(command)) return null;
    if (command === "Z" || command === "z") {
      closed = true;
      if (start) points.push(start);
      continue;
    }
    if (command === "H" || command === "h") {
      const nx = nextNumber();
      if (nx == null) return null;
      x = command === "h" ? x + nx : nx;
      pushPoint([x, y]);
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (command === "V" || command === "v") {
      const ny = nextNumber();
      if (ny == null) return null;
      y = command === "v" ? y + ny : ny;
      pushPoint([x, y]);
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (command === "M" || command === "m" || command === "L" || command === "l") {
      const next = nextPoint(command === "m" || command === "l");
      if (!next) return null;
      [x, y] = next;
      pushPoint([x, y]);
      if (command === "M") command = "L";
      if (command === "m") command = "l";
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (command === "C" || command === "c") {
      const c1 = nextPoint(command === "c");
      const c2 = nextPoint(command === "c");
      const end = nextPoint(command === "c");
      if (!c1 || !c2 || !end) return null;
      for (const curve of cubicPoints([x, y], c1, c2, end)) pushPoint(curve);
      [x, y] = end;
      lastCubicControl = c2;
      lastQuadControl = null;
    } else if (command === "S" || command === "s") {
      const c1: [number, number] = lastCubicControl ? [x * 2 - lastCubicControl[0], y * 2 - lastCubicControl[1]] : [x, y];
      const c2 = nextPoint(command === "s");
      const end = nextPoint(command === "s");
      if (!c2 || !end) return null;
      for (const curve of cubicPoints([x, y], c1, c2, end)) pushPoint(curve);
      [x, y] = end;
      lastCubicControl = c2;
      lastQuadControl = null;
    } else if (command === "Q" || command === "q") {
      const control = nextPoint(command === "q");
      const end = nextPoint(command === "q");
      if (!control || !end) return null;
      for (const curve of quadraticPoints([x, y], control, end)) pushPoint(curve);
      [x, y] = end;
      lastQuadControl = control;
      lastCubicControl = null;
    } else if (command === "T" || command === "t") {
      const control: [number, number] = lastQuadControl ? [x * 2 - lastQuadControl[0], y * 2 - lastQuadControl[1]] : [x, y];
      const end = nextPoint(command === "t");
      if (!end) return null;
      for (const curve of quadraticPoints([x, y], control, end)) pushPoint(curve);
      [x, y] = end;
      lastQuadControl = control;
      lastCubicControl = null;
    } else if (command === "A" || command === "a") {
      const rx = nextNumber();
      const ry = nextNumber();
      const angle = nextNumber();
      const largeArc = nextNumber();
      const sweep = nextNumber();
      const end = nextPoint(command === "a");
      if (rx == null || ry == null || angle == null || largeArc == null || sweep == null || !end) return null;
      for (const arc of arcPoints([x, y], rx, ry, angle, Math.round(largeArc) !== 0, Math.round(sweep) !== 0, end)) pushPoint(arc);
      [x, y] = end;
      lastQuadControl = null;
      lastCubicControl = null;
    }
  }
  return points.length >= 2 ? { points, closed } : null;
}

function cubicPoints(start: [number, number], c1: [number, number], c2: [number, number], end: [number, number]): [number, number][] {
  const points: [number, number][] = [];
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

function quadraticPoints(start: [number, number], control: [number, number], end: [number, number]): [number, number][] {
  const points: [number, number][] = [];
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

function arcPoints(
  start: [number, number],
  rxValue: number,
  ryValue: number,
  xAxisRotation: number,
  largeArc: boolean,
  sweep: boolean,
  end: [number, number],
): [number, number][] {
  if (rxValue === 0 || ryValue === 0 || (start[0] === end[0] && start[1] === end[1])) return [end];
  let rx = Math.abs(rxValue);
  let ry = Math.abs(ryValue);
  const phi = ((xAxisRotation % 360) * Math.PI) / 180;
  const cosPhi = Math.cos(phi);
  const sinPhi = Math.sin(phi);
  const dx = (start[0] - end[0]) / 2;
  const dy = (start[1] - end[1]) / 2;
  const x1p = cosPhi * dx + sinPhi * dy;
  const y1p = -sinPhi * dx + cosPhi * dy;
  const radiusScale = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry);
  if (radiusScale > 1) {
    const scale = Math.sqrt(radiusScale);
    rx *= scale;
    ry *= scale;
  }
  const sign = largeArc === sweep ? -1 : 1;
  const numerator = Math.max(rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p, 0);
  const denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p;
  const coef = denominator ? sign * Math.sqrt(numerator / denominator) : 0;
  const cxp = coef * ((rx * y1p) / ry);
  const cyp = coef * ((-ry * x1p) / rx);
  const cx = cosPhi * cxp - sinPhi * cyp + (start[0] + end[0]) / 2;
  const cy = sinPhi * cxp + cosPhi * cyp + (start[1] + end[1]) / 2;
  const startAngle = vectorAngle([1, 0], [(x1p - cxp) / rx, (y1p - cyp) / ry]);
  let deltaAngle = vectorAngle([(x1p - cxp) / rx, (y1p - cyp) / ry], [(-x1p - cxp) / rx, (-y1p - cyp) / ry]);
  if (!sweep && deltaAngle > 0) deltaAngle -= Math.PI * 2;
  if (sweep && deltaAngle < 0) deltaAngle += Math.PI * 2;
  const segments = Math.max(4, Math.min(32, Math.ceil(Math.abs(deltaAngle) / (Math.PI / 12))));
  const points: [number, number][] = [];
  for (let step = 1; step <= segments; step += 1) {
    const theta = startAngle + (deltaAngle * step) / segments;
    points.push([
      cosPhi * rx * Math.cos(theta) - sinPhi * ry * Math.sin(theta) + cx,
      sinPhi * rx * Math.cos(theta) + cosPhi * ry * Math.sin(theta) + cy,
    ]);
  }
  return points;
}

function vectorAngle(u: [number, number], v: [number, number]): number {
  return Math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]);
}

function emu(value: number): number {
  return Math.round(value * emuPerPx);
}

function hex(value: string): string {
  const parsed = parseCssColor(value);
  if (parsed) return parsed.slice(1, 7).toUpperCase();
  if (value.startsWith("#")) {
    const raw = value.slice(1);
    if (raw.length === 3) return raw.split("").map((char) => char + char).join("").toUpperCase();
    return raw.slice(0, 6).toUpperCase();
  }
  return "111827";
}

function xml(value: string): string {
  return escapeHtml(value);
}

function xmlDecl(body: string): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${body}`;
}

const nsA = "http://schemas.openxmlformats.org/drawingml/2006/main";
const nsP = "http://schemas.openxmlformats.org/presentationml/2006/main";
const nsR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

function contentTypes(slideCount: number): string {
  const slides = Array.from({ length: slideCount }, (_, index) => `  <Override PartName="/ppt/slides/slide${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join("\n");
  return xmlDecl(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="gif" ContentType="image/gif"/><Default Extension="webp" ContentType="image/webp"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>${slides}</Types>`);
}

function appProps(slideCount: number): string {
  return xmlDecl(`<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>drawingml-svg web</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>${slideCount}</Slides></Properties>`);
}

function presentationXml(slideCount: number, [width, height]: [number, number]): string {
  const ids = Array.from({ length: slideCount }, (_, index) => `<p:sldId id="${256 + index}" r:id="rId${index + 2}"/>`).join("");
  return xmlDecl(`<p:presentation xmlns:a="${nsA}" xmlns:r="${nsR}" xmlns:p="${nsP}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>${ids}</p:sldIdLst><p:sldSz cx="${emu(width)}" cy="${emu(height)}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>`);
}

function presentationRels(slideCount: number): string {
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
