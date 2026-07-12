// T1204 — Feishu app tests setup
import { vi } from 'vitest';

(globalThis as any).uni = {
  requireNativePlugin: vi.fn(),
  navigateTo: vi.fn(),
  showToast: vi.fn(),
  showModal: vi.fn(),
};

(globalThis as any).tt = undefined;