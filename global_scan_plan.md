## Plan: Global Scan Tray Drill-In

Make Global Scan backend-driven end to end: first fix active-module resolution so the API returns the real current pick table for a scanned tray, then extend the frontend handoff so the destination page can find the correct row, auto-click its existing view icon, and focus the scanned tray inside that modal. This keeps the backend as SSOT for module ownership and uses existing per-module view-icon flows instead of inventing a second tray-details path.

**Steps**
1. Confirm and normalize active-tray ownership rules in the global scan backend in `a:\Workspace\Watchcase\TTT-Jan2026\adminportal\global_scan.py`. Tighten each module query to match what that module considers active in its pick table, especially Jig Unloading and Nickel Audit where the current search is too broad. Reuse `delink_tray=False` and `rejected_tray=False` where those fields exist, and define an explicit fallback policy for models that do not yet track both flags.
2. Refactor the backend response contract in `a:\Workspace\Watchcase\TTT-Jan2026\adminportal\global_scan.py` so it returns both row-target and tray-target context. Response should distinguish `highlight_key` for row location from `tray_id` for tray focus, and include enough context for destination pages to open the existing view icon without frontend guesswork.
3. Decide and implement one consistent row-target strategy across pick tables. Recommended approach: backend returns the owning `lot_id` and, when applicable, `batch_id`; frontend uses those identifiers first, not the scanned tray id, to locate the row. Keep scanned `tray_id` separate for tray-level focus after the modal opens. This step depends on 1 and 2.
4. Update the Global Scan navigation script in `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\base.html` so it stores a structured handoff payload in `sessionStorage` and redirects with a row-level `highlight` value based on backend ownership, not the raw scanned tray id. Also update the page-hunt logic to prefer `batch_id`, `lot_id`, and existing row data attributes before falling back to plain cell text. This step depends on 2.
5. Extend the destination-page post-navigation flow in `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\base.html` to auto-open the row’s existing view icon after the row is found. Add a generic hook that looks for the row-local view trigger already used by each pick table rather than creating a new tray-details API. This step depends on 4.
6. Add a small reusable destination-page contract for modal focusing. Recommended approach: after auto-clicking the existing view icon, dispatch a custom event or set a `sessionStorage` key carrying the scanned `tray_id`; module-specific modal JS reads that key once the modal DOM is ready and highlights or scrolls to the matching tray entry. This keeps the global scan script generic while allowing each module’s current modal markup to stay mostly unchanged. This step can begin after 4 and 5.
7. Implement the first module slice in Input Screening as the reference path because its pick table already exposes clear `data-stock-lot-id`, `data-batch-id`, and `.tray-scan-btn-DayPlanning-view` attributes in the template. Wire the modal focus logic in `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Input_Screening\IS_PickTable.html` and/or `a:\Workspace\Watchcase\TTT-Jan2026\static\js\inputscreening_picktable.js`. Validate this end to end before widening scope. This step depends on 5 and 6.
8. Roll the same row-open and tray-focus contract through the remaining active pick tables in workflow order: Brass QC, Brass Audit, IQF, Nickel Inspection, Nickel Audit, Spider Spindle, Jig Unloading, Jig Loading. Reuse the same data-attribute convention where available and only add minimal template hooks where missing. This step depends on 7 and can be parallelized by module once the reference pattern is stable.
9. Add targeted logging in `a:\Workspace\Watchcase\TTT-Jan2026\adminportal\global_scan.py` and minimal frontend debug guards in `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\base.html` so failures can be diagnosed by stage: search, redirect, row-find, view-open, tray-focus. Remove noisy console output that is no longer needed after verification.

10. Implement keyboard shortcut row navigation and focus behavior. When any keyboard shortcut (A/R/V/D/J/S/Q/I/U/T/C/O) is pressed:
    - Focus the next available row and highlight it (yellow background or border)
    - Allow ↑↓ arrow keys to navigate between rows while row is focused
    - Hitting Enter executes the shortcut action on the highlighted row
    - Only one row can be highlighted at a time; keyboard focus moves between rows, not entire page

11. Implement Draft Lot direct child screen behavior. When a lot has `brass_draft=True` (or equivalent draft flag per module):
    - If user scans a valid tray_id belonging to that drafted lot
    - Open the child screen/modal directly (e.g., reject modal for Brass QC) without pagination lookup
    - Bypass row selection — go directly to the action interface
    - Preserve draft data from backend so user can resume work

12. Implement Active Row Highlight with Tray Scan integration. When a tray_id is scanned and exists in the current pick table with accept/reject buttons enabled:
    - Automatically highlight the owning row (yellow or high-contrast background)
    - Move the highlighted row to the top of the visible table (via DOM reorder or scroll)
    - Display the row's current state (qty, status, tray count)
    - Enable action buttons (Accept, Reject, View Details) for immediate use

13. Implement Active Row Exclusivity and Lifecycle Management:
    - **At any moment**, only ONE row can be highlighted and in active access state
    - When a child screen is open (modal), the parent row remains highlighted
    - **Closing the child screen** clears the highlight and resets the row to normal state
    - **Scanning a new valid tray_id while a row is already active:**
        - Clear the current row's highlight and any open child screen
        - Move focus to the newly scanned tray's row
        - Highlight the new row and move it to the top
        - Ready for new action without state collision
    - **Escape key** closes any open child screen and clears highlight on parent row

14. Implement Highlight State Persistence in sessionStorage:
    - Store `sessionStorage.activeRowKey = { lot_id, batch_id, tray_id, module }`
    - Store `sessionStorage.highlightedRow = true/false`
    - When user navigates away and returns, reapply highlight to the same row if it still exists
    - If the lot no longer exists (completed/removed), clear the stored state and reset view

**Keyboard Shortcut Reference (Updated with Row Focus Behavior)**

| Key | Action | Row Behavior |
|-----|--------|--------------|
| **F2** | Scan Tray (Global) | Redirects to owning module, highlights row with scanned tray |
| **A** | Accept Row | Focus row with yellow highlight; Enter to execute accept |
| **R** | Reject Row | Focus row with yellow highlight; Enter to open reject modal |
| **V** | View Details | Focus row with yellow highlight; Enter to open view modal |
| **D** | Delete/Draft | Focus row with yellow highlight; Enter to execute delete or open draft |
| **↑ ↓** | Navigate Rows | While row is highlighted, move selection up/down between rows |
| **← →** | Scroll Table | Horizontal table scroll (unchanged) |
| **1–9** | Jump Page | Navigate to page N; clears current row highlight |
| **J** | Add Jig | Focus row with yellow highlight; Enter to open Add Jig modal |
| **Q** | Audit (IQF) | Focus row with yellow highlight; Enter to open IQF Audit child screen |
| **I** | Inspection (IP) | Focus row with yellow highlight; Enter to open IP Inspection child screen |
| **U** | Jig Unload | Focus row with yellow highlight; Enter to open Unload child screen |
| **T** | Tray Scan (DP) | Focus row with yellow highlight; Enter to open Day Planning Tray Scan modal |
| **C** | Clear (Jig) | Focus row with yellow highlight; Enter to clear all scanned trays |
| **O** | Redo (Jig) | Focus row with yellow highlight; Enter to clear and restart |
| **S** | Spider Spindle | Focus row with yellow highlight; Enter to open Spider Spindle module |
| **⏎ (Enter)** | Execute | Execute the focused shortcut action on the highlighted row |
| **Esc** | Close | Close any open child screen; clear row highlight |

**Relevant files**
- `a:\Workspace\Watchcase\TTT-Jan2026\adminportal\global_scan.py` — core module-order search, active-tray filters, API response contract, structured logging.
- `a:\Workspace\Watchcase\TTT-Jan2026\adminportal\urls.py` — route is already present; verify no contract changes require URL changes.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\base.html` — F2 scan request, redirect logic, row hunt logic, post-navigation auto-open orchestration.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Input_Screening\IS_PickTable.html` — reference implementation for row-local view icon and modal trigger attributes.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\js\inputscreening_picktable.js` — reference implementation for opening tray modal and adding scanned-tray focus inside the modal.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Brass_Qc\Brass_PickTable.html` — likely needs the same row-local trigger and tray-focus hook.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\BrassAudit\BrassAudit_PickTable.html` — likely needs the same row-local trigger and tray-focus hook.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\IQF\Iqf_PickTable.html` — likely needs the same row-local trigger and tray-focus hook.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Nickel_Inspection\Nickel_PickTable.html` — confirm view-icon markup and modal trigger contract.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Nickel_Audit\NickelAudit_PickTable.html` — confirm view-icon markup and modal trigger contract.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\SpiderSpindle_Z1\ss_z1_pick_table.html` — confirm whether current pick table has a reusable row-level drill-in path or needs a minimal hook.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\SpiderSpindle_Z2\ss_z2_pick_table.html` — same as Z1.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\Jig_Unloading\Jig_Unloading_Main.html` — confirm row-local view button and modal wiring.
- `a:\Workspace\Watchcase\TTT-Jan2026\static\templates\JigLoading\Jig_Picktable.html` — confirm row-local view button and modal wiring.

**Verification**
1. Backend verification: run a narrow Django check and then exercise `POST /adminportal/global_tray_search/` for known trays that currently misroute, including one tray per early-stage and late-stage module, confirming the returned module matches the live pick table.
2. UI verification for the reference module: from any page, press F2, scan a tray known to exist in Input Screening, and confirm the app redirects to the Input Screening pick table, highlights the correct row, auto-opens the view icon, and visibly focuses the scanned tray inside the modal.
3. Regression verification: repeat the same flow for at least one tray in Brass QC, Brass Audit, IQF, and Jig Loading to confirm the shared handoff contract works across templates.
4. Negative verification: scan a non-existent tray and confirm the flow stops at a clear not-found message without redirecting or leaving stale session state.
5. State-filter verification: create or identify a delinked or rejected tray and confirm Global Scan does not falsely route to a stale earlier module.
6. Keyboard shortcut row navigation verification:
   - Open a pick table (e.g., Brass QC)
   - Press 'A' (Accept) — verify a row is highlighted with yellow background
   - Press ↑/↓ — verify selection moves up/down between rows
   - Press Enter — verify Accept action is triggered on the highlighted row
   - Press Esc — verify highlight is cleared
7. Draft lot direct child screen verification:
   - Create a drafted lot in Brass QC (set `brass_draft=True`)
   - Press F2 and scan a tray belonging to that drafted lot
   - Confirm the Brass QC page opens AND the reject/action modal opens directly (not pick table)
   - Verify draft data is pre-populated in the modal
8. Active row highlight and tray scan verification:
   - Open Brass QC pick table
   - Press F2 and scan a valid tray_id
   - Confirm the row containing that tray_id is highlighted and moved to the top
   - Verify Accept/Reject buttons are enabled and ready
   - Open the row's modal (press V)
   - Confirm parent row remains highlighted while modal is open
   - Close modal (Esc)
   - Confirm row highlight persists
9. Active row exclusivity verification:
   - Highlight a row in Brass QC (press A)
   - While that row is highlighted, press F2 and scan a DIFFERENT tray_id
   - Confirm the first row's highlight is cleared
   - Confirm the second tray's row is now highlighted and moved to the top
   - Close the application and reopen the page
   - Confirm the same row is still highlighted (sessionStorage persistence)
10. Edge case verification:
    - Scan a tray_id, highlight its row, then delete that lot from the database (simulate external removal)
    - Reopen the page or navigate away and back
    - Confirm the highlight is cleared and a "Not Found" message is shown instead of a stale highlight

**Decisions**
- Included scope: active pick tables only, in workflow order, with row highlight plus automatic view-icon open and scanned-tray focus inside the opened modal.
- Excluded scope: accept, reject, completed, and recovery tables unless the user later asks for those surfaces to participate in Global Scan.
- Recommended backend contract: separate ownership identifiers for row targeting from the scanned tray identifier used for modal focus.
- Recommended rollout strategy: implement and validate Input Screening first as the reference slice, then expand module by module.
- **Keyboard shortcut row navigation:** All shortcuts (A/R/V/D/J/Q/I/U/T/C/O) focus the next available row and highlight it (yellow background). User navigates rows with ↑/↓ and executes the action with Enter. Only one row highlighted at a time.
- **Draft lot behavior:** If a lot has `draft_*=True` flag and a tray_id from that lot is scanned, bypass the pick table and open the child screen directly with draft data pre-populated.
- **Active row highlight:** When a tray_id is scanned and found, its row is highlighted and moved to top of table. Only one row active at a time; scanning a new tray clears the previous highlight.
- **sessionStorage state tracking:** Store active row context (`lot_id`, `batch_id`, `tray_id`, `module`) so that page refresh or back/forward navigation restores the highlight if the row still exists.

**Further Considerations**
1. Spider Spindle appears to lack the same state fields as other modules. If its tray model cannot distinguish active from historical rows, either add minimal state tracking there or explicitly document a temporary degraded match rule before enabling it in strict order.
2. If some modules do not expose a reusable row-local view trigger, add a thin data-attribute hook in the template rather than creating another tray-detail API. That keeps the existing module modal as the single detail surface.
3. If multiple rows can legitimately share a lot identifier on a page, prefer `batch_id` as the first match key and only fall back to `lot_id` when batch is absent.
4. **Keyboard shortcut timing:** Ensure keyboard event listeners are attached AFTER the DOM is fully loaded (e.g., in DOMContentLoaded) so that shortcut handlers don't fire before the table rows are ready.
5. **Row highlight CSS:** Use a consistent, high-contrast background color (e.g., `#fff5bd` yellow with `z-index: 50`) across all modules so the highlighted row is always visible even in sticky columns.
6. **Draft modal transition:** When opening a child screen from a draft lot, preserve the `sessionStorage` highlight state so that closing the modal restores the highlighted row without flickering or losing context.
7. **Pagination edge case:** If a highlighted row exists on page 3 and user navigates to page 1, clear the highlight (since the row is no longer visible) and reset sessionStorage. When user returns to page 3, reapply the highlight if the row still exists.
8. **Concurrent access:** If multiple users have the same lot_id in sessionStorage on different sessions, ensure that one session's highlight does not interfere with another. sessionStorage is per-session, so this is naturally isolated, but verify in testing.