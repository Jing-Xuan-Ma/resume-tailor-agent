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

export interface OutreachMessage {
  id: string;
  user_id: string;
  job_id?: string;
  contact_name?: string;
  contact_role?: string;
  company?: string;
  channel: string;
  subject: string;
  body: string;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface GrowthPlan {
  id: string;
  user_id: string;
  job_id?: string;
  target_role: string;
  gaps: Record<string, unknown>[];
  recommendations: Record<string, unknown>[];
  roadmap: Record<string, unknown>[];
  created_at: string;
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
  resume_id?: string;
  embedded_count: number;
  message: string;
}

export interface SourceResumeRecord {
  id: string;
  user_id: string;
  source_type: string;
  filename?: string;
  raw_text?: string;
  parsed: Record<string, unknown>;
  embedded_count: number;
  created_at: string;
  updated_at: string;
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

export async function getLatestResume(user_id: string): Promise<SourceResumeRecord | undefined> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/resume-tailor/resumes/latest?${params}`);
  if (res.status === 404) return undefined;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<SourceResumeRecord>;
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
  min_match_score?: number;
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

export async function draftOutreach(req: {
  user_id: string;
  job_id?: string;
  contact_name?: string;
  contact_role?: string;
  company?: string;
  channel?: "email" | "linkedin" | "referral";
  tone?: "concise" | "warm" | "formal";
}): Promise<OutreachMessage> {
  return post<OutreachMessage>("/api/v1/outreach/draft", req);
}

export async function listOutreachMessages(user_id: string, limit = 50): Promise<{ messages: OutreachMessage[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/outreach?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ messages: OutreachMessage[] }>;
}

export async function markOutreachSent(message_id: string, user_id: string): Promise<OutreachMessage> {
  return post<OutreachMessage>(`/api/v1/outreach/${message_id}/mark-sent`, { user_id });
}

export interface RecommendedJob {
  id: string;
  title: string;
  company?: string;
  location?: string;
  source_platform: string;
  source_url?: string;
  match_score: number;
  raw_text: string;
  parsed: Record<string, unknown>;
  created_at: string;
}

export interface HistoryRecord {
  id: string;
  user_id: string;
  job_id: string;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string;
  title?: string;
  company?: string;
  location?: string;
  source_platform?: string;
  match_score?: number;
  job_created_at?: string;
}

export async function getRecommendedJobs(user_id: string, top_n = 10): Promise<{
  jobs: RecommendedJob[];
  total_candidates: number;
  already_processed: number;
}> {
  const params = new URLSearchParams({ user_id, top_n: String(top_n) });
  const res = await fetch(`${API_BASE}/api/v1/jobs/recommended?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ jobs: RecommendedJob[]; total_candidates: number; already_processed: number }>;
}

export async function getJobHistory(user_id: string, limit = 50): Promise<{ records: HistoryRecord[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/jobs/history?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ records: HistoryRecord[] }>;
}

export interface JdSessionResponse {
  session_id: string;
  jd_text: string;
  job_id?: string;
  created_at: string;
}

export interface KeywordMatchItem {
  keyword: string;
  status: "covered" | "missing" | string;
  source_span_in_jd: [number, number];
  suggestion?: string;
}

export interface AnalyzeResponse {
  session_id: string;
  keyword_matches: KeywordMatchItem[];
}

export interface ContentDelta {
  changed_fields?: string[];
  changes?: Array<{
    path: string;
    kind: string;
    before?: string;
    after?: string;
  }>;
  change_count?: number;
  instruction?: string;
}

export interface RewriteResponse {
  new_version_id: string;
  session_id: string;
  version_index: number;
  full_resume: unknown;
  markdown: string;
  keyword_matches: KeywordMatchItem[];
  content_delta?: ContentDelta;
}

export interface VersionItem {
  id: string;
  version_index: number;
  is_confirmed: boolean;
  created_at: string;
  confirmed_at?: string;
}

export interface ListVersionsResponse {
  versions: VersionItem[];
}

export interface GetVersionResponse {
  id: string;
  session_id: string;
  version_index: number;
  content_delta: Record<string, unknown>;
  full_resume: Record<string, unknown>;
  markdown: string;
  is_confirmed: boolean;
  created_at: string;
  confirmed_at?: string;
}

export async function createJdSession(
  user_id: string,
  jd_text: string,
  job_id?: string
): Promise<JdSessionResponse> {
  return post<JdSessionResponse>("/api/v1/resume-workspace/jd-session", {
    user_id,
    jd_text,
    job_id,
  });
}

export async function analyzeJd(
  session_id: string
): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>(
    `/api/v1/resume-workspace/jd-session/${session_id}/analyze`,
    {}
  );
}

export async function rewriteResume(
  user_id: string,
  session_id: string,
  instruction: string,
  base_version_id?: string
): Promise<RewriteResponse> {
  return post<RewriteResponse>(
    `/api/v1/resume-workspace/jd-session/${session_id}/rewrite`,
    { user_id, session_id, instruction, base_version_id }
  );
}

export interface StartApplyResponse {
  apply_id: string;
  mode: string;
  status: string;
  submitted: boolean;
  paused_before_submit: boolean;
  message: string;
  filled_fields: Array<Record<string, unknown>>;
  final_path?: string;
}

export async function startApply(
  version_id: string,
  user_id: string,
  mode: "manual" | "auto",
  opts?: { company?: string; position?: string; final_path?: string }
): Promise<StartApplyResponse> {
  return post<StartApplyResponse>(
    `/api/v1/resume-workspace/resume-version/${version_id}/start-apply`,
    {
      user_id,
      mode,
      company: opts?.company,
      position: opts?.position,
      final_path: opts?.final_path,
    }
  );
}

export async function confirmVersion(
  version_id: string,
  user_id: string
): Promise<{
  ok: boolean;
  version_id: string;
  final_path?: string;
  files?: Record<string, string>;
  company?: string;
  position?: string;
}> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/resume-version/${version_id}/confirm?${params}`,
    { method: "POST" }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function suggestProject(
  version_id: string,
  user_id: string,
  keyword: string
): Promise<{ suggestion: string }> {
  return post<{ suggestion: string }>(
    `/api/v1/resume-workspace/resume-version/${version_id}/suggest-project`,
    { user_id, keyword }
  );
}

export async function listVersions(
  session_id: string,
  user_id: string
): Promise<ListVersionsResponse> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/jd-session/${session_id}/versions?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getVersion(
  version_id: string,
  user_id: string
): Promise<GetVersionResponse> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/resume-version/${version_id}?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function exportVersion(
  version_id: string,
  user_id: string,
  format: "pdf" | "docx" | "text"
): Promise<Blob> {
  const params = new URLSearchParams({ user_id, format });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/resume-version/${version_id}/export?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.blob();
}

const API_BASE_PREVIEW = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function uploadTemplate(
  user_id: string,
  file: File
): Promise<{ template_id: string; block_count: number; filename: string }> {
  const formData = new FormData();
  formData.append("user_id", user_id);
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/v1/resume-workspace/template/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getActiveTemplate(
  user_id: string
): Promise<{ template_id: string; filename: string; block_count: number; created_at: string } | null> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/resume-workspace/template/active?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export function getVersionPreviewUrl(version_id: string, user_id: string): string {
  const params = new URLSearchParams({ user_id });
  return `${API_BASE_PREVIEW}/api/v1/resume-workspace/resume-version/${version_id}/preview?${params}`;
}

export async function previewVersionPdf(
  version_id: string,
  user_id: string
): Promise<Blob> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/resume-version/${version_id}/preview?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.blob();
}

export async function analyzeGrowth(req: {
  user_id: string;
  job_id?: string;
  target_role?: string;
}): Promise<GrowthPlan> {
  return post<GrowthPlan>("/api/v1/growth/analyze", req);
}

export async function listGrowthPlans(user_id: string, limit = 20): Promise<{ plans: GrowthPlan[] }> {
  const params = new URLSearchParams({ user_id, limit: String(limit) });
  const res = await fetch(`${API_BASE}/api/v1/growth?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ plans: GrowthPlan[] }>;
}
