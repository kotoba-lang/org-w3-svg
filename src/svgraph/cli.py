from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib
from xml.etree import ElementTree as ET

from .coverage import analyze_svg
from .converter import drawingml_to_svg, svg_to_drawingml
from .pptx import svg_to_pptx
from .model import svg_svgraph_presentation_to_json, svg_svgraph_to_json


VISIBLE_COMMANDS = ("svg2dml", "dml2svg", "svg2pptx", "analyze", "svgraph", "svgraph-presentation")
LEGACY_COMMANDS = ("ir", "pptxsvg")
REPORT_COMMANDS = {"analyze", "ir", "svgraph", "svgraph-presentation", "pptxsvg"}
COMMAND_HELP = {
    "svg2dml": "convert SVG to a DrawingML shape fragment",
    "dml2svg": "convert a DrawingML shape fragment to SVG",
    "svg2pptx": "convert SVG/SVGraph presentation metadata to a PPTX package",
    "analyze": "report SVG conversion coverage and unsupported features",
    "svgraph": "emit the metadata-preserving SVGraph JSON document",
    "svgraph-presentation": "emit the SVGraph presentation/package JSON projection",
}


def main(argv: list[str] | None = None) -> int:
    argv_was_provided = argv is not None
    invoked_as = None if argv_was_provided else Path(sys.argv[0]).name
    argv = _normalize_argv(argv)
    parser = argparse.ArgumentParser(prog=_program_name(argv_was_provided))
    parser.add_argument("--version", action="version", version=f"svgraph {_package_version()}")
    subparsers = parser.add_subparsers(dest="command", metavar="{" + ",".join(VISIBLE_COMMANDS) + "}")
    subparsers.required = True

    for command in (*VISIBLE_COMMANDS, *LEGACY_COMMANDS):
        help_text = COMMAND_HELP.get(command)
        sub = subparsers.add_parser(command, help=help_text, description=help_text)
        if command in LEGACY_COMMANDS:
            subparsers._choices_actions = [action for action in subparsers._choices_actions if action.dest != command]
        sub.add_argument("input", nargs="?", help="Input file. Reads stdin when omitted.")
        if command not in REPORT_COMMANDS:
            sub.add_argument("-o", "--output", help="Output file. Writes stdout when omitted.")

    args = parser.parse_args(argv)
    if invoked_as is not None:
        _warn_legacy_executable_invocation(parser, invoked_as)
    try:
        source = _read_text(args.input)
        if args.command == "svg2dml":
            output = svg_to_drawingml(source)
        elif args.command == "dml2svg":
            output = drawingml_to_svg(source)
        elif args.command == "svg2pptx":
            if not args.output:
                parser.error("svg2pptx requires -o/--output")
            svg_to_pptx(source, args.output)
            output = None
        elif args.command == "analyze":
            output = json.dumps(analyze_svg(source).to_dict(), indent=2, sort_keys=True) + "\n"
        elif args.command == "ir":
            _warn_legacy_command(parser, "ir", "svgraph")
            output = svg_svgraph_to_json(source)
        elif args.command == "svgraph":
            output = svg_svgraph_to_json(source)
        elif args.command == "svgraph-presentation":
            output = svg_svgraph_presentation_to_json(source)
        elif args.command == "pptxsvg":
            _warn_legacy_command(parser, "pptxsvg", "svgraph-presentation")
            output = svg_svgraph_presentation_to_json(source)
        else:
            parser.error(f"unknown command: {args.command}")

        if output is not None:
            _write_text(getattr(args, "output", None), output)
    except (ET.ParseError, OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    return 0


def _package_version() -> str:
    try:
        return version("svgraph")
    except PackageNotFoundError:
        source_tree_version = _source_tree_version()
        if source_tree_version is not None:
            return source_tree_version
        return "0+unknown"


def _source_tree_version() -> str | None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.is_file():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    if project.get("name") != "svgraph":
        return None
    source_version = project.get("version")
    return source_version if isinstance(source_version, str) else None


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is not None:
        return argv
    invoked_as = Path(sys.argv[0]).name
    if invoked_as in {"svgraph", "drawingml-svg"} and sys.argv[1:] and sys.argv[1] not in {*VISIBLE_COMMANDS, *LEGACY_COMMANDS}:
        if sys.argv[1] not in {"--version", "-h", "--help"}:
            return ["svgraph", *sys.argv[1:]]
    if invoked_as in {"svg2dml", "dml2svg", "svg2pptx", "drawingml-svg-analyze"}:
        if sys.argv[1:] == ["--version"]:
            return sys.argv[1:]
        if invoked_as == "drawingml-svg-analyze":
            invoked_as = "analyze"
        return [invoked_as, *sys.argv[1:]]
    return None


def _program_name(argv_was_provided: bool) -> str:
    if argv_was_provided:
        return "svgraph"
    invoked_as = Path(sys.argv[0]).name
    if invoked_as in {"svgraph", "drawingml-svg"}:
        return invoked_as
    return "drawingml-svg"


def _read_text(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str | None, text: str) -> None:
    if path is None or path == "-":
        sys.stdout.write(text)
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _warn_legacy_command(parser: argparse.ArgumentParser, command: str, replacement: str) -> None:
    parser._print_message(
        f"{parser.prog}: warning: '{command}' is deprecated; use '{replacement}'.\n",
        sys.stderr,
    )


def _warn_legacy_executable(parser: argparse.ArgumentParser, executable: str, replacement: str) -> None:
    parser._print_message(
        f"{parser.prog}: warning: executable '{executable}' is deprecated; use '{replacement}'.\n",
        sys.stderr,
    )


def _warn_legacy_executable_invocation(parser: argparse.ArgumentParser, invoked_as: str) -> None:
    replacements = {
        "drawingml-svg": "svgraph",
        "svg2dml": "svgraph svg2dml",
        "dml2svg": "svgraph dml2svg",
        "svg2pptx": "svgraph svg2pptx",
        "drawingml-svg-analyze": "svgraph analyze",
    }
    replacement = replacements.get(invoked_as)
    if replacement is not None:
        _warn_legacy_executable(parser, invoked_as, replacement)


if __name__ == "__main__":
    sys.argv[0] = "svgraph"
    raise SystemExit(main())
