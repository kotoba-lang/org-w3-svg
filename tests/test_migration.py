from __future__ import annotations

from pathlib import Path


LEGACY_TERMS = (
    "PPTXSVG",
    "pptxsvg",
    "SvgIR",
    "svg_to_ir",
    "svg_to_pptx_ir",
    "svg_ir",
    "pptx_ir",
    "presentation IR",
    "SVG IR",
    "downloadIrBtn",
    "downloadSvgraphBtn",
    "downloadPptxsvg",
    "Svgraph",
    "_pptxsvg",
)

ALLOWED_LEGACY_TERMS = {
    "MIGRATION.md": {"pptxsvg", "SvgIR", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir"},
    "README.md": {"pptxsvg", "svg_to_ir", "svg_to_pptx_ir", "pptx_ir"},
    "docs/adr/0001-svgraph.md": {"svg_to_ir"},
    "src/drawingml_svg/cli.py": {"pptxsvg"},
    "src/drawingml_svg/ir.py": {"SvgIR", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir"},
    "src/svgraph/cli.py": {"pptxsvg"},
    "tests/test_converter.py": {
        "PPTXSVG",
        "pptxsvg",
        "_pptxsvg",
        "svg_to_ir",
        "svg_to_pptx_ir",
        "presentation IR",
        "pptx_ir",
        "downloadIrBtn",
        "downloadSvgraphBtn",
        "downloadPptxsvg",
        "Svgraph",
    },
    "tests/test_migration.py": set(LEGACY_TERMS),
    "tests/test_svgraph.py": {"SvgIR", "pptxsvg", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir", "Svgraph"},
}

FORBIDDEN_PUBLIC_LEGACY_STRINGS = (
    "com-junkawasaki/drawingml-svg",
    "com-junkawasaki.github.io/drawingml-svg",
    "drawingml-svg-web",
    "drawingml-svg sample",
    "drawingml-svg web",
    "DrawingML SVG Group",
    "drawingml-svg-arrow",
    "drawingml-svg-sample.pptx",
    "drawingml-svg-coverage.pptx",
    "drawingml-svg-complex.pptx",
    "drawingml-svg-svgraph.pptx",
)

FORBIDDEN_DISTRIBUTION_LEGACY_STRINGS = (
    'name = "drawingml-svg"',
    "Name: drawingml-svg",
    "tmp/dist/drawingml_svg-",
    "tmp/dist/drawingml-svg-",
    "drawingml_svg-*.whl",
    "drawingml_svg-*.tar.gz",
    "drawingml-svg-*.whl",
    "drawingml-svg-*.tar.gz",
    "src/drawingml_svg.egg-info",
)

LEGACY_IMPORT_PATTERNS = (
    "from drawingml_svg",
    "import drawingml_svg",
    "python -m drawingml_svg.cli",
    "drawingml_svg.cli",
)

ALLOWED_LEGACY_IMPORT_SURFACES = {
    "tests/test_migration.py",
    "tests/test_svgraph.py",
}

COMPATIBILITY_WRAPPER_MODULES = {
    "src/drawingml_svg/cli.py": "from svgraph.cli import *",
    "src/drawingml_svg/converter.py": "from svgraph.converter import *",
    "src/drawingml_svg/coverage.py": "from svgraph.coverage import *",
    "src/drawingml_svg/pptx.py": "from svgraph.pptx import *",
    "src/drawingml_svg/svgraph.py": "from svgraph.model import *",
}


def test_legacy_names_are_limited_to_compatibility_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    unexpected: list[str] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        allowed = ALLOWED_LEGACY_TERMS.get(relative, set())
        for term in LEGACY_TERMS:
            if term in text and term not in allowed:
                unexpected.append(f"{relative}: {term}")

    assert unexpected == []


def test_public_surfaces_use_svgraph_repo_and_artifact_names() -> None:
    root = Path(__file__).resolve().parents[1]
    unexpected: list[str] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in {"MIGRATION.md", "tests/test_migration.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN_PUBLIC_LEGACY_STRINGS:
            if term in text:
                unexpected.append(f"{relative}: {term}")

    assert unexpected == []


def test_distribution_metadata_uses_svgraph_name() -> None:
    root = Path(__file__).resolve().parents[1]
    unexpected: list[str] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/test_migration.py":
            continue
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN_DISTRIBUTION_LEGACY_STRINGS:
            if term in text:
                unexpected.append(f"{relative}: {term}")

    assert unexpected == []


def test_canonical_code_paths_import_svgraph_package() -> None:
    root = Path(__file__).resolve().parents[1]
    unexpected: list[str] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in ALLOWED_LEGACY_IMPORT_SURFACES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in LEGACY_IMPORT_PATTERNS:
            if pattern in text:
                unexpected.append(f"{relative}: {pattern}")

    assert unexpected == []


def test_drawingml_svg_modules_are_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    unexpected: list[str] = []
    for relative, expected_import in COMPATIBILITY_WRAPPER_MODULES.items():
        text = (root / relative).read_text(encoding="utf-8")
        if expected_import not in text:
            unexpected.append(f"{relative}: missing {expected_import}")
        if "def " in text or "class " in text:
            unexpected.append(f"{relative}: contains implementation definitions")

    assert unexpected == []


def _text_files(root: Path) -> list[Path]:
    skipped = {".git", ".pytest_cache", ".ruff_cache", "build", "dist", "node_modules", "tmp", "__pycache__"}
    suffixes = {".html", ".js", ".json", ".md", ".py", ".svg", ".toml", ".ts", ".txt", ".yml", ".yaml"}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and not any(part in skipped or part.endswith(".egg-info") for part in path.relative_to(root).parts)
    )
