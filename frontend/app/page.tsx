"use client";

import { useState } from "react";
import ChatPanel from "@/components/chat-panel";
import ResumeWorkspace from "@/components/resume-workspace";

const DEMO_USER_ID = "00000000-0000-0000-0000-000000000001";
const DEMO_RESUME_ID = "00000000-0000-0000-0000-000000000002";

export default function Home() {
  const [tailoredResume, setTailoredResume] = useState<unknown>(undefined);

  return (
    <main className="flex h-screen w-full bg-gray-50">
      <ChatPanel
        userId={DEMO_USER_ID}
        resumeId={DEMO_RESUME_ID}
        onTailored={(result) => setTailoredResume(result)}
      />
      <ResumeWorkspace tailoredResume={tailoredResume} />
    </main>
  );
}
