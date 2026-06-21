#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { stdin, stdout, stderr, argv, exit } from "node:process";
import { DOMParser as XmldomParser, XMLSerializer } from "@xmldom/xmldom";

class QueryDomParser extends XmldomParser {
  parseFromString(text, mimeType) {
    return patchSelectorApi(super.parseFromString(text, mimeType));
  }
}

globalThis.DOMParser ??= QueryDomParser;
globalThis.XMLSerializer ??= XMLSerializer;
globalThis.Node ??= { ELEMENT_NODE: 1, TEXT_NODE: 3 };

const {
  buildSVGraph,
  drawingMlToSvg,
  svgToDrawingMl,
  svgToPptx,
} = await import("../docs/app.js");

const usage = `Usage:
  svgraph svg2dml <input.svg|-> [-o output.xml]
  svgraph dml2svg <input.xml|-> [-o output.svg]
  svgraph svg2pptx <input.svg|-> [-o output.pptx]
  svgraph svgraph <input.svg|-> [-o output.json]
  svgraph svgraph-presentation <input.svg|-> [-o output.json]
  svgraph analyze <input.svg|-> [-o output.json]
  svgraph --version`;

const args = argv.slice(2);
const command = args[0];

try {
  if (!command || command === "-h" || command === "--help") {
    stdout.write(`${usage}\n`);
    exit(0);
  }
  if (command === "--version") {
    const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
    stdout.write(`svgraph ${packageJson.version}\n`);
    exit(0);
  }

  const { input, output } = parseIo(args.slice(1));
  const text = await readInput(input);
  if (command === "svg2dml") {
    await writeOutput(output, svgToDrawingMl(text));
  } else if (command === "dml2svg") {
    await writeOutput(output, drawingMlToSvg(text));
  } else if (command === "svg2pptx") {
    await writeOutput(output, svgToPptx(text));
  } else if (command === "svgraph") {
    await writeOutput(output, `${JSON.stringify(buildSVGraph(text), null, 2)}\n`);
  } else if (command === "svgraph-presentation") {
    await writeOutput(output, `${JSON.stringify(buildSVGraph(text).presentation, null, 2)}\n`);
  } else if (command === "analyze") {
    await writeOutput(output, `${JSON.stringify(buildSVGraph(text).coverage, null, 2)}\n`);
  } else {
    throw new Error(`unknown command: ${command}`);
  }
} catch (error) {
  stderr.write(`${error instanceof Error ? error.message : String(error)}\n${usage}\n`);
  exit(1);
}

function parseIo(args) {
  let input = "-";
  let output = "-";
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "-o" || arg === "--output") {
      output = args[index + 1] ?? "";
      index += 1;
    } else if (!input || input === "-") {
      input = arg;
    } else {
      throw new Error(`unexpected argument: ${arg}`);
    }
  }
  if (!input) throw new Error("missing input path");
  if (!output) throw new Error("missing output path");
  return { input, output };
}

async function readInput(path) {
  if (path === "-") {
    const chunks = [];
    for await (const chunk of stdin) chunks.push(chunk);
    return Buffer.concat(chunks).toString("utf8");
  }
  return readFile(path, "utf8");
}

async function writeOutput(path, value) {
  if (path === "-") {
    stdout.write(value);
    return;
  }
  await writeFile(path, value);
}

function patchSelectorApi(document) {
  const querySelectorAll = function querySelectorAll(selector) {
    return findBySimpleSelector(this, selector);
  };
  const querySelector = function querySelector(selector) {
    return querySelectorAll.call(this, selector)[0] ?? null;
  };
  const install = (node) => {
    if (node && typeof node === "object") {
      node.querySelector ??= querySelector;
      node.querySelectorAll ??= querySelectorAll;
      for (const child of Array.from(node.childNodes ?? [])) install(child);
    }
  };
  install(document);
  return document;
}

function findBySimpleSelector(root, selector) {
  const normalized = selector.trim();
  if (!/^[A-Za-z_][A-Za-z0-9_.:-]*$/.test(normalized)) {
    throw new Error(`unsupported CLI selector: ${selector}`);
  }
  const matches = [];
  const visit = (node) => {
    if (node?.nodeType === 1 && (node.localName || node.nodeName).split(":").pop() === normalized.split(":").pop()) {
      matches.push(node);
    }
    for (const child of Array.from(node?.childNodes ?? [])) visit(child);
  };
  visit(root.documentElement ?? root);
  return matches;
}
