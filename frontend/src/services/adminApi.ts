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

// ---------------------------------------------------------------------------
// API Methods
// ---------------------------------------------------------------------------

export async function fetchDashboardStats(): Promise<IDashboardStats> {
  const r = await api.get<IDashboardStats>('/admin/dashboard');
  return r.data;
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
