// Centralized 2-Hour Autonomous Online Scanner Internal Engine
// Calculates deterministic 2-hour cycles aligned with universal epoch intervals

export const TWO_HOURS_SEC = 7200;
export const TWO_HOURS_MS = TWO_HOURS_SEC * 1000;

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
    digital: `${pad(h)}:${pad(m)}:${pad(s)}`,
    human: `${h}h ${pad(m)}m ${pad(s)}s`
  };
}

export interface InternalCronSchedule {
  last_run_at: string;
  next_run_at: string;
  countdown_sec: number;
  formatted: FormattedCountdown;
}

/**
 * Returns the website's deterministic internal 2-hour schedule.
 * Independent of when any user logs in, visits the site, leaves, or reloads.
 */
export function getWebsiteInternalSchedule(): InternalCronSchedule {
  const now = Date.now();
  // Epoch-aligned 2-hour window
  const cycleStartMs = Math.floor(now / TWO_HOURS_MS) * TWO_HOURS_MS;
  const cycleEndMs = cycleStartMs + TWO_HOURS_MS;
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

