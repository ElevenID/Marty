/**
 * Vitest setup file for unit and component tests.
 * Sets up testing-library matchers and Tauri IPC mocks.
 */
import '@testing-library/jest-dom';
import { vi, beforeEach } from 'vitest';

// Mock Tauri IPC for unit tests
// This allows testing React components that call Tauri commands
const mockInvoke = vi.fn();
const mockListen = vi.fn();
const mockOnce = vi.fn();

// Create window.__TAURI_INTERNALS__ mock
const tauriMock = {
  invoke: mockInvoke,
  convertFileSrc: vi.fn((src: string) => src),
  transformCallback: vi.fn(),
};

// Set up global Tauri mock
Object.defineProperty(window, '__TAURI_INTERNALS__', {
  value: tauriMock,
  writable: true,
});

// Mock @tauri-apps/api/core
vi.mock('@tauri-apps/api/core', () => ({
  invoke: mockInvoke,
  convertFileSrc: vi.fn((src: string) => src),
  transformCallback: vi.fn(),
}));

// Mock @tauri-apps/api/event
vi.mock('@tauri-apps/api/event', () => ({
  listen: mockListen,
  once: mockOnce,
  emit: vi.fn(),
  TauriEvent: {
    WINDOW_RESIZED: 'tauri://resize',
    WINDOW_MOVED: 'tauri://move',
    WINDOW_CLOSE_REQUESTED: 'tauri://close-requested',
    WINDOW_CREATED: 'tauri://window-created',
    WINDOW_DESTROYED: 'tauri://destroyed',
    WINDOW_FOCUS: 'tauri://focus',
    WINDOW_BLUR: 'tauri://blur',
    WINDOW_SCALE_FACTOR_CHANGED: 'tauri://scale-change',
    WINDOW_THEME_CHANGED: 'tauri://theme-changed',
  },
}));

// Mock @tauri-apps/api/window
vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: vi.fn(() => ({
    listen: mockListen,
    once: mockOnce,
    setFullscreen: vi.fn(),
    isFullscreen: vi.fn(() => Promise.resolve(false)),
    minimize: vi.fn(),
    maximize: vi.fn(),
    close: vi.fn(),
  })),
  Window: vi.fn(),
}));

// Helper to set up mock responses for specific Tauri commands
export function mockTauriCommand<T>(command: string, response: T) {
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === command) {
      return Promise.resolve(response);
    }
    return Promise.reject(new Error(`Unmocked command: ${cmd}`));
  });
}

// Helper to set up mock responses for multiple commands
export function mockTauriCommands(commands: Record<string, unknown>) {
  mockInvoke.mockImplementation((cmd: string, args?: unknown) => {
    if (cmd in commands) {
      const handler = commands[cmd];
      // If it's a function, call it with args
      if (typeof handler === 'function') {
        return Promise.resolve(handler(args));
      }
      // If it has __error property, reject with that error
      if (handler && typeof handler === 'object' && '__error' in handler) {
        return Promise.reject(new Error((handler as { __error: string }).__error));
      }
      return Promise.resolve(handler);
    }
    return Promise.reject(new Error(`Unmocked command: ${cmd}`));
  });
}

// Helper to make a command fail
export function mockTauriCommandError(command: string, error: string) {
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === command) {
      return Promise.reject(new Error(error));
    }
    return Promise.reject(new Error(`Unmocked command: ${cmd}`));
  });
}

// Reset mocks before each test
beforeEach(() => {
  mockInvoke.mockReset();
  mockListen.mockReset();
  mockOnce.mockReset();
  
  // Default: return empty/safe values
  mockInvoke.mockImplementation((cmd: string) => {
    console.warn(`Unmocked Tauri command: ${cmd}`);
    return Promise.resolve(null);
  });
  
  mockListen.mockImplementation(() => Promise.resolve(() => {}));
  mockOnce.mockImplementation(() => Promise.resolve(() => {}));
});

// Export mocks for direct access in tests
export { mockInvoke, mockListen, mockOnce };
