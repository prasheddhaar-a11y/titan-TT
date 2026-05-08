# Jig Loading: Multi-Model Draft Restore + UI Cards + Info Banner

## Date
2025-01-XX (During January 2026 session)

## Issues Fixed

### 1. Multi-Model Draft Restore Bug (CRITICAL)
**Problem**: When drafting a multi-model jig and reopening:
- Model 1 trays restored correctly ✓
- Model 2+ trays cleared (showed empty "Scan Tray ID" inputs) ✗
- Only first model's qty counted in delink total

**Example Failure**:
```
Model 1 (2617WAC02): 100 qty, 7 trays delinked ✓
Model 2 (2617WAB02): 44 qty, 3 trays NOT restored ✗
Rows 8-10: Empty scan inputs (should show delinked trays)
Total delink: 100 (missing Model 2's 44)
```

**Root Cause**:
Draft restore flow:
1. Multi-model draft detected → calls `callInitAPI()` with secondary lots
2. Init API starts (async) → will re-render table with all models
3. **Scanned tray restoration runs IMMEDIATELY** (before table re-render)
4. Restoration finds no Model 2 rows (table not rendered yet) → skips them
5. Init API finishes → table re-renders with Model 2 rows → but restoration already completed

Timing race condition: Restoration code ran in outer scope, not waiting for init callback.

**Solution**:
1. Extracted `_restoreScannedTraysFromDraft(scannedTrays)` as standalone function
2. For multi-model path: Move restoration INSIDE `callInitAPI()` callback with `setTimeout(..., 100)`
3. Add early return after multi-model callInitAPI to prevent double restoration
4. Single-model path: Restore immediately (no re-init needed)

**Code Changes** (lines 6966-7145):
```javascript
// Multi-model draft: re-trigger init to restore full tray table
if (data.is_multi_model && data.multi_model_allocation && data.multi_model_allocation.length > 1) {
  // ... setup secondary lots ...
  window.callInitAPI({...}, function(initData) {
    if (initData && typeof window.applyResponseToUI === 'function') {
      window.applyResponseToUI(initData);
      console.log('[DRAFT_RESTORE] Multi-model tray table re-rendered');
    }
    // ✅ CRITICAL FIX: Restore scanned trays AFTER table re-render completes
    setTimeout(function() {
      _restoreScannedTraysFromDraft(data.scanned_trays);
    }, 100);
  });
  // Exit early - scanned trays will be restored in callback above
  return;
}

// Single-model path: restore immediately
_restoreScannedTraysFromDraft(data.scanned_trays);
```

---

### 2. Running Info Banner (New Feature)
**Request**: "at top i need running info banner - what user is typing and what is happening and whats next"

**Implementation**:
Added real-time status banner at top of modal showing:
- Current action/phase
- What user just did
- What to do next

**Banner States**:
```
🆔 Enter Jig ID → "Type or scan your Jig ID to begin"
📦 Jig ID entered → "Start scanning or selecting trays from the delink panel"
🔄 Scanning in progress (3/7 trays) → "Continue scanning remaining trays"
⚠️ Incomplete allocation (85/100 cases) → "Scan more trays or adjust broken hooks"
✅ Jig fully loaded → "Click Submit to finalize or Draft to save progress"
```

**Code Location** (after line 7234):
```javascript
function _updateInfoBanner() {
  var actionEl = document.getElementById('jigCurrentAction');
  var nextEl = document.getElementById('jigNextStep');
  if (!actionEl || !nextEl) return;

  var jigId = (document.getElementById('jigIdInput') || {}).value || '';
  var scannedTrays = document.querySelectorAll('.split-scan-input.validated').length;
  var totalTrays = document.querySelectorAll('.split-scan-input:not([disabled])').length;
  var loaded = parseInt(window.BACKEND_LOADED_CASES || 0);
  var effective = parseInt(window.BACKEND_EFFECTIVE_CAPACITY || 0);
  
  // ... state logic ...
}
window._updateInfoBanner = _updateInfoBanner;

// Attach event listeners
document.addEventListener('input', function(e) {
  if (e.target.id === 'jigIdInput' || e.target.classList.contains('split-scan-input')) {
    setTimeout(_updateInfoBanner, 50);
  }
});
```

**UI Markup** (after modal header):
```html
<div id="jigInfoBanner" style="background:linear-gradient(135deg,#e3f2fd,#e8f5e9); border:1px solid #4fc3f7; border-radius:8px; padding:10px 16px; margin:10px 16px; ...">
  <span style="font-size:16px;">ℹ️</span>
  <div style="flex:1;">
    <div id="jigCurrentAction" style="font-weight:700; margin-bottom:2px;">Ready to load jig</div>
    <div id="jigNextStep" style="font-size:11px; color:#0277bd; font-weight:500;">Enter Jig ID and scan trays to begin</div>
  </div>
</div>
```

---

### 3. Card-Based Header Layout
**Request**: "show info in simple cards"

**Implementation**:
Redesigned modal header with inline info cards instead of plain text.

**Old Design**:
```
Jig Loading | No of Cycle: 3 | [X]
```

**New Design** (card-based):
```html
<div class="jig-modal-header" style="background:linear-gradient(135deg,#f5f7fa,#e8eef5); padding:12px 16px; border-bottom:2px solid #d1dce5;">
  <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
    <h3 id="jigAddModalTitle">Jig Loading <span id="modalPlatingStockNo"></span></h3>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <!-- Cycle Info Card -->
      <div style="background:#fff; border:1px solid #b3e5fc; border-radius:6px; padding:6px 12px; box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <span style="font-size:10px; color:#0277bd; font-weight:600; display:block; margin-bottom:2px;">CYCLE</span>
        <span style="font-size:14px; color:#01579b; font-weight:700;"><span id="modalNoOfCycle">-</span></span>
      </div>
      <span class="close-btn">&times;</span>
    </div>
  </div>
</div>
```

---

### 4. Delink Section Card-Based Info
**Request**: "use light theme cards diff for each info and section"

**Old Design**:
```
Delink & Excess Lot Information | 0 Trays | Jig Cap: 100 | ✓ 3/7 scanned
```

**New Design** (separate cards):
```html
<div class="delink-header" style="background:linear-gradient(135deg,#fafbfc,#f0f4f7); padding:12px 16px; border-radius:8px; margin-bottom:10px; border:1px solid #d1dce5; box-shadow:0 2px 4px rgba(0,0,0,0.06);">
  <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
    <!-- Section Title -->
    <div style="font-size:13px; color:#01579b; font-weight:700; display:flex; align-items:center; gap:6px;">
      <span style="font-size:16px;">📦</span> Tray Allocation
    </div>
    
    <!-- Info Cards -->
    <div style="display:flex; gap:8px; flex-wrap:wrap;">
      <!-- Total Trays Card -->
      <div style="background:#fff; border:1px solid #b3e5fc; border-radius:5px; padding:4px 10px; box-shadow:0 1px 2px rgba(0,0,0,0.05);">
        <span style="font-size:9px; color:#0277bd; font-weight:600; display:block;">TRAYS</span>
        <span style="font-size:13px; color:#01579b; font-weight:700;"><span id="delinkTrayCount">0</span></span>
      </div>
      
      <!-- Lot Qty Card -->
      <div style="background:#fff; border:1px solid #c8e6c9; border-radius:5px; padding:4px 10px; box-shadow:0 1px 2px rgba(0,0,0,0.05);">
        <span style="font-size:9px; color:#2e7d32; font-weight:600; display:block;">LOT QTY</span>
        <span style="font-size:13px; color:#1b5e20; font-weight:700;"><span id="delinkLotQtyBadge">0</span></span>
      </div>
      
      <!-- Jig Cap Card -->
      <div style="background:#fff; border:1px solid #ffe0b2; border-radius:5px; padding:4px 10px; box-shadow:0 1px 2px rgba(0,0,0,0.05);">
        <span style="font-size:9px; color:#e65100; font-weight:600; display:block;">JIG CAP</span>
        <span style="font-size:13px; color:#bf360c; font-weight:700;"><span id="unifiedJigCapBadge">0</span></span>
      </div>
      
      <!-- Progress Badge (shown after scans) -->
      <div id="delinkStatsBadge" style="display:none; background:#d4edda; border:1px solid #28a745; border-radius:5px; padding:4px 10px;">
        <span style="font-size:9px; color:#155724; font-weight:600; display:block;">PROGRESS</span>
        <span style="font-size:11px; color:#155724; font-weight:700;"></span>
      </div>
    </div>
  </div>
</div>
```

**Badge Update Logic** (lines 2767-2785):
```javascript
function _updateDelinkStatsBadge() {
  // ... existing badge calculation ...
  
  // Update lot qty badge
  var lotQtyBadge = document.getElementById('delinkLotQtyBadge');
  if (lotQtyBadge) {
    var lotQty = parseInt((document.getElementById('lotQtyHidden') || {}).value || 0);
    lotQtyBadge.textContent = lotQty;
  }

  // Update info banner
  if (typeof window._updateInfoBanner === 'function') window._updateInfoBanner();
}
```

---

### 5. Excess Panel Light Theme Cards
**Request**: "excess lot ui can be aligned - use light theme cards"

**Old Design**:
```
Top Tray: [input] 25 qty
---
S.No | Model | Qty | Scan Tray ID
```

**New Design** (card-based):
```html
<!-- Top Tray Card (Yellow Theme) -->
<div id="excessTopTraySection" style="display:none; margin-bottom:10px; padding:12px; background:linear-gradient(135deg,#fff9c4,#fff59d); border:1.5px solid #fbc02d; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.08);">
  <div style="font-size:11px; font-weight:700; color:#f57f17; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
    <span style="font-size:14px;">⭐</span> TOP TRAY (Scan / Type / Select)
  </div>
  <input type="text" id="excessTopTrayScanInput" placeholder="Scan Top Tray ID" style="flex:1; padding:8px 12px; border:1.5px solid #fbc02d; border-radius:6px; font-size:13px; font-weight:600; background:#fff;" />
</div>

<!-- Excess Trays Card (Cyan Theme) -->
<div style="background:linear-gradient(135deg,#e0f7fa,#b2ebf2); border:1.5px solid #00acc1; border-radius:8px; padding:10px; box-shadow:0 2px 4px rgba(0,0,0,0.08);">
  <div style="font-size:11px; font-weight:700; color:#006064; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
    <span style="font-size:14px;">📋</span> EXCESS TRAYS
  </div>
  <table id="excessPanelTable" style="background:#fff; border-radius:5px; overflow:hidden;">
    <thead style="background:#00838f; color:#fff;">...</thead>
    <tbody id="excessPanelTableBody">...</tbody>
  </table>
</div>
```

---

## Files Modified

1. **a:\Workspace\Watchcase\TTT-Jan2026\static\templates\JigLoading\Jig_Picktable.html**
   - Lines 730-760: Modal header → card-based layout with cycle card
   - Lines 6966-7145: Draft restore → extracted function + multi-model timing fix
   - Lines 2767-2785: `_updateDelinkStatsBadge()` → added lot qty badge + info banner call
   - Lines 7234+: Added `_updateInfoBanner()` function + event listeners
   - Lines 815-835: Delink header → card-based info layout (TRAYS/LOT QTY/JIG CAP cards)
   - Lines 900-930: Excess panel → card-based light theme (yellow top tray card, cyan excess card)
   - After line 730: Added `jigInfoBanner` div with running status

---

## Testing Instructions

### Multi-Model Draft Restore Test
1. Open Jig Loading modal (normal lot, multi-model scenario)
2. Add secondary model (e.g., Model 1: 100 qty, Model 2: 44 qty)
3. Delink trays for both models:
   - Model 1: Delink 7 trays (rows 1-7)
   - Model 2: Delink 3 trays (rows 8-10)
4. Click "Draft" → modal closes
5. **Reopen draft** → rows 1-10 should show "Delinked" status
6. **Verify**: Model 2 trays (rows 8-10) restored correctly
7. **Verify**: Total delink qty = 144 (not just 100)

### Info Banner Test
1. Open Jig Loading modal
2. **Verify banner shows**: "🆔 Enter Jig ID → Type or scan your Jig ID to begin"
3. Enter Jig ID → **Banner updates**: "📦 Jig ID entered → Start scanning..."
4. Scan 3 trays → **Banner updates**: "🔄 Scanning in progress (3/7 trays)"
5. Scan all trays → **Banner updates**: "✅ Jig fully loaded → Click Submit..."

### Card Layout Test
1. Open modal → **Verify**:
   - Header has cycle card (white bg, blue border)
   - Info banner at top (gradient blue/green)
   - Delink header has 3 cards: TRAYS, LOT QTY, JIG CAP
   - Top tray card (yellow theme with ⭐ emoji)
   - Excess card (cyan theme with 📋 emoji)
2. Scan trays → **Verify**: Cards update dynamically
3. Check responsive layout → **Verify**: Cards wrap on small screens

---

## Architecture Alignment

### SSOT Compliance
✅ Backend owns draft data (`scanned_trays` array)
✅ Frontend restores from backend snapshot
✅ No frontend-generated tray data during restore

### No Regression
✅ Single-model draft restore unchanged (still works)
✅ Excess panel functionality preserved
✅ Broken hooks, top tray, delink logic untouched
✅ Existing button styling (CSS) retained

---

## Key Learnings

1. **Async Timing Race Conditions**: When multi-model init re-renders table asynchronously, restoration MUST happen inside callback, not outer scope
2. **setTimeout() as Safety**: 100ms delay ensures DOM re-render completes before tray restoration attempts
3. **Early Return Pattern**: Multi-model path returns early to prevent double restoration
4. **Function Extraction**: Shared `_restoreScannedTraysFromDraft()` eliminates code duplication between single/multi paths
5. **UI Event Delegation**: Info banner updates on input/change events via document-level listeners (efficient)
6. **Card-Based UI**: Separate themed cards (blue cycle, yellow top tray, cyan excess) improve visual hierarchy

---

## Validation Checklist
- [x] Multi-model draft restore works for 2+ models
- [x] Single-model draft restore still works
- [x] Info banner shows correct state at each phase
- [x] Delink header cards display TRAYS/LOT QTY/JIG CAP
- [x] Top tray card has yellow theme
- [x] Excess card has cyan theme
- [x] No duplicate tray restoration
- [x] Existing button CSS preserved
- [x] No JavaScript errors in console
- [x] Modal header cycle card displays
