"use client";

import { create } from "zustand";

export type UiSection = "chat" | "recommendations" | "settings" | "memory";

type UiState = {
  section: UiSection;
  sidebarCollapsed: boolean;
  mobileOpen: boolean;
  setSection: (section: UiSection) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileOpen: (open: boolean) => void;
};

export const useUi = create<UiState>((set) => ({
  section: "chat",
  sidebarCollapsed: false,
  mobileOpen: false,
  setSection: (section) => set({ section, mobileOpen: false }),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  setMobileOpen: (mobileOpen) => set({ mobileOpen }),
}));
