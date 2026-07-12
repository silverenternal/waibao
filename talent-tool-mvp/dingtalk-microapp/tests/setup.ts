// T1204 — DingTalk microapp tests setup
import { vi } from 'vitest';

// Mock uni.* APIs used by dd.ts
(globalThis as any).uni = {
  requireNativePlugin: vi.fn(),
  navigateTo: vi.fn(),
  showToast: vi.fn(),
  showModal: vi.fn(),
};

// Mock dd global (no real container in test)
(globalThis as any).dd = undefined;