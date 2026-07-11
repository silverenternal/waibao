"use client";

import * as React from "react";
import { API_KEY_SCOPES, type ApiKeyScope } from "@/lib/api-public-keys";

interface Props {
  value: ApiKeyScope[];
  onChange: (next: ApiKeyScope[]) => void;
}

/**
 * 公开 API scope 多选 (T803).
 * 合法 scope: candidates:read / candidates:write / roles:read /
 *             matches:write / tickets:write.
 */
export function ScopeMultiSelect({ value, onChange }: Props) {
  function toggle(s: ApiKeyScope) {
    if (value.includes(s)) onChange(value.filter((x) => x !== s));
    else onChange([...value, s]);
  }
  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-600">
        选择此 Key 允许访问的 API (scope).
      </div>
      <div className="flex flex-wrap gap-2">
        {API_KEY_SCOPES.map((s) => {
          const selected = value.includes(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggle(s)}
              className={`px-2.5 py-1 rounded text-xs font-mono border transition-colors ${
                selected
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-700 border-slate-300 hover:border-blue-400"
              }`}
            >
              {s}
            </button>
          );
        })}
      </div>
      {value.length === 0 && (
        <div className="text-[11px] text-amber-600">
          未选择任何 scope;Key 将无法访问任何端点。
        </div>
      )}
    </div>
  );
}
