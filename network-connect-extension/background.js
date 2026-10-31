// DealerOS Network Connect -- minimal Manifest V3 service worker.
//
// This extension does all of its real work inside popup.js when the user
// opens the popup (signup, connector selection, KPI submission, benchmark
// retrieval) -- there is no background polling, no alarms, and nothing
// running while the popup is closed. This file exists only because
// manifest.json's `background.service_worker` key requires a real file to
// point at; it's intentionally a no-op today.
//
// A future slice could add a periodic reminder (e.g. chrome.alarms) to
// nudge the user to submit their monthly KPI snapshot -- not built here
// since it wasn't part of what this pass verified end to end, and a
// fabricated "your data is stale" nag with no real submission-history
// check behind it would be worse than no reminder at all.

chrome.runtime.onInstalled.addListener(() => {
  // No first-run action needed -- popup.js's own init() handles the
  // signup-vs-signed-in branch every time the popup opens.
});
