"use client";

import { create } from "zustand";
import { api } from "./api";

interface User {
  id: string;
  email: string;
  full_name: string;
  phone?: string;
  role: string;
  avatar_url?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, phone?: string) => Promise<void>;
  logout: () => void;
  loadUser: () => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  token: typeof window !== "undefined" ? localStorage.getItem("token") : null,
  isLoading: false,

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const res: any = await api.auth.login({ email, password });
      localStorage.setItem("token", res.access_token);
      set({ user: res.user, token: res.access_token, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (email, password, fullName, phone) => {
    set({ isLoading: true });
    try {
      const res: any = await api.auth.register({
        email,
        password,
        full_name: fullName,
        phone,
      });
      localStorage.setItem("token", res.access_token);
      set({ user: res.user, token: res.access_token, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ user: null, token: null });
  },

  loadUser: async () => {
    const token = get().token;
    if (!token) return;
    try {
      const user: any = await api.auth.me(token);
      set({ user });
    } catch {
      localStorage.removeItem("token");
      set({ user: null, token: null });
    }
  },
}));
