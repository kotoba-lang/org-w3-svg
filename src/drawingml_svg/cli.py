from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .coverage import analyze_svg
from .converter import drawingml_to_svg, svg_to_drawingml


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_argv(argv)
    parser = argparse.ArgumentParser(prog="drawingml-svg")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    for command in ("svg2dml", "dml2svg", "analyze"):
        sub = subparsers.add_parser(command)
        sub.add_argument("input", nargs="?", help="Input file. Reads stdin when omitted.")
        if command != "analyze":
            sub.add_argument("-o", "--output", help="Output file. Writes stdout when omitted.")

    args = parser.parse_args(argv)
    source = _read_text(args.input)
    if args.command == "svg2dml":
        output = svg_to_drawingml(source)
    elif args.command == "dml2svg":
        output = drawingml_to_svg(source)
    elif args.command == "analyze":
        output = json.dumps(analyze_svg(source).to_dict(), indent=2, sort_keys=True) + "\n"
    else:
        parser.error(f"unknown command: {args.command}")

    _write_text(getattr(args, "output", None), output)
    return 0


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is not None:
        return argv
    invoked_as = Path(sys.argv[0]).name
    if invoked_as in {"svg2dml", "dml2svg", "drawingml-svg-analyze"}:
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
