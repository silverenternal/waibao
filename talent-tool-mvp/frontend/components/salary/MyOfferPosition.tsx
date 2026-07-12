"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { locateOffer, type OfferPosition } from "@/lib/api-salary";

export interface MyOfferPositionProps {
  role: string;
  city: string;
  seniority: string;
  defaultOfferK?: number;
}

export function MyOfferPosition({
  role,
  city,
  seniority,
  defaultOfferK = 25,
}: MyOfferPositionProps) {
  const [offer, setOffer] = React.useState(defaultOfferK);
  const [result, setResult] = React.useState<OfferPosition | null>(null);
  const [loading, setLoading] = React.useState(false);

  const handleLocate = async () => {
    setLoading(true);
    try {
      const pos = await locateOffer(role, city, seniority, offer);
      setResult(pos);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    handleLocate();
  }, [role, city, seniority]);

  const recColor = {
    low: "bg-rose-100 text-rose-700",
    fair: "bg-amber-100 text-amber-700",
    competitive: "bg-emerald-100 text-emerald-700",
    high: "bg-blue-100 text-blue-700",
  }[result?.recommendation ?? "fair"];

  const recLabel = {
    low: "低于市场",
    fair: "合理区间",
    competitive: "有竞争力",
    high: "高于市场",
  }[result?.recommendation ?? "fair"];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">我的 Offer 在 P 几?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            type="number"
            value={offer}
            onChange={(e) => setOffer(Number(e.target.value))}
            placeholder="offer 月薪 (k)"
          />
          <Button onClick={handleLocate} disabled={loading}>
            {loading ? "查询中…" : "定位"}
          </Button>
        </div>
        {result && (
          <div className="space-y-2 pt-2 border-t">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">百分位</span>
              <span className="text-2xl font-bold text-amber-600">
                P{(result.percentile_rank).toFixed(0)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">市场 P50</span>
              <span>¥{result.p50_k}k</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">你的 offer</span>
              <span className="font-bold">¥{result.offer_k}k</span>
            </div>
            <div className={`text-center text-sm font-medium py-2 rounded ${recColor}`}>
              {recLabel}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}