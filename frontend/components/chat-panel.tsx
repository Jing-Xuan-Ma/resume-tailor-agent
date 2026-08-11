"use client";

import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "@/lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatPanelProps {
  userId: string;
}

export default function ChatPanel({ userId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Ask about jobs, apply flow, or open Tailor from Profile after uploading your master .docx. Resume edits happen in the Tailor workspace.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setLoading(true);
    try {
      const chatRes = await sendChatMessage({
        user_id: userId,
        session_id: sessionId,
        message: userMsg,
        context: {},
      });
      setSessionId(chatRes.session_id);
      setMessages((prev) => [...prev, { role: "assistant", content: chatRes.agent_message }]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${msg}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside
      className="flex w-full max-w-sm shrink-0 flex-col border-r border-slate-200 bg-white"
      data-testid="chat-panel"
    >
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#14352b]">Assistant</p>
        <p className="text-xs text-slate-500">General help · Tailor lives in Profile → Tailor</p>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-xl px-3 py-2 text-sm leading-6 ${
              m.role === "user" ? "ml-6 bg-[#14352b] text-white" : "mr-4 bg-slate-50 text-slate-800"
            }`}
          >
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-slate-100 p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void handleSend()}
            placeholder="Ask anything…"
            className="h-10 flex-1 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-[#14352b]"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={loading || !input.trim()}
            className="h-10 rounded-xl bg-[#14352b] px-3 text-xs font-semibold text-white disabled:opacity-50"
          >
            {loading ? "…" : "Send"}
          </button>
        </div>
      </div>
    </aside>
  );
}
