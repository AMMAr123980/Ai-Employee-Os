"use client";

import { useEffect, useRef, useState } from "react";
import { api, ContractAnalysisResponse, KBAskResponse, KBDocument } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  ready: "bg-green-100 text-green-700",
  processing: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
};

const RISK_COLORS: Record<string, string> = {
  standard: "bg-green-100 text-green-700",
  attention: "bg-amber-100 text-amber-700",
  high_risk: "bg-red-100 text-red-700",
  unreviewed: "bg-slate-100 text-slate-600",
};

const RISK_LABELS: Record<string, string> = {
  standard: "Standard",
  attention: "Worth a look",
  high_risk: "High risk",
  unreviewed: "Unreviewed",
};

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [question, setQuestion] = useState("");
  const [scopeDocId, setScopeDocId] = useState<string>("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<KBAskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  // Contract analysis: keyed by document id so each row's panel is
  // independent — you can have several open, each showing its own result.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [analysisByDoc, setAnalysisByDoc] = useState<Record<string, ContractAnalysisResponse>>({});
  const [analysisErrorByDoc, setAnalysisErrorByDoc] = useState<Record<string, string>>({});

  async function refresh() {
    setLoading(true);
    try {
      setDocuments(await api.listDocuments());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      await api.uploadDocument(file, { title: file.name.replace(/\.[^.]+$/, "") });
      await refresh();
    } catch (e: any) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function handleAsk() {
    if (!question.trim()) return;
    setAsking(true);
    setAskError(null);
    setAnswer(null);
    try {
      setAnswer(await api.askDocuments(question, scopeDocId || undefined));
    } catch (e: any) {
      setAskError(e.message);
    } finally {
      setAsking(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this document? This can't be undone.")) return;
    await api.deleteDocument(id);
    await refresh();
  }

  async function handleAnalyzeContract(docId: string, opts: { refresh?: boolean } = {}) {
    // Already have a result and this isn't a forced refresh — just toggle
    // the panel open instead of hitting the API again.
    if (!opts.refresh && analysisByDoc[docId]) {
      setExpandedId(expandedId === docId ? null : docId);
      return;
    }
    setExpandedId(docId);
    setAnalyzingId(docId);
    setAnalysisErrorByDoc((prev) => ({ ...prev, [docId]: "" }));
    try {
      const result = await api.analyzeContract(docId, opts);
      setAnalysisByDoc((prev) => ({ ...prev, [docId]: result }));
    } catch (e: any) {
      setAnalysisErrorByDoc((prev) => ({ ...prev, [docId]: e.message }));
    } finally {
      setAnalyzingId(null);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">Knowledge Base</h1>
      <p className="text-slate-500 mb-6">
        Upload company documents — policies, price lists, contract templates, handbooks —
        and ask questions against them. Answers come only from what's uploaded here, with
        the source passage attached, never from general knowledge. The same store backs
        the "ask_documents" voice command. Scanned PDFs are OCR'd automatically, and any
        document can be read specifically as a contract — clause by clause, with what's
        missing flagged too.
      </p>

      {/* Ask */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 mb-6 space-y-3">
        <p className="text-sm font-medium">Ask a question</p>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="e.g. What's our refund window for late returns?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          />
          <select
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm max-w-[10rem]"
            value={scopeDocId}
            onChange={(e) => setScopeDocId(e.target.value)}
          >
            <option value="">All documents</option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
          <button
            onClick={handleAsk}
            disabled={asking}
            className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {asking ? "Asking…" : "Ask"}
          </button>
        </div>
        {askError && <p className="text-sm text-red-500">{askError}</p>}

        {answer && (
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 space-y-3">
            {answer.mode === "no_match" && (
              <p className="text-sm text-slate-500">Nothing in the knowledge base looks related to that.</p>
            )}
            {answer.mode === "passages_only" && (
              <p className="text-xs text-amber-600">
                No OpenAI key configured — showing the closest matching passages instead of a
                synthesised answer.
              </p>
            )}
            {answer.answer && <p className="text-sm text-slate-700 whitespace-pre-wrap">{answer.answer}</p>}
            {answer.sources.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Sources</p>
                {answer.sources.map((s) => (
                  <div key={s.chunk_id} className="text-xs text-slate-500 border-l-2 border-slate-200 pl-2">
                    <span className="font-medium text-slate-600">{s.document_title}</span> —{" "}
                    {s.content.slice(0, 220)}
                    {s.content.length > 220 ? "…" : ""}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Upload */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 mb-6">
        <p className="text-sm font-medium mb-3">Upload a document</p>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.txt,.md,.csv"
          disabled={uploading}
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          className="text-sm"
        />
        {uploading && <p className="text-sm text-slate-400 mt-2">Uploading and indexing…</p>}
        {uploadError && <p className="text-sm text-red-500 mt-2">{uploadError}</p>}
        <p className="text-xs text-slate-400 mt-2">
          PDF, DOCX, TXT, Markdown or CSV. Up to 25 MB. Scanned PDFs with no text layer are OCR'd
          automatically.
        </p>
      </div>

      {/* List */}
      <div className="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
        {loading ? (
          <p className="p-5 text-sm text-slate-400">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="p-5 text-sm text-slate-400">No documents uploaded yet.</p>
        ) : (
          documents.map((d) => {
            const analysis = analysisByDoc[d.id];
            const analysisError = analysisErrorByDoc[d.id];
            const isExpanded = expandedId === d.id;
            const isAnalyzing = analyzingId === d.id;
            return (
              <div key={d.id}>
                <div className="p-4 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{d.title}</p>
                    <p className="text-xs text-slate-400 truncate">
                      {d.filename} · {formatBytes(d.size_bytes)}
                      {d.chunk_count > 0 ? ` · ${d.chunk_count} chunks` : ""}
                      {d.uploaded_by_name ? ` · uploaded by ${d.uploaded_by_name}` : ""}
                    </p>
                    {d.error && <p className="text-xs text-red-500 mt-1">{d.error}</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {d.ocr_used && (
                      <span
                        title="At least one page had no text layer and was read with OCR"
                        className="text-xs font-medium rounded-full px-2.5 py-0.5 bg-blue-100 text-blue-700"
                      >
                        OCR
                      </span>
                    )}
                    <span
                      className={`text-xs font-medium rounded-full px-2.5 py-0.5 capitalize ${
                        STATUS_COLORS[d.status] || "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {d.status}
                    </span>
                    {d.status === "ready" && (
                      <button
                        onClick={() => handleAnalyzeContract(d.id)}
                        disabled={isAnalyzing}
                        className="text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50"
                      >
                        {isAnalyzing ? "Analyzing…" : isExpanded ? "Hide clauses" : "Analyze as contract"}
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="text-xs font-medium text-slate-400 hover:text-red-500"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-4 pb-4">
                    <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 space-y-4">
                      {isAnalyzing && !analysis && (
                        <p className="text-sm text-slate-400">Reading the document for clauses…</p>
                      )}
                      {analysisError && <p className="text-sm text-red-500">{analysisError}</p>}

                      {analysis && (
                        <>
                          <div className="flex items-center justify-between gap-2">
                            <div className="space-y-1">
                              {analysis.mode === "keyword_fallback" && (
                                <p className="text-xs text-amber-600">
                                  No OpenAI key configured — showing keyword matches instead of a
                                  full read. Risk levels aren't assessed in this mode.
                                </p>
                              )}
                              {analysis.truncated && (
                                <p className="text-xs text-amber-600">
                                  This document is long — analysis covers the first portion only.
                                </p>
                              )}
                              {analysis.error && (
                                <p className="text-xs text-red-500">
                                  Full read failed, showing keyword matches instead: {analysis.error}
                                </p>
                              )}
                            </div>
                            <button
                              onClick={() => handleAnalyzeContract(d.id, { refresh: true })}
                              disabled={isAnalyzing}
                              className="text-xs font-medium text-slate-400 hover:text-slate-600 shrink-0 disabled:opacity-50"
                            >
                              {isAnalyzing ? "Re-analyzing…" : "Re-analyze"}
                            </button>
                          </div>

                          {analysis.clauses.length === 0 ? (
                            <p className="text-sm text-slate-500">
                              No clauses from the standard taxonomy were found in this document.
                            </p>
                          ) : (
                            <div className="space-y-3">
                              <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
                                Clauses found ({analysis.clauses.length})
                              </p>
                              {analysis.clauses.map((c, i) => (
                                <div key={i} className="rounded-lg border border-slate-200 bg-white p-3 space-y-1.5">
                                  <div className="flex items-center justify-between gap-2 flex-wrap">
                                    <p className="text-sm font-medium text-slate-700">
                                      {c.title || c.label}
                                    </p>
                                    <span
                                      className={`text-xs font-medium rounded-full px-2 py-0.5 shrink-0 ${
                                        RISK_COLORS[c.risk_level] || "bg-slate-100 text-slate-600"
                                      }`}
                                    >
                                      {RISK_LABELS[c.risk_level] || c.risk_level}
                                    </span>
                                  </div>
                                  {c.plain_english && (
                                    <p className="text-sm text-slate-600">{c.plain_english}</p>
                                  )}
                                  <p className="text-xs text-slate-400 border-l-2 border-slate-200 pl-2 whitespace-pre-wrap">
                                    {c.excerpt}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}

                          {analysis.missing_clause_types.length > 0 && (
                            <div className="space-y-2">
                              <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
                                Not found in this document
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {analysis.missing_clause_types.map((m) => (
                                  <span
                                    key={m.clause_type}
                                    title={m.description}
                                    className="text-xs rounded-full px-2.5 py-0.5 bg-slate-100 text-slate-500"
                                  >
                                    {m.label}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
