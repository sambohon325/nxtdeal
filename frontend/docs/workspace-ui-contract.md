# NXTDeal workspace interaction contract

The application follows one progression: department overview → work list → record → action → return to work.

## Shared structure

Today is the visual reference. Import WorkButton, WorkInput, WorkSelect and WorkTextarea from WorkspaceUi for action controls. Keep their native handlers, labels, validation and submission semantics. Shared measurements are 44px control height, 14px body/action text, 13px field/table labels, 18px section headings, 28px page/record titles, 16px spacing and 20px panel padding. Use primary for the main action, secondary for ordinary actions and danger for destructive actions. Selected views use aria-pressed/aria-current, not a different department palette.

Use WorkStat for compact list snapshots and OverviewMetrics for department snapshots. Use OverviewActions for department shortcuts. Local styles may control layout but must not override shared controls with important declarations or tiny font sizes. Customer-facing previews keep their own design; the surrounding editor controls follow the workspace contract.

Use WorkOverlay for a form that must remain modal. It mounts at the theme root so a glass panel cannot clip a fixed-position dialog. Prefer an inline record for sustained work, with a clear return action and existing unsaved-change protection. Do not reset an originating list's filters when returning from its record.

Use DepartmentOverview for the page header, snapshot measures and quick actions. A page has one primary heading, a short explanation of its purpose, and a clear next action. Keep statuses, evidence and simulated-data notices accurate. Do not manufacture metrics to fill a card.

Department groups expand inside WorkspaceNavigation in the existing left rail. Secondary destinations stay in that rail. Use inline record editors, preserve draft protection, and provide a return to the originating work. Specialized calendars, pipelines, comparison charts and editors may retain layouts needed for their job, while inheriting the same typography, surfaces, controls and focus behavior.

## Collections

Use CollectionPagination for server-paged or explicitly filtered lists. Its page index is zero-based, default size is 25, and adjustable client collections offer 10, 25 and 50. Show the visible range, total, page count, and First/Previous/Next/Last controls. Reset paging when a filter or size changes. Clamp after records disappear. Disable controls while relevant edits or saves are pending.

Use RecordTable for complete in-memory row sets. Keep real table headers and row controls. It preserves grouped/rowspan tables instead of splitting groups. Set paginate=false when a server or parent already controls paging, to avoid two independent pagers. Never put RecordCollection inside tbody.

Use RecordCollection for complete card lists and histories; use list=true inside ul/ol. Give filtered collections a key based on their filter so a new search starts at the beginning. Disable paging when a child edit must be finished first.

Loaded counts describe only the records supplied by the API. They are not asserted to be whole-database totals. Server pagination must use the server total and page size. An intentional overview preview must identify its limited scope and link to the complete work list. Never render a capped list with an inert “more” label.

## Verification

Run the shared collection tests and the affected workflow tests. Check light and dark modes, the persistent sidebar, horizontal overflow on wide tables, empty/error states, and record return. Review forms using synthetic records. Navigation audits confirm that destinations render; they do not establish that every business mutation or external provider integration succeeded.

This contract applies to application workspaces. Customer-facing website/email previews, print/export layouts, and the separate app suite retain their own presentation requirements.
