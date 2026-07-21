"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage, tailorResume } from "@/lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatPanelProps {
  userId: string;
  resumeId: string;
  onTailored?: (result: unknown) => void;
}

export default function ChatPanel({ userId, resumeId, onTailored }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm your Resume Tailor Agent. I can help you customize your resume for any job description — without making things up.\n\nPaste a job description to get started!",
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
      // 1. Try chat endpoint first for general conversation
      const chatRes = await sendChatMessage({
        user_id: userId,
        session_id: sessionId,
        message: userMsg,
      });

      setSessionId(chatRes.session_id);

      // 2. If the message looks like a job description, also trigger tailoring
      const looksLikeJD =
        userMsg.length > 200 &&
        (userMsg.toLowerCase().includes("responsibilities") ||
          userMsg.toLowerCase().includes("requirements") ||
          userMsg.toLowerCase().includes("experience") ||
          userMsg.toLowerCase().includes("skills"));

      if (looksLikeJD) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: chatRes.agent_message + "\n\n⏳ Tailoring your resume now..." },
        ]);

        const tailorRes = await tailorResume({
          user_id: userId,
          resume_id: resumeId,
          jd_text: userMsg,
        });

        if (tailorRes.success) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content:
                tailorRes.message ||
                "I've tailored your resume for this role! Check the preview panel on the right.",
            },
          ]);
          onTailored?.(tailorRes.tailored_resume);
        } else {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content:
                tailorRes.clarification_question ||
                "I need a bit more clarity to tailor your resume accurately.",
            },
          ]);
        }
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: chatRes.agent_message },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ Error: ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex w-1/3 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4">
        <h1 className="text-lg font-semibold text-gray-900">Resume Agent</h1>
        <p className="text-sm text-gray-500">Your AI career coach</p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl px-4 py-3 text-sm bg-gray-100 text-gray-500">
              Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-200 px-4 py-4">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Paste a job description or ask me anything..."
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSend}
            disabled={loading}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
