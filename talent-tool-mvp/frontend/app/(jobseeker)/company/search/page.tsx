"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { searchCompanies } from "@/lib/api-company-review";

/**
 * 公司搜索页 (T2401).
 *
 * 按名称模糊搜索,显示公司基础信息 + 评分.
 */
export default function CompanySearchPage() {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<
    Array<{ id: string; name: string; industry: string; rating: number }>
  >([]);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      searchCompanies(query, 20)
        .then((r) => setResults(r.results))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="container mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">公司搜索</h1>
      <Input
        placeholder="输入公司名称 (例如 字节 / bytedance / Tencent)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      {loading && (
        <div className="text-sm text-slate-500">搜索中…</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {results.map((c) => (
          <a key={c.id} href={`/company/${c.id}`}>
            <Card className="hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{c.name}</div>
                    <div className="text-xs text-slate-500">{c.industry}</div>
                  </div>
                  <div className="text-amber-600 font-bold">
                    ★ {c.rating.toFixed(1)}
                  </div>
                </div>
              </CardContent>
            </Card>
          </a>
        ))}
      </div>
      {!loading && query && results.length === 0 && (
        <div className="text-sm text-slate-500">未找到匹配的公司</div>
      )}
    </div>
  );
}