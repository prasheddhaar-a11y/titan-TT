# Default System Prompt — TTT Manufacturing Workflow System

## READ FIRST
1. AGENTS.md
2. guardrails/PROJECT_GUARDRAILS.md
3. memory/module-flow.md
4. memory/architecture.md

---

## CORE PRINCIPLE: Backend is Single Source of Truth (SSOT)

**Frontend displays. Backend decides. Database remembers.**

All critical decisions (quantities, movement, routing) belong in Django backend ONLY.

---

# Real Module Flow (Verified from Code)

## Primary Path: IP → BQ → BA → JL (Production)

```
Input Screening (IP)
    ↓ [accepted qty → next_process_module = 'Brass QC']
Brass QC (BQ)
    ├─→ FULL_ACCEPT   [accepted_qty = total_stock] → next_process_module = 'Brass Audit'
    ├─→ FULL_REJECT   [accepted_qty = 0] → next_process_module = None (removed, sent to IQF reject table)
    └─→ PARTIAL       [0 < accepted_qty < total_stock] → parent closed, children route independently
        ├─→ Accept Child → Brass Audit
        └─→ Reject Child → IQF
    ↓
Brass Audit (BA)
    ├─→ FULL_ACCEPT   [accepted_qty = total_stock] → next_process_module = 'Jig Loading' ✓ PRODUCTION
    ├─→ FULL_REJECT   [accepted_qty = 0] → next_process_module = 'Brass QC' + send_brass_audit_to_qc=True (re-entry)
    └─→ PARTIAL       [0 < accepted_qty < total_stock] → parent closed, children route independently
        ├─→ Accept Child → next_process_module = 'Jig Loading'
        └─→ Reject Child → next_process_module = 'IQF' (send_brass_audit_to_iqf=True)
    ↓
Jig Loading (accepts ONLY from BA Full Accept)
    ↓
Production Flow
```

## IQF Loop Path: BA partial reject → IQF → BQ (return)

```
IQF (Quality Final Inspection)
    ├─→ FULL_ACCEPT   [accepted_qty = total_stock] → next_process_module = 'Brass QC' (return for secondary audit)
    ├─→ FULL_REJECT   [accepted_qty = 0] → next_process_module = None (stays in IQF Reject table)
    └─→ PARTIAL       [0 < accepted_qty < total_stock] → parent closed, children route independently
        ├─→ Accept Child → next_process_module = 'Brass QC' (return)
        └─→ Reject Child → next_process_module = None (IQF Reject table)
```

---

# Quantity Rules (CRITICAL)

## IQF Qty Processing (SSOT Violation = Data Loss)

| Context | Field | Rule |
|---------|-------|------|
| **IQF incoming qty** | `rw_qty` from Brass_QC_Rejection_ReasonStore | Use THIS, never `total_batch_quantity` |
| **IQF tray qty** | `remaining_qty` on IQFTrayId | Updated post-rejection, use for active qty |
| **Display qty** | Context builder output | Frontend renders only, no JS calculations |

```python
# ✅ CORRECT — IQF DOMAIN
rw_qty = Brass_QC_Rejection_ReasonStore.objects.get(lot_id=lot_id).total_rejection_quantity
iqf_tray_qty = IQFTrayId.objects.get(lot_id=lot_id, tray_id=tid).remaining_qty

# ❌ WRONG — SSOT VIOLATION
iqf_qty = ts.total_batch_quantity  # Uses original, not rw qty
tray_qty = ts.tray_capacity  # Uses capacity, not actual
```

## Lot Qty Equation (Always True)

```
total_stock = accepted_qty + rejected_qty + pending_qty

Examples:
- Full Accept: 100 = 100 + 0 + 0
- Full Reject: 100 = 0 + 100 + 0
- Partial: 100 = 70 + 30 + 0
- Never negative, never exceed original
```

---

# Movement Control (Verified from TotalStockModel)

## Field Meanings

| Field | Values | Purpose |
|-------|--------|---------|
| `next_process_module` | 'Brass QC' / 'Brass Audit' / 'Jig Loading' / 'IQF' / None | Controls which pick table includes lot |
| `last_process_module` | Module name | Audit trail, never reset |
| `send_brass_audit_to_qc` | True/False | Re-entry flag: Audit → BQ |
| `send_brass_audit_to_iqf` | True/False | Route flag: Audit partial reject → IQF |
| `brass_qc_accptance` | True/False | Full Accept at BQ |
| `brass_qc_rejection` | True/False | Full Reject at BQ |
| `brass_qc_few_cases_accptance` | True/False | Partial at BQ |
| `is_split` | True/False | Lot was split (parent closed) |
| `remove_lot` | True/False | Exclude from all pick tables |

## Pick Table Filter Logic (Django Views)

```python
# BQ Pick Table: Show lots awaiting BQ verification
BQ_lots = TotalStockModel.objects.filter(
    next_process_module='Brass QC',
    remove_lot=False
)

# BA Pick Table: Show lots awaiting BA verification
BA_lots = TotalStockModel.objects.filter(
    next_process_module='Brass Audit',
    remove_lot=False
)

# JL Pick Table: Show lots awaiting Jig Loading (ONLY from BA Full Accept)
JL_lots = TotalStockModel.objects.filter(
    next_process_module='Jig Loading',
    brass_audit_accptance=True,  # Verify: came from BA Full Accept
    remove_lot=False
)

# IQF Pick Table: Show lots awaiting IQF verification
IQF_lots = TotalStockModel.objects.filter(
    next_process_module='IQF',
    remove_lot=False
)
```

---

# Tray Rules (CRITICAL)

## Tray Lifecycle States

| Field | Value | Meaning | Reusable? |
|-------|-------|---------|-----------|
| `delink_tray` | True | Separated temporarily (empty) | **YES** ✓ |
| `delink_tray` | False | Normal active state | **YES** ✓ |
| `rejected_tray` | True | Permanently rejected | **NO** ✗ |
| `rejected_tray` | False | Normal active state | **YES** ✓ |

**Critical:** `delink_tray ≠ rejected_tray` — they are INDEPENDENT states.

## Tray Records per Module

| Module | Tray Model | Fields Used | Purpose |
|--------|-----------|------------|---------|
| Input Screening | TrayId | lot_id, tray_id, tray_quantity, top_tray | Origin |
| Brass QC | BrassTrayId | lot_id, tray_id, tray_quantity, delink_tray | QC trays |
| Brass Audit | BrassAuditTrayId | lot_id, tray_id, tray_quantity, top_tray | Audit trays |
| IQF | IQFTrayId | lot_id, tray_id, remaining_qty, top_tray, iqf_reject_verify | IQF trays |

---

# Django Architecture (Required Pattern)

```
Module/
├── models.py           → Schema only (no business logic)
├── views.py            → HTTP layer (thin controllers)
├── urls.py             → URL routing
├── services/
│   ├── routing.py      → Pure routing decisions (next_process_module)
│   ├── submission_service.py → Main orchestration
│   ├── lot_service.py  → Lot creation + validation
│   ├── tray_service.py → Tray management
│   ├── validators.py   → Input validation
│   └── selectors.py    → Query/read layer
└── templates/
    └── Module_PickTable.html → Render only
```

## View Pattern (Layered)

```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_action(request):
    # 1. VALIDATE (validators.py)
    validate_not_duplicate_submit(lot_id)
    validate_rejection_reasons(data)
    
    # 2. RESOLVE STATE (selectors.py)
    stock = TotalStockModel.objects.select_related('batch_id').get(lot_id=lot_id)
    trays = resolve_lot_trays(lot_id)  # tray_service.py
    
    # 3. DECIDE ROUTING (routing.py)
    next_stage = get_next_stage(submission_type)
    flags = get_stock_flag_updates(submission_type, accepted_qty, rejected_qty)
    
    # 4. ORCHESTRATE (submission_service.py)
    handle_submission(request, action)
    
    # 5. RESPOND
    return JsonResponse({"success": True, "next_module": next_stage})
```

---

# Frontend Rules (Non-Negotiable)

## What Frontend CAN Do

✓ Capture user input (form, modal, tray scans)  
✓ Call backend API with data  
✓ Display response (qty, status, errors)  
✓ Show loading/error states  
✓ Validate form format (email, required fields)  
✓ Refresh page or reload data  

## What Frontend CANNOT Do

✗ Calculate quantity (accepted_qty, rw_qty, remaining_qty)  
✗ Decide next stage  
✗ Validate tray eligibility  
✗ Check delink/reject states  
✗ Allocate trays  
✗ Generate lot_id  
✗ Create child records  
✗ Determine submission_type  

**If frontend does any ✗ item → SSOT violation.**

---

# Submission Flow (All Modules)

### Step 1: User Submits (Frontend)
```javascript
// BAD ❌ — calculates qty
const accepted_qty = total - rejected;  // NO
fetch('/api/submit', { data: { accepted_qty } });

// GOOD ✓ — calls API with raw data
fetch('/api/submit', {
  data: {
    lot_id,
    action: 'FULL_ACCEPT',  // or 'FULL_REJECT', 'PARTIAL'
    rejected_tray_ids: [],
    remarks: ''
  }
});
```

### Step 2: Backend Validates & Routes
```python
# views.py
def submit_action(request):
    action = request.data.get('action')  # 'FULL_ACCEPT' | 'FULL_REJECT' | 'PARTIAL'
    
    # Backend decides everything
    submission_service.handle_submission(request, action)
    
    # Returns: { success, next_module, message, ... }
```

### Step 3: Backend Updates Lot State
```python
# Set flags based on submission_type
if submission_type == "FULL_ACCEPT":
    stock.brass_qc_accptance = True
    stock.next_process_module = 'Brass Audit'
elif submission_type == "FULL_REJECT":
    stock.brass_qc_rejection = True
    stock.next_process_module = None

stock.save()
```

### Step 4: Frontend Displays Result
```javascript
// Just display what backend returns
if (response.success) {
  showStatus(`Moved to ${response.next_module}`);  // Trust backend
  redirectTo(response.next_module);
}
```

---

# Child Lot Generation (Partial Splits)

When a lot is split (0 < accepted_qty < total_stock):

### Backend Creates:

1. **New parent lot state:** `is_split=True`, `remove_lot=True`, `next_process_module=None`
2. **Accept child lot:** new `lot_id`, inherit batch, set target module
3. **Reject child lot:** new `lot_id`, inherit batch, set target module
4. **Tray records:** Copy trays to appropriate module (BrassAuditTrayId, IQFTrayId, etc.)
5. **Snapshot tables:** Store frozen tray data (for audit trail)

### Child Lot Field Setup (Example: BA Partial)

```python
# Accept child → Jig Loading
accept_child.lot_id = generate_new_lot_id()
accept_child.total_stock = accepted_qty
accept_child.next_process_module = 'Jig Loading'
accept_child.last_process_module = 'Brass Audit'
accept_child.brass_audit_accptance = True
accept_child.brass_audit_physical_qty = accepted_qty
accept_child.save()

# Reject child → IQF
reject_child.lot_id = generate_new_lot_id()
reject_child.total_stock = rejected_qty
reject_child.next_process_module = 'IQF'
reject_child.last_process_module = 'Brass Audit'
reject_child.send_brass_audit_to_iqf = True
reject_child.iqf_accepted_qty = rejected_qty  # Set IQF qty
reject_child.save()
```

---

# Before Coding: Mandatory Checklist

- [ ] **Understand module flow** — Read module-flow.md section for your module
- [ ] **Identify root cause** — Not the symptom, the cause (e.g., qty source wrong)
- [ ] **Trace backend source** — Find which view/service sets the field
- [ ] **Check movement flags** — Verify next_process_module logic
- [ ] **Verify SSOT** — Is frontend calculating? If yes = violation
- [ ] **Validate security** — Input sanitization? Permission check? CSRF?
- [ ] **Check performance** — N+1 queries? Unnecessary loads?
- [ ] **Explain root cause** — To user or in commit message
- [ ] **Minimal fix** — One focused change, no scope creep
- [ ] **Test existing workflows** — No regression on other modules

---

# NEVER Do This

```
❌ Move business logic to frontend
❌ Break existing tray flow
❌ Duplicate API logic
❌ Bypass validation
❌ Modify unrelated modules
❌ Hardcode qty calculations
❌ Trust frontend data directly
❌ Ignore movement flags
❌ Reuse tray_id across lots without delink
❌ Leave debug code in production
```

---

# ALWAYS Do This

```
✓ Preserve existing workflows
✓ Use backend as SSOT
✓ Validate permissions
✓ Filter by lot_id scope
✓ Use select_related/prefetch_related
✓ Add logging for audit trail
✓ Check draft persistence
✓ Test quantity reconciliation
✓ Validate performance (queries < 500ms)
✓ Explain to user what changed and why
```

---

# Project Stack

- **Backend:** Python + Django
- **Frontend:** HTML + CSS + JavaScript
- **Database:** SQL (queries via ORM)
- **Hosting:** IIS

## Core Modules

- Input Screening
- Brass QC
- Brass Audit
- IQF
- Jig Loading
- Jig Unloading (Z1, Z2)
- Day Planning
- Inprocess Inspection
- Nickel Inspection (Z1, Z2)
- Nickel Audit (Z1, Z2)
- Spider Spindle (Z1, Z2)
- Reports Module