from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from xml.etree import ElementTree as ET

from .coverage import analyze_svg
from .converter import drawingml_to_svg, svg_to_drawingml
from .ir import svg_ir_to_json, svg_pptx_ir_to_json, svg_svgraph_to_json
from .pptx import svg_to_pptx


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_argv(argv)
    parser = argparse.ArgumentParser(prog="drawingml-svg")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    for command in ("svg2dml", "dml2svg", "svg2pptx", "analyze", "ir", "svgraph", "pptxsvg"):
        sub = subparsers.add_parser(command)
        sub.add_argument("input", nargs="?", help="Input file. Reads stdin when omitted.")
        if command not in {"analyze", "ir", "svgraph", "pptxsvg"}:
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
            output = svg_ir_to_json(source)
        elif args.command == "svgraph":
            output = svg_svgraph_to_json(source)
        elif args.command == "pptxsvg":
            output = svg_pptx_ir_to_json(source)
        else:
            parser.error(f"unknown command: {args.command}")

        if output is not None:
            _write_text(getattr(args, "output", None), output)
    except (ET.ParseError, OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    return 0


def _package_version() -> str:
    try:
        return version("drawingml-svg")
    except PackageNotFoundError:
        return "0+unknown"


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is not None:
        return argv
    invoked_as = Path(sys.argv[0]).name
    if invoked_as in {"svg2dml", "dml2svg", "svg2pptx", "drawingml-svg-analyze"}:
        if sys.argv[1:] == ["--version"]:
            return sys.argv[1:]
        if invoked_as == "drawingml-svg-analyze":
            invoked_as = "analyze"
        return [invoked_as, *sys.argv[1:]]
    return None


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


if __name__ == "__main__":
    raise SystemExit(main())
