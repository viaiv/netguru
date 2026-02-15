import { api } from './api';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface IWorkspaceResponse {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  plan_tier: string;
  created_at: string;
  updated_at: string;
}

export interface IWorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  workspace_role: string;
  joined_at: string;
}

export interface IWorkspaceSeatInfo {
  max_members_included: number;
  current_members: number;
  seats_billed: number;
  extra_seats: number;
  extra_seat_price_cents: number;
  can_invite: boolean;
}

export interface IWorkspaceDetail extends IWorkspaceResponse {
  members: IWorkspaceMember[];
  member_count: number;
  seat_info: IWorkspaceSeatInfo | null;
}

/* ------------------------------------------------------------------ */
/* API calls                                                           */
/* ------------------------------------------------------------------ */

export async function fetchMyWorkspaces(): Promise<IWorkspaceResponse[]> {
  const response = await api.get<IWorkspaceResponse[]>('/workspaces');
  return response.data;
}

export async function createWorkspace(name: string): Promise<IWorkspaceResponse> {
  const response = await api.post<IWorkspaceResponse>('/workspaces', { name });
  return response.data;
}

export async function fetchWorkspaceDetail(workspaceId: string): Promise<IWorkspaceDetail> {
  const response = await api.get<IWorkspaceDetail>(`/workspaces/${workspaceId}`);
  return response.data;
}

export async function updateWorkspace(
  workspaceId: string,
  name: string,
): Promise<IWorkspaceResponse> {
  const response = await api.patch<IWorkspaceResponse>(`/workspaces/${workspaceId}`, { name });
  return response.data;
}

export async function inviteMember(
  workspaceId: string,
  email: string,
  workspaceRole: string = 'member',
): Promise<IWorkspaceMember> {
  const response = await api.post<IWorkspaceMember>(`/workspaces/${workspaceId}/members`, {
    email,
    workspace_role: workspaceRole,
  });
  return response.data;
}

export async function removeMember(
  workspaceId: string,
  userId: string,
): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/members/${userId}`);
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  workspaceRole: string,
): Promise<IWorkspaceMember> {
  const response = await api.patch<IWorkspaceMember>(
    `/workspaces/${workspaceId}/members/${userId}/role`,
    { workspace_role: workspaceRole },
  );
  return response.data;
}

export async function switchWorkspace(workspaceId: string): Promise<IWorkspaceResponse> {
  const response = await api.post<IWorkspaceResponse>(`/workspaces/switch/${workspaceId}`);
  return response.data;
}
