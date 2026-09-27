export function pressureDelta(event) {
  return event.kind === 'reading' && event.previousPressure != null
    ? Number((event.pressure - event.previousPressure).toFixed(1)) : null;
}
export function status(pressure) {
  if (pressure == null) return 'unknown';
  return pressure < 50 ? 'critical' : pressure < 100 ? 'warning' : 'healthy';
}
export function estimateLitres(drop, capacity = 10000, ratedPressure = 200) {
  return Math.round(drop * capacity / ratedPressure);
}
export function validateEntry(entry, current) {
  if (!['left', 'right'].includes(entry.side)) throw new Error('Choose a valid cylinder.');
  if (!['initial', 'reading', 'replacement'].includes(entry.kind)) throw new Error('Choose a valid activity.');
  if (!Number.isFinite(entry.pressure) || entry.pressure < 0 || entry.pressure > 400) throw new Error('Enter a pressure between 0 and 400 bar.');
  if (entry.kind === 'initial' && current) throw new Error('This cylinder is already set up. Refresh and try again.');
  if (entry.kind !== 'initial' && !current) throw new Error('Set up the cylinder first.');
  if (entry.kind === 'reading' && entry.pressure > current.pressure) throw new Error('Pressure has increased. Use Replace cylinder for a new cylinder.');

}
export function createEvent(entry, current, now = new Date().toISOString()) {
  validateEntry(entry, current);
  const rating = entry.kind === 'reading' ? current : entry;
  return {...entry, id: crypto.randomUUID(), at: now, previousPressure: current?.pressure ?? null,
    used: entry.kind === 'reading' ? estimateLitres(current.pressure-entry.pressure, 10000, 200) : null,
    capacity: 10000, ratedPressure: 200, serial: rating.serial || '',
    installedAt: entry.kind === 'reading' ? current.installedAt : now,
    startingPressure: entry.kind === 'reading' ? current.startingPressure : entry.pressure};
}
export function textExport(events) {
  return ['O2 CYLINDER TRACKER — COMPLETE HISTORY', `Exported: ${new Date().toISOString()}`, 'Times below are UTC (ISO 8601). Litres are estimated from pressure drop × capacity / rated pressure.', '',
    ...events.map(e => [
      `${e.at} | ${e.side.toUpperCase()} CYLINDER | ${e.kind.toUpperCase()}`,
      `Pressure: ${e.previousPressure ?? '—'} → ${e.pressure} bar | Delta: ${pressureDelta(e) == null ? 'N/A (baseline / replacement)' : pressureDelta(e) + ' bar'} | Gas used: ${e.used == null ? 'N/A (baseline / replacement)' : e.used + ' L'}`,
      `Cylinder ID: ${e.serial || 'Not recorded'} | Rated: ${e.capacity} L at ${e.ratedPressure} bar | Starting pressure: ${e.startingPressure} bar`,
      `Installed: ${e.installedAt} | Recorded by: ${e.operator || 'Not recorded'}`, `Notes: ${e.notes || '—'}`, ''
    ].join('\n'))].join('\n');
}
