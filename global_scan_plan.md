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

**Decisions**
- Included scope: active pick tables only, in workflow order, with row highlight plus automatic view-icon open and scanned-tray focus inside the opened modal.
- Excluded scope: accept, reject, completed, and recovery tables unless the user later asks for those surfaces to participate in Global Scan.
- Recommended backend contract: separate ownership identifiers for row targeting from the scanned tray identifier used for modal focus.
- Recommended rollout strategy: implement and validate Input Screening first as the reference slice, then expand module by module.

**Further Considerations**
1. Spider Spindle appears to lack the same state fields as other modules. If its tray model cannot distinguish active from historical rows, either add minimal state tracking there or explicitly document a temporary degraded match rule before enabling it in strict order.
2. If some modules do not expose a reusable row-local view trigger, add a thin data-attribute hook in the template rather than creating another tray-detail API. That keeps the existing module modal as the single detail surface.
3. If multiple rows can legitimately share a lot identifier on a page, prefer `batch_id` as the first match key and only fall back to `lot_id` when batch is absent.