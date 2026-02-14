import { api } from './api';

export type MemoryScope = 'global' | 'site' | 'device';

export interface IMemory {
  id: string;
  user_id: string;
  scope: MemoryScope;
  scope_name: string | null;
  memory_key: string;
  memory_value: string;
  tags: string[] | null;
  ttl_seconds: number | null;
  expires_at: string | null;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ICreateMemoryPayload {
  scope: MemoryScope;
  scope_name?: string | null;
  memory_key: string;
  memory_value: string;
  tags?: string[] | null;
  ttl_seconds?: number;
}

export interface IUpdateMemoryPayload {
  scope?: MemoryScope;
  scope_name?: string | null;
  memory_key?: string;
  memory_value?: string;
  tags?: string[] | null;
  ttl_seconds?: number;
  clear_ttl?: boolean;
}

export async function fetchMemories(params?: {
  scope?: MemoryScope;
  scope_name?: string;
  include_inactive?: boolean;
}): Promise<IMemory[]> {
  const response = await api.get<IMemory[]>('/memories', { params });
  return response.data;
}

export async function createMemory(payload: ICreateMemoryPayload): Promise<IMemory> {
  const response = await api.post<IMemory>('/memories', payload);
  return response.data;
}

export async function updateMemory(memoryId: string, payload: IUpdateMemoryPayload): Promise<IMemory> {
  const response = await api.patch<IMemory>(`/memories/${memoryId}`, payload);
  return response.data;
}

export async function deleteMemory(memoryId: string): Promise<void> {
  await api.delete(`/memories/${memoryId}`);
}
