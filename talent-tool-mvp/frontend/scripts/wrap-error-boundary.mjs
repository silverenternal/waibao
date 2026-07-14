// T5006 — Wrap every page.tsx default export's returned JSX in <ErrorBoundary>.
// Uses recast + @babel/parser (TSX) for safe AST surgery. Idempotent.
//
// Skip rules:
//   - body contains a redirect() call (the page just redirects)
//   - module declares `export const dynamic` / `force-static` (static page)
//   - already wrapped (an <ErrorBoundary> is the outermost returned element)
//   - returns a non-JSX value (e.g. null, a string, early returns everywhere)
//
// Output: prints a summary; mutates files in place.

import { readFileSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";

let recast;
let parser;
try {
  recast = (await import("recast")).default;
} catch {
  console.error("recast not installed");
  process.exit(1);
}

const babel = await import("@babel/parser");

// Custom parser plugin hook for recast.
const parse = (source) =>
  babel.parse(source, {
    sourceType: "module",
    plugins: ["jsx", "typescript"],
    tokens: true, // recast needs tokens to preserve formatting
  });

// Collect all page.tsx files.
const files = execSync("find app -name page.tsx", { encoding: "utf8" })
  .trim()
  .split("\n")
  .filter(Boolean);

let wrapped = 0;
let skipped = 0;
const skipReasons = {};

function note(reason, file) {
  skipped++;
  (skipReasons[reason] ??= []).push(file);
}

// Detect whether a node is a JSX element/fragment.
function isJSX(node) {
  if (!node) return false;
  const t = node.type;
  return (
    t === "JSXElement" ||
    t === "JSXFragment" ||
    t === "JSXExpressionContainer"
  );
}

function localName(node) {
  // function name
  if (node?.id?.name) return node.id.name;
  return "Page";
}

for (const file of files) {
  const src = readFileSync(file, "utf8");

  // Skip static / dynamic-typed pages.
  if (/export\s+const\s+dynamic\b/.test(src) || /force-static/.test(src)) {
    note("static", file);
    continue;
  }
  // Skip pages whose body only redirects.
  if (/redirect\s*\(/.test(src)) {
    note("redirect", file);
    continue;
  }

  let ast;
  try {
    ast = recast.parse(src, { parser: { parse } });
  } catch (e) {
    note("parse-error", file);
    continue;
  }

  const b = recast.types.builders;
  let didWrap = false;
  let alreadyWrapped = false;

  recast.types.visit(ast, {
    visitExportDefaultDeclaration(path) {
      const decl = path.node.declaration;
      // Resolve: `export default function Foo() {}` or `export default Foo`
      let fnNode = null;
      if (decl.type === "FunctionDeclaration") {
        fnNode = decl;
      } else if (
        (decl.type === "Identifier" || decl.type === "FunctionExpression") &&
        false
      ) {
        fnNode = null;
      }

      if (fnNode) {
        const body = fnNode.body; // BlockStatement
        const stmts = body.body;
        if (stmts.length === 0) {
          note("empty-body", file);
          return false;
        }
        // Find the last ReturnStatement.
        let lastReturnIdx = -1;
        for (let i = stmts.length - 1; i >= 0; i--) {
          if (stmts[i].type === "ReturnStatement") {
            lastReturnIdx = i;
            break;
          }
        }
        if (lastReturnIdx === -1) {
          note("no-return", file);
          return false;
        }
        const ret = stmts[lastReturnIdx];
        const arg = ret.argument;
        if (!arg || !isJSX(arg)) {
          note("non-jsx-return", file);
          return false;
        }
        // Check if already wrapped.
        if (
          arg.type === "JSXElement" &&
          arg.openingElement.name.type === "JSXIdentifier" &&
          arg.openingElement.name.name === "ErrorBoundary"
        ) {
          alreadyWrapped = true;
          return false;
        }
        // Wrap: return (<ErrorBoundary>ARG</ErrorBoundary>)
        const opening = b.jsxOpeningElement(
          b.jsxIdentifier("ErrorBoundary"),
          [],
          false
        );
        const closing = b.jsxClosingElement(b.jsxIdentifier("ErrorBoundary"));
        const wrappedEl = b.jsxElement(opening, closing, [arg], false);
        ret.argument = wrappedEl;
        didWrap = true;
      }
      return false;
    },
  });

  if (alreadyWrapped) {
    note("already-wrapped", file);
    continue;
  }
  if (!didWrap) {
    continue;
  }

  // Inject the import if not present.
  const hasImport = /from\s+["']@\/components\/ErrorBoundary["']/.test(src);
  let out = recast.print(ast, { reuseWhitespace: true, quote: "double" }).code;
  if (!hasImport) {
    const importLine =
      'import { ErrorBoundary } from "@/components/ErrorBoundary";\n';
    // The directive ("use client" etc.) MUST stay first. Place the import
    // immediately after it; if there is no directive, place at the very top.
    const directiveMatch = out.match(
      /^\s*("use client"|"use strict";?'use client'|'use strict';?)\s*\n/
    );
    if (directiveMatch) {
      const cut = directiveMatch[0].length;
      out = out.slice(0, cut) + "\n" + importLine + out.slice(cut);
    } else {
      out = importLine + out;
    }
  }

  writeFileSync(file, out, "utf8");
  wrapped++;
}

console.log(`\n=== T5006 ErrorBoundary wrap summary ===`);
console.log(`Total page.tsx files: ${files.length}`);
console.log(`Wrapped: ${wrapped}`);
console.log(`Skipped: ${skipped}`);
for (const [reason, list] of Object.entries(skipReasons)) {
  console.log(`  - ${reason}: ${list.length}`);
  if (list.length <= 25) list.forEach((f) => console.log(`      ${f}`));
}
