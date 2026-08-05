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

export interface OutreachContact {
  id: string;
  name: string;
  role: string;
  company: string;
  job_id?: string | null;
  linkedin_url: string;
  email: string;
  coffee_availability: string;
  notes: string;
  status: string;
  reply_status?: string;
  last_reply_at?: string;
  coffee_slots?: string[];
  updated_at: string;
}

export interface OutreachRankedCandidate {
  id: string;
  name: string;
  title: string;
  snippet: string;
  recent_activity: string;
  linkedin_url: string;
  score: number;
  stars: number;
  match_reason: string;
  reason_details: string[];
  components: Record<string, number>;
  status: string;
}

export interface OutreachEmailCandidate {
  email: string;
  source: string;
  source_detail: string;
  pattern: string;
  confidence: number;
  confidence_label: string;
  smtp_status: string;
  recommendation: string;
}

export interface OutreachJdIngestResult {
  ok: boolean;
  error?: string | null;
  company: string;
  position: string;
  jd_text: string;
  platform: string;
  source_url: string;
  page_title: string;
  fetch_status: string;
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

export interface CandidateLibrary {
  user_id: string;
  inventory: Record<string, unknown>;
  apply: Record<string, unknown>;
  updated_at: string;
}

export async function getCandidateLibrary(user_id: string): Promise<CandidateLibrary> {
  const res = await fetch(`${API_BASE}/api/v1/profile/${encodeURIComponent(user_id)}/library`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<CandidateLibrary>;
}

export async function updateCandidateLibrary(
  user_id: string,
  payload: { inventory?: Record<string, unknown>; apply?: Record<string, unknown> }
): Promise<CandidateLibrary> {
  const res = await fetch(`${API_BASE}/api/v1/profile/${encodeURIComponent(user_id)}/library`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<CandidateLibrary>;
}

export async function resetCandidateLibrary(user_id: string): Promise<CandidateLibrary> {
  return post<CandidateLibrary>(`/api/v1/profile/${encodeURIComponent(user_id)}/library/reset`, {});
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
  template_type?:
    | "coffee_chat"
    | "post_apply_thanks"
    | "recruiter_ping"
    | "linkedin_connect"
    | "general";
  linkedin_url?: string;
  contact_email?: string;
  coffee_availability?: string;
  save_to_crm?: boolean;
}): Promise<OutreachMessage> {
  return post<OutreachMessage>("/api/v1/outreach/draft", req);
}

export async function rankOutreachCandidates(req: {
  user_id: string;
  candidates: Array<{
    id?: string;
    name?: string;
    title?: string;
    snippet?: string;
    recent_activity?: string;
    linkedin_url?: string;
    company_size?: string;
    status?: string;
  }>;
  jd_text?: string;
  position?: string;
  company?: string;
  company_size?: string;
}): Promise<{ candidates: OutreachRankedCandidate[]; jd_signals: Record<string, unknown> }> {
  return post("/api/v1/outreach/rank-candidates", req);
}

export async function ingestOutreachJd(req: {
  user_id: string;
  url: string;
  jd_text_override?: string;
}): Promise<OutreachJdIngestResult> {
  return post<OutreachJdIngestResult>("/api/v1/outreach/jd-ingest", req);
}

export async function findOutreachEmail(req: {
  user_id: string;
  name: string;
  company?: string;
  domain?: string;
  website?: string;
  use_hunter?: boolean;
}): Promise<{
  name: string;
  company: string;
  domain: string;
  hunter_used: boolean;
  candidates: OutreachEmailCandidate[];
  expectancy_note: string;
  empty_reason?: string | null;
}> {
  return post("/api/v1/outreach/find-email", req);
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

export async function upsertOutreachContact(req: {
  user_id: string;
  id?: string;
  name?: string;
  role?: string;
  company?: string;
  job_id?: string;
  linkedin_url?: string;
  email?: string;
  coffee_availability?: string;
  notes?: string;
  status?: string;
  reply_status?: string;
  coffee_slots?: string[];
}): Promise<OutreachContact> {
  return post<OutreachContact>("/api/v1/outreach/contacts", req);
}

export async function listOutreachContacts(user_id: string): Promise<{ contacts: OutreachContact[] }> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/outreach/contacts?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ contacts: OutreachContact[] }>;
}

export function getOutreachCrmExportUrl(user_id: string): string {
  const params = new URLSearchParams({ user_id });
  return `${API_BASE}/api/v1/outreach/contacts/export?${params}`;
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
  unchanged_paths?: string[];
  hidden_entries?: Array<Record<string, unknown> | string>;
  diff_baseline?: string;
  highlight?: { changed?: string; unchanged?: string; hidden?: string };
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

export interface ConstitutionRule {
  id: string;
  title: string;
  detail: string;
}

export interface ConstitutionResponse {
  version: string;
  source: string;
  master_template: string;
  track: string;
  rules: ConstitutionRule[];
  full_text?: string;
}

export async function getResumeConstitution(): Promise<ConstitutionResponse> {
  const res = await fetch(`${API_BASE}/api/v1/resume-workspace/constitution`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return (await res.json()) as ConstitutionResponse;
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

export interface JobWorkspaceHandoff {
  session_id: string;
  job_id: string;
  jd_text: string;
  title?: string;
  company?: string;
  jobright_url?: string;
  source_url?: string;
}

export async function openJobInResumeWorkspace(
  job_id: string,
  user_id: string
): Promise<JobWorkspaceHandoff> {
  const res = await fetch(
    `${API_BASE}/api/v1/jobs/${encodeURIComponent(job_id)}/to-resume-workspace?user_id=${encodeURIComponent(user_id)}`,
    { method: "POST" }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  const data = (await res.json()) as Record<string, unknown>;
  const session_id = String(data.session_id || data.sessionId || "");
  const jd_text = String(data.jd_text || "");
  if (!session_id || !jd_text) {
    throw new Error("Job handoff did not return session_id/jd_text");
  }
  return {
    session_id,
    job_id: String(data.job_id || data.jobId || job_id),
    jd_text,
    title: data.title ? String(data.title) : undefined,
    company: data.company ? String(data.company) : undefined,
    jobright_url: data.jobright_url ? String(data.jobright_url) : undefined,
    source_url: data.source_url ? String(data.source_url) : undefined,
  };
}

export interface AgentTurnResponse {
  session_id: string;
  agent_message: string;
  intent: "chat" | "rewrite" | "update_profile" | string;
  did_rewrite: boolean;
  new_version_id?: string | null;
  version_index?: number | null;
  full_resume?: Record<string, unknown> | null;
  keyword_matches: KeywordMatchItem[];
  content_delta: Record<string, unknown>;
  llm_provider?: string | null;
  llm_model?: string | null;
  profile_updated?: boolean;
  changed_apply?: string[];
  changed_inventory?: string[];
}

export async function workspaceAgentTurn(
  user_id: string,
  session_id: string,
  message: string,
  opts?: {
    base_version_id?: string;
    chat_history?: Array<{ role: string; content: string }>;
  }
): Promise<AgentTurnResponse> {
  return post<AgentTurnResponse>(
    `/api/v1/resume-workspace/jd-session/${session_id}/agent`,
    {
      user_id,
      message,
      base_version_id: opts?.base_version_id,
      chat_history: opts?.chat_history || [],
    }
  );
}

export interface FillPlanItem {
  field_id?: string;
  profile_key?: string | null;
  value?: string;
  confidence?: number;
  needs_review?: boolean;
  action?: string;
  reason?: string;
  label?: string;
  tier?: "auto" | "review" | "empty" | string;
  selector?: string;
  type?: string;
  [key: string]: unknown;
}

export interface StartApplyResponse {
  apply_id: string;
  mode: string;
  status: string;
  submitted: boolean;
  paused_before_submit: boolean;
  message: string;
  filled_fields: Array<{
    field: string;
    value?: string;
    note?: string;
    required?: boolean;
    type?: string;
    ats_type?: string;
    tier?: string;
    confidence?: number;
    needs_review?: boolean;
    profile_key?: string;
    action?: string;
  }>;
  ats_fields?: Array<Record<string, unknown>>;
  ats_type?: string;
  source_url?: string;
  /** Indeed/board listing when company ATS is missing or unusable (e.g. Workday career root). */
  board_url?: string;
  browser_fill?: {
    status?: string;
    submitted?: boolean;
    paused_before_submit?: boolean;
    message?: string;
    filled?: Array<{ field?: string; status?: string }>;
    screenshot_path?: string | null;
    ats_type?: string;
    sandbox?: boolean;
    fill_url?: string;
    original_url?: string | null;
    [key: string]: unknown;
  } | null;
  final_path?: string;
  fill_plan?: FillPlanItem[];
  map_provider?: string | null;
  requires_human_review?: boolean;
  confirmed_submit_at?: string;
}

export async function startApply(
  version_id: string,
  user_id: string,
  mode: "manual" | "auto",
  opts?: {
    company?: string;
    position?: string;
    final_path?: string;
    job_id?: string;
    source_url?: string;
  }
): Promise<StartApplyResponse> {
  return post<StartApplyResponse>(
    `/api/v1/resume-workspace/resume-version/${version_id}/start-apply`,
    {
      user_id,
      mode,
      company: opts?.company,
      position: opts?.position,
      final_path: opts?.final_path,
      job_id: opts?.job_id,
      source_url: opts?.source_url,
    }
  );
}

export async function confirmApplySubmit(
  apply_id: string,
  user_id: string,
  acknowledge = true
): Promise<{
  apply_id: string;
  status: string;
  submitted: boolean;
  paused_before_submit: boolean;
  message: string;
  confirmed_submit_at?: string;
  source_url?: string;
}> {
  return post(`/api/v1/resume-workspace/apply/${encodeURIComponent(apply_id)}/confirm-submit`, {
    user_id,
    acknowledge,
  });
}

export async function getApply(apply_id: string): Promise<StartApplyResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/apply/${encodeURIComponent(apply_id)}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
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
  const params = new URLSearchParams({ user_id, v: String(Date.now()) });
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

export async function translateJdSegments(
  texts: string[],
  target_lang = "zh-CN"
): Promise<{ translations: { source: string; translated: string }[]; provider?: string }> {
  return post("/api/v1/jobs/translate-segments", { texts, target_lang });
}

export type QueueItem = {
  id: string;
  user_id: string;
  job_id?: string;
  version_id?: string;
  source_url?: string;
  company?: string;
  position?: string;
  fill_status: string;
  awaiting_confirm: boolean;
  apply_id?: string;
  submitted_at?: string;
  skipped_at?: string;
  error?: string;
  created_at?: string;
  updated_at?: string;
};

export async function enqueueApplications(
  user_id: string,
  items: Array<{
    job_id?: string;
    version_id?: string;
    source_url?: string;
    company?: string;
    position?: string;
  }>
): Promise<{ items: QueueItem[] }> {
  return post("/api/v1/queue/enqueue", { user_id, items });
}

export async function listApplicationQueue(user_id: string): Promise<{ items: QueueItem[] }> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/queue?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ items: QueueItem[] }>;
}

export async function processQueueItem(item_id: string, user_id: string): Promise<QueueItem> {
  return post(`/api/v1/queue/${encodeURIComponent(item_id)}/process`, { user_id });
}

export async function confirmQueueItem(
  item_id: string,
  user_id: string,
  acknowledge = true
): Promise<QueueItem> {
  return post(`/api/v1/queue/${encodeURIComponent(item_id)}/confirm-submit`, {
    user_id,
    acknowledge,
  });
}

export async function skipQueueItem(item_id: string, user_id: string): Promise<QueueItem> {
  return post(`/api/v1/queue/${encodeURIComponent(item_id)}/skip`, { user_id });
}


export interface LlmProviderInfo {
  id: string;
  name: string;
  default_model: string;
  configured: boolean;
  preferred: boolean;
  cooled_down: boolean;
}

export interface LlmStatus {
  preferred_provider: string | null;
  failover: boolean;
  last_provider: string | null;
  last_model: string | null;
  active_provider: string | null;
  active_provider_name: string | null;
  active_model: string | null;
  configured: LlmProviderInfo[];
  available: LlmProviderInfo[];
}

export async function getLlmStatus(): Promise<LlmStatus> {
  const res = await fetch(`${API_BASE}/api/v1/llm/status`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<LlmStatus>;
}

export async function setLlmPreference(body: {
  provider?: string | null;
  failover?: boolean | null;
}): Promise<LlmStatus> {
  const res = await fetch(`${API_BASE}/api/v1/llm/preference`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<LlmStatus>;
}
