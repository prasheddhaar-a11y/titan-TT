# Module Flow — Real Routing Logic

## Primary Manufacturing Flow

Input Screening (IP)
    ↓
Brass QC (BQ)
    ├─→ Full Accept → Brass Audit
    ├─→ Full Reject → IQF (Reject Table)
    └─→ Partial → Children (accept→BA, reject→IQF)
    ↓
Brass Audit (BA)
    ├─→ Full Accept → Jig Loading
    ├─→ Full Reject → Brass QC (re-entry)
    └─→ Partial → Children (accept→Jig Loading, reject→IQF)
    ↓
IQF (Quality Inspection)
    ├─→ Full Accept → Brass QC (return)
    ├─→ Full Reject → IQF Reject Table (stays)
    └─→ Partial → Children (both independent)
    ↓
Jig Loading → Production Flow

---

## Input Screening (IP)

Responsibilities:
- Accept/reject quantity split
- Tray creation and assignment
- Initial tray_id generation
- Lot origin point

Key Fields:
- `lot_id` - unique identifier (SSOT)
- `total_stock` - original lot quantity
- `total_IP_accpeted_quantity` - accepted qty
- `total_qty_after_rejection_IP` - rejected qty
- `next_process_module` = 'Brass QC'

Important:
- Tray quantities originate here (source of truth)
- TrayId records created here for each tray
- Movement flags initialized here

---

## Brass QC (BQ)

Responsibilities:
- QC verification of accepted trays
- Rejection reason tracking
- RW quantity generation (for IQF)
- Draft persistence and recovery

### Full Accept
- **Condition:** `accepted_qty = total_stock`
- **Action:** Set `brass_qc_accptance = True`
- **Next Stage:** `next_process_module = 'Brass Audit'`
- **Tray Move:** BrassTrayId records copied to Brass Audit

### Full Reject
- **Condition:** `accepted_qty = 0`
- **Action:** Set `brass_qc_rejection = True`
- **Next Stage:** `next_process_module = None` (removed from pick tables)
- **Route:** Rejection stored in Brass_QC_Rejection_ReasonStore
- **Destination:** IQF via rw_qty (RW = Reject Work)

### Partial Accept + Reject
- **Condition:** `0 < accepted_qty < total_stock`
- **Action:** Set `brass_qc_few_cases_accptance = True`, `is_split = True`
- **Parent Lot:** Closed (removed, next_process_module = None)
- **Child Lots Created:**
  - **Accept Child:** → Brass Audit (new lot_id)
  - **Reject Child:** → IQF (new lot_id, rw_qty set)

Key Fields:
- `brass_qc_accptance` - full accept flag
- `brass_qc_rejection` - full reject flag
- `brass_qc_few_cases_accptance` - partial flag
- `brass_qc_accepted_qty` - accepted qty snapshot
- `brass_qc_after_rejection_qty` - rejected qty snapshot
- `brass_physical_qty` - verified qty in BQ

Critical Rules:
- rw_qty becomes IQF incoming quantity
- Brass QC rejection store acts as source for IQF children
- Draft save → recovery on reload
- Only accepted trays move forward
- Reject reasons stored for traceability

---

## Brass Audit (BA)

Responsibilities:
- Final audit of Brass QC accepted lots
- Rejection re-audit on re-entry
- Tray verification
- Final split decision for IQF returns

### Full Accept
- **Condition:** `accepted_qty = total_stock`
- **Action:** Set `brass_audit_accptance = True`
- **Next Stage:** `next_process_module = 'Jig Loading'`
- **Tray Move:** BrassAuditTrayId records maintained
- **Status:** Lot proceeds to production

### Full Reject
- **Condition:** `accepted_qty = 0`
- **Action:** Set `brass_audit_rejection = True`
- **Next Stage:** `next_process_module = 'Brass QC'` (re-entry)
- **Flag:** `send_brass_audit_to_qc = True`
- **Reset:** `brass_qc_accepted_qty_verified = False` (re-check required)
- **History:** Brass QC flags preserved for audit trail

### Partial Accept + Reject
- **Condition:** `0 < accepted_qty < total_stock`
- **Action:** Set `brass_audit_few_cases_accptance = True`, `is_split = True`
- **Parent Lot:** Closed (next_process_module = 'Split Completed')
- **Child Lots Created:**
  - **Accept Child:** → Jig Loading (new lot_id)
  - **Reject Child:** → IQF (new lot_id, set iqf_accepted_qty)
- **Snapshots:** BrassAudit_PartialAcceptLot, BrassAudit_PartialRejectLot

Key Fields:
- `brass_audit_accptance` - full accept flag
- `brass_audit_rejection` - full reject flag
- `brass_audit_few_cases_accptance` - partial flag
- `brass_audit_accepted_qty` - verified qty
- `brass_audit_physical_qty` - physical count snapshot
- `send_brass_audit_to_qc` - re-entry flag for BQ

Important:
- Only Brass Audit Full Accept reaches Jig Loading
- Full Reject loops back to Brass QC for reprocessing
- Partial splits are final (parent closed)
- IQF reject child set with remaining qty

---

## IQF (Quality Inspection Final)

Responsibilities:
- Final inspection/verification
- Last-stage rejection handling
- Return path to Brass QC (via Full Accept)
- Draft persistence

### Full Accept
- **Condition:** `accepted_qty = total_stock`
- **Action:** Set `iqf_accptance = True`
- **Next Stage:** `next_process_module = 'Brass QC'` (return path)
- **Flag:** Lot goes back to Brass QC pick table
- **Purpose:** Secondary audit/verification

### Full Reject
- **Condition:** `accepted_qty = 0`
- **Action:** Set `iqf_rejection = True`
- **Next Stage:** `next_process_module = None` (stays in IQF)
- **Table:** Moved to IQF Reject table (terminal state)
- **Purpose:** Rejected lots remain for root-cause analysis

### Partial Accept + Reject
- **Condition:** `0 < accepted_qty < total_stock`
- **Action:** Set `iqf_few_cases_accptance = True`, `is_split = True`
- **Parent Lot:** Closed
- **Child Lots:** Both route independently
  - **Accept Child:** → Brass QC (return)
  - **Reject Child:** → IQF Reject Table

Key Fields:
- `iqf_accptance` - full accept flag
- `iqf_rejection` - full reject flag
- `iqf_few_cases_accptance` - partial flag
- `iqf_accepted_qty` - verified qty (SSOT for quantity)
- `iqf_after_rejection_qty` - rejected qty
- `remaining_qty` - active quantity in rejection flows

Critical Rules:
- IQF uses `iqf_accepted_qty` ONLY (never total_batch_quantity)
- `remaining_qty` tracks active quantity in tray-based splits
- Full Accept loops back to Brass QC (quality cycle)
- Full Reject ends lot lifecycle
- Draft save → recovery on reload
- Partial creates independent child lots

---

## Jig Loading

Responsibilities:
- Accept lots from Brass Audit Full Accept only
- Assign trays to jigs
- Manage tray allocation state
- Prevent duplicate allocation

Eligible Lots:
- `next_process_module = 'Jig Loading'` (from BA)
- `brass_audit_accptance = True`
- `total_stock > 0`

Critical Rules:
- Only full-accept trays from Brass Audit
- Tray state must persist across reloads
- No lots from IQF or partial rejects
- No re-entry from Brass QC rejects

---

# Shared System Rules

## Backend (Source of Truth)

Controls:
- All quantity calculations
- Movement state (next_process_module)
- Rejection routing decisions
- Draft state management
- Child lot creation

Responsibility:
- Set `next_process_module` on every submission
- Maintain `last_process_module` history
- Persist `draft_*` flags
- Generate new lot_id for splits
- Create child records (TrayId, Submission, Snapshots)

## Frontend

Responsibilities:
- Capture user input only
- Call API with submission_type + data
- Render response + status
- Show loading/error states

Must NOT:
- Calculate quantities
- Choose next stage
- Decide rejection routing
- Modify tray allocation
- Generate lot_id
- Create child records

## Movement Control

Mechanism:
- **`next_process_module`** field on TotalStockModel
- Values: Module name string or NULL
- Used by pick table queries to filter eligible lots

States:
- Active: `next_process_module = <module_name>`
- Removed: `next_process_module = None` OR `next_process_module = 'Split Completed'`
- Re-entry: `send_brass_audit_to_qc = True` (Brass Audit → BQ)

History:
- **`last_process_module`** records where lot came from
- Used for audit trail + navigation
- Never reset (cumulative record)