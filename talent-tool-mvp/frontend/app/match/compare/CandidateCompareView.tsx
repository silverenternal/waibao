"use client";

/**
 * T2301 — 候选人对比视图 (客户端组件)
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertCircle, GitCompare, X } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { CompareTable, type CompareItem, type CompareDimension } from "@/components/compare/CompareTable";
import { CompareDiff, type DiffDimension } from "@/components/compare/CompareDiff";
import { SaveCompareButton } from "@/components/compare/SaveCompareButton";

interface CompareResponse {
  items: CompareItem[];
  diff_dimensions: CompareDimension[];
  highlights: DiffDimension[];
  created_at: string;
}

export function CandidateCompareView() {
  const searchParams = useSearchParams();
  const initialIds = (searchParams.get("ids") || "").split(",").filter(Boolean);

  const [idsText, setIdsText] = useState(initialIds.join(","));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CompareResponse | null>(null);

  async function runCompare(idList: string[]) {
    if (idList.length < 2) {
      setError("请输入 2-5 个候选人 ID");
      setData(null);
      return;
    }
    if (idList.length > 5) {
      setError("最多 5 个候选人");
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAPI<CompareResponse>(
        `/api/match/compare?ids=${encodeURIComponent(idList.join(","))}`
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "对比失败");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (initialIds.length >= 2) {
      runCompare(initialIds);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const ids = idsText.split(",").map((s) => s.trim()).filter(Boolean);
    runCompare(ids);
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 md:flex-row md:items-end">
            <div className="flex-1">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                候选人 ID (逗号分隔, 2-5 个)
              </label>
              <Input
                value={idsText}
                onChange={(e) => setIdsText(e.target.value)}
                placeholder="uuid1,uuid2,uuid3"
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                  对比中
                </>
              ) : (
                <>
                  <GitCompare className="w-4 h-4 mr-1.5" />
                  对比
                </>
              )}
            </Button>
            {data && (
              <SaveCompareButton
                itemType="candidate"
                itemIds={data.items.map((i) => i.id)}
                payload={data}
                defaultTitle={`候选人对比 (${data.items.length} 项)`}
              />
            )}
          </form>
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-300 text-sm">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>{error}</div>
          <button
            onClick={() => setError(null)}
            className="ml-auto opacity-70 hover:opacity-100"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {data && (
        <>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold">差异概览</h2>
                  <p className="text-xs text-muted-foreground">
                    共 {data.items.length} 项 · {data.diff_dimensions.length} 维度对齐
                  </p>
                </div>
                <div className="flex gap-2">
                  {data.highlights.slice(0, 3).map((h) => (
                    <Badge key={h.dimension} variant="secondary">
                      {h.label}: {h.spread.toFixed(1)}
                    </Badge>
                  ))}
                </div>
              </div>
              <CompareDiff
                items={data.items.map((it) => ({
                  id: it.id,
                  name: it.name,
                  values: Object.fromEntries(
                    Object.entries(it.dimensions).map(([k, v]) => [k, v.score])
                  ),
                }))}
                highlights={data.highlights}
              />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <h2 className="text-lg font-semibold mb-4">详细对比表</h2>
              <CompareTable
                items={data.items}
                dimensions={data.diff_dimensions}
              />
            </CardContent>
          </Card>
        </>
      )}

      {!data && !error && !loading && (
        <div className="text-sm text-muted-foreground py-12 text-center">
          输入候选人 ID 开始对比,或访问{" "}
          <code className="px-1.5 py-0.5 rounded bg-muted">
            /match/compare?ids=id1,id2
          </code>
        </div>
      )}
    </div>
  );
}