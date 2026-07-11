/**
 * CostByTenantTable (T806).
 */
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TenantCost } from "@/lib/api-cost";

interface CostByTenantTableProps {
  data: TenantCost[];
}

export function CostByTenantTable({ data }: CostByTenantTableProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cost by Tenant</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground py-8 text-center">
          No tenant cost data yet.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cost by Tenant</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full text-sm min-w-[400px]">
            <thead className="bg-muted text-xs">
              <tr>
                <th className="text-left px-3 py-2">Tenant</th>
                <th className="text-right px-3 py-2">Cost (USD)</th>
                <th className="text-right px-3 py-2">Share</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const total = data.reduce((s, d) => s + d.cost_usd, 0) || 1;
                return data.map((row) => (
                  <tr key={row.tenant_id} className="border-t">
                    <td className="px-3 py-2 font-medium">{row.tenant_id}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      ${row.cost_usd.toFixed(4)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                      {((row.cost_usd / total) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ));
              })()}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
