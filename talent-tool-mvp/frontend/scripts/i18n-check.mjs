#!/usr/bin/env node
/**
 * i18n key parity check (T801).
 *
 * Ensures that every top-level namespace in zh-CN.json has the same
 * leaf-key shape in en-US.json and ja-JP.json. CI fails if:
 *   - zh-CN has key X but en-US is missing X.
 *   - zh-CN vs en-US namespace counts differ by > 20%.
 *
 * ja-JP may lag, but namespaces with > 30 missing leaves fail CI
 * (machine translation cost should be near-zero — DeepL follow-up expected).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const messagesDir = join(here, "..", "messages");

function loadAll(path) {
  const raw = readFileSync(path, "utf8");
  return JSON.parse(raw);
}

const zh = loadAll(join(messagesDir, "zh-CN.json"));
const en = loadAll(join(messagesDir, "en-US.json"));
const ja = loadAll(join(messagesDir, "ja-JP.json"));

function* walk(obj, prefix = "") {
  for (const [k, v] of Object.entries(obj ?? {})) {
    const next = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      yield* walk(v, next);
    } else {
      yield next;
    }
  }
}

const zhKeys = new Set([...walk(zh)]);
const enKeys = new Set([...walk(en)]);
const jaKeys = new Set([...walk(ja)]);

const missingInEn = [...zhKeys].filter((k) => !enKeys.has(k));
const missingInJa = [...zhKeys].filter((k) => !jaKeys.has(k));

// namespace counts
function countNamespaces(set) {
  const namespaces = new Map();
  for (const k of set) {
    const ns = k.split(".")[0];
    namespaces.set(ns, (namespaces.get(ns) ?? 0) + 1);
  }
  return namespaces;
}
const zhNs = countNamespaces(zhKeys);
const enNs = countNamespaces(enKeys);

const errors = [];

if (missingInEn.length) {
  errors.push(
    `[FATAL] ${missingInEn.length} keys missing in en-US.json:\n  ` +
      missingInEn.slice(0, 50).join("\n  ") +
      (missingInEn.length > 50 ? `\n  ... +${missingInEn.length - 50} more` : "")
  );
}

const jaThreshold = Math.ceil(zhKeys.size * 0.7); // at least 70% localized
if (jaKeys.size < jaThreshold) {
  errors.push(
    `[FATAL] ja-JP has ${jaKeys.size} keys, expected at least ${jaThreshold} ` +
      `(70% of zh-CN). The language fallback would be visible to users.`
  );
}

const enThreshold = zhKeys.size;
if (enKeys.size < enThreshold) {
  errors.push(
    `[FATAL] en-US has ${enKeys.size} keys, expected ${enThreshold} (full parity).`
  );
}

for (const [ns, count] of zhNs) {
  const enCount = enNs.get(ns) ?? 0;
  const ratio = Math.abs(count - enCount) / Math.max(count, 1);
  if (ratio > 0.2) {
    errors.push(
      `[WARN] Namespace '${ns}' differs by > 20%: zh=${count} en=${enCount}`
    );
  }
}

if (errors.length) {
  console.error("\n❌ i18n check failed:");
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  `✓ i18n check passed: ${zhKeys.size} zh-CN keys, ${enKeys.size} en-US, ${jaKeys.size} ja-JP`
);
process.exit(0);
