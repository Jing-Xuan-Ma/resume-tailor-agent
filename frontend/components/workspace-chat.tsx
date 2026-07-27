"use client";

import { useState, useRef, useEffect } from "react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface WorkspaceChatProps {
  onSend: (message: string) => Promise<void>;
  loading?: boolean;
}

export default function WorkspaceChat({ onSend, loading }: WorkspaceChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "I can help you refine your resume for this job. Try: \"Emphasize my experience with distributed systems\" or \"Shorten the project descriptions.\"",
    },
  ]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    await onSend(userMsg);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "I've updated the resume based on your instruction. Check the new version on the right." },
    ]);
  };

  return (
    <div className="flex flex-1 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">AI Rewrite Chat</h3>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 max-h-[240px]">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[90%] rounded-xl px-3 py-2 text-[13px] leading-5 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-50 text-slate-700 border border-slate-100"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-slate-50 px-3 py-2 text-[13px] text-slate-400 border border-slate-100">
              Rewriting...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-100 p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Tell me how to improve the resume..."
            className="h-9 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-[13px] outline-none focus:border-blue-400 focus:bg-white"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="h-9 rounded-lg bg-blue-600 px-3 text-[12px] font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
