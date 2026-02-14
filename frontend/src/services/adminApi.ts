/**
 * Admin API service — typed methods for admin endpoints.
 */
import { api } from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface IPaginationMeta {
  total: number;
  page: number;
  pages: number;
  limit: number;
}

export interface IDashboardStats {
  total_users: number;
  active_users: number;
  total_conversations: number;
  total_messages: number;
  total_documents: number;
  users_by_plan: Record<string, number>;
  users_by_role: Record<string, number>;
  recent_signups_7d: number;
  messages_today: number;
}

export interface IByoLlmTotals {
  messages: number;
  tokens: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  error_rate_pct: number;
  attempts_total: number;
  attempts_failed: number;
  tool_calls_total: number;
  tool_calls_failed: number;
}

export interface IByoLlmProviderModelItem {
  provider: string;
  model: string;
  messages: number;
  tokens: number;
  avg_latency_ms: number;
  error_rate_pct: number;
}

export interface IByoLlmToolItem {
  tool: string;
  calls: number;
  failed_calls: number;
  avg_duration_ms: number;
  error_rate_pct: number;
}

export interface IByoLlmAlert {
  code: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  current_value: number;
  threshold: number;
}

export interface IByoLlmExportRow {
  message_id: string;
  conversation_id: string;
  user_id: string;
  created_at: string;
  provider: string;
  model: string;
  tokens: number;
  latency_ms: number;
  attempts_total: number;
  attempts_failed: number;
  tool_calls_total: number;
  tool_calls_failed: number;
  fallback_triggered: boolean;
}

export interface IByoLlmUsageReport {
  start_date: string;
  end_date: string;
  provider_filter: string | null;
  totals: IByoLlmTotals;
  by_provider_model: IByoLlmProviderModelItem[];
  by_tool: IByoLlmToolItem[];
  alerts: IByoLlmAlert[];
  export_rows: IByoLlmExportRow[];
}

export interface IServiceStatus {
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  latency_ms?: number;
  details?: string;
}

export interface ISystemHealth {
  overall: 'healthy' | 'degraded' | 'down';
  services: IServiceStatus[];
  uptime_seconds?: number;
}

export interface IAdminUser {
  id: string;
  email: string;
  full_name: string | null;
  plan_tier: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface IUsageSummary {
  uploads_today: number;
  messages_today: number;
  tokens_today: number;
}

export interface ISubscription {
  id: string;
  user_id: string;
  plan_id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IAdminUserDetail extends IAdminUser {
  llm_provider: string | null;
  has_api_key: boolean;
  usage: IUsageSummary;
  subscription: ISubscription | null;
}

export interface IAdminUserUpdate {
  role?: string;
  is_active?: boolean;
  plan_tier?: string;
}

export interface IAuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  changes: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface IPlan {
  id: string;
  name: string;
  display_name: string;
  stripe_product_id: string | null;
  stripe_price_id: string | null;
  price_cents: number;
  billing_period: string;
  upload_limit_daily: number;
  max_file_size_mb: number;
  max_conversations_daily: number;
  max_tokens_daily: number;
  features: Record<string, boolean> | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface IPlanCreate {
  name: string;
  display_name: string;
  stripe_product_id?: string | null;
  stripe_price_id?: string | null;
  price_cents: number;
  billing_period: string;
  upload_limit_daily: number;
  max_file_size_mb: number;
  max_conversations_daily: number;
  max_tokens_daily: number;
  features?: Record<string, boolean>;
  is_active?: boolean;
  sort_order?: number;
}

export interface IPlanUpdate {
  display_name?: string;
  stripe_product_id?: string | null;
  stripe_price_id?: string | null;
  price_cents?: number;
  billing_period?: string;
  upload_limit_daily?: number;
  max_file_size_mb?: number;
  max_conversations_daily?: number;
  max_tokens_daily?: number;
  features?: Record<string, boolean>;
  is_active?: boolean;
  sort_order?: number;
}

export interface IEmailLog {
  id: string;
  recipient_email: string;
  recipient_user_id: string | null;
  email_type: string;
  subject: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ISystemSetting {
  id: string;
  key: string;
  value: string;
  is_encrypted: boolean;
  description: string | null;
  updated_at: string;
}

export interface ISystemSettingUpdate {
  value: string;
  description?: string;
}

export interface ISystemMemory {
  id: string;
  scope: 'system';
  scope_name: string | null;
  memory_key: string;
  memory_value: string;
  tags: string[] | null;
  ttl_seconds: number | null;
  expires_at: string | null;
  version: number;
  is_active: boolean;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ISystemMemoryCreate {
  memory_key: string;
  memory_value: string;
  tags?: string[] | null;
  ttl_seconds?: number;
}

export interface ISystemMemoryUpdate {
  memory_key?: string;
  memory_value?: string;
  tags?: string[] | null;
  ttl_seconds?: number;
  clear_ttl?: boolean;
}

// ---------------------------------------------------------------------------
// API Methods
// ---------------------------------------------------------------------------

export async function fetchDashboardStats(): Promise<IDashboardStats> {
  const r = await api.get<IDashboardStats>('/admin/dashboard');
  return r.data;
}

export async function fetchByoLlmUsageReport(params: {
  start_date?: string;
  end_date?: string;
  provider?: string;
  user_id?: string;
}): Promise<IByoLlmUsageReport> {
  const r = await api.get<IByoLlmUsageReport>('/admin/usage/byollm', { params });
  return r.data;
}

export async function exportByoLlmUsageCsv(params: {
  start_date?: string;
  end_date?: string;
  provider?: string;
  user_id?: string;
}): Promise<Blob> {
  const r = await api.get('/admin/usage/byollm', {
    params: { ...params, export: 'csv' },
    responseType: 'blob',
  });
  return r.data as Blob;
}

export async function fetchSystemHealth(): Promise<ISystemHealth> {
  const r = await api.get<ISystemHealth>('/admin/system-health');
  return r.data;
}

export async function fetchAdminUsers(params: {
  page?: number;
  limit?: number;
  search?: string;
  role?: string;
  plan_tier?: string;
  is_active?: boolean;
}): Promise<{ items: IAdminUser[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/users', { params });
  return r.data;
}

export async function fetchAdminUserDetail(userId: string): Promise<IAdminUserDetail> {
  const r = await api.get<IAdminUserDetail>(`/admin/users/${userId}`);
  return r.data;
}

export async function updateAdminUser(
  userId: string,
  data: IAdminUserUpdate,
): Promise<IAdminUserDetail> {
  const r = await api.patch<IAdminUserDetail>(`/admin/users/${userId}`, data);
  return r.data;
}

export async function deleteAdminUser(userId: string): Promise<void> {
  await api.delete(`/admin/users/${userId}`);
}

export async function fetchAuditLog(params: {
  page?: number;
  limit?: number;
  action?: string;
  actor_id?: string;
  target_type?: string;
}): Promise<{ items: IAuditLogEntry[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/audit-log', { params });
  return r.data;
}

export async function fetchPlans(): Promise<IPlan[]> {
  const r = await api.get<IPlan[]>('/admin/plans');
  return r.data;
}

export async function createPlan(data: IPlanCreate): Promise<IPlan> {
  const r = await api.post<IPlan>('/admin/plans', data);
  return r.data;
}

export async function updatePlan(planId: string, data: IPlanUpdate): Promise<IPlan> {
  const r = await api.patch<IPlan>(`/admin/plans/${planId}`, data);
  return r.data;
}

export async function deletePlan(planId: string): Promise<IPlan> {
  const r = await api.delete<IPlan>(`/admin/plans/${planId}`);
  return r.data;
}

export async function stripeSyncPlan(planId: string): Promise<IPlan> {
  const r = await api.post<IPlan>(`/admin/plans/${planId}/stripe-sync`);
  return r.data;
}

// ---------------------------------------------------------------------------
// System Settings
// ---------------------------------------------------------------------------

export async function fetchSettings(): Promise<ISystemSetting[]> {
  const r = await api.get<ISystemSetting[]>('/admin/settings');
  return r.data;
}

export async function upsertSetting(
  key: string,
  data: ISystemSettingUpdate,
): Promise<ISystemSetting> {
  const r = await api.put<ISystemSetting>(`/admin/settings/${key}`, data);
  return r.data;
}

export async function testEmail(): Promise<{ message: string }> {
  const r = await api.post<{ message: string }>('/admin/settings/test-email');
  return r.data;
}

export async function testR2(): Promise<{ message: string }> {
  const r = await api.post<{ message: string }>('/admin/settings/test-r2');
  return r.data;
}

export async function testStripe(): Promise<{ message: string }> {
  const r = await api.post<{ message: string }>('/admin/settings/test-stripe');
  return r.data;
}

// ---------------------------------------------------------------------------
// System Memories
// ---------------------------------------------------------------------------

export async function fetchSystemMemories(params?: {
  include_inactive?: boolean;
}): Promise<ISystemMemory[]> {
  const r = await api.get<ISystemMemory[]>('/admin/system-memories', { params });
  return r.data;
}

export async function createSystemMemory(data: ISystemMemoryCreate): Promise<ISystemMemory> {
  const r = await api.post<ISystemMemory>('/admin/system-memories', data);
  return r.data;
}

export async function updateSystemMemory(
  memoryId: string,
  data: ISystemMemoryUpdate,
): Promise<ISystemMemory> {
  const r = await api.patch<ISystemMemory>(`/admin/system-memories/${memoryId}`, data);
  return r.data;
}

export async function deleteSystemMemory(memoryId: string): Promise<void> {
  await api.delete(`/admin/system-memories/${memoryId}`);
}

export async function testFreeLlm(): Promise<{ message: string }> {
  const r = await api.post<{ message: string }>('/admin/settings/test-free-llm');
  return r.data;
}

// ---------------------------------------------------------------------------
// Email Logs
// ---------------------------------------------------------------------------

export async function fetchEmailLogs(params: {
  page?: number;
  limit?: number;
  email_type?: string;
  status?: string;
  search?: string;
}): Promise<{ items: IEmailLog[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/email-logs', { params });
  return r.data;
}

// ---------------------------------------------------------------------------
// Email Templates
// ---------------------------------------------------------------------------

export interface IEmailTemplateVariable {
  name: string;
  description: string;
}

export interface IEmailTemplate {
  id: string;
  email_type: string;
  subject: string;
  body_html: string;
  variables: IEmailTemplateVariable[];
  is_active: boolean;
  updated_at: string;
  updated_by: string | null;
}

export interface IEmailTemplateUpdate {
  subject?: string;
  body_html?: string;
  is_active?: boolean;
}

export interface IEmailTemplatePreview {
  subject: string;
  html: string;
}

export async function fetchEmailTemplates(): Promise<IEmailTemplate[]> {
  const r = await api.get<IEmailTemplate[]>('/admin/email-templates');
  return r.data;
}

export async function fetchEmailTemplate(emailType: string): Promise<IEmailTemplate> {
  const r = await api.get<IEmailTemplate>(`/admin/email-templates/${emailType}`);
  return r.data;
}

export async function updateEmailTemplate(
  emailType: string,
  data: IEmailTemplateUpdate,
): Promise<IEmailTemplate> {
  const r = await api.put<IEmailTemplate>(`/admin/email-templates/${emailType}`, data);
  return r.data;
}

export async function previewEmailTemplate(
  emailType: string,
  variables?: Record<string, string>,
): Promise<IEmailTemplatePreview> {
  const r = await api.post<IEmailTemplatePreview>(
    `/admin/email-templates/${emailType}/preview`,
    { variables: variables ?? {} },
  );
  return r.data;
}

// ---------------------------------------------------------------------------
// Stripe Events
// ---------------------------------------------------------------------------

export interface IStripeEvent {
  id: string;
  event_id: string;
  event_type: string;
  status: string;
  customer_id: string | null;
  subscription_id: string | null;
  user_id: string | null;
  error_message: string | null;
  payload_summary: string | null;
  created_at: string;
}

export async function fetchStripeEvents(params: {
  page?: number;
  limit?: number;
  event_type?: string;
  status?: string;
}): Promise<{ items: IStripeEvent[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/stripe-events', { params });
  return r.data;
}

// ---------------------------------------------------------------------------
// RAG Management
// ---------------------------------------------------------------------------

export interface IRagStats {
  total_documents: number;
  total_chunks: number;
  global_documents: number;
  global_chunks: number;
  local_documents: number;
  local_chunks: number;
  by_file_type: { file_type: string; count: number }[];
  by_status: { status: string; count: number }[];
}

export interface IRagDocument {
  id: string;
  user_id: string | null;
  user_email: string | null;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  chunk_count: number;
  metadata: Record<string, unknown> | null;
  created_at: string;
  processed_at: string | null;
}

export interface IRagUploadResponse {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  created_at: string;
}

export interface IRagIngestUrlResponse {
  id: string;
  original_filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  source_url: string;
  created_at: string;
}

export interface IRagReprocessResponse {
  id: string;
  status: string;
  message: string;
}

export async function fetchRagStats(): Promise<IRagStats> {
  const r = await api.get<IRagStats>('/admin/rag/stats');
  return r.data;
}

export async function fetchRagDocuments(params: {
  page?: number;
  limit?: number;
  scope?: 'global' | 'local' | 'all';
  status?: string;
  file_type?: string;
  search?: string;
}): Promise<{ items: IRagDocument[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/rag/documents', { params });
  return r.data;
}

export async function uploadRagDocument(file: File): Promise<IRagUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const r = await api.post<IRagUploadResponse>('/admin/rag/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return r.data;
}

export async function ingestRagUrl(data: {
  url: string;
  title?: string;
}): Promise<IRagIngestUrlResponse> {
  const r = await api.post<IRagIngestUrlResponse>('/admin/rag/documents/ingest-url', data);
  return r.data;
}

export async function reprocessRagDocument(id: string): Promise<IRagReprocessResponse> {
  const r = await api.post<IRagReprocessResponse>(`/admin/rag/documents/${id}/reprocess`);
  return r.data;
}

export async function deleteRagDocument(id: string): Promise<void> {
  await api.delete(`/admin/rag/documents/${id}`);
}

// ---------------------------------------------------------------------------
// RAG Gap Tracking
// ---------------------------------------------------------------------------

export interface IRagGapItem {
  id: string;
  user_id: string | null;
  user_email: string | null;
  conversation_id: string | null;
  tool_name: string;
  query: string;
  gap_type: string;
  result_preview: string | null;
  created_at: string;
}

export interface ITopGapQuery {
  query: string;
  count: number;
  last_seen: string;
}

export interface IRagGapStats {
  total_gaps: number;
  global_gaps: number;
  local_gaps: number;
  top_queries: ITopGapQuery[];
}

export async function fetchRagGaps(params: {
  page?: number;
  limit?: number;
  tool_name?: string;
  gap_type?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}): Promise<{ items: IRagGapItem[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/rag/gaps', { params });
  return r.data;
}

export async function fetchRagGapStats(): Promise<IRagGapStats> {
  const r = await api.get<IRagGapStats>('/admin/rag/gaps/stats');
  return r.data;
}

// ---------------------------------------------------------------------------
// Celery Task Events
// ---------------------------------------------------------------------------

export interface ICeleryTaskEvent {
  id: string;
  task_id: string;
  task_name: string;
  status: string;
  args_summary: string | null;
  result_summary: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  worker: string | null;
}

export async function fetchCeleryTasks(params: {
  page?: number;
  limit?: number;
  status?: string;
  task_name?: string;
}): Promise<{ items: ICeleryTaskEvent[]; pagination: IPaginationMeta }> {
  const r = await api.get('/admin/celery-tasks', { params });
  return r.data;
}
