/**
 * Admin Zustand store — state management for admin area.
 */
import { create } from 'zustand';

import type {
  IAdminUser,
  IAdminUserDetail,
  IAuditLogEntry,
  IDashboardStats,
  IEmailLog,
  IPaginationMeta,
  IPlan,
  ISystemHealth,
  ISystemSetting,
} from '../services/adminApi';
import {
  fetchAdminUserDetail,
  fetchAdminUsers,
  fetchAuditLog,
  fetchDashboardStats,
  fetchEmailLogs,
  fetchPlans,
  fetchSettings,
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

  // Settings
  settings: ISystemSetting[];
  settingsLoading: boolean;

  // Email logs
  emailLogs: IEmailLog[];
  emailLogsPagination: IPaginationMeta | null;
  emailLogsLoading: boolean;

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
  loadSettings: () => Promise<void>;
  loadEmailLogs: (params?: {
    page?: number;
    limit?: number;
    email_type?: string;
    status?: string;
    search?: string;
  }) => Promise<void>;
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
  settings: [],
  settingsLoading: false,
  emailLogs: [],
  emailLogsPagination: null,
  emailLogsLoading: false,

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

  loadSettings: async () => {
    set({ settingsLoading: true });
    try {
      const settings = await fetchSettings();
      set({ settings });
    } finally {
      set({ settingsLoading: false });
    }
  },

  loadEmailLogs: async (params) => {
    set({ emailLogsLoading: true });
    try {
      const { items, pagination } = await fetchEmailLogs(params ?? {});
      set({ emailLogs: items, emailLogsPagination: pagination });
    } finally {
      set({ emailLogsLoading: false });
    }
  },
}));
