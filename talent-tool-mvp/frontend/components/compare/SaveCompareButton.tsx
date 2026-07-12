"use client";

/**
 * T2301 — SaveCompareButton
 * 保存对比快照按钮.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Bookmark, Loader2, Check } from "lucide-react";
import { fetchAPI } from "@/lib/api";

interface SaveCompareButtonProps {
  itemType: "candidate" | "role";
  itemIds: string[];
  payload: unknown;
  defaultTitle?: string;
  onSaved?: (saved: { id: string; title: string }) => void;
  className?: string;
}

export function SaveCompareButton({
  itemType,
  itemIds,
  payload,
  defaultTitle,
  onSaved,
  className,
}: SaveCompareButtonProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(defaultTitle ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetchAPI<{ id: string; title: string }>(
        "/api/match/compare/save",
        {
          method: "POST",
          body: JSON.stringify({
            item_type: itemType,
            item_ids: itemIds,
            payload,
            title: title || defaultTitle || undefined,
          }),
        }
      );
      setSavedId(res.id);
      onSaved?.(res);
      setTimeout(() => {
        setOpen(false);
        setSavedId(null);
        setTitle("");
      }, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        className={className}
        onClick={() => setOpen(true)}
      >
        <Bookmark className="w-4 h-4 mr-1.5" />
        保存对比
      </Button>
    );
  }

  return (
    <div className={className}>
      <div className="flex flex-col gap-2 p-3 border rounded-lg bg-card">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="对比标题 (可选)"
          disabled={saving || !!savedId}
        />
        {error && (
          <div className="text-xs text-red-500">{error}</div>
        )}
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || !!savedId}
            className="flex-1"
          >
            {saving ? (
              <>
                <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />
                保存中
              </>
            ) : savedId ? (
              <>
                <Check className="w-3 h-3 mr-1.5" />
                已保存
              </>
            ) : (
              "确认保存"
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setOpen(false);
              setTitle("");
              setError(null);
            }}
            disabled={saving}
          >
            取消
          </Button>
        </div>
      </div>
    </div>
  );
}