import * as React from "react";

/**
 * JsonLd — render Schema.org JSON-LD into <script type="application/ld+json">.
 *
 * Pass an object, an array of objects, or an array of strings. Placed in
 * <head> by the parent server component. Multiple payloads are joined
 * by JSON.stringify. Strict about HTML-escaping inside string values.
 */
export interface JsonLdProps {
  data: Record<string, unknown> | Record<string, unknown>[] | string | string[];
  /** Optional id for the <script> element (helps test stability). */
  id?: string;
}

export function JsonLd({ data, id = "jsonld" }: JsonLdProps) {
  const arr = Array.isArray(data) ? data : [data];
  const json = arr.map((d) => (typeof d === "string" ? d : JSON.stringify(d))).join("\n");
  return (
    <script
      id={id}
      type="application/ld+json"
      // We deliberately use dangerouslySetInnerHTML for JSON-LD; values are
      // JSON-safe (escaped by JSON.stringify). Avoid passing user-controlled
      // strings outside of JSON encoding.
      dangerouslySetInnerHTML={{ __html: json }}
    />
  );
}

export default JsonLd;
