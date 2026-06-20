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

    for ignored in ["__pycache__/", ".pytest_cache/", "*.egg-info/", "build/", "tmp/", "node_modules/"]:
        assert ignored in gitignore

    forbidden_tracked_patterns = [
        "tmp/",
        "build/",
        "node_modules/",
        "src/drawingml_svg.egg-info/",
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
    assert package_metadata["name"] == "svgraph-web"
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
    assert "tmp/wheel-venv/bin/python -m svgraph --version" in workflow
    assert "tmp/wheel-venv/bin/python -m svgraph analyze examples/coverage.svg" in workflow
    assert "python -m svgraph --version" in readme
    assert "python -m svgraph --version" in migration
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

    assert visible_commands == ("svg2dml", "dml2svg", "svg2pptx", "analyze", "svgraph", "svgraph-presentation")
    assert legacy_commands == ("ir", "pptxsvg")
    assert "ir" not in visible_commands
    assert "pptxsvg" not in visible_commands


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
    assert "drawingml-svg = svgraph.cli:main" in entry_point_text
    assert "drawingml-svg-analyze = svgraph.cli:main" in entry_point_text
    assert {"svgraph", "drawingml_svg"} <= top_level_names


def test_release_checklist_keeps_legacy_console_alias_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    release = (root / "RELEASE.md").read_text(encoding="utf-8")
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]

    assert "pyproject.toml` and `package.json` have the intended version" in release
    for executable in sorted(set(scripts) - {"svgraph"}):
        assert f"tmp/release-venv/bin/{executable} --version" in release


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
        'urlopen("https://com-junkawasaki.github.io/svgraph/", timeout=20)',
        '"<title>SVGraph Editor</title>"',
        "'name=\"description\"'",
        '\'property="og:title" content="SVGraph Editor"\'',
        '\'property="og:url" content="https://com-junkawasaki.github.io/svgraph/"\'',
        '\'name="twitter:title" content="SVGraph Editor"\'',
        '"https://com-junkawasaki.github.io/svgraph/"',
        '"Download SVGraph"',
        '"PPTX" + "SVG"',
        '"pptx" + "svg"',
        '"drawingml-" + "svg-web"',
        '"download" + "IrBtn"',
        '"download" + "Pptxsvg"',
        "assert expected in html",
        "assert forbidden not in html",
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
        assert 'web_package["name"] == "svgraph-web"' in source
        assert 'web_package["version"] == pyproject["project"]["version"]' in source
        assert (
            'web_package["description"] == "Browser-only SVGraph editor and SVG to PresentationML/PPTX converter."'
        ) in source
        assert 'web_package["homepage"] == "https://com-junkawasaki.github.io/svgraph/"' in source
        assert 'web_package["private"] is True' in source
        assert 'web_package["license"] == "MIT"' in source
        assert 'web_lock["name"] == web_package["name"]' in source
        assert 'web_lock["packages"][""]["name"] == web_package["name"]' in source
        assert 'web_lock["packages"][""]["license"] == web_package["license"]' in source
        assert "tmp/dist/drawingml_svg-" not in source
        assert "tmp/dist/drawingml-svg-" not in source

    assert "tmp/release-svgraph.json" in release
    assert "tmp/release-svgraph-presentation.json" in release
    assert "tmp/release-legacy-svgraph.json" in release
    assert "tmp/wheel-svgraph.json" in workflow
    assert "tmp/wheel-svgraph-presentation.json" in workflow
    assert "tmp/wheel-legacy-svgraph.json" in workflow


def test_release_checklist_rebuilds_and_packages_svgraph_web_editor() -> None:
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    for expected in [
        "npm ci",
        "npm run check:web",
        "npm run build:web",
        "git diff --exit-code docs/app.js",
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
    release = (Path(__file__).resolve().parents[1] / "RELEASE.md").read_text(encoding="utf-8")

    assert "tmp/release-venv/bin/svgraph svg2dml examples/sample.svg -o tmp/release-smoke.xml" in release
    assert "tmp/release-venv/bin/svgraph svg2pptx examples/sample.svg -o tmp/release-smoke.pptx" in release
    assert "python -m zipfile --test tmp/release-smoke.pptx" in release
    assert "tmp/release-venv/bin/svg2pptx examples/" not in release


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

    assert "tmp/release-venv/bin/svgraph --version" in release
    assert "tmp/release-venv/bin/python -m svgraph --version" in release


def test_contributor_checks_use_canonical_svgraph_commands_and_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pr_template = (root / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

    for source in [contributing, pr_template]:
        assert "PYTHONPATH=src python -m pytest -q" in source
        assert "npm ci" in source
        assert "npm run check:web" in source
        assert "npm run build:web" in source
        assert "PYTHONPATH=src python -m svgraph analyze examples/coverage.svg" in source
        assert "PYTHONPATH=src python -m svgraph svgraph examples/svgraph.svg > tmp/svgraph.json" in source
        assert (
            "PYTHONPATH=src python -m svgraph svgraph-presentation examples/svgraph.svg > tmp/svgraph-presentation.json"
            in source
        )
        assert "tmp/svgraph-coverage.pptx" in source
        assert "python -m zipfile --test tmp/svgraph-coverage.pptx" in source
        assert "git diff --exit-code docs/app.js" in source
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


def test_legacy_import_allowlist_is_limited_to_migration_tests() -> None:
    assert ALLOWED_LEGACY_IMPORT_SURFACES == {
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
    assert (
        'content="Browser-only SVGraph editor for converting SVG presentation graphs into editable '
        'PresentationML and PPTX."'
    ) in html
    assert '<link rel="canonical" href="https://com-junkawasaki.github.io/svgraph/" />' in html
    assert '<meta property="og:title" content="SVGraph Editor" />' in html
    assert '<meta property="og:url" content="https://com-junkawasaki.github.io/svgraph/" />' in html
    assert '<meta name="twitter:title" content="SVGraph Editor" />' in html
    assert "https://com-junkawasaki.github.io/drawingml-svg" not in workflow + html


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

    assert '"name": "svgraph-web"' in package_json
    assert '"name": "svgraph-web"' in package_lock
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
    assert package_metadata["private"] is True
    assert package_metadata["license"] == "MIT"
    assert lock_metadata["packages"][""]["license"] == package_metadata["license"]
    assert "<title>SVGraph Editor</title>" in html
    assert 'id="downloadSVGraphBtn"' in html
    assert 'mustElement<HTMLButtonElement>("downloadSVGraphBtn")' in source
    for generated in [source, app_js]:
        assert 'downloadText("svgraph.json"' in generated
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
    assert "npm run check:web" in readme
    assert "npm run build:web" in readme
    assert package_metadata["scripts"]["build:web"] == "tsc -p tsconfig.web.json"
    assert package_metadata["scripts"]["check:web"] == "tsc -p tsconfig.web.json --noEmit"
    assert "node-version: \"24\"" in workflow
    assert "run: npm ci" in workflow
    assert "npm run check:web" in workflow
    assert "npm run build:web" in workflow
    assert "git diff --exit-code docs/app.js" in workflow


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
        "browser editor source, committed Pages artifact, and examples",
        "published sdist",
        "`slide_size` and `text_styles`",
        "`slideSize` and `textStyles`",
        "GitHub Actions, Python, and npm/web dependency update pull requests",
        "public repository description, MIT license metadata, and SVGraph topics",
        "published Pages title, description, Open Graph, and Twitter metadata",
        "release package metadata URLs for Homepage, Repository, Documentation, and Issues",
        "wheel license expression and license file metadata",
        "canonical `svgraph.model` explicit exports",
        "canonical `svgraph` distribution version lookup",
    ]:
        assert expected in changelog


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
        if "def " in text or "class " in text:
            unexpected.append(f"{relative}: contains implementation definitions")

    assert "compatibility import path whose main modules are wrappers over `svgraph`" in readme
    assert "new code should import `svgraph`" in readme
    assert "main modules are compatibility wrappers over `svgraph`" in migration
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
        '`data-kind="slide-master"`',
        '`data-kind="slide-layout"`',
        '`data-kind="guide"`',
        '`data-kind="ruler"`',
        '`data-kind="style-template"`',
        "The package emitter can then map:",
        "each slide node to `ppt/slides/slideN.xml`",
        "`masters` and `layouts` to PresentationML slide master/layout parts",
        "`guides` and `rulers` to editor metadata or custom XML sidecars",
        "`text_styles` to PresentationML default text styles and placeholder styles",
        "semantic relations to connectors when they have visual counterparts",
        "use `svgraph-presentation` as the package-level contract",
    ]:
        assert expected in adr

    assert "pptxsvg" not in adr
    assert "presentation IR" not in adr


def test_web_editor_design_uses_browser_only_svgraph_contract() -> None:
    design = (Path(__file__).resolve().parents[1] / "docs" / "svgraph-web-editor.md").read_text(encoding="utf-8")

    for expected in [
        "`svg_to_svgraph()` exposes SVGraph structure",
        "`svg_to_svgraph_presentation()` provides the package-level plan for `.pptx` export",
        "`web/app.ts` is the TypeScript browser runtime.",
        "GitHub Pages loads the compiled `docs/app.js`.",
        "without Python",
        "`SVGraphDocument`",
        "`SVGraphPresentation` projection",
        "`svgraph-presentation` view",
        "`svgraph.json`",
        "`svgraph-presentation.json`",
        "The `.pptx` exporter should consume the SVGraph `presentation.parts` projection",
        "Web LLM should run in a dedicated worker",
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
        'find src -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +',
        "rm -rf build tmp/dist",
        "ruff check .",
        "npm ci",
        "npm run check:web",
        "npm run build:web",
        "git diff --exit-code docs/app.js",
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
