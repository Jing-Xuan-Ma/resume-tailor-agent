"use client";

import { useState, useRef, useEffect } from "react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AgentSendResult {
  agent_message: string;
  did_rewrite?: boolean;
}

interface WorkspaceChatProps {
  onSend: (
    message: string,
    history: Array<{ role: string; content: string }>
  ) => Promise<AgentSendResult>;
  loading?: boolean;
  /** Appended once after auto-tailor / bootstrap completes */
  bootNotice?: string | null;
}

const SUGGESTIONS = [
  "Emphasize SQL and Tableau in my bullets",
  "Make the summary more DA-focused",
  "Shorten experience bullets to fit one page",
];

export default function WorkspaceChat({ onSend, loading, bootNotice }: WorkspaceChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "I am your resume tailor agent. Every rewrite follows RESUME_CONSTITUTION.md: no fabrication, evidence-backed bullets, locked master DOCX layout, one page. When you open a job I draft automatically — ask me to refine.",
    },
  ]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const seenBootNotice = useRef<string | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!bootNotice || seenBootNotice.current === bootNotice) return;
    seenBootNotice.current = bootNotice;
    setMessages((prev) => [...prev, { role: "assistant", content: bootNotice }]);
  }, [bootNotice]);

  const handleSend = async (text?: string) => {
    const userMsg = (text ?? input).trim();
    if (!userMsg || loading) return;
    setError(null);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    try {
      const result = await onSend(userMsg, history);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.agent_message || "Done.",
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Agent request failed";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Sorry — I could not complete that turn. ${msg}`,
        },
      ]);
    }
    inputRef.current?.focus();
  };

  return (
    <div
      className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm"
      data-testid="workspace-chat"
    >
      <div className="shrink-0 border-b border-slate-100 px-5 py-3">
        <h3 className="text-sm font-bold text-slate-950">Resume Agent</h3>
        <p className="text-[12px] text-slate-500">
          Chat normally, or ask for edits — rewrite updates the locked master-template PDF.
          No job yet? Use <span className="font-semibold text-slate-700">Paste JD</span> in the header.
        </p>
        <p className="mt-0.5 text-[10px] text-slate-400" data-testid="chat-send-hint">
          Enter to send · Shift+Enter for newline
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-5 ${
                msg.role === "user"
                  ? "bg-emerald-600 text-white"
                  : "border border-slate-100 bg-slate-50 text-slate-700"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3.5 py-2.5 text-[13px] text-slate-400">
              {loading ? "Working…" : "Thinking…"}
            </div>
          </div>
        )}
        {error ? <p className="text-[11px] text-rose-600">{error}</p> : null}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 border-t border-slate-100 p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              disabled={loading}
              onClick={() => handleSend(s)}
              className="rounded-full bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-white disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            rows={2}
            placeholder="Chat or tell me how to tailor your resume…"
            className="min-h-[44px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[13px] outline-none focus:border-emerald-400 focus:bg-white"
            data-testid="chat-input"
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={loading || !input.trim()}
            data-testid="chat-send"
            className="self-end rounded-xl bg-emerald-600 px-4 py-2 text-[12px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
