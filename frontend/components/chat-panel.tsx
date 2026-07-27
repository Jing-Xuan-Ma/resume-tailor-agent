"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage, tailorResume, uploadResumeText, uploadResumeFile, modifyDraft } from "@/lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatPanelProps {
  userId: string;
  resumeId?: string;
  onResumeUploaded?: (resumeId: string) => void;
  onTailored?: (result: unknown) => void;
}

type Mode = "chat" | "upload";
type UploadSubMode = "file" | "text";

export default function ChatPanel({ userId, resumeId, onResumeUploaded, onTailored }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm your Resume Tailor Agent. I can help you customize your resume for any job description — without making things up.\n\nPaste a job description to get started, or upload your resume first!",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [draftId, setDraftId] = useState<string | undefined>();
  const [mode, setMode] = useState<Mode>("chat");
  const [uploadSubMode, setUploadSubMode] = useState<UploadSubMode>("file");
  const [resumeInput, setResumeInput] = useState("");
  const [uploadedResumeNote, setUploadedResumeNote] = useState<string | undefined>();
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatFileInputRef = useRef<HTMLInputElement>(null);
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
        context: {
          has_uploaded_resume: Boolean(uploadedResumeNote),
          uploaded_resume_note: uploadedResumeNote,
          active_draft_id: draftId,
        },
      });

      setSessionId(chatRes.session_id);

      const looksLikeJD =
        userMsg.length > 200 &&
        (userMsg.toLowerCase().includes("responsibilities") ||
          userMsg.toLowerCase().includes("requirements") ||
          userMsg.toLowerCase().includes("experience") ||
          userMsg.toLowerCase().includes("skills"));
      const looksLikeDraftEdit =
        draftId &&
        /(revise|rewrite|edit|change|update|remove|delete|shorten|lengthen|adjust|modify|polish|优化|修改|改写|调整|删除|去掉|缩短|精简|润色)/i.test(userMsg);

      if (looksLikeJD) {
        if (!resumeId) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Upload your resume first so I can tailor it against this job description." },
          ]);
          return;
        }
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "⏳ Tailoring your resume now..." },
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
          if (tailorRes.draft_id) setDraftId(tailorRes.draft_id);
          onTailored?.({
            tailored_resume: tailorRes.tailored_resume,
            tailored_resume_id: tailorRes.tailored_resume_id,
            draft_id: tailorRes.draft_id,
            revision_id: tailorRes.revision_id,
            markdown: tailorRes.markdown,
            key_map: tailorRes.key_map || [],
          });
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
      } else if (looksLikeDraftEdit) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: chatRes.agent_message + "\n\nApplying that change to the current resume draft..." },
        ]);

        const modified = await modifyDraft(userId, draftId, userMsg);
        if (modified.success) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: modified.message || "Updated the resume draft. Review the workspace on the right." },
          ]);
          onTailored?.({
            tailored_resume: modified.tailored_resume,
            draft_id: modified.draft_id,
            revision_id: modified.revision_id,
            markdown: modified.markdown,
            key_map: modified.key_map || [],
          });
        } else {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: modified.message || "I couldn't update the current draft." },
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

  const handleUploadResume = async () => {
    if (!resumeInput.trim() || loading) return;

    setLoading(true);
    try {
      const result = await uploadResumeText(userId, resumeInput.trim());
      if (result.success) {
        if (result.resume_id) onResumeUploaded?.(result.resume_id);
        setUploadedResumeNote(`Text resume uploaded and ${result.embedded_count} chunks embedded.`);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `✅ ${result.message}\n\nYour resume has been saved. Now you can paste a job description and I'll tailor it for you!`,
          },
        ]);
        setResumeInput("");
        setMode("chat");
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ Upload failed: ${result.message}` },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ Error: ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (loading) return;

    const validTypes = [".docx", ".pdf", ".txt"];
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!validTypes.includes(ext)) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ Unsupported file type: ${ext}. Please upload .docx, .pdf, or .txt`,
        },
      ]);
      return;
    }

    setLoading(true);
    try {
      const result = await uploadResumeFile(userId, file);
      if (result.success) {
        if (result.resume_id) onResumeUploaded?.(result.resume_id);
        setUploadedResumeNote(`File '${file.name}' uploaded and ${result.embedded_count} chunks embedded.`);
        setMessages((prev) => [
          ...prev,
          { role: "user", content: `📎 Uploaded resume file: ${file.name}` },
          {
            role: "assistant",
            content: `✅ ${result.message}\n\nYour resume has been saved. Now you can paste a job description and I'll tailor it for you!`,
          },
        ]);
        setMode("chat");
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ Upload failed: ${result.message}` },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ Error: ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const onDragLeave = () => {
    setDragOver(false);
  };

  return (
    <div className="flex w-[min(34vw,470px)] min-w-[390px] flex-col border-r border-slate-200 bg-white/95 shadow-[8px_0_30px_rgba(15,23,42,0.04)]">
      <div className="border-b border-slate-200 px-5 py-4 flex items-center justify-between bg-white">
        <div>
          <h1 className="text-[15px] font-bold tracking-tight text-slate-950">Resume Agent</h1>
          <p className="text-xs text-slate-500">JD-aware resume workspace</p>
        </div>
        <div className="flex gap-1 rounded-full bg-slate-100 p-1">
          <button
            onClick={() => setMode("chat")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              mode === "chat"
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMode("upload")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              mode === "upload"
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Upload
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 bg-gradient-to-b from-white to-slate-50">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[92%] rounded-2xl px-4 py-3 text-[13px] leading-5 whitespace-pre-wrap shadow-sm ${
                msg.role === "user"
                  ? "bg-blue-600 text-white shadow-blue-200"
                  : "border border-slate-200 bg-white text-slate-800"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-white px-4 py-3 text-[13px] text-slate-500 shadow-sm">
              Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {mode === "chat" ? (
        <div className="border-t border-slate-200 bg-white px-4 py-4">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-1.5 shadow-inner">
            <input
              ref={chatFileInputRef}
              type="file"
              accept=".docx,.pdf,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
                e.currentTarget.value = "";
              }}
              className="hidden"
            />
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Paste a job description or ask me anything..."
              className="h-10 flex-1 rounded-xl border-0 bg-white px-4 text-[13px] shadow-sm outline-none ring-1 ring-transparent placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={() => chatFileInputRef.current?.click()}
              disabled={loading}
              title="Upload resume file"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l9.193-9.193a3 3 0 114.243 4.243l-9.193 9.193a1.5 1.5 0 01-2.121-2.121l8.486-8.486" />
              </svg>
            </button>
            <button
              onClick={handleSend}
              disabled={loading}
              className="h-10 rounded-xl bg-blue-600 px-4 text-[13px] font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      ) : (
        <div className="border-t border-gray-200 px-4 py-4">
          {/* Sub-mode toggle */}
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1 mb-3">
            <button
              onClick={() => setUploadSubMode("file")}
              className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                uploadSubMode === "file"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Upload File
            </button>
            <button
              onClick={() => setUploadSubMode("text")}
              className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                uploadSubMode === "text"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Paste Text
            </button>
          </div>

          {uploadSubMode === "file" ? (
            <>
              <div
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                className={`rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${
                  dragOver
                    ? "border-blue-400 bg-blue-50"
                    : "border-gray-300 bg-gray-50"
                }`}
              >
                <svg
                  className="mx-auto h-8 w-8 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M12 16.5V9.75m0 0l-3 3m3-3l3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                  />
                </svg>
                <p className="mt-2 text-sm text-gray-600">
                  <span className="font-medium text-blue-600">Click to upload</span> or drag and drop
                </p>
                <p className="mt-1 text-xs text-gray-500">.docx, .pdf, or .txt</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx,.pdf,.txt"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                  }}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading}
                  className="mt-3 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {loading ? "Uploading..." : "Select File"}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="mb-2 text-xs text-gray-500">
                Paste your resume text below. I'll save it so I can tailor it for any job description.
              </p>
              <textarea
                value={resumeInput}
                onChange={(e) => setResumeInput(e.target.value)}
                placeholder="Paste your full resume here...

Example:
John Doe
Software Engineer

Experience:
• Senior Engineer at TechCorp (2021-Present)
  - Built REST APIs with Python/FastAPI
  - Reduced latency by 40%"
                className="w-full h-32 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
              <button
                onClick={handleUploadResume}
                disabled={loading || !resumeInput.trim()}
                className="mt-2 w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {loading ? "Uploading..." : "Save Resume"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
