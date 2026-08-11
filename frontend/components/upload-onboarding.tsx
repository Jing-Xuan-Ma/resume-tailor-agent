"use client";

import { useRef, useState } from "react";
import { uploadTemplate } from "@/lib/api";

interface UploadOnboardingProps {
  userId: string;
  displayName?: string;
  onUploaded: () => void;
}

export default function UploadOnboarding({ userId, displayName, onUploaded }: UploadOnboardingProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith(".docx")) {
      setError("Please upload a .docx resume (locked master template).");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadTemplate(userId, file);
      onUploaded();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main
      className="flex min-h-0 flex-1 items-center justify-center bg-[#f7f7f5] px-4 py-10"
      data-testid="upload-onboarding"
    >
      <section className="w-full max-w-xl rounded-2xl border border-[#e8e8e4] bg-white p-8 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#5f7a6c]">Get started</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#14352b]">
          Upload your resume
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          {displayName ? `Welcome, ${displayName}. ` : null}
          Your master .docx becomes the locked template for every tailored version — content edits only, format stays yours.
        </p>

        <div
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          onDragEnter={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void handleFile(e.dataTransfer.files?.[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`mt-8 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 transition-colors ${
            dragging
              ? "border-[#14352b] bg-[#14352b]/[0.04]"
              : "border-[#d9d9d3] bg-[#fafaf8] hover:border-[#14352b]/40"
          }`}
          data-testid="upload-dropzone"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#14352b] text-white">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 16V4m0 0 4 4m-4-4-4 4M4 16.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1.5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <p className="mt-4 text-sm font-semibold text-[#14352b]">
            {uploading ? "Uploading…" : "Drop your .docx here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-slate-400">Word documents only · PDF coming later</p>
          <input
            ref={inputRef}
            type="file"
            accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              void handleFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>

        {error ? (
          <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700">{error}</p>
        ) : null}
      </section>
    </main>
  );
}
