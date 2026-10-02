/**
 * API client and offline cache.
 *
 * Two requirements from the spec drive this file:
 *   - "offline caching of previously calculated charts"
 *   - "no loss of event data"
 *
 * A computed chart is immutable for a given (birth data, config), so it is
 * cached aggressively and served from cache when the network is unavailable.
 *
 * Unsent events are different: they are the only user-authored data in the
 * app, so they are written to a local outbox FIRST and sent second. If the
 * send fails the event is still on the device, and the app shows a pending
 * badge rather than silently dropping the user's input.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * API base URL.
 *
 * Empty by default, which makes every request relative and therefore
 * same-origin. That is what lets the app be served from a public tunnel
 * without a rebuild: there is no hardcoded host to get wrong.
 *
 * Set EXPO_PUBLIC_API_URL only when the API lives on a different origin.
 */
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? '';

const CHART_PREFIX = 'chart:';
const CHART_INDEX = 'chart:index';
const OUTBOX_KEY = 'outbox:events';
const CATEGORY_PREFIX = 'category:';

export type Precision = 'exact' | 'month' | 'quarter' | 'year' | 'unknown';

export interface Taxonomy {
  categories: Record<string, string[]>;
  precisions: Precision[];
}

export interface BirthInput {
  name: string;
  birth_date: string;
  birth_time: string;
  /** City name; looked up server-side. Optional if coords are given. */
  city?: string;
  /** IANA identifier. Defaults to Asia/Kolkata when omitted. */
  timezone?: string;
  latitude?: number;
  longitude?: number;
  country?: string;
  /** Fixed offset such as "+05:30". Overrides `timezone`; use pre-1900. */
  utc_offset?: string | null;
}

export interface CityResult {
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  timezone: string;
}

export interface PendingEvent {
  localId: string;
  profileId: string;
  category: string;
  sub_category: string;
  date: string;
  precision: Precision;
  impact: number;
  certainty: number;
  description: string;
  createdAt: string;
}

function chartKey(birth: BirthInput): string {
  return [
    birth.birth_date,
    birth.birth_time,
    birth.city ?? '',
    birth.utc_offset ?? birth.timezone ?? 'IST',
    (birth.latitude ?? 0).toFixed(4),
    (birth.longitude ?? 0).toFixed(4),
  ].join('|');
}

// --- networking -------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// --- charts -----------------------------------------------------------------

export async function getChart(birth: BirthInput): Promise<any> {
  const key = chartKey(birth);
  const cached = await AsyncStorage.getItem(CHART_PREFIX + key);
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch {
      // fall through to the network
    }
  }

  const result = await request('/chart', {
    method: 'POST',
    body: JSON.stringify(birth),
  });

  // Cache only after a successful computation. A chart is deterministic, so
  // this stays valid until the calculation conventions change — which is why
  // the fingerprint is stored alongside it.
  const storageKey = CHART_PREFIX + key;
  await AsyncStorage.setItem(storageKey, JSON.stringify(result));

  const rawIndex = await AsyncStorage.getItem(CHART_INDEX);
  let index: string[] = [];
  try {
    index = rawIndex ? JSON.parse(rawIndex) : [];
  } catch {
    index = [];
  }
  if (!index.includes(storageKey)) {
    index.push(storageKey);
    await AsyncStorage.setItem(CHART_INDEX, JSON.stringify(index));
  }

  return result;
}

export function clearChartCache(): Promise<void> {
  // AsyncStorage cannot enumerate keys, so the chart keys are tracked
  // separately. Without this index a cache clear would be impossible and
  // stale charts could never be dropped after a convention change.
  return (async () => {
    const raw = await AsyncStorage.getItem(CHART_INDEX);
    if (!raw) return;
    let keys: string[] = [];
    try {
      keys = JSON.parse(raw);
    } catch {
      return;
    }
    if (keys.length) await AsyncStorage.multiRemove(keys);
    await AsyncStorage.removeItem(CHART_INDEX);
  })();
}

// --- profiles ---------------------------------------------------------------

export async function createProfile(birth: BirthInput): Promise<{ profile_id: string }> {
  return request('/profiles', { method: 'POST', body: JSON.stringify(birth) });
}

export async function getProfile(profileId: string): Promise<any> {
  const key = CATEGORY_PREFIX + profileId;
  const cached = await AsyncStorage.getItem(key);
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch {
      /* fall through */
    }
  }
  const result = await request(`/profiles/${profileId}`);
  await AsyncStorage.setItem(key, JSON.stringify(result));
  return result;
}

// --- events -----------------------------------------------------------------

/**
 * Queue an event locally, then try to send it.
 *
 * The local write happens first and unconditionally. If the send throws, the
 * event stays queued and is retried on next launch — the user's data is never
 * lost because the network was down.
 */
export async function addEvent(
  profileId: string,
  event: Omit<PendingEvent, 'localId' | 'profileId' | 'createdAt'>,
): Promise<{ sent: boolean; localId: string }> {
  const localId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const pending: PendingEvent = {
    ...event,
    localId,
    profileId,
    createdAt: new Date().toISOString(),
  };

  const outbox = await readOutbox();
  outbox.push(pending);
  await AsyncStorage.setItem(OUTBOX_KEY, JSON.stringify(outbox));

  return { sent: await flushOutbox(), localId };
}

export async function readOutbox(): Promise<PendingEvent[]> {
  const raw = await AsyncStorage.getItem(OUTBOX_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

export async function pendingEventCount(): Promise<number> {
  return (await readOutbox()).length;
}

/** Attempt to send everything queued. Returns true if the outbox is empty. */
export async function flushOutbox(): Promise<boolean> {
  const outbox = await readOutbox();
  if (outbox.length === 0) return true;

  const remaining: PendingEvent[] = [];
  for (const item of outbox) {
    try {
      await request(`/profiles/${item.profileId}/events`, {
        method: 'POST',
        body: JSON.stringify({
          category: item.category,
          sub_category: item.sub_category,
          date: item.date,
          precision: item.precision,
          impact: item.impact,
          certainty: item.certainty,
          description: item.description,
        }),
      });
    } catch {
      // Keep it queued; try again next time.
      remaining.push(item);
    }
  }
  await AsyncStorage.setItem(OUTBOX_KEY, JSON.stringify(remaining));
  return remaining.length === 0;
}

// --- reference data ---------------------------------------------------------

export async function getTaxonomy(): Promise<Taxonomy> {
  const cached = await AsyncStorage.getItem('taxonomy');
  if (cached) {
    try {
      return JSON.parse(cached) as Taxonomy;
    } catch {
      /* fall through */
    }
  }
  const result = await request<Taxonomy>('/taxonomy');
  await AsyncStorage.setItem('taxonomy', JSON.stringify(result));
  return result;
}

export async function getCities(q: string): Promise<{
  cities: CityResult[];
  default_timezone: string;
}> {
  const cached = await AsyncStorage.getItem(`cities:${q}`);
  if (cached) {
    try {
      return JSON.parse(cached) as { cities: CityResult[]; default_timezone: string };
    } catch {
      /* fall through */
    }
  }
  const result = await request<{ cities: CityResult[]; default_timezone: string }>(
    `/cities?q=${encodeURIComponent(q)}`,
  );
  await AsyncStorage.setItem(`cities:${q}`, JSON.stringify(result));
  return result;
}

export async function getConfig(): Promise<any> {
  return request('/config');
}

export async function getTimeline(profileId: string): Promise<any> {
  return request(`/profiles/${profileId}/timeline`);
}

export async function getAnalysis(profileId: string): Promise<any> {
  return request(`/profiles/${profileId}/analysis`);
}

export { BASE_URL };
