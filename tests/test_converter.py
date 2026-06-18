import base64
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


def _webp_data_uri(width: int, height: int) -> str:
    payload = b"\0\0\0\0" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    data = b"RIFF" + (len(payload) + 10).to_bytes(4, "little") + b"WEBPVP8X" + len(payload).to_bytes(4, "little") + payload
    return f"data:image/webp;base64,{base64.b64encode(data).decode('ascii')}"


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
    svg = drawingml_to_svg(svg_to_drawingml('<svg><rect x="5" y="6" width="7" height="8" fill="none" stroke="#112233"/></svg>'))

    assert '<rect fill="none" stroke="#112233" stroke-width="1" stroke-linecap="butt" stroke-linejoin="miter" stroke-miterlimit="4" x="5" y="6" width="7" height="8"/>' in svg
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
    assert dml.count("<p:sp>") == 1
    assert dml.count("<a:noFill/>") == 1

    svg = drawingml_to_svg(dml)
    assert '<rect fill="#000000" stroke="none" x="0" y="0" width="10" height="8"/>' in svg
    assert "<line" not in svg


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


def test_analyze_svg_ignores_invisible_paint_only_shapes() -> None:
    report = analyze_svg(
        f"""<svg>
          <rect width="10" height="8" fill="none" stroke="none" filter="url(#blur)"/>
          <line x1="0" y1="12" x2="10" y2="12" mix-blend-mode="multiply"/>
          <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="8" opacity="0" mask="url(#fade)"/>
        </svg>"""
    )

    assert report.convertible_elements == 1
    assert report.ignored_elements == 3
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


def test_invalid_polygon_and_polyline_points_are_reported_and_skipped() -> None:
    svg = """<svg>
      <polygon points="0,0 10,0 5" fill="#fee2e2"/>
      <polyline points="0,0 1e999,0" fill="none" stroke="#111111"/>
      <rect width="10" height="8" fill="#22c55e"/>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert dml.count("<p:sp>") == 1
    assert report.unsupported_elements == {"polygon:invalid-points": 1, "polyline:invalid-points": 1}


def test_non_finite_path_coordinates_are_reported_and_skipped() -> None:
    svg = '<svg><path d="M0 0 L1e999 0" fill="none" stroke="#111111"/><rect width="10" height="8"/></svg>'
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert dml.count("<p:sp>") == 1
    assert report.unsupported_elements == {"path:unsupported-command": 1}


def test_non_finite_svg_lengths_fall_back_to_defaults() -> None:
    svg = """<svg width="1e999" height="1e999">
      <rect x="1e999" y="2" width="1e999" height="8" fill="#ef4444"/>
      <rect x="4" y="6" width="10" height="8" stroke-width="1e999" fill="none" stroke="#111111"/>
      <text x="0" y="24" font-size="1e999" fill="#111111">Fallback</text>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert dml.count("<p:sp>") == 2
    assert 'x="0"' in dml
    assert 'w="9525"' in dml
    assert 'sz="1600"' in dml
    assert report.unsupported_elements == {}


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


def test_css_property_names_are_normalized_without_changing_custom_properties() -> None:
    svg = """<svg>
      <style>
        :root { --Brand: #dc2626; }
        rect { FILL: var(--Brand); STROKE: #111111; STROKE-WIDTH: 2; }
      </style>
      <rect width="10" height="8"/>
      <text x="0" y="20" style="FONT-SIZE: 10; TEXT-TRANSFORM: uppercase; FILL: #111111">mixed</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="111111"' in dml
    assert 'w="19050"' in dml
    assert 'sz="1000"' in dml
    assert "<a:t>MIXED</a:t>" in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_declarations_ignore_semicolons_inside_values() -> None:
    svg = """<svg>
      <style>
        rect { font-family: "A;B"; stroke: #0f766e; stroke-width: 2; }
      </style>
      <rect width="10" height="8" style="fill: url(data:image/svg+xml;utf8,&lt;svg/&gt;); fill: #dc2626"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="0F766E"' in dml
    assert 'w="19050"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_css_sibling_selectors_are_applied_in_converter_and_analyzer() -> None:
    svg = """<svg>
      <style>
        g > rect + rect { fill: #dc2626; }
        rect ~ circle { stroke: #2563eb; stroke-width: 2; }
        stop + stop { stop-color: #16a34a; }
      </style>
      <defs>
        <linearGradient id="grad">
          <stop offset="0%" stop-color="#16a34a"/>
          <stop offset="100%"/>
        </linearGradient>
      </defs>
      <g>
        <rect width="10" height="8" fill="#111111"/>
        <rect x="12" width="10" height="8"/>
        <circle cx="28" cy="4" r="4" fill="url(#grad)"/>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="111111"' in dml
    assert 'val="DC2626"' in dml
    assert 'val="2563EB"' in dml
    assert 'val="16A34A"' in dml
    assert 'w="19050"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_attribute_selectors_are_applied() -> None:
    svg = """<svg>
      <style>
        rect[data-tone] { fill: #fef3c7; }
        [data-state="active"] { stroke: #0f766e; stroke-width: 2; }
        *[data-wide] { stroke-width: 3; }
        rect[data-tags~="signal"][data-kind|="meter"] { stroke: #1d4ed8; }
        rect[data-icon^="coverage"][data-icon$="probe"][data-icon*="age-pr"] { fill: #dbeafe; }
        rect[data-mode="loud" i] { stroke: #be123c; }
        rect[data-mode="quiet" s] { fill: #bbf7d0; }
        rect[data-name="a,b"], circle[data-kind="pair"] { stroke: #7c2d12; }
      </style>
      <rect data-tone="warm" data-state="active" data-wide="1" x="1" y="2" width="3" height="4"/>
      <rect data-tags="warm signal" data-kind="meter-high" data-icon="coverage-probe" x="6" y="2" width="3" height="4"/>
      <rect data-mode="LOUD" x="11" y="2" width="3" height="4"/>
      <rect data-mode="QUIET" x="16" y="2" width="3" height="4"/>
      <rect data-name="a,b" x="21" y="2" width="3" height="4"/>
      <circle data-kind="pair" cx="28" cy="4" r="2"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="FEF3C7"' in dml
    assert 'val="0F766E"' in dml
    assert 'val="DBEAFE"' in dml
    assert 'val="1D4ED8"' in dml
    assert 'val="BE123C"' in dml
    assert 'val="BBF7D0"' not in dml
    assert dml.count('val="7C2D12"') == 2
    assert 'w="28575"' in dml
    assert analyze_svg(svg).estimated_element_coverage == 1.0


def test_css_not_pseudo_class_selectors_are_applied() -> None:
    svg = """<svg>
      <style>
        rect:not(.skip) { fill: #dc2626; stroke: #1d4ed8; stroke-width: 2; }
        rect:not([data-muted]) { opacity: 50%; }
        rect:not(#target) { stroke: #16a34a; }
        rect:not([data-name="a,b"]) { fill-opacity: 25%; }
      </style>
      <rect id="target" data-name="a,b" width="10" height="8"/>
      <rect class="skip" x="12" width="10" height="8"/>
      <rect data-muted="1" x="24" width="10" height="8"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="1D4ED8"' in dml
    assert 'val="16A34A"' in dml
    assert dml.count('val="50000"') == 3
    assert dml.count('val="25000"') == 1
    assert dml.count('val="12500"') == 1
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_is_and_where_pseudo_class_selectors_are_applied() -> None:
    svg = """<svg>
      <style>
        .accent { fill: #f97316; }
        :is(#target, circle[data-tone]) { fill: #dc2626; }
        rect { stroke: #2563eb; stroke-width: 2; }
        :where(.outlined) { stroke: #16a34a; stroke-width: 3; }
        g :is(text.label, tspan.emphasis) { text-transform: uppercase; fill: #111111; }
      </style>
      <g>
        <rect id="target" class="accent outlined" width="10" height="8"/>
        <circle data-tone="warm" cx="18" cy="4" r="4"/>
        <text class="label" x="0" y="24">mixed</text>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count('val="DC2626"') == 2
    assert 'val="F97316"' not in dml
    assert 'val="2563EB"' in dml
    assert 'val="16A34A"' not in dml
    assert 'w="19050"' in dml
    assert '<a:t>MIXED</a:t>' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_custom_properties_resolve_var_colors() -> None:
    svg = """<svg>
      <style>
        :root { --brand: #dc2626; --line: rgb(22, 163, 74); }
        g.theme { --accent: #2563eb; color: var(--brand); }
        rect { fill: var(--accent); stroke: var(--line); stroke-width: 2; }
        circle { fill: var(--missing, #f97316); stroke: var(--line-missing, hsl(0.5turn 100% 25%)); stroke-width: 2; }
      </style>
      <g class="theme">
        <rect width="10" height="8"/>
        <circle cx="18" cy="4" r="4"/>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="2563EB"' in dml
    assert 'val="16A34A"' in dml
    assert 'val="F97316"' in dml
    assert 'val="007F80"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_inline_css_custom_properties_resolve_current_color() -> None:
    svg = '<svg><rect width="10" height="8" style="--brand: #dc2626; color: var(--brand); fill: currentColor; stroke: var(--missing, #2563eb); stroke-width: 2"/></svg>'
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert 'val="2563EB"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_media_rules_apply_only_screen_compatible_queries() -> None:
    svg = """<svg>
      <style>
        @media print { rect { fill: #dc2626; stroke: #dc2626; } }
        @media not screen { rect { fill: #f97316; } }
        @media screen { rect { fill: #2563eb; } }
        @media all and (min-width: 1px) { rect { stroke: #16a34a; stroke-width: 2; } }
        @media only screen { rect { stroke-linejoin: bevel; } }
        @media not print { rect { stroke-linecap: round; } }
      </style>
      <rect width="10" height="8"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="2563EB"' in dml
    assert 'val="16A34A"' in dml
    assert '<a:bevel' in dml
    assert 'cap="rnd"' in dml
    assert 'val="DC2626"' not in dml
    assert 'val="F97316"' not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_ignores_non_style_at_rules_without_losing_later_rules() -> None:
    svg = """<svg>
      <style>
        @font-face { font-family: Demo; src: url(demo.woff2); }
        @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
        rect { fill: #dc2626; }
      </style>
      <rect width="10" height="8"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="DC2626"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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

    assert report.ignored_elements == 4
    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {}
    assert report.unsupported_path_commands == {}


def test_hidden_display_and_visibility_values_are_normalized() -> None:
    svg = """<svg>
      <path display=" NONE " d="M0 0 R10 20" filter="url(#blur)"/>
      <g visibility=" COLLAPSE ">
        <foreignObject width="10" height="10"/>
        <path d="M0 0 R10 20"/>
      </g>
      <rect x="20" width="10" height="8" fill="#222222"/>
    </svg>"""

    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert dml.count("<p:sp>") == 1
    assert report.ignored_elements == 4
    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {}
    assert report.unsupported_path_commands == {}


def test_visibility_visible_descendant_renders_inside_hidden_parent() -> None:
    svg = """<svg>
      <g visibility="hidden">
        <path d="M0 0 R10 20" filter="url(#blur)"/>
        <rect x="10" y="12" width="20" height="16" fill="#16a34a" visibility="visible"/>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    assert dml.count("<p:sp>") == 1
    assert 'val="16A34A"' in dml
    assert shape_off.attrib == {"x": "95250", "y": "114300"}
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


def test_text_rotate_angle_units_are_resolved() -> None:
    dml = svg_to_drawingml('<svg><text x="10" y="20" rotate=".25turn" font-size="10" fill="#111">Quarter</text></svg>')

    root = ET.fromstring(dml)
    shape_xfrm = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")[1]
    assert shape_xfrm.get("rot") == "5400000"
    assert analyze_svg('<svg><text x="10" y="20" rotate=".25turn">Quarter</text></svg>').unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'rotate="90"' in svg


def test_equal_multi_value_text_rotate_angle_units_are_supported() -> None:
    source = '<svg><text x="10" y="20" rotate="0.20943951023931953rad 0.20943951023931953rad" font-size="10" fill="#111">Tilt</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    shape_xfrm = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")[1]
    assert shape_xfrm.get("rot") == "720000"
    assert analyze_svg(source).unsupported_attributes == {}


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


def test_text_length_spacing_values_are_normalized() -> None:
    source = '<svg><text x="10" y="20" textLength="48" lengthAdjust=" SPACINGANDGLYPHS " letter-spacing=" NORMAL " font-size="10" fill="#111">Wide</text></svg>'
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


def test_text_transform_uppercase_maps_to_literal_text() -> None:
    source = '<svg><text x="10" y="20" text-transform="uppercase" font-size="10" fill="#111">Mixed case</text></svg>'
    dml = svg_to_drawingml(source)

    assert "<a:t>MIXED CASE</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_inherited_text_transform_lowercase_maps_to_literal_text() -> None:
    source = '<svg><g text-transform="lowercase"><text x="10" y="20" font-size="10" fill="#111">LOUD Label</text></g></svg>'
    dml = svg_to_drawingml(source)

    assert "<a:t>loud label</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_css_text_transform_capitalize_maps_to_literal_text() -> None:
    source = """<svg>
      <style>text.title { text-transform: capitalize; }</style>
      <text class="title" x="10" y="20" font-size="10" fill="#111">hello-world label</text>
    </svg>"""
    dml = svg_to_drawingml(source)

    assert "<a:t>Hello-World Label</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_tspan_text_transform_maps_to_literal_text() -> None:
    source = '<svg><text x="10" y="20" font-size="10" fill="#111">Keep <tspan text-transform="uppercase">small</tspan></text></svg>'
    dml = svg_to_drawingml(source)

    assert "<a:t>Keep</a:t>" in dml
    assert "<a:t>SMALL</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_css_tspan_text_transform_overrides_parent_transform() -> None:
    source = """<svg>
      <style>tspan.keep { text-transform: none; }</style>
      <text x="10" y="20" text-transform="uppercase" font-size="10" fill="#111">
        <tspan>loud</tspan>
        <tspan class="keep">MiXeD</tspan>
      </text>
    </svg>"""
    dml = svg_to_drawingml(source)

    assert "<a:t>LOUD</a:t>" in dml
    assert "<a:t>MiXeD</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_normal_text_transform_value_is_supported_as_noop() -> None:
    source = '<svg><text x="10" y="20" text-transform=" NORMAL " font-size="10" fill="#111">MiXeD</text></svg>'
    dml = svg_to_drawingml(source)

    assert "<a:t>MiXeD</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {}


def test_unsupported_text_transform_value_is_reported() -> None:
    source = '<svg><text x="10" y="20" font-size="10" fill="#111"><tspan text-transform="full-width">wide</tspan></text></svg>'
    dml = svg_to_drawingml(source)

    assert "<a:t>wide</a:t>" in dml
    assert analyze_svg(source).unsupported_attributes == {"text-transform": 1}


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


def test_word_spacing_accepts_normal_letter_spacing_values() -> None:
    source = '<svg><text x="10" y="20" word-spacing="6px" letter-spacing=" NORMAL " font-size="10" fill="#111">Hi all</text></svg>'
    dml = svg_to_drawingml(source)

    root = ET.fromstring(dml)
    run_pr = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert run_pr is not None
    assert run_pr.get("spc") == "90"
    assert shape_ext.get("cx") == "571500"
    assert analyze_svg(source).unsupported_attributes == {}


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


def test_text_decoration_line_maps_to_drawingml_decoration() -> None:
    svg = """<svg>
      <style>.decorated { text-decoration-line: underline line-through; }</style>
      <text class="decorated" x="0" y="20" font-size="10" fill="#111111">CSS</text>
      <text x="0" y="40" font-size="10" fill="#111111" text-decoration-line="underline">Attr</text>
      <text x="0" y="60" font-size="10" fill="#111111" style="text-decoration-line: line-through">Style</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    run_prs = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
    assert run_prs[0].get("u") == "sng"
    assert run_prs[0].get("strike") == "sngStrike"
    assert run_prs[1].get("u") == "sng"
    assert run_prs[2].get("strike") == "sngStrike"
    assert analyze_svg(svg).unsupported_attributes == {}


def test_text_decoration_color_and_non_solid_style_are_reported_when_visible() -> None:
    svg = """<svg>
      <text x="0" y="20" text-decoration-line="underline" text-decoration-color="#dc2626">Color</text>
      <text x="0" y="40" text-decoration="line-through" text-decoration-style="dashed">Style</text>
      <text x="0" y="60" text-decoration-style="dotted">No decoration</text>
      <text x="0" y="80" text-decoration-line="underline" text-decoration-style="solid">Solid</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "text-decoration-color": 1,
        "text-decoration-style": 1,
    }


def test_unsupported_text_decoration_tokens_are_reported() -> None:
    svg = """<svg>
      <text x="0" y="20" text-decoration="overline">Over</text>
      <text x="0" y="40" text-decoration="underline overline">Mixed</text>
      <text x="0" y="60" text-decoration-line="blink">Blink</text>
      <text x="0" y="80" text-decoration-line="underline line-through">Supported</text>
      <text x="0" y="100" text-decoration="none">None</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "text-decoration": 2,
        "text-decoration-line": 1,
    }


def test_unconverted_text_layout_attributes_are_reported() -> None:
    svg = """<svg>
      <style>
        .stretch { font-stretch: condensed; }
        .orient { text-orientation: upright; }
      </style>
      <text class="stretch" x="0" y="20">Stretch</text>
      <text x="0" y="40" font-size-adjust=".5">Adjust</text>
      <text class="orient" x="0" y="60">Orient</text>
      <text x="0" y="80" style="baseline-shift: super">Shift</text>
      <text x="0" y="100" font-stretch="normal" font-size-adjust="none" text-orientation="mixed" baseline-shift="0">Noop</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "baseline-shift": 1,
        "font-size-adjust": 1,
        "font-stretch": 1,
        "text-orientation": 1,
    }


def test_unconverted_text_direction_and_typography_attributes_are_reported() -> None:
    svg = """<svg>
      <style>
        .vertical { writing-mode: vertical-rl; }
        .features { font-feature-settings: &quot;liga&quot; 0; font-variation-settings: &quot;wght&quot; 650; }
      </style>
      <text class="vertical" x="0" y="20">Vertical</text>
      <text x="0" y="40" direction="rtl" unicode-bidi="bidi-override">Bidi</text>
      <text x="0" y="60" alignment-baseline="mathematical" dominant-baseline="mathematical">Baseline</text>
      <text x="0" y="80" glyph-orientation-vertical="90deg" glyph-orientation-horizontal="90deg">Glyphs</text>
      <text class="features" x="0" y="100" kerning="4" font-kerning="none">Features</text>
      <text x="0" y="120" writing-mode="horizontal-tb" direction="ltr" unicode-bidi="normal"
        alignment-baseline="hanging" dominant-baseline="middle" glyph-orientation-vertical="0deg"
        glyph-orientation-horizontal="0" kerning="auto" font-kerning="normal"
        font-feature-settings="normal" font-variation-settings="normal">Noop</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "alignment-baseline": 1,
        "direction": 1,
        "dominant-baseline": 1,
        "font-feature-settings": 1,
        "font-kerning": 1,
        "font-variation-settings": 1,
        "glyph-orientation-horizontal": 1,
        "glyph-orientation-vertical": 1,
        "kerning": 1,
        "unicode-bidi": 1,
        "writing-mode": 1,
    }


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


def test_clip_path_units_values_are_normalized() -> None:
    svg = """<svg>
      <defs><clipPath id="crop" clipPathUnits=" OBJECTBOUNDINGBOX "><rect x=".25" y=".2" width=".5" height=".4"/></clipPath></defs>
      <rect x="10" y="20" width="80" height="50" fill="#f97316" clip-path="url(#crop)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "285750", "y": "285750"}
    assert shape_ext.attrib == {"cx": "381000", "cy": "190500"}
    assert analyze_svg(svg).unsupported_attributes == {}


def test_clip_path_url_allows_whitespace_around_reference() -> None:
    svg = """<svg>
      <defs><clipPath id="crop"><rect x="2" y="1" width="5" height="4"/></clipPath></defs>
      <rect width="10" height="8" fill="#f97316" clip-path="url( #crop )"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert shape_off.attrib == {"x": "19050", "y": "9525"}
    assert shape_ext.attrib == {"cx": "47625", "cy": "38100"}
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


def test_preserve_aspect_ratio_values_are_normalized() -> None:
    none_dml = svg_to_drawingml(
        '<svg viewBox="0 0 100 50" width="200" height="200" preserveAspectRatio=" NONE "><rect x="0" y="0" width="100" height="50"/></svg>'
    )
    slice_dml = svg_to_drawingml(
        '<svg viewBox="0 0 100 50" width="200" height="200" preserveAspectRatio=" XMAXYMAX SLICE "><rect x="0" y="0" width="100" height="50"/></svg>'
    )

    none_root = ET.fromstring(none_dml)
    none_shape_off = none_root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    none_shape_ext = none_root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert none_shape_off.attrib == {"x": "0", "y": "0"}
    assert none_shape_ext.attrib == {"cx": "1905000", "cy": "1905000"}

    slice_root = ET.fromstring(slice_dml)
    slice_shape_off = slice_root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    slice_shape_ext = slice_root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    assert slice_shape_off.attrib == {"x": "-1905000", "y": "0"}
    assert slice_shape_ext.attrib == {"cx": "3810000", "cy": "1905000"}


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


def test_transform_angle_and_length_units_are_resolved() -> None:
    svg = """<svg>
      <rect x="10" y="12" width="20" height="16" fill="#f97316" transform="rotate(.25turn 20px 20px)"/>
      <rect x="0" y="0" width="1" height="1" fill="#22c55e" transform="translate(1in 2.54cm)"/>
      <rect x="0" y="0" width="10" height="10" fill="#2563eb" transform="skewX(50grad)"/>
      <rect x="0" y="0" width="10" height="10" fill="#9333ea" transform="rotate(1e999turn)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    assert xfrm is not None
    assert xfrm.get("rot") == "5400000"
    assert {"x": "914400", "y": "914400"} in [offset.attrib for offset in offsets]
    assert dml.count("<a:custGeom>") == 1
    assert 'val="9333EA"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_transform_function_names_are_normalized() -> None:
    svg = """<svg>
      <rect x="0" y="0" width="10" height="8" fill="#111111" transform="TRANSLATE(10 20)"/>
      <rect x="20" y="0" width="10" height="8" fill="#222222" transform="Scale(2)"/>
      <rect x="0" y="20" width="10" height="8" fill="#333333" transform="SKEWX(45)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    assert {"x": "95250", "y": "190500"} in [offset.attrib for offset in offsets]
    assert {"x": "381000", "y": "0"} in [offset.attrib for offset in offsets]
    assert dml.count("<a:custGeom>") == 1
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_transform_property_is_applied_without_inheritance() -> None:
    svg = """<svg>
      <style>
        .rule-move { transform: translate(30px, 40px); }
      </style>
      <rect width="10" height="8" fill="#111111" style="transform: translate(10px, 20px)"/>
      <rect class="rule-move" width="10" height="8" fill="#222222"/>
      <g style="transform: translate(50px, 60px)">
        <rect width="10" height="8" fill="#333333"/>
      </g>
      <g style="transform: translate(70px, 80px)">
        <rect width="10" height="8" fill="#444444" style="transform: translate(5px, 6px)"/>
      </g>
      <g style="transform: translate(90px, 100px)">
        <g><rect width="10" height="8" fill="#555555"/></g>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    offsets = [off.attrib for off in root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")]
    assert {"x": "95250", "y": "190500"} in offsets
    assert {"x": "285750", "y": "381000"} in offsets
    assert {"x": "476250", "y": "571500"} in offsets
    assert {"x": "714375", "y": "819150"} in offsets
    assert {"x": "857250", "y": "952500"} in offsets
    assert analyze_svg(svg).unsupported_attributes == {}


def test_absolute_transform_origin_is_applied_to_css_transform() -> None:
    svg = '<svg><rect x="10" y="12" width="20" height="16" fill="#111111" style="transform-origin: 20px 20px 0; transform: rotate(90deg)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    shape_off = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")[1]
    shape_ext = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")[1]
    xfrm = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm[@rot]")
    assert xfrm is not None
    assert xfrm.get("rot") == "5400000"
    assert shape_off.attrib == {"x": "95250", "y": "114300"}
    assert shape_ext.attrib == {"cx": "190500", "cy": "152400"}
    assert analyze_svg(svg).unsupported_attributes == {}


def test_unsupported_transform_origin_values_are_reported() -> None:
    svg = """<svg>
      <rect width="10" height="8" style="transform-origin: left top; transform: rotate(90deg)"/>
      <rect x="12" width="10" height="8" style="transform-origin: 50% 50%; transform: rotate(90deg)"/>
      <rect x="24" width="10" height="8" style="transform-origin: 5px 4px 1px; transform: rotate(90deg)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"transform-origin": 3}


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


def test_non_finite_svg_transform_values_do_not_crash() -> None:
    svg = """<svg>
      <rect width="10" height="8" fill="#111111" transform="scale(1e999)"/>
      <rect x="12" width="10" height="8" fill="#222222" transform="rotate(1e999)"/>
      <rect x="24" width="10" height="8" fill="#333333" transform="matrix(1 0 0 1 1e999 0) translate(4 0)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)
    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")

    assert dml.count("<p:sp>") == 3
    assert 'val="111111"' in dml
    assert 'val="222222"' in dml
    assert 'val="333333"' in dml
    assert offsets[1].attrib == {"x": "0", "y": "0"}
    assert offsets[2].attrib == {"x": "114300", "y": "0"}
    assert offsets[3].attrib == {"x": "266700", "y": "0"}
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
      <path d="M0 0 H10 V10 Z" fill-rule="evenodd" stroke="#111111" stroke-width="2"/>
      <rect width="10" height="8" filter="url(#blur)" mask="url(#fade)"/>
      <text x="0" y="20" isolation="isolate">Hint</text>
      <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="8" image-rendering="pixelated" color-rendering="optimizeQuality"/>
      <defs><linearGradient id="spread" spreadMethod="reflect" gradientUnits="userSpaceOnUse" gradientTransform="rotate(15)"><stop stop-color="#fff"/></linearGradient></defs>
    </svg>"""

    report = analyze_svg(svg)

    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {
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
        marker="none"
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


def test_analyze_svg_ignores_clip_rule_outside_clip_path() -> None:
    svg = '<svg><path d="M0 0 H10 V10 Z" clip-rule="evenodd" fill="#111111"/></svg>'

    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_clip_rule_inside_inline_clip_path() -> None:
    svg = """<svg>
      <clipPath id="crop"><path d="M0 0 H10 V10 Z" clip-rule="evenodd"/></clipPath>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"clip-rule": 1}


def test_analyze_svg_ignores_paint_order_when_only_one_paint_channel_is_visible() -> None:
    svg = """<svg>
      <path d="M0 0 H10 V10 Z" fill="#111111" stroke="none" paint-order="stroke fill"/>
      <path d="M20 0 H30 V10 Z" fill="none" stroke="#111111" stroke-width="2" paint-order="fill stroke"/>
      <path d="M40 0 H50 V10 Z" fill="#111111" fill-opacity="0" stroke="#111111" stroke-width="2" paint-order="fill stroke"/>
      <path d="M60 0 H70 V10 Z" fill="#111111" stroke="#111111" stroke-opacity="0" stroke-width="2" paint-order="stroke fill"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_paint_order_when_fill_and_stroke_are_visible() -> None:
    svg = '<svg><path d="M0 0 H10 V10 Z" fill="#ffffff" stroke="#111111" stroke-width="2" paint-order="stroke fill"/></svg>'

    assert analyze_svg(svg).unsupported_attributes == {"paint-order": 1}


def test_analyze_svg_ignores_fill_rule_without_visible_fill() -> None:
    svg = """<svg>
      <path d="M0 0 H10 V10 Z" fill="none" stroke="#111111" fill-rule="evenodd"/>
      <path d="M20 0 H30 V10 Z" fill="#111111" fill-opacity="0" stroke="#111111" fill-rule="evenodd"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {}


def test_analyze_svg_reports_fill_rule_when_fill_is_visible() -> None:
    svg = '<svg><path d="M0 0 H10 V10 Z" fill="#111111" fill-rule="evenodd"/></svg>'

    assert analyze_svg(svg).unsupported_attributes == {"fill-rule": 1}


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
      <rect width="10" height="8" fill="none" stroke="none" mix-blend-mode="multiply"/>
      <rect width="10" height="8" fill="#111111" opacity="0" mix-blend-mode="multiply"/>
      <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="8" opacity="0" mix-blend-mode="multiply"/>
      <path d="M0 0 L10 0" stroke="#111111" stroke-dasharray="4 2" stroke-dashoffset="0"/>
      <path d="M0 4 L10 4" stroke="#111111" stroke-dasharray="4 2" stroke-dashoffset="12"/>
      <path d="M0 8 L10 8" stroke="#111111" stroke-dasharray="2 1 3" stroke-dashoffset="-12"/>
      <path d="M0 12 L10 12" stroke="#111111" stroke-dashoffset="2"/>
      <path d="M0 16 L10 16" stroke="none" stroke-dasharray="4 2" stroke-dashoffset="2"/>
      <path d="M0 20 L10 20" stroke="#111111" stroke-opacity="0" stroke-dasharray="4 2" stroke-dashoffset="2"/>
    </svg>""".format(PNG_DATA_URI=PNG_DATA_URI)

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


def test_analyze_svg_accepts_data_image_preserve_aspect_ratio_when_dimensions_are_known() -> None:
    svg = f"""<svg viewBox="0 0 100 50" width="200" height="200" preserveAspectRatio="xMaxYMax slice">
      <svg x="0" y="0" width="20" height="20" viewBox="0 0 10 5" preserveAspectRatio="none">
        <rect width="10" height="5"/>
      </svg>
      <image href="{PNG_DATA_URI}" x="0" y="0" width="10" height="8" preserveAspectRatio="none"/>
      <image href="{PNG_DATA_URI}" x="12" y="0" width="10" height="8" preserveAspectRatio="xMidYMid meet"/>
      <image href="{PNG_DATA_URI}" x="24" y="0" width="10" height="8" preserveAspectRatio="xMaxYMax slice"/>
    </svg>"""

    report = analyze_svg(svg)

    assert report.unsupported_elements == {}
    assert report.unsupported_attributes == {}


def test_analyze_svg_reports_image_preserve_aspect_ratio_when_dimensions_are_unknown() -> None:
    svg = '<svg><image href="data:image/webp;base64,AAAA" x="0" y="0" width="10" height="8" preserveAspectRatio="xMidYMid meet"/></svg>'

    assert analyze_svg(svg).unsupported_attributes == {"preserveAspectRatio": 1}


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


def test_drawingml_text_outline_style_round_trips_to_svg() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:r>
              <a:rPr sz="1200">
                <a:solidFill><a:srgbClr val="111111"/></a:solidFill>
                <a:ln w="19050" cap="sq">
                  <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
                  <a:custDash><a:ds d="200000" sp="100000"/></a:custDash>
                  <a:miter lim="600000"/>
                </a:ln>
              </a:rPr>
              <a:t>Outlined</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'stroke="#ffffff"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-linecap="square"' in svg
    assert 'stroke-linejoin="miter"' in svg
    assert 'stroke-dasharray="4 2"' in svg
    assert 'stroke-miterlimit="6"' in svg


def test_drawingml_text_run_no_fill_overrides_shape_fill() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DC2626"/></a:solidFill>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"><a:noFill/></a:rPr><a:t>Hidden fill</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<text" in svg
    assert 'fill="none"' in svg
    assert 'fill="#dc2626"' not in svg


def test_drawingml_default_run_properties_fall_back_to_svg_text_style() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr>
              <a:defRPr sz="1800" b="1" i="1" cap="small" spc="150" u="sng" strike="sngStrike">
                <a:solidFill><a:srgbClr val="334455"/></a:solidFill>
                <a:latin typeface="Aptos Display"/>
              </a:defRPr>
            </a:pPr>
            <a:r><a:t>Default</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'font-size="18"' in svg
    assert 'font-weight="bold"' in svg
    assert 'font-style="italic"' in svg
    assert 'font-family="Aptos Display"' in svg
    assert 'font-variant="small-caps"' in svg
    assert 'letter-spacing="2"' in svg
    assert 'text-decoration="underline line-through"' in svg
    assert 'fill="#334455"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_run_properties_override_default_run_properties() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr>
              <a:defRPr sz="1800" b="1">
                <a:solidFill><a:srgbClr val="334455"/></a:solidFill>
                <a:latin typeface="Aptos Display"/>
              </a:defRPr>
            </a:pPr>
            <a:r><a:rPr sz="1200"><a:solidFill><a:srgbClr val="AA5500"/></a:solidFill></a:rPr><a:t>Override</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'font-size="12"' in svg
    assert 'font-weight="bold"' in svg
    assert 'font-family="Aptos Display"' in svg
    assert 'fill="#aa5500"' in svg
    assert 'fill="#334455"' not in svg


def test_drawingml_end_paragraph_run_properties_fall_back_to_svg_text_style() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:r><a:t>End defaults</a:t></a:r>
            <a:endParaRPr sz="1600" b="1" i="1" spc="120" u="sng">
              <a:solidFill><a:srgbClr val="224466"/></a:solidFill>
              <a:ln w="19050"><a:solidFill><a:srgbClr val="CC5500"/></a:solidFill></a:ln>
              <a:latin typeface="Aptos"/>
            </a:endParaRPr>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'font-size="16"' in svg
    assert 'font-weight="bold"' in svg
    assert 'font-style="italic"' in svg
    assert 'font-family="Aptos"' in svg
    assert 'letter-spacing="1.6"' in svg
    assert 'text-decoration="underline"' in svg
    assert 'fill="#224466"' in svg
    assert 'stroke="#cc5500"' in svg
    assert 'stroke-width="2"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_run_properties_override_end_paragraph_run_properties() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:r><a:rPr sz="1200"><a:solidFill><a:srgbClr val="AA5500"/></a:solidFill></a:rPr><a:t>Run wins</a:t></a:r>
            <a:endParaRPr sz="1800" b="1"><a:solidFill><a:srgbClr val="334455"/></a:solidFill></a:endParaRPr>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'font-size="12"' in svg
    assert 'font-weight="bold"' in svg
    assert 'fill="#aa5500"' in svg
    assert 'fill="#334455"' not in svg


def test_drawingml_non_latin_typefaces_fall_back_to_svg_font_family() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr><a:defRPr sz="1200"><a:ea typeface="Yu Gothic"/></a:defRPr></a:pPr>
            <a:r><a:t>East Asian</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="666750"/><a:ext cx="762000" cy="571500"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr><a:defRPr sz="1200"><a:cs typeface="Arial Unicode MS"/></a:defRPr></a:pPr>
            <a:r><a:rPr><a:sym typeface="Wingdings"/></a:rPr><a:t>Symbol</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'font-family="Yu Gothic"' in svg
    assert 'font-family="Wingdings"' in svg
    assert 'font-family="Arial Unicode MS"' not in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_default_run_outline_falls_back_to_svg_text_stroke() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr>
              <a:defRPr sz="1200">
                <a:ln w="19050" cap="rnd">
                  <a:solidFill><a:srgbClr val="224466"><a:alpha val="50000"/></a:srgbClr></a:solidFill>
                  <a:prstDash val="dash"/>
                  <a:round/>
                </a:ln>
              </a:defRPr>
            </a:pPr>
            <a:r><a:t>Outlined</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'stroke="#224466"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-opacity="0.5"' in svg
    assert 'stroke-linecap="round"' in svg
    assert 'stroke-linejoin="round"' in svg
    assert 'stroke-dasharray="4 3"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_run_outline_overrides_default_run_outline() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:pPr><a:defRPr sz="1200"><a:ln w="19050"><a:solidFill><a:srgbClr val="224466"/></a:solidFill></a:ln></a:defRPr></a:pPr>
            <a:r>
              <a:rPr><a:ln w="9525"><a:solidFill><a:srgbClr val="AA5500"/></a:solidFill></a:ln></a:rPr>
              <a:t>Override</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'stroke="#aa5500"' in svg
    assert 'stroke-width="1"' in svg
    assert 'stroke="#224466"' not in svg


def test_drawingml_scheme_colors_round_trip_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:schemeClr val="accent1"/></a:solidFill>
          <a:ln><a:solidFill><a:schemeClr val="tx2"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="190500"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:rPr><a:t>Theme</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#4472c4"' in svg
    assert 'stroke="#44546a"' in svg
    assert 'fill="#ed7d31"' in svg


def test_drawingml_shape_style_refs_fall_back_to_svg_paint() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="style refs"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:ln w="19050"/>
        </p:spPr>
        <p:style>
          <a:lnRef idx="1"><a:schemeClr val="accent2"><a:alpha val="50000"/></a:schemeClr></a:lnRef>
          <a:fillRef idx="1"><a:schemeClr val="accent1"><a:lumMod val="50000"/></a:schemeClr></a:fillRef>
        </p:style>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#223962"' in svg
    assert 'stroke="#ed7d31"' in svg
    assert 'stroke-opacity="0.5"' in svg
    assert 'stroke-width="2"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_explicit_shape_paint_overrides_style_refs() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="explicit paint"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="AA5500"/></a:solidFill>
          <a:ln><a:solidFill><a:srgbClr val="224466"/></a:solidFill></a:ln>
        </p:spPr>
        <p:style>
          <a:lnRef idx="1"><a:schemeClr val="accent2"/></a:lnRef>
          <a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef>
        </p:style>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#aa5500"' in svg
    assert 'stroke="#224466"' in svg
    assert 'fill="#4472c4"' not in svg
    assert 'stroke="#ed7d31"' not in svg


def test_drawingml_font_ref_falls_back_to_svg_text_fill() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="font ref"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:schemeClr val="accent1"/></a:solidFill>
        </p:spPr>
        <p:style>
          <a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef>
          <a:fontRef idx="minor"><a:schemeClr val="accent2"><a:alpha val="50000"/></a:schemeClr></a:fontRef>
        </p:style>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Styled text</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#ed7d31"' in svg
    assert 'fill-opacity="0.5"' in svg
    assert 'fill="#4472c4"' not in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_text_run_fill_overrides_font_ref() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="font ref override"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:style><a:fontRef idx="minor"><a:schemeClr val="accent2"/></a:fontRef></p:style>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"><a:solidFill><a:srgbClr val="224466"/></a:solidFill></a:rPr><a:t>Explicit</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#224466"' in svg
    assert 'fill="#ed7d31"' not in svg


def test_drawingml_scheme_color_luminance_modifiers_round_trip_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:schemeClr val="accent1"><a:lumMod val="50000"/></a:schemeClr></a:solidFill>
          <a:ln><a:solidFill><a:schemeClr val="tx1"><a:lumOff val="40000"/></a:schemeClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#223962"' in svg
    assert 'stroke="#666666"' in svg


def test_drawingml_srgb_color_luminance_modifiers_round_trip_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="336699"><a:lumMod val="50000"/></a:srgbClr></a:solidFill>
          <a:ln><a:solidFill><a:srgbClr val="000000"><a:lumOff val="40000"/></a:srgbClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#1a334c"' in svg
    assert 'stroke="#666666"' in svg


def test_drawingml_gradient_fill_falls_back_to_average_svg_color() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:gradFill>
            <a:gsLst>
              <a:gs pos="0"><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:gs>
              <a:gs pos="100000"><a:srgbClr val="0000FF"/></a:gs>
            </a:gsLst>
          </a:gradFill>
          <a:ln>
            <a:gradFill>
              <a:gsLst>
                <a:gs pos="0"><a:srgbClr val="008000"><a:alpha val="50000"/></a:srgbClr></a:gs>
                <a:gs pos="100000"><a:srgbClr val="000000"/></a:gs>
              </a:gsLst>
            </a:gradFill>
          </a:ln>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="190500"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/>
          <a:ln><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"><a:gradFill><a:gsLst>
            <a:gs pos="0"><a:srgbClr val="FFFF00"/></a:gs>
            <a:gs pos="100000"><a:srgbClr val="00FFFF"/></a:gs>
          </a:gsLst></a:gradFill></a:rPr><a:t>Gradient</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#800080"' in svg
    assert 'fill-opacity="0.75"' in svg
    assert 'stroke="#004000"' in svg
    assert 'stroke-opacity="0.75"' in svg
    assert 'fill="#80ff80"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_pattern_fill_falls_back_to_average_svg_color() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:pattFill prst="pct50">
            <a:fgClr><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:fgClr>
            <a:bgClr><a:srgbClr val="0000FF"/></a:bgClr>
          </a:pattFill>
          <a:ln>
            <a:pattFill prst="ltHorz">
              <a:fgClr><a:srgbClr val="008000"><a:alpha val="50000"/></a:srgbClr></a:fgClr>
              <a:bgClr><a:srgbClr val="000000"/></a:bgClr>
            </a:pattFill>
          </a:ln>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="190500"/><a:ext cx="762000" cy="285750"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/>
          <a:ln><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"><a:pattFill prst="pct25">
            <a:fgClr><a:srgbClr val="FFFF00"/></a:fgClr>
            <a:bgClr><a:srgbClr val="00FFFF"/></a:bgClr>
          </a:pattFill></a:rPr><a:t>Pattern</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#800080"' in svg
    assert 'fill-opacity="0.75"' in svg
    assert 'stroke="#004000"' in svg
    assert 'stroke-opacity="0.75"' in svg
    assert 'fill="#80ff80"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_tint_and_shade_modifiers_round_trip_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="336699"><a:tint val="50000"/></a:srgbClr></a:solidFill>
          <a:ln><a:solidFill><a:schemeClr val="accent1"><a:shade val="50000"/></a:schemeClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#99b2cc"' in svg
    assert 'stroke="#223962"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_scrgb_color_round_trips_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:scrgbClr r="20000" g="40000" b="60000"/></a:solidFill>
          <a:ln><a:solidFill><a:scrgbClr r="100000" g="0" b="0"><a:shade val="50000"/></a:scrgbClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#336699"' in svg
    assert 'stroke="#800000"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_hsl_color_round_trips_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:hslClr hue="10800000" sat="50000" lum="40000"/></a:solidFill>
          <a:ln><a:solidFill><a:hslClr hue="0" sat="100000" lum="50000"><a:shade val="50000"/></a:hslClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#339999"' in svg
    assert 'stroke="#800000"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_system_color_last_color_round_trips_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:sysClr val="windowText" lastClr="112233"/></a:solidFill>
          <a:ln><a:solidFill><a:sysClr val="highlight" lastClr="AABBCC"><a:shade val="50000"/></a:sysClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#112233"' in svg
    assert 'stroke="#555e66"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_preset_color_round_trips_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:prstClr val="dkBlue"/></a:solidFill>
          <a:ln><a:solidFill><a:prstClr val="red"><a:shade val="50000"/></a:prstClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#00008b"' in svg
    assert 'stroke="#800000"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_extended_preset_colors_round_trip_to_svg_hex_colors() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:prstClr val="medSeaGreen"/></a:solidFill>
          <a:ln><a:solidFill><a:prstClr val="dkOrange"><a:shade val="50000"/></a:prstClr></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:prstClr val="whiteSmoke"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill="#3cb371"' in svg
    assert 'stroke="#804600"' in svg
    assert 'fill="#f5f5f5"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_alpha_mod_round_trips_to_svg_opacity() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="76200"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="336699"><a:alpha val="80000"/><a:alphaMod amt="50000"/></a:srgbClr></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'fill-opacity="0.4"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_invalid_numeric_paint_and_transform_values_do_not_crash() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="line"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm rot="inf"><a:off x="bad" y="95250"/><a:ext cx="bad" cy="0"/></a:xfrm>
          <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
          <a:ln w="bad">
            <a:solidFill><a:srgbClr val="111111"><a:alpha val="nan"/><a:lumMod val="inf"/></a:srgbClr></a:solidFill>
            <a:custDash><a:ds d="bad" sp="100000"/></a:custDash>
            <a:miter lim="bad"/>
          </a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<line" in svg
    assert 'stroke="#111111"' in svg
    assert "stroke-opacity" not in svg
    assert "stroke-width" not in svg
    assert "stroke-dasharray" not in svg
    assert "stroke-miterlimit" not in svg
    assert "transform=" not in svg


def test_drawingml_oval_preset_round_trips_to_svg_ellipse() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="oval"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="oval"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill>
          <a:ln w="19050"><a:solidFill><a:srgbClr val="2563EB"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<ellipse" in svg
    assert 'cx="30"' in svg
    assert 'cy="30"' in svg
    assert 'rx="20"' in svg
    assert 'ry="10"' in svg
    assert 'fill="#dbeafe"' in svg
    assert 'stroke="#2563eb"' in svg
    assert 'stroke-width="2"' in svg


def test_drawingml_straight_connector_preset_round_trips_to_svg_line() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="straight connector"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="190500"/><a:ext cx="381000" cy="95250"/></a:xfrm>
          <a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>
          <a:ln w="9525"><a:solidFill><a:srgbClr val="111827"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<line" in svg
    assert 'x1="10"' in svg
    assert 'y1="20"' in svg
    assert 'x2="50"' in svg
    assert 'y2="30"' in svg
    assert 'stroke="#111827"' in svg
    assert 'stroke-width="1"' in svg
    assert 'fill="none"' in svg


def test_drawingml_common_polygon_presets_round_trip_to_svg_polygons() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="triangle"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="triangle"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEE2E2"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="diamond"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="571500" y="190500"/><a:ext cx="190500" cy="190500"/></a:xfrm>
          <a:prstGeom prst="diamond"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="4" name="pentagon"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="857250" y="190500"/><a:ext cx="190500" cy="190500"/></a:xfrm>
          <a:prstGeom prst="pentagon"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DCFCE7"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="5" name="hexagon"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="1143000" y="190500"/><a:ext cx="190500" cy="190500"/></a:xfrm>
          <a:prstGeom prst="hexagon"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEF3C7"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<polygon fill="#fee2e2" points="30,20 50,40 10,40"/>' in svg
    assert '<polygon fill="#dbeafe" points="70,20 80,30 70,40 60,30"/>' in svg
    assert '<polygon fill="#dcfce7" points="100,20 110,27.6 106.2,40 93.8,40 90,27.6"/>' in svg
    assert '<polygon fill="#fef3c7" points="125,20 135,20 140,30 135,40 125,40 120,30"/>' in svg


def test_drawingml_polygon_presets_preserve_rotation_and_flip() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="rotated diamond"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm rot="1800000" flipH="1"><a:off x="95250" y="190500"/><a:ext cx="381000" cy="381000"/></a:xfrm>
          <a:prstGeom prst="diamond"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="EDE9FE"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<polygon fill="#ede9fe" points="30,20 50,40 30,60 10,40" transform="rotate(30 30 40) translate(30 40) scale(-1 1) translate(-30 -40)"/>' in svg


def test_drawingml_arrow_presets_round_trip_to_svg_polygons() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="right arrow"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="rightArrow"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="left arrow"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="571500" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="leftArrow"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEE2E2"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="4" name="up arrow"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="1047750" y="190500"/><a:ext cx="190500" cy="381000"/></a:xfrm>
          <a:prstGeom prst="upArrow"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DCFCE7"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="5" name="down arrow"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="1333500" y="190500"/><a:ext cx="190500" cy="381000"/></a:xfrm>
          <a:prstGeom prst="downArrow"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEF3C7"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<polygon fill="#dbeafe" points="10,25 36,25 36,20 50,30 36,40 36,35 10,35"/>' in svg
    assert '<polygon fill="#fee2e2" points="100,25 74,25 74,20 60,30 74,40 74,35 100,35"/>' in svg
    assert '<polygon fill="#dcfce7" points="115,60 115,34 110,34 120,20 130,34 125,34 125,60"/>' in svg
    assert '<polygon fill="#fef3c7" points="145,20 145,46 140,46 150,60 160,46 155,46 155,20"/>' in svg


def test_drawingml_flowchart_presets_round_trip_to_svg_shapes() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="process"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="95250" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="flowChartProcess"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="decision"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="571500" y="190500"/><a:ext cx="190500" cy="190500"/></a:xfrm>
          <a:prstGeom prst="flowChartDecision"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEE2E2"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="4" name="data"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="857250" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="flowChartData"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="DCFCE7"/></a:solidFill>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="5" name="terminator"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="1333500" y="190500"/><a:ext cx="381000" cy="190500"/></a:xfrm>
          <a:prstGeom prst="flowChartTerminator"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FEF3C7"/></a:solidFill>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<rect fill="#dbeafe" x="10" y="20" width="40" height="20"/>' in svg
    assert '<polygon fill="#fee2e2" points="70,20 80,30 70,40 60,30"/>' in svg
    assert '<polygon fill="#dcfce7" points="100,20 130,20 120,40 90,40"/>' in svg
    assert '<rect fill="#fef3c7" x="140" y="20" width="40" height="20" rx="3.3333" ry="3.3333"/>' in svg


def test_drawingml_group_transform_scales_child_shapes_to_svg() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="2" name="group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr>
          <a:xfrm>
            <a:off x="95250" y="190500"/><a:ext cx="190500" cy="190500"/>
            <a:chOff x="0" y="0"/><a:chExt cx="95250" cy="95250"/>
          </a:xfrm>
        </p:grpSpPr>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="3" name="rect"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr>
            <a:xfrm><a:off x="95250" y="95250"/><a:ext cx="95250" cy="95250"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
            <a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill>
            <a:ln w="9525"><a:solidFill><a:srgbClr val="2563EB"/></a:solidFill></a:ln>
          </p:spPr>
        </p:sp>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="4" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
          <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="1000"><a:solidFill><a:srgbClr val="111111"/></a:solidFill></a:rPr><a:t>Group</a:t></a:r></a:p></p:txBody>
        </p:sp>
      </p:grpSp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<rect fill="#dbeafe" stroke="#2563eb" stroke-width="2" x="30" y="40" width="20" height="20"/>' in svg
    assert '<text fill="#111111" x="10" y="40" font-size="20">Group</text>' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_group_transform_scales_child_lines_and_pictures_to_svg() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="2" name="group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr>
          <a:xfrm>
            <a:off x="95250" y="190500"/><a:ext cx="190500" cy="190500"/>
            <a:chOff x="0" y="0"/><a:chExt cx="95250" cy="95250"/>
          </a:xfrm>
        </p:grpSpPr>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="3" name="line"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr>
            <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="47625"/></a:xfrm>
            <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
            <a:ln w="9525"><a:solidFill><a:srgbClr val="111827"/></a:solidFill></a:ln>
          </p:spPr>
        </p:sp>
        <p:pic>
          <p:nvPicPr><p:cNvPr id="4" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
          <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
          <p:spPr><a:xfrm><a:off x="47625" y="47625"/><a:ext cx="47625" cy="47625"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        </p:pic>
      </p:grpSp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert '<line stroke="#111827" stroke-width="2" x1="10" y1="20" x2="30" y2="30" fill="none"/>' in svg
    assert f'<image href="{PNG_DATA_URI}" x="20" y="30" width="10" height="10"/>' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_group_flip_preserves_child_image_and_text_reflection() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="2" name="flipped group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr>
          <a:xfrm flipV="1">
            <a:off x="95250" y="190500"/><a:ext cx="190500" cy="190500"/>
            <a:chOff x="0" y="0"/><a:chExt cx="190500" cy="190500"/>
          </a:xfrm>
        </p:grpSpPr>
        <p:pic>
          <p:nvPicPr><p:cNvPr id="3" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
          <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
          <p:spPr><a:xfrm><a:off x="47625" y="47625"/><a:ext cx="47625" cy="47625"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        </p:pic>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="4" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
          <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="1000"><a:solidFill><a:srgbClr val="111111"/></a:solidFill></a:rPr><a:t>Flip</a:t></a:r></a:p></p:txBody>
        </p:sp>
      </p:grpSp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert f'<image href="{PNG_DATA_URI}" x="15" y="30" width="5" height="5" transform="translate(17.5 32.5) scale(1 -1) translate(-17.5 -32.5)"/>' in svg
    assert '<text fill="#111111" x="10" y="40" font-size="10" transform="translate(15 35) scale(1 -1) translate(-15 -35)">Flip</text>' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_invalid_srgb_colors_do_not_crash() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="76200"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="not-a-color"><a:lumMod val="50000"/></a:srgbClr></a:solidFill>
          <a:ln><a:solidFill><a:srgbClr val="bad"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<rect" in svg
    assert "not-a-color" not in svg
    assert "bad" not in svg
    assert "fill=" not in svg
    assert "stroke=" not in svg


def test_drawingml_invalid_custom_geometry_points_do_not_crash() -> None:
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
                <a:lnTo><a:pt x="bad" y="95250"/></a:lnTo>
                <a:lnTo><a:pt x="381000" y="190500"/></a:lnTo>
                <a:quadBezTo>
                  <a:pt x="bad" y="0"/>
                  <a:pt x="762000" y="0"/>
                </a:quadBezTo>
              </a:path>
            </a:pathLst>
          </a:custGeom>
          <a:ln><a:solidFill><a:srgbClr val="111111"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "<polyline" in svg
    assert "bad" not in svg
    assert "0,0" in svg
    assert "40,20" in svg
    assert "80,0" not in svg


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


def test_link_wrapper_converts_child_shapes_without_reporting_hyperlink_href() -> None:
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
    assert report["unsupported_attributes"] == {}


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


def test_percentage_opacity_values_are_written_as_drawingml_alpha() -> None:
    svg = '<svg><rect x="0" y="0" width="10" height="8" fill="#ff0000" fill-opacity="50%" stroke="#0000ff" stroke-opacity="25%" stroke-width="2"/></svg>'
    dml = svg_to_drawingml(svg)

    assert 'val="FF0000"' in dml
    assert 'val="0000FF"' in dml
    assert 'val="50000"' in dml
    assert 'val="25000"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'fill-opacity="0.5"' in round_trip
    assert 'stroke-opacity="0.25"' in round_trip


def test_opacity_css_math_functions_are_written_as_drawingml_alpha() -> None:
    svg = """<svg>
      <rect x="0" y="0" width="10" height="8" fill="#ff0000" fill-opacity="clamp(0%, 25%, 100%)" stroke="#0000ff" stroke-opacity="calc(50% - 10%)" stroke-width="2"/>
      <rect x="12" y="0" width="10" height="8" fill="#16a34a" opacity="min(80%, 0.5)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="FF0000"' in dml
    assert 'val="0000FF"' in dml
    assert 'val="25000"' in dml
    assert 'val="40000"' in dml
    assert 'val="50000"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_zero_alpha_paint_is_skipped_as_invisible() -> None:
    dml = svg_to_drawingml(
        '<svg><rect width="10" height="8" fill="#111111" fill-opacity="0" stroke="#222222" stroke-opacity="0" stroke-width="2"/></svg>'
    )

    assert 'val="111111"' not in dml
    assert 'val="222222"' not in dml
    assert "<p:sp>" not in dml

    svg = drawingml_to_svg(dml)
    assert 'viewBox="0 0 0 0"' in svg


def test_percentage_opacity_can_make_paint_invisible() -> None:
    svg = '<svg><rect width="10" height="8" fill="#111111" fill-opacity="0%" stroke="#222222" stroke-opacity="0%" stroke-width="2"/></svg>'

    assert "<p:sp>" not in svg_to_drawingml(svg)
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_math_opacity_can_make_paint_invisible() -> None:
    svg = '<svg><rect width="10" height="8" fill="#111111" opacity="calc(10% - 10%)"/><image href="photo.png" width="10" height="8" opacity="max(0%, 0%)"/></svg>'

    assert "<p:sp>" not in svg_to_drawingml(svg)
    report = analyze_svg(svg)
    assert report.ignored_elements == 2
    assert report.unsupported_attributes == {}


def test_css_color_functions_named_colors_and_gradient_fallback() -> None:
    svg = """<svg>
      <style>
        stop.start { stop-color: currentcolor; stop-opacity: 0.5; }
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


def test_gradient_percentage_stop_opacity_contributes_to_average_alpha() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="grad">
          <stop stop-color="#000000" stop-opacity="50%"/>
          <stop stop-color="#ffffff"/>
        </linearGradient>
      </defs>
      <rect width="10" height="8" fill="url(#grad)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="808080"' in dml
    assert 'val="75000"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_invalid_css_color_functions_do_not_crash() -> None:
    svg = """<svg>
      <rect width="10" height="8" fill="rgb(1e999 0 0)" stroke="hsl(1e999turn 100% 50%)"/>
      <rect x="12" width="10" height="8" fill="rgb(255 0 0 / 1e999)"/>
      <rect x="24" width="10" height="8" fill="#22c55e"/>
    </svg>"""
    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert dml.count("<p:sp>") == 3
    assert dml.count('val="000000"') == 2
    assert 'val="22C55E"' in dml
    assert report.unsupported_attributes == {}


def test_inherit_paint_values_use_parent_computed_style() -> None:
    svg = """<svg>
      <style>
        g.theme { fill: #123456; stroke: #abcdef; color: #f97316; }
        rect.accent { fill: inherit; stroke: currentColor; }
      </style>
      <g class="theme">
        <rect class="accent" x="0" y="0" width="10" height="8" style="stroke-width: 2"/>
        <circle cx="20" cy="4" r="4" fill="inherit" stroke="inherit"/>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="123456"' in dml
    assert 'val="F97316"' in dml
    assert 'val="ABCDEF"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_context_paint_values_use_parent_computed_fill_and_stroke() -> None:
    svg = """<svg>
      <defs>
        <symbol id="badge" viewBox="0 0 20 10">
          <rect width="20" height="10" fill="context-stroke" stroke="context-fill" stroke-width="2"/>
        </symbol>
      </defs>
      <use href="#badge" x="0" y="0" width="20" height="10" fill="#123456" stroke="#abcdef"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="ABCDEF"' in dml
    assert 'val="123456"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_initial_style_values_reset_inherited_presentation_attributes() -> None:
    svg = """<svg>
      <g fill="#123456" stroke="#abcdef" stroke-width="3" color="#f97316" font-size="24" text-anchor="middle">
        <rect x="0" y="0" width="10" height="8" fill="initial" stroke="initial" stroke-width="initial"/>
        <text x="0" y="20" font-size="initial" text-anchor="initial" fill="currentColor" stroke="initial">Reset</text>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="123456"' not in dml
    assert 'val="ABCDEF"' not in dml
    assert 'val="F97316"' in dml
    assert '<a:rPr sz="1600">' in dml
    assert 'algn="ctr"' not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_unset_style_values_follow_available_inherited_values_or_defaults() -> None:
    svg = """<svg>
      <style>
        g.theme { fill: #123456; stroke: #abcdef; color: #f97316; text-anchor: middle; }
        .reset { fill: unset; stroke: unset; text-anchor: unset; }
      </style>
      <g class="theme">
        <rect class="reset" x="0" y="0" width="10" height="8" stroke-width="2"/>
        <text class="reset" x="20" y="20" fill="currentColor">Unset</text>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="123456"' in dml
    assert 'val="ABCDEF"' in dml
    assert 'val="F97316"' not in dml
    assert 'algn="ctr"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_gradient_stop_color_inherit_uses_gradient_style() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="grad" stop-color="#ff0000" stop-opacity=".5">
          <stop offset="0%" stop-color="inherit"/>
          <stop offset="100%" stop-color="#0000ff"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="10" height="8" fill="url(#grad)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="800080"' in dml
    assert 'val="50000"' in dml
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


def test_paint_server_url_allows_whitespace_around_reference() -> None:
    svg = """<svg>
      <defs>
        <linearGradient id="grad">
          <stop stop-color="#000000"/>
          <stop stop-color="#ffffff"/>
        </linearGradient>
      </defs>
      <rect width="10" height="8" fill='url( "#grad" )' stroke="url( #grad )"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count('val="808080"') == 2
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
    report = analyze_svg(
        """<svg>
          <rect width="10" height="8" fill="url(#missing)"/>
          <line x1="0" y1="0" x2="10" y2="0" stroke="url(#missing-stroke)"/>
          <line x1="0" y1="2" x2="10" y2="2" stroke="url(#fallback) #111111"/>
          <line x1="0" y1="4" x2="10" y2="4" stroke="none"/>
        </svg>"""
    )

    assert report.unsupported_attributes == {"fill:paint-server": 1, "stroke:paint-server": 1}


def test_pattern_paint_server_falls_back_to_representative_color() -> None:
    svg = """<svg>
      <style>.dot { fill: currentcolor; }</style>
      <defs>
        <pattern id="dots" width="4" height="4">
          <rect width="4" height="4" fill="#ffffff"/>
          <circle class="dot" cx="2" cy="2" r="1"/>
        </pattern>
      </defs>
      <rect width="10" height="8" color="#000000" fill="url(#dots)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)
    report = analyze_svg(svg)

    assert 'val="808080"' in dml
    assert report.unsupported_attributes == {}


def test_pattern_representative_color_ignores_hidden_content() -> None:
    svg = """<svg>
      <defs>
        <pattern id="dots" width="4" height="4">
          <rect width="4" height="4" fill="#ff0000" display="none"/>
          <g visibility="hidden"><rect width="4" height="4" fill="#00ff00"/></g>
          <rect width="4" height="4" fill="#0000ff"/>
        </pattern>
      </defs>
      <rect width="10" height="8" fill="url(#dots)"/>
    </svg>"""

    dml = svg_to_drawingml(svg)

    assert 'val="0000FF"' in dml
    assert 'val="800080"' not in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_invalid_negative_rect_radius_is_ignored() -> None:
    negative_rx = svg_to_drawingml('<svg><rect width="20" height="10" rx="-3" fill="#111111"/></svg>')
    negative_ry = svg_to_drawingml('<svg><rect width="20" height="10" ry="-3" fill="#111111"/></svg>')
    fallback_from_ry = svg_to_drawingml('<svg><rect width="20" height="10" rx="-3" ry="4" fill="#111111"/></svg>')
    fallback_from_rx = svg_to_drawingml('<svg><rect width="20" height="10" rx="4" ry="-3" fill="#111111"/></svg>')
    bad_rx = svg_to_drawingml('<svg><rect width="20" height="10" rx="bad" ry="4" fill="#111111"/></svg>')

    assert 'prst="roundRect"' not in negative_rx
    assert 'prst="roundRect"' not in negative_ry
    assert 'prst="roundRect"' in fallback_from_ry
    assert 'prst="roundRect"' in fallback_from_rx
    assert 'prst="roundRect"' in bad_rx
    assert analyze_svg('<svg><rect width="20" height="10" rx="-3" fill="#111111"/></svg>').unsupported_attributes == {}


def test_stroke_linecap_and_linejoin_values_are_normalized() -> None:
    source = '<svg><polyline points="0,0 20,0 20,12" fill="none" stroke="#111111" stroke-width="2" stroke-linecap=" ROUND " stroke-linejoin=" BEVEL "/></svg>'
    dml = svg_to_drawingml(source)

    assert 'cap="rnd"' in dml
    assert "<a:bevel/>" in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-linecap="round"' in svg
    assert 'stroke-linejoin="bevel"' in svg


def test_analyze_svg_reports_unconverted_stroke_line_enums_when_visible() -> None:
    svg = """<svg>
      <style>
        .bad-cap { stroke-linecap: triangle; }
        .svg2-join { stroke-linejoin: arcs; }
      </style>
      <line class="bad-cap" x1="0" y1="0" x2="10" y2="0" stroke="#111111"/>
      <path class="svg2-join" d="M0 0 L10 0 L10 10" fill="none" stroke="#111111"/>
      <path d="M0 12 L10 12 L10 22" fill="none" stroke="#111111" stroke-linejoin="miter-clip"/>
      <line x1="0" y1="24" x2="10" y2="24" stroke="#111111" stroke-linecap="round"/>
      <path d="M0 26 L10 26 L10 36" fill="none" stroke="#111111" stroke-linejoin="bevel"/>
      <line x1="0" y1="38" x2="10" y2="38" stroke="none" stroke-linecap="triangle" stroke-linejoin="arcs"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "stroke-linecap": 1,
        "stroke-linejoin": 2,
    }


def test_dash_offset_inside_dash_is_approximated_with_shifted_custom_dash() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" stroke-dashoffset="2"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="300000" sp="200000"/>' in dml
    assert '<a:ds d="100000" sp="0"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="6 4 2 0"' in svg


def test_css_math_dasharray_and_dashoffset_are_resolved() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="calc(4px + 4px), max(3px, 4px)" stroke-dashoffset="calc(1px + 1px)"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="300000" sp="200000"/>' in dml
    assert '<a:ds d="100000" sp="0"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="6 4 2 0"' in svg


def test_percentage_dasharray_and_dashoffset_resolve_against_viewport_diagonal() -> None:
    source = '<svg width="100" height="100"><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8% 4%" stroke-dashoffset="2%"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="300000" sp="200000"/>' in dml
    assert '<a:ds d="100000" sp="0"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="6 4 2 0"' in svg


def test_dash_offset_inside_gap_is_approximated_with_leading_gap_dash() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" stroke-dashoffset="10"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="0" sp="100000"/>' in dml
    assert '<a:ds d="400000" sp="100000"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="0 2 8 2"' in svg


def test_dash_offset_at_segment_boundary_is_approximated_with_next_segment() -> None:
    source = '<svg><line x1="0" y1="0" x2="40" y2="0" stroke="#111111" stroke-width="2" stroke-dasharray="8 4" stroke-dashoffset="8"/></svg>'
    dml = svg_to_drawingml(source)

    assert '<a:custDash>' in dml
    assert '<a:ds d="0" sp="200000"/>' in dml
    assert '<a:ds d="400000" sp="0"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'stroke-dasharray="0 4 8 0"' in svg


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


def test_drawingml_preset_dash_patterns_round_trip_to_svg_dasharray() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="dashDot"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="0"/></a:xfrm>
          <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
          <a:ln><a:solidFill><a:srgbClr val="111111"/></a:solidFill><a:prstDash val="dashDot"/></a:ln>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="lgDashDotDot"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="95250"/><a:ext cx="95250" cy="0"/></a:xfrm>
          <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
          <a:ln><a:solidFill><a:srgbClr val="222222"/></a:solidFill><a:prstDash val="lgDashDotDot"/></a:ln>
        </p:spPr>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'stroke-dasharray="4 3 1 3"' in svg
    assert 'stroke-dasharray="8 3 1 3 1 3"' in svg


def test_zero_stroke_width_is_converted_as_no_line() -> None:
    dml = svg_to_drawingml('<svg><rect width="10" height="8" fill="#ffffff" stroke="#111111" stroke-width="0"/></svg>')

    assert 'val="111111"' not in dml
    assert "<a:noFill/>" in dml

    svg = drawingml_to_svg(dml)
    assert 'stroke="none"' in svg
    assert 'stroke-width="0"' in svg


def test_negative_stroke_width_falls_back_to_svg_default() -> None:
    svg = """<svg>
      <line x1="0" y1="0" x2="10" y2="0" stroke="#111111" stroke-width="-2"/>
      <text x="0" y="20" fill="#111111" stroke="#222222" stroke-width="-3">Outlined</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'val="111111"' in dml
    assert dml.count('w="9525"') >= 2
    assert 'val="222222"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'stroke-width="1"' in round_trip


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


def test_percentage_stroke_width_resolves_against_viewport_diagonal() -> None:
    svg = """<svg width="100" height="100">
      <line x1="0" y1="10" x2="40" y2="10" stroke="#111111" stroke-width="5%"/>
      <text x="0" y="30" fill="#111111" stroke="#ffffff" stroke-width="5%">Wide</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count('<a:ln w="47625"') == 2
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert round_trip.count('stroke-width="5"') == 2


def test_calc_lengths_are_resolved_for_geometry_strokes_and_text() -> None:
    svg = """<svg width="100" height="50">
      <rect x="calc(10px + 5px)" y="calc(2px + 3px)" width="calc(50% - 10px)" height="calc(100% - 20px)" fill="#dc2626"/>
      <line x1="0" y1="40" x2="40" y2="40" stroke="#111111" stroke-width="calc(1px + 1px)"/>
      <text x="0" y="20" font-size="calc(8px + 4px)" fill="#111111">Hi</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    extents = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert offsets[1].attrib == {"x": "142875", "y": "47625"}
    assert extents[1].attrib == {"cx": "381000", "cy": "285750"}
    assert '<a:ln w="19050" cap="flat">' in dml
    assert 'sz="1200"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_complex_calc_lengths_are_resolved_for_geometry_strokes_and_text() -> None:
    svg = """<svg width="120" height="60">
      <rect x="calc((10px + 5px) * 2)" y="calc(max(4px, 2px) + 1px)" width="calc((100% - 20px) / 2)" height="calc(clamp(10px, 50%, 24px) - 4px)" fill="#dc2626"/>
      <line x1="0" y1="40" x2="40" y2="40" stroke="#111111" stroke-width="calc(6px / 3)"/>
      <text x="0" y="20" font-size="calc(min(16px, 12px) * 1.5)" fill="#111111">Hi</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    extents = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert offsets[1].attrib == {"x": "285750", "y": "47625"}
    assert extents[1].attrib == {"cx": "476250", "cy": "190500"}
    assert '<a:ln w="19050" cap="flat">' in dml
    assert 'sz="1800"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_css_length_functions_are_resolved_for_geometry_strokes_and_text() -> None:
    svg = """<svg width="100" height="50">
      <rect x="min(20px, 12px)" y="max(2px, 5px)" width="min(50%, 30px)" height="clamp(10px, 100%, 25px)" fill="#dc2626"/>
      <line x1="0" y1="40" x2="40" y2="40" stroke="#111111" stroke-width="max(1px, 2px)"/>
      <text x="0" y="20" font-size="clamp(8px, 12px, 16px)" fill="#111111">Hi</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    offsets = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    extents = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert offsets[1].attrib == {"x": "114300", "y": "47625"}
    assert extents[1].attrib == {"cx": "285750", "cy": "238125"}
    assert '<a:ln w="19050" cap="flat">' in dml
    assert 'sz="1200"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_marker_url_allows_whitespace_around_reference() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <line x1="0" y1="0" x2="40" y2="10" stroke="#111111" stroke-width="2" marker-start='url( "#arrow" )' marker-end="url( #arrow )"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert '<a:tailEnd type="triangle"/>' in dml
    assert '<a:headEnd type="triangle"/>' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_marker_shorthand_converts_to_drawingml_arrows_when_no_mid_marker_is_needed() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <line x1="0" y1="0" x2="40" y2="10" stroke="#111111" stroke-width="2" marker="url(#arrow)"/>
      <polyline points="0,20 40,30" fill="none" stroke="#222222" stroke-width="2" marker="url(#arrow)"/>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count('<a:tailEnd type="triangle"/>') == 2
    assert dml.count('<a:headEnd type="triangle"/>') == 2
    assert analyze_svg(svg).unsupported_attributes == {}


def test_marker_shorthand_with_midpoints_is_reported_as_unsupported() -> None:
    svg = """<svg>
      <defs><marker id="arrow" viewBox="0 0 10 10"><path d="M0 0 L10 5 L0 10 Z"/></marker></defs>
      <polyline points="0,0 20,0 20,20" fill="none" stroke="#111111" marker="url(#arrow)"/>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {"marker": 1}


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


def test_data_uri_image_preserve_aspect_ratio_meet_fits_visible_picture_bounds() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="20" width="20" height="10" preserveAspectRatio="xMidYMid meet"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic/{http://schemas.openxmlformats.org/presentationml/2006/main}spPr/{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")
    assert xfrm is not None
    off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    ext = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    src_rect = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}srcRect")
    assert off is not None
    assert ext is not None
    assert off.attrib == {"x": "142875", "y": "190500"}
    assert ext.attrib == {"cx": "95250", "cy": "95250"}
    assert src_rect is None
    assert analyze_svg(svg).unsupported_attributes == {}


def test_data_uri_image_preserve_aspect_ratio_slice_crops_picture_source() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="20" width="20" height="10" preserveAspectRatio="xMidYMid slice"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic/{http://schemas.openxmlformats.org/presentationml/2006/main}spPr/{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")
    assert xfrm is not None
    off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    ext = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    src_rect = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}srcRect")
    assert off is not None
    assert ext is not None
    assert src_rect is not None
    assert off.attrib == {"x": "95250", "y": "190500"}
    assert ext.attrib == {"cx": "190500", "cy": "95250"}
    assert src_rect.attrib == {"t": "25000", "b": "25000"}
    assert analyze_svg(svg).unsupported_attributes == {}

    round_trip = drawingml_to_svg(dml)
    assert 'preserveAspectRatio="xMidYMid slice"' in round_trip


def test_drawingml_picture_source_crop_round_trips_to_svg_preserve_aspect_ratio() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:pic>
        <p:nvPicPr><p:cNvPr id="2" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"/><a:srcRect t="25000" b="25000"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="95250" y="190500"/><a:ext cx="190500" cy="95250"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'preserveAspectRatio="xMidYMid slice"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_webp_data_uri_dimensions_support_preserve_aspect_ratio() -> None:
    webp = _webp_data_uri(32, 16)
    svg = f'<svg><image href="{webp}" x="10" y="20" width="10" height="20" preserveAspectRatio="xMaxYMax meet"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    xfrm = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic/{http://schemas.openxmlformats.org/presentationml/2006/main}spPr/{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")
    assert xfrm is not None
    off = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}off")
    ext = xfrm.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ext")
    assert off is not None
    assert ext is not None
    assert off.attrib == {"x": "95250", "y": "333375"}
    assert ext.attrib == {"cx": "95250", "cy": "47625"}
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_drawingml_picture_alpha_round_trips_to_svg_opacity() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:pic>
        <p:nvPicPr><p:cNvPr id="2" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"><a:alpha val="40000"/></a:blip><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'opacity="0.4"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_picture_alpha_mod_round_trips_to_svg_opacity() -> None:
    dml = f"""<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:pic>
        <p:nvPicPr><p:cNvPr id="2" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="{PNG_DATA_URI}"><a:alpha val="80000"/><a:alphaMod amt="50000"/></a:blip><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="95250" cy="95250"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'opacity="0.4"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_data_uri_image_percentage_opacity_maps_to_picture_alpha() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16" opacity="35%"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    alpha = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}alphaModFix")
    assert alpha is not None
    assert alpha.attrib == {"amt": "35000"}
    assert analyze_svg(svg).unsupported_attributes == {}


def test_data_uri_image_css_math_opacity_maps_to_picture_alpha() -> None:
    svg = f'<svg><image href="{PNG_DATA_URI}" x="10" y="12" width="20" height="16" opacity="calc(25% + 10%)"/></svg>'
    dml = svg_to_drawingml(svg)

    root = ET.fromstring(dml)
    alpha = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}alphaModFix")
    assert alpha is not None
    assert alpha.attrib == {"amt": "35000"}
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_quoted_font_family_with_comma_is_preserved() -> None:
    source = '<svg><text x="0" y="20" font-family="\'A,B Display\', Arial, sans-serif" font-size="10" fill="#111111">Name</text></svg>'
    dml = svg_to_drawingml(source)

    assert 'typeface="A,B Display"' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'font-family="A,B Display"' in svg


def test_text_anchor_and_baseline_values_are_normalized() -> None:
    source = '<svg><text x="100" y="40" text-anchor=" MIDDLE " dominant-baseline=" CENTRAL " font-size="20" fill="#111111">Center</text></svg>'
    dml = svg_to_drawingml(source)

    assert 'anchor="ctr"' in dml
    assert '<a:pPr algn="ctr"/>' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'text-anchor="middle"' in svg
    assert 'dominant-baseline="middle"' in svg


def test_drawingml_list_style_paragraph_alignment_falls_back_to_svg_text_anchor() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle><a:lvl1pPr algn="ctr"/></a:lstStyle>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Centered</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'text-anchor="middle"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_list_style_paragraph_alignment_uses_paragraph_level() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle><a:lvl1pPr algn="ctr"/><a:lvl2pPr algn="r"/></a:lstStyle>
          <a:p><a:pPr lvl="1"/><a:r><a:rPr sz="1200"/><a:t>Indented</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'text-anchor="end"' in svg
    assert 'text-anchor="middle"' not in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_paragraph_alignment_overrides_list_style_alignment() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle><a:lvl1pPr algn="ctr"/></a:lstStyle>
          <a:p><a:pPr algn="r"/><a:r><a:rPr sz="1200"/><a:t>Right</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'text-anchor="end"' in svg
    assert 'text-anchor="middle"' not in svg


def test_drawingml_paragraph_bullet_character_round_trips_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:pPr><a:buChar char="*"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Item</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert ">* Item</text>" in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_list_style_bullet_character_falls_back_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle><a:lvl1pPr><a:buChar char="-"/></a:lvl1pPr></a:lstStyle>
          <a:p><a:r><a:rPr sz="1200"/><a:t>First</a:t></a:r></a:p>
          <a:p><a:pPr><a:buNone/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Plain</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "- First" in svg
    assert "<a:t>Plain</a:t>" not in svg
    assert "Plain</tspan>" in svg
    assert "- Plain</tspan>" not in svg


def test_drawingml_list_style_bullet_character_uses_paragraph_level() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle><a:lvl1pPr><a:buChar char="-"/></a:lvl1pPr><a:lvl2pPr><a:buChar char="+"/></a:lvl2pPr></a:lstStyle>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Top</a:t></a:r></a:p>
          <a:p><a:pPr lvl="1"/><a:r><a:rPr sz="1200"/><a:t>Nested</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "- Top" in svg
    assert "+ Nested" in svg
    assert "- Nested" not in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_auto_number_bullet_round_trips_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:pPr><a:buAutoNum type="arabicPeriod" startAt="3"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>First</a:t></a:r></a:p>
          <a:p><a:pPr><a:buAutoNum type="arabicParenR" startAt="3"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Second</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "3. First" in svg
    assert "4) Second" in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_list_style_auto_number_falls_back_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle><a:lvl1pPr><a:buAutoNum type="arabicParenBoth" startAt="2"/></a:lvl1pPr></a:lstStyle>
          <a:p><a:r><a:rPr sz="1200"/><a:t>First</a:t></a:r></a:p>
          <a:p><a:pPr><a:buNone/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Plain</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "(2) First" in svg
    assert "Plain</tspan>" in svg
    assert "(3) Plain" not in svg


def test_drawingml_list_style_auto_number_uses_paragraph_level() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="571500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle><a:lvl1pPr><a:buAutoNum type="arabicPeriod" startAt="1"/></a:lvl1pPr><a:lvl2pPr><a:buAutoNum type="alphaLcParenR" startAt="2"/></a:lvl2pPr></a:lstStyle>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Top</a:t></a:r></a:p>
          <a:p><a:pPr lvl="1"/><a:r><a:rPr sz="1200"/><a:t>Nested</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "1. Top" in svg
    assert "c) Nested" in svg
    assert "2. Nested" not in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_alpha_and_roman_auto_number_bullets_round_trip_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="762000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p><a:pPr><a:buAutoNum type="alphaLcPeriod" startAt="26"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Lower</a:t></a:r></a:p>
          <a:p><a:pPr><a:buAutoNum type="alphaUcParenR" startAt="26"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Upper</a:t></a:r></a:p>
          <a:p><a:pPr><a:buAutoNum type="romanLcParenBoth" startAt="4"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Roman lower</a:t></a:r></a:p>
          <a:p><a:pPr><a:buAutoNum type="romanUcPeriod" startAt="4"/></a:pPr><a:r><a:rPr sz="1200"/><a:t>Roman upper</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "z. Lower" in svg
    assert "AA) Upper" in svg
    assert "(vi) Roman lower" in svg
    assert "VII. Roman upper" in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_alignment_baseline_maps_to_text_anchor_when_dominant_baseline_is_absent() -> None:
    source = '<svg><text x="100" y="40" alignment-baseline=" hanging " font-size="20" fill="#111111">Top</text></svg>'
    dml = svg_to_drawingml(source)

    assert 'anchor="t"' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'dominant-baseline="text-before-edge"' in svg


def test_tspan_baseline_controls_are_reported_as_unconverted() -> None:
    svg = """<svg>
      <text x="0" y="20" font-size="10" fill="#111111">
        <tspan alignment-baseline="hanging">Top</tspan>
        <tspan dominant-baseline="middle">Mid</tspan>
        <tspan alignment-baseline="baseline" dominant-baseline="auto">Noop</tspan>
      </text>
      <text x="0" y="40" alignment-baseline="hanging" dominant-baseline="middle">Whole box</text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "alignment-baseline": 1,
        "dominant-baseline": 1,
    }


def test_tspan_run_level_styling_is_reported_as_unconverted() -> None:
    svg = """<svg>
      <text x="0" y="20" font-size="10" fill="#111111">
        <tspan fill="#ff0000" fill-opacity=".5" font-family="Arial" font-size="24"
          font-style="italic" font-weight="700" font-variant="small-caps"
          stroke="#0000ff" stroke-width="2" stroke-opacity=".5" stroke-dasharray="4 2"
          stroke-miterlimit="6" text-anchor="end" text-decoration-line="underline"
          letter-spacing="1px" word-spacing="2px">Wide gap</tspan>
        <tspan text-transform="uppercase">kept</tspan>
      </text>
      <text font-size="10" fill="#111111"><tspan x="20" y="40" dx="5" dy="7">Position</tspan></text>
    </svg>"""

    assert analyze_svg(svg).unsupported_attributes == {
        "fill": 1,
        "fill-opacity": 1,
        "font-family": 1,
        "font-size": 1,
        "font-style": 1,
        "font-variant": 1,
        "font-weight": 1,
        "letter-spacing": 1,
        "stroke": 1,
        "stroke-dasharray": 1,
        "stroke-miterlimit": 1,
        "stroke-opacity": 1,
        "stroke-width": 1,
        "text-anchor": 1,
        "text-decoration-line": 1,
        "word-spacing": 1,
    }


def test_font_weight_and_style_values_are_normalized() -> None:
    source = '<svg><text x="0" y="20" font-size="10" font-weight=" BOLD " font-style=" oblique 10deg " fill="#111111">Bold Italic</text></svg>'
    dml = svg_to_drawingml(source)

    assert 'b="1"' in dml
    assert 'i="1"' in dml
    assert analyze_svg(source).unsupported_attributes == {}

    svg = drawingml_to_svg(dml)
    assert 'font-weight="bold"' in svg
    assert 'font-style="italic"' in svg


def test_css_font_shorthand_expands_to_text_properties() -> None:
    svg = """<svg>
      <style>
        text.title { font: italic small-caps 700 18px/1.2 "Aptos Display", Arial, sans-serif; fill: #111111; }
        text.caption { font: oblique 10deg bold large "Aptos"; fill: #222222; }
        text.override { font: 10px Arial !important; font-size: 20px; fill: #333333; }
      </style>
      <text class="title" x="0" y="20">Title</text>
      <text class="caption" x="0" y="48">Caption</text>
      <text class="override" x="0" y="76">Override</text>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'sz="1800"' in dml
    assert 'sz="1000"' in dml
    assert 'b="1"' in dml
    assert 'i="1"' in dml
    assert 'cap="small"' in dml
    assert 'typeface="Aptos Display"' in dml
    assert 'typeface="Aptos"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_font_presentation_attribute_expands_and_inherits() -> None:
    svg = """<svg>
      <g font='italic small-caps 700 18px "Aptos Display", Arial, sans-serif' fill="#111111">
        <text x="0" y="20">Inherited</text>
        <text x="0" y="48" font='normal 10px "Aptos"'>Own</text>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert 'sz="1800"' in dml
    assert 'sz="1000"' in dml
    assert dml.count('b="1"') == 1
    assert dml.count('i="1"') == 1
    assert dml.count('cap="small"') == 1
    assert 'typeface="Aptos Display"' in dml
    assert 'typeface="Aptos"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


def test_relative_font_sizes_resolve_against_inherited_font_size() -> None:
    svg = """<svg>
      <style>
        :root { --caption-size: 75%; }
        g { font-size: 20px; fill: #111111; }
        text.em { font-size: 1.5em; }
        text.percent { font-size: 150%; }
        text.rem { font-size: 1.25rem; }
        text.var { font-size: var(--caption-size); }
      </style>
      <g>
        <text class="em" x="0" y="20">Em</text>
        <text class="percent" x="0" y="56">Percent</text>
        <text class="rem" x="0" y="92">Rem</text>
        <text class="var" x="0" y="128">Var</text>
      </g>
    </svg>"""
    dml = svg_to_drawingml(svg)

    assert dml.count('sz="3000"') == 2
    assert 'sz="2000"' in dml
    assert 'sz="1500"' in dml
    assert analyze_svg(svg).unsupported_attributes == {}


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


def test_drawingml_field_and_tab_text_round_trip_to_svg_text() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="285750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr/><a:lstStyle/>
          <a:p>
            <a:r><a:rPr sz="1200"/><a:t>Slide</a:t></a:r>
            <a:tab/>
            <a:fld id="{00000000-0000-0000-0000-000000000000}" type="slidenum"><a:rPr sz="1200"/><a:t>12</a:t></a:fld>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert "Slide\t12" in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_text_body_insets_adjust_svg_text_position() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="95250" y="190500"/><a:ext cx="762000" cy="381000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr lIns="19050" tIns="28575" rIns="95250" bIns="19050"/>
          <a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Inset</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'x="12"' in svg
    assert 'y="35"' in svg
    assert analyze_svg(svg).unsupported_attributes == {}


def test_drawingml_text_body_insets_adjust_centered_svg_text_anchor() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="952500" cy="190500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr lIns="95250" rIns="285750"/>
          <a:lstStyle/>
          <a:p><a:pPr algn="ctr"/><a:r><a:rPr sz="1200"/><a:t>Centered</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'x="40"' in svg
    assert 'text-anchor="middle"' in svg


def test_drawingml_text_body_insets_adjust_middle_and_bottom_svg_baselines() -> None:
    dml = """<p:spTree xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="middle"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="952500" cy="381000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr anchor="ctr" tIns="95250" bIns="95250"/>
          <a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Middle</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="bottom"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="476250"/><a:ext cx="952500" cy="381000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody>
          <a:bodyPr anchor="b" tIns="95250" bIns="190500"/>
          <a:lstStyle/>
          <a:p><a:r><a:rPr sz="1200"/><a:t>Bottom</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>"""

    svg = drawingml_to_svg(dml)

    assert 'y="20"' in svg
    assert 'dominant-baseline="middle"' in svg
    assert 'y="70"' in svg
    assert 'dominant-baseline="text-after-edge"' in svg
