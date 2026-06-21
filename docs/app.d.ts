export type JsonValue = null | boolean | number | string | JsonValue[] | {
    [key: string]: JsonValue;
};
export type SVGraphNode = {
    node_id: string;
    tag: string;
    attributes: Record<string, string>;
    data: Record<string, string>;
    metadata: {
        text?: string;
        json?: JsonValue;
    };
    dependencies: Dependency[];
    children: SVGraphNode[];
    text: string | null;
};
export type Dependency = {
    kind: string;
    source: string;
    target: string;
    attribute: string;
};
export type SVGraphPresentationProjection = {
    kind: "svgraph-presentation";
    slide_size: [number, number];
    slides: SlideRecord[];
    parts: PartRecord[];
    masters: TemplateRecord[];
    layouts: TemplateRecord[];
    guides: GuideRecord[];
    rulers: RulerRecord[];
    text_styles: TextStyleRecord[];
    metadata: Record<string, JsonValue>;
};
export type SlideRecord = {
    slide_id: string;
    node_id: string;
    title: string | null;
    view_box: [number, number, number, number];
    data: Record<string, string>;
    metadata: {
        text?: string;
        json?: JsonValue;
    };
};
export type PartRecord = {
    part_name: string;
    content_type: string;
    kind: string;
    source_node_id: string | null;
};
export type TemplateRecord = {
    template_id: string;
    kind: string;
    node_id: string | null;
    data: Record<string, string>;
    metadata: JsonValue;
};
export type GuideRecord = {
    guide_id: string;
    orientation: string;
    position: number;
    unit: string;
    node_id: string | null;
};
export type RulerRecord = {
    ruler_id: string;
    orientation: string;
    origin: number;
    unit: string;
    spacing: number | null;
    node_id: string | null;
};
export type TextStyleRecord = {
    style_id: string;
    role: string;
    properties: Record<string, JsonValue>;
    node_id: string | null;
};
export type SVGraphDocument = {
    kind: "svgraph";
    version: string;
    root: SVGraphNode;
    metadata: {
        text?: string;
        json?: JsonValue;
    };
    dependencies: Dependency[];
    coverage: SvgCoverage;
    presentation: SVGraphPresentationProjection;
};
export type SVGraphSidecar = {
    kind: "svgraph-sidecar";
    version: string;
    source_svg: string;
    metadata: {
        text?: string;
        json?: JsonValue;
    };
    dependencies: Dependency[];
    coverage: SvgCoverage;
    presentation: SVGraphPresentationProjection;
};
export type SvgCoverage = {
    total_elements: number;
    convertible_elements: number;
    ignored_elements: number;
    unsupported_elements: Record<string, number>;
    unsupported_attributes: Record<string, number>;
    unsupported_path_commands: Record<string, number>;
    estimated_element_coverage: number;
};
export declare function buildSVGraph(svgText: string): SVGraphDocument;
export declare function buildSVGraphSidecar(svgraph: SVGraphDocument, svgText?: string): SVGraphSidecar;
export declare function svgToPptx(svgText: string): Uint8Array;
export declare function svgToDrawingMl(svgText: string): string;
export declare function initSVGraphEditor(): void;
