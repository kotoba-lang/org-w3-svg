from __future__ import annotations

import json
from dataclasses import asdict

import pytest

import drawingml_svg
import drawingml_svg.ir
import svgraph as svgraph_package
from drawingml_svg.ir import svg_ir_to_json, svg_pptx_ir_to_json, svg_to_ir, svg_to_pptx_ir
from svgraph import svg_to_drawingml, svg_to_svgraph, svg_to_svgraph_presentation
from svgraph.cli import main as cli_main
from svgraph.model import svg_svgraph_presentation_to_json, svg_svgraph_to_json


def test_svgraph_model_exports_only_canonical_svgraph_surface() -> None:
    import svgraph.model

    assert svgraph.model.__all__ == [
        "SVGraphDependency",
        "SVGraphDocument",
        "SVGraphGuide",
        "SVGraphNode",
        "SVGraphPackagePart",
        "SVGraphPresentation",
        "SVGraphRuler",
        "SVGraphSlide",
        "SVGraphTemplate",
        "SVGraphTextStyle",
        "svg_svgraph_presentation_to_json",
        "svg_svgraph_to_json",
        "svg_to_svgraph",
        "svg_to_svgraph_presentation",
    ]
    for legacy_name in [
        "SvgIRDocument",
        "SvgIRNode",
        "SvgIRPresentation",
        "svg_ir_to_json",
        "svg_pptx_ir_to_json",
        "svg_to_ir",
        "svg_to_pptx_ir",
    ]:
        assert legacy_name not in svgraph.model.__all__


def test_svgraph_package_is_canonical_api_surface() -> None:
    assert svgraph_package.svg_to_svgraph is svg_to_svgraph
    assert svgraph_package.svg_to_svgraph_presentation is svg_to_svgraph_presentation
    assert "svg_to_svgraph" in svgraph_package.__all__
    assert "svg_to_ir" not in svgraph_package.__all__


def test_compatibility_package_declares_inline_types() -> None:
    from importlib import resources

    assert resources.files(drawingml_svg).joinpath("py.typed").is_file()


def test_compatibility_package_top_level_exports_match_svgraph_api() -> None:
    for name in svgraph_package.__all__:
        assert getattr(drawingml_svg, name) is getattr(svgraph_package, name)
    assert drawingml_svg.__all__ == svgraph_package.__all__


def test_compatibility_submodules_export_canonical_svgraph_callables() -> None:
    import drawingml_svg.converter
    import drawingml_svg.coverage
    import drawingml_svg.pptx
    import drawingml_svg.svgraph
    import svgraph.converter
    import svgraph.coverage
    import svgraph.model
    import svgraph.pptx

    assert drawingml_svg.converter.svg_to_drawingml is svgraph.converter.svg_to_drawingml
    assert drawingml_svg.converter.drawingml_to_svg is svgraph.converter.drawingml_to_svg
    assert drawingml_svg.coverage.analyze_svg is svgraph.coverage.analyze_svg
    assert drawingml_svg.pptx.svg_to_pptx is svgraph.pptx.svg_to_pptx
    assert drawingml_svg.pptx.svg_to_pptx_bytes is svgraph.pptx.svg_to_pptx_bytes
    assert drawingml_svg.svgraph.svg_to_svgraph is svgraph.model.svg_to_svgraph
    assert drawingml_svg.svgraph.svg_to_svgraph_presentation is svgraph.model.svg_to_svgraph_presentation
    assert drawingml_svg.converter.__all__ == svgraph.converter.__all__ == ["drawingml_to_svg", "svg_to_drawingml"]
    assert drawingml_svg.coverage.__all__ == svgraph.coverage.__all__ == ["SvgCoverage", "analyze_svg"]
    assert drawingml_svg.pptx.__all__ == svgraph.pptx.__all__ == [
        "build_slide_xml",
        "prepare_slide_media",
        "svg_to_pptx",
        "svg_to_pptx_bytes",
        "svg_to_slide_xmls",
        "write_pptx",
    ]
    assert drawingml_svg.svgraph.__all__ == svgraph.model.__all__


@pytest.mark.parametrize("executable", ["drawingml-svg", "svg2dml", "dml2svg", "svg2pptx", "drawingml-svg-analyze"])
def test_cli_alias_version_writes_canonical_package_identity(monkeypatch, capsys, executable: str) -> None:
    monkeypatch.setattr("sys.argv", [executable, "--version"])

    with pytest.raises(SystemExit) as excinfo:
        cli_main()

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert captured.out == "svgraph 0.1.46\n"


@pytest.mark.parametrize(
    ("executable", "command"),
    [
        ("svg2dml", "svg2dml"),
        ("dml2svg", "dml2svg"),
        ("svg2pptx", "svg2pptx"),
        ("drawingml-svg-analyze", "analyze"),
    ],
)
def test_cli_alias_help_writes_command_help(monkeypatch, capsys, executable: str, command: str) -> None:
    monkeypatch.setattr("sys.argv", [executable, "-h"])

    with pytest.raises(SystemExit) as excinfo:
        cli_main()

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert captured.out.startswith(f"usage: drawingml-svg {command} ")
    assert "Input file. Reads stdin when omitted." in captured.out


def test_legacy_executable_accepts_direct_svgraph_input(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "input.svg"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect data-kind="table"/></svg>', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["drawingml-svg", str(source)])

    assert cli_main() == 0
    captured = capsys.readouterr()

    assert '"kind": "svgraph"' in captured.out
    assert "executable 'drawingml-svg' is deprecated; use 'svgraph'" in captured.err


@pytest.mark.parametrize(
    ("executable", "replacement"),
    [
        ("svg2dml", "svgraph svg2dml"),
        ("dml2svg", "svgraph dml2svg"),
        ("svg2pptx", "svgraph svg2pptx"),
        ("drawingml-svg-analyze", "svgraph analyze"),
    ],
)
def test_legacy_executable_aliases_warn_toward_canonical_svgraph_commands(
    monkeypatch,
    tmp_path,
    capsys,
    executable: str,
    replacement: str,
) -> None:
    svg_source = tmp_path / "input.svg"
    svg_source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="8"/></svg>', encoding="utf-8")
    dml_source = tmp_path / "input.xml"
    dml_source.write_text(svg_to_drawingml(svg_source.read_text(encoding="utf-8")), encoding="utf-8")
    output = tmp_path / "out"
    argv_by_executable = {
        "svg2dml": ["svg2dml", str(svg_source), "-o", str(output.with_suffix(".xml"))],
        "dml2svg": ["dml2svg", str(dml_source), "-o", str(output.with_suffix(".svg"))],
        "svg2pptx": ["svg2pptx", str(svg_source), "-o", str(output.with_suffix(".pptx"))],
        "drawingml-svg-analyze": ["drawingml-svg-analyze", str(svg_source)],
    }
    monkeypatch.setattr("sys.argv", argv_by_executable[executable])

    assert cli_main() == 0
    captured = capsys.readouterr()

    assert f"executable '{executable}' is deprecated; use '{replacement}'" in captured.err


def test_cli_help_lists_svgraph_commands_and_hides_legacy_aliases(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["--help"])

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert captured.out.startswith("usage: svgraph ")
    assert "svgraph" in captured.out
    assert "svgraph-presentation" in captured.out
    assert "emit the metadata-preserving SVGraph JSON document" in captured.out
    assert "emit the SVGraph presentation/package JSON projection" in captured.out
    assert "convert SVG/SVGraph presentation metadata to a PPTX" in captured.out
    assert "package" in captured.out
    assert "pptxsvg" not in captured.out
    assert "{svg2dml,dml2svg,svg2pptx,analyze,ir" not in captured.out


def test_svgraph_preserves_metadata_data_attributes_and_dependencies() -> None:
    svg = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
  <metadata>{"title": "System", "relations": [{"from": "api", "to": "db"}]}</metadata>
  <defs>
    <linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient>
  </defs>
  <rect id="api" data-kind="service" data-bind="svc.api" fill="url(#g)" stroke="#fef9c3" x="1" y="2" width="3" height="4"/>
  <use id="api-copy" href="#api" x="10"/>
</svg>
"""

    svgraph = svg_to_svgraph(svg)

    assert svgraph.kind == "svgraph"
    assert svgraph.version == "0.1"
    assert svgraph.metadata["json"] == {"title": "System", "relations": [{"from": "api", "to": "db"}]}
    assert svgraph.presentation.kind == "svgraph-presentation"
    assert svgraph.presentation.slide_size == (100.0, 50.0)
    assert svgraph.presentation.slides[0].slide_id == "slide-1"
    assert svgraph.presentation.parts[-1].part_name == "/ppt/slides/slide1.xml"
    rect = svgraph.root.children[1]
    assert rect.tag == "rect"
    assert rect.data == {"bind": "svc.api", "kind": "service"}
    assert rect.dependencies[0].kind == "paint-server"
    assert rect.dependencies[0].target == "#g"
    assert "#fef9c3" not in [dep.target for dep in svgraph.dependencies]
    use = svgraph.root.children[2]
    assert use.dependencies[0].kind == "href"
    assert use.dependencies[0].target == "#api"
    assert [dep.target for dep in svgraph.dependencies] == ["#g", "#api"]


def test_svgraph_json_cli_payload_is_serializable() -> None:
    payload = svg_svgraph_to_json(
        """<svg xmlns="http://www.w3.org/2000/svg"><rect data-kind="table" width="10" height="10"/></svg>"""
    )

    data = json.loads(payload)

    assert data["root"]["children"][0]["data"] == {"kind": "table"}
    assert data["kind"] == "svgraph"
    assert data["presentation"]["kind"] == "svgraph-presentation"


def test_legacy_ir_aliases_are_not_top_level_exports() -> None:
    assert not hasattr(drawingml_svg, "svg_to_ir")
    assert not hasattr(drawingml_svg, "svg_to_pptx_ir")
    assert "svg_to_ir" not in drawingml_svg.__all__
    assert "svg_to_pptx_ir" not in drawingml_svg.__all__


def test_legacy_ir_module_keeps_only_explicit_pre_svgraph_aliases() -> None:
    assert hasattr(drawingml_svg.ir, "SvgIRDocument")
    assert not hasattr(drawingml_svg.ir, "SVGraphDocument")
    assert not hasattr(drawingml_svg.ir, "SvgraphDocument")
    assert "SvgIRDocument" in drawingml_svg.ir.__all__
    assert "SVGraphDocument" not in drawingml_svg.ir.__all__
    assert "SvgraphDocument" not in drawingml_svg.ir.__all__
    assert "svg_to_svgraph" not in drawingml_svg.ir.__all__


def test_legacy_svg_ir_alias_matches_svgraph_payload() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg"><rect data-kind="table" width="10" height="10"/></svg>"""
    with pytest.warns(DeprecationWarning, match=r"svg_to_ir\(\) is deprecated; use svgraph\.model\.svg_to_svgraph"):
        direct = svg_to_ir(svg).to_dict()
    with pytest.warns(DeprecationWarning, match=r"svg_ir_to_json\(\) is deprecated; use svgraph\.model\.svg_svgraph_to_json"):
        payload = json.loads(svg_ir_to_json(svg))

    assert direct["kind"] == "svgraph"
    assert payload["kind"] == "svgraph"
    assert payload["root"]["children"][0]["data"] == {"kind": "table"}


def test_svgraph_presentation_discovers_declared_slides() -> None:
    svg = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <metadata>{"presentation": {"slideSize": {"width": 1280, "height": 720}}}</metadata>
  <g id="intro" data-kind="slide" data-title="Intro" viewBox="0 0 1280 720">
    <title>Opening</title>
    <rect data-role="title" width="300" height="80"/>
  </g>
  <svg id="detail" data-role="slide" viewBox="0 0 960 540">
    <metadata>{"title": "Detail"}</metadata>
    <rect data-kind="table" width="600" height="300"/>
  </svg>
</svg>
"""

    presentation = svg_to_svgraph_presentation(svg)

    assert presentation.kind == "svgraph-presentation"
    assert presentation.slide_size == (1280.0, 720.0)
    assert [slide.slide_id for slide in presentation.slides] == ["intro", "detail"]
    assert [slide.title for slide in presentation.slides] == ["Intro", "Detail"]
    assert presentation.slides[1].view_box == (0.0, 0.0, 960.0, 540.0)
    assert [part.part_name for part in presentation.parts[-2:]] == ["/ppt/slides/slide1.xml", "/ppt/slides/slide2.xml"]
    assert [part.content_type for part in presentation.parts[-2:]] == [
        "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
        "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
    ]
    assert [part.source_node_id for part in presentation.parts[-2:]] == ["n0.0", "n0.1"]


def test_svgraph_presentation_preserves_presentation_templates_guides_rulers_and_text_styles() -> None:
    svg = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <metadata>{
    "presentation": {
      "masters": [{"id": "brand-master", "theme": "brand"}],
      "layouts": [{"id": "title-content", "master": "brand-master"}],
      "guides": [{"id": "safe-left", "orientation": "vertical", "position": 96}],
      "rulers": [{"id": "x", "orientation": "horizontal", "origin": 0, "spacing": 16}],
      "textStyles": {
        "title": {"fontFamily": "Aptos Display", "fontSize": 48, "bold": true},
        "lead": {"fontFamily": "Aptos", "fontSize": 24},
        "body": {"fontFamily": "Aptos", "fontSize": 16}
      }
    }
  }</metadata>
  <g id="master-node" data-kind="slide-master" data-name="Brand"/>
  <g id="layout-node" data-kind="slide-layout" data-master="brand-master"/>
  <line id="guide-node" data-kind="guide" data-orientation="horizontal" data-position="120"/>
  <line id="ruler-node" data-kind="ruler" data-orientation="vertical" data-origin="8" data-spacing="24"/>
  <text id="caption-style" data-kind="style-template" data-role="caption" font-size="12"/>
  <g id="slide-a" data-kind="slide"><rect width="10" height="10"/></g>
</svg>
"""

    presentation = svg_to_svgraph_presentation(svg)

    assert [master.template_id for master in presentation.masters] == ["brand-master", "master-node"]
    assert [layout.template_id for layout in presentation.layouts] == ["title-content", "layout-node"]
    assert [part.part_name for part in presentation.parts if part.kind == "slide-master"] == [
        "/ppt/slideMasters/slideMaster1.xml",
        "/ppt/slideMasters/slideMaster2.xml",
    ]
    assert [part.content_type for part in presentation.parts if part.kind == "slide-master"] == [
        "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
        "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
    ]
    assert [part.content_type for part in presentation.parts if part.kind == "slide-layout"] == [
        "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
        "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
    ]
    assert [part.content_type for part in presentation.parts if part.kind == "theme"] == [
        "application/vnd.openxmlformats-officedocument.theme+xml",
    ]
    assert [part.part_name for part in presentation.parts if part.kind == "custom-xml"] == [
        "/customXml/item1.xml",
    ]
    assert [part.content_type for part in presentation.parts if part.kind == "custom-xml"] == ["application/xml"]
    assert [part.source_node_id for part in presentation.parts if part.kind == "slide-master"] == [None, "n0.0"]
    assert [(guide.guide_id, guide.orientation, guide.position) for guide in presentation.guides] == [
        ("safe-left", "vertical", 96.0),
        ("guide-node", "horizontal", 120.0),
    ]
    assert [(ruler.ruler_id, ruler.orientation, ruler.spacing) for ruler in presentation.rulers] == [
        ("x", "horizontal", 16.0),
        ("ruler-node", "vertical", 24.0),
    ]
    assert [style.role for style in presentation.text_styles] == ["title", "lead", "body", "caption"]
    assert presentation.text_styles[0].properties["fontSize"] == 48


def test_svgraph_presentation_accepts_snake_case_presentation_metadata() -> None:
    svg = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9">
  <metadata>{
    "presentation": {
      "slide_size": [1920, 1080],
      "text_styles": [
        {"id": "title-style", "role": "title", "fontFamily": "Aptos Display", "fontSize": 60},
        {"role": "body", "fontFamily": "Aptos", "fontSize": 24}
      ]
    }
  }</metadata>
  <g id="slide-a" data-kind="slide"><rect width="10" height="10"/></g>
</svg>
"""

    presentation = svg_to_svgraph_presentation(svg)

    assert presentation.slide_size == (1920.0, 1080.0)
    assert [(style.style_id, style.role) for style in presentation.text_styles] == [
        ("title-style", "title"),
        ("body", "body"),
    ]
    assert presentation.text_styles[0].properties["fontSize"] == 60


def test_svgraph_presentation_json_cli_payload_is_serializable() -> None:
    payload = svg_svgraph_presentation_to_json(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><g data-slide="1"/></svg>"""
    )

    data = json.loads(payload)

    assert data["kind"] == "svgraph-presentation"
    assert data["slide_size"] == [16.0, 9.0]
    assert data["slides"][0]["slide_id"] == "1"
    part_types = {part["kind"]: part["content_type"] for part in data["parts"]}
    assert part_types == {
        "presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        "slide-master": "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
        "slide-layout": "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
        "theme": "application/vnd.openxmlformats-officedocument.theme+xml",
        "custom-xml": "application/xml",
        "slide": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
    }
    assert data["parts"][-1] == {
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
        "kind": "slide",
        "part_name": "/ppt/slides/slide1.xml",
        "source_node_id": "n0.0",
    }


def test_legacy_pptx_ir_alias_matches_svgraph_presentation_payload() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><g data-slide="1"/></svg>"""

    with pytest.warns(
        DeprecationWarning,
        match=r"svg_to_pptx_ir\(\) is deprecated; use svgraph\.model\.svg_to_svgraph_presentation",
    ):
        legacy = svg_to_pptx_ir(svg)
    with pytest.warns(
        DeprecationWarning,
        match=r"svg_pptx_ir_to_json\(\) is deprecated; use svgraph\.model\.svg_svgraph_presentation_to_json",
    ):
        legacy_payload = json.loads(svg_pptx_ir_to_json(svg))

    assert legacy.kind == "svgraph-presentation"
    assert legacy_payload == json.loads(json.dumps(asdict(legacy)))


def test_cli_legacy_svgraph_commands_still_work(tmp_path, capsys) -> None:
    source = tmp_path / "input.svg"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><g data-slide="1"/></svg>', encoding="utf-8")

    assert cli_main(["ir", str(source)]) == 0
    captured = capsys.readouterr()
    assert '"kind": "svgraph"' in captured.out
    assert "'ir' is deprecated; use 'svgraph'" in captured.err

    assert cli_main(["pptxsvg", str(source)]) == 0
    captured = capsys.readouterr()
    assert '"kind": "svgraph-presentation"' in captured.out
    assert "'pptxsvg' is deprecated; use 'svgraph-presentation'" in captured.err
