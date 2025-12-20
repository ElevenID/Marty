/**
 * Playwright test fixtures for Marty Verifier E2E tests.
 * Provides Tauri IPC mocking and page object helpers.
 */
import { test as base, expect, Page } from '@playwright/test';

// Types for Tauri mock state
export interface LicenseStatus {
  valid: boolean;
  org_id: string | null;
  features: string[];
  expires_at: string | null;
  days_until_expiry: number | null;
  grace_period_active: boolean;
  grace_period_days: number | null;
  hardware_bound: boolean;
  deployment_mode: string | null;
  max_daily_verifications: number | null;
  verifications_today: number;
}

export interface SyncStatus {
  last_sync: string | null;
  hours_since_sync: number | null;
  sync_overdue: boolean;
  iaca_certificates: number;
  csca_certificates: number;
  dsc_certificates: number;
  last_error: string | null;
}

export interface HardwareCapabilities {
  has_camera: boolean;
  has_nfc: boolean;
  has_ble: boolean;
  has_biometric: boolean;
  has_tpm: boolean;
}

// Default mock values
export const defaultLicenseStatus: LicenseStatus = {
  valid: true,
  org_id: 'test-org',
  features: ['mdl', 'oid4vp', 'emrtd'],
  expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  days_until_expiry: 30,
  grace_period_active: false,
  grace_period_days: null,
  hardware_bound: false,
  deployment_mode: 'development',
  max_daily_verifications: 1000,
  verifications_today: 5,
};

export const defaultSyncStatus: SyncStatus = {
  last_sync: new Date().toISOString(),
  hours_since_sync: 1,
  sync_overdue: false,
  iaca_certificates: 56,
  csca_certificates: 120,
  dsc_certificates: 450,
  last_error: null,
};

export const defaultHardwareCapabilities: HardwareCapabilities = {
  has_camera: true,
  has_nfc: false,
  has_ble: false,
  has_biometric: false,
  has_tpm: false,
};

// Mock command responses
export interface MockCommands {
  get_license_status?: LicenseStatus;
  get_sync_status?: SyncStatus;
  detect_hardware_tier?: string;
  get_hardware_capabilities?: HardwareCapabilities;
  get_config?: object;
  check_online?: boolean;
  [key: string]: unknown;
}

// Extended test fixture with Tauri mocking
export interface TestFixtures {
  mockTauri: (commands?: MockCommands) => Promise<void>;
  setLicenseStatus: (status: Partial<LicenseStatus>) => Promise<void>;
  setSyncStatus: (status: Partial<SyncStatus>) => Promise<void>;
  setOffline: () => Promise<void>;
  setOnline: () => Promise<void>;
}

/**
 * Inject Tauri mock into page before navigation
 */
async function injectTauriMock(page: Page, commands: MockCommands = {}) {
  const mockCommands = {
    get_license_status: defaultLicenseStatus,
    get_sync_status: defaultSyncStatus,
    detect_hardware_tier: 'Simple',
    get_hardware_capabilities: defaultHardwareCapabilities,
    check_online: true,
    get_config: {
      sync_config: {
        sync_interval_hours: 24,
        max_offline_hours: 72,
        enable_usb_import: true,
      },
      reporting_config: {
        enabled: true,
        local_only: false,
        batch_interval_minutes: 15,
      },
      ui_config: {
        theme: 'light',
        kiosk_mode: false,
        show_offline_banner: true,
      },
      retention: {
        verification_events_days: 30,
        audit_log_days: 90,
        encrypt_pii: true,
      },
    },
    ...commands,
  };

  await page.addInitScript((cmds) => {
    // Create Tauri mock
    const mockInvoke = (command: string, args?: unknown) => {
      console.log(`[Tauri Mock] invoke: ${command}`, args);
      if (command in cmds) {
        return Promise.resolve(cmds[command as keyof typeof cmds]);
      }
      console.warn(`[Tauri Mock] Unmocked command: ${command}`);
      return Promise.resolve(null);
    };

    // Set up window.__TAURI_INTERNALS__
    (window as any).__TAURI_INTERNALS__ = {
      invoke: mockInvoke,
      convertFileSrc: (src: string) => src,
      transformCallback: () => {},
      metadata: {
        currentWindow: { label: 'main' },
        currentWebviewWindow: { label: 'main' },
      },
    };

    // Also mock the module imports
    (window as any).__TAURI_MOCK_COMMANDS__ = cmds;
  }, mockCommands);
}

// Extended test with fixtures
export const test = base.extend<TestFixtures>({
  mockTauri: async ({ page }, use) => {
    const mock = async (commands: MockCommands = {}) => {
      await injectTauriMock(page, commands);
    };
    await use(mock);
  },

  setLicenseStatus: async ({ page }, use) => {
    const setter = async (status: Partial<LicenseStatus>) => {
      await page.evaluate((s) => {
        const cmds = (window as any).__TAURI_MOCK_COMMANDS__ || {};
        cmds.get_license_status = { ...cmds.get_license_status, ...s };
        (window as any).__TAURI_MOCK_COMMANDS__ = cmds;
      }, status);
    };
    await use(setter);
  },

  setSyncStatus: async ({ page }, use) => {
    const setter = async (status: Partial<SyncStatus>) => {
      await page.evaluate((s) => {
        const cmds = (window as any).__TAURI_MOCK_COMMANDS__ || {};
        cmds.get_sync_status = { ...cmds.get_sync_status, ...s };
        (window as any).__TAURI_MOCK_COMMANDS__ = cmds;
      }, status);
    };
    await use(setter);
  },

  setOffline: async ({ page }, use) => {
    const setter = async () => {
      await page.evaluate(() => {
        const cmds = (window as any).__TAURI_MOCK_COMMANDS__ || {};
        cmds.check_online = false;
        (window as any).__TAURI_MOCK_COMMANDS__ = cmds;
      });
    };
    await use(setter);
  },

  setOnline: async ({ page }, use) => {
    const setter = async () => {
      await page.evaluate(() => {
        const cmds = (window as any).__TAURI_MOCK_COMMANDS__ || {};
        cmds.check_online = true;
        (window as any).__TAURI_MOCK_COMMANDS__ = cmds;
      });
    };
    await use(setter);
  },
});

export { expect };
