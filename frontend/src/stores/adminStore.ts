/**
 * Admin Zustand store — state management for admin area.
 */
import { create } from 'zustand';

import type {
  IAdminUser,
  IAdminUserDetail,
  IAuditLogEntry,
  IDashboardStats,
  IPaginationMeta,
  IPlan,
  ISystemHealth,
} from '../services/adminApi';
import {
  fetchAdminUserDetail,
  fetchAdminUsers,
  fetchAuditLog,
  fetchDashboardStats,
  fetchPlans,
  fetchSystemHealth,
} from '../services/adminApi';

interface IAdminState {
  // Dashboard
  stats: IDashboardStats | null;
  statsLoading: boolean;
  health: ISystemHealth | null;
  healthLoading: boolean;

  // Users
  users: IAdminUser[];
  usersPagination: IPaginationMeta | null;
  usersLoading: boolean;
  userDetail: IAdminUserDetail | null;
  userDetailLoading: boolean;

  // Audit log
  auditLog: IAuditLogEntry[];
  auditPagination: IPaginationMeta | null;
  auditLoading: boolean;

  // Plans
  plans: IPlan[];
  plansLoading: boolean;

  // Actions
  loadStats: () => Promise<void>;
  loadHealth: () => Promise<void>;
  loadUsers: (params?: {
    page?: number;
    limit?: number;
    search?: string;
    role?: string;
    plan_tier?: string;
    is_active?: boolean;
  }) => Promise<void>;
  loadUserDetail: (userId: string) => Promise<void>;
  loadAuditLog: (params?: {
    page?: number;
    limit?: number;
    action?: string;
    actor_id?: string;
    target_type?: string;
  }) => Promise<void>;
  loadPlans: () => Promise<void>;
}

export const useAdminStore = create<IAdminState>((set) => ({
  stats: null,
  statsLoading: false,
  health: null,
  healthLoading: false,
  users: [],
  usersPagination: null,
  usersLoading: false,
  userDetail: null,
  userDetailLoading: false,
  auditLog: [],
  auditPagination: null,
  auditLoading: false,
  plans: [],
  plansLoading: false,

  loadStats: async () => {
    set({ statsLoading: true });
    try {
      const stats = await fetchDashboardStats();
      set({ stats });
    } finally {
      set({ statsLoading: false });
    }
  },

  loadHealth: async () => {
    set({ healthLoading: true });
    try {
      const health = await fetchSystemHealth();
      set({ health });
    } finally {
      set({ healthLoading: false });
    }
  },

  loadUsers: async (params) => {
    set({ usersLoading: true });
    try {
      const { items, pagination } = await fetchAdminUsers(params ?? {});
      set({ users: items, usersPagination: pagination });
    } finally {
      set({ usersLoading: false });
    }
  },

  loadUserDetail: async (userId) => {
    set({ userDetailLoading: true });
    try {
      const detail = await fetchAdminUserDetail(userId);
      set({ userDetail: detail });
    } finally {
      set({ userDetailLoading: false });
    }
  },

  loadAuditLog: async (params) => {
    set({ auditLoading: true });
    try {
      const { items, pagination } = await fetchAuditLog(params ?? {});
      set({ auditLog: items, auditPagination: pagination });
    } finally {
      set({ auditLoading: false });
    }
  },

  loadPlans: async () => {
    set({ plansLoading: true });
    try {
      const plans = await fetchPlans();
      set({ plans });
    } finally {
      set({ plansLoading: false });
    }
  },
}));
