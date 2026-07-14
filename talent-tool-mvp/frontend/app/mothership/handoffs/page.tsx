"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Handoff, HandoffCreate, Candidate, Role, User } from "@/contracts/canonical";
import { apiClient } from "@/lib/api-client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { HandoffCard } from "@/components/mothership/handoff-card";
import { HandoffSendDialog } from "@/components/mothership/handoff-send-dialog";
import { HandoffRespondDialog } from "@/components/mothership/handoff-respond-dialog";
import { HandoffTimeline } from "@/components/mothership/handoff-timeline";
import { Send, Inbox, SendHorizontal, ArrowLeft } from "lucide-react";

export default function HandoffsPage() {
  const qc = useQueryClient();
  const [sendOpen, setSendOpen] = useState(false);
  const [respondTarget, setRespondTarget] = useState<{ handoff: Handoff; action: "accept" | "decline" } | null>(null);
  const [detailHandoff, setDetailHandoff] = useState<Handoff | null>(null);

  // T5007 — declarative data fetching via TanStack Query.
  const { data: inbox = [], isLoading: inboxLoading } = useQuery({
    queryKey: ["handoffs", "inbox"],
    queryFn: () => apiClient.handoffs.inbox(),
  });
  const { data: outbox = [] } = useQuery({
    queryKey: ["handoffs", "outbox"],
    queryFn: () => apiClient.handoffs.outbox(),
  });
  const { data: candidates = [] } = useQuery({
    queryKey: ["candidates", "list"],
    queryFn: () => apiClient.candidates.list(),
  });
  const { data: roles = [] } = useQuery({
    queryKey: ["roles", "list"],
    queryFn: () => apiClient.roles.list(),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => apiClient.admin.users(),
  });
  const partners: User[] = users.filter((u) => u.role === "talent_partner");
  const loading = inboxLoading;

  const sendMutation = useMutation({
    mutationFn: (data: HandoffCreate) => apiClient.handoffs.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["handoffs"] });
      toast.success("Handoff sent successfully");
    },
    onError: () => toast.error("Failed to send handoff"),
  });

  const respondMutation = useMutation({
    mutationFn: (vars: { id: string; accept: boolean; notes: string }) =>
      apiClient.handoffs.respond(vars.id, vars.accept, vars.notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["handoffs"] });
    },
    onError: () => toast.error("Failed to respond to handoff"),
  });

  function handleSend(data: HandoffCreate) {
    sendMutation.mutate(data);
  }

  function handleRespond(accept: boolean, notes: string) {
    if (!respondTarget) return;
    respondMutation.mutate(
      { id: respondTarget.handoff.id, accept, notes },
      {
        onSuccess: () => {
          setRespondTarget(null);
          toast.success(accept ? "Handoff accepted" : "Handoff declined");
        },
      },
    );
  }

  // Detail view with timeline
  if (detailHandoff) {
    return (
      <div className="p-4 md:p-6 max-w-3xl">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setDetailHandoff(null)}
          className="mb-4"
        >
          <ArrowLeft className="h-4 w-4 mr-1.5" />
          Back to handoffs
        </Button>
        <h2 className="text-xl font-semibold mb-6">Handoff Details</h2>
        <HandoffTimeline handoff={detailHandoff} />
      </div>
    );
  }

  const pendingCount = inbox.filter((h) => h.status === "pending").length;

  return (
    <ErrorBoundary>(<div className="p-0 max-w-4xl">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Handoffs</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Share candidates with partners and track referral attribution.
            </p>
          </div>
          <Button onClick={() => setSendOpen(true)}>
            <Send className="h-4 w-4 mr-1.5" />
            Send Handoff
          </Button>
        </div>
        <Tabs defaultValue="inbox">
          <TabsList>
            <TabsTrigger value="inbox" className="gap-1.5">
              <Inbox className="h-4 w-4" />
              Inbox
              {pendingCount > 0 && (
                <span className="ml-1 rounded-full bg-blue-500/10 text-blue-400 px-2 py-0.5 text-xs font-medium">
                  {pendingCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="outbox" className="gap-1.5">
              <SendHorizontal className="h-4 w-4" />
              Outbox
            </TabsTrigger>
          </TabsList>

          <TabsContent value="inbox" className="mt-4 space-y-3">
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28 rounded-lg" />
              ))
            ) : inbox.length === 0 ? (
              <div className="text-center py-12 border rounded-lg border-dashed">
                <Inbox className="h-10 w-10 mx-auto text-muted-foreground/50 mb-3" />
                <p className="text-muted-foreground">No handoffs received yet.</p>
                <p className="text-sm text-muted-foreground mt-1">
                  When a partner shares candidates with you, they will appear here.
                </p>
              </div>
            ) : (
              inbox.map((handoff) => (
                <HandoffCard
                  key={handoff.id}
                  handoff={handoff}
                  direction="inbox"
                  onAccept={() => setRespondTarget({ handoff, action: "accept" })}
                  onDecline={() => setRespondTarget({ handoff, action: "decline" })}
                  onViewDetail={() => setDetailHandoff(handoff)}
                />
              ))
            )}
          </TabsContent>

          <TabsContent value="outbox" className="mt-4 space-y-3">
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28 rounded-lg" />
              ))
            ) : outbox.length === 0 ? (
              <div className="text-center py-12 border rounded-lg border-dashed">
                <SendHorizontal className="h-10 w-10 mx-auto text-muted-foreground/50 mb-3" />
                <p className="text-muted-foreground">No handoffs sent yet.</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => setSendOpen(true)}
                >
                  Send your first handoff
                </Button>
              </div>
            ) : (
              outbox.map((handoff) => (
                <HandoffCard
                  key={handoff.id}
                  handoff={handoff}
                  direction="outbox"
                  onViewDetail={() => setDetailHandoff(handoff)}
                />
              ))
            )}
          </TabsContent>
        </Tabs>
        {/* Send dialog */}
        <HandoffSendDialog
          open={sendOpen}
          onOpenChange={setSendOpen}
          onSubmit={handleSend}
          candidates={candidates}
          partners={partners}
          roles={roles}
        />
        {/* Respond dialog */}
        {respondTarget && (
          <HandoffRespondDialog
            open={!!respondTarget}
            onOpenChange={() => setRespondTarget(null)}
            onRespond={handleRespond}
            action={respondTarget.action}
          />
        )}
      </div>)</ErrorBoundary>
  );
}
