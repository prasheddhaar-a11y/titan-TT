// locators/day-planning.locators.ts
// Centralised locators for all Day Planning pages
// Derived from actual HTML IDs and classes in DP_PickTable.html and DP_BulkUpload.html

export const DayPlanningPickTableLocators = {
  // ── Page & Navigation ──────────────────────────────────────────────────────
  pageHeading: 'h1, .page-title, .dp-heading',
  moduleNavLink: 'a[href*="dayplanning"]',

  // ── Main Pick Table ────────────────────────────────────────────────────────
  pickTable: '#order-listing',
  pickTableRows: '#order-listing tbody tr',
  pickTableHeaders: '#order-listing thead th',

  // ── Scan Status ───────────────────────────────────────────────────────────
  scanStatusMessage: '#scanStatusMessage',
  scanHiddenInput: '#scanHiddenInput',

  // ── Row action buttons ─────────────────────────────────────────────────────
  editQtyButton: '.edit-qty-btn',
  deleteBatchButton: '.delete-batch-btn',
  trayScanButton: '.tray-scan-btn',

  // ── Tray Scan Modal (Editable) ─────────────────────────────────────────────
  trayScanModal: '#trayScanModal',
  closeTrayScanModal: '#closeTrayScanModal',
  modalPlatingStk: '#modalPlatingStk',
  modalTrayQty: '#modalTrayQty',
  trayScanSummary: '#trayScanSummary',
  trayIdRedoBtn: '#trayIDRedoBtn',
  traySlotExceededInfo: '#traySlotExceededInfo',
  trayScanDetails: '#trayScanDetails',
  trayScanDraftBtn: '#trayScanDraftBtn',
  trayScanSubmitBtn: '#trayScanSubmitBtn',
  trayScanCancelBtn: '#trayScanCancelBtn',
  trayQtyErrorFooter: '#trayQtyErrorFooter',

  // ── Tray Scan Modal (Day Planning readonly view) ────────────────────────────
  trayScanModalDayPlanning: '#trayScanModal_DayPlanning',
  closeTrayScanModalDayPlanning: '#closeTrayScanModal_DayPlanning',
  modalModelNoDayPlanning: '#modalModelNo_DayPlanning',
  trayValidateBtn: '#trayValidateBtn',
  trayValidateInput: '#trayValidateInput',
  trayScanRedoBtn: '#trayScanRedoBtn',
  trayErrorMessage: '#trayErrorMessage',
  trayErrorText: '#trayErrorText',
  trayScanDetailsDayPlanning: '#trayScanDetails_DayPlanning',

  // ── Tray ID Inputs ─────────────────────────────────────────────────────────
  trayIdInput: '.tray-id-input',

  // ── Hold/Unhold Modal ──────────────────────────────────────────────────────
  holdRemarkModal: '#holdRemarkModal',
  closeHoldRemarkModal: '#closeHoldRemarkModal',
  holdRemarkInput: '#holdRemarkInput',
  saveHoldRemarkBtn: '#saveHoldRemarkBtn',
  holdRemarkError: '#holdRemarkError',

  // ── Quick Help Panel ───────────────────────────────────────────────────────
  quickHelpPanel: '#howItWorksPanel',
  quickHelpDragHandle: '#howItWorksDragHandle',
  quickHelpCloseBtn: '#howItWorksClose',

  // ── Pagination / Search / Filter ──────────────────────────────────────────
  searchInput: 'input[type="search"], #tableSearch, .dataTables_filter input',
  paginationNext: '.paginate_button.next, [data-dt-idx="next"]',
  paginationPrev: '.paginate_button.previous, [data-dt-idx="previous"]',
  paginationInfo: '.dataTables_info',
  pageLengthSelect: '.dataTables_length select, [name="order-listing_length"]',

  // ── Status / Alerts ────────────────────────────────────────────────────────
  alertSuccess: '.alert-success, .swal2-success, [class*="success"]',
  alertError: '.alert-danger, .swal2-error, [class*="error"]',
  alertWarning: '.alert-warning, .swal2-warning',
  swalConfirmBtn: '.swal2-confirm',
  swalCancelBtn: '.swal2-cancel',
  swalPopup: '.swal2-popup',
} as const;

export const DayPlanningBulkUploadLocators = {
  // ── Page ──────────────────────────────────────────────────────────────────
  pageHeading: 'h1, .page-title',
  moduleNavLink: 'a[href*="bulk_upload"]',

  // ── Upload Form ───────────────────────────────────────────────────────────
  fileInput: 'input[type="file"]',
  uploadButton: 'button[type="submit"], #uploadBtn, .upload-btn',
  downloadTemplateBtn: 'a[href*="download_excel_template"], #downloadTemplateBtn',
  previewTable: '.preview-table, #previewTable',
  confirmUploadBtn: '#confirmUploadBtn, .confirm-upload',
  cancelUploadBtn: '#cancelUploadBtn, .cancel-upload',

  // ── Validation Messages ────────────────────────────────────────────────────
  uploadError: '.upload-error, .error-message',
  uploadSuccess: '.upload-success, .success-message',
  validationSummary: '.validation-summary, #validationSummary',
} as const;

export const DayPlanningCompletedTableLocators = {
  pageHeading: 'h1, .page-title',
  completedTable: '#completed-table, .completed-table',
  completedTableRows: '#completed-table tbody tr, .completed-table tbody tr',
  searchInput: 'input[type="search"], .dataTables_filter input',
  paginationNext: '.paginate_button.next',
  paginationPrev: '.paginate_button.previous',
  paginationInfo: '.dataTables_info',
  exportBtn: '.export-btn, #exportBtn',
} as const;

export const CommonLocators = {
  navbar: 'nav, .navbar, .sidebar',
  homeLink: 'a[href*="home"]',
  logoutLink: 'a[href*="logout"], #logoutBtn',
  breadcrumb: '.breadcrumb',
  loadingSpinner: '.loading, .spinner, #loader',
  toastContainer: '.toast, .toast-container',
  modalBackdrop: '.modal-backdrop',
  bodyContent: 'body',
} as const;
