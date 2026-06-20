from __future__ import annotations

import ast
from email.parser import Parser
import json
from pathlib import Path
import tomllib


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
    "src/drawingml_svg/__init__.py": "from svgraph import",
    "src/drawingml_svg/cli.py": "from svgraph.cli import *",
    "src/drawingml_svg/converter.py": "from svgraph.converter import *",
    "src/drawingml_svg/coverage.py": "from svgraph.coverage import *",
    "src/drawingml_svg/pptx.py": "from svgraph.pptx import *",
    "src/drawingml_svg/svgraph.py": "from svgraph.model import *",
}

CANONICAL_TOP_LEVEL_API = [
    "analyze_svg",
    "drawingml_to_svg",
    "svg_to_drawingml",
    "svg_to_pptx",
    "svg_to_pptx_bytes",
    "svg_to_svgraph",
    "svg_to_svgraph_presentation",
]


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


def test_pyproject_keeps_legacy_console_scripts_as_svgraph_compatibility_aliases() -> None:
    project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]

    assert project["scripts"]["drawingml-svg"] == "svgraph.cli:main"
    assert project["scripts"]["drawingml-svg-analyze"] == "svgraph.cli:main"
    assert project["scripts"]["dml2svg"] == "svgraph.cli:main"
    assert project["scripts"]["svg2dml"] == "svgraph.cli:main"
    assert project["scripts"]["svg2pptx"] == "svgraph.cli:main"


def test_top_level_packages_expose_only_canonical_svgraph_api() -> None:
    root = Path(__file__).resolve().parents[1]
    svgraph_init = (root / "src" / "svgraph" / "__init__.py").read_text(encoding="utf-8")
    compatibility_init = (root / "src" / "drawingml_svg" / "__init__.py").read_text(encoding="utf-8")

    assert _literal_all(svgraph_init) == CANONICAL_TOP_LEVEL_API
    assert _literal_all(compatibility_init) == CANONICAL_TOP_LEVEL_API
    for source in [svgraph_init, compatibility_init]:
        assert "svg_to_ir" not in source
        assert "svg_to_pptx_ir" not in source
        assert "SvgIRDocument" not in source


def test_module_execution_is_canonical_svgraph_entry_point() -> None:
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "src" / "svgraph" / "__main__.py").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")

    assert 'sys.argv[0] = "svgraph"' in main_source
    assert "from .cli import main" in main_source
    assert "raise SystemExit(main())" in main_source
    assert "tmp/wheel-venv/bin/python -m svgraph --version" in workflow
    assert "tmp/wheel-venv/bin/python -m svgraph analyze examples/coverage.svg" in workflow
    assert "python -m svgraph --version" in readme
    assert "python -m svgraph --version" in migration
    assert "python -m drawingml_svg" not in readme
    assert "python -m drawingml_svg" not in migration


def test_readme_lists_all_legacy_console_compatibility_aliases() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (root / "README.md").read_text(encoding="utf-8")

    for executable in sorted(set(project["scripts"]) - {"svgraph"}):
        assert executable in readme


def test_generated_distribution_metadata_preserves_legacy_compatibility_entry_points() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_info = root / "src" / "svgraph.egg-info" / "PKG-INFO"
    entry_points = root / "src" / "svgraph.egg-info" / "entry_points.txt"
    top_level = root / "src" / "svgraph.egg-info" / "top_level.txt"
    if not pkg_info.exists() or not entry_points.exists() or not top_level.exists():
        return

    metadata = Parser().parsestr(pkg_info.read_text(encoding="utf-8"))
    entry_point_text = entry_points.read_text(encoding="utf-8")
    top_level_names = set(top_level.read_text(encoding="utf-8").splitlines())

    assert metadata["Name"] == "svgraph"
    assert "drawingml-svg = svgraph.cli:main" in entry_point_text
    assert "drawingml-svg-analyze = svgraph.cli:main" in entry_point_text
    assert {"svgraph", "drawingml_svg"} <= top_level_names


def test_release_checklist_keeps_legacy_console_alias_smoke() -> None:
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    assert "pyproject.toml` and `package.json` have the intended version" in release
    assert "drawingml-svg --version" in release


def test_release_and_ci_distribution_smoke_use_svgraph_artifact_names() -> None:
    root = Path(__file__).resolve().parents[1]
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for source in [release, workflow]:
        assert "tmp/dist/svgraph-*.whl" in source
        assert "tmp/dist/svgraph-*.tar.gz" in source
        assert "tmp/dist/drawingml_svg-" not in source
        assert "tmp/dist/drawingml-svg-" not in source

    assert "tmp/release-svgraph.json" in release
    assert "tmp/release-svgraph-presentation.json" in release
    assert "tmp/release-legacy-svgraph.json" in release
    assert "tmp/wheel-svgraph.json" in workflow
    assert "tmp/wheel-svgraph-presentation.json" in workflow
    assert "tmp/wheel-legacy-svgraph.json" in workflow


def test_contributor_checks_use_canonical_svgraph_commands_and_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pr_template = (root / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

    for source in [contributing, pr_template]:
        assert "PYTHONPATH=src python -m pytest -q" in source
        assert "PYTHONPATH=src python -m svgraph analyze examples/coverage.svg" in source
        assert "tmp/svgraph-coverage.pptx" in source
        assert "python -m zipfile --test tmp/svgraph-coverage.pptx" in source
        assert "python -m svgraph.cli" not in source
        assert "python -m drawingml_svg" not in source
        assert "tmp/drawingml-svg-coverage.pptx" not in source

    assert "PYTHONPATH=src python -m svgraph svgraph examples/svgraph.svg > tmp/svgraph.json" in contributing
    assert (
        "PYTHONPATH=src python -m svgraph svgraph-presentation examples/svgraph.svg > tmp/svgraph-presentation.json"
        in contributing
    )


def test_pptx_exporter_uses_only_svgraph_internal_shape_prefix() -> None:
    pptx_source = (Path(__file__).resolve().parents[1] / "src" / "svgraph" / "pptx.py").read_text(encoding="utf-8")

    assert "_svgraph_" in pptx_source
    assert "_pptxsvg_" not in pptx_source


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


def test_pages_artifacts_use_svgraph_naming() -> None:
    root = Path(__file__).resolve().parents[1]
    public_assets = "\n".join(
        [
            (root / "docs" / "index.html").read_text(encoding="utf-8"),
            (root / "docs" / "app.js").read_text(encoding="utf-8"),
        ]
    )

    assert "SVGraph" in public_assets
    assert "downloadSVGraphBtn" in public_assets
    assert "PPTXSVG" not in public_assets
    assert "pptxsvg" not in public_assets
    assert "presentation IR" not in public_assets
    assert "downloadIrBtn" not in public_assets
    assert "downloadSvgraphBtn" not in public_assets
    assert "downloadPptxsvg" not in public_assets


def test_web_source_and_package_metadata_use_svgraph_naming() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_json = (root / "package.json").read_text(encoding="utf-8")
    package_lock = (root / "package-lock.json").read_text(encoding="utf-8")
    package_metadata = json.loads(package_json)
    lock_metadata = json.loads(package_lock)
    html = (root / "docs" / "index.html").read_text(encoding="utf-8")
    source = (root / "web" / "app.ts").read_text(encoding="utf-8")

    assert '"name": "svgraph-web"' in package_json
    assert '"name": "svgraph-web"' in package_lock
    assert package_metadata["version"] == pyproject["project"]["version"]
    assert lock_metadata["version"] == package_metadata["version"]
    assert lock_metadata["packages"][""]["version"] == package_metadata["version"]
    assert package_metadata["homepage"] == "https://com-junkawasaki.github.io/svgraph/"
    assert package_metadata["repository"] == {
        "type": "git",
        "url": "git+https://github.com/com-junkawasaki/svgraph.git",
    }
    assert package_metadata["bugs"] == {"url": "https://github.com/com-junkawasaki/svgraph/issues"}
    assert package_metadata["license"] == "MIT"
    assert "<title>SVGraph Editor</title>" in html
    assert 'id="downloadSVGraphBtn"' in html
    assert 'mustElement<HTMLButtonElement>("downloadSVGraphBtn")' in source
    assert 'downloadText("svgraph-presentation.json"' in source

    combined = "\n".join([package_json, package_lock, html, source])
    assert "drawingml-" + "svg-web" not in combined
    assert "PPTXSVG" not in combined
    assert "presentation IR" not in combined
    assert "downloadIrBtn" not in combined
    assert "downloadSvgraphBtn" not in combined
    assert "downloadPptxsvg" not in combined


def test_pages_typescript_build_targets_committed_svgraph_artifact() -> None:
    root = Path(__file__).resolve().parents[1]
    package_metadata = json.loads((root / "package.json").read_text(encoding="utf-8"))
    tsconfig = json.loads((root / "tsconfig.web.json").read_text(encoding="utf-8"))
    html = (root / "docs" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")

    assert package_metadata["scripts"]["build:web"] == "tsc -p tsconfig.web.json"
    assert package_metadata["scripts"]["check:web"] == "tsc -p tsconfig.web.json --noEmit"
    assert tsconfig["compilerOptions"]["rootDir"] == "web"
    assert tsconfig["compilerOptions"]["outDir"] == "docs"
    assert tsconfig["include"] == ["web/**/*.ts"]
    assert '<script type="module" src="./app.js"></script>' in html
    assert 'version: "0.3-svgraph-web-ts"' in app_js
    assert 'downloadBlob("svgraph-web.pptx"' in app_js


def test_browser_only_svgraph_build_is_documented_and_ci_guarded() -> None:
    root = Path(__file__).resolve().parents[1]
    package_metadata = json.loads((root / "package.json").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "`web/app.ts` builds SVGraph" in readme
    assert "`docs/app.js` is the compiled Pages artifact." in readme
    assert "Python or server APIs" in readme
    assert "npm ci" in readme
    assert "npm run build:web" in readme
    assert package_metadata["scripts"]["build:web"] == "tsc -p tsconfig.web.json"
    assert package_metadata["scripts"]["check:web"] == "tsc -p tsconfig.web.json --noEmit"
    assert "node-version: \"24\"" in workflow
    assert "run: npm ci" in workflow
    assert "run: npm run build:web" in workflow


def test_changelog_documents_svgraph_migration_guard_surfaces() -> None:
    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")

    for expected in [
        "top-level APIs",
        "Pages artifacts",
        "non-compatibility code paths",
        "python -m svgraph",
        "python -m svgraph.cli",
        "release and CI smoke checks",
        "wheel metadata",
        "canonical `svgraph` surfaces",
        "canonical typed Python import package",
        "svgraph.model",
        "svgraph.converter",
        "svgraph.coverage",
        "svgraph.pptx",
        "contributing, security, code of conduct, issue templates, PR template",
    ]:
        assert expected in changelog


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


def test_docs_point_legacy_ir_to_svgraph_model() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    adr = (root / "docs" / "adr" / "0001-svgraph.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")

    assert "python -m svgraph --version" in readme
    assert "compatibility aliases that point to `svgraph.model`" in readme
    assert "svgraph.model.svg_to_svgraph()" in adr
    assert "warns toward `svgraph.model`" in adr
    assert "`drawingml_svg.ir.svg_to_ir()` | `svgraph.model.svg_to_svgraph()`" in migration
    assert "`drawingml_svg.ir.svg_to_pptx_ir()` | `svgraph.model.svg_to_svgraph_presentation()`" in migration


def test_migration_guide_covers_public_rename_surfaces() -> None:
    migration = (Path(__file__).resolve().parents[1] / "MIGRATION.md").read_text(encoding="utf-8")

    for legacy, canonical in [
        ("`com-junkawasaki/" + "drawingml-svg`", "`com-junkawasaki/svgraph`"),
        ("`drawingml-svg` Python distribution", "`svgraph` Python distribution"),
        ("`drawingml_svg` import package", "`svgraph` import package"),
        ("`drawingml-svg` executable", "`svgraph` executable"),
        ("`pptxsvg` CLI command", "`svgraph-presentation` CLI command"),
    ]:
        assert f"{legacy} | {canonical}" in migration


def test_migration_guide_module_mapping_matches_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    module_pairs = {
        "drawingml_svg.converter": "svgraph.converter",
        "drawingml_svg.coverage": "svgraph.coverage",
        "drawingml_svg.pptx": "svgraph.pptx",
        "drawingml_svg.svgraph": "svgraph.model",
    }

    for legacy_module, canonical_module in module_pairs.items():
        legacy_path = root / "src" / Path(*legacy_module.split(".")).with_suffix(".py")
        canonical_path = root / "src" / Path(*canonical_module.split(".")).with_suffix(".py")
        legacy_text = legacy_path.read_text(encoding="utf-8")

        assert canonical_path.is_file()
        assert f"`{legacy_module}` | `{canonical_module}`" in migration
        assert f"from {canonical_module} import *" in legacy_text
        assert "def " not in legacy_text
        assert "class " not in legacy_text


def test_migration_guide_cli_examples_use_canonical_svgraph_entry_points() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    cli_section = migration.split("## CLI", maxsplit=1)[1].split("## Generated Artifacts", maxsplit=1)[0]

    assert project["scripts"]["svgraph"] == "svgraph.cli:main"
    for command in [
        "svgraph svg2dml input.svg -o shape.xml",
        "svgraph svg2pptx deck.svg -o deck.pptx",
        "svgraph analyze input.svg",
        "svgraph input.svg",
        "svgraph svgraph-presentation input.svg",
        "python -m svgraph --version",
    ]:
        assert command in cli_section

    assert "drawingml-svg" not in cli_section
    assert "pptxsvg" not in cli_section
    assert "\nir " not in cli_section


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


def _literal_all(source: str) -> list[str]:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, list)
            assert all(isinstance(item, str) for item in value)
            return value
    raise AssertionError("missing __all__ assignment")
