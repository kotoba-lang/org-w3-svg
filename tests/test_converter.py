from xml.etree import ElementTree as ET

from drawingml_svg import analyze_svg, drawingml_to_svg, svg_to_drawingml
from examples.make_pptx import build_slide_xml


def test_svg_rect_to_drawingml_preserves_geometry_and_paint() -> None:
    dml = svg_to_drawingml(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80">
          <rect x="10" y="20" width="30" height="40" fill="#abc" stroke="#112233" stroke-width="2"/>
        </svg>"""
    )

    root = ET.fromstring(dml)
    assert root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off").attrib == {
        "x": "0",
        "y": "0",
    }
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "95250", "y": "190500"}
    assert shape_ext.attrib == {"cx": "285750", "cy": "381000"}
    assert 'val="AABBCC"' in dml
    assert 'val="112233"' in dml
    assert 'w="19050"' in dml


def test_drawingml_to_svg_rect_round_trip() -> None:
    svg = drawingml_to_svg(svg_to_drawingml('<svg><rect x="5" y="6" width="7" height="8" fill="none"/></svg>'))

    assert '<rect fill="none" x="5" y="6" width="7" height="8"/>' in svg
    assert 'viewBox="0 0 12 14"' in svg


def test_svg_line_round_trip_keeps_direction_with_flips() -> None:
    svg = drawingml_to_svg(svg_to_drawingml('<svg><line x1="20" y1="30" x2="5" y2="10" stroke="#ff0000"/></svg>'))

    assert '<line stroke="#ff0000" x1="20" y1="30" x2="5" y2="10" fill="none"/>' in svg


def test_converted_shapes_can_be_embedded_in_slide_xml() -> None:
    fragment = ET.fromstring(
        svg_to_drawingml(
            '<svg><rect x="1" y="2" width="3" height="4"/><ellipse cx="20" cy="30" rx="5" ry="6"/></svg>'
        )
    )
    shapes = [
        child
        for child in fragment
        if child.tag == "{http://schemas.openxmlformats.org/presentationml/2006/main}sp"
    ]
    slide_xml = build_slide_xml(shapes).decode("utf-8")

    assert slide_xml.count("<p:sp>") == 2
    assert 'prst="rect"' in slide_xml
    assert 'prst="ellipse"' in slide_xml


def test_polygon_polyline_linear_path_and_text_convert() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <polygon points="0,0 20,0 10,10" fill="#fee2e2"/>
          <polyline points="30,0 40,10 50,0" fill="none" stroke="#111111"/>
          <path d="M60 0 L80 0 L70 12 Z" fill="#e0f2fe" stroke="#0369a1"/>
          <text x="5" y="40" font-size="18" fill="#0f172a">Hello</text>
        </svg>"""
    )
    assert dml.count("<a:custGeom>") == 3
    assert "<p:txBody>" in dml
    assert "<a:t>Hello</a:t>" in dml

    svg = drawingml_to_svg(dml)
    assert svg.count("<polygon") == 2
    assert svg.count("<polyline") == 1
    assert "<text" in svg
    assert "Hello" in svg


def test_cubic_path_is_approximated_as_custom_geometry() -> None:
    dml = svg_to_drawingml('<svg><path d="M0 0 C10 20, 30 20, 40 0 S70 -20, 80 0" fill="none" stroke="#0891b2"/></svg>')

    assert dml.count("<a:custGeom>") == 1
    assert dml.count("<a:lnTo>") >= 30

    svg = drawingml_to_svg(dml)
    assert "<polyline" in svg
    assert 'stroke="#0891b2"' in svg


def test_css_class_and_group_transform_are_applied() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <style>
            .box { fill: #e0e7ff; stroke: #4338ca; stroke-width: 3; }
            text.label { fill: #0f172a; font-size: 20; }
          </style>
          <g transform="translate(10 20) scale(2)">
            <rect class="box" x="5" y="6" width="7" height="8"/>
            <text class="label" x="2" y="10">CSS</text>
          </g>
        </svg>"""
    )
    assert "<a:custGeom>" in dml
    assert 'val="E0E7FF"' in dml
    assert 'val="4338CA"' in dml
    assert 'w="28575"' in dml
    assert "<a:t>CSS</a:t>" in dml

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    assert {"x": "190500", "y": "304800"} in [offset.attrib for offset in offsets]


def test_css_descendant_selectors_are_applied_in_converter_and_analyzer() -> None:
    svg = """<svg>
      <style>
        g .hot { fill: red; }
        #layer rect { stroke: rgb(0, 128, 0); stroke-width: 2; }
      </style>
      <g id="layer"><rect class="hot" x="1" y="2" width="3" height="4"/></g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="FF0000"' in dml
    assert 'val="008000"' in dml
    assert 'w="19050"' in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_compound_child_selectors_hidden_shapes_and_scientific_numbers() -> None:
    svg = """<svg>
      <style>
        g > rect.hot.primary { fill: #f97316; stroke: #7c2d12; }
        .skip { display: none; }
      </style>
      <g>
        <rect class="hot primary" x="1e1" y="2e1" width="3e1" height="4e1"/>
        <rect class="skip" x="0" y="0" width="100" height="100"/>
        <path d="M1e2 0 L1.2e2 2e1 L1e2 4e1 Z" fill="#dbeafe"/>
        <polygon points="1e2,6e1 1.2e2,8e1 8e1,8e1" fill="#fee2e2"/>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count("<p:sp>") == 3
    assert 'val="F97316"' in dml
    assert 'val="7C2D12"' in dml
    assert 'x="95250"' in dml
    report = analyze_svg(svg).to_dict()
    assert report["ignored_elements"] == 1
    assert report["estimated_element_coverage"] == 1.0


def test_text_position_can_come_from_first_tspan() -> None:
    dml = svg_to_drawingml('<svg><text font-size="10" fill="#111"><tspan x="20" y="40">From tspan</tspan></text></svg>')

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    assert shape_off.attrib == {"x": "190500", "y": "285750"}
    assert "<a:t>From tspan</a:t>" in dml


def test_root_viewbox_offsets_and_scales_coordinates() -> None:
    dml = svg_to_drawingml(
        '<svg viewBox="-10 -20 100 50" width="200" height="100"><rect x="-10" y="-20" width="10" height="10"/></svg>'
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "0", "y": "0"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "190500"}


def test_root_viewbox_preserve_aspect_ratio_meet_centers_content() -> None:
    dml = svg_to_drawingml(
        '<svg viewBox="0 0 100 50" width="200" height="200"><rect x="0" y="0" width="100" height="50"/></svg>'
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "0", "y": "476250"}
    assert shape_ext.attrib == {"cx": "1905000", "cy": "952500"}


def test_root_viewbox_preserve_aspect_ratio_none_stretches_content() -> None:
    dml = svg_to_drawingml(
        '<svg viewBox="0 0 100 50" width="200" height="200" preserveAspectRatio="none"><rect x="0" y="0" width="100" height="50"/></svg>'
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "0", "y": "0"}
    assert shape_ext.attrib == {"cx": "1905000", "cy": "1905000"}


def test_symbol_use_viewbox_width_height_scales_referenced_shapes_with_none() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <defs>
            <symbol id="icon" viewBox="-5 -5 10 10" preserveAspectRatio="none">
              <circle cx="0" cy="0" r="5" fill="#2563eb"/>
            </symbol>
          </defs>
          <use href="#icon" x="20" y="30" width="40" height="20"/>
        </svg>"""
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "190500", "y": "285750"}
    assert shape_ext.attrib == {"cx": "381000", "cy": "190500"}
    assert 'val="2563EB"' in dml


def test_symbol_use_viewbox_width_height_preserves_aspect_ratio_by_default() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <defs>
            <symbol id="icon" viewBox="-5 -5 10 10">
              <circle cx="0" cy="0" r="5" fill="#2563eb"/>
            </symbol>
          </defs>
          <use href="#icon" x="20" y="30" width="40" height="20"/>
        </svg>"""
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "285750", "y": "285750"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "190500"}


def test_analyze_svg_reports_coverage_and_unsupported_features() -> None:
    report = analyze_svg(
        """<svg>
          <rect x="0" y="0" width="10" height="10"/>
          <image href="photo.png" x="0" y="0" width="10" height="10"/>
          <path d="M0 0 R10 20 30 0"/>
        </svg>"""
    )

    data = report.to_dict()
    assert data["total_elements"] == 4
    assert data["convertible_elements"] == 2
    assert data["unsupported_elements"] == {"image": 1, "path:unsupported-command": 1}
    assert data["unsupported_attributes"] == {"href": 1}
    assert data["unsupported_path_commands"] == {"R": 1}


def test_quadratic_path_is_approximated_as_custom_geometry() -> None:
    dml = svg_to_drawingml('<svg><path d="M0 0 Q10 20 30 0 T60 0" fill="none" stroke="#be123c"/></svg>')

    assert dml.count("<a:custGeom>") == 1
    assert dml.count("<a:lnTo>") >= 20
    assert analyze_svg('<svg><path d="M0 0 Q10 20 30 0 T60 0"/></svg>').estimated_element_coverage == 1.0


def test_arc_path_is_approximated_as_custom_geometry() -> None:
    dml = svg_to_drawingml('<svg><path d="M0 20 A20 20 0 0 1 40 20" fill="none" stroke="#111111"/></svg>')

    assert dml.count("<a:custGeom>") == 1
    assert dml.count("<a:lnTo>") >= 4
    assert analyze_svg('<svg><path d="M0 20 A20 20 0 0 1 40 20"/></svg>').estimated_element_coverage == 1.0


def test_defs_use_are_expanded_without_rendering_defs_directly() -> None:
    svg = """<svg>
      <defs>
        <g id="glyph"><rect x="0" y="0" width="10" height="8" fill="#123456"/></g>
      </defs>
      <use href="#glyph" x="20" y="30"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count("<p:sp>") == 1
    assert 'val="123456"' in dml
    assert 'x="190500"' in dml
    assert 'y="285750"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}
    assert analyze_svg(svg).to_dict()["estimated_element_coverage"] == 1.0


def test_opacity_is_written_as_drawingml_alpha() -> None:
    dml = svg_to_drawingml(
        '<svg><rect x="0" y="0" width="10" height="8" fill="#ff0000" fill-opacity="0.5" stroke="#0000ff" opacity="0.25"/></svg>'
    )

    assert 'val="12500"' in dml
    assert 'val="25000"' in dml
    svg = drawingml_to_svg(dml)
    assert 'fill-opacity="0.125"' in svg
    assert 'stroke-opacity="0.25"' in svg


def test_css_color_functions_named_colors_and_gradient_fallback() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="grad">
          <stop offset="0%" stop-color="red" stop-opacity="0.5"/>
          <stop offset="100%" style="stop-color: rgb(0, 0, 255); stop-opacity: .25"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="10" height="8" fill="url(#grad)" stroke="rgba(0, 128, 0, .75)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="800080"' in dml
    assert 'val="008000"' in dml
    assert 'val="37500"' in dml
    assert 'val="75000"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_missing_paint_server() -> None:
    report = analyze_svg('<svg><rect width="10" height="8" fill="url(#missing)"/></svg>')

    assert report.unsupported_attributes == {"fill:paint-server": 1}


def test_round_rect_and_stroke_style_convert() -> None:
    dml = svg_to_drawingml(
        '<svg><rect x="1" y="2" width="30" height="20" rx="5" fill="white" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="bevel" stroke-dasharray="8 4"/></svg>'
    )

    assert 'prst="roundRect"' in dml
    assert 'cap="rnd"' in dml
    assert '<a:bevel/>' in dml
    assert '<a:prstDash val="lgDash"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'rx="' in svg
    assert 'stroke-linecap="round"' in svg
    assert 'stroke-linejoin="bevel"' in svg
    assert 'stroke-dasharray="8 3"' in svg


def test_tspan_text_anchor_and_bold_convert() -> None:
    dml = svg_to_drawingml(
        '<svg><text x="100" y="40" text-anchor="middle" font-size="20" font-weight="700" fill="#111111"><tspan>Hello</tspan><tspan x="100" dy="22">World</tspan></text></svg>'
    )

    assert '<a:br/>' in dml
    assert 'b="1"' in dml
    assert '<a:t>Hello</a:t>' in dml
    assert '<a:t>World</a:t>' in dml

    svg = drawingml_to_svg(dml)
    assert "Hello" in svg
    assert "World" in svg
    assert "<tspan" in svg
    assert 'font-weight="bold"' in svg
