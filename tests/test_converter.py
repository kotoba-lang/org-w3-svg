import io
import zipfile
from importlib import resources
from xml.etree import ElementTree as ET

import pytest

import drawingml_svg
from drawingml_svg import analyze_svg, drawingml_to_svg, svg_to_drawingml
from drawingml_svg.cli import main as cli_main
from examples.make_pptx import build_slide_xml, main as make_pptx_main, prepare_slide_media, write_pptx

PNG_DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luzQnAAAAABJRU5ErkJggg=="


def test_package_declares_inline_types() -> None:
    assert resources.files(drawingml_svg).joinpath("py.typed").is_file()


def test_cli_analyze_writes_json_to_stdout(tmp_path, capsys) -> None:
    source = tmp_path / "input.svg"
    source.write_text('<svg><rect width="10" height="8"/></svg>', encoding="utf-8")

    assert cli_main(["analyze", str(source)]) == 0
    captured = capsys.readouterr()

    assert '"estimated_element_coverage": 1.0' in captured.out
    assert '"unsupported_attributes": {}' in captured.out


def test_cli_converts_between_files_and_creates_output_parent(tmp_path) -> None:
    source = tmp_path / "input.svg"
    dml_output = tmp_path / "nested" / "shape.xml"
    svg_output = tmp_path / "roundtrip.svg"
    source.write_text('<svg><rect x="1" y="2" width="3" height="4" fill="#123456"/></svg>', encoding="utf-8")

    assert cli_main(["svg2dml", str(source), "-o", str(dml_output)]) == 0
    assert dml_output.is_file()
    assert 'val="123456"' in dml_output.read_text(encoding="utf-8")

    assert cli_main(["dml2svg", str(dml_output), "-o", str(svg_output)]) == 0
    assert 'fill="#123456"' in svg_output.read_text(encoding="utf-8")


def test_cli_svg2dml_reads_stdin_and_writes_stdout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO('<svg><rect x="1" y="2" width="3" height="4" fill="#123456"/></svg>'),
    )

    assert cli_main(["svg2dml"]) == 0
    captured = capsys.readouterr()

    assert "<p:spTree" in captured.out
    assert 'val="123456"' in captured.out


def test_cli_dml2svg_reads_dash_stdin_and_writes_dash_stdout(monkeypatch, capsys) -> None:
    dml = svg_to_drawingml('<svg><rect x="1" y="2" width="3" height="4" fill="#123456"/></svg>')
    monkeypatch.setattr("sys.stdin", io.StringIO(dml))

    assert cli_main(["dml2svg", "-", "-o", "-"]) == 0
    captured = capsys.readouterr()

    assert "<svg" in captured.out
    assert 'fill="#123456"' in captured.out


def test_cli_alias_invocation_uses_executable_name(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.svg"
    output = tmp_path / "shape.xml"
    source.write_text('<svg><rect width="10" height="8"/></svg>', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["svg2dml", str(source), "-o", str(output)])

    assert cli_main() == 0
    assert output.is_file()
    assert "<p:sp>" in output.read_text(encoding="utf-8")


def test_cli_reports_missing_input_without_traceback(tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["svg2dml", str(tmp_path / "missing.svg")])

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "drawingml-svg: error:" in captured.err
    assert "missing.svg" in captured.err
    assert "Traceback" not in captured.err


def test_cli_reports_invalid_xml_without_traceback(tmp_path, capsys) -> None:
    source = tmp_path / "broken.svg"
    source.write_text("<svg><rect></svg>", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        cli_main(["analyze", str(source)])

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "drawingml-svg: error:" in captured.err
    assert "mismatched tag" in captured.err
    assert "Traceback" not in captured.err


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


def test_transformed_line_stays_as_editable_line_shape() -> None:
    dml = svg_to_drawingml('<svg><g transform="translate(10 20) rotate(90)"><line x1="0" y1="0" x2="10" y2="0" stroke="#0f766e"/></g></svg>')

    assert 'prst="line"' in dml
    assert "<a:custGeom>" not in dml
    assert 'x="95250"' in dml
    assert 'y="190500"' in dml
    assert 'cy="95250"' in dml
    assert 'val="0F766E"' in dml


def test_svg_default_paint_is_explicitly_converted() -> None:
    dml = svg_to_drawingml('<svg><rect x="0" y="0" width="10" height="8"/><line x1="0" y1="12" x2="10" y2="12"/></svg>')

    assert 'val="000000"' in dml
    assert dml.count("<a:noFill/>") >= 2

    svg = drawingml_to_svg(dml)
    assert '<rect fill="#000000" stroke="none" x="0" y="0" width="10" height="8"/>' in svg
    assert '<line fill="none" stroke="none" x1="0" y1="12" x2="10" y2="12"/>' in svg


def test_non_rendering_non_positive_dimension_shapes_are_skipped() -> None:
    dml = svg_to_drawingml(
        f"""<svg>
          <rect x="0" y="0" width="0" height="8"/>
          <rect x="0" y="10" width="8" height="-2"/>
          <circle cx="10" cy="10" r="0"/>
          <ellipse cx="20" cy="20" rx="8" ry="0"/>
          <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="0"/>
        </svg>"""
    )

    assert "<p:sp>" not in dml
    assert "<p:pic>" not in dml


def test_analyze_svg_ignores_non_rendering_non_positive_dimension_shapes() -> None:
    report = analyze_svg(
        """<svg viewBox="0 0 100 100">
          <rect width="0%" height="8" filter="url(#blur)"/>
          <circle cx="10" cy="10" r="0" mix-blend-mode="multiply"/>
          <ellipse cx="20" cy="20" rx="8" ry="-1" shape-rendering="crispEdges"/>
          <image href="photo.png" width="50%" height="0"/>
        </svg>"""
    )

    assert report.convertible_elements == 1
    assert report.ignored_elements == 4
    assert report.unsupported_attributes == {}


def test_css_geometry_properties_convert_for_basic_shapes() -> None:
    dml = svg_to_drawingml(
        """<svg viewBox="0 0 100 100">
          <style>
            .box { x: 10%; y: 6px; width: 20%; height: 12px; rx: 3px; fill: #ef4444; }
            .dot { cx: 44px; cy: 18px; r: 5px; fill: #22c55e; }
            .oval { cx: 64px; cy: 18px; rx: 7px; ry: 4px; fill: #3b82f6; }
            .rule { x1: 4px; y1: 36px; x2: 40px; y2: 36px; stroke: #111111; }
          </style>
          <rect class="box"/>
          <circle class="dot"/>
          <ellipse class="oval"/>
          <line class="rule"/>
        </svg>"""
    )

    assert dml.count("<p:sp>") == 4
    assert 'prst="roundRect"' in dml
    assert 'x="95250"' in dml
    assert 'y="57150"' in dml
    assert 'cx="190500"' in dml
    assert 'cy="114300"' in dml
    assert analyze_svg(
        '<svg><style>.box { width: 20px; height: 12px; }</style><rect class="box"/></svg>'
    ).unsupported_attributes == {}


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


def test_invalid_data_uri_image_is_not_embedded_as_pptx_media() -> None:
    slide_xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:cSld><p:spTree><p:pic><p:blipFill><a:blip r:embed="data:image/png;base64,abc"/></p:blipFill></p:pic></p:spTree></p:cSld>
    </p:sld>"""

    prepared_slide, rels, media = prepare_slide_media(slide_xml)

    assert media == []
    assert b"data:image/png;base64,abc" in prepared_slide
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"' not in rels


def test_write_pptx_creates_package_with_unique_relationship_ids(tmp_path) -> None:
    fragment = ET.fromstring(
        svg_to_drawingml(f'<svg><rect width="10" height="8"/><image href="{PNG_DATA_URI}" x="12" y="0" width="8" height="8"/></svg>')
    )
    shapes = [
        child
        for child in fragment
        if child.tag
        in {
            "{http://schemas.openxmlformats.org/presentationml/2006/main}sp",
            "{http://schemas.openxmlformats.org/presentationml/2006/main}pic",
        }
    ]
    pptx_path = tmp_path / "nested" / "sample.pptx"

    write_pptx(pptx_path, build_slide_xml(shapes))

    assert pptx_path.is_file()
    with zipfile.ZipFile(pptx_path) as pptx:
        names = set(pptx.namelist())
        root_rels = ET.fromstring(pptx.read("_rels/.rels"))
        slide_rels = ET.fromstring(pptx.read("ppt/slides/_rels/slide1.xml.rels"))
    assert {"[Content_Types].xml", "ppt/slides/slide1.xml", "ppt/slides/_rels/slide1.xml.rels"} <= names
    assert any(name.startswith("ppt/media/image") for name in names)
    for rels in (root_rels, slide_rels):
        ids = [rel.get("Id") for rel in rels]
        assert len(ids) == len(set(ids))


def test_make_pptx_cli_writes_valid_package(tmp_path) -> None:
    source = tmp_path / "input.svg"
    output = tmp_path / "nested" / "sample.pptx"
    source.write_text(f'<svg><rect width="10" height="8"/><image href="{PNG_DATA_URI}" x="12" y="0" width="8" height="8"/></svg>', encoding="utf-8")

    assert make_pptx_main([str(source), "-o", str(output)]) == 0

    with zipfile.ZipFile(output) as pptx:
        names = set(pptx.namelist())
        slide = pptx.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "ppt/slides/slide1.xml" in names
    assert "ppt/slides/_rels/slide1.xml.rels" in names
    assert "<p:sp>" in slide
    assert "<p:pic>" in slide
    assert any(name.startswith("ppt/media/image") for name in names)


def test_make_pptx_cli_reports_errors_without_traceback(tmp_path, capsys) -> None:
    source = tmp_path / "empty.svg"
    source.write_text("<svg><defs><rect width='10' height='8'/></defs></svg>", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        make_pptx_main([str(source), "-o", str(tmp_path / "out.pptx")])

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "make_pptx.py: error: input did not produce any DrawingML shapes" in captured.err
    assert "Traceback" not in captured.err


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
    assert 'prst="rect"' in dml
    assert "<a:custGeom>" not in dml
    assert 'val="E0E7FF"' in dml
    assert 'val="4338CA"' in dml
    assert 'w="57150"' in dml
    assert "<a:t>CSS</a:t>" in dml

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    assert {"x": "190500", "y": "304800"} in [offset.attrib for offset in offsets]


def test_group_scale_applies_to_stroke_width_and_dasharray() -> None:
    dml = svg_to_drawingml(
        '<svg><g transform="scale(2)"><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4"/></g></svg>'
    )

    assert 'w="38100"' in dml
    assert '<a:ds d="400000" sp="200000"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'stroke-width="4"' in svg
    assert 'stroke-dasharray="16 8"' in svg


def test_non_scaling_stroke_keeps_stroke_width_and_dasharray_under_scale() -> None:
    source = '<svg><g transform="scale(2)"><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" vector-effect="non-scaling-stroke"/></g></svg>'
    dml = svg_to_drawingml(source)

    assert 'w="19050"' in dml
    assert '<a:ds d="400000" sp="200000"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-width="2"' in svg
    assert 'stroke-dasharray="8 4"' in svg


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


def test_analyze_svg_skips_hidden_unsupported_details() -> None:
    svg = """<svg>
      <path display="none" d="M0 0 R10 20" filter="url(#blur)"/>
      <g visibility="hidden">
        <foreignObject width="10" height="10"/>
        <path d="M0 0 R10 20"/>
      </g>
    </svg>"""

    report = analyze_svg(svg)

    assert report.ignored_elements == 2
    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {}
    assert report.unsupported_path_commands == {}


def test_text_position_can_come_from_first_tspan() -> None:
    dml = svg_to_drawingml('<svg><text font-size="10" fill="#111"><tspan x="20" y="40" dx="5" dy="7">From tspan</tspan></text></svg>')

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    assert shape_off.attrib == {"x": "238125", "y": "352425"}
    assert "<a:t>From tspan</a:t>" in dml


def test_text_position_applies_text_dx_dy() -> None:
    dml = svg_to_drawingml('<svg><text x="10" y="20" dx="4" dy="6" font-size="10" fill="#111">Shifted</text></svg>')

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    assert shape_off.attrib == {"x": "133350", "y": "152400"}


def test_text_single_rotate_maps_to_shape_rotation() -> None:
    dml = svg_to_drawingml('<svg><text x="10" y="20" rotate="30" font-size="10" fill="#111">Rotated</text></svg>')

    root = ET.fromstring(dml)
    shape_xfrm = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")[1]
    assert shape_xfrm.get("rot") == "1800000"
    assert analyze_svg('<svg><text x="10" y="20" rotate="30">Rotated</text></svg>').unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'rotate="30"' in svg


def test_zero_multi_value_text_rotate_is_not_reported_as_unsupported() -> None:
    svg = '<svg><text x="10" y="20"><tspan rotate="0 0 0">Flat</tspan></text></svg>'

    assert analyze_svg(svg).unsupported_attributes == {}


def test_equal_multi_value_text_rotate_maps_to_shape_rotation() -> None:
    dml = svg_to_drawingml('<svg><text x="10" y="20" rotate="12 12" font-size="10" fill="#111">Tilt</text></svg>')

    root = ET.fromstring(dml)
    shape_xfrm = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")[1]
    assert shape_xfrm.get("rot") == "720000"
    assert analyze_svg('<svg><text x="10" y="20" rotate="12 12">Tilt</text></svg>').unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'rotate="12"' in svg


def test_single_character_multi_value_text_rotate_uses_first_value() -> None:
    dml = svg_to_drawingml('<svg><text x="10" y="20" rotate="12 24" font-size="10" fill="#111">A</text></svg>')

    root = ET.fromstring(dml)
    shape_xfrm = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")[1]
    assert shape_xfrm.get("rot") == "720000"
    assert analyze_svg('<svg><text x="10" y="20" rotate="12 24">A</text></svg>').unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'rotate="12"' in svg


def test_text_letter_spacing_maps_to_character_spacing() -> None:
    source = '<svg><text x="10" y="20" letter-spacing="2px" font-size="10" fill="#111">Spaced</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    assert run_pr is not None
    assert run_pr.get("spc") == "150"
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'letter-spacing="2"' in svg


def test_text_length_spacing_maps_to_character_spacing() -> None:
    source = '<svg><text x="10" y="20" textLength="48" lengthAdjust="spacing" font-size="10" fill="#111">Wide</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert run_pr is not None
    assert run_pr.get("spc") == "300"
    assert shape_ext.get("cx") == "457200"
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'letter-spacing="4"' in svg


def test_text_length_spacing_and_glyphs_is_approximated_with_character_spacing() -> None:
    source = '<svg><text x="10" y="20" textLength="48" lengthAdjust="spacingAndGlyphs" font-size="10" fill="#111">Wide</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert run_pr is not None
    assert run_pr.get("spc") == "300"
    assert shape_ext.get("cx") == "457200"
    assert analyze_svg(source).unsupported_attributes == {}


def test_word_spacing_without_spaces_is_not_reported_as_unsupported() -> None:
    source = '<svg><text x="10" y="20" word-spacing="4px" font-size="10" fill="#111">Compact<tspan>Label</tspan></text></svg>'

    assert analyze_svg(source).unsupported_attributes == {}


def test_word_spacing_maps_to_distributed_character_spacing() -> None:
    source = '<svg><text x="10" y="20" word-spacing="6px" font-size="10" fill="#111">Hi all</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert run_pr is not None
    assert run_pr.get("spc") == "90"
    assert shape_ext.get("cx") == "571500"
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'letter-spacing="1.2"' in svg


def test_text_small_caps_maps_to_drawingml_caps() -> None:
    source = '<svg><text x="10" y="20" font-variant="small-caps" font-size="10" fill="#111">Caps</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    assert run_pr is not None
    assert run_pr.get("cap") == "small"
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'font-variant="small-caps"' in svg


def test_text_all_small_caps_maps_to_drawingml_caps() -> None:
    source = '<svg><text x="10" y="20" font-variant="all-small-caps" font-size="10" fill="#111">Caps</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    assert run_pr is not None
    assert run_pr.get("cap") == "all"
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'font-variant="all-small-caps"' in svg


def test_xml_space_preserve_keeps_text_whitespace() -> None:
    dml = svg_to_drawingml(
        '<svg><text x="0" y="20" xml:space="preserve" fill="#111111">  padded  <tspan> kept </tspan></text></svg>'
    )

    assert "<a:t>  padded  </a:t>" in dml
    assert "<a:t> kept </a:t>" in dml
    assert analyze_svg('<svg><text xml:space="preserve">  padded  </text></svg>').unsupported_attributes == {}


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


def test_rectangular_clip_path_clips_image_geometry() -> None:
    svg = f"""<svg>
      <defs><clipPath id="crop"><rect x="4" y="3" width="6" height="5"/></clipPath></defs>
      <image href="{PNG_DATA_URI}" x="0" y="0" width="12" height="10" clip-path="url(#crop)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    picture = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic")
    assert picture is not None
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "38100", "y": "28575"}
    assert shape_ext.attrib == {"cx": "57150", "cy": "47625"}
    assert PNG_DATA_URI in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_object_bounding_box_clip_path_clips_image_geometry() -> None:
    svg = f"""<svg>
      <defs><clipPath id="crop" clipPathUnits="objectBoundingBox"><rect x=".25" y=".2" width=".5" height=".4"/></clipPath></defs>
      <image href="{PNG_DATA_URI}" x="10" y="20" width="80" height="50" clip-path="url(#crop)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    picture = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic")
    assert picture is not None
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "285750", "y": "285750"}
    assert shape_ext.attrib == {"cx": "381000", "cy": "190500"}
    assert PNG_DATA_URI in dml
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
    assert 'prst="rect"' in dml
    assert "<a:custGeom>" not in dml
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


def test_root_viewbox_preserve_aspect_ratio_slice_aligns_max_edges() -> None:
    dml = svg_to_drawingml(
        '<svg viewBox="0 0 100 50" width="200" height="200" preserveAspectRatio="xMaxYMax slice"><rect x="0" y="0" width="100" height="50"/></svg>'
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "-1905000", "y": "0"}
    assert shape_ext.attrib == {"cx": "3810000", "cy": "1905000"}


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
    assert 'prst="rect"' in dml
    assert "<a:custGeom>" not in dml
    assert shape_off.attrib == {"x": "476250", "y": "381000"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "190500"}
    assert 'val="0F766E"' in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_scaled_rounded_rect_stays_as_editable_round_rect() -> None:
    dml = svg_to_drawingml(
        '<svg><g transform="translate(10 20) scale(2 3)"><rect x="5" y="4" width="20" height="10" rx="3" ry="2" fill="#f97316"/></g></svg>'
    )

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert 'prst="roundRect"' in dml
    assert "<a:custGeom>" not in dml
    assert shape_off.attrib == {"x": "190500", "y": "304800"}
    assert shape_ext.attrib == {"cx": "381000", "cy": "285750"}
    assert analyze_svg('<svg><g transform="scale(2)"><rect width="10" height="8"/></g></svg>').estimated_element_coverage == 1.0


def test_rotated_rect_stays_as_editable_rect_with_rotation() -> None:
    svg = '<svg><rect x="10" y="12" width="20" height="16" fill="#f97316" transform="rotate(90 20 20)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "5400000"
    assert 'prst="rect"' in dml
    assert "<a:custGeom>" not in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'transform="rotate(90 20 20)"' in round_trip


def test_reflected_rect_stays_as_editable_rect() -> None:
    svg = '<svg><rect x="10" y="12" width="20" height="16" fill="#f97316" transform="scale(-1 1)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "10800000"
    assert 'prst="rect"' in dml
    assert "<a:custGeom>" not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_scaled_circle_and_ellipse_stay_as_editable_ellipses() -> None:
    dml = svg_to_drawingml(
        """<svg>
          <g transform="translate(10 20) scale(2 3)">
            <circle cx="5" cy="4" r="3" fill="#22c55e"/>
            <ellipse cx="15" cy="8" rx="4" ry="2" fill="#3b82f6"/>
          </g>
        </svg>"""
    )

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    extents = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert dml.count('prst="ellipse"') == 2
    assert "<a:custGeom>" not in dml
    assert offsets[1].attrib == {"x": "133350", "y": "219075"}
    assert extents[1].attrib == {"cx": "114300", "cy": "171450"}
    assert offsets[2].attrib == {"x": "304800", "y": "361950"}
    assert extents[2].attrib == {"cx": "152400", "cy": "114300"}
    assert analyze_svg('<svg><g transform="scale(2 3)"><circle cx="5" cy="4" r="3"/></g></svg>').estimated_element_coverage == 1.0


def test_rotated_ellipse_stays_as_editable_ellipse_with_rotation() -> None:
    svg = '<svg><ellipse cx="20" cy="20" rx="10" ry="6" fill="#3b82f6" transform="rotate(90 20 20)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "5400000"
    assert 'prst="ellipse"' in dml
    assert "<a:custGeom>" not in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'transform="rotate(90 20 20)"' in round_trip


def test_reflected_ellipse_stays_as_editable_ellipse() -> None:
    svg = '<svg><ellipse cx="20" cy="20" rx="10" ry="6" fill="#3b82f6" transform="scale(-1 1)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "10800000"
    assert 'prst="ellipse"' in dml
    assert "<a:custGeom>" not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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
    assert 'prst="ellipse"' in dml
    assert "<a:custGeom>" not in dml
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


def test_xlink_use_reference_converts() -> None:
    svg = """<svg xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs><g id="glyph"><rect x="0" y="0" width="10" height="8" fill="#123456"/></g></defs>
      <use xlink:href="#glyph" x="20" y="30"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="123456"' in dml
    assert 'x="190500"' in dml
    assert 'y="285750"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_analyze_svg_reports_unconverted_visual_attributes() -> None:
    svg = f"""<svg>
      <style>
        path {{ clip-rule: evenodd; paint-order: stroke fill; vector-effect: non-scaling-stroke; shape-rendering: crispEdges; mix-blend-mode: multiply; }}
        text {{ text-rendering: geometricPrecision; }}
      </style>
      <path d="M0 0 H10 V10 Z" fill-rule="evenodd"/>
      <rect width="10" height="8" filter="url(#blur)" mask="url(#fade)"/>
      <text x="0" y="20" isolation="isolate">Hint</text>
      <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="8" image-rendering="pixelated" color-rendering="optimizeQuality"/>
      <defs><linearGradient id="spread" spreadMethod="reflect" gradientUnits="userSpaceOnUse" gradientTransform="rotate(15)"><stop stop-color="#fff"/></linearGradient></defs>
    </svg>"""

    report = analyze_svg(svg)

    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {
        "clip-rule": 1,
        "fill-rule": 1,
        "filter": 1,
        "isolation": 1,
        "mask": 1,
        "mix-blend-mode": 1,
        "paint-order": 1,
    }


def test_invalid_data_uri_image_is_reported_and_not_converted() -> None:
    svg = '<svg><image href="data:image/png;base64,abc" x="0" y="0" width="10" height="8"/></svg>'

    assert "<p:pic>" not in svg_to_drawingml(svg)
    assert analyze_svg(svg).unsupported_attributes == {"href": 1}


def test_analyze_svg_ignores_default_visual_attribute_values() -> None:
    svg = """<svg>
      <path
        d="M0 0 H10 V10 Z"
        clip-path="none"
        clip-rule="nonzero"
        fill-rule="nonzero"
        filter="none"
        marker-start="none"
        marker-mid="none"
        marker-end="none"
        mask="none"
        paint-order="fill stroke markers"
        pathLength="100"
        shape-rendering="auto"
        vector-effect="none"
      />
      <text x="0" y="20" text-rendering="auto">Auto</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_ignores_rendering_quality_hints() -> None:
    svg = """<svg>
      <path d="M0 0 H10 V10 Z" color-rendering="optimizeQuality" shape-rendering="crispEdges"/>
      <image href="photo.png" x="0" y="0" width="10" height="8" image-rendering="pixelated"/>
      <text x="0" y="20" text-rendering="geometricPrecision">Hint</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"href": 1}


def test_analyze_svg_deduplicates_isolation_when_blend_is_reported() -> None:
    svg = """<svg>
      <g isolation="isolate">
        <rect width="10" height="8" mix-blend-mode="multiply"/>
      </g>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"mix-blend-mode": 1}


def test_analyze_svg_ignores_noop_blend_and_dash_offset() -> None:
    svg = """<svg>
      <rect width="10" height="8" mix-blend-mode="normal"/>
      <path d="M0 0 L10 0" stroke="#111111" stroke-dasharray="4 2" stroke-dashoffset="0"/>
      <path d="M0 4 L10 4" stroke="#111111" stroke-dasharray="4 2" stroke-dashoffset="12"/>
      <path d="M0 8 L10 8" stroke="#111111" stroke-dasharray="2 1 3" stroke-dashoffset="-12"/>
      <path d="M0 12 L10 12" stroke="#111111" stroke-dashoffset="2"/>
      <path d="M0 16 L10 16" stroke="none" stroke-dasharray="4 2" stroke-dashoffset="2"/>
      <path d="M0 20 L10 20" stroke="#111111" stroke-opacity="0" stroke-dasharray="4 2" stroke-dashoffset="2"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_gradient_attributes_without_color_fallback() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="empty" spreadMethod="repeat" gradientUnits="userSpaceOnUse" gradientTransform="rotate(15)"/>
      </defs>
      <rect width="10" height="8" fill="url(#empty)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "fill:paint-server": 1,
        "gradientTransform": 1,
        "gradientUnits": 1,
        "spreadMethod": 1,
    }


def test_analyze_svg_reports_unconverted_layout_length_attributes() -> None:
    svg = """<svg>
      <path d="M0 0 L10 0" pathLength="100" stroke="#111111" stroke-dasharray="4 2" stroke-dashoffset="2"/>
      <text x="0" y="10" textLength="80" lengthAdjust="spacingAndGlyphs" font-variant="all-small-caps" word-spacing="4">
        <tspan rotate="15 0">Fit word</tspan>
      </text>
    </svg>"""

    report = analyze_svg(svg)

    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {
        "pathLength": 1,
        "rotate": 1,
        "word-spacing": 1,
    }


def test_text_stroke_maps_to_run_outline() -> None:
    svg = '<svg><text x="0" y="10" fill="#111111" stroke="#ffffff" stroke-width="2" stroke-opacity=".5">Outlined</text></svg>'

    report = analyze_svg(svg)
    dml = svg_to_drawingml(svg)

    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {}
    assert '<a:ln w="19050">' in dml
    assert 'val="FFFFFF"' in dml
    assert 'val="50000"' in dml

    round_trip = drawingml_to_svg(dml)
    assert 'stroke="#ffffff"' in round_trip
    assert 'stroke-width="2"' in round_trip
    assert 'stroke-opacity="0.5"' in round_trip


def test_text_stroke_width_scales_with_transform() -> None:
    svg = '<svg><text x="0" y="10" fill="#111111" stroke="#ffffff" stroke-width="2" transform="scale(2)">Outlined</text></svg>'

    dml = svg_to_drawingml(svg)

    assert '<a:rPr sz="3200">' in dml
    assert '<a:ln w="38100">' in dml

    round_trip = drawingml_to_svg(dml)
    assert 'font-size="32"' in round_trip
    assert 'stroke-width="4"' in round_trip


def test_text_non_scaling_stroke_width_survives_transform() -> None:
    svg = '<svg><text x="0" y="10" fill="#111111" stroke="#ffffff" stroke-width="2" vector-effect="non-scaling-stroke" transform="scale(2)">Outlined</text></svg>'

    dml = svg_to_drawingml(svg)

    assert '<a:rPr sz="3200">' in dml
    assert '<a:ln w="19050">' in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'font-size="32"' in round_trip
    assert 'stroke-width="2"' in round_trip


def test_quadratic_path_is_approximated_as_custom_geometry() -> None:
    dml = svg_to_drawingml('<svg><path d="M0 0 Q10 20 30 0 T60 0" fill="none" stroke="#be123c"/></svg>')

    assert dml.count("<a:custGeom>") == 1
    assert dml.count("<a:lnTo>") >= 20
    assert analyze_svg('<svg><path d="M0 0 Q10 20 30 0 T60 0"/></svg>').estimated_element_coverage == 1.0


def test_drawingml_quadratic_custom_geometry_round_trips_to_polyline() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="curve"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="571500" cy="190500"/></a:xfrm>
          <a:custGeom>
            <a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>
            <a:pathLst>
              <a:path w="571500" h="190500">
                <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
                <a:quadBezTo>
                  <a:pt x="285750" y="190500"/>
                  <a:pt x="571500" y="0"/>
                </a:quadBezTo>
              </a:path>
            </a:pathLst>
          </a:custGeom>
          <a:ln><a:solidFill><a:srgbClr val="BE123C"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<polyline" in svg
    assert 'stroke="#be123c"' in svg
    assert svg.count(",") >= 12
    assert "60,0" in svg


def test_drawingml_cubic_custom_geometry_round_trips_to_polyline() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="curve"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="190500"/></a:xfrm>
          <a:custGeom>
            <a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>
            <a:pathLst>
              <a:path w="762000" h="190500">
                <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
                <a:cubicBezTo>
                  <a:pt x="95250" y="190500"/>
                  <a:pt x="285750" y="190500"/>
                  <a:pt x="381000" y="0"/>
                </a:cubicBezTo>
                <a:cubicBezTo>
                  <a:pt x="476250" y="-190500"/>
                  <a:pt x="666750" y="-190500"/>
                  <a:pt x="762000" y="0"/>
                </a:cubicBezTo>
              </a:path>
            </a:pathLst>
          </a:custGeom>
          <a:ln><a:solidFill><a:srgbClr val="0891B2"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<polyline" in svg
    assert 'stroke="#0891b2"' in svg
    assert svg.count(",") >= 32
    assert "80,0" in svg


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


def test_analyze_svg_reports_unsupported_use_references() -> None:
    missing = analyze_svg('<svg><use href="#missing" x="20" y="30"/></svg>').to_dict()
    external = analyze_svg('<svg><use href="icons.svg#glyph" x="20" y="30"/></svg>').to_dict()

    assert missing["convertible_elements"] == 1
    assert missing["unsupported_elements"] == {"use:unsupported-reference": 1}
    assert missing["unsupported_attributes"] == {"href": 1}
    assert missing["estimated_element_coverage"] == 0.5
    assert external["unsupported_elements"] == {"use:unsupported-reference": 1}
    assert external["unsupported_attributes"] == {"href": 1}


def test_link_wrapper_converts_child_shapes_and_reports_href_only() -> None:
    svg = """<svg>
      <a href="https://example.test" fill="#dbeafe" stroke="#1d4ed8">
        <rect x="4" y="6" width="20" height="10"/>
      </a>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg).to_dict()

    assert dml.count("<p:sp>") == 1
    assert 'val="DBEAFE"' in dml
    assert 'val="1D4ED8"' in dml
    assert report["estimated_element_coverage"] == 1.0
    assert report["unsupported_elements"] == {}
    assert report["unsupported_attributes"] == {"href": 1}


def test_switch_renders_first_supported_branch_only() -> None:
    svg = """<svg>
      <switch>
        <rect requiredExtensions="https://example.test/ext" x="0" y="0" width="10" height="10" fill="#123abc"/>
        <rect x="0" y="0" width="10" height="10" fill="#16a34a"/>
        <rect x="0" y="0" width="10" height="10" fill="#2563eb"/>
      </switch>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg).to_dict()

    assert dml.count("<p:sp>") == 1
    assert 'val="16A34A"' in dml
    assert 'val="123ABC"' not in dml
    assert 'val="2563EB"' not in dml
    assert report["estimated_element_coverage"] == 1.0
    assert report["total_elements"] == 3
    assert report["unsupported_elements"] == {}
    assert report["unsupported_attributes"] == {}


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
      <style>
        stop.start { stop-color: currentColor; stop-opacity: 0.5; }
        stop.end { stop-color: rgb(0, 0, 255); stop-opacity: .25; }
      </style>
      <defs>
        <linearGradient id="grad">
          <stop class="start" offset="0%"/>
          <stop class="end" offset="100%"/>
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


def test_radial_gradient_fallback_uses_outer_stop_color() -> None:
    svg = """<svg>
      <defs>
        <radialGradient id="halo">
          <stop offset="0%" stop-color="#fef3c7"/>
          <stop offset="100%" stop-color="#92400e" stop-opacity=".6"/>
        </radialGradient>
      </defs>
      <circle cx="10" cy="10" r="8" fill="url(#halo)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="92400E"' in dml
    assert 'val="60000"' in dml
    assert 'val="FEF3C7"' not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_gradient_href_inherits_stop_list_before_fallback_average() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="base">
          <stop offset="0%" stop-color="#ff0000"/>
          <stop offset="50%" stop-color="#00ff00"/>
        </linearGradient>
        <linearGradient id="derived" href="#base">
          <stop offset="100%" stop-color="#0000ff"/>
        </linearGradient>
      </defs>
      <rect width="10" height="8" fill="url(#derived)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)

    assert 'val="555555"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_xlink_gradient_href_inherits_stop_list_before_fallback_average() -> None:
    svg = """<svg xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs>
        <linearGradient id="base">
          <stop offset="0%" stop-color="#ff0000"/>
          <stop offset="50%" stop-color="#00ff00"/>
        </linearGradient>
        <linearGradient id="derived" xlink:href="#base">
          <stop offset="100%" stop-color="#0000ff"/>
        </linearGradient>
      </defs>
      <rect width="10" height="8" fill="url(#derived)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)

    assert 'val="555555"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_gradient_href_cycle_can_use_fallback_color() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="cycle" href="#cycle"/>
      </defs>
      <rect width="10" height="8" fill="url(#cycle) #123456"/>
    </svg>"""

    dml = svg_to_drawingml(svg)

    assert 'val="123456"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_missing_paint_server() -> None:
    report = analyze_svg('<svg><rect width="10" height="8" fill="url(#missing)"/></svg>')

    assert report.unsupported_attributes == {"fill:paint-server": 1}


def test_pattern_paint_server_falls_back_to_representative_color() -> None:
    svg = """<svg>
      <style>.dot { fill: #000000; }</style>
      <defs>
        <pattern id="dots" width="4" height="4">
          <rect width="4" height="4" fill="#ffffff"/>
          <circle class="dot" cx="2" cy="2" r="1"/>
        </pattern>
      </defs>
      <rect width="10" height="8" fill="url(#dots)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert 'val="808080"' in dml
    assert report.unsupported_attributes == {}


def test_analyze_svg_reports_pattern_without_paint_fallback() -> None:
    svg = """<svg>
      <defs><pattern id="empty" width="4" height="4"/></defs>
      <rect width="10" height="8" fill="url(#empty)" stroke="url(#empty)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"fill:pattern": 1, "stroke:pattern": 1}


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


def test_dash_offset_inside_dash_is_approximated_with_shifted_custom_dash() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" stroke-dashoffset="2"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="300000" sp="200000"/>' in dml
    assert '<a:ds d="100000" sp="0"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="6 4 2 0"' in svg


def test_dash_offset_inside_gap_is_reported_as_unsupported() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" stroke-dashoffset="10"/></svg>'

    assert analyze_svg(source).unsupported_attributes == {"stroke-dashoffset": 1}


def test_zero_dasharray_is_treated_as_no_dash() -> None:
    dml = svg_to_drawingml('<svg><line x1="0" y1="0" x2="10" y2="0" stroke="#111111" stroke-dasharray="0 0"/></svg>')

    assert "<a:custDash>" not in dml
    assert "<a:prstDash" not in dml

    svg = drawingml_to_svg(dml)
    assert "stroke-dasharray" not in svg
    assert analyze_svg('<svg><line x1="0" y1="0" x2="10" y2="0" stroke="#111111" stroke-dasharray="0 0"/></svg>').unsupported_attributes == {}


def test_negative_dasharray_is_treated_as_invalid_and_solid() -> None:
    dml = svg_to_drawingml('<svg><line x1="0" y1="0" x2="10" y2="0" stroke="#111111" stroke-dasharray="-1 2"/></svg>')

    assert "<a:custDash>" not in dml
    assert "<a:prstDash" not in dml

    svg = drawingml_to_svg(dml)
    assert "stroke-dasharray" not in svg
    assert analyze_svg('<svg><line x1="0" y1="0" x2="10" y2="0" stroke="#111111" stroke-dasharray="-1 2"/></svg>').unsupported_attributes == {}


def test_zero_stroke_width_is_converted_as_no_line() -> None:
    dml = svg_to_drawingml('<svg><rect width="10" height="8" fill="#ffffff" stroke="#111111" stroke-width="0"/></svg>')

    assert 'val="111111"' not in dml
    assert "<a:noFill/>" in dml

    svg = drawingml_to_svg(dml)
    assert 'stroke="none"' in svg
    assert 'stroke-width="0"' in svg


def test_invalid_miterlimit_falls_back_to_svg_default() -> None:
    dml = svg_to_drawingml(
        '<svg><polyline points="0,0 10,0 10,8" fill="none" stroke="#111111" stroke-linejoin="miter" stroke-miterlimit="0"/></svg>'
    )

    assert '<a:miter lim="400000"/>' in dml

    svg = drawingml_to_svg(dml)
    assert 'stroke-miterlimit="4"' in svg
    assert analyze_svg(
        '<svg><polyline points="0,0 10,0 10,8" fill="none" stroke="#111111" stroke-linejoin="miter" stroke-miterlimit="0"/></svg>'
    ).unsupported_attributes == {}


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


def test_data_uri_image_opacity_maps_to_picture_alpha_and_round_trips() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16" opacity="0.35"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    alpha = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}alphaModFix")
    assert alpha is not None
    assert alpha.attrib == {"amt": "35000"}
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'opacity="0.35"' in round_trip


def test_transformed_data_uri_image_preserves_rotation() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16" transform="rotate(90 20 20)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "5400000"
    off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    ext = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert off is not None
    assert ext is not None
    assert off.attrib == {"x": "95250", "y": "114300"}
    assert ext.attrib == {"cx": "190500", "cy": "152400"}
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'transform="rotate(90 20 20)"' in round_trip


def test_reflected_data_uri_image_preserves_flip() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16" transform="translate(0 40) scale(1 -1)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@flipV]")
    assert xfrm is not None
    assert xfrm.get("flipV") == "1"
    off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    ext = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert off is not None
    assert ext is not None
    assert off.attrib == {"x": "95250", "y": "114300"}
    assert ext.attrib == {"cx": "190500", "cy": "152400"}
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'transform="translate(20 20) scale(1 -1) translate(-20 -20)"' in round_trip


def test_drawingml_picture_rotation_and_flip_round_trip_to_svg_transform() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:pic>
        <p:nvPicPr><p:cNvPr id="2" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm rot="1800000" flipH="1"><a:off x="95250" y="114300"/><a:ext cx="190500" cy="152400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>"""
    svg = drawingml_to_svg(dml)

    assert "<image" in svg
    assert 'transform="rotate(30 20 20) translate(20 20) scale(-1 1) translate(-20 -20)"' in svg


def test_drawingml_line_rotation_round_trip_to_svg_transform() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="line"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm rot="2700000"><a:off x="95250" y="190500"/><a:ext cx="381000" cy="0"/></a:xfrm>
          <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
          <a:ln><a:solidFill><a:srgbClr val="111111"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""
    svg = drawingml_to_svg(dml)

    assert "<line" in svg
    assert 'stroke="#111111"' in svg
    assert 'x1="10"' in svg
    assert 'y1="20"' in svg
    assert 'x2="50"' in svg
    assert 'y2="20"' in svg
    assert 'fill="none"' in svg
    assert 'transform="rotate(45 30 20)"' in svg
    assert 'viewBox="0 0 44.1421 34.1421"' in svg


def test_drawingml_freeform_rotation_and_flip_round_trip_to_svg_transform() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm rot="1800000" flipH="1"><a:off x="95250" y="190500"/><a:ext cx="381000" cy="285750"/></a:xfrm>
          <a:custGeom>
            <a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>
            <a:pathLst>
              <a:path w="381000" h="285750">
                <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
                <a:lnTo><a:pt x="381000" y="0"/></a:lnTo>
                <a:lnTo><a:pt x="190500" y="285750"/></a:lnTo>
                <a:close/>
              </a:path>
            </a:pathLst>
          </a:custGeom>
          <a:solidFill><a:srgbClr val="FEE2E2"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""
    svg = drawingml_to_svg(dml)

    assert '<polygon fill="#fee2e2" points="10,20 50,20 30,50" transform="rotate(30 30 35) translate(30 35) scale(-1 1) translate(-30 -35)"/>' in svg


def test_xlink_data_uri_image_converts_to_picture_media() -> None:
    svg = f'<svg xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16"/></svg>'
    fragment = ET.fromstring(svg_to_drawingml(svg))
    pictures = [
        child
        for child in fragment
        if child.tag == "{http://schemas.openxmlformats.org/presentationml/2006/main}pic"
    ]
    prepared_slide, rels, media = prepare_slide_media(build_slide_xml(pictures))

    assert len(pictures) == 1
    assert len(media) == 1
    assert media[0][0] == "ppt/media/image1.png"
    assert b"data:image/png" not in prepared_slide
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"' in rels
    assert analyze_svg(svg).unsupported_attributes == {}


def test_unsupported_marker_usage_is_reported() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <polygon points="0,0 20,0 10,10" marker-end="url(#arrow)"/>
      <polyline points="30,0 40,10 50,0" marker-mid="url(#arrow)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"marker-end": 1, "marker-mid": 1}


def test_tspan_text_anchor_and_bold_convert() -> None:
    dml = svg_to_drawingml(
        '<svg><text x="100" y="40" text-anchor="middle" dominant-baseline="middle" font-size="20" font-weight="700" font-style="italic" font-variant="small-caps" font-family="\'Aptos Display\', Arial, sans-serif" text-decoration="underline line-through" fill="#111111"><tspan>Hello</tspan><tspan x="100" dy="22">World</tspan></text></svg>'
    )

    assert '<a:br/>' in dml
    assert 'anchor="ctr"' in dml
    assert '<a:pPr algn="ctr"/>' in dml
    assert 'b="1"' in dml
    assert 'i="1"' in dml
    assert 'cap="small"' in dml
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
    assert 'font-variant="small-caps"' in svg
    assert 'font-family="Aptos Display"' in svg
    assert 'text-decoration="underline line-through"' in svg
    assert 'text-anchor="middle"' in svg
    assert 'dominant-baseline="middle"' in svg
    assert 'x="100"' in svg
    assert 'y="40"' in svg


def test_drawingml_multiple_text_paragraphs_round_trip_to_svg_lines() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="95250" y="190500"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:r><a:rPr sz="1200"/><a:t>First</a:t></a:r>
            <a:br/>
            <a:r><a:rPr sz="1200"/><a:t>Break</a:t></a:r>
          </a:p>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Second</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)
    root = ET.fromstring(svg)
    text = root.find("{http://www.w3.org/2000/svg}text")
    assert text is not None
    tspans = text.findall("{http://www.w3.org/2000/svg}tspan")

    assert (text.text or "").strip() == "First"
    assert [tspan.text for tspan in tspans] == ["Break", "Second"]
