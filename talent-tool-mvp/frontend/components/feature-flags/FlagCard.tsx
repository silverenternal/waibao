"use client";

/**
 * v6.0 T2103 — FlagCard.
 *
 * Visualises a single feature flag row: name, description, enabled toggle,
 * rollout slider, overrides list. Used by the admin /feature-flags page.
 */

import * as React from "react";
import { RolloutSlider } from "./RolloutSlider";

export interface FlagOverride {
  id?: number;
  user_id?: string | null;
  org_id?: string | null;
  flag_name: string;
  value: boolean;
  reason?: string;
  expires_at?: string | null;
}

export interface FlagRecord {
  id?: number;
  name: string;
  description: string;
  rules: Record<string, any>;
  rollout_percent: number;
  enabled: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface FlagCardProps {
  flag: FlagRecord;
  overrides: FlagOverride[];
  onSave: (next: Partial<FlagRecord>) => Promise<void>;
  onAddOverride: (
    payload: Omit<FlagOverride, "id" | "flag_name">
  ) => Promise<void>;
  onRemoveOverride: (ov: FlagOverride) => Promise<void>;
  onDelete: () => Promise<void>;
  saving?: boolean;
}

export function FlagCard(props: FlagCardProps): JSX.Element {
  const { flag, overrides, onSave, onAddOverride, onRemoveOverride, onDelete, saving } = props;
  const [rollout, setRollout] = React.useState<number>(flag.rollout_percent);
  const [enabled, setEnabled] = React.useState<boolean>(flag.enabled);
  const [description, setDescription] = React.useState<string>(flag.description);
  const [dirty, setDirty] = React.useState(false);

  // New override form state
  const [ovUserId, setOvUserId] = React.useState("");
  const [ovOrgId, setOvOrgId] = React.useState("");
  const [ovValue, setOvValue] = React.useState(true);
  const [ovReason, setOvReason] = React.useState("");

  React.useEffect(() => {
    setRollout(flag.rollout_percent);
    setEnabled(flag.enabled);
    setDescription(flag.description);
    setDirty(false);
  }, [flag.name, flag.rollout_percent, flag.enabled, flag.description]);

  const onClickSave = async () => {
    await onSave({
      rollout_percent: rollout,
      enabled,
      description,
    });
    setDirty(false);
  };

  const onClickAddOverride = async () => {
    if (!ovUserId && !ovOrgId) return;
    await onAddOverride({
      user_id: ovUserId || null,
      org_id: ovOrgId || null,
      value: ovValue,
      reason: ovReason,
    });
    setOvUserId("");
    setOvOrgId("");
    setOvReason("");
  };

  const status = enabled
    ? rollout >= 100
      ? "全网启用"
      : rollout > 0
      ? `灰度 ${rollout}%`
      : "开启 (白名单)"
    : "关闭";

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      data-testid={`flag-card-${flag.name}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-mono text-base font-semibold text-slate-900">{flag.name}</h3>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                enabled
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {status}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">{description || "—"}</p>
          {flag.updated_at && (
            <p className="mt-1 text-xs text-slate-400">
              updated {new Date(flag.updated_at).toLocaleString()}
              {flag.updated_by ? ` by ${flag.updated_by}` : ""}
            </p>
          )}
        </div>
        <button
          type="button"
          className="text-xs text-rose-600 hover:underline"
          onClick={onDelete}
          aria-label={`delete flag ${flag.name}`}
        >
          delete
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">描述</span>
          <input
            type="text"
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm"
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setDirty(true);
            }}
            placeholder="What this flag does"
          />
        </label>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => {
              setEnabled(e.target.checked);
              setDirty(true);
            }}
            className="h-4 w-4"
          />
          <span className="font-medium text-slate-700">
            启用 (enabled=true → 全网生效)
          </span>
        </label>
      </div>

      <div className="mt-4">
        <RolloutSlider
          value={rollout}
          onChange={(v) => {
            setRollout(v);
            setDirty(true);
          }}
        />
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={!dirty || saving}
          onClick={onClickSave}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "保存中…" : "保存"}
        </button>
      </div>

      {/* Overrides */}
      <div className="mt-6 border-t border-slate-100 pt-4">
        <h4 className="text-sm font-semibold text-slate-700">
          白名单 / 黑名单 ({overrides.length})
        </h4>
        {overrides.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">暂无 override</p>
        ) : (
          <ul className="mt-2 space-y-1">
            {overrides.map((ov, idx) => (
              <li
                key={`${ov.user_id ?? ov.org_id ?? idx}-${idx}`}
                className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-1.5 text-xs"
              >
                <span className="font-mono text-slate-700">
                  {ov.user_id ? `user:${ov.user_id}` : `org:${ov.org_id}`}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 ${
                    ov.value
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {ov.value ? "force-on" : "force-off"}
                </span>
                <span className="flex-1 truncate text-slate-500">{ov.reason}</span>
                <button
                  type="button"
                  className="text-rose-600 hover:underline"
                  onClick={() => onRemoveOverride(ov)}
                >
                  remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-5">
          <input
            type="text"
            placeholder="user_id (可选)"
            className="rounded-md border border-slate-200 px-2 py-1 text-xs"
            value={ovUserId}
            onChange={(e) => setOvUserId(e.target.value)}
          />
          <input
            type="text"
            placeholder="org_id (可选)"
            className="rounded-md border border-slate-200 px-2 py-1 text-xs"
            value={ovOrgId}
            onChange={(e) => setOvOrgId(e.target.value)}
          />
          <select
            value={ovValue ? "on" : "off"}
            onChange={(e) => setOvValue(e.target.value === "on")}
            className="rounded-md border border-slate-200 px-2 py-1 text-xs"
          >
            <option value="on">force-on</option>
            <option value="off">force-off</option>
          </select>
          <input
            type="text"
            placeholder="reason"
            className="rounded-md border border-slate-200 px-2 py-1 text-xs"
            value={ovReason}
            onChange={(e) => setOvReason(e.target.value)}
          />
          <button
            type="button"
            className="rounded-md bg-slate-700 px-2 py-1 text-xs text-white"
            onClick={onClickAddOverride}
            disabled={!ovUserId && !ovOrgId}
          >
            添加 override
          </button>
        </div>
      </div>
    </div>
  );
}