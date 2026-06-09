# Production Edge Case Catalogue & Production Readiness Checklist
## TTT — Titan Track & Trace | Enterprise Manufacturing Workflow System
**Document Version:** 1.0  
**Generated Date:** 2026-06-08  
**Prepared By:** Senior QA Architect / Business Analyst / Solution Architect / Product Owner / Production Support Engineer  
**Classification:** Internal — Production Readiness

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Application Architecture Overview](#2-application-architecture-overview)
3. [Module-wise Edge Case Catalogue](#3-module-wise-edge-case-catalogue)
   - 3.1 Day Planning (DP)
   - 3.2 Input Screening (IS)
   - 3.3 Brass QC (BQC)
   - 3.4 Brass Audit (BA)
   - 3.5 IQF
   - 3.6 Jig Loading (JL)
   - 3.7 Jig Unloading Zone 1 & 2 (JU)
   - 3.8 Inprocess Inspection (IP)
   - 3.9 Nickel Inspection Zone 1 & 2 (NI)
   - 3.10 Nickel Audit Zone 1 & 2 (NA)
   - 3.11 Spider Spindle Zone 1 & 2
   - 3.12 Recovery Modules
   - 3.13 Admin Portal & User Management
   - 3.14 Model Master & Master Data
   - 3.15 Reports Module
   - 3.16 Cross-Module & System-Wide
4. [Production Readiness Checklist](#4-production-readiness-checklist)
5. [Critical Go-Live Risks](#5-critical-go-live-risks)
6. [Additional Production Readiness Reviews](#6-additional-production-readiness-reviews)
7. [Recommended Mitigations](#7-recommended-mitigations)
8. [Production Support Considerations](#8-production-support-considerations)
9. [Final Risk Assessment](#9-final-risk-assessment)

---

## 1. Executive Summary

The TTT (Titan Track & Trace) system is a production-grade Django-based manufacturing workflow application managing lot movement across 10+ processing stages with multi-zone support. The system tracks watchcase components from Day Planning through final Nickel Audit across 23 Django apps, ~150+ API endpoints, and a PostgreSQL database backend.

**Key Risk Profile:**

| Risk Category | Risk Level | Rationale |
|---|---|---|
| Data Integrity | CRITICAL | Multi-module tray reuse, delink logic, concurrent lot access |
| Security | HIGH | Session management, SSO pipeline, direct object access risks |
| Scalability | HIGH | In-process cache (LocMemCache) not suitable for multi-worker |
| Availability | MEDIUM | No distributed lock, no Redis, IIS-hosted monolith |
| Auditability | HIGH | Sparse logging, missing immutable audit trail |
| Disaster Recovery | HIGH | No documented backup schedule, no tested rollback |

**Production Readiness Score: 62/100 — Conditional Go-Live with Critical Fixes Required**

---

## 2. Application Architecture Overview

### Processing Pipeline

```
Day Planning → Input Screening → Brass QC → Brass Audit → IQF
     ↓                                                       ↓
     └──────── Recovery Modules (Rejection/Rework Path) ─────┘
                                                             ↓
                          Jig Loading → Jig Unloading (Z1/Z2)
                                              ↓
                          Inprocess Inspection
                                              ↓
                    Nickel Inspection (Z1/Z2) → Nickel Audit (Z1/Z2)
                                              ↓
                                    Spider Spindle (Z1/Z2)
```

### Technology Stack
- **Backend:** Python 3.x / Django 5.2.6 / Django REST Framework 3.16.1
- **Database:** PostgreSQL (watchcase2026)
- **Frontend:** HTML5 / CSS3 / JavaScript (no framework)
- **Auth:** Session-based + Microsoft MSAL (Entra ID SSO)
- **Cache:** LocMemCache (in-process, 300s TTL)
- **Hosting:** IIS (Windows Server)
- **Static:** WhiteNoise

---

## 3. Module-wise Edge Case Catalogue

### 3.1 Day Planning (DP)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| DP-001 | Day Planning | Two operators simultaneously scan the same lot ID from the pick table before either submits | Duplicate lot creation, qty duplication in DB | RowAccessLock must block second scan; return 409 Conflict | Critical | Verify RowAccessLock atomicity; add DB-level unique constraint on active lot + user |
| DP-002 | Day Planning | Bulk CSV upload contains same lot ID on multiple rows | Duplicate lots created silently | Validate for duplicate lot_id within CSV before any inserts; reject entire file or skip duplicates | Critical | Add pre-import deduplication pass; transactional bulk_create with unique constraint |
| DP-003 | Day Planning | Tray capacity in CSV exceeds model master defined tray_capacity | Over-allocated tray created silently | Cross-validate qty per tray against ModelMaster.tray_capacity; reject row | High | Add server-side capacity check in bulk upload service |
| DP-004 | Day Planning | User assigns a tray_id that already exists in TrayId table as active | Duplicate active tray in two lots | Block tray assignment if TrayId record exists with no delink; return descriptive error | Critical | Add unique active tray check before insert in DP tray service |
| DP-005 | Day Planning | User submits a lot then navigates back and resubmits the same lot | Double submission, qty counting error | Check is_submitted flag before processing; idempotency key per submission | Critical | Implement idempotency token or submission state check |
| DP-006 | Day Planning | Network drops mid-way through bulk upload (partial CSV processed) | Orphaned partial lot records | Wrap entire bulk upload in DB transaction; rollback on failure | High | Use atomic() transaction for full CSV; log and alert on partial success |
| DP-007 | Day Planning | Lot ID format differs from expected pattern (e.g., special chars, leading spaces) | Lot not found in downstream modules | Strict format validation on lot_id at submission | High | Add regex validator for lot_id format at API boundary |
| DP-008 | Day Planning | Operator deletes a lot that has already been picked by Input Screening | Orphaned IS records with invalid parent batch | Check downstream module activity before allowing DP lot deletion | Critical | Block DP lot deletion if any downstream module has active records |
| DP-009 | Day Planning | DraftTrayId auto-save fails silently (unique_together constraint violation) | User loses draft on page reload | Surface DB constraint error to user; retry with conflict resolution | Medium | Add unique conflict handling in TrayAutoSaveData upsert |
| DP-010 | Day Planning | Operator scans same tray_id twice during one session (duplicate in DraftTrayId) | Draft has duplicate tray inflating qty | Deduplicate tray scans in real-time before draft save; highlight duplicate to user | High | Client-side duplicate detection + server-side draft dedup |
| DP-011 | Day Planning | Day planning lot has zero trays assigned but is submitted | Empty lot propagates to IS with qty=0 | Require minimum 1 tray before submission | High | Add pre-submit validation: at least one tray must exist |
| DP-012 | Day Planning | DP_TrayIdRescan scan_count increments beyond configured maximum | Operator retries beyond policy limit | Cap scan retries and alert QA supervisor | Medium | Add max_scan_count threshold in DP_TrayIdRescan service |
| DP-013 | Day Planning | Microsoft SSO token expires during active bulk upload session | Upload halts mid-way; data in inconsistent state | Session check before long-running operations; client-side session expiry warning | High | Implement pre-operation session validity check; auto-extend session |
| DP-014 | Day Planning | Operator imports CSV with incorrect column headers | Silently maps wrong data to wrong fields | Strict column header validation at parse time; reject with descriptive error | High | CSV schema validation before any processing |
| DP-015 | Day Planning | Two different batch_ids assigned to same lot_id | Lot shows in two batches simultaneously | Enforce lot_id uniqueness across ModelMasterCreation at DB and application level | Critical | DB unique constraint on lot_id in ModelMasterCreation |

---

### 3.2 Input Screening (IS)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| IS-001 | Input Screening | Operator performs full accept on a lot that was already fully accepted by another operator | Double-accepted lot; qty duplication in TotalStockModel | is_submitted flag check + InputScreening_Submitted unique on lot_id prevents second submission | Critical | Ensure unique constraint on lot_id in InputScreening_Submitted; verify in acceptance service |
| IS-002 | Input Screening | Partial accept creates child lot; parent lot is then modified or deleted | Orphaned IS_PartialAcceptLot with invalid parent FK | Cascade rules: block parent deletion if child lot exists; verify on_delete=PROTECT | Critical | Set on_delete=PROTECT on parent_submission FK in IS_PartialAcceptLot |
| IS-003 | Input Screening | Partial accept qty + partial reject qty > original lot qty | Qty reconciliation failure | Backend validate: accepted_qty + rejected_qty must equal original_lot_qty | Critical | Add qty reconciliation check in IS submission service; reject if mismatch |
| IS-004 | Input Screening | Operator saves draft, session expires, another operator opens same lot | Two users editing same draft concurrently | RowAccessLock must hold lock during draft edit session | Critical | Verify RowAccessLock is acquired and held during draft lifecycle |
| IS-005 | Input Screening | Tray scanned in IS but tray_id not in TrayId master | Invalid tray accepted into production flow | Validate every scanned tray_id against TrayId master before accepting | Critical | Add tray master lookup in scan validation |
| IS-006 | Input Screening | IS_AllocationTray row has both accept_lot and reject_lot set (should be mutually exclusive) | Tray counted in both accept and reject | DB constraint or service check: reject if both FKs non-null | Critical | Add DB check constraint or pre-save signal validation |
| IS-007 | Input Screening | Delink tray scanned in IS that still has qty > 0 in previous lot | Qty double-counted across two lots | Validate delink status and remaining qty before accepting delinked tray | Critical | Full delink audit before reuse: check delink_timestamp, delink_qty = 0 |
| IS-008 | Input Screening | IP_Rejection_Draft JSON field corrupted (invalid JSON in DB) | Draft cannot be loaded; user loses work | Validate JSON on read; fallback to empty draft with error notification | High | JSON schema validation in draft load service |
| IS-009 | Input Screening | Rejection reason deleted from IP_Rejection_Table while a lot is drafted | Draft references deleted rejection reason ID | Foreign key on rejection_reason in IP_Rejection_Draft or soft-delete rejection reasons | High | Soft-delete rejection reasons; validate reason IDs at draft load |
| IS-010 | Input Screening | Operator submits full reject but acceptance data exists in IP_Accepted_TrayID_Store | Conflicting accept and reject data in DB | Clear accept draft on full reject submission; ensure mutual exclusivity | Critical | Service check: cannot have both accept and reject active for same lot |
| IS-011 | Input Screening | Multiple rejection reasons assigned to single tray with conflicting quantities | Rejection qty per reason exceeds tray qty | Validate sum of rejection quantities against tray qty | High | Add cross-reason qty validation per tray |
| IS-012 | Input Screening | View icon API called with lot_id that does not exist in InputScreening_Submitted | 500 error or empty modal | Return 404 with descriptive error; modal shows "lot not found" | Medium | Add existence check before detail query |
| IS-013 | Input Screening | IS_PartialRejectLot.trays_snapshot JSON does not match actual IP_Rejected_TrayScan records | Audit trail inconsistency | Snapshot must be generated from actual scan records at submission time, not frontend | High | Generate snapshot in submission service from DB records, not from client payload |
| IS-014 | Input Screening | Scanner device sends duplicate scan events (hardware glitch) | Duplicate tray_id entries | Deduplicate tray scans at API level with idempotency | High | Accept idempotency key per scan session; reject duplicate tray_id for same lot |
| IS-015 | Input Screening | Lot verification status (IP_TrayVerificationStatus) not updated after full accept | Tray shows as unverified in reports | Update verification status atomically with submission | High | Include verification status update in acceptance transaction |
| IS-016 | Input Screening | Batch rejection (batch_rejection=True) submits zero tray records | Batch rejection recorded with no tray evidence | Require at least one tray scan or explicit exception approval for batch rejection | High | Validate min 1 tray for batch rejection |
| IS-017 | Input Screening | is_revoked set to True but lot still appears in accept table | Revoked lot visible and actionable | Filter out is_revoked=True lots from all table queries | Critical | Add is_revoked=False filter to all IS table queries |

---

### 3.3 Brass QC (BQC)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| BQC-001 | Brass QC | BrassTrayId tray scanned belongs to a lot that was rejected in IS and not recovered | Invalid tray in Brass QC from rejected lot | Validate lot active state in LotMaster before accepting into Brass QC | Critical | Pre-scan lot status check against LotMaster.active and module_name |
| BQC-002 | Brass QC | Brass_QC_Draft_Store draft_transition_lot_id references a lot that has been deleted | Draft load fails or loads wrong lot | Validate transition lot exists before loading draft | High | Validate draft_transition_lot_id on draft load; clear stale drafts |
| BQC-003 | Brass QC | Brass_TopTray_Draft_Store has delink_tray_ids array with IDs already used in another lot's submission | Tray reuse collision | Validate all delink_tray_ids are truly delinked before draft submission | Critical | Real-time delink status check at draft load and final submission |
| BQC-004 | Brass QC | Two operators submit Brass QC for same lot simultaneously from different terminals | Duplicate submission records | RowAccessLock must block second submitter; unique lot constraint | Critical | Verify unique_together or unique=True on lot_id in Brass QC submission |
| BQC-005 | Brass QC | BrassTrayId.unique_together=(lot_id, tray_id) violated in concurrent insert | DB integrity error not surfaced to user | Catch IntegrityError and return 409 Conflict with clear message | High | Wrap insert in try/except IntegrityError; return 409 |
| BQC-006 | Brass QC | Rejected tray qty in Brass_QC_Rejected_TrayScan exceeds original tray qty from IS | Negative or inflated remaining qty | Validate rejected_tray_qty against source tray qty | Critical | Lookup original tray qty from BrassTrayId; reject if exceeded |
| BQC-007 | Brass QC | Operator changes rejection reason after saving draft but before submitting | Draft has stale reason; submission has different reason | Invalidate draft on rejection reason change; require fresh submission | High | Version draft payload; detect stale draft on submission |
| BQC-008 | Brass QC | Brass QC completed but TotalStockModel not updated for bq_physical_qty | Stock model out of sync | Wrap TotalStockModel update in same transaction as Brass QC submission | Critical | Atomic transaction for submission + stock update |
| BQC-009 | Brass QC | Brass QC lot_id appears in pick table after submission (is_active not cleared) | Lot submitted but still visible for editing | Set is_active=False on lot in pick table view after successful submission | High | Verify is_active flag update in submission service |
| BQC-010 | Brass QC | Draft type constraint (unique_together=(lot_id, draft_type)) violated on retry | Silent failure; draft not saved | Return descriptive error; merge or overwrite draft with upsert | Medium | Use get_or_create/update_or_create for draft save |

---

### 3.4 Brass Audit (BA)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| BA-001 | Brass Audit | Lot submitted for Brass Audit but Brass QC was never completed | Invalid workflow sequence | Check TotalStockModel.brass_submission_type before allowing BA pick | Critical | Module gate: BA pick table must verify BQC submission status |
| BA-002 | Brass Audit | Brass Audit action (approve/reject) called without supervisor role | Unauthorized audit approval | Role-based check on audit action endpoint | Critical | Add @permission_required or role check in brass_audit_action view |
| BA-003 | Brass Audit | Lot approved in BA but rejected in BQC recovery process simultaneously | Conflicting states across modules | Hold/release mutex: one active state per lot at any time | Critical | Enforce single active submission state in TotalStockModel |
| BA-004 | Brass Audit | submit_brass_audit called without required tray verification | Audit submitted with unverified trays | Require all trays verified before audit submission | High | Pre-submit check: all trays in BrassTrayId for lot must have IP_tray_verified=True |
| BA-005 | Brass Audit | Brass Audit completed but IQF pick table does not show the lot | Lot stuck between stages | Verify TotalStockModel.ba_submission_type updated to trigger IQF visibility | High | Verify atomic BA submission updates all relevant status fields |

---

### 3.5 IQF

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| IQF-001 | IQF | IQFTrayId.remaining_qty goes negative due to over-rejection | Negative stock in IQF | Validate: rejected_qty cannot exceed remaining_qty | Critical | Add qty guard in IQF rejection service |
| IQF-002 | IQF | iqf_toggle_verified called without supervisor/QA role | Unauthorized verification toggle | Role check on toggle endpoint | Critical | Add role guard on iqf_toggle_verified view |
| IQF-003 | IQF | IQF_Draft_Store unique_together=(lot_id, draft_type) conflict on multi-tab open | Draft overwritten silently | Detect multi-tab via session/draft timestamp; warn user | High | Add last_modified timestamp to draft; conflict detection on save |
| IQF-004 | IQF | IQF optimal distribution draft JSON schema mismatch after code update | Corrupt draft loaded with wrong structure | Version IQF_OptimalDistribution_Draft JSON schema | Medium | Add schema_version field to draft; validate on load |
| IQF-005 | IQF | IQF deletion (iqf_delete_lot) called on lot with accepted trays already recorded | Loss of accepted tray data | Block delete if IQF_Accepted_TrayID_Store has records for lot | Critical | Pre-delete check: no accepted records must exist |
| IQF-006 | IQF | IQF lot with iqf_reject_verify=True submitted for rework without rejection reason | Rework without reason tracked | Require rejection reason before marking iqf_reject_verify | High | Validate rejection reason presence before verify flag update |
| IQF-007 | IQF | Two IQF submissions for different draft_types on same lot in parallel threads | Race condition in IQF_Draft_Store | DB unique constraint is the last line of defense; service must also serialize | Critical | Use select_for_update() when reading draft before write |
| IQF-008 | IQF | IQF pick table shows lot with incomplete Brass Audit | Workflow skip | IQF pick table query must check ba_submission_type completion | High | Add stage gate filter in IQF pick table selector |
| IQF-009 | IQF | IQF accepted tray qty does not reconcile with IQF total after delink | Qty discrepancy in IQF stock model | Post-submission reconciliation check in IQF service | High | Add reconciliation assertion after submit |

---

### 3.6 Jig Loading (JL)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| JL-001 | Jig Loading | JigLoadInitAPI called twice for same lot (double initialization) | Two jig records for same lot | Idempotency check: if lot already initialized, return existing state | Critical | Check existing jig record before init; return existing if found |
| JL-002 | Jig Loading | JigLoadUpdateAPI called with mismatched lot and jig composition | Jig linked to wrong lot | Validate lot_id matches jig's parent lot in update | High | Cross-validate lot_id in update payload against existing record |
| JL-003 | Jig Loading | Jig composition exceeds maximum jig capacity | Physical damage risk on shop floor | Enforce max jig capacity from master data | Critical | Validate jig composition qty against jig capacity limit |
| JL-004 | Jig Loading | Jig loading completed but Jig Unloading pick table does not receive the lot | Lot stuck at jig loading stage | Verify state transition: jig_loading_done flag and TotalStockModel update | High | Verify all state flags updated atomically in JL submission |
| JL-005 | Jig Loading | Same model tray placed into multiple jigs simultaneously | Cross-contamination of lots in plating | Block tray from being added to more than one active jig | Critical | Add active jig check before tray assignment |
| JL-006 | Jig Loading | Bath number saved as empty string or zero | Traceability loss for plating bath | Require non-empty bath number before jig submission | High | Validate bath_number: not null, not empty, matches expected format |
| JL-007 | Jig Loading | Network timeout during jig_load_update; partial update committed | Jig in half-updated state | Use atomic transaction for full jig update | High | Wrap jig update in transaction.atomic() |

---

### 3.7 Jig Unloading Zone 1 & 2 (JU)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| JU-001 | Jig Unloading | Jig unloaded in Zone 2 when zone assignment is Zone 1 | Wrong zone processes wrong plating color | Validate plating_color zone assignment (Plating_Color.jig_unload_zone_1/2) before accepting | Critical | Zone gate: check plating color zone flag before allowing JU pick |
| JU-002 | Jig Unloading | Jig unloaded twice (Zone 1 and Zone 2 both process same jig) | Qty duplication in downstream modules | Enforce jig unloaded status flag; block re-unload | Critical | Set jig_unloaded=True on first JU submission; block if already set |
| JU-003 | Jig Unloading | Jig Unloading submission with qty that differs from Jig Loading qty | Unexplained qty loss/gain | Post-unload qty must reconcile with jig loaded qty within tolerance | High | Post-submission reconciliation check; flag discrepancy for QA |
| JU-004 | Jig Unloading | Zone 2 module operates independently without Zone 1 completion check | Sequence violation | Zone 2 pick table must gate on Zone 1 completion or explicit zone exemption | High | Add zone sequence gate in Zone 2 selector |
| JU-005 | Jig Unloading | Operator in Zone 1 and Zone 2 both pick the same jig at the same time | Race condition | RowAccessLock must be zone-aware; lock by jig_id not just lot_id | Critical | Extend RowAccessLock scope to include zone identifier |

---

### 3.8 Inprocess Inspection (IP)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| IP-001 | Inprocess Inspection | save_bath_number called with duplicate bath number for different lots | Bath traceability collision | Validate bath_number uniqueness per production run | High | Add uniqueness or collision check in bath number save service |
| IP-002 | Inprocess Inspection | save_jig_remarks called with empty or whitespace-only remark | Non-informative audit trail | Require non-empty, non-whitespace remarks | Medium | Validate remark content: strip and check length |
| IP-003 | Inprocess Inspection | Inprocess Inspection submitted without completing jig unloading | Workflow stage skip | Gate IP pick table on JU completion flag in TotalStockModel | Critical | Add JU completion gate in IP pick table filter |
| IP-004 | Inprocess Inspection | Multiple sessions edit IP data for same lot concurrently | Lost update | RowAccessLock or optimistic locking with version field | High | Add RowAccessLock in IP submission service |
| IP-005 | Inprocess Inspection | IP lot transitions to Nickel Inspection with missing ip_top_tray flag | Top tray traceability lost | Verify ip_top_tray set before IP submission allowed | High | Pre-submit check: ip_top_tray must be designated |

---

### 3.9 Nickel Inspection Zone 1 & 2 (NI)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| NI-001 | Nickel Inspection | Nickle_IP_Rejected_TrayScan tray accepted simultaneously in Nickle_IP_Accepted_TrayScan | Tray in both accept and reject tables | Mutual exclusivity check: tray cannot exist in both tables for same lot | Critical | Pre-insert check: verify tray not in opposite table |
| NI-002 | Nickel Inspection | Zone 1 and Zone 2 both process same lot due to routing error | Double processing, qty inflation | Validate lot zone assignment before NI pick; block if wrong zone | Critical | Add zone gate in Nickel Inspection pick table selector |
| NI-003 | Nickel Inspection | Rejection reason in NI not found in Nickle_IP_Rejection_Table | Foreign key error on submission | Validate rejection reason IDs exist before submission | High | Pre-submit rejection reason existence check |
| NI-004 | Nickel Inspection | Nickel Inspection submission without IP completion | Workflow skip | Gate NI on IP completion status in TotalStockModel | Critical | Add IP completion gate in NI pick table |
| NI-005 | Nickel Inspection | Nickle_IP_Accepted_TrayID_Store scan count differs from tray qty | Qty count mismatch | Post-insert: sum of accepted scans must equal accepted tray qty | High | Post-submission reconciliation in NI service |
| NI-006 | Nickel Inspection | NI rejection reason M2M table grows unbounded with soft-deleted reasons | DB bloat, slow queries | Periodic archival of unused rejection reasons | Low | Add archival job for inactive rejection reasons |

---

### 3.10 Nickel Audit Zone 1 & 2 (NA)

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| NA-001 | Nickel Audit | na_action called without audit supervisor role | Unauthorized audit action | Role check on na_action endpoint | Critical | Add role guard to na_action view |
| NA-002 | Nickel Audit | na_completed_tray_validate called with tray that was already validated | Double validation attempt | Idempotency: already-validated tray should return success without side effects | Medium | Check tray validation state before processing |
| NA-003 | Nickel Audit | Nickel Audit completed but TotalStockModel nickel audit status not updated | Lot stuck at NA; downstream blocked | Atomic update of TotalStockModel in NA submission | Critical | Wrap NA submission + TotalStockModel update in same transaction |
| NA-004 | Nickel Audit | Nickel Audit Zone 2 processes lot that belongs to Zone 1 | Cross-zone audit contamination | Zone gate check in NA Zone 2 pick table | Critical | Validate Plating_Color zone assignment before NA pick |
| NA-005 | Nickel Audit | Audit reason records deleted while lot is pending audit | Missing reason in audit report | Soft-delete audit reasons; validate on audit action | High | Implement soft-delete pattern for NA rejection reasons |

---

### 3.11 Spider Spindle Zone 1 & 2

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| SS-001 | Spider Spindle | SpiderSpindle_Z1 processes lot intended for Z2 | Cross-zone contamination | Zone assignment check before SpiderSpindle pick | Critical | Add zone gate in Spider Spindle pick table selector |
| SS-002 | Spider Spindle | SpiderSpindle submission without Nickel Audit completion | Workflow stage skip | Gate SpiderSpindle on NA completion in TotalStockModel | Critical | Add NA completion gate in Spider Spindle pick table |
| SS-003 | Spider Spindle | Zone 1 and Zone 2 both attempt to process same lot | Duplicate processing | Enforce single active zone per lot during Spider Spindle stage | Critical | Lock lot to one zone on first Spider Spindle pick |

---

### 3.12 Recovery Modules

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| REC-001 | Recovery | Recovery module invoked for a lot that was not rejected in parent module | Invalid recovery on non-rejected lot | Validate lot rejection status before allowing recovery submission | Critical | Gate recovery modules on parent module rejection flag |
| REC-002 | Recovery | Recovery submission creates new lot_id that collides with existing lot_id | Lot ID collision | Lot ID generation must guarantee uniqueness across all modules | Critical | Use DB sequence or UUID for recovery lot ID generation |
| REC-003 | Recovery | Recovery lot submitted but original rejected tray not delinked | Tray exists in both original and recovery lot | Atomically delink original tray on recovery submission | Critical | Include original tray delink in recovery submission transaction |
| REC-004 | Recovery | Recovery module updates TotalStockModel but original module qty not reduced | Qty inflation in stock model | Recovery must reduce original module qty and add to recovery qty atomically | Critical | Atomic debit/credit in TotalStockModel during recovery |
| REC-005 | Recovery | Recovery lot_id not associated with root_lot_id in LotMaster | Audit trail broken; cannot trace to origin | Set root_lot_id in LotMaster for every recovery lot | High | Enforce root_lot_id propagation in LotMaster creation service |
| REC-006 | Recovery | Multiple recovery submissions for same rejected tray | Qty double-recovered | Block second recovery if original tray already recovered | Critical | Track recovery status per tray; block duplicate recovery |

---

### 3.13 Admin Portal & User Management

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| ADM-001 | Admin Portal | UserDeleteAPIView deletes a user with active lot assignments | Lot owner missing; audit trail broken | Block user deletion if user has active lots in any module | Critical | Pre-delete check: user has no active lot ownership |
| ADM-002 | Admin Portal | UserModuleProvision grants access to module not in Module master | Invalid module access granted | Validate module_name against Module master before provisioning | High | FK constraint or lookup validation in module provisioning |
| ADM-003 | Admin Portal | UserProfile.role deleted while user has active session | User loses role mid-session; authorization bypass risk | Soft-delete roles; re-verify role on each request | High | Add role validation in request middleware |
| ADM-004 | Admin Portal | ShortcutConfiguration.keys JSON malformed in DB | UI shortcut system crashes | Validate JSON schema on save; fallback to defaults on load error | Medium | JSON schema validation for shortcut configuration |
| ADM-005 | Admin Portal | DashboardStatsAPIView cache poisoned with stale or zero counts | Wrong stats displayed to management | Cache TTL (300s) may be too long for production; add manual refresh | Medium | Add cache invalidation endpoint; reduce TTL or use event-driven invalidation |
| ADM-006 | Admin Portal | UserCreateAPIView creates duplicate username | Duplicate user in system | Enforce Django's unique=True on username; catch IntegrityError | High | Handle IntegrityError in user creation; return 400 with clear message |
| ADM-007 | Admin Portal | Admin deletes a Module that has active UserModuleProvision records | Users lose access unexpectedly | Cascade delete of provisions or block module deletion with active provisions | High | Block module deletion if active provisions exist |
| ADM-008 | Admin Portal | delete_all_tables() utility view accessible in production | Full data wipe in production | This endpoint must be removed or protected behind a superuser+debug=False guard | Critical | Remove or require superuser + confirmation token; never expose in production |
| ADM-009 | Admin Portal | Microsoft SSO callback URL mismatch (settings vs. Azure app registration) | All SSO logins fail | SSO callback URL must match exactly in settings and Azure; test after any domain change | Critical | Automated SSO smoke test post-deployment |
| ADM-010 | Admin Portal | MSAL client secret in settings.py (hardcoded) | Secret exposed in code repository | Move to environment variable or secrets manager | Critical | Externalize all secrets to .env or Azure Key Vault |

---

### 3.14 Model Master & Master Data

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| MM-001 | Model Master | ModelMaster deleted while active lots reference it via FK | Lots lose model reference; reports broken | Set on_delete=PROTECT on all lot FKs to ModelMaster | Critical | Audit all FK on_delete settings to ModelMaster |
| MM-002 | Model Master | TrayType capacity changed after trays allocated with old capacity | Allocated trays exceed new capacity | Prevent capacity reduction if active TrayId records reference this TrayType | Critical | Block TrayType capacity reduction if trays are allocated |
| MM-003 | Model Master | PolishFinishType renamed or deleted mid-production | Historical records lose polish finish reference | Soft-delete all master data; never hard-delete referenced records | High | Implement soft-delete (is_active flag) on all master data models |
| MM-004 | Model Master | LookLikeModel plating_stk_no M2M includes model deleted from ModelMaster | Broken M2M reference | Soft-delete models; or cascade M2M cleanup | High | Soft-delete models referenced in LookLikeModel |
| MM-005 | Model Master | ModelImage upload with no file extension or non-image file | Corrupt image reference in master | Validate file type and extension on upload | Medium | Validate MIME type and extension in image upload handler |
| MM-006 | Model Master | Vendor deleted with active lots referencing vendor_internal | Lot vendor traceability lost | on_delete=PROTECT on Vendor FK in active lot models | High | Set on_delete=PROTECT for Vendor FK |
| MM-007 | Model Master | Version deleted with active lots referencing it | Version traceability lost | on_delete=PROTECT for Version FK | High | Set on_delete=PROTECT for Version FK |
| MM-008 | Model Master | TotalStockModel cascade delete triggered on ModelMasterCreation delete | All scan records deleted across all modules | Add explicit on_delete=RESTRICT or protect with pre-delete signal | Critical | Audit cascade delete behavior; add pre-delete signal protection |

---

### 3.15 Reports Module

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| REP-001 | Reports | Large table query (10K+ lots) without pagination triggers timeout | Report page hangs or 504 | Enforce pagination (max 500 rows per page); background export for large data | High | Add pagination enforcement in all report queries |
| REP-002 | Reports | Excel/CSV export with special characters (commas, quotes, newlines in remarks) | Corrupt export file | Proper CSV escaping; use openpyxl for Excel with cell-level data | Medium | Use openpyxl or csv.writer with proper quoting |
| REP-003 | Reports | Report query spans all modules without index hints | Slow report; DB overload | Add composite indexes on frequently joined fields; use selectors with select_related | High | Profile report queries; add covering indexes |
| REP-004 | Reports | Report date range filter with start_date > end_date | Empty or misleading results | Validate date range at API: start_date must be <= end_date | Medium | Add date range validation in report API |
| REP-005 | Reports | Report shows deleted user names for historical records | Audit trail shows blank user | Preserve username snapshot at record creation; do not rely on User FK for display | High | Store user display name at record time; not just FK |
| REP-006 | Reports | Concurrent report exports by multiple users cause DB overload | DB performance degradation | Rate limit report exports per user; queue large exports | High | Add export rate limiting and async export queue |
| REP-007 | Reports | TotalStockModel dp_missing_qty shows negative values in report | Confusing report output | Validate missing qty cannot be negative in stock update service | Medium | Add non-negative constraint on missing qty fields |

---

### 3.16 Cross-Module & System-Wide

| Edge Case ID | Module | Scenario Description | Business Impact | Expected System Behavior | Severity | Recommended Mitigation |
|---|---|---|---|---|---|---|
| SYS-001 | System-Wide | LocMemCache not shared across IIS worker processes | Cache miss on every non-first worker; stale dashboard stats | Replace LocMemCache with Redis for multi-worker production | Critical | Migrate cache backend to Redis before production |
| SYS-002 | System-Wide | RowAccessLock is in-process; does not work across multiple Django processes | Two workers can lock same lot simultaneously | RowAccessLock must be DB-backed (select_for_update) not in-memory | Critical | Reimplement RowAccessLock using DB-level select_for_update() |
| SYS-003 | System-Wide | Session backend (cached_db) loses cache on IIS restart | All users logged out; active sessions lost | Decouple session storage from in-process cache; use Redis or pure DB session | High | Switch session backend to DB-only or Redis-backed |
| SYS-004 | System-Wide | Lot ID collision across modules due to independent generation | Same lot_id in two modules | Centralize lot ID generation in a single service with DB sequence | Critical | Use DB sequence or UUID for all lot_id generation |
| SYS-005 | System-Wide | LotMaster parent_lot_id / root_lot_id chain corrupted (null parent for child lot) | Audit trail broken; cannot trace lot history | Enforce parent_lot_id not null for all non-origin lots | High | DB constraint: non-ORIGIN lots must have parent_lot_id |
| SYS-006 | System-Wide | TotalStockModel qty fields updated without transaction; partial update on crash | Stock model permanently out of sync | All TotalStockModel updates must use transaction.atomic() | Critical | Audit all TotalStockModel update calls for atomic() wrapping |
| SYS-007 | System-Wide | Hold lot flag (hold_lot=True) in TotalStockModel does not block downstream module pick | Held lot continues through production | All module pick table queries must filter hold_lot=False | Critical | Add hold_lot=False filter to every module's pick table selector |
| SYS-008 | System-Wide | Concurrency: two users submit same lot in different modules simultaneously | State machine violation | Module-level RowAccessLock with DB select_for_update | Critical | DB-level locking on LotMaster row during any state transition |
| SYS-009 | System-Wide | Django DEBUG=True in production | Full stack traces exposed to users; security risk | Verify DEBUG=False in production settings.py | Critical | Settings audit: confirm DEBUG=False, ALLOWED_HOSTS set |
| SYS-010 | System-Wide | ALLOWED_HOSTS set to ['*'] in production | Host header injection risk | Set explicit ALLOWED_HOSTS list | High | Production settings review |
| SYS-011 | System-Wide | CSRF protection bypassed via exempt decorator on critical API endpoints | CSRF attacks possible | Audit all @csrf_exempt decorators; remove where not needed | High | Security audit of all @csrf_exempt usages |
| SYS-012 | System-Wide | User navigates to another user's lot detail via direct URL (IDOR) | Unauthorized data access | Validate requesting user has access to requested lot | Critical | Add ownership/permission check in every detail view |
| SYS-013 | System-Wide | Remark fields allow HTML/JavaScript injection (XSS) | Stored XSS via remarks field | Sanitize all text input server-side; escape on output | Critical | Add HTML escaping in all remark/text fields; use Django's autoescape |
| SYS-014 | System-Wide | Database connection pool exhausted during peak load | All requests fail with connection error | Configure connection pool size; add database connection monitoring | High | Set CONN_MAX_AGE and monitor active connections |
| SYS-015 | System-Wide | IIS worker recycles during active lot submission (long request) | Request killed mid-transaction | Transaction rollback is automatic; client receives 500; need retry UI | High | Add client-side error handling for 5xx; user can safely retry |
| SYS-016 | System-Wide | Audit log (LatencyMiddleware) does not log user actions, only latency | Insufficient audit trail for compliance | Extend middleware to log user, action, resource, result | High | Add structured action logging to all critical endpoints |
| SYS-017 | System-Wide | No rate limiting on login endpoint | Brute force password attack risk | Add rate limiting to TimedLoginView | High | Add django-ratelimit or equivalent on login view |
| SYS-018 | System-Wide | No rate limiting on API endpoints | DoS via API flooding | Add API rate limiting via DRF throttling | High | Configure DEFAULT_THROTTLE_CLASSES in DRF settings |
| SYS-019 | System-Wide | Large file upload via dropzone.js without server-side size limit | OOM or disk exhaustion | Enforce server-side file size limit (e.g., 10MB max) | Medium | Set DATA_UPLOAD_MAX_MEMORY_SIZE in settings.py |
| SYS-020 | System-Wide | delete_all_tables() view exists in production codebase | Catastrophic data loss risk | Remove or protect with superuser + environment guard | Critical | Remove delete_all_tables() from production; move to management command with safeguards |
| SYS-021 | System-Wide | Logging configured only for django.server; application errors not captured | Production errors invisible | Add structured logging for all app loggers to file/centralized sink | Critical | Configure logging for all app modules; rotate logs |
| SYS-022 | System-Wide | No health check endpoint | IIS/load balancer cannot determine app health | Add /health/ endpoint returning 200 if DB connected | Medium | Implement health check view with DB connectivity test |
| SYS-023 | System-Wide | Microsoft SSO client secret rotation not planned | Service disruption when secret expires | Track secret expiry; automate rotation or alert before expiry | High | Add secret expiry monitoring and renewal process |
| SYS-024 | System-Wide | Session cookie SameSite=Lax allows CSRF in cross-origin navigation | CSRF risk on cross-origin redirect | Evaluate SameSite=Strict for manufacturing intranet context | Medium | Assess SameSite=Strict suitability |
| SYS-025 | System-Wide | No DB connection retry logic on transient errors | Single transient DB error fails request | Add retry logic with exponential backoff for transient DB errors | Medium | Implement retry in critical service calls |

---

## 4. Production Readiness Checklist

### 4.1 Security Checklist

| # | Check | Status | Priority |
|---|---|---|---|
| S-01 | DEBUG=False in production | Verify | Critical |
| S-02 | SECRET_KEY not hardcoded in settings.py | Verify | Critical |
| S-03 | MSAL client_secret externalized to env var | Verify | Critical |
| S-04 | ALLOWED_HOSTS explicitly set (no wildcard) | Verify | Critical |
| S-05 | HTTPS enforced (SECURE_SSL_REDIRECT=True) | Verify | Critical |
| S-06 | HSTS configured (SECURE_HSTS_SECONDS) | Verify | High |
| S-07 | delete_all_tables() removed from production | Verify | Critical |
| S-08 | All API endpoints require authentication | Verify | Critical |
| S-09 | Role-based access enforced on audit actions | Verify | Critical |
| S-10 | CSRF protection on all state-changing endpoints | Verify | High |
| S-11 | XSS protection: all remark fields escaped on output | Verify | Critical |
| S-12 | IDOR protection: per-object permission checks | Verify | Critical |
| S-13 | Login rate limiting implemented | Verify | High |
| S-14 | Session cookie Secure=True on HTTPS | Verify | High |
| S-15 | File upload MIME type validation | Verify | Medium |

### 4.2 Data Integrity Checklist

| # | Check | Status | Priority |
|---|---|---|---|
| D-01 | All TotalStockModel updates wrapped in transaction.atomic() | Verify | Critical |
| D-02 | RowAccessLock uses DB-level select_for_update() | Verify | Critical |
| D-03 | Tray uniqueness enforced: no active tray in two lots | Verify | Critical |
| D-04 | Hold lot flag filters applied in all module pick tables | Verify | Critical |
| D-05 | Lot qty reconciliation: accepted + rejected = original | Verify | Critical |
| D-06 | Recovery module delinks original tray atomically | Verify | Critical |
| D-07 | Cascade deletes reviewed on TotalStockModel | Verify | Critical |
| D-08 | All master FK on_delete=PROTECT where appropriate | Verify | High |
| D-09 | Delink tray reuse validation before scan acceptance | Verify | Critical |
| D-10 | Tray mutual exclusivity: not in both accept and reject | Verify | Critical |
| D-11 | LotMaster root_lot_id propagated in all recovery flows | Verify | High |
| D-12 | Draft JSON schema versioning implemented | Verify | Medium |

### 4.3 Performance Checklist

| # | Check | Status | Priority |
|---|---|---|---|
| P-01 | LocMemCache replaced with Redis for multi-worker | Verify | Critical |
| P-02 | All pick table queries paginated (max 500 rows) | Verify | High |
| P-03 | select_related/prefetch_related on all N+1 queries | Verify | High |
| P-04 | DB indexes on lot_id, batch_id, created_at, active | Verify | High |
| P-05 | Report queries profiled and optimized | Verify | High |
| P-06 | DB connection pool configured (CONN_MAX_AGE) | Verify | High |
| P-07 | Large export operations queued asynchronously | Verify | Medium |
| P-08 | API rate limiting configured | Verify | High |
| P-09 | Session backend uses Redis or DB (not in-process cache) | Verify | Critical |
| P-10 | Static files served via WhiteNoise with caching headers | Verify | Medium |

### 4.4 Availability & Reliability Checklist

| # | Check | Status | Priority |
|---|---|---|---|
| A-01 | Health check endpoint /health/ returns DB connectivity | Verify | Medium |
| A-02 | IIS application pool configured with restart policy | Verify | High |
| A-03 | PostgreSQL connection retry configured | Verify | Medium |
| A-04 | Application error logging to file/centralized sink | Verify | Critical |
| A-05 | Alert on unhandled 5xx errors | Verify | High |
| A-06 | Alert on DB connection failures | Verify | High |
| A-07 | Microsoft SSO fallback/maintenance mode | Verify | Medium |

### 4.5 Operations & Deployment Checklist

| # | Check | Status | Priority |
|---|---|---|---|
| O-01 | Database backup schedule defined and tested | Verify | Critical |
| O-02 | Backup restore tested | Verify | Critical |
| O-03 | Rollback plan documented | Verify | High |
| O-04 | Migrations tested on production-sized dataset | Verify | High |
| O-05 | Environment variables documented (.env.example) | Verify | High |
| O-06 | MSAL secret expiry tracked and rotation planned | Verify | High |
| O-07 | Production deployment runbook documented | Verify | High |
| O-08 | Zero-downtime deployment strategy documented | Verify | Medium |
| O-09 | Post-deployment smoke tests defined | Verify | High |

---

## 5. Critical Go-Live Risks

### RISK-01: In-Process Cache in Multi-Worker Environment (CRITICAL)
**Description:** LocMemCache does not synchronize across IIS worker processes. Dashboard stats, user module provisions, and shortcut configurations will be inconsistent across workers.  
**Impact:** Users may see stale data; cache invalidation will not propagate; session loss on worker recycle.  
**Blocker:** YES — must resolve before go-live.  
**Fix:** Replace LocMemCache with Redis. Switch session backend to Redis or DB.

### RISK-02: RowAccessLock Not DB-Backed (CRITICAL)
**Description:** RowAccessLock appears to be in-memory or application-level. In a multi-process IIS deployment, two workers can independently acquire the same "lock" for the same lot.  
**Impact:** Race conditions on lot submissions; duplicate submissions; qty inflation.  
**Blocker:** YES.  
**Fix:** Implement select_for_update() on LotMaster row during all state transitions.

### RISK-03: delete_all_tables() in Production Codebase (CRITICAL)
**Description:** A utility view to delete all tables exists in the codebase with unclear access controls.  
**Impact:** Catastrophic data loss if accessed by any authenticated user.  
**Blocker:** YES.  
**Fix:** Remove from production deployment or restrict to superuser + confirmation token + management command only.

### RISK-04: TotalStockModel Non-Atomic Updates (CRITICAL)
**Description:** TotalStockModel is the single source of truth for all lot quantities. If any module's submission service updates it outside a transaction, a server crash between module submission and stock update leaves the system permanently inconsistent.  
**Blocker:** YES.  
**Fix:** Audit all submission services; wrap every TotalStockModel update in transaction.atomic() with the triggering module's submission.

### RISK-05: Hardcoded Secrets (CRITICAL)
**Description:** MSAL client_secret and potentially SECRET_KEY may be in settings.py in the repository.  
**Impact:** Credential exposure; unauthorized SSO access; Django security compromise.  
**Blocker:** YES.  
**Fix:** Externalize all secrets to environment variables; rotate any exposed secrets immediately.

### RISK-06: Hold Lot Flag Not Universally Filtered (CRITICAL)
**Description:** If hold_lot=True in TotalStockModel but module pick tables do not filter on this flag, held lots continue through production.  
**Impact:** Lots on quality hold proceed to next stage.  
**Blocker:** YES.  
**Fix:** Audit all pick table selectors; add hold_lot=False filter to every query.

### RISK-07: Lot ID Collision in Multi-Module Generation (CRITICAL)
**Description:** Recovery modules and partial lot creation generate new lot IDs. If generation is not centralized with a DB-backed sequence, collisions are possible.  
**Impact:** Two different lots with the same ID; data corruption.  
**Blocker:** YES.  
**Fix:** Centralize lot ID generation using Django's sequences or UUID4.

### RISK-08: Insufficient Logging (CRITICAL)
**Description:** Logging is configured only for django.server. Application-level errors, validation failures, and business events are not captured in production.  
**Impact:** Invisible production errors; impossible to diagnose issues post-incident.  
**Blocker:** YES for compliance; HIGH for operations.  
**Fix:** Configure structured logging for all app modules with rotation and centralized sink.

---

## 6. Additional Production Readiness Reviews

### 6.1 Data Integrity Risks

| Risk | Description | Severity |
|---|---|---|
| Qty Reconciliation | accepted_qty + rejected_qty ≠ original_lot_qty never cross-checked after each module's submission | Critical |
| Orphaned Child Lots | IS_PartialAcceptLot / IS_PartialRejectLot parent deleted without cascade check | Critical |
| Tray Reuse Without Delink | Delinked trays reused without verifying delink_qty = 0 | Critical |
| Stock Model Divergence | TotalStockModel updated outside transaction; crash leaves qty permanently wrong | Critical |
| Cascade Delete Risk | TotalStockModel deletion cascades to all scan tables across all modules | Critical |
| Boolean Flag Collision | Multiple boolean states (hold_lot, release_lot, draft, is_active) can coexist in invalid combinations | High |
| Draft JSON Corruption | No JSON schema version on IQF/Brass/IS draft stores; code updates can corrupt existing drafts | High |
| Missing Qty Tracking | dp_missing_qty, brass_missing_qty etc. in TotalStockModel never trigger alerts | Medium |

### 6.2 Security Risks

| Risk | Description | Severity |
|---|---|---|
| Secrets in Codebase | MSAL client_secret potentially in settings.py / repository | Critical |
| IDOR Vulnerability | Lot details, tray records accessible by guessing lot_id in URL | Critical |
| XSS via Remarks | Remark fields rendered without HTML escaping | Critical |
| delete_all_tables() Endpoint | Data wipe endpoint accessible to authenticated users | Critical |
| DEBUG Mode | Django DEBUG=True exposes tracebacks in production | Critical |
| Brute Force on Login | No rate limiting on /accounts/login/ | High |
| CSRF Exemptions | Unknown number of @csrf_exempt decorators on state-changing views | High |
| Role Escalation | No middleware-level role re-validation on session | High |
| SSO Token Refresh | No token refresh logic; stale tokens may bypass authentication | High |
| File Upload MIME | dropzone.js does not enforce server-side MIME validation | Medium |

### 6.3 Scalability Risks

| Risk | Description | Severity |
|---|---|---|
| In-Process Cache | LocMemCache not shared across workers; 2000 entry limit | Critical |
| No Async Worker | No Celery/async worker for long-running tasks (bulk upload, report export) | High |
| DB Connection Pool | CONN_MAX_AGE not configured; connection-per-request under load | High |
| Unbounded Queries | Pick tables may load all records without pagination | High |
| M2M Rejection Reasons | Unbounded M2M growth in rejection reason tables | Medium |
| JSON Draft Storage | Large JSON drafts stored in DB; no archival | Medium |

### 6.4 Availability Risks

| Risk | Description | Severity |
|---|---|---|
| Single Process Cache | IIS recycle clears all cache including sessions | Critical |
| No Health Check | No /health/ endpoint for load balancer or monitoring | High |
| SSO Single Point of Failure | If Microsoft Entra ID is unavailable, no fallback login | High |
| DB Connection Failure | No retry logic; single DB connection failure fails all requests | High |
| No Circuit Breaker | No circuit breaker for external calls (SSO, any future APIs) | Medium |

### 6.5 Disaster Recovery Risks

| Risk | Description | Severity |
|---|---|---|
| No Documented Backup Schedule | PostgreSQL backup schedule and retention not verified | Critical |
| Restore Not Tested | No evidence of backup restoration test | Critical |
| No Point-in-Time Recovery | PostgreSQL WAL archiving for PITR not documented | High |
| Rollback Plan Missing | No documented rollback plan for failed deployments | High |
| Migration Irreversibility | Some migrations may be irreversible (column drops, type changes) | High |
| Media File Backup | model images in /media/ not included in DB backup | Medium |

### 6.6 Monitoring & Alerting Gaps

| Gap | Description | Severity |
|---|---|---|
| No Application Performance Monitoring | No APM (New Relic, Datadog, Azure Monitor) configured | High |
| No Error Rate Alerting | 5xx errors not aggregated or alerted | Critical |
| No DB Slow Query Alerting | PostgreSQL slow query threshold not configured | High |
| No Cache Hit Rate Monitoring | Cache effectiveness unknown in production | Medium |
| No Business Metric Monitoring | No alerting on qty discrepancies, stuck lots, zero-output stages | High |
| Latency Middleware Headers Only | LatencyMiddleware writes headers but not centralized logs or dashboards | Medium |
| No Dead Letter Queue | Async operations (if added) have no dead letter handling | Medium |

### 6.7 Audit Trail Gaps

| Gap | Description | Severity |
|---|---|---|
| No Immutable Audit Log | No append-only audit log table for all state changes | Critical |
| User Actions Not Logged | Module submissions, approvals, rejections not logged to structured log | Critical |
| Deletion Not Logged | iqf_delete_lot and similar deletions have no audit trace | Critical |
| Role Change Not Logged | UserProfile role changes not audited | High |
| Draft Access Not Logged | Who opened and edited drafts not tracked | High |
| Remark Edit Not Audited | Remarks can be changed without version history | High |
| IP Address Not Captured | No client IP captured in submission records | Medium |

### 6.8 Compliance Risks

| Risk | Description | Severity |
|---|---|---|
| No Immutable Audit Trail | Manufacturing regulatory compliance requires tamper-evident records | Critical |
| User Action Non-Repudiation | Cannot prove who submitted a specific lot decision | High |
| Data Retention Policy | No defined data retention period or archival strategy | High |
| Access Review | No periodic user access review process documented | Medium |
| Export Controls | No restrictions on what data can be exported to CSV/Excel | Medium |

### 6.9 Master Data Risks

| Risk | Description | Severity |
|---|---|---|
| Hard Delete of Referenced Masters | ModelMaster, Version, Vendor, TrayType, PolishFinish can potentially be hard-deleted | Critical |
| No Master Data Versioning | Model master changes not versioned; historical lots lose accurate reference | High |
| Plating Color Zone Assignment | Incorrect zone flag on Plating_Color routes lot to wrong zone | Critical |
| TrayType Capacity Reduction | Capacity can be reduced below active tray allocations | Critical |
| Duplicate Model Numbers | No unique constraint enforcement audit on model_no | High |

### 6.10 Integration Risks

| Risk | Description | Severity |
|---|---|---|
| Microsoft SSO Secret Expiry | MSAL client secret will expire; no rotation alert | High |
| SSO Callback URL Dependency | Domain change breaks SSO without Azure app registration update | High |
| No ERP Integration | No ERP/SAP sync visible; manual data re-entry risk | Medium |
| No WMS Integration | Lot tracking is siloed within TTT; no external WMS sync | Medium |
| CSV Import as Integration | Bulk CSV upload is the primary data integration method; fragile | High |

### 6.11 Operational Risks

| Risk | Description | Severity |
|---|---|---|
| No On-Call Runbook | No documented runbook for production incidents | High |
| No Lot Stuck Detection | No automated detection of lots stuck between stages | High |
| Manual Qty Reconciliation | No automated qty reconciliation job across modules | High |
| Shift Change Risk | Active drafts from one shift not automatically expired | Medium |
| Scanner Device Failure | No offline mode; scanner failure stops entire production flow | High |
| Printer/Label Failure | If tray labels cannot print, trays cannot be scanned | Medium |

### 6.12 Deployment Risks

| Risk | Description | Severity |
|---|---|---|
| No Zero-Downtime Strategy | IIS deployment restarts workers; active sessions lost | High |
| Migration Safety | Column renames or drops on production-sized tables untested | High |
| Static Files Not Precompressed | WhiteNoise compression not pre-generated before deploy | Low |
| Environment Parity | Dev/staging environment may differ from production (OS, IIS version) | High |
| Settings Audit Missing | No automated check that production settings are correctly configured | High |

### 6.13 Rollback Risks

| Risk | Description | Severity |
|---|---|---|
| No Rollback Tested | Rollback procedure never tested on production data | Critical |
| Migration Rollback Gaps | Some migrations irreversible; rollback requires point-in-time restore | High |
| Feature Flag Absence | No feature flags to disable new features without rollback | Medium |
| Cache State on Rollback | LocMemCache has no TTL-forced purge on rollback | Low |

### 6.14 Supportability Risks

| Risk | Description | Severity |
|---|---|---|
| No Error Reference Codes | Errors returned without error codes; support cannot triage | Medium |
| No User-Facing Error Messages | Generic 500 errors shown to users in some paths | High |
| No Self-Service Recovery | Operators cannot self-recover from stuck lot; need DBA intervention | High |
| No Admin Lot Correction Tool | No admin UI to manually adjust lot qty in emergency | High |
| Sparse Code Documentation | Complex business logic without inline documentation | Medium |

---

## 7. Recommended Mitigations

### Priority 1 — Pre-Go-Live Blockers (Must Fix Before Production)

| # | Action | Effort | Owner |
|---|---|---|---|
| M-01 | Replace LocMemCache with Redis (cache + session backend) | Medium | DevOps |
| M-02 | Reimplement RowAccessLock using select_for_update() on LotMaster | High | Dev |
| M-03 | Remove delete_all_tables() endpoint from production | Low | Dev |
| M-04 | Externalize all secrets to environment variables | Low | Dev/DevOps |
| M-05 | Wrap all TotalStockModel updates in transaction.atomic() | High | Dev |
| M-06 | Audit and add hold_lot=False filter to all pick table selectors | Medium | Dev |
| M-07 | Centralize lot ID generation with DB sequence or UUID | Medium | Dev |
| M-08 | Configure structured application logging (file + rotation) | Medium | Dev/DevOps |
| M-09 | Set DEBUG=False, ALLOWED_HOSTS, HTTPS enforcement in production | Low | DevOps |
| M-10 | Add HTML escaping on all remark/text output fields | Medium | Dev |
| M-11 | Add IDOR protection (per-object permission checks) in all detail views | High | Dev |
| M-12 | Verify and document DB backup schedule + test restore | Low | DBA |

### Priority 2 — Post-Go-Live Within 30 Days

| # | Action | Effort | Owner |
|---|---|---|---|
| M-13 | Implement immutable audit log table for all state changes | High | Dev |
| M-14 | Add API rate limiting (DRF throttling + login rate limit) | Low | Dev |
| M-15 | Add /health/ endpoint with DB connectivity check | Low | Dev |
| M-16 | Implement qty reconciliation job (scheduled) | Medium | Dev |
| M-17 | Add lot stuck detection alert (lots in same stage > X hours) | Medium | Dev |
| M-18 | Document and test rollback procedure | Medium | DevOps/DBA |
| M-19 | Implement soft-delete on all master data models | High | Dev |
| M-20 | Add on_delete=PROTECT to critical FK relationships | Medium | Dev |

### Priority 3 — Within 90 Days

| # | Action | Effort | Owner |
|---|---|---|---|
| M-21 | APM integration (Azure Monitor / Datadog) | Medium | DevOps |
| M-22 | Async worker (Celery + Redis) for bulk upload and reports | High | Dev |
| M-23 | Draft JSON schema versioning | Medium | Dev |
| M-24 | Scanner device offline mode investigation | High | Dev/Product |
| M-25 | Admin lot correction tool for emergency manual adjustment | Medium | Dev |

---

## 8. Production Support Considerations

### 8.1 Common Incident Scenarios

| Incident | Likely Cause | First Response | Escalation |
|---|---|---|---|
| Lot stuck between stages | State flag not updated; hold flag set | Check TotalStockModel flags for lot; verify module submission status | DBA to inspect and update flag if safe |
| User cannot log in | SSO token expired; MSAL secret expired | Check SSO health; verify MSAL secret validity | Azure admin to check app registration |
| Pick table empty unexpectedly | Cache stale; hold_lot=True; filter bug | Clear cache; check lot status in DB | Dev to investigate query |
| Qty mismatch in report | Race condition; non-atomic update | Run reconciliation check on lot | DBA + Dev to trace update sequence |
| Tray scan rejected (valid tray) | Tray flagged active in another lot | Check TrayId table for tray status | DBA to verify and clear if safe |
| 500 error on submission | Unhandled exception; DB constraint violation | Check logs (if configured); check last exception in DB | Dev to investigate traceback |
| All users logged out | IIS worker recycle cleared in-memory sessions | Restart issue; move to Redis sessions | DevOps to configure Redis |

### 8.2 Key Database Queries for Production Support

```sql
-- Find lot stuck in a module (not progressed in 4 hours)
SELECT lot_id, batch_id, updated_at, stage 
FROM modelmasterapp_totalstockmodel 
WHERE updated_at < NOW() - INTERVAL '4 hours' 
  AND is_active = TRUE;

-- Find lots on hold
SELECT lot_id, hold_lot, hold_lot_reason 
FROM modelmasterapp_totalstockmodel 
WHERE hold_lot = TRUE AND is_active = TRUE;

-- Find duplicate active trays
SELECT tray_id, COUNT(*) 
FROM modelmasterapp_trayid 
WHERE rejected_tray = FALSE 
GROUP BY tray_id 
HAVING COUNT(*) > 1;

-- Qty reconciliation check for a lot
SELECT batch_id, lot_id, total_batch_qty,
       current_batch_qty
FROM modelmasterapp_modelmastercreation
WHERE lot_id = '<lot_id>';
```

### 8.3 Monitoring Dashboard Recommendations

- **Lot Throughput per Stage per Hour** — detect bottlenecks
- **Lots on Hold** — count and duration
- **Lots in Draft > 2 Hours** — abandoned draft detection
- **API 5xx Rate** — error trending
- **DB Query Latency (p95, p99)** — performance degradation
- **Active Session Count** — user load
- **Cache Hit Rate** — cache effectiveness
- **Qty Discrepancy Alerts** — automatic reconciliation alerts

---

## 9. Final Risk Assessment

### Risk Summary Matrix

| Category | Current Risk Level | Target Risk Level | Gap |
|---|---|---|---|
| Data Integrity | CRITICAL | LOW | Address Mitigations M-02, M-05, M-06 |
| Security | HIGH | LOW | Address Mitigations M-03, M-04, M-09, M-10, M-11 |
| Scalability | HIGH | MEDIUM | Address Mitigation M-01 |
| Availability | MEDIUM | LOW | Address Mitigations M-12, M-15 |
| Audit & Compliance | HIGH | MEDIUM | Address Mitigations M-13, M-16 |
| Disaster Recovery | HIGH | LOW | Address Mitigation M-12, M-18 |
| Monitoring | HIGH | MEDIUM | Address Mitigations M-08, M-21 |
| Supportability | MEDIUM | LOW | Address Mitigations M-17, M-25 |

### Overall Production Readiness Verdict

```
╔══════════════════════════════════════════════════════════╗
║        PRODUCTION READINESS: CONDITIONAL                 ║
║                                                          ║
║  Current Score:    62 / 100                              ║
║  Blockers:         12 Critical items must be resolved    ║
║  Recommended:      Resolve Priority 1 items before       ║
║                    go-live; plan Priority 2 items in     ║
║                    first 30 days post-launch             ║
║                                                          ║
║  GO-LIVE RECOMMENDATION: NOT READY                       ║
║  Re-assess after Priority 1 mitigations applied          ║
╚══════════════════════════════════════════════════════════╝
```

### Critical Go/No-Go Gate Checklist

Before go-live, all of the following must be confirmed:

- [ ] Redis deployed and cache backend switched
- [ ] RowAccessLock uses DB-level select_for_update
- [ ] delete_all_tables() removed from production build
- [ ] All secrets in environment variables; no secrets in code
- [ ] All TotalStockModel updates wrapped in atomic transactions
- [ ] Hold lot filter in all pick table selectors
- [ ] Lot ID generation centralized
- [ ] Structured application logging configured
- [ ] DEBUG=False; HTTPS enforced; ALLOWED_HOSTS set
- [ ] XSS protection on all remark fields
- [ ] IDOR protection in all detail views
- [ ] DB backup schedule verified and restore tested
- [ ] SSO smoke test passing post-deployment
- [ ] Post-deployment runbook reviewed

---

*End of Document*

---

## Files Created

- **production-edge-case.md**

## Files Modified

- None

## Files Deleted

- None
