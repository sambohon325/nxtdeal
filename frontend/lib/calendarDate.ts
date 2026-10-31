/** Calendar dates have no timezone; timestamps continue to use the viewer's timezone. */
export function formatCalendarDate(value: string, locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString(locales, /^\d{4}-\d{2}-\d{2}$/.test(value) ? {...options, timeZone: "UTC"} : options);
}
