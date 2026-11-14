/** Formatting helpers for the NGSH console. */

import { now as clockNow } from './clock';

const ISO_FORMAT = new Intl.DateTimeFormat('en-CA', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/** `2026-11-14 18:42:00Z` — dense, sortable, unambiguous. */
export function formatTimestamp(iso: string | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts = ISO_FORMAT.formatToParts(date);
  const get = (type: string): string => parts.find((part) => part.type === type)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}Z`;
}

/** `2026-11-14` — date only. */
export function formatDate(iso: string | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return iso.slice(0, 10);
}

/** `4m 12s ago` — relative to the active reference clock. */
export function formatRelative(iso: string | undefined, now: number = clockNow()): string {
  if (!iso) return '—';
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return '—';
  const deltaSeconds = Math.round((now - time) / 1000);
  const future = deltaSeconds < 0;
  const seconds = Math.abs(deltaSeconds);

  let text: string;
  if (seconds < 60) text = `${seconds}s`;
  else if (seconds < 3600) text = `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  else if (seconds < 86_400) text = `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  else text = `${Math.floor(seconds / 86_400)}d ${Math.floor((seconds % 86_400) / 3600)}h`;

  return future ? `in ${text}` : `${text} ago`;
}

/** Thousands-separated integer. */
export function formatCount(value: number): string {
  return value.toLocaleString('en-US');
}

/** Compact byte size: `482 MB`. */
export function formatBytes(bytes: number | undefined): string {
  if (bytes === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = value >= 100 || unit === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unit]}`;
}
