from xml.etree import ElementTree as ET

from drawingml_svg import analyze_svg, drawingml_to_svg, svg_to_drawingml
from examples.make_pptx import build_slide_xml, prepare_slide_media

PNG_DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luzQnAAAAABJRU5ErkJggg=="


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

    assert '<rect fill="none" stroke="none" x="5" y="6" width="7" height="8"/>' in svg
    assert 'viewBox="0 0 12 14"' in svg


def test_svg_line_round_trip_keeps_direction_with_flips() -> None:
    svg = drawingml_to_svg(svg_to_drawingml('<svg><line x1="20" y1="30" x2="5" y2="10" stroke="#ff0000"/></svg>'))

    assert '<line fill="none" stroke="#ff0000" stroke-width="1" stroke-linecap="butt" stroke-linejoin="miter" stroke-miterlimit="4" x1="20" y1="30" x2="5" y2="10"/>' in svg


def test_svg_default_paint_is_explicitly_converted() -> None:
    dml = svg_to_drawingml('<svg><rect x="0" y="0" width="10" height="8"/><line x1="0" y1="12" x2="10" y2="12"/></svg>')

    assert 'val="000000"' in dml
    assert dml.count("<a:noFill/>") >= 2

    svg = drawingml_to_svg(dml)
    assert '<rect fill="#000000" stroke="none" x="0" y="0" width="10" height="8"/>' in svg
    assert '<line fill="none" stroke="none" x1="0" y1="12" x2="10" y2="12"/>' in svg


def test_default_stroke_linecap_is_explicitly_flat() -> None:
    dml = svg_to_drawingml('<svg><line x1="0" y1="0" x2="10" y2="0" stroke="#111111"/></svg>')

    assert '<a:ln w="9525" cap="flat">' in dml
    svg = drawingml_to_svg(dml)
    assert 'stroke-width="1"' in svg
    assert 'stroke-linecap="butt"' in svg


def test_default_stroke_linejoin_is_explicitly_miter() -> None:
    dml = svg_to_drawingml('<svg><polygon points="0,0 10,0 5,8" fill="none" stroke="#111111"/></svg>')

    assert '<a:miter lim="400000"/>' in dml
    svg = drawingml_to_svg(dml)
    assert 'stroke-linejoin="miter"' in svg
    assert 'stroke-miterlimit="4"' in svg


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


def test_converted_data_uri_image_can_be_embedded_as_pptx_media() -> None:
    fragment = ET.fromstring(svg_to_drawingml(f'<svg><image href="{PNG_DATA_URI}" x="1" y="2" width="3" height="4"/></svg>'))
    pictures = [
        child
        for child in fragment
        if child.tag == "{http://schemas.openxmlformats.org/presentationml/2006/main}pic"
    ]
    slide_xml = build_slide_xml(pictures)
    prepared_slide, rels, media = prepare_slide_media(slide_xml)

    assert len(media) == 1
    assert media[0][0] == "ppt/media/image1.png"
    assert b"data:image/png" not in prepared_slide
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"' in rels


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
            .box { fill: #e0e7ff !important; stroke: #4338ca; stroke-width: 3 !important; }
            text.label { fill: #0f172a; font-size: 20 !important; }
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


def test_inline_style_important_values_are_normalized() -> None:
    dml = svg_to_drawingml(
        '<svg><rect width="10" height="8" style="fill: #ff0000 !IMPORTANT; stroke: #000000; stroke-width: 2 !important"/></svg>'
    )

    assert 'val="FF0000"' in dml
    assert 'val="000000"' in dml
    assert 'w="19050"' in dml


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


def test_css_attribute_selectors_are_applied() -> None:
    svg = """<svg>
      <style>
        rect[data-tone] { fill: #fef3c7; }
        [data-state="active"] { stroke: #0f766e; stroke-width: 2; }
        *[data-wide] { stroke-width: 3; }
        rect[data-tags~="signal"][data-kind|="meter"] { stroke: #1d4ed8; }
        rect[data-icon^="coverage"][data-icon$="probe"][data-icon*="age-pr"] { fill: #dbeafe; }
      </style>
      <rect data-tone="warm" data-state="active" data-wide="1" x="1" y="2" width="3" height="4"/>
      <rect data-tags="warm signal" data-kind="meter-high" data-icon="coverage-probe" x="6" y="2" width="3" height="4"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="FEF3C7"' in dml
    assert 'val="0F766E"' in dml
    assert 'val="DBEAFE"' in dml
    assert 'val="1D4ED8"' in dml
    assert 'w="28575"' in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_css_specificity_wins_over_later_lower_specificity_rules() -> None:
    svg = """<svg>
      <style>
        #target { fill: #dc2626; }
        .accent { stroke: #16a34a; }
        rect { fill: #2563eb; stroke: #9333ea; }
      </style>
      <rect id="target" class="accent" x="1" y="2" width="3" height="4"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="16A34A"' in dml
    assert 'val="2563EB"' not in dml
    assert 'val="9333EA"' not in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_css_cascade_honors_presentation_inline_and_important_priority() -> None:
    svg = """<svg>
      <style>
        rect { fill: #2563eb; stroke: #9333ea !important; stroke-width: 3 !important; }
        #target { fill: #dc2626; stroke: #16a34a; }
      </style>
      <rect id="target" x="1" y="2" width="3" height="4" fill="#f8fafc" stroke-width="1" style="fill: #f97316; stroke: #0f172a"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="F97316"' in dml
    assert 'val="9333EA"' in dml
    assert 'w="28575"' in dml
    assert 'val="F8FAFC"' not in dml
    assert 'val="0F172A"' not in dml


def test_css_rules_override_presentation_attributes() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <style>rect { fill: #2563eb; stroke-width: 3; }</style>
          <rect width="10" height="8" fill="#f8fafc" stroke="#111111" stroke-width="1"/>
        </svg>"""
    )

    assert 'val="2563EB"' in dml
    assert 'w="28575"' in dml
    assert 'val="F8FAFC"' not in dml
    assert 'w="9525"' not in dml


def test_inline_important_wins_over_stylesheet_important() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <style>rect { fill: #2563eb !important; }</style>
          <rect width="10" height="8" style="fill: #dc2626 !important"/>
        </svg>"""
    )

    assert 'val="DC2626"' in dml
    assert 'val="2563EB"' not in dml


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


def test_rectangular_clip_path_clips_rect_geometry() -> None:
    svg = """<svg>
      <defs><clipPath id="crop"><rect x="10" y="12" width="20" height="10"/></clipPath></defs>
      <rect x="0" y="0" width="50" height="50" fill="#f97316" clip-path="url(#crop)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "95250", "y": "114300"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "95250"}
    assert analyze_svg(svg).unsupported_attributes == {}


def test_object_bounding_box_clip_path_clips_rect_geometry() -> None:
    svg = """<svg>
      <defs><clipPath id="crop" clipPathUnits="objectBoundingBox"><rect x=".25" y=".2" width=".5" height=".4"/></clipPath></defs>
      <rect x="10" y="20" width="80" height="50" fill="#f97316" clip-path="url(#crop)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "285750", "y": "285750"}
    assert shape_ext.attrib == {"cx": "381000", "cy": "190500"}
    assert analyze_svg(svg).unsupported_attributes == {}


def test_non_rectangular_clip_targets_remain_reported_as_unsupported() -> None:
    svg = """<svg>
      <defs><clipPath id="crop"><rect x="10" y="12" width="20" height="10"/></clipPath></defs>
      <ellipse cx="20" cy="20" rx="15" ry="10" clip-path="url(#crop)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"clip-path": 1}


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


def test_nested_svg_viewbox_translates_scales_and_sets_child_viewport() -> None:
    svg = """<svg>
      <svg x="10" y="20" width="40" height="20" viewBox="0 0 20 10" preserveAspectRatio="none">
        <rect x="50%" y="50%" width="25%" height="50%" fill="#0f766e"/>
      </svg>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "476250", "y": "381000"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "190500"}
    assert 'val="0F766E"' in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_percent_lengths_resolve_against_root_viewport() -> None:
    dml = svg_to_drawingml(
        '<svg viewBox="0 0 200 100" width="400" height="200"><rect x="10%" y="20%" width="25%" height="40%"/><line x1="0%" y1="100%" x2="50%" y2="0%" stroke="#111111"/></svg>'
    )

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    extents = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert offsets[1].attrib == {"x": "381000", "y": "381000"}
    assert extents[1].attrib == {"cx": "952500", "cy": "762000"}
    assert offsets[2].attrib == {"x": "0", "y": "0"}
    assert extents[2].attrib == {"cx": "1905000", "cy": "1905000"}


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
    assert data["convertible_elements"] == 3
    assert data["unsupported_elements"] == {"path:unsupported-command": 1}
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
        '<svg><rect x="0" y="0" width="10" height="8" fill="#f008" stroke="#0000ff" opacity="0.25"/></svg>'
    )

    assert 'val="FF0000"' in dml
    assert 'val="13333"' in dml
    assert 'val="25000"' in dml
    svg = drawingml_to_svg(dml)
    assert 'fill-opacity="0.1333"' in svg
    assert 'stroke-opacity="0.25"' in svg


def test_zero_alpha_paint_is_converted_as_no_fill_and_no_line() -> None:
    dml = svg_to_drawingml(
        '<svg><rect width="10" height="8" fill="#111111" fill-opacity="0" stroke="#222222" stroke-opacity="0" stroke-width="2"/></svg>'
    )

    assert 'val="111111"' not in dml
    assert 'val="222222"' not in dml
    assert dml.count("<a:noFill/>") == 2

    svg = drawingml_to_svg(dml)
    assert 'fill="none"' in svg
    assert 'stroke="none"' in svg
    assert 'stroke-width="2"' in svg


def test_css_color_functions_named_colors_and_gradient_fallback() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="grad">
          <stop offset="0%" stop-color="currentColor" stop-opacity="0.5"/>
          <stop offset="100%" style="stop-color: rgb(0, 0, 255); stop-opacity: .25"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="10" height="8" color="red" fill="url(#grad)" stroke="hsl(0.333333turn 100% 25% / 75%)"/>
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


def test_paint_server_fallback_color_is_used_when_server_is_missing() -> None:
    svg = '<svg><rect width="10" height="8" fill="url(#missing) #dc2626" stroke="url(#also-missing) rgb(22 163 74)"/></svg>'
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="16A34A"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_round_rect_and_stroke_style_convert() -> None:
    dml = svg_to_drawingml(
        '<svg><rect x="1" y="2" width="30" height="20" rx="5" fill="white" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="miter" stroke-miterlimit="6" stroke-dasharray="8px, 4px"/></svg>'
    )

    assert 'prst="roundRect"' in dml
    assert 'cap="rnd"' in dml
    assert '<a:miter lim="600000"/>' in dml
    assert '<a:custDash>' in dml
    assert '<a:ds d="400000" sp="200000"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'rx="' in svg
    assert 'stroke-linecap="round"' in svg
    assert 'stroke-linejoin="miter"' in svg
    assert 'stroke-miterlimit="6"' in svg
    assert 'stroke-dasharray="8 4"' in svg


def test_zero_stroke_width_is_converted_as_no_line() -> None:
    dml = svg_to_drawingml('<svg><rect width="10" height="8" fill="#ffffff" stroke="#111111" stroke-width="0"/></svg>')

    assert 'val="111111"' not in dml
    assert "<a:noFill/>" in dml

    svg = drawingml_to_svg(dml)
    assert 'stroke="none"' in svg
    assert 'stroke-width="0"' in svg


def test_pt_units_are_converted_to_px() -> None:
    dml = svg_to_drawingml(
        '<svg><text x="0" y="20" font-size="12pt" fill="#111111">Pt</text><line x1="0" y1="30" x2="40" y2="30" stroke="#222222" stroke-width="1.5pt" stroke-dasharray="6pt 3pt"/></svg>'
    )

    assert 'sz="1600"' in dml
    assert '<a:ln w="19050" cap="flat">' in dml
    assert '<a:ds d="400000" sp="200000"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'font-size="16"' in svg
    assert 'fill="#111111"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-dasharray="8 4"' in svg


def test_absolute_length_units_are_converted_to_px() -> None:
    dml = svg_to_drawingml(
        '<svg><rect x="0" y="0" width="1in" height="2.54cm" fill="none" stroke="#111111" stroke-width="1mm" stroke-dasharray="2mm 1mm"/></svg>'
    )

    assert 'cx="914400"' in dml
    assert 'cy="914400"' in dml
    assert '<a:ln w="36000" cap="flat">' in dml
    assert '<a:ds d="200000" sp="100000"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'width="96"' in svg
    assert 'height="96"' in svg
    assert 'stroke-width="3.7795"' in svg
    assert 'stroke-dasharray="7.5591 3.7795"' in svg


def test_line_markers_convert_to_drawingml_arrows_and_round_trip() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <line x1="0" y1="0" x2="40" y2="10" stroke="#111111" stroke-width="2" marker-start="url(#arrow)" marker-end="url(#arrow)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert '<a:tailEnd type="triangle"/>' in dml
    assert '<a:headEnd type="triangle"/>' in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert '<marker id="drawingml-svg-arrow"' in round_trip
    assert 'marker-start="url(#drawingml-svg-arrow)"' in round_trip
    assert 'marker-end="url(#drawingml-svg-arrow)"' in round_trip


def test_data_uri_image_converts_to_picture_and_round_trips() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16"/></svg>'
    dml = svg_to_drawingml(svg)

    assert "<p:pic>" in dml
    assert "<a:blip" in dml
    assert PNG_DATA_URI in dml
    assert analyze_svg(svg).unsupported_elements == {}
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert "<image" in round_trip
    assert f'href="{PNG_DATA_URI}"' in round_trip


def test_unsupported_marker_usage_is_reported() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <polygon points="0,0 20,0 10,10" marker-end="url(#arrow)"/>
      <polyline points="30,0 40,10 50,0" marker-mid="url(#arrow)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"marker-end": 1, "marker-mid": 1}


def test_tspan_text_anchor_and_bold_convert() -> None:
    dml = svg_to_drawingml(
        '<svg><text x="100" y="40" text-anchor="middle" dominant-baseline="middle" font-size="20" font-weight="700" font-style="italic" font-family="\'Aptos Display\', Arial, sans-serif" text-decoration="underline line-through" fill="#111111"><tspan>Hello</tspan><tspan x="100" dy="22">World</tspan></text></svg>'
    )

    assert '<a:br/>' in dml
    assert 'anchor="ctr"' in dml
    assert '<a:pPr algn="ctr"/>' in dml
    assert 'b="1"' in dml
    assert 'i="1"' in dml
    assert 'u="sng"' in dml
    assert 'strike="sngStrike"' in dml
    assert 'typeface="Aptos Display"' in dml
    assert '<a:t>Hello</a:t>' in dml
    assert '<a:t>World</a:t>' in dml

    svg = drawingml_to_svg(dml)
    assert "Hello" in svg
    assert "World" in svg
    assert "<tspan" in svg
    assert 'font-weight="bold"' in svg
    assert 'font-style="italic"' in svg
    assert 'font-family="Aptos Display"' in svg
    assert 'text-decoration="underline line-through"' in svg
    assert 'text-anchor="middle"' in svg
    assert 'dominant-baseline="middle"' in svg
    assert 'x="100"' in svg
    assert 'y="40"' in svg
