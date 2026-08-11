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
  tailored: Record<string, unknown>;
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

export interface KeyMapItem {
  jd_key: string;
  resume_phrase: string;
  status: "matched" | "partial" | "missing" | string;
  highlight_terms: string[];
  note: string;
}

async function post<T>(path: string, body: unknown, init?: { signal?: AbortSignal }): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: init?.signal,
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
    signal?: AbortSignal;
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
    },
    { signal: opts?.signal }
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

export type TemplateVersionItem = {
  id: string;
  filename: string;
  is_active: boolean;
  resume_structure?: {
    sections?: Array<{ type?: string; entries?: Array<{ bullets?: unknown[] }> }>;
  };
  unmapped_sections: Array<{ raw_title: string }>;
  created_at: string;
  updated_at: string;
};

export type ActiveTemplate = {
  template_id: string;
  filename: string;
  block_count: number;
  resume_structure?: { sections?: Array<{ type?: string; title?: string }> };
  unmapped_sections?: Array<{ raw_title: string }>;
  created_at: string;
};

export async function uploadTemplate(
  user_id: string,
  file: File
): Promise<{
  template_id: string;
  block_count: number;
  filename: string;
  resume_structure?: Record<string, unknown>;
  unmapped_sections?: Array<{ raw_title: string }>;
  is_active?: boolean;
}> {
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

export async function getActiveTemplate(user_id: string): Promise<ActiveTemplate | null> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/resume-workspace/template/active?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function listTemplates(user_id: string): Promise<{ templates: TemplateVersionItem[] }> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(`${API_BASE}/api/v1/resume-workspace/templates?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<{ templates: TemplateVersionItem[] }>;
}

export async function activateTemplate(
  template_id: string,
  user_id: string
): Promise<{ ok: boolean; template_id: string; resume_structure?: Record<string, unknown> }> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/resume-workspace/template/${encodeURIComponent(template_id)}/activate?${params}`,
    { method: "POST" }
  );
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

export type CartApplyState = {
  status?: string;
  error?: string | null;
  jobright_url?: string | null;
  ats_url?: string | null;
  form_url?: string | null;
  storage_state_path?: string | null;
  ats_type?: string | null;
  nav_method?: string | null;
  apply_clicked?: boolean;
  autofill_clicked?: boolean;
  resume_attached?: boolean;
  phase3_done?: boolean;
  phase4_done?: boolean;
  phase5_done?: boolean;
  email_masked?: string | null;
  auth_mode?: string | null;
  next_screen?: string | null;
  resume_path?: string | null;
  fill_snapshot_path?: string | null;
  screenshot_path?: string | null;
  filled_fields?: Array<{
    field?: string;
    value?: string;
    tier?: string;
    status?: string;
    note?: string;
  }>;
  profile_checklist?: Array<{ field?: string; value?: string; tier?: string; note?: string }>;
  fill_plan?: Array<Record<string, unknown>>;
  dry_run?: boolean;
  paused_before_submit?: boolean;
  updated_at?: string;
  note?: string;
  timeline?: Array<{ status?: string; at?: string; error?: string | null }>;
};

export type CartFillReview = {
  cart_id: string;
  item_id: string;
  company?: string;
  position?: string;
  apply_status?: string;
  steps?: Array<{ id: string; label: string; hint?: string }>;
  review?: {
    filled_fields?: CartApplyState["filled_fields"];
    profile_checklist?: CartApplyState["profile_checklist"];
    fill_plan?: CartApplyState["fill_plan"];
    screenshot_path?: string | null;
    ats_url?: string | null;
    form_url?: string | null;
    storage_state_path?: string | null;
    ats_type?: string | null;
    paused_before_submit?: boolean;
    submitted?: boolean;
    method?: string;
    dry_run?: boolean;
    message?: string;
  };
};

export type ShoppingCartItem = {
  item_id?: string;
  intern_job_id?: string;
  listing_id?: string;
  company?: string;
  position?: string;
  location?: string;
  source_url?: string;
  status?: string;
  ok?: boolean;
  error?: string;
  session_id?: string;
  version_id?: string;
  folder?: string;
  resume_md?: string;
  cover_letter_md?: string;
  has_resume_pdf?: boolean;
  has_cover_letter_pdf?: boolean;
  has_detail?: boolean;
  elapsed_ms?: number;
  rewrite_ms?: number;
  cover_letter_ms?: number;
  apply?: CartApplyState;
};

export type ShoppingCartPreview = {
  requested: number;
  status?: string;
  items: ShoppingCartItem[];
};

export type ShoppingCartResponse = {
  cart_id: string;
  status?: string;
  requested?: number;
  ok_count?: number;
  failed_count?: number;
  generating_count?: number;
  concurrency?: number;
  elapsed_ms?: number;
  max_item_ms?: number;
  soft_timeout_s?: number;
  apply_summary?: {
    counts?: Record<string, number>;
    ready_to_submit?: number;
    queued?: number;
    navigating?: number;
    on_ats?: number;
    applying?: number;
    registered?: number;
    filled?: number;
    failed?: number;
    submitted?: number;
  };
  items: ShoppingCartItem[];
};

export async function previewShoppingCart(
  intern_job_ids: string[]
): Promise<ShoppingCartPreview> {
  return post("/api/v1/shopping-cart/preview", { intern_job_ids });
}

export async function generateShoppingCart(
  user_id: string,
  intern_job_ids: string[],
  concurrency?: number
): Promise<ShoppingCartResponse> {
  return post("/api/v1/shopping-cart/batch-generate", {
    user_id,
    intern_job_ids,
    ...(concurrency != null ? { concurrency } : {}),
    wait: false,
  });
}

export async function getShoppingCart(
  cart_id: string,
  user_id: string
): Promise<ShoppingCartResponse> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<ShoppingCartResponse>;
}

/** Best existing cart for this job selection (prefers finished drafts). */
export async function getLatestShoppingCart(
  user_id: string,
  intern_job_ids: string[]
): Promise<ShoppingCartResponse | null> {
  const params = new URLSearchParams({
    user_id,
    intern_job_ids: intern_job_ids.join(","),
  });
  const res = await fetch(`${API_BASE}/api/v1/shopping-cart/latest?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<ShoppingCartResponse>;
}

export async function confirmShoppingCartItem(
  cart_id: string,
  item_id: string,
  user_id: string
): Promise<{
  cart_id: string;
  item_id: string;
  status: string;
  folder?: string;
  resume_pdf_path?: string;
  cover_letter_pdf_path?: string;
}> {
  return post(
    `/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/items/${encodeURIComponent(item_id)}/confirm`,
    { user_id }
  );
}

/** Ephemeral PDF preview (not written to folder until confirm). */
export function getShoppingCartItemPreviewUrl(
  cart_id: string,
  item_id: string,
  user_id: string,
  kind: "resume" | "cover" = "resume"
): string {
  const params = new URLSearchParams({ user_id, kind });
  return `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/items/${encodeURIComponent(item_id)}/preview.pdf?${params}`;
}

export async function getShoppingCartFillReview(
  cart_id: string,
  item_id: string,
  user_id: string
): Promise<CartFillReview> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/items/${encodeURIComponent(item_id)}/fill-review?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<CartFillReview>;
}

export function getShoppingCartFillScreenshotUrl(
  cart_id: string,
  item_id: string,
  user_id: string
): string {
  const params = new URLSearchParams({ user_id });
  return `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/items/${encodeURIComponent(item_id)}/fill-screenshot?${params}`;
}

export async function openShoppingCartFilledForm(
  cart_id: string,
  item_id: string,
  user_id: string,
  keep_open_ms = 1_800_000
): Promise<{
  ok: boolean;
  opened?: boolean;
  form_url?: string;
  session_restored?: boolean;
  refilled?: boolean;
  official_ats?: boolean;
  method?: string;
  message?: string;
  error?: string;
}> {
  const res = await fetch(
    `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/items/${encodeURIComponent(item_id)}/open-form`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id, keep_open_ms }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function startShoppingCartApply(
  cart_id: string,
  user_id: string,
  item_ids?: string[],
  process_now = true
): Promise<{
  cart_id: string;
  queued_count: number;
  processed_count?: number;
  ok_count?: number;
  failed_count?: number;
  skipped: Array<{ item_id?: string; reason?: string }>;
  queued: Array<{ item_id?: string; intern_job_id?: string; apply?: CartApplyState }>;
  apply_summary?: ShoppingCartResponse["apply_summary"];
  phase?: number;
  message?: string;
}> {
  return post(`/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/apply/start`, {
    user_id,
    item_ids: item_ids || [],
    process_now,
  });
}

export async function processShoppingCartApply(
  cart_id: string,
  user_id: string,
  limit = 20
): Promise<{
  cart_id: string;
  processed_count?: number;
  ok_count?: number;
  failed_count?: number;
  apply_summary?: ShoppingCartResponse["apply_summary"];
  phase?: number;
}> {
  return post(`/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/apply/process`, {
    user_id,
    limit,
  });
}

export async function getShoppingCartApplyStatus(
  cart_id: string,
  user_id: string
): Promise<{
  cart_id: string;
  apply_summary?: ShoppingCartResponse["apply_summary"];
  items: ShoppingCartItem[];
}> {
  const params = new URLSearchParams({ user_id });
  const res = await fetch(
    `${API_BASE}/api/v1/shopping-cart/${encodeURIComponent(cart_id)}/apply/status?${params}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
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
