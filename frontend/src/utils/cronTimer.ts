// Centralized 24/7 Autonomous Online Scanner Internal Engine
// Calculates deterministic continuous scanning cycles aligned with universal epoch intervals

export const SCAN_INTERVAL_SEC = 300; // 5-minute continuous 24/7 autonomous scanning loop
export const SCAN_INTERVAL_MS = SCAN_INTERVAL_SEC * 1000;
export const TWO_HOURS_SEC = SCAN_INTERVAL_SEC;
export const TWO_HOURS_MS = SCAN_INTERVAL_MS;

export const MANUAL_LAST_CRON_KEY = 'issuetopr_manual_last_cron_run_at';

export interface FormattedCountdown {
  h: string;
  m: string;
  s: string;
  digital: string;
  human: string;
}

export function formatCountdownSec(totalSec: number): FormattedCountdown {
  const clamped = Math.max(0, Math.floor(totalSec));
  const h = Math.floor(clamped / 3600);
  const m = Math.floor((clamped % 3600) / 60);
  const s = clamped % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');

  return {
    h: pad(h),
    m: pad(m),
    s: pad(s),
    digital: h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`,
    human: h > 0 ? `${h}h ${pad(m)}m ${pad(s)}s` : `${pad(m)}m ${pad(s)}s`
  };
}

export interface InternalCronSchedule {
  last_run_at: string;
  next_run_at: string;
  countdown_sec: number;
  formatted: FormattedCountdown;
}

/**
 * Returns the website's deterministic internal 24/7 continuous schedule.
 * Independent of when any user logs in, visits the site, leaves, or reloads.
 */
export function getWebsiteInternalSchedule(): InternalCronSchedule {
  const now = Date.now();
  // Epoch-aligned continuous window
  const cycleStartMs = Math.floor(now / SCAN_INTERVAL_MS) * SCAN_INTERVAL_MS;
  const cycleEndMs = cycleStartMs + SCAN_INTERVAL_MS;
  const countdownSec = Math.max(0, Math.floor((cycleEndMs - now) / 1000));

  let lastRunIso = new Date(cycleStartMs).toISOString();

  // If a manual scan was triggered more recently than cycleStart, display that
  try {
    const manualLast = localStorage.getItem(MANUAL_LAST_CRON_KEY);
    if (manualLast) {
      const manualMs = new Date(manualLast).getTime();
      if (!isNaN(manualMs) && manualMs > cycleStartMs && manualMs <= now) {
        lastRunIso = new Date(manualMs).toISOString();
      }
    }
  } catch {
    // Ignore localStorage access issues
  }

  const nextRunIso = new Date(cycleEndMs).toISOString();

  return {
    last_run_at: lastRunIso,
    next_run_at: nextRunIso,
    countdown_sec: countdownSec,
    formatted: formatCountdownSec(countdownSec)
  };
}

/**
 * Records an immediate manual scan execution while keeping the website's internal schedule aligned.
 */
export function recordManualCronScan(): InternalCronSchedule {
  const now = Date.now();
  const nowIso = new Date(now).toISOString();
  try {
    localStorage.setItem(MANUAL_LAST_CRON_KEY, nowIso);
  } catch {
    // Ignore localStorage errors
  }
  return getWebsiteInternalSchedule();
}

