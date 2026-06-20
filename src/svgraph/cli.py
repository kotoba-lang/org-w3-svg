from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from xml.etree import ElementTree as ET

from .coverage import analyze_svg
from .converter import drawingml_to_svg, svg_to_drawingml
from .pptx import svg_to_pptx
from .model import svg_svgraph_presentation_to_json, svg_svgraph_to_json


VISIBLE_COMMANDS = ("svg2dml", "dml2svg", "svg2pptx", "analyze", "svgraph", "svgraph-presentation")
LEGACY_COMMANDS = ("ir", "pptxsvg")
REPORT_COMMANDS = {"analyze", "ir", "svgraph", "svgraph-presentation", "pptxsvg"}


def main(argv: list[str] | None = None) -> int:
    argv_was_provided = argv is not None
    argv = _normalize_argv(argv)
    parser = argparse.ArgumentParser(prog=_program_name(argv_was_provided))
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    subparsers = parser.add_subparsers(dest="command", metavar="{" + ",".join(VISIBLE_COMMANDS) + "}")
    subparsers.required = True

    for command in (*VISIBLE_COMMANDS, *LEGACY_COMMANDS):
        sub = subparsers.add_parser(command)
        if command in LEGACY_COMMANDS:
            subparsers._choices_actions = [action for action in subparsers._choices_actions if action.dest != command]
        sub.add_argument("input", nargs="?", help="Input file. Reads stdin when omitted.")
        if command not in REPORT_COMMANDS:
            sub.add_argument("-o", "--output", help="Output file. Writes stdout when omitted.")

    args = parser.parse_args(argv)
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
        try:
            return version("drawingml-svg")
        except PackageNotFoundError:
            return "0+unknown"


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is not None:
        return argv
    invoked_as = Path(sys.argv[0]).name
    if invoked_as == "svgraph" and sys.argv[1:] and sys.argv[1] not in {*VISIBLE_COMMANDS, *LEGACY_COMMANDS}:
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


if __name__ == "__main__":
    sys.argv[0] = "svgraph"
    raise SystemExit(main())
