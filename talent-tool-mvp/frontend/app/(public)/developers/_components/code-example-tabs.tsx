"use client";

import { useState } from "react";

const EXAMPLES: Record<string, { lang: string; code: string }> = {
  curl: {
    lang: "cURL",
    code: `# 1) Register a developer app (returns client_id + client_secret once)
curl -X POST https://api.recruittech.com/api/developer/apps \\
  -H "Authorization: Bearer $USER_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Acme ATS",
    "homepage_url": "https://acme.example.com",
    "redirect_uris": ["https://acme.example.com/cb"],
    "scopes": ["candidates:read", "matches:write"],
    "environment": "sandbox"
  }'

# 2) Mint a server-side API key bound to the app
curl -X POST https://api.recruittech.com/api/developer/apps/$APP_ID/keys \\
  -H "Authorization: Bearer $USER_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{ "name": "primary", "scopes": ["candidates:read"] }'

# 3) Call the API
curl https://api.recruittech.com/api/v2/candidates \\
  -H "Authorization: Bearer wb_live_..."`,
  },
  python: {
    lang: "Python",
    code: `from recruittech import Client

client = Client(api_key="wb_live_...", environment="sandbox")

# List candidates (paged iterator)
for c in client.candidates.list(limit=50):
    print(c.id, c.full_name)

# Score a candidate against a role
score = client.matches.create(
    candidate_id="cand_123",
    role_id="role_456",
)
print(score.composite, score.breakdown)`,
  },
  typescript: {
    lang: "TypeScript",
    code: `import { RecruitTech } from "@recruittech/sdk";

const client = new RecruitTech({
  apiKey: process.env.RECRUIT_API_KEY!,
  environment: "sandbox",
});

const { data: candidates } = await client.candidates.list({ limit: 50 });

const score = await client.matches.create({
  candidate_id: "cand_123",
  role_id: "role_456",
});
console.log(score.composite, score.breakdown);`,
  },
  go: {
    lang: "Go",
    code: `package main

import (
    "context"
    "fmt"
    "github.com/recruittech/sdk-go/recruittech"
)

func main() {
    client := recruittech.New("wb_live_...", recruittech.Sandbox)

    candidates, _, err := client.Candidates.List(context.Background(), &recruittech.CandidateListParams{
        Limit: 50,
    })
    if err != nil {
        panic(err)
    }
    for _, c := range candidates {
        fmt.Println(c.ID, c.FullName)
    }
}`,
  },
};

const ORDER = ["curl", "python", "typescript", "go"] as const;
type TabKey = (typeof ORDER)[number];

export function CodeExampleTabs() {
  const [active, setActive] = useState<TabKey>("curl");
  const example = EXAMPLES[active];

  return (
    <div className="rounded-lg border border-border">
      <div className="flex flex-wrap gap-1 border-b border-border bg-muted/30 px-2 py-2">
        {ORDER.map((key) => (
          <button
            type="button"
            key={key}
            onClick={() => setActive(key)}
            className={
              "rounded px-3 py-1 text-xs font-medium transition-colors " +
              (active === key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted")
            }
          >
            {EXAMPLES[key].lang}
          </button>
        ))}
      </div>
      <pre className="overflow-x-auto p-4 text-xs leading-relaxed">
        <code>{example.code}</code>
      </pre>
    </div>
  );
}
