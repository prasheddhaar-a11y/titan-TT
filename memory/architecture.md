# Architecture Memory

## SSOT Rules

Backend is Single Source of Truth.

Frontend must:
- display only
- never calculate business logic
- never determine tray eligibility
- never calculate movement state

---

# Quantity Rules

IQF incoming quantity:
- MUST use rw_qty
- MUST NOT use total_batch_quantity

Active tray quantity:
- Use remaining_qty after processing
- Do not rely on original tray_quantity

---

# Tray Rules

delink_tray:
- reusable
- temporary separation

rejected_tray:
- permanently rejected
- never reusable

These are NOT equivalent.

---

# Movement Rules

Movement controlled through:
- send_brass_qc
- send_brass_audit
- iqf_acceptance
- iqf_rejection
- iqf_onhold_picking

Module tracking:
- last_process_module
- next_process_module

---

# Query Rules

Always:
- filter by lot_id
- validate movement flags
- validate completion state

Never:
- query global tray state without scope
- trust frontend values

---

# Performance Rules

Always:
- use select_related/prefetch_related
- paginate large tables
- avoid repeated queries

Never:
- perform N+1 queries
- load unnecessary tray datasets

---

# Security Rules

Always:
- validate payloads
- enforce CSRF
- validate permissions
- sanitize inputs

Never:
- trust JS inputs directly
- expose debug errors