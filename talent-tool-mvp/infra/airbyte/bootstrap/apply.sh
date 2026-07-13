#!/usr/bin/env bash
# T2801 — 一键注册 Airbyte source / destination / connection
# 用法: AIRBYTE_API_TOKEN=xxx ./apply.sh
set -euo pipefail

: "${AIRBYTE_URL:=http://localhost:8001}"
: "${AIRBYTE_API_TOKEN:?AIRBYTE_API_TOKEN required (在 Airbyte UI -> Settings -> Applications 生成)}"

WD=$(cd "$(dirname "$0")" && pwd)
H="Authorization: Bearer $AIRBYTE_API_TOKEN"
CT="Content-Type: application/json"

echo "==> 1) 替换 workspaceId 占位符"
# 第一次从 Airbyte 拉 workspaceId
WID=$(curl -fsS -H "$H" "$AIRBYTE_URL/api/v1/workspaces" | jq -r '.workspaces[0].workspaceId // .workspaces[0].id')
echo "    workspaceId = $WID"
for f in postgres-source.json clickhouse-destination.json connection.json; do
  sed -i.bak "s/REPLACE_WITH_AIRBYTE_WORKSPACE_ID/$WID/g" "$WD/$f"
done

echo "==> 2) 创建 Source (Supabase Postgres CDC)"
SOURCE=$(curl -fsS -H "$H" -H "$CT" \
  "$AIRBYTE_URL/api/v1/sources/source_postgres/create" \
  -d "$(jq '.connectionConfiguration' $WD/postgres-source.json | jq --arg wid "$WID" '. + {workspaceId:$wid} + {name:"Supabase Postgres"}')")
SOURCE_ID=$(echo "$SOURCE" | jq -r '.sourceId')
echo "    sourceId = $SOURCE_ID"

echo "==> 3) 创建 Destination (ClickHouse)"
DEST=$(curl -fsS -H "$H" -H "$CT" \
  "$AIRBYTE_URL/api/v1/destinations/destination_clickhouse/create" \
  -d "$(jq '.connectionConfiguration' $WD/clickhouse-destination.json | jq --arg wid "$WID" --arg sid "$SOURCE_ID" '. + {workspaceId:$wid} + {name:"ClickHouse Warehouse"}')")
DEST_ID=$(echo "$DEST" | jq -r '.destinationId')
echo "    destinationId = $DEST_ID"

echo "==> 4) 创建 Connection (hourly)"
# 注入 source / destination ID
PAYLOAD=$(jq --arg sid "$SOURCE_ID" --arg did "$DEST_ID" \
  '.sourceId=$sid | .destinationId=$did' $WD/connection.json)
CONN=$(curl -fsS -H "$H" -H "$CT" \
  "$AIRBYTE_URL/api/v1/connections/create" \
  -d "$PAYLOAD")
CONN_ID=$(echo "$CONN" | jq -r '.connectionId')
echo "    connectionId = $CONN_ID"

echo ""
echo "==> 完成! Airbyte 将每小时自动同步"
echo "    Source:      $SOURCE_ID"
echo "    Destination: $DEST_ID"
echo "    Connection:  $CONN_ID"
echo ""
echo "立即触发一次同步:"
echo "  curl -H \"$H\" -H \"$CT\" -X POST \\"
echo "    $AIRBYTE_URL/api/v1/connections/sync \\"
echo "    -d '{\"connectionId\":\"$CONN_ID\"}'"
