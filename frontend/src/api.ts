import { Issue, Task, PlatformSettings, DiscoveryStatus, AuditLog } from './types';

const API_BASE = '/api/v1';

const AUTH_TOKEN_KEY = 'issuetopr_auth_token';
let onUnauthorizedCallback: (() => void) | null = null;

export function setOnUnauthorized(cb: () => void) {
  onUnauthorizedCallback = cb;
}

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getAuthToken();
}

export async function loginWithPassword(password: string): Promise<string> {
  const trimmed = password.trim();
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: trimmed }),
    });
    if (res.ok) {
      const data = await res.json();
      setAuthToken(data.token);
      return data.token;
    }
    if (res.status === 401) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Incorrect password. Access denied.");
    }
  } catch (err: any) {
    if (err.message && err.message.includes("Incorrect password")) {
      throw err;
    }
    // Fallback for static GitHub Pages hosting where /api/v1 is not a live server
  }

  // Client-side fallback authentication (for GitHub Pages static host)
  if (trimmed === 'mwps@1534') {
    const clientToken = `client_session_${Date.now()}_${Math.random().toString(36).substring(2)}`;
    setAuthToken(clientToken);
    return clientToken;
  }

  throw new Error("Incorrect password. Access denied.");
}

export async function verifyAuth(): Promise<boolean> {
  const token = getAuthToken();
  if (!token) return false;
  if (token.startsWith('client_session_')) return true;
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) {
      if (res.status === 404) return true; // Static hosting fallback
      clearAuthToken();
      return false;
    }
    return true;
  } catch {
    return true; // Static hosting / offline fallback
  }
}

export function logout() {
  clearAuthToken();
  if (onUnauthorizedCallback) {
    onUnauthorizedCallback();
  }
}

// ==========================================
// WebAuthn Device Biometric Authentication
// ==========================================

const BIOMETRIC_CRED_ID_KEY = 'issuetopr_biometric_cred_id';

export function getStoredBiometricCredentialId(): string | null {
  return localStorage.getItem(BIOMETRIC_CRED_ID_KEY);
}

export function setStoredBiometricCredentialId(id: string) {
  localStorage.setItem(BIOMETRIC_CRED_ID_KEY, id);
}

export function clearStoredBiometricCredentialId() {
  localStorage.removeItem(BIOMETRIC_CRED_ID_KEY);
}

export function isSecureContextAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.isSecureContext;
}

export function getValidRpId(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const hostname = window.location.hostname;
  // W3C Web Authentication specification Level 2 & 3 explicitly states:
  // "An RP ID must be a valid domain string, and cannot be an IP address."
  const isIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(hostname) || hostname === '[::1]';
  if (isIp) {
    return undefined; // Let browser default to document origin
  }
  return hostname || undefined;
}

export async function isBiometricsSupported(): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  if (!window.isSecureContext) return false;
  if (!window.PublicKeyCredential) return false;
  if (typeof PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable !== 'function') return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

function bufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlToBuffer(base64Url: string): ArrayBuffer {
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const pad = base64.length % 4 === 0 ? '' : '='.repeat(4 - (base64.length % 4));
  const binary = window.atob(base64 + pad);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export async function getBiometricStatus(): Promise<{ has_registered_credentials: boolean; registered_count: number }> {
  try {
    const res = await fetch(`${API_BASE}/auth/biometric/status`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Static hosting fallback
  }
  const hasLocal = !!getStoredBiometricCredentialId();
  return {
    has_registered_credentials: hasLocal,
    registered_count: hasLocal ? 1 : 0
  };
}

async function fetchOrGenerateChallenge(): Promise<string> {
  try {
    const chalRes = await fetch(`${API_BASE}/auth/biometric/challenge`);
    if (chalRes.ok) {
      const { challenge } = await chalRes.json();
      if (challenge) return challenge;
    }
  } catch {
    // Static hosting fallback
  }
  // Client-side 32-byte cryptographic challenge
  const randomBytes = new Uint8Array(32);
  window.crypto.getRandomValues(randomBytes);
  return bufferToBase64Url(randomBytes.buffer);
}

export async function registerDeviceBiometrics(password?: string, deviceName?: string): Promise<string> {
  if (!navigator.credentials || !navigator.credentials.create) {
    throw new Error('Biometric authentication is not supported by your browser.');
  }

  const challenge = await fetchOrGenerateChallenge();
  const challengeBuffer = base64UrlToBuffer(challenge);
  const userId = new Uint8Array([1, 5, 3, 4]);
  const rpId = getValidRpId();

  const credential = await navigator.credentials.create({
    publicKey: {
      challenge: challengeBuffer,
      rp: {
        name: 'Issue-to-PR Platform',
        ...(rpId ? { id: rpId } : {}),
      },
      user: {
        id: userId,
        name: 'admin@issuetopr.local',
        displayName: 'Platform Admin',
      },
      pubKeyCredParams: [
        { alg: -7, type: 'public-key' },   // ES256
        { alg: -257, type: 'public-key' }, // RS256
      ],
      authenticatorSelection: {
        authenticatorAttachment: 'platform',
        userVerification: 'required',
        residentKey: 'discouraged',
        requireResidentKey: false,
      },
      timeout: 60000,
    },
  }) as PublicKeyCredential | null;

  if (!credential) {
    throw new Error('Biometric registration was cancelled.');
  }

  const credentialId = bufferToBase64Url(credential.rawId);
  setStoredBiometricCredentialId(credentialId);

  // Attempt backend registration if available
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const currentToken = getAuthToken();
    if (currentToken && !currentToken.startsWith('client_session_')) {
      headers['Authorization'] = `Bearer ${currentToken}`;
    }

    const regRes = await fetch(`${API_BASE}/auth/biometric/register`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        credential_id: credentialId,
        device_name: deviceName || (navigator.userAgent.includes('Mac') ? 'MacBook Touch ID' : 'Personal Device'),
        password: password || undefined,
      }),
    });

    if (regRes.ok) {
      const data = await regRes.json();
      if (data.token) {
        setAuthToken(data.token);
        return data.token;
      }
    }
  } catch {
    // Static hosting fallback
  }

  const clientToken = `client_session_${Date.now()}`;
  setAuthToken(clientToken);
  return clientToken;
}

export async function loginWithBiometrics(): Promise<string> {
  if (!navigator.credentials || !navigator.credentials.get) {
    throw new Error('Biometric authentication is not supported by your browser.');
  }

  const storedCredId = getStoredBiometricCredentialId();
  if (!storedCredId) {
    throw new Error('NO_DEVICE_CREDENTIAL');
  }

  const challenge = await fetchOrGenerateChallenge();
  const rpId = getValidRpId();

  // Explicitly specify transports: ['internal'] and userVerification: 'required'
  // to invoke the local device sensor (Touch ID / fingerprint) directly without passkey picker
  const assertion = await navigator.credentials.get({
    publicKey: {
      challenge: base64UrlToBuffer(challenge),
      ...(rpId ? { rpId } : {}),
      allowCredentials: [{
        id: base64UrlToBuffer(storedCredId),
        type: 'public-key',
        transports: ['internal'],
      }],
      userVerification: 'required',
      timeout: 60000,
    },
  }) as PublicKeyCredential | null;

  if (!assertion) {
    throw new Error('Biometric unlock was cancelled.');
  }

  const credentialId = bufferToBase64Url(assertion.rawId);

  // Attempt verification with backend if available
  try {
    const verifyRes = await fetch(`${API_BASE}/auth/biometric/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credential_id: credentialId,
        challenge,
      }),
    });

    if (verifyRes.ok) {
      const data = await verifyRes.json();
      setStoredBiometricCredentialId(credentialId);
      setAuthToken(data.token);
      return data.token;
    }
  } catch {
    // Static hosting fallback
  }

  // Device hardware platform authenticator verified successfully on this device
  setStoredBiometricCredentialId(credentialId);
  const clientToken = `client_session_${Date.now()}`;
  setAuthToken(clientToken);
  return clientToken;
}

export async function resetBiometrics(): Promise<void> {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    await fetch(`${API_BASE}/auth/biometric/reset`, {
      method: 'POST',
      headers,
    });
  } catch {
    // Static hosting fallback
  }
  clearStoredBiometricCredentialId();
}


async function authedFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init?.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    clearAuthToken();
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback();
    }
  }
  return res;
}


export async function fetchIssues(params: {
  page?: number;
  page_size?: number;
  query?: string;
  language?: string;
  repository?: string;
  difficulty?: string;
  license_status?: string;
  gsoc_only?: boolean;
  gsoc_org?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<{ items: Issue[]; total: number; page: number; total_pages: number; coverage_status: any }> {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page.toString());
  if (params.page_size) query.set('page_size', params.page_size.toString());
  if (params.query) query.set('query', params.query);
  if (params.language) query.set('language', params.language);
  if (params.repository) query.set('repository', params.repository);
  if (params.difficulty) query.set('difficulty', params.difficulty);
  if (params.license_status) query.set('license_status', params.license_status);
  if (params.gsoc_only !== undefined) query.set('gsoc_only', params.gsoc_only.toString());
  if (params.gsoc_org) query.set('gsoc_org', params.gsoc_org);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);

  const res = await authedFetch(`${API_BASE}/issues?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch issues: ${res.statusText}`);
  return res.json();
}

export async function fetchIssue(id: string): Promise<Issue> {
  const res = await authedFetch(`${API_BASE}/issues/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch issue: ${res.statusText}`);
  return res.json();
}

export async function importIssue(url: string): Promise<{
  issue: Issue;
  conditions_checked: any;
  meets_all_conditions: boolean;
}> {
  const res = await authedFetch(`${API_BASE}/issues/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to import issue: ${res.statusText}`);
  }
  return res.json();
}

export async function reconcileIssues(purge: boolean = false): Promise<{
  status: string;
  checked: number;
  reconciled_closed: number;
  purged: number;
  remaining_open: number;
}> {
  const query = new URLSearchParams();
  if (purge) query.set('purge', 'true');
  const res = await authedFetch(`${API_BASE}/issues/reconcile?${query.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Reconciliation failed: ${res.statusText}`);
  }
  return res.json();
}

export async function completeIssue(id: string): Promise<{
  status: string;
  message: string;
  issue_id: string;
  issue_number: number;
}> {
  const res = await authedFetch(`${API_BASE}/issues/${id}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to complete issue: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteIssue(id: string): Promise<{
  status: string;
  message: string;
  issue_id: string;
}> {
  const res = await authedFetch(`${API_BASE}/issues/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete issue: ${res.statusText}`);
  }
  return res.json();
}

export async function clearInboxIssues(): Promise<{
  status: string;
  message: string;
  deleted_count: number;
}> {
  const res = await authedFetch(`${API_BASE}/issues/clear-inbox`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to clear issues: ${res.statusText}`);
  }
  return res.json();
}


export async function triggerDiscoverySync(language?: string, forceRefresh: boolean = false, gsocOnly: boolean = false): Promise<any> {
  const res = await authedFetch(`${API_BASE}/discovery/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, force_refresh: forceRefresh, gsoc_only: gsocOnly }),
  });
  if (!res.ok) throw new Error(`Discovery sync failed: ${res.statusText}`);
  return res.json();
}

export async function fetchDiscoveryStatus(): Promise<DiscoveryStatus> {
  const res = await authedFetch(`${API_BASE}/discovery/status`);
  if (!res.ok) throw new Error(`Failed to fetch discovery status: ${res.statusText}`);
  return res.json();
}

export async function getCronStatus(): Promise<{
  enabled: boolean;
  interval_seconds: number;
  interval_hours: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string;
  last_issues_synced: number;
  last_issues_pruned: number;
}> {
  const res = await authedFetch(`${API_BASE}/discovery/cron-status`);
  if (!res.ok) throw new Error(`Failed to fetch cron status: ${res.statusText}`);
  return res.json();
}

export async function triggerCronRunNow(): Promise<{
  status: string;
  message: string;
  last_run_at: string;
  next_run_at: string;
  last_run_status: string;
  last_issues_synced: number;
  last_issues_pruned: number;
}> {
  const res = await authedFetch(`${API_BASE}/discovery/cron-run-now`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to trigger cron scan: ${res.statusText}`);
  }
  return res.json();
}

export async function selectIssue(issueId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ issue_id: issueId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to select issue: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchTasks(state?: string): Promise<Task[]> {
  const query = state ? `?state=${encodeURIComponent(state)}` : '';
  const res = await authedFetch(`${API_BASE}/tasks${query}`);
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.statusText}`);
  return res.json();
}

export async function fetchTask(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Failed to fetch task: ${res.statusText}`);
  return res.json();
}

export async function approveAssignment(taskId: string, approvedComment: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/assignment/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_comment: approvedComment }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to post assignment comment');
  }
  return res.json();
}

export async function autonomousApprove(
  taskId: string,
  payload?: { custom_comment?: string; auto_publish_pr?: boolean }
): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/autonomous-approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to execute autonomous approval');
  }
  return res.json();
}

export async function generateBriefing(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/briefing/generate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to generate issue briefing');
  }
  return res.json();
}

export async function recheckAssignment(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/assignment/recheck`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to recheck assignment: ${res.statusText}`);
  return res.json();
}

export async function prepareWorkspace(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/workspace/prepare`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to prepare workspace');
  }
  return res.json();
}

export async function openInAntigravity(taskId: string): Promise<{
  success: boolean;
  method: string;
  message: string;
  workspace_path?: string;
  fallback_prompt?: string;
}> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/antigravity/open`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to trigger desktop handoff: ${res.statusText}`);
  return res.json();
}

export async function markReadyForValidation(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/ready-for-validation`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to mark ready for validation: ${res.statusText}`);
  return res.json();
}

export async function runValidation(taskId: string, customTestCommand?: string): Promise<{
  task_id: string;
  workflow_state: string;
  passed: boolean;
  diff_security_passed: boolean;
  secrets_detected: string[];
  unrelated_files: string[];
  command_outputs: any[];
  message: string;
}> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/validation/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ custom_test_command: customTestCommand }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to run validation');
  }
  return res.json();
}

export async function overrideValidation(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/validation/override`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to override validation');
  }
  return res.json();
}

export async function publishPR(taskId: string, forceOverride: boolean = false): Promise<{
  task_id: string;
  workflow_state: string;
  pr_number?: number;
  pr_url?: string;
  success: boolean;
  message: string;
}> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force_override: forceOverride }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to publish pull request');
  }
  return res.json();
}

export async function cancelTask(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to cancel task: ${res.statusText}`);
  return res.json();
}

export async function syncPRStatus(taskId: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tasks/${taskId}/pr/sync`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to sync PR status');
  }
  return res.json();
}

export async function fetchSettings(): Promise<PlatformSettings> {
  const res = await authedFetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.statusText}`);
  return res.json();
}

export async function updateSettings(settings: Partial<PlatformSettings> & { github_token?: string }): Promise<PlatformSettings> {
  const res = await authedFetch(`${API_BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error(`Failed to update settings: ${res.statusText}`);
  return res.json();
}

export async function fetchAuditLogs(taskId?: string, action?: string): Promise<AuditLog[]> {
  const query = new URLSearchParams();
  if (taskId) query.set('task_id', taskId);
  if (action) query.set('action', action);
  const res = await authedFetch(`${API_BASE}/audit-logs?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch audit logs: ${res.statusText}`);
  return res.json();
}

export async function clearAuditLogs(): Promise<{ status: string; cleared: number }> {
  const res = await authedFetch(`${API_BASE}/audit-logs`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to clear audit logs: ${res.statusText}`);
  return res.json();
}

export async function deleteAuditLog(logId: string): Promise<{ status: string; deleted_id: string }> {
  const res = await authedFetch(`${API_BASE}/audit-logs/${logId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete notification: ${res.statusText}`);
  return res.json();
}


export async function trackItem(url: string): Promise<Task> {
  const res = await authedFetch(`${API_BASE}/tracker/track`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to track item.');
  }
  return res.json();
}

export async function syncAllTracker(): Promise<{ status: string; synced_prs: number; synced_issues: number; total_active: number }> {
  const res = await authedFetch(`${API_BASE}/tracker/sync-all`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to sync tracked items.');
  }
  return res.json();
}

export async function untrackItem(taskId: string): Promise<{ status: string; message: string }> {
  const res = await authedFetch(`${API_BASE}/tracker/${taskId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to untrack item.');
  }
  return res.json();
}

export async function fetchTrackerStats(): Promise<{
  total_tracked: number;
  prs_open: number;
  prs_merged: number;
  prs_changes_requested: number;
  issues_tracked: number;
}> {
  const res = await authedFetch(`${API_BASE}/tracker/stats`);
  if (!res.ok) throw new Error('Failed to fetch tracker stats.');
  return res.json();
}

export async function removeAllTracked(scope: 'all' | 'merged' | 'issues' | 'prs' = 'all'): Promise<{ status: string; removed: number; scope: string }> {
  const res = await authedFetch(`${API_BASE}/tracker/all?scope=${scope}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to remove tracked items.');
  }
  return res.json();
}

export async function importAuthorPRs(username?: string): Promise<{
  status: string;
  username: string;
  found_on_github: number;
  imported: number;
}> {
  const query = username ? `?username=${encodeURIComponent(username)}` : '';
  const res = await authedFetch(`${API_BASE}/tracker/import-author${query}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to import author pull requests.');
  }
  return res.json();
}



