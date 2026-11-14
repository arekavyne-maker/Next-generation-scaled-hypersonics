/**
 * Reference clock for relative timestamps.
 *
 * The mock dataset is anchored to a fixed epoch so that every run produces
 * identical data (including the audit ledger hashes). When the console is
 * serving mock data, relative times are measured against that epoch instead
 * of the wall clock, so "28m ago" means 28 minutes before the newest event in
 * the dataset — not 28 minutes before the operator's laptop clock.
 */

type ClockSource = () => number;

let source: ClockSource = () => Date.now();

export function setClockSource(next: ClockSource): void {
  source = next;
}

export function now(): number {
  return source();
}
