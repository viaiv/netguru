import { api } from './api';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface IPublicPlan {
  id: string;
  name: string;
  display_name: string;
  price_cents: number;
  billing_period: string;
  promo_price_cents: number | null;
  promo_months: number | null;
  max_members: number;
  price_per_extra_seat_cents: number;
  upload_limit_daily: number;
  max_file_size_mb: number;
  max_conversations_daily: number;
  max_tokens_daily: number;
  features: Record<string, unknown> | null;
  sort_order: number;
  is_purchasable: boolean;
}

export interface ISubscriptionDetail {
  id: string;
  status: string;
  stripe_subscription_id: string | null;
  seat_quantity: number;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
}

export interface IUsageToday {
  uploads_today: number;
  messages_today: number;
  tokens_today: number;
}

export interface ISeatInfo {
  max_members_included: number;
  current_members: number;
  seats_billed: number;
  extra_seats: number;
  extra_seat_price_cents: number;
  can_invite: boolean;
}

export interface IUserSubscriptionPlan {
  id: string;
  name: string;
  display_name: string;
  price_cents: number;
  billing_period: string;
  max_members: number;
  price_per_extra_seat_cents: number;
  upload_limit_daily: number;
  max_file_size_mb: number;
  max_conversations_daily: number;
  max_tokens_daily: number;
  features: Record<string, unknown> | null;
}

export interface IUserSubscription {
  has_subscription: boolean;
  plan: IUserSubscriptionPlan;
  subscription: ISubscriptionDetail | null;
  usage_today: IUsageToday;
  seat_info: ISeatInfo | null;
}

export interface ICheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export interface IPortalResponse {
  portal_url: string;
}

/* ------------------------------------------------------------------ */
/* API calls                                                           */
/* ------------------------------------------------------------------ */

export async function fetchPublicPlans(): Promise<IPublicPlan[]> {
  const response = await api.get<IPublicPlan[]>('/plans');
  return response.data;
}

export async function fetchMySubscription(): Promise<IUserSubscription> {
  const response = await api.get<IUserSubscription>('/billing/subscription');
  return response.data;
}

export async function createCheckout(planId: string): Promise<ICheckoutResponse> {
  const response = await api.post<ICheckoutResponse>('/billing/checkout', {
    plan_id: planId,
    success_url: `${window.location.origin}/billing/success`,
    cancel_url: `${window.location.origin}/pricing`,
  });
  return response.data;
}

export async function createPortalSession(): Promise<IPortalResponse> {
  const response = await api.post<IPortalResponse>('/billing/portal');
  return response.data;
}

export async function updateSeats(quantity: number): Promise<ISeatInfo> {
  const response = await api.post<ISeatInfo>('/billing/seats', { quantity });
  return response.data;
}
