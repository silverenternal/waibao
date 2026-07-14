"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Database,
  FileText,
  MessagesSquare,
  Plus,
  Trash2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  type RagCollection,
  type RagDocument,
  createCollection,
  listCollections,
  listDocuments,
} from "@/lib/api-rag";
import DocumentUpload, { type UploadedDocument } from "@/components/rag/DocumentUpload";
import ChatWithCitations, { type Citation } from "@/components/rag/ChatWithCitations";

const SAMPLE_TENANT_ID = "demo-tenant";

const SAMPLE_COLLECTIONS: RagCollection[] = [
  {
    id: "demo-collection-handbook",
    tenant_id: SAMPLE_TENANT_ID,
    name: "员工手册",
    description: "公司政策、福利、行为准则",
    embedding_model: "bge-large-en-v1.5",
    embedding_dim: 1024,
    qdrant_collection: "tenant_demo_handbook",
    chunk_size: 512,
    chunk_overlap: 50,
    is_active: true,
    created_at: new Date().toISOString(),
  },
];

const SAMPLE_DOCUMENTS: RagDocument[] = [
  {
    id: "demo-doc-1",
    collection_id: "demo-collection-handbook",
    name: "handbook-2026.pdf",
    display_name: "员工手册 2026 版",
    source: "upload",
    mime_type: "application/pdf",
    size_bytes: 1_245_678,
    status: "indexed",
    total_chunks: 87,
    total_tokens: 18_400,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "demo-doc-2",
    collection_id: "demo-collection-handbook",
    name: "benefits-2026.md",
    display_name: "福利政策 2026",
    source: "upload",
    mime_type: "text/markdown",
    size_bytes: 32_120,
    status: "indexed",
    total_chunks: 12,
    total_tokens: 3_240,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export default function KnowledgePage() {
  const [collections, setCollections] = React.useState<RagCollection[]>(SAMPLE_COLLECTIONS);
  const [documents, setDocuments] = React.useState<RagDocument[]>(SAMPLE_DOCUMENTS);
  const [activeCollection, setActiveCollection] = React.useState<string>(
    SAMPLE_COLLECTIONS[0]?.id ?? "",
  );
  const [loading, setLoading] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cs = await listCollections();
      if (cs.length) setCollections(cs);
      if (activeCollection) {
        const ds = await listDocuments(activeCollection);
        if (ds.length) setDocuments(ds);
      }
    } catch {
      // fall back to sample data on error
    } finally {
      setLoading(false);
    }
  }, [activeCollection]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setError(null);
    try {
      const c = await createCollection({ name, embedding_model: "bge-large-en-v1.5" });
      setCollections((prev) => [c, ...prev]);
      setActiveCollection(c.id);
      setNewName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create collection");
    }
  };

  const handleUploaded = (doc: UploadedDocument) => {
    setDocuments((prev) => [
      {
        id: doc.id,
        collection_id: activeCollection,
        name: doc.display_name,
        display_name: doc.display_name,
        source: "upload",
        mime_type: doc.mime_type ?? null,
        size_bytes: doc.size_bytes,
        status: doc.status,
        total_chunks: doc.total_chunks,
        total_tokens: doc.total_tokens,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      ...prev,
    ]);
  };

  const handleCitation = (c: Citation) => {
    // open document/chunk in a side panel — simplified to alert for now
    if (typeof window !== "undefined") {
      window.console.log("citation", c);
    }
  };

  const activeColl = collections.find((c) => c.id === activeCollection);

  return (
    <ErrorBoundary>(<div className="container mx-auto max-w-7xl space-y-6 p-6">
        <header className="flex items-start justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold">
              <Database className="h-6 w-6" />
              知识库 (Knowledge Base)
            </h1>
            <p className="text-sm text-muted-foreground">
              上传公司文档,基于 LlamaIndex + Qdrant 检索,带源引用的对话式问答。
            </p>
          </div>
          <Button onClick={refresh} variant="outline" size="sm" disabled={loading}>
            <RefreshCw className={"mr-1 h-4 w-4" + (loading ? " animate-spin" : "")} />
            刷新
          </Button>
        </header>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">集合数</CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-bold">{collections.length}</CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">文档数</CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-bold">{documents.length}</CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">总 chunks</CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-bold">
              {documents.reduce((a, d) => a + d.total_chunks, 0)}
            </CardContent>
          </Card>
        </div>
        <Tabs defaultValue="manage" className="space-y-4">
          <TabsList>
            <TabsTrigger value="manage">
              <FileText className="mr-1 h-4 w-4" /> 管理
            </TabsTrigger>
            <TabsTrigger value="chat">
              <MessagesSquare className="mr-1 h-4 w-4" /> 对话
            </TabsTrigger>
          </TabsList>

          <TabsContent value="manage" className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <Card className="md:col-span-1">
                <CardHeader>
                  <CardTitle className="text-base">集合</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {collections.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setActiveCollection(c.id)}
                      className={
                        "w-full rounded-md border p-3 text-left text-sm transition " +
                        (c.id === activeCollection
                          ? "border-primary bg-primary/5"
                          : "hover:border-primary/40")
                      }
                    >
                      <div className="font-medium">{c.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {c.embedding_model} · dim {c.embedding_dim} · chunk {c.chunk_size}/{c.chunk_overlap}
                      </div>
                    </button>
                  ))}
                  <div className="flex gap-1 pt-2">
                    <input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="新集合名"
                      className="flex-1 rounded-md border bg-background px-2 py-1 text-sm"
                    />
                    <Button size="sm" onClick={handleCreate}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {error && <p className="text-xs text-destructive">{error}</p>}
                </CardContent>
              </Card>

              <div className="space-y-4 md:col-span-2">
                {activeCollection ? (
                  <>
                    <DocumentUpload
                      collectionId={activeCollection}
                      onUploaded={handleUploaded}
                    />
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">
                          文档 ({documents.filter((d) => d.collection_id === activeCollection).length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-2">
                          {documents
                            .filter((d) => d.collection_id === activeCollection)
                            .map((d) => (
                              <div
                                key={d.id}
                                className="flex items-center gap-3 rounded-md border p-3 text-sm"
                              >
                                <FileText className="h-4 w-4 text-muted-foreground" />
                                <div className="flex-1">
                                  <div className="font-medium">{d.display_name}</div>
                                  <div className="text-xs text-muted-foreground">
                                    {d.total_chunks} chunks · {d.total_tokens} tokens · {(d.size_bytes / 1024).toFixed(1)} KB
                                  </div>
                                </div>
                                <Badge
                                  variant={d.status === "indexed" ? "secondary" : "outline"}
                                >
                                  {d.status}
                                </Badge>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  onClick={() =>
                                    setDocuments((prev) => prev.filter((x) => x.id !== d.id))
                                  }
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                        </div>
                      </CardContent>
                    </Card>
                  </>
                ) : (
                  <Card>
                    <CardContent className="p-8 text-center text-muted-foreground">
                      请先创建或选择一个集合。
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="chat">
            {activeCollection ? (
              <ChatWithCitations
                collectionId={activeCollection}
                onCitationClick={handleCitation}
              />
            ) : (
              <Card>
                <CardContent className="p-8 text-center text-muted-foreground">
                  请先选择集合再开始对话。
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
        <footer className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
          <Sparkles className="mr-1 inline h-3 w-3" />
          由 LlamaIndex (40k+ ⭐) + Qdrant (25k+ ⭐) 驱动 · BGE-reranker · 1024-dim BGE-large embeddings
          {activeColl && <> · 集合：{activeColl.name}</>}
          <Link href="/admin/rag" className="ml-3 underline">
            管理后台
          </Link>
        </footer>
      </div>)</ErrorBoundary>
  );
}
