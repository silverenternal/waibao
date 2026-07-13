"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface Room {
  room_id: string;
  last_message_at?: string;
  participants?: string[];
  admin_id?: string;
}

interface Nudge {
  room_id: string;
  reason: string;
  severity: string;
  suggested_message: string;
  target_user: string;
}

interface Activation {
  action_type: string;
  detail: string;
  payload: Record<string, any>;
}

export function SilenceNudge() {
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [actions, setActions] = useState<Record<string, Activation[]>>({});
  const [loading, setLoading] = useState(false);

  const hoursAgo = (h: number) => new Date(Date.now() - h * 3600 * 1000).toISOString();

  const run = async () => {
    setLoading(true);
    try {
      const rooms: Room[] = [
        { room_id: "R-A", last_message_at: hoursAgo(2), participants: ["u1", "u2"], admin_id: "admin-x" },
        { room_id: "R-B", last_message_at: hoursAgo(30), participants: ["u3"], admin_id: "admin-y" },
        { room_id: "R-C", last_message_at: hoursAgo(72), participants: ["u4"], admin_id: "admin-z" },
      ];

      const r1 = await fetch("/api/v8_1_p2/silence/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rooms, silence_hours: 24 }),
      });
      if (r1.ok) {
        const data = await r1.json();
        setNudges(data.nudges);
      }

      const r2 = await fetch("/api/v8_1_p2/silence/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rooms, silence_hours: 24 }),
      });
      if (r2.ok) {
        const data = await r2.json();
        setActions(data.rooms);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>沉默激活 · Silence Nudge</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3707: 24h 没新消息自动 @ 管理员</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button disabled={loading} onClick={run}>扫描协作室</Button>

        {nudges.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">沉默</div>
            {nudges.map((n, i) => (
              <div key={i} className="border-l-2 pl-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={n.severity === "urgent" ? "destructive" : "secondary"}>
                    {n.severity}
                  </Badge>
                  <span className="font-medium">{n.room_id}</span>
                </div>
                <p className="text-xs text-muted-foreground">{n.reason}</p>
                <p className="text-xs italic mt-1">{n.suggested_message}</p>
              </div>
            ))}
          </div>
        )}

        {Object.keys(actions).length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">AI 建议动作</div>
            {Object.entries(actions).map(([rid, acts]) => (
              <div key={rid} className="rounded border p-2 text-sm">
                <div className="font-medium">{rid}</div>
                {acts.map((a, i) => (
                  <div key={i} className="ml-2 mt-1">
                    <Badge variant="outline">{a.action_type}</Badge>
                    <span className="ml-2 text-xs">{a.detail}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SilenceNudge;
