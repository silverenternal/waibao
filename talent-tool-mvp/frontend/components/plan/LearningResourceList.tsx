"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, Clock, Star, Tag } from "lucide-react";
import type { LearningResource } from "@/lib/api-learning";

interface Props {
  items: LearningResource[];
  emptyText?: string;
}

const LEVEL_LABEL: Record<string, string> = {
  beginner: "入门",
  intermediate: "进阶",
  advanced: "高级",
};

const PROVIDER_COLOR: Record<string, string> = {
  coursera: "bg-blue-100 text-blue-700",
  geekbang: "bg-orange-100 text-orange-700",
  juejin: "bg-cyan-100 text-cyan-700",
  imooc: "bg-green-100 text-green-700",
  bilibili: "bg-pink-100 text-pink-700",
  fallback: "bg-slate-100 text-slate-700",
};

export function LearningResourceList({ items, emptyText = "暂无资源" }: Props) {
  if (!items || items.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {items.map((item, idx) => {
        const color =
          PROVIDER_COLOR[item.provider] || PROVIDER_COLOR.fallback;
        return (
          <Card key={`${item.provider}-${idx}`} className="overflow-hidden">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold leading-snug">
                    {item.title}
                  </h4>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs">
                    <Badge className={color} variant="secondary">
                      {item.provider}
                    </Badge>
                    <span className="text-muted-foreground">
                      {LEVEL_LABEL[item.level] || item.level}
                    </span>
                    {item.rating > 0 && (
                      <span className="inline-flex items-center gap-0.5 text-amber-600">
                        <Star className="h-3 w-3 fill-current" />
                        {item.rating.toFixed(1)}
                      </span>
                    )}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="shrink-0"
                  onClick={() => item.url && window.open(item.url, "_blank", "noreferrer")}
                  aria-label={`打开 ${item.title}`}
                >
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                {item.duration_hours > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {item.duration_hours.toFixed(1)}h
                  </span>
                )}
                {item.price !== undefined && (
                  <span>
                    {item.price > 0 ? `¥${item.price}` : "免费"}
                  </span>
                )}
                {item.language && (
                  <span>{item.language === "en" ? "英文" : "中文"}</span>
                )}
                {item.source === "fallback" && (
                  <Badge variant="outline" className="text-[10px]">
                    离线兜底
                  </Badge>
                )}
              </div>
              {item.skill_tags && item.skill_tags.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 text-[11px]">
                  <Tag className="h-3 w-3 text-muted-foreground" />
                  {item.skill_tags.slice(0, 4).map((t) => (
                    <span
                      key={t}
                      className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export default LearningResourceList;