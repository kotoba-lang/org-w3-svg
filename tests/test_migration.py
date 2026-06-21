from __future__ import annotations

import ast
from email.parser import Parser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile


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
    ".github/workflows/ci.yml",
    "RELEASE.md",
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


def test_legacy_name_allowlist_is_explicitly_scoped_to_compatibility_docs_and_tests() -> None:
    assert ALLOWED_LEGACY_TERMS == {
        "MIGRATION.md": {"pptxsvg", "SvgIR", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir"},
        "README.md": {"pptxsvg", "svg_to_ir", "svg_to_pptx_ir", "pptx_ir"},
        "docs/adr/0001-svgraph.md": {"svg_to_ir"},
        "src/drawingml_svg/cli.py": {"pptxsvg"},
        "src/drawingml_svg/ir.py": {"SvgIR", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir"},
        "src/svgraph/cli.py": {"pptxsvg"},
        "tests/test_migration.py": set(LEGACY_TERMS),
        "tests/test_svgraph.py": {"SvgIR", "pptxsvg", "svg_to_ir", "svg_to_pptx_ir", "svg_ir", "pptx_ir", "Svgraph"},
    }
    for allowed_path in ALLOWED_LEGACY_TERMS:
        assert allowed_path in {
            "MIGRATION.md",
            "README.md",
            "docs/adr/0001-svgraph.md",
            "src/drawingml_svg/cli.py",
            "src/drawingml_svg/ir.py",
            "src/svgraph/cli.py",
            "tests/test_migration.py",
            "tests/test_svgraph.py",
        }


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


def test_browser_coverage_sets_match_python_analyzer_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    coverage_source = (root / "src" / "svgraph" / "coverage.py").read_text(encoding="utf-8")
    web_source = (root / "web" / "app.ts").read_text(encoding="utf-8")
    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")

    expected_supported = set(_literal_assignment(coverage_source, "SUPPORTED_ELEMENTS"))
    expected_ignored = set(_literal_assignment(coverage_source, "IGNORED_ELEMENTS"))
    expected_unsupported = set(_literal_assignment(coverage_source, "UNSUPPORTED_ATTRIBUTES"))
    expected_text_layout = set(_literal_assignment(coverage_source, "TEXT_LAYOUT_ATTRIBUTES"))

    for generated in [web_source, app_js]:
        assert _typescript_string_set(generated, "coverageSupportedElements") == expected_supported
        assert _typescript_string_set(generated, "coverageIgnoredElements") == expected_ignored
        assert _typescript_string_set(generated, "coverageUnsupportedAttributes") == expected_unsupported
        assert _typescript_string_set(generated, "coverageTextLayoutAttributes") == expected_text_layout


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


def test_generated_artifact_paths_are_ignored_and_untracked() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    tracked = subprocess.run(
        ["git", "ls-files"],
        check=True,
        cwd=root,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.splitlines()

    for ignored in [
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        ".ruff_cache/",
        "*.egg-info/",
        "build/",
        "dist/",
        "tmp/",
        "node_modules/",
    ]:
        assert ignored in gitignore

    forbidden_tracked_patterns = [
        "tmp/",
        "build/",
        "dist/",
        "node_modules/",
        "src/drawingml_svg.egg-info/",
        "src/svgraph.egg-info/",
        ".ruff_cache/",
        "drawingml-svg-",
        "drawingml_svg-0.",
        "pptxsvg-web",
    ]
    unexpected = [
        path
        for path in tracked
        for pattern in forbidden_tracked_patterns
        if path.startswith(pattern) or pattern in path
    ]

    assert unexpected == []


def test_project_urls_are_canonical_svgraph_locations() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_metadata = json.loads((root / "package.json").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")

    assert pyproject["project"]["urls"] == {
        "Homepage": "https://github.com/com-junkawasaki/svgraph",
        "Repository": "https://github.com/com-junkawasaki/svgraph",
        "Documentation": "https://com-junkawasaki.github.io/svgraph/",
        "Issues": "https://github.com/com-junkawasaki/svgraph/issues",
    }
    assert package_metadata["homepage"] == "https://com-junkawasaki.github.io/svgraph/"
    assert package_metadata["repository"]["url"] == "git+https://github.com/com-junkawasaki/svgraph.git"
    assert package_metadata["bugs"]["url"] == "https://github.com/com-junkawasaki/svgraph/issues"
    assert pyproject["project"]["description"] == (
        "Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, "
        "and browser-only web editing."
    )
    assert {"svg", "svgraph", "drawingml", "presentationml", "pptx", "web"} <= set(
        pyproject["project"]["keywords"]
    )
    assert package_metadata["name"] == "@com-junkawasaki/svgraph"
    project_links = readme.split("## Project links", maxsplit=1)[1].split("## Install", maxsplit=1)[0]
    assert "- Repository: <https://github.com/com-junkawasaki/svgraph>" in project_links
    assert "- Issue tracker: <https://github.com/com-junkawasaki/svgraph/issues>" in project_links
    assert "- SVGraph web editor: <https://com-junkawasaki.github.io/svgraph/>" in project_links
    assert "https://github.com/com-junkawasaki/svgraph/issues" in readme
    assert "https://com-junkawasaki.github.io/svgraph/" in readme
    assert "https://com-junkawasaki.github.io/svgraph/" in migration
    for source in [readme, migration, json.dumps(package_metadata), json.dumps(pyproject)]:
        assert "github.com/com-junkawasaki/drawingml-svg" not in source
        assert "com-junkawasaki.github.io/drawingml-svg" not in source


def test_github_templates_cover_canonical_svgraph_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    }
    pr_template = (root / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    security = (root / "SECURITY.md").read_text(encoding="utf-8")
    advisory_url = "https://github.com/com-junkawasaki/svgraph/security/advisories/new"

    assert set(templates) == {"bug_report.yml", "config.yml", "feature_request.yml"}
    assert "SVG to SVGraph" in templates["bug_report.yml"]
    assert "SVG to SVGraph presentation" in templates["bug_report.yml"]
    assert "SVG to PresentationML/PPTX" in templates["bug_report.yml"]
    assert "Browser editor" in templates["bug_report.yml"]
    assert "SVGraph JSON" in templates["bug_report.yml"]
    assert "SVGraph model" in templates["feature_request.yml"]
    assert "SVGraph presentation model" in templates["feature_request.yml"]
    assert "PresentationML/PPTX export" in templates["feature_request.yml"]
    assert "Browser editor" in templates["feature_request.yml"]
    assert advisory_url in templates["config.yml"]
    assert advisory_url in security
    assert "SVGraph JSON payload" in security
    assert "generated PPTX package" in security
    assert "## SVGraph impact" in pr_template
    assert "SVGraph model or metadata changed" in pr_template
    assert "SVGraph presentation/package projection changed" in pr_template
    assert "PresentationML/PPTX export changed" in pr_template
    assert "Browser editor or Pages artifact changed" in pr_template
    assert "## Converter impact" not in pr_template
    assert "tmp/svgraph-coverage.pptx" in pr_template
    for source in [*templates.values(), pr_template, security]:
        assert "drawingml-svg" not in source
        assert "pptxsvg" not in source


def test_documented_python_api_examples_use_canonical_svgraph_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    docs = {
        "README.md": (root / "README.md").read_text(encoding="utf-8"),
        "MIGRATION.md": (root / "MIGRATION.md").read_text(encoding="utf-8"),
    }

    for name, text in docs.items():
        python_blocks = re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)
        assert python_blocks, name
        for block in python_blocks:
            ast.parse(block)
            assert "from svgraph" in block
            assert "from drawingml_svg" not in block
            assert "import drawingml_svg" not in block
            assert "svg_to_ir" not in block
            assert "svg_to_pptx_ir" not in block


def test_migration_guide_python_import_example_covers_top_level_svgraph_api() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    python_blocks = re.findall(r"```python\n(.*?)```", migration, flags=re.DOTALL)
    import_block = python_blocks[0]
    module = ast.parse(import_block)
    imported_from_svgraph = {
        alias.name
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module == "svgraph"
        for alias in node.names
    }

    assert imported_from_svgraph == set(CANONICAL_TOP_LEVEL_API)


def test_readme_python_examples_cover_top_level_svgraph_api() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    python_blocks = re.findall(r"```python\n(.*?)```", readme, flags=re.DOTALL)
    imported_from_svgraph = {
        alias.name
        for block in python_blocks
        for node in ast.parse(block).body
        if isinstance(node, ast.ImportFrom) and node.module == "svgraph"
        for alias in node.names
    }

    assert imported_from_svgraph == set(CANONICAL_TOP_LEVEL_API)


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


def test_typed_package_data_keeps_svgraph_canonical_and_compatibility_markers() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert package_data == {"drawingml_svg": ["py.typed"], "svgraph": ["py.typed"]}
    assert (root / "src" / "svgraph" / "py.typed").is_file()
    assert (root / "src" / "drawingml_svg" / "py.typed").is_file()
    assert '"svgraph/py.typed",' in workflow
    assert '"drawingml_svg/py.typed",' in workflow
    assert '"src/svgraph/py.typed",' in workflow
    assert '"src/drawingml_svg/py.typed",' in workflow
    assert 'assert expected in wheel_names' in workflow
    assert 'assert f"{root}/{expected}" in sdist_names' in workflow


def test_manifest_and_ci_package_svgraph_migration_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    packaged_docs = [
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "MIGRATION.md",
        "RELEASE.md",
        "SECURITY.md",
        "package.json",
        "package-lock.json",
        "tsconfig.web.json",
        "docs/.nojekyll",
        "docs/adr/0001-svgraph.md",
        "docs/app.d.ts",
        "docs/app.js",
        "docs/index.html",
        "docs/svgraph-web-editor.md",
        "examples/__init__.py",
        "examples/complex.svg",
        "examples/coverage.svg",
        "examples/make_pptx.py",
        "examples/sample.svg",
        "examples/svgraph.svg",
        "web/app.ts",
    ]

    for doc in packaged_docs:
        assert (root / doc).is_file()
        assert f"include {doc}" in manifest
        assert f'f"{{root}}/{doc}" in sdist_names' in workflow


def test_module_execution_is_canonical_svgraph_entry_point() -> None:
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "src" / "svgraph" / "__main__.py").read_text(encoding="utf-8")
    cli_source = (root / "src" / "svgraph" / "cli.py").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")

    assert 'sys.argv[0] = "svgraph"' in main_source
    assert "from .cli import main" in main_source
    assert "raise SystemExit(main())" in main_source
    assert '"tmp/wheel-venv/bin/python -m svgraph"' in workflow
    assert 'actual_version="$($command --version)"' in workflow
    assert "tmp/wheel-venv/bin/python -m svgraph analyze examples/coverage.svg" in workflow
    assert "python -m svgraph --version" in readme
    assert "python -m svgraph --version" in migration
    assert 'version=f"svgraph {_package_version()}"' in cli_source
    assert 'version=f"%(prog)s {_package_version()}"' not in cli_source
    assert 'version("svgraph")' in cli_source
    assert 'version("drawingml-svg")' not in cli_source
    assert 'project.get("name") != "svgraph"' in cli_source
    assert "python -m drawingml_svg" not in readme
    assert "python -m drawingml_svg" not in migration


def test_cli_visible_commands_are_canonical_svgraph_commands() -> None:
    root = Path(__file__).resolve().parents[1]
    cli_source = (root / "src" / "svgraph" / "cli.py").read_text(encoding="utf-8")
    visible_commands = _literal_assignment(cli_source, "VISIBLE_COMMANDS")
    legacy_commands = _literal_assignment(cli_source, "LEGACY_COMMANDS")
    command_help = _literal_assignment(cli_source, "COMMAND_HELP")

    assert visible_commands == ("svg2dml", "dml2svg", "svg2pptx", "analyze", "svgraph", "svgraph-presentation")
    assert legacy_commands == ("ir", "pptxsvg")
    assert command_help == {
        "svg2dml": "convert SVG to a DrawingML shape fragment",
        "dml2svg": "convert a DrawingML shape fragment to SVG",
        "svg2pptx": "convert SVG/SVGraph presentation metadata to a PPTX package",
        "analyze": "report SVG conversion coverage and unsupported features",
        "svgraph": "emit the metadata-preserving SVGraph JSON document",
        "svgraph-presentation": "emit the SVGraph presentation/package JSON projection",
    }
    assert "ir" not in visible_commands
    assert "pptxsvg" not in visible_commands
    assert set(command_help) == set(visible_commands)


def test_readme_lists_all_legacy_console_compatibility_aliases() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (root / "README.md").read_text(encoding="utf-8")

    for executable in sorted(set(project["scripts"]) - {"svgraph"}):
        assert executable in readme


def test_docs_describe_legacy_executable_alias_deprecation_warnings() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    cli_source = (root / "src" / "svgraph" / "cli.py").read_text(encoding="utf-8")

    assert "emit deprecation warnings that point to the equivalent `svgraph ...` commands" in readme
    assert (
        "Retained legacy executable aliases emit deprecation warnings that point to their canonical SVGraph commands"
        in migration
    )
    for executable, replacement in {
        "drawingml-svg": "svgraph",
        "svg2dml": "svgraph svg2dml",
        "dml2svg": "svgraph dml2svg",
        "svg2pptx": "svgraph svg2pptx",
        "drawingml-svg-analyze": "svgraph analyze",
    }.items():
        assert f'"{executable}": "{replacement}"' in cli_source


def test_readme_cli_block_covers_every_visible_svgraph_command() -> None:
    root = Path(__file__).resolve().parents[1]
    cli_source = (root / "src" / "svgraph" / "cli.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    cli_section = readme.split("## CLI", maxsplit=1)[1].split("## PPTX smoke test", maxsplit=1)[0]
    visible_commands = _literal_assignment(cli_source, "VISIBLE_COMMANDS")

    documented_commands = {
        "svg2dml": "svgraph svg2dml input.svg -o shape.xml",
        "dml2svg": "svgraph dml2svg shape.xml -o shape.svg",
        "svg2pptx": "svgraph svg2pptx deck.svg -o deck.pptx",
        "analyze": "svgraph analyze input.svg",
        "svgraph": "svgraph input.svg",
        "svgraph-presentation": "svgraph svgraph-presentation input.svg",
    }

    assert set(documented_commands) == set(visible_commands)
    for command in visible_commands:
        assert documented_commands[command] in cli_section

    assert "python -m svgraph --version" in cli_section
    assert "drawingml-svg" not in cli_section.split("```bash", maxsplit=1)[1].split("```", maxsplit=1)[0]
    assert "pptxsvg" not in cli_section


def test_generated_distribution_metadata_preserves_legacy_compatibility_entry_points(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    egg_info = root / "src" / "svgraph.egg-info"
    build_dir = root / "build"
    had_egg_info = egg_info.exists()
    had_build_dir = build_dir.exists()

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(tmp_path)],
            check=True,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wheel_path = next(tmp_path.glob("svgraph-*.whl"))
        with zipfile.ZipFile(wheel_path) as wheel:
            wheel_names = set(wheel.namelist())
            metadata_name = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
            entry_points_name = next(name for name in wheel_names if name.endswith(".dist-info/entry_points.txt"))
            top_level_name = next(name for name in wheel_names if name.endswith(".dist-info/top_level.txt"))
            metadata = Parser().parsestr(wheel.read(metadata_name).decode("utf-8"))
            entry_point_text = wheel.read(entry_points_name).decode("utf-8")
            top_level_names = set(wheel.read(top_level_name).decode("utf-8").splitlines())
    finally:
        if not had_egg_info:
            shutil.rmtree(egg_info, ignore_errors=True)
        if not had_build_dir:
            shutil.rmtree(build_dir, ignore_errors=True)

    assert metadata["Name"] == "svgraph"
    assert metadata["Summary"] == (
        "Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, PresentationML/PPTX, "
        "and browser-only web editing."
    )
    assert metadata["Keywords"] == "drawingml,svg,svgraph,presentationml,ooxml,pptx,web,converter"
    assert metadata["License-Expression"] == "MIT"
    assert "LICENSE" in metadata.get_all("License-File")
    assert "Documentation, https://com-junkawasaki.github.io/svgraph/" in metadata.get_all("Project-URL")
    for name, target in scripts.items():
        assert f"{name} = {target}" in entry_point_text
    assert {"svgraph", "drawingml_svg"} <= top_level_names


def test_release_checklist_keeps_legacy_console_alias_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]

    assert "pyproject.toml` and `package.json` have the intended version" in release
    assert 'expected_version="svgraph $(' in release
    assert 'from importlib.metadata import version' in release
    assert 'print(version("svgraph"))' in release
    assert 'actual_version="$($command --version)"' in release
    assert 'test "$actual_version" = "$expected_version"' in release
    assert "assert drawingml_svg.converter.__all__ == svgraph.converter.__all__" in release
    assert "assert drawingml_svg.coverage.__all__ == svgraph.coverage.__all__" in release
    assert "assert drawingml_svg.pptx.__all__ == svgraph.pptx.__all__" in release
    assert "assert drawingml_svg.svgraph.__all__ == svgraph.model.__all__" in release
    assert '"tmp/release-venv/bin/python -m svgraph"' in release
    for executable in sorted(set(scripts) - {"svgraph"}):
        assert f'"tmp/release-venv/bin/{executable}"' in release
    for expected in [
        "tmp/release-legacy-analyze.err",
        "tmp/release-legacy-svgraph.err",
        "tmp/release-dml2svg.err",
        "executable 'drawingml-svg-analyze' is deprecated; use 'svgraph analyze'",
        "executable 'drawingml-svg' is deprecated; use 'svgraph'",
        "executable 'dml2svg' is deprecated; use 'svgraph dml2svg'",
    ]:
        assert expected in release


def test_release_checklist_verifies_public_svgraph_repo_identity() -> None:
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    for expected in [
        (
            "gh repo view com-junkawasaki/svgraph --json "
            "nameWithOwner,description,isPrivate,visibility,url,homepageUrl,defaultBranchRef,"
            "repositoryTopics,licenseInfo"
        ),
        "nameWithOwner: com-junkawasaki/svgraph",
        "description: SVG presentation graph toolkit for SVGraph, DrawingML, and PPTX conversion",
        "isPrivate: false",
        "visibility: PUBLIC",
        "url: https://github.com/com-junkawasaki/svgraph",
        "homepageUrl: https://com-junkawasaki.github.io/svgraph/",
        "defaultBranchRef.name: main",
        "repositoryTopics: drawingml, ooxml, pptx, presentationml, svg, svgraph, web-editor",
        "licenseInfo.key: mit",
        "licenseInfo.name: MIT License",
    ]:
        assert expected in release


def test_release_checklist_smokes_published_svgraph_pages_site() -> None:
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    for expected in [
        '"https://github.com/com-junkawasaki/svgraph"',
        '"https://github.com/com-junkawasaki/svgraph/issues"',
        '"https://github.com/com-junkawasaki/svgraph/actions/workflows/ci.yml"',
        "assert response.status == 200",
        'urlopen("https://com-junkawasaki.github.io/svgraph/", timeout=20)',
        'urlopen("https://com-junkawasaki.github.io/svgraph/app.js", timeout=20)',
        '"<title>SVGraph Editor</title>"',
        "'name=\"description\"'",
        '\'property="og:title" content="SVGraph Editor"\'',
        '\'property="og:url" content="https://com-junkawasaki.github.io/svgraph/"\'',
        '\'name="twitter:title" content="SVGraph Editor"\'',
        '"https://com-junkawasaki.github.io/svgraph/"',
        '\'<a class="btn" href="https://github.com/com-junkawasaki/svgraph">GitHub</a>\'',
        '\'<a class="btn" href="https://github.com/com-junkawasaki/svgraph/issues">Issues</a>\'',
        '"Download SVG"',
        '"Download SVGraph"',
        '"Download Sidecar"',
        '"downloadSVGraphBtn"',
        '"svgraph-source.svg"',
        '"svgraph-sidecar.json"',
        '"svgraph-web.pptx"',
        '"PPTX" + "SVG"',
        '"pptx" + "svg"',
        '"drawingml-" + "svg-web"',
        '"download" + "IrBtn"',
        '"download" + "Pptxsvg"',
        "assert expected in html",
        "assert expected in app_js",
        "assert forbidden not in html",
        "assert forbidden not in app_js",
    ]:
        assert expected in release


def test_release_and_ci_distribution_smoke_use_svgraph_artifact_names() -> None:
    root = Path(__file__).resolve().parents[1]
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for source in [release, workflow]:
        assert 'find src -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +' in source
        assert "rm -rf build tmp/dist" in source
    assert 'python -m pip install -e ".[dev]"' in release
    for source in [release, workflow]:
        assert "tmp/dist/svgraph-*.whl" in source
        assert "tmp/dist/svgraph-*.tar.gz" in source
        for wheel_entry in [
            "drawingml_svg/__init__.py",
            "drawingml_svg/cli.py",
            "drawingml_svg/converter.py",
            "drawingml_svg/coverage.py",
            "drawingml_svg/ir.py",
            "drawingml_svg/pptx.py",
            "drawingml_svg/py.typed",
            "drawingml_svg/svgraph.py",
            "svgraph/__init__.py",
            "svgraph/__main__.py",
            "svgraph/cli.py",
            "svgraph/converter.py",
            "svgraph/coverage.py",
            "svgraph/model.py",
            "svgraph/pptx.py",
            "svgraph/py.typed",
        ]:
            assert f'"{wheel_entry}"' in source
        assert "Name: svgraph" in source
        assert (
            "Summary: Small, dependency-free SVG presentation graph toolkit for SVGraph, DrawingML, "
            "PresentationML/PPTX, and browser-only web editing."
        ) in source
        assert "Keywords: drawingml,svg,svgraph,presentationml,ooxml,pptx,web,converter" in source
        assert "License-Expression: MIT" in source
        assert "License-File: LICENSE" in source
        assert "Project-URL: Homepage, https://github.com/com-junkawasaki/svgraph" in source
        assert "Project-URL: Repository, https://github.com/com-junkawasaki/svgraph" in source
        assert "Project-URL: Documentation, https://com-junkawasaki.github.io/svgraph/" in source
        assert "Project-URL: Issues, https://github.com/com-junkawasaki/svgraph/issues" in source
        assert 'pyproject["project"]["name"] == "svgraph"' in source
        assert 'pyproject["project"]["description"] == "Small, dependency-free SVG presentation graph toolkit' in source
        assert '"presentationml", "pptx", "web"' in source
        assert 'pyproject["project"]["urls"] == {' in source
        assert 'web_package["name"] == "@com-junkawasaki/svgraph"' in source
        assert 'web_package["version"] == pyproject["project"]["version"]' in source
        assert (
            'web_package["description"] == "Browser-only SVGraph editor and SVG to PresentationML/PPTX converter."'
        ) in source
        assert 'web_package["homepage"] == "https://com-junkawasaki.github.io/svgraph/"' in source
        assert 'web_package["private"] is False' in source
        assert '"registry": "https://npm.pkg.github.com"' in source
        assert '"access": "public"' in source
        assert 'web_package["license"] == "MIT"' in source
        assert 'web_lock["name"] == web_package["name"]' in source
        assert 'web_lock["packages"][""]["name"] == web_package["name"]' in source
        assert 'web_lock["packages"][""]["license"] == web_package["license"]' in source
        assert 'entry_points_name = next(name for name in wheel_names if name.endswith(".dist-info/entry_points.txt"))' in source
        assert 'top_level_name = next(name for name in wheel_names if name.endswith(".dist-info/top_level.txt"))' in source
        assert 'for name, target in pyproject["project"]["scripts"].items():' in source
        assert 'assert f"{name} = {target}" in entry_points' in source
        assert 'assert {"svgraph", "drawingml_svg"} <= top_level' in source
        assert "tmp/dist/drawingml_svg-" not in source
        assert "tmp/dist/drawingml-svg-" not in source

    assert "tmp/release-svgraph.json" in release
    assert "tmp/release-svgraph-presentation.json" in release
    assert "tmp/release-legacy-svgraph.json" in release
    assert "tmp/release-legacy-analyze.json" in release
    assert "tmp/wheel-svgraph.json" in workflow
    assert "tmp/wheel-svgraph-presentation.json" in workflow
    assert "tmp/wheel-legacy-svgraph.json" in workflow
    assert "tmp/wheel-legacy-analyze.json" in workflow
    for expected in [
        "tmp/wheel-legacy-analyze.err",
        "tmp/wheel-legacy-svgraph.err",
        "tmp/wheel-dml2svg.err",
        "tmp/wheel-svg2dml.err",
        "tmp/wheel-svg2pptx.err",
        "executable 'drawingml-svg-analyze' is deprecated; use 'svgraph analyze'",
        "executable 'drawingml-svg' is deprecated; use 'svgraph'",
        "executable 'dml2svg' is deprecated; use 'svgraph dml2svg'",
        "executable 'svg2dml' is deprecated; use 'svgraph svg2dml'",
        "executable 'svg2pptx' is deprecated; use 'svgraph svg2pptx'",
    ]:
        assert expected in workflow
    assert 'part_types = {part["kind"]: part["content_type"] for part in presentation["parts"]}' in workflow
    assert 'part["content_type"] == "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"' in workflow
    assert 'expected_version="svgraph $(tmp/wheel-venv/bin/python' in workflow
    assert 'from importlib.metadata import version' in workflow
    assert 'print(version("svgraph"))' in workflow
    assert "assert drawingml_svg.converter.__all__ == svgraph.converter.__all__" in workflow
    assert "assert drawingml_svg.coverage.__all__ == svgraph.coverage.__all__" in workflow
    assert "assert drawingml_svg.pptx.__all__ == svgraph.pptx.__all__" in workflow
    assert "assert drawingml_svg.svgraph.__all__ == svgraph.model.__all__" in workflow
    assert '"tmp/wheel-venv/bin/python -m svgraph"' in workflow
    for executable in ["svgraph", "drawingml-svg", "svg2dml", "svg2pptx", "dml2svg", "drawingml-svg-analyze"]:
        assert f'"tmp/wheel-venv/bin/{executable}"' in workflow
    assert 'actual_version="$($command --version)"' in workflow
    assert 'test "$actual_version" = "$expected_version"' in workflow


def test_release_checklist_rebuilds_and_packages_svgraph_web_editor() -> None:
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    for expected in [
        "npm ci",
        "npm run check:web",
        "npm run build:web",
        "npm run check:package",
        "git diff --exit-code docs/app.js",
        "git diff --exit-code docs/app.d.ts",
        'sdist_path = glob.glob("tmp/dist/svgraph-*.tar.gz")[0]',
        '"README.md"',
        '"LICENSE"',
        '"CODE_OF_CONDUCT.md"',
        '"CHANGELOG.md"',
        '"CONTRIBUTING.md"',
        '"MIGRATION.md"',
        '"RELEASE.md"',
        '"SECURITY.md"',
        '"package.json"',
        '"package-lock.json"',
        '"tsconfig.web.json"',
        '"docs/.nojekyll"',
        '"docs/adr/0001-svgraph.md"',
        '"docs/index.html"',
        '"docs/app.js"',
        '"docs/svgraph-web-editor.md"',
        '"examples/__init__.py"',
        '"examples/complex.svg"',
        '"examples/coverage.svg"',
        '"examples/make_pptx.py"',
        '"examples/sample.svg"',
        '"examples/svgraph.svg"',
        '"web/app.ts"',
        '"src/drawingml_svg/__init__.py"',
        '"src/drawingml_svg/cli.py"',
        '"src/drawingml_svg/converter.py"',
        '"src/drawingml_svg/coverage.py"',
        '"src/drawingml_svg/ir.py"',
        '"src/drawingml_svg/pptx.py"',
        '"src/drawingml_svg/py.typed"',
        '"src/drawingml_svg/svgraph.py"',
        '"src/svgraph/__init__.py"',
        '"src/svgraph/__main__.py"',
        '"src/svgraph/cli.py"',
        '"src/svgraph/converter.py"',
        '"src/svgraph/coverage.py"',
        '"src/svgraph/model.py"',
        '"src/svgraph/pptx.py"',
        '"src/svgraph/py.typed"',
        'assert f"{root}/{expected}" in names',
    ]:
        assert expected in release


def test_release_checklist_smokes_canonical_svgraph_pptx_export() -> None:
    root = Path(__file__).resolve().parents[1]
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "tmp/release-venv/bin/svgraph svg2dml examples/sample.svg -o tmp/release-smoke.xml" in release
    assert "tmp/release-venv/bin/dml2svg tmp/release-smoke.xml -o tmp/release-smoke.svg" in release
    assert "tmp/release-venv/bin/svgraph svg2pptx examples/sample.svg -o tmp/release-smoke.pptx" in release
    assert "python -m zipfile --test tmp/release-smoke.pptx" in release
    assert "tmp/release-venv/bin/svg2pptx examples/" not in release
    for source in [release, workflow]:
        assert "from svgraph.pptx import svg_to_pptx_bytes" in source
        assert '"ppt/slideMasters/slideMaster2.xml" in names' in source
        assert '"ppt/slideLayouts/slideLayout2.xml" in names' in source
        assert 'Target="../slideLayouts/slideLayout2.xml"' in source


def test_release_checklist_smokes_all_canonical_svgraph_report_commands() -> None:
    root = Path(__file__).resolve().parents[1]
    cli_source = (root / "src" / "svgraph" / "cli.py").read_text(encoding="utf-8")
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    visible_commands = _literal_assignment(cli_source, "VISIBLE_COMMANDS")

    expected_smokes = {
        "analyze": "tmp/release-venv/bin/svgraph analyze examples/coverage.svg",
        "svgraph": "tmp/release-venv/bin/svgraph examples/svgraph.svg > tmp/release-svgraph.json",
        "svgraph-presentation": (
            "tmp/release-venv/bin/svgraph svgraph-presentation examples/svgraph.svg"
            " > tmp/release-svgraph-presentation.json"
        ),
    }

    assert set(expected_smokes) <= set(visible_commands)
    for smoke in expected_smokes.values():
        assert smoke in release

    for expected in [
        'presentation = json.loads(Path("tmp/release-svgraph-presentation.json").read_text(encoding="utf-8"))',
        'part_types = {part["kind"]: part["content_type"] for part in presentation["parts"]}',
        'part_types["presentation"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"',
        'part_types["slide-master"] == "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"',
        'part_types["slide-layout"] == "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"',
        'part_types["theme"] == "application/vnd.openxmlformats-officedocument.theme+xml"',
        'part["content_type"] == "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"',
    ]:
        assert expected in release

    assert '"tmp/release-venv/bin/svgraph"' in release
    assert 'actual_version="$($command --version)"' in release
    assert '"tmp/release-venv/bin/python -m svgraph"' in release


def test_contributor_checks_use_canonical_svgraph_commands_and_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pr_template = (root / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

    for source in [contributing, pr_template]:
        assert "PYTHONPATH=src python -m pytest -q" in source
        assert "npm ci" in source
        assert "npm run check:web" in source
        assert "npm run build:web" in source
        assert "npm run check:package" in source
        assert "PYTHONPATH=src python -m svgraph analyze examples/coverage.svg" in source
        assert "PYTHONPATH=src python -m svgraph svgraph examples/svgraph.svg > tmp/svgraph.json" in source
        assert (
            "PYTHONPATH=src python -m svgraph svgraph-presentation examples/svgraph.svg > tmp/svgraph-presentation.json"
            in source
        )
        assert "tmp/svgraph-coverage.pptx" in source
        assert "python -m zipfile --test tmp/svgraph-coverage.pptx" in source
        assert "git diff --exit-code docs/app.js" in source
        assert "git diff --exit-code docs/app.d.ts" in source
        assert "python -m svgraph.cli" not in source
        assert "python -m drawingml_svg" not in source
        assert "tmp/drawingml-svg-coverage.pptx" not in source


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


def test_legacy_import_allowlist_is_limited_to_migration_and_distribution_smoke() -> None:
    assert ALLOWED_LEGACY_IMPORT_SURFACES == {
        ".github/workflows/ci.yml",
        "RELEASE.md",
        "tests/test_migration.py",
        "tests/test_svgraph.py",
    }
    assert LEGACY_IMPORT_PATTERNS == (
        "from drawingml_svg",
        "import drawingml_svg",
        "python -m drawingml_svg.cli",
        "drawingml_svg.cli",
    )


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


def test_pages_workflow_deploys_svgraph_docs_site() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    html = (root / "docs" / "index.html").read_text(encoding="utf-8")

    assert "name: Pages" in workflow
    assert 'branches: ["main"]' in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "uses: actions/configure-pages@v6" in workflow
    assert "uses: actions/upload-pages-artifact@v5" in workflow
    assert "path: docs" in workflow
    assert "uses: actions/deploy-pages@v5" in workflow
    assert "actions/upload-pages-artifact@v4" not in workflow
    assert "actions/deploy-pages@v4" not in workflow
    assert (root / "docs" / ".nojekyll").is_file()
    assert "<title>SVGraph Editor</title>" in html
    assert 'accept=".svg,.xml,.json,image/svg+xml,application/xml,text/xml,application/json"' in html
    assert (
        'content="Browser-only SVGraph editor for converting SVG presentation graphs into editable '
        'PresentationML and PPTX."'
    ) in html
    assert '<link rel="canonical" href="https://com-junkawasaki.github.io/svgraph/" />' in html
    assert '<meta property="og:title" content="SVGraph Editor" />' in html
    assert '<meta property="og:url" content="https://com-junkawasaki.github.io/svgraph/" />' in html
    assert '<meta name="twitter:title" content="SVGraph Editor" />' in html
    assert '<a class="btn" href="https://github.com/com-junkawasaki/svgraph">GitHub</a>' in html
    assert '<a class="btn" href="https://github.com/com-junkawasaki/svgraph/issues">Issues</a>' in html
    assert "https://com-junkawasaki.github.io/drawingml-svg" not in workflow + html


def test_npm_publish_workflow_targets_github_packages() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "npm-publish.yml").read_text(encoding="utf-8")

    assert "name: Publish npm package" in workflow
    assert "packages: write" in workflow
    assert 'registry-url: "https://npm.pkg.github.com"' in workflow
    assert 'scope: "@com-junkawasaki"' in workflow
    assert "npm run check:web" in workflow
    assert "npm run build:web" in workflow
    assert "npm pack --dry-run" in workflow
    assert "npm publish" in workflow
    assert "NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow


def test_web_source_and_package_metadata_use_svgraph_naming() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_json = (root / "package.json").read_text(encoding="utf-8")
    package_lock = (root / "package-lock.json").read_text(encoding="utf-8")
    package_metadata = json.loads(package_json)
    lock_metadata = json.loads(package_lock)
    html = (root / "docs" / "index.html").read_text(encoding="utf-8")
    source = (root / "web" / "app.ts").read_text(encoding="utf-8")
    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")
    app_dts = (root / "docs" / "app.d.ts").read_text(encoding="utf-8")

    assert '"name": "@com-junkawasaki/svgraph"' in package_json
    assert '"name": "@com-junkawasaki/svgraph"' in package_lock
    assert package_metadata["version"] == pyproject["project"]["version"]
    assert lock_metadata["version"] == package_metadata["version"]
    assert lock_metadata["packages"][""]["version"] == package_metadata["version"]
    assert package_metadata["description"] == "Browser-only SVGraph editor and SVG to PresentationML/PPTX converter."
    assert {"svg", "svgraph", "presentationml", "pptx", "web"} <= set(package_metadata["keywords"])
    assert package_metadata["homepage"] == "https://com-junkawasaki.github.io/svgraph/"
    assert package_metadata["repository"] == {
        "type": "git",
        "url": "git+https://github.com/com-junkawasaki/svgraph.git",
    }
    assert package_metadata["bugs"] == {"url": "https://github.com/com-junkawasaki/svgraph/issues"}
    assert package_metadata["main"] == "./docs/app.js"
    assert package_metadata["types"] == "./docs/app.d.ts"
    assert package_metadata["exports"] == {
        ".": {
            "types": "./docs/app.d.ts",
            "default": "./docs/app.js",
        },
        "./web/app.ts": "./web/app.ts",
    }
    assert package_metadata["bin"] == {
        "svgraph": "bin/svgraph.mjs",
        "svgraph-browser": "bin/svgraph.mjs",
    }
    assert "bin" in package_metadata["files"]
    assert "examples/freeform.dml" in package_metadata["files"]
    assert "examples/group.dml" in package_metadata["files"]
    assert "examples/picture.dml" in package_metadata["files"]
    assert "examples/preset.dml" in package_metadata["files"]
    assert "examples/sample.svg" in package_metadata["files"]
    assert "@xmldom/xmldom" in package_metadata["dependencies"]
    assert package_metadata["private"] is False
    assert package_metadata["publishConfig"] == {
        "registry": "https://npm.pkg.github.com",
        "access": "public",
    }
    assert package_metadata["license"] == "MIT"
    assert lock_metadata["packages"][""]["license"] == package_metadata["license"]
    assert "<title>SVGraph Editor</title>" in html
    assert 'id="downloadSvgBtn"' in html
    assert 'id="downloadSVGraphBtn"' in html
    assert 'id="downloadSidecarBtn"' in html
    assert 'id="downloadDrawingMlBtn"' in html
    assert 'id="undoBtn"' in html
    assert 'id="redoBtn"' in html
    assert 'id="clearSavedBtn"' in html
    assert 'accept=".svg,.xml,.json,image/svg+xml,application/xml,text/xml,application/json"' in html
    assert "Open SVG/XML" in html
    assert 'mustElement<HTMLButtonElement>("downloadSvgBtn")' in source
    assert 'mustElement<HTMLButtonElement>("downloadSVGraphBtn")' in source
    assert 'mustElement<HTMLButtonElement>("downloadSidecarBtn")' in source
    assert 'mustElement<HTMLButtonElement>("downloadDrawingMlBtn")' in source
    assert 'mustElement<HTMLButtonElement>("undoBtn")' in source
    assert 'mustElement<HTMLButtonElement>("redoBtn")' in source
    assert 'mustElement<HTMLButtonElement>("clearSavedBtn")' in source
    assert "export function buildSVGraph" in source
    assert "export function buildSVGraphSidecar" in source
    assert "export function svgToDrawingMl" in source
    assert "export function drawingMlToSvg" in source
    assert "export function svgToPptx" in source
    assert "export function buildSVGraphAssistantPrompt" in source
    assert "export function parseAssistantPatchProposal" in source
    assert "export function validateAssistantPatch" in source
    assert "export function assistantPatchDiff" in source
    assert "export function applyAssistantPatch" in source
    assert "export function initSVGraphEditor" in source
    assert "new Worker(URL.createObjectURL" in source
    assert '"https://cdn.jsdelivr.net/npm/@huggingface/transformers"' in source
    assert '"webgpu" | "wasm" | "disabled"' in source
    assert 'document.getElementById("source")' in source
    for expected in [
        "export type SVGraphDocument",
        "export type SVGraphPresentationProjection",
        "export type SVGraphSidecar",
        "export type SvgCoverage",
        "export type AssistantPatchProposal",
        "export type AssistantBackendPolicy",
        "export declare function buildSVGraph",
        "export declare function buildSVGraphSidecar",
        "export declare function svgToDrawingMl",
        "export declare function drawingMlToSvg",
        "export declare function svgToPptx",
        "export declare function buildSVGraphAssistantPrompt",
        "export declare function parseAssistantPatchProposal",
        "export declare function validateAssistantPatch",
        "export declare function assistantPatchDiff",
        "export declare function applyAssistantPatch",
        "export declare function initSVGraphEditor",
    ]:
        assert expected in app_dts
    for generated in [source, app_js]:
        assert 'downloadBlob("svgraph-source.svg"' in generated
        assert "function setSourceValue" in generated
        assert "function recordManualSourceEdit" in generated
        assert "function undoSourceEdit" in generated
        assert "function redoSourceEdit" in generated
        assert "function updateHistoryButtons" in generated
        assert "storageStatus" in generated
        assert "function setStorageStatus" in generated
        assert "function persistSourceDocument" in generated
        assert "function openDocumentDb" in generated
        assert "function saveSourceDocument" in generated
        assert "function loadSourceDocument" in generated
        assert "function clearSavedSourceDocument" in generated
        assert '"svgraph-documents"' in generated
        assert '"active-svg"' in generated
        assert 'downloadText("svgraph.json"' in generated
        assert 'downloadText("svgraph-sidecar.json"' in generated
        assert 'kind: "svgraph-sidecar"' in generated
        assert "source_svg:" in generated
        assert "function sourceFromOpenedFile" in generated
        assert 'obj.kind === "svgraph-sidecar"' in generated
        assert "Open failed:" in generated
        assert "drawingMlToSvg(text)" in generated
        assert 'fileInput.value = ""' in generated
        assert "function buildSVGraphSidecar" in generated
        assert 'downloadBlob("svgraph-drawingml.xml"' in generated
        assert "function svgToDrawingMl" in generated
        assert "function drawingMlToSvg" in generated
        assert "function dmlShapeToSvg" in generated
        assert "function dmlPresetPoints" in generated
        assert "function regularPolygonPoints" in generated
        assert "function regularStarPoints" in generated
        assert "function ellipseArcPoints" in generated
        assert "function dmlCustomGeometryToSvg" in generated
        assert "function dmlCustomPoints" in generated
        assert "function dmlConnectorToSvg" in generated
        assert "function dmlPictureToSvg" in generated
        assert "function dmlBlipAlpha" in generated
        assert "function dmlTableFrameToSvg" in generated
        assert "function dmlTableColumns" in generated
        assert "function dmlSvgItemsWalk" in generated
        assert "function dmlGroupMatrix" in generated
        assert "function dmlXfrmTransformAttr" in generated
        assert "function dmlXfrmTransformBounds" in generated
        assert "function directChildrenByLocal" in generated
        assert 'data-kind="table"' in generated
        assert 'data-kind="cell"' in generated
        assert "gridSpan" in generated
        assert "rowSpan" in generated
        assert "hMerge" in generated
        assert "vMerge" in generated
        assert "function buildDrawingMlFragment" in generated
        assert 'value("text-decoration-style")' in generated
        assert "underlineStyle: underlineStyle(textStyle)" in generated
        assert "underlineStyle: underlineStyle(runStyle)" in generated
        assert "text-decoration-style:dashed" in generated
        assert "text-decoration-style:wavy" in generated
        assert "text-decoration-style:inherit" in generated
        assert "text-decoration-color:inherit" in generated
        assert "text-decoration-thickness:inherit" in generated
        assert "resolvedCascadedDeclarations(element, css, style)" in generated
        assert "function cssInitialValue" in generated
        assert 'id="initial-reset-rect"' in generated
        assert 'id="unset-reset-text"' in generated
        assert "const coverageTextLayoutAttributes" in generated
        assert "function subtreeHasVisibleText" in generated
        assert "coverageTextLayoutAttributes.has(name)" in generated
        assert "function coverageAttributeHasNoEffect" in generated
        assert "function coverageElementIsIgnored" in generated
        assert "function coverageHasNonRenderingGeometry" in generated
        assert "function coverageHasNoVisiblePaint" in generated
        assert "function coverageSubtreeHasVisibleRendering" in generated
        assert "function coverageUseReferenceIsSupported" in generated
        assert "function coverageReferencedSubtreeIsSupported" in generated
        assert "function hrefValue" in generated
        assert 'getAttributeNS("http://www.w3.org/1999/xlink", "href")' in generated
        assert "const href = hrefValue(element)" in generated
        assert "function simpleElementStyle" in generated
        assert 'style.display === "none"' in generated
        assert 'style.fillAlpha !== 0' in generated
        assert 'value("fill-opacity")' in generated
        assert 'const inheritedStopColor = gradientDeclarations["stop-color"]' in generated
        assert 'const inheritedStopOpacity = gradientDeclarations["stop-opacity"]' in generated
        assert "gradientStyle" in generated
        assert "parseCssColor(gradientColor, style)" in generated
        assert "paintServerColor(ref.id, refs, style, new Set(), css)" in generated
        assert "resolvedCascadedDeclarations(stop, css, gradientStyle)" in generated
        assert "const stopOpacityAlpha = parseAlpha(stopOpacity)" in generated
        assert "combinedAlpha(stopOpacityAlpha, colorAlpha) !== 0" in generated
        assert "textRuns(element, paintStyle, viewport, textMetricScale, css, refs)" in generated
        assert "computedStyle(tspan, inheritedStyle, css, refs, viewport)" in generated
        assert "const declarations = resolvedCascadedDeclarations(element, css, paintStyle)" in generated
        assert "cascadedGeom(element, declarations, \"width\", \"x\", viewport)" in generated
        assert "cascadedGeom(element, declarations, \"cx\", \"x\", viewport)" in generated
        assert "cascadedGeom(element, declarations, \"x1\", \"x\", viewport)" in generated
        assert "imagePreserveAspectRatioRect(" in generated
        assert "function dataImageBytes" in generated
        assert "function base64PayloadBytes" in generated
        assert "const data = base64PayloadBytes(payload)" in generated
        assert "return _match" in generated
        assert "function jpegDimensions" in generated
        assert "while (index + 9 <= bytes.length)" in generated
        assert "marker >= 0xd0 && marker <= 0xd7" in generated
        assert "cascadedGeom(element, declarations, \"height\", \"y\", viewport)" in generated
        assert "css-image-frame" in generated
        assert 'style="x:90px;y:465px;width:360px;height:90px"' in generated
        assert "shapesFromForeignObject(element, ownMatrix, nextId, ownStyle, css, childViewport)" in generated
        assert 'id="cell-width-html-table"' in generated
        assert "function htmlTableGrid" in generated
        assert "htmlTableGrid(item) != null" in generated
        assert "placements.some((item) => item.row + item.rowSpan > rows.length)" in generated
        assert "function htmlTableFirstRowColumnWidths" in generated
        assert "function htmlTableSizes" in generated
        assert "return htmlTableSizes(explicit, rows.length, height)" in generated
        assert 'htmlStyleValue(cell, "width") ?? cell.getAttribute("width")' in generated
        assert 'htmlSpan(col, "span")' in generated
        assert "function htmlFirstColorFill" in generated
        assert "background:padding-box #ffffff" in generated
        assert "padding:calc(0.5px + 0.5px)" in generated
        assert "border:hidden 2px #94a3b8" in generated
        assert "function htmlBorderIsNone" in generated
        assert '["none", "hidden"].includes' in generated
        assert '<strong style="font-weight:400">plain</strong>' in generated
        assert "text-transform:lowercase" in generated
        assert "text-transform:uppercase" in generated
        assert "word-spacing:6px" in generated
        assert "function htmlFontWeightIsNormal" in generated
        assert "function htmlFontStyleIsNormal" in generated
        assert 'const textTransform = value("text-transform")' in generated
        assert "next.textTransform = normalizeTextTransform(textTransform)" in generated
        assert "const transformed = applyTextTransform(text, style.textTransform)" in generated
        assert "letterSpacing: effectiveLetterSpacing(style, transformed, fontSize)" in generated
        assert "const parts = cssValueTokens(value).slice(0, 4)" in generated
        assert "const tokens = cssValueTokens(value).slice(0, 4)" in generated
        assert "const parts = cssValueTokens(value)" in generated
        assert "function htmlTableFitSpacing" in generated
        assert "Math.min(spacing, size / 3)" in generated
        assert 'trimmed === "thick"' in generated
        assert "coverageHasNonRenderingGeometry(element, tag, style, css, viewport)" in generated
        assert "styleTransformMatrix(element, ownStyle, currentViewport, css)" in generated
        assert "elementReferenceBox(element, viewport, css, inheritedStyle)" in generated
        assert "pathLengthScale(paintStyle, element, \"line\", viewport, null, css, paintStyle)" in generated
        assert "renderedSvgViewport(element, currentViewport, css, ownStyle)" in generated
        assert "useViewport(ref, element, currentViewport, css, ownStyle)" in generated
        assert "rectClipBounds(rawShape, ownStyle, refs, ownMatrix, childViewport, css)" in generated
        assert "bboxCascadedGeom" in generated
        assert "function normalizedClipPathUnits" in generated
        assert "clip.getAttribute(\"clipPathUnits\")" in generated
        assert 'clipPathUnits=" OBJECTBOUNDINGBOX "' in generated
        assert "computedStyle(clip, style, css, refs, viewport)" in generated
        assert "computedStyle(rect, clipStyle, css, refs, viewport)" in generated
        assert "transformMatrix(rectStyle.transform ?? rect.getAttribute(\"transform\"))" in generated
        assert "const ownContainerClip = rectClipBounds(null, ownStyle, refs, ownMatrix, childViewport, css)" in generated
        assert "childClip = combineClips(childClip, ownContainerClip)" in generated
        assert "walk(ref, useMatrix, ownStyle, new Set([...refStack, refId]), refViewport, childClip)" in generated
        assert "function lineXfrmAttrs" in generated
        assert 'shape.x2 < shape.x1 ? \' flipH="1"\'' in generated
        assert 'shape.y2 < shape.y1 ? \' flipV="1"\'' in generated
        assert 'spXml(shape.id, shape.name, x, y, width, height, "line"' in generated
        assert "function normalizeStrokeWidth" in generated
        assert "normalizeStrokeWidth(strokeWidth, next.fontSize ?? rootFontSize, next.strokeWidth ?? 1)" in generated
        assert "stroke-width:-2" in generated
        assert "function rectRadius" in generated
        assert "optionalNonnegativeCascadedGeom" in generated
        assert 'rx="-3" ry="8"' in generated
        assert "function normalizeMarkerReference" in generated
        assert "markerRefIsArrowLike(value, refs)" in generated
        assert "function markerAttributeIsSupportedOrNoop" in generated
        assert "function subtreeMarkerAttributeIsSupported" in generated
        assert "function subtreeMarkerMidHasNoEffect" in generated
        assert 'id="ignored-marker-mid"' in generated
        assert 'id="dot-marker"' in generated
        assert 'id="non-arrow-marker-line"' in generated
        assert "css-use-frame" in generated
        assert "css-nested-frame" in generated
        assert "svgTextPosition(element, viewport, css, paintStyle)" in generated
        assert "optionalCascadedGeom" in generated
        assert "firstOptionalCascadedGeom" in generated
        assert "tspanStartsNewLine(tspan, viewport, css, inheritedStyle)" in generated
        assert "textRotation(element, textStyle, css, refs, viewport)" in generated
        assert "function zeroAngle" in generated
        assert "function textHasNoKerningPairs" in generated
        assert 'name === "font-kerning"' in generated
        assert 'name === "glyph-orientation-horizontal"' in generated
        assert 'name === "unicode-bidi"' in generated
        assert 'name === "writing-mode"' in generated
        assert "function textDecorationShorthandIsSupported" in generated
        assert "function textDecorationLineIsSupportedOrNoop" in generated
        assert "function textDecorationLineTokensAreSupportedOrNoop" in generated
        assert "function textDecorationStyleIsSupportedOrNoop" in generated
        assert "function textDecorationColorHasNoEffect" in generated
        assert "function textDecorationThicknessHasNoEffect" in generated
        assert "function hasOnlyVisibleUnderline" in generated
        assert "function transformOriginIsSupportedOrNoop" in generated
        assert 'id="ignored-transform-origin"' in generated
        assert "function textLengthIsSupported" in generated
        assert 'value.includes("%") || style.letterSpacing != null' in generated
        assert 'normalizeLengthAdjust(lengthAdjustValue) == null' in generated
        assert "function wordSpacingHasNoEffect" in generated
        assert "function wordSpacingIsSupported" in generated
        assert "style.letterSpacing != null || style.textLength != null" in generated
        assert "function renderingQualityHintHasNoEffect" in generated
        assert '"crisp-edges"' in generated
        assert '"optimizelegibility"' in generated
        assert '"pixelated"' in generated
        assert "function paintOrderHasNoEffect" in generated
        assert "function hasVisibleMarker" in generated
        assert '"fill stroke markers"' in generated
        assert 'paint-order="fill stroke markers"' in generated
        assert "strokeLineCapSource" in generated
        assert "strokeLineJoinSource" in generated
        assert "function subtreeHasUnsupportedStrokeLineEnum" in generated
        assert "function strokeLineEnumIsUnsupported" in generated
        assert 'id="ignored-stroke-enum"' in generated
        assert 'stroke-linejoin="arcs"' in generated
        assert "function isolationIsRedundantWithBlend" in generated
        assert "function subtreeHasBlend" in generated
        assert 'id="blend-isolation-dedupe"' in generated
        assert 'id="hidden-blend-effect"' in generated
        assert "function subtreeHasVisibleFill" in generated
        assert "function hasVisibleFill" in generated
        assert "function clipRuleHasNoEffect" in generated
        assert 'id="ignored-clip-rule"' in generated
        assert 'id="ignored-fill-rule"' in generated
        assert "function strokeDashoffsetHasNoEffect" in generated
        assert "function strokeDashoffsetIsSupported" in generated
        assert "function dashPatternPeriod" in generated
        assert "function pathLengthIsSupportedOrNoop" in generated
        assert 'id="ignored-path-length"' in generated
        assert "function overflowIsSupportedOrNoop" in generated
        assert "function opacityIsSupportedOrNoop" in generated
        assert 'id="ignored-group-opacity"' in generated
        assert "visibleRenderingDescendantCount(element, style, refs, css, viewport, 2) < 2" in generated
        assert "function preserveAspectRatioIsSupportedOrNoop" in generated
        assert 'localName(ref) === "svg" || localName(ref) === "symbol"' in generated
        assert "dataImageDimensions(hrefValue(element)) != null" in generated
        assert "function vectorEffectIsSupportedOrNoop" in generated
        assert "function subtreeHasVisibleStroke" in generated
        assert 'id="ignored-vector-effect"' in generated
        assert 'id="visible-overflow"' in generated
        assert 'id="hidden-overflow-empty"' in generated
        assert 'id="length-glyphs-text"' in generated
        assert 'lengthAdjust=" SPACINGANDGLYPHS "' in generated
        assert 'id="word-spacing-text"' in generated
        assert 'id="inherited-word-spacing"' in generated
        assert 'id="hidden-text-layout"' in generated
        assert "coverageHasNoVisiblePaint(element, tag, style, refs, css, viewport, refStack)" in generated
        assert 'text-rendering="optimizeLegibility"' in generated
        assert 'shape-rendering="crisp-edges"' in generated
        assert 'image-rendering="pixelated"' in generated
        assert 'color-rendering="optimizeQuality"' in generated
        assert 'decoration.includes("wavy")' in generated
        assert 'name === "text-decoration-style"' in generated
        assert "textDecorationStyleTokens.has(normalized)" in generated
        assert 'id="first-tspan-baseline"' in generated
        assert "function firstPositionedTspanBaselineIsSupported" in generated
        assert "element.previousElementSibling" in generated
        assert 'id="unsupported-tspan-anchor"' in generated
        assert "function inspectCoverageTspanRunAttributes" in generated
        assert 'addCoverageCount(stats.unsupported_attributes, "text-anchor")' in generated
        assert "function tspanPositionIsSupportedOrNoop" in generated
        assert 'id="empty-gradient"' in generated
        assert 'id="empty-gradient-fill"' in generated
        assert 'id="missing-base-gradient"' in generated
        assert 'id="missing-base-gradient-fill"' in generated
        assert "function hasHrefAttribute" in generated
        assert "function inspectReferencedPaintServerAttributes" in generated
        assert 'addCoverageCount(stats.unsupported_attributes, "href")' in generated
        assert 'addCoverageCount(stats.unsupported_attributes, "gradientTransform")' in generated
        assert "function subtreeReferencesPaintServer" in generated
        assert 'id="unsupported-clip-target"' in generated
        assert "function clipPathIsSupportedOrNoop" in generated
        assert "function clipPathTargetIsSupported" in generated
        assert "function subtreeClipPathIsSupported" in generated
        assert 'id="hidden-filtered-use-target"' in generated
        assert 'id="ignored-filtered-use"' in generated
        assert "function coverageHasUnresolvedPaintServer" in generated
        assert "const coverageRenderingElements" in generated
        assert 'id="ignored-empty-filter"' in generated
        unsupported_attributes = generated.split("const coverageUnsupportedAttributes", 1)[1].split(
            "const coverageSupportedPathCommands",
            1,
        )[0]
        for attr in [
            "letter-spacing",
            "opacity",
            "overflow",
            "pathLength",
            "rotate",
            "stroke-dashoffset",
            "stroke-linecap",
            "stroke-linejoin",
            "textLength",
            "text-decoration-color",
            "text-decoration-line",
            "text-decoration-thickness",
            "text-transform",
            "transform-origin",
            "vector-effect",
            "word-spacing",
        ]:
            assert f'"{attr}"' in unsupported_attributes
        assert 'return \' u="wavy"\'' in generated
        assert 'case "text-decoration-style":' in generated
        assert 'case "text-decoration-color":' in generated
        assert 'case "text-decoration-thickness":' in generated
        assert "const assistantAllowedOps" in generated
        assert "function assistantPatchProposal" in generated
        assert "function buildSVGraphAssistantPrompt" in generated
        assert "function parseAssistantPatchProposal" in generated
        assert "function createAssistantWorker" in generated
        assert "function requestAssistantPatch" in generated
        assert "function validateAssistantPatch" in generated
        assert "function assistantPatchDiff" in generated
        assert "function assistantDataDiff" in generated
        assert "function applyAssistantPatch" in generated
        assert "function applyAssistantPatchOp" in generated
        assert "function elementByNodeId" in generated
        assert "assistantBackendPolicy" in generated
        assert "runAssistantLlmBtn" in generated
        assert "resetAssistantProposalBtn" in generated
        assert "Local Web LLM suggestions run in a browser worker" in generated
        assert "Transformers.js runtime" in generated
        assert "onnx-community/gemma-4-e2b-it-ONNX" in generated
        assert "applyAssistantPatchBtn" in generated
        assert "patchValidation" in generated
        assert "patchDiff" in generated
        assert "patchProposal" in generated
        assert 'downloadText("svgraph-presentation.json"' in generated
        assert 'downloadBlob("svgraph-web.pptx"' in generated

    combined = "\n".join([package_json, package_lock, html, source, app_js])
    assert "drawingml-" + "svg-web" not in combined
    assert "PPTXSVG" not in combined
    assert "presentation IR" not in combined
    assert "downloadIrBtn" not in combined
    assert "downloadSvgraphBtn" not in combined
    assert "downloadPptxsvg" not in combined


def test_web_runtime_accepts_canonical_svgraph_presentation_metadata_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "app.ts").read_text(encoding="utf-8")
    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")

    for generated in [source, app_js]:
        assert "rootMeta.slideSize || rootMeta.slide_size" in generated
        assert "rootMeta.textStyles || rootMeta.text_styles" in generated
        assert "Array.isArray(metadataStyles)" in generated
        assert "text-style-${index + 1}" in generated
        assert "style_id: String(obj.id || role)" in generated
        assert "content_type:" in generated
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml" in generated
        assert "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml" in generated
        assert "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml" in generated
        assert "application/vnd.openxmlformats-officedocument.presentationml.slide+xml" in generated
        assert "part_name:" in generated
        assert '"/customXml/item1.xml"' in generated
        assert 'kind: "custom-xml"' in generated
        assert "const masters = templates(nodes, rootMeta.masters ?? null, \"slide-master\")" in generated
        assert "const masterParts = (masters.length ? masters : [null]).map" in generated
        assert "presentation.masters.length" in generated
        assert "presentation.layouts.length" in generated
        assert "state.presentation.parts.map" in generated
        assert "part.content_type" in generated
        assert "contentTypes(slideXmls.length, masterCount, layoutCount, true)" in generated
        assert "presentationRels(slideXmls.length, masterCount)" in generated
        assert "slideLayoutRel(layoutIndex)" in generated
        assert "slideMaster(presentation.text_styles)" in generated
        assert "function textStyleXml" in generated
        assert "Aptos Display" in generated
        assert "writePptx(slideXmls, svgraph.presentation, svgText)" in generated
        assert '"customXml/item1.xml": svgraphPresentationSidecar(presentation, sourceSvg)' in generated
        assert "function svgraphPresentationSidecar" in generated
        assert "source_svg: sourceSvg" in generated
        assert "relationships/customXml" in generated


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
    assert tsconfig["compilerOptions"]["declaration"] is True
    assert tsconfig["include"] == ["web/**/*.ts"]
    assert '<script type="module" src="./app.js"></script>' in html
    assert 'version: "0.3-svgraph-web-ts"' in app_js
    assert 'downloadBlob("svgraph-source.svg"' in app_js
    assert 'downloadBlob("svgraph-web.pptx"' in app_js
    assert 'downloadBlob("svgraph-drawingml.xml"' in app_js


def test_browser_only_svgraph_build_is_documented_and_ci_guarded() -> None:
    root = Path(__file__).resolve().parents[1]
    package_metadata = json.loads((root / "package.json").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    npm_cli = (root / "bin" / "svgraph.mjs").read_text(encoding="utf-8")

    assert "`web/app.ts` builds SVGraph" in readme
    assert "`docs/app.js` is the compiled Pages artifact." in readme
    assert "Python or server APIs" in readme
    assert "DrawingML-to-SVG import for basic shape, common preset polygon/arc/flowchart/bevel/snip/symbol/star/arrow/callout/ribbon/action shape, custom geometry/freeform, grouped shape, connector, picture, and native table fragments" in readme
    assert "underline/strike decoration including underline style, color, and thickness" in readme
    assert "npm ci" in readme
    assert "npm run check:web" in readme
    assert "npm run build:web" in readme
    assert "npm run check:package" in readme
    assert 'from "@com-junkawasaki/svgraph";' in readme
    assert "drawingMlToSvg" in readme
    assert "buildSVGraphAssistantPrompt" in readme
    assert "validateAssistantPatch" in readme
    assert "Browser Assistant can run a local Transformers.js worker" in readme
    assert package_metadata["scripts"]["build:web"] == "tsc -p tsconfig.web.json"
    assert package_metadata["scripts"]["check:web"] == "tsc -p tsconfig.web.json --noEmit"
    assert "check:package" in package_metadata["scripts"]
    assert "drawingMlToSvg" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs --version" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs svg2dml examples/sample.svg" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs dml2svg tmp/package-smoke.xml" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs dml2svg examples/group.dml" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs dml2svg examples/freeform.dml" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs dml2svg examples/picture.dml" in package_metadata["scripts"]["check:package"]
    assert "node ./bin/svgraph.mjs dml2svg examples/preset.dml" in package_metadata["scripts"]["check:package"]
    assert 'transform=\\\"matrix(2 0 0 2 10 20)\\\"' in package_metadata["scripts"]["check:package"]
    assert 'transform=\\\"rotate(30 20 25) translate(20 25) scale(-1 1) translate(-20 -25)\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"30,20 50,40 10,40\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"120,20 160,20 160,36.4 150,40 140,37.6 130,40 120,36.4\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"170,20 200,20 210,30 200,40 170,40 180,30\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"227,20 233,20 233,27 240,27 240,33 233,33 233,40 227,40 227,33 220,33 220,27 227,27\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"280,25 306,25 306,20 320,30 306,40 306,35 280,35\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"330,20 370,20 354.8,31.6 354.8,40 345.2,40 345.2,31.6\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"450,20 470,25 460,25 460,28 470,28 470,32 460,32 460,40 440,40 440,32 430,32 430,28 440,28 440,25 430,25\\\"' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"490,30 490,20 491.3053,20.0856' in package_metadata["scripts"]["check:package"]
    assert 'points=\\\"550,20 551.2,27.2 555.8,22 553.6,28.6' in package_metadata["scripts"]["check:package"]
    assert "package-freeform.svg" in package_metadata["scripts"]["check:package"]
    assert "package-picture.svg" in package_metadata["scripts"]["check:package"]
    assert "package-preset.svg" in package_metadata["scripts"]["check:package"]
    assert "buildSVGraphAssistantPrompt" in package_metadata["scripts"]["check:package"]
    assert "applyAssistantPatch" in package_metadata["scripts"]["check:package"]
    assert "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2dml" in readme
    assert "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- dml2svg" in readme
    assert "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2pptx" in readme
    assert "node-version: \"24\"" in workflow
    assert "run: npm ci" in workflow
    assert "npm run check:web" in workflow
    assert "npm run build:web" in workflow
    assert "npm run check:package" in workflow
    assert "git diff --exit-code docs/app.js" in workflow
    assert "git diff --exit-code docs/app.d.ts" in workflow
    assert "QueryDomParser" in npm_cli
    assert "globalThis.DOMParser" in npm_cli
    assert "globalThis.Node" in npm_cli
    assert "svgToDrawingMl" in npm_cli
    assert "drawingMlToSvg" in npm_cli
    assert "svgToPptx" in npm_cli
    assert "buildSVGraph" in npm_cli


def test_dependabot_tracks_all_svgraph_dependency_surfaces() -> None:
    dependabot = (Path(__file__).resolve().parents[1] / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    for ecosystem, label in [
        ("github-actions", "github-actions"),
        ("pip", "python"),
        ("npm", "web"),
    ]:
        assert f'package-ecosystem: "{ecosystem}"' in dependabot
        assert f'- "{label}"' in dependabot
    assert dependabot.count('directory: "/"') == 3
    assert dependabot.count('interval: "weekly"') == 3
    assert "drawingml-svg" not in dependabot
    assert "pptxsvg" not in dependabot


def test_changelog_documents_svgraph_migration_guard_surfaces() -> None:
    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")

    for expected in [
        "top-level APIs",
        "Pages artifacts",
        "non-compatibility code paths",
        "python -m svgraph",
        "python -m svgraph.cli",
        "release and CI smoke checks",
        "public `com-junkawasaki/svgraph` repository identity and Pages URL",
        "stale local `*.egg-info` metadata",
        "generated artifact ignore coverage for Ruff cache, build distributions",
        "browser type checking and committed Pages artifact freshness",
        "every retained compatibility console script",
        "canonical `com-junkawasaki/svgraph` private advisory URL",
        "pull request checklist with canonical SVGraph JSON and presentation JSON smoke commands",
        "wheel metadata",
        "canonical `svgraph` surfaces",
        "canonical typed Python import package",
        "svgraph.model",
        "svgraph.converter",
        "svgraph.coverage",
        "svgraph.pptx",
        "contributing, security, code of conduct, issue templates, PR template",
        "pull request impact checklist with SVGraph model, presentation/package, PPTX, browser editor",
        "browser editor source, committed Pages artifact, and examples",
        "published sdist",
        "every pyproject console script and top-level package is verified from built wheel metadata",
        "`slide_size` and `text_styles`",
        "`slideSize` and `textStyles`",
        "GitHub Actions, Python, and npm/web dependency update pull requests",
        "canonical CLI help descriptions for visible SVGraph commands",
        "public repository description, MIT license metadata, and SVGraph topics",
        "published Pages title, description, Open Graph, and Twitter metadata",
        "live `app.js` artifact for canonical SVGraph controls and legacy-name exclusions",
        "release package metadata URLs for Homepage, Repository, Documentation, and Issues",
        "wheel license expression and license file metadata",
        "canonical `svgraph.model` explicit exports",
        "canonical `svgraph` distribution version lookup",
        "canonical `svgraph` version identity for retained compatibility console scripts",
        "CI and release wheel smoke checks that verify every retained console script",
        "browser SVGraph presentation package part content types",
        "SVGraph presentation package part schema documentation",
        "release and CI generated presentation JSON package part content types",
        "Python SVGraph presentation package part content type unit coverage",
        "SVGraph presentation JSON helper content type and source-node provenance regression coverage",
        "generated PPTX content type regression coverage aligned with the SVGraph presentation package blueprint",
        "generated PPTX slide master and layout part expansion from SVGraph presentation metadata and nodes",
        "generated PPTX slide relationship routing to declared SVGraph slide layout parts",
        "browser PPTX export parity for SVGraph presentation slide master and layout package parts",
        "release and CI wheel smoke coverage for multi-master SVGraph PPTX packages",
        "Python PPTX slide master default text style emission from SVGraph presentation text styles",
        "browser PPTX slide master default text style emission from SVGraph presentation text styles",
        "Python PPTX custom XML sidecar preservation for SVGraph presentation metadata",
        "browser PPTX custom XML sidecar preservation for SVGraph presentation metadata",
        "SVGraph presentation package blueprint custom XML sidecar part",
        "browser Slides pane package blueprint preview",
        "browser DrawingML fragment download",
        "browser SVG source download",
        "browser SVGraph sidecar JSON download",
        "browser PPTX custom XML `source_svg` preservation",
        "browser assistant patch proposal validation",
        "browser assistant patch diff preview",
        "browser assistant patch apply support",
        "browser SVG source undo/redo history",
        "browser IndexedDB persistence",
        "control for clearing the saved IndexedDB SVG source document",
        "browser storage status reporting",
        "`svgraph-sidecar.json` source restoration",
        "browser Open flow error reporting",
        "browser PPTX export support for SVG `text-decoration-style` underline mapping, including wavy underline",
        "browser PPTX export support for inherited SVG underline style, color, and thickness details",
        "browser coverage analyzer with supported SVG `text-decoration-style` values",
        "browser coverage analyzer with SVG `text-decoration-color` and `text-decoration-thickness` diagnostics",
        "browser coverage analyzer with CSS declaration diagnostics for supported SVG text, stroke, transform, and opacity attributes",
        "browser coverage analyzer text-layout no-op handling for non-text SVG subtrees",
        "browser coverage analyzer attribute-specific no-op handling for SVG font, glyph, bidi, writing-mode, and text-decoration controls",
        "browser coverage analyzer ignored-element handling for non-rendering geometry and no visible paint",
        "browser coverage analyzer `use` reference support checks against referenced SVG subtrees",
        "browser pattern paint-server fallback colors to ignore hidden and fully transparent content",
        "browser gradient paint-server fallback colors to ignore fully transparent stops",
        "browser gradient paint-server fallback colors with inherited stop color, opacity, and currentColor context",
        "browser SVG `href` resolution with namespace-aware legacy `xlink:href` handling",
        "browser paint-server fallback colors with CSS cascade rules for gradient stops and pattern children",
        "browser text run export with CSS cascade rules for `tspan` styling, rotation, anchor, and baseline fallback",
        "browser text position export with CSS cascade rules for `text` and `tspan` `x`/`y`/`dx`/`dy` geometry",
        "browser basic shape geometry export with CSS cascade rules for `rect`, `circle`, `ellipse`, and `line` geometry",
        "browser frame geometry export with CSS cascade rules for embedded images and `foreignObject` HTML tables",
        "browser geometry-dependent analysis and transform calculations with CSS cascade rules for non-rendering checks, reference boxes, and line `pathLength` scaling",
        "browser nested SVG, `use`, and rectangular `clipPath` geometry with CSS cascade rules",
        "browser rectangular `clipPath` transforms with CSS cascade rules",
        "browser rectangular `clipPath` container propagation",
        "browser line direction with DrawingML `flipH`/`flipV` transforms",
        "browser `clipPathUnits` values",
        "browser negative `stroke-width` fallback",
        "browser negative SVG rect radius fallback",
        "browser marker export with arrow-like SVG marker references",
        "browser JPEG intrinsic-size detection with segmented JPEG files",
        "browser data URI image validation",
        "browser `initial` and `unset` CSS keyword handling",
        "local Web LLM assistant worker hooks",
        "browser policy controls for WebGPU/WASM/disabled inference",
        "importable assistant prompt, parser, validation, diff, and patch helpers",
        "browser TypeScript `drawingMlToSvg` import support",
        "browser TypeScript `drawingMlToSvg` import support for DrawingML grouped shapes",
        "browser TypeScript `drawingMlToSvg` import support for DrawingML custom geometry/freeform paths",
        "browser TypeScript `drawingMlToSvg` import support for DrawingML pictures as SVG images",
        "browser TypeScript `drawingMlToSvg` import support for DrawingML rotation/flip transforms",
        "browser TypeScript `drawingMlToSvg` import support for common DrawingML preset polygon",
        "browser TypeScript `drawingMlToSvg` preset import support for DrawingML document/data/display flowchart",
        "browser TypeScript `drawingMlToSvg` preset import support for DrawingML bracket, brace, math symbol",
        "browser TypeScript `drawingMlToSvg` preset import support for DrawingML action buttons, funnel, wedge callouts",
        "browser TypeScript `drawingMlToSvg` preset import support for DrawingML pie, chord, block arc",
        "XML Open flow conversion back into canonical SVG source",
        "native DrawingML table fragments as semantic SVG table and cell nodes",
        "npm package CLI backed by the TypeScript/browser converter",
        "web editor design package part schema documentation",
        "compatibility submodule public-surface guards",
        "installed compatibility submodules prove their canonical `__all__` and callable parity",
        "retained legacy executable aliases, including `dml2svg`, verify their deprecation warnings",
        "canonical GitHub repository and issue tracker links to the published SVGraph Pages editor header",
        "release checklist HTTP smoke coverage for the canonical GitHub repository, issue tracker, and CI workflow URLs",
        "canonical GitHub repository link to the README project links section",
    ]:
        assert expected in changelog


def test_python_pptx_exporter_covers_svgraph_text_style_defaults() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "svgraph" / "pptx.py").read_text(encoding="utf-8")
    tests = (root / "tests" / "test_converter.py").read_text(encoding="utf-8")

    assert "text_styles=presentation.text_styles" in source
    assert "def _slide_master(text_styles" in source
    assert "def _text_style_xml" in source
    assert "test_svg_to_pptx_bytes_writes_presentation_text_styles_to_slide_master" in tests
    assert '<p:titleStyle><a:lvl1pPr><a:defRPr sz="4800" b="1">' in tests


def test_python_pptx_exporter_preserves_svgraph_sidecar_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "svgraph" / "pptx.py").read_text(encoding="utf-8")
    tests = (root / "tests" / "test_converter.py").read_text(encoding="utf-8")

    assert "custom_xml=_svgraph_presentation_sidecar(presentation, svg_text)" in source
    assert "def _svgraph_presentation_sidecar(presentation: object, source_svg: str)" in source
    assert 'payload_dict["source_svg"] = source_svg' in source
    assert '"https://com-junkawasaki.github.io/svgraph/schema/presentation"' in source
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"' in source
    assert "test_svg_to_pptx_bytes_preserves_svgraph_presentation_sidecar" in tests
    assert "customXml/item1.xml" in tests
    assert 'payload["source_svg"] == svg' in tests


def test_drawingml_svg_modules_are_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    unexpected: list[str] = []
    assert COMPATIBILITY_WRAPPER_MODULES == {
        "src/drawingml_svg/__init__.py": "from svgraph import",
        "src/drawingml_svg/cli.py": "from svgraph.cli import *",
        "src/drawingml_svg/converter.py": "from svgraph.converter import *",
        "src/drawingml_svg/coverage.py": "from svgraph.coverage import *",
        "src/drawingml_svg/pptx.py": "from svgraph.pptx import *",
        "src/drawingml_svg/svgraph.py": "from svgraph.model import *",
    }
    for relative, expected_import in COMPATIBILITY_WRAPPER_MODULES.items():
        text = (root / relative).read_text(encoding="utf-8")
        if expected_import not in text:
            unexpected.append(f"{relative}: missing {expected_import}")
        if expected_import.endswith(" import *") and (
            f"from {expected_import.removeprefix('from ').removesuffix(' import *')} import __all__ as __all__"
            not in text
        ):
            unexpected.append(f"{relative}: missing canonical __all__ re-export")
        if "def " in text or "class " in text:
            unexpected.append(f"{relative}: contains implementation definitions")

    assert "compatibility import path whose main modules are wrappers over `svgraph`" in readme
    assert "new code should import `svgraph`" in readme
    assert "main modules are compatibility wrappers over `svgraph`" in migration
    assert "main modules re-export the canonical module `__all__` values" in migration
    assert unexpected == []


def test_legacy_ir_module_keeps_only_pre_svgraph_alias_exports() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "drawingml_svg" / "ir.py").read_text(encoding="utf-8")
    model_source = (root / "src" / "svgraph" / "model.py").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")

    assert _literal_all(source) == [
        "SvgIRDependency",
        "SvgIRDocument",
        "SvgIRGuide",
        "SvgIRNode",
        "SvgIRPackagePart",
        "SvgIRPresentation",
        "SvgIRRuler",
        "SvgIRSlide",
        "SvgIRTemplate",
        "SvgIRTextStyle",
        "svg_ir_to_json",
        "svg_pptx_ir_to_json",
        "svg_to_ir",
        "svg_to_pptx_ir",
    ]
    for unexpected in [
        "SVGraphDocument",
        "SVGraphNode",
        "svg_to_svgraph",
        "svg_to_svgraph_presentation",
        "svg_svgraph_to_json",
        "svg_svgraph_presentation_to_json",
    ]:
        assert f'"{unexpected}"' not in source
    assert _literal_all(model_source) == [
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
        "svg_ir_to_json",
        "svg_pptx_ir_to_json",
        "svg_to_ir",
        "svg_to_pptx_ir",
    ]:
        assert f'"{legacy_name}"' not in model_source
    assert '_warn_legacy("svg_to_ir()", "svgraph.model.svg_to_svgraph()")' in source
    assert '_warn_legacy("svg_to_pptx_ir()", "svgraph.model.svg_to_svgraph_presentation()")' in source
    assert "legacy `drawingml_svg.ir` module intentionally exports only pre-SVGraph `SvgIR*` aliases" in migration
    assert "import canonical `SVGraph*` types from `svgraph.model`" in migration


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


def test_adr_defines_svgraph_as_presentation_package_contract() -> None:
    adr = (Path(__file__).resolve().parents[1] / "docs" / "adr" / "0001-svgraph.md").read_text(encoding="utf-8")

    for expected in [
        "SVG source can later emit Android VectorDrawable, DrawingML, PresentationML, or other targets.",
        '"kind": "svgraph"',
        '"kind": "svgraph-presentation"',
        '"masters": []',
        '"layouts": []',
        '"guides": []',
        '"rulers": []',
        '"text_styles": []',
        '"part_name": "/ppt/presentation.xml"',
        '"content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"',
        '"source_node_id": null',
        '`data-kind="slide-master"`',
        '`data-kind="slide-layout"`',
        '`data-kind="guide"`',
        '`data-kind="ruler"`',
        '`data-kind="style-template"`',
        "The package emitter can then map:",
        "each slide node to `ppt/slides/slideN.xml`",
        "the `parts` list to the required package blueprint, including `part_name`, `content_type`, `kind`, and source-node provenance",
        "`/customXml/item1.xml`",
        "`masters` and `layouts` to PresentationML slide master/layout parts",
        "`guides` and `rulers` to editor metadata or custom XML sidecars",
        "`text_styles` to PresentationML default text styles and placeholder styles",
        "semantic relations to connectors when they have visual counterparts",
        "use `svgraph-presentation` as the package-level contract",
    ]:
        assert expected in adr

    assert "pptxsvg" not in adr
    assert "presentation IR" not in adr


def test_readme_documents_svgraph_presentation_package_part_contract() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

    for expected in [
        "The `svgraph-presentation` command and `svg_to_svgraph_presentation()` API",
        "with each part carrying `part_name`, `content_type`, `kind`, and source-node provenance where available",
        "slide master/layout/theme parts",
        "generated `/ppt/slides/slideN.xml` parts",
        "custom XML sidecar part",
        "Generated PPTX custom XML also preserves `source_svg`",
    ]:
        assert expected in readme


def test_web_editor_design_uses_browser_only_svgraph_contract() -> None:
    design = (Path(__file__).resolve().parents[1] / "docs" / "svgraph-web-editor.md").read_text(encoding="utf-8")

    for expected in [
        "`svg_to_svgraph()` exposes SVGraph structure",
        "`svg_to_svgraph_presentation()` provides the package-level plan for `.pptx` export",
        "`web/app.ts` is the TypeScript browser runtime.",
        "GitHub Pages loads the compiled `docs/app.js`.",
        "without Python",
        "`svgraph-sidecar.json`",
        "can restore the editable SVG source by opening that sidecar JSON",
        "reports invalid Open inputs without replacing the current source",
        "semantic sidecar with metadata, dependencies, coverage, and presentation package state",
        "DrawingML fragments and `.pptx` without Python",
        "import basic DrawingML shape fragments back into canonical SVG source without Python",
        'p:cxnSp` connectors as `data-kind="relation"` SVG lines',
        "native `p:graphicFrame`/`a:tbl` tables as `data-kind=\"table\"`",
        "deterministic patch proposal/validation preview",
        "can replace the proposal with local Web LLM output after validation",
        "deterministic patch diff preview rows",
        "apply validated SVGraph patch operations back into the canonical SVG source",
        "lazy-load a dedicated Transformers.js worker",
        "choose WebGPU, WASM, or disabled backend policy",
        "reject invalid operations",
        "SVG source undo/redo history",
        "persists the active SVG source document in IndexedDB",
        "control for clearing the saved document",
        "reports storage status in the UI",
        "`SVGraphDocument`",
        "`SVGraphPresentation` projection",
        "`svgraph-presentation` view",
        "`svgraph.json`",
        "`svgraph-presentation.json`",
        "The `.pptx` exporter should consume the SVGraph `presentation.parts` projection",
        "Each package part record carries `part_name`, `content_type`, `kind`, and `source_node_id`",
        "The Web LLM runs in a dedicated worker",
        "The editor also exposes `wasm` and `disabled` policies",
        'device: "webgpu"',
        "LLM output is always a proposed patch against SVGraph-level commands",
        "validated by deterministic code before applying",
        "The canonical Python import package is `svgraph`",
    ]:
        assert expected in design

    assert "PPTXSVG" not in design
    assert "pptxsvg" not in design
    assert "presentation IR" not in design
    assert "drawingml-svg-web" not in design


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


def test_migration_guide_covers_all_compatibility_console_scripts() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]

    expected_aliases = {
        "drawingml-svg": "svgraph",
        "drawingml-svg-analyze": "svgraph analyze",
        "svg2dml": "svgraph svg2dml",
        "dml2svg": "svgraph dml2svg",
        "svg2pptx": "svgraph svg2pptx",
    }

    assert set(scripts) - {"svgraph"} == set(expected_aliases)
    for alias, canonical in expected_aliases.items():
        assert f"`{alias}` executable | `{canonical}`" in migration
        assert scripts[alias] == "svgraph.cli:main"


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


def test_migration_guide_verification_matches_svgraph_web_and_python_guards() -> None:
    migration = (Path(__file__).resolve().parents[1] / "MIGRATION.md").read_text(encoding="utf-8")
    verification = migration.split("## Verification", maxsplit=1)[1]

    for command in [
        "npm install @com-junkawasaki/svgraph --registry=https://npm.pkg.github.com",
        "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2dml input.svg -o shape.xml",
        "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- dml2svg shape.xml -o shape.svg",
        "npm exec --registry=https://npm.pkg.github.com @com-junkawasaki/svgraph -- svg2pptx deck.svg -o deck.pptx",
    ]:
        assert command in migration

    for command in [
        'find src -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +',
        "rm -rf build tmp/dist",
        "ruff check .",
        "npm ci",
        "npm run check:web",
        "npm run build:web",
        "npm run check:package",
        "git diff --exit-code docs/app.js",
        "git diff --exit-code docs/app.d.ts",
        "PYTHONPATH=src python -m pytest -q tests/test_migration.py tests/test_svgraph.py",
    ]:
        assert command in verification

    assert "browser editor artifacts" in verification
    assert "PYTHONPATH=src pytest " not in verification


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


def _literal_assignment(source: str, name: str) -> object:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing {name} assignment")


def _typescript_string_set(source: str, name: str) -> set[str]:
    match = re.search(rf"const {name} = new Set\(\[([\s\S]*?)\]\);", source)
    if not match:
        raise AssertionError(f"missing {name} set")
    return set(re.findall(r'"([^"]+)"', match.group(1)))
