"use client";

import React, { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Schedule {
  slots: Array<{
    scheduled_at: string;
    hour: number;
    audience: string;
    template: string;
  }>;
}

export function NotificationBell() {
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    fetch("/api/v8_1_p2/silence/schedule")
      .then(r => r.json())
      .then(setSchedule)
      .catch(() => undefined);
  }, []);

  return (
    <div className="relative inline-block">
      <button className="relative p-2">
        <Bell className="w-5 h-5" />
        {count > 0 && (
          <Badge variant="destructive" className="absolute -top-1 -right-1 px-1 py-0">
            {count}
          </Badge>
        )}
      </button>

      {schedule && (
        <Card className="absolute right-0 mt-2 w-72 z-50">
          <CardHeader>
            <CardTitle className="text-sm">今天还会推送</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs">
            {schedule.slots.map((s, i) => (
              <div key={i} className="flex justify-between">
                <span>{s.hour}:00</span>
                <span className="text-muted-foreground">{s.audience} · {s.template}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default NotificationBell;
