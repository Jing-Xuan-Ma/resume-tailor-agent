const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  user_id: string;
  session_id?: string;
  message: string;
  context?: Record<string, unknown>;
}

export interface ChatResponse {
  session_id: string;
  agent_message: string;
  agent_state: string;
  suggested_actions: string[];
}

export interface TailorRequest {
  user_id: string;
  resume_id: string;
  jd_text: string;
  job_id?: string;
  preferences?: Record<string, unknown>;
}

export interface TailorResponse {
  success: boolean;
  tailored_resume: unknown;
  message: string;
  clarification_needed: boolean;
  clarification_question?: string;
  ats_score_estimate?: number;
  tailored_resume_id?: string;
  draft_id?: string;
  revision_id?: string;
  markdown?: string;
  key_map?: KeyMapItem[];
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: Record<string, unknown>;
}

export interface JobRecord {
  id: string;
  user_id: string;
  title: string;
  company?: string;
  location?: string;
  source_url?: string;
  source_platform: string;
  raw_text: string;
  parsed: Record<string, unknown>;
  match_score?: number;
  created_at: string;
}

export interface ApplicationPlanResponse {
  application_run_id: string;
  status: string;
  plan: Record<string, unknown>;
  answers: Record<string, unknown>[];
}

export interface ApplicationSubmitResponse {
  application_run_id: string;
  status: string;
  submission_result: Record<string, unknown>;
}

export interface JobPrepareApplicationResponse {
  job: JobRecord;
  tailored: TailorResponse;
  cover_letter?: Record<string, unknown>;
  application_plan?: ApplicationPlanResponse & Record<string, unknown>;
}

export interface KeyMapItem {
  jd_key: string;
  resume_phrase: string;
  status: "matched" | "partial" | "missing" | string;
  highlight_terms: string[];
  note: string;
}

export interface ModifyDraftResponse {
  success: boolean;
  draft_id: string;
  revision_id?: string;
  tailored_resume?: unknown;
  markdown?: string;
  key_map?: KeyMapItem[];
  message: string;
}

export interface UploadResumeResponse {
  success: boolean;
  embedded_count: number;
  message: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function sendChatMessage(
  req: ChatRequest
): Promise<ChatResponse> {
  return post<ChatResponse>("/api/v1/chat/send", req);
}

export async function registerUser(email: string, full_name: string, password: string): Promise<AuthResponse> {
  return post<AuthResponse>("/api/v1/auth/register", { email, full_name, password });
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  return post<AuthResponse>("/api/v1/auth/login", { email, password });
}

export async function getCurrentUser(token: string): Promise<{ user: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ user: Record<string, unknown> }>;
}

export async function tailorResume(req: TailorRequest): Promise<TailorResponse> {
  return post<TailorResponse>("/api/v1/resume-tailor/tailor", req);
}

export async function exportText(tailoredResume: unknown): Promise<{ text: string }> {
  return post<{ text: string }>("/api/v1/resume-tailor/export-text", {
    tailored_resume: tailoredResume,
  });
}

export async function modifyDraft(
  user_id: string,
  draft_id: string,
  instruction: string
): Promise<ModifyDraftResponse> {
  return post<ModifyDraftResponse>("/api/v1/resume-tailor/drafts/modify", {
    user_id,
    draft_id,
    instruction,
  });
}

export async function getTailoredResume(
  tailored_resume_id: string,
  user_id?: string
): Promise<Record<string, unknown>> {
  const params = user_id ? `?${new URLSearchParams({ user_id })}` : "";
  const res = await fetch(`${API_BASE}/api/v1/resume-tailor/tailored/${tailored_resume_id}${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function exportDraft(
  user_id: string,
  draft_id: string,
  format: "pdf" | "docx"
): Promise<Blob> {
  const params = new URLSearchParams({ user_id, format });
  const res = await fetch(`${API_BASE}/api/v1/resume-tailor/drafts/${draft_id}/export?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.blob();
}

export async function uploadResumeText(
  user_id: string,
  resume_text: string
): Promise<UploadResumeResponse> {
  return post<UploadResumeResponse>("/api/v1/resume-tailor/upload-resume", {
    user_id,
    resume_text,
  });
}

export async function uploadResumeFile(
  user_id: string,
  file: File
): Promise<UploadResumeResponse> {
  const formData = new FormData();
  formData.append("user_id", user_id);
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/v1/resume-tailor/upload-resume-file`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<UploadResumeResponse>;
}

export async function checkHealth(): Promise<{
  status: string;
  version: string;
  env: string;
}> {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function getProfile(user_id: string): Promise<{ user_id: string; profile: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/api/v1/profile/${user_id}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ user_id: string; profile: Record<string, unknown> }>;
}

export async function updateProfileFeedback(
  user_id: string,
  feedback: Record<string, unknown>
): Promise<{ user_id: string; profile: Record<string, unknown> }> {
  return post<{ user_id: string; profile: Record<string, unknown> }>("/api/v1/profile/feedback", {
    user_id,
    feedback,
  });
}

export async function discoverJobs(req: {
  user_id: string;
  query: string;
  location?: string;
  limit?: number;
  sites?: string[];
  provider?: string;
  hours_old?: number;
  country_indeed?: string;
}): Promise<{ jobs: JobRecord[] }> {
  return post<{ jobs: JobRecord[] }>("/api/v1/jobs/discover", req);
}

export async function ingestJob(req: {
  user_id: string;
  raw_text: string;
  source_url?: string;
  source_platform?: string;
}): Promise<JobRecord> {
  return post<JobRecord>("/api/v1/jobs/ingest", req);
}

export async function listJobs(user_id: string, limit = 20): Promise<{ jobs: JobRecord[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/jobs?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ jobs: JobRecord[] }>;
}

export async function bookmarkJob(
  user_id: string,
  job_id: string,
  notes?: string
): Promise<{ bookmark: Record<string, unknown> }> {
  return post<{ bookmark: Record<string, unknown> }>("/api/v1/jobs/bookmarks", {
    user_id,
    job_id,
    notes,
  });
}

export async function listBookmarkedJobs(user_id: string, limit = 50): Promise<{ jobs: JobRecord[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/jobs/bookmarks?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ jobs: JobRecord[] }>;
}

export async function planApplication(req: {
  user_id: string;
  job_id: string;
  tailored_resume_id?: string;
  auto_submit?: boolean;
  submit_mode?: "manual_review" | "auto_submit";
  user_profile?: Record<string, unknown>;
}): Promise<ApplicationPlanResponse> {
  return post<ApplicationPlanResponse>("/api/v1/applications/plan", req);
}

export async function listApplicationRuns(
  user_id: string,
  limit = 50
): Promise<{ runs: Record<string, unknown>[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/applications?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ runs: Record<string, unknown>[] }>;
}

export async function confirmManualSubmit(
  application_run_id: string,
  user_id: string,
  confirmation_note?: string
): Promise<ApplicationSubmitResponse> {
  return post<ApplicationSubmitResponse>(`/api/v1/applications/${application_run_id}/confirm-manual-submit`, {
    user_id,
    confirmation_note,
  });
}

export async function autoSubmitApplication(
  application_run_id: string,
  user_id: string
): Promise<ApplicationSubmitResponse> {
  return post<ApplicationSubmitResponse>(`/api/v1/applications/${application_run_id}/auto-submit`, {
    user_id,
    confirm_auto_submit: true,
  });
}

export async function prepareApplicationForJob(
  job_id: string,
  req: {
    user_id: string;
    resume_id: string;
    include_cover_letter?: boolean;
    include_application_plan?: boolean;
    auto_submit?: boolean;
    submit_mode?: "manual_review" | "auto_submit";
    user_profile?: Record<string, unknown>;
  }
): Promise<JobPrepareApplicationResponse> {
  return post<JobPrepareApplicationResponse>(`/api/v1/jobs/${job_id}/prepare-application`, req);
}
