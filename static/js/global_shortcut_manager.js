(function () {
    'use strict';

    var SHORTCUT_ENDPOINT = '/adminportal/api/shortcuts/';
    var SESSION_KEY = 'activeRowContext';
    var ROW_HIGHLIGHT_CLASSES = [
        'gkb-row-focus',
        'dp-row-action-highlight',
        'gs-active-scan',
        'gs-hi'
    ];
    var ROW_QUERY = '#order-listing tbody tr, table.dataTable tbody tr, table tbody tr';
    var MODAL_ROOT_QUERY = [
        '.modal.show',
        '.modal[aria-modal="true"]',
        '.modal-overlay',
        '.overlay-modal',
        '.swal2-container',
        '.flag-modal-backdrop[aria-hidden="false"]',
        '.tray-scan-modal.open',
        '.tray-scan-modal-DayPlanning.open',
        '#trayScanModal.open',
        '#trayScanModal_DayPlanning.open',
        '[role="dialog"]',
        '.barcode-modal'
    ].join(', ');

    var shortcutConfigs = [];
    var shortcutsByKey = new Map();
    var shortcutsByCode = new Map();
    var activeRow = null;
    var pendingElement = null;
    var lastTargetSelector = '';
    var actionSelectorText = '';
    var tooltipApplyTimer = null;

    injectHighlightStyle();
    installPublicApi();
    installClickTracking();
    installKeyboardHandler();
    loadShortcuts();
    onReady(clearPending);
    onReady(installMutationObserver);
    window.addEventListener('pagehide', clearPending);

    function injectHighlightStyle() {
        if (document.getElementById('gkb-highlight-style')) {
            return;
        }
        var styleElement = document.createElement('style');
        styleElement.id = 'gkb-highlight-style';
        styleElement.textContent = [
            'tr.gkb-row-focus > td { background-color: #fff5bd !important; z-index: 50; }',
            'tr.gkb-row-focus { outline: 2px solid rgba(2,128,132,0.55); outline-offset: -2px; }'
        ].join('\n');
        document.head.appendChild(styleElement);
    }

    function installPublicApi() {
        window._gkbHighlightRow = function (row) {
            if (row) {
                highlightRow(row);
            }
        };
        window._gkbClearPending = function (row) {
            if (!row || row === activeRow) {
                clearPending();
            }
        };
        window.GlobalShortcutManager = {
            refresh: loadShortcuts,
            getActiveRow: function () {
                return activeRow;
            },
            getShortcut: getShortcutByCode,
            getShortcutKeyDisplay: function (shortcutCode) {
                var config = getShortcutByCode(shortcutCode);
                return config ? config.keyDisplay : '';
            },
            highlightRow: highlightRow,
            clear: clearPending
        };
    }

    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
    }

    function loadShortcuts() {
        return fetch(SHORTCUT_ENDPOINT, {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json'
            }
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Shortcut configuration request failed.');
                }
                return response.json();
            })
            .then(function (payload) {
                shortcutConfigs = sanitizeShortcutConfigs(payload.shortcuts || []);
                buildShortcutIndex();
                renderShortcutPanel();
                applyShortcutTooltips();
                applyShortcutTextBindings();
                if (typeof CustomEvent === 'function') {
                    document.dispatchEvent(new CustomEvent('ttt:shortcuts-loaded', { detail: { shortcuts: shortcutConfigs } }));
                }
                return shortcutConfigs;
            })
            .catch(function () {
                shortcutConfigs = [];
                shortcutsByKey = new Map();
                shortcutsByCode = new Map();
                actionSelectorText = '';
                renderShortcutPanel('Shortcut configuration unavailable.');
                return [];
            });
    }

    function sanitizeShortcutConfigs(configs) {
        return configs
            .filter(function (config) {
                return config && Array.isArray(config.keys) && config.keys.length;
            })
            .map(function (config) {
                return {
                    code: String(config.code || ''),
                    keys: config.keys.map(normalizeConfiguredKey).filter(Boolean),
                    keyDisplay: String(config.key_display || config.keys.join(', ')),
                    label: String(config.label || config.code || ''),
                    description: String(config.description || ''),
                    actionType: String(config.action_type || ''),
                    targetSelector: String(config.target_selector || '').trim(),
                    fallbackSelector: String(config.fallback_selector || '').trim(),
                    contexts: Array.isArray(config.contexts) ? config.contexts : [],
                    allowInModal: Boolean(config.allow_in_modal),
                    allowWhenTyping: Boolean(config.allow_when_typing),
                    sortOrder: Number(config.sort_order || 100)
                };
            })
            .sort(function (firstConfig, secondConfig) {
                return firstConfig.sortOrder - secondConfig.sortOrder || firstConfig.label.localeCompare(secondConfig.label);
            });
    }

    function buildShortcutIndex() {
        shortcutsByKey = new Map();
        shortcutsByCode = new Map();
        var actionSelectors = [];
        shortcutConfigs.forEach(function (config) {
            shortcutsByCode.set(config.code, config);
            config.keys.forEach(function (shortcutKey) {
                if (!shortcutsByKey.has(shortcutKey)) {
                    shortcutsByKey.set(shortcutKey, []);
                }
                shortcutsByKey.get(shortcutKey).push(config);
            });
            if (config.targetSelector && ['row_action', 'row_or_page_action', 'page_action', 'focus'].indexOf(config.actionType) !== -1) {
                actionSelectors.push(config.targetSelector);
            }
            if (config.fallbackSelector && ['row_or_page_action', 'page_action', 'focus'].indexOf(config.actionType) !== -1) {
                actionSelectors.push(config.fallbackSelector);
            }
        });
        actionSelectorText = actionSelectors.filter(Boolean).join(', ');
    }

    function getShortcutByCode(shortcutCode) {
        return shortcutsByCode.get(String(shortcutCode || '')) || null;
    }

    function normalizeConfiguredKey(shortcutKey) {
        var normalizedKey = String(shortcutKey || '').trim();
        if (!normalizedKey) {
            return '';
        }
        if (normalizedKey.toLowerCase() === 'esc') {
            return 'Escape';
        }
        if (normalizedKey.toLowerCase() === 'enter') {
            return 'Enter';
        }
        if (normalizedKey.length === 1) {
            return normalizedKey.toUpperCase();
        }
        return normalizedKey;
    }

    function normalizeEventKey(event) {
        var eventKey = event.key || '';
        if (!eventKey) {
            return '';
        }
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            var modifierParts = [];
            if (event.ctrlKey) {
                modifierParts.push('Ctrl');
            }
            if (event.shiftKey) {
                modifierParts.push('Shift');
            }
            if (event.altKey) {
                modifierParts.push('Alt');
            }
            if (event.metaKey) {
                modifierParts.push('Meta');
            }
            var modifiedKey = eventKey.length === 1 ? eventKey.toUpperCase() : eventKey;
            return modifierParts.concat(modifiedKey).join('+');
        }
        if (eventKey.length === 1) {
            return eventKey.toUpperCase();
        }
        return eventKey;
    }

    function renderShortcutPanel(message) {
        var gridElement = document.getElementById('shortcutsGrid');
        if (!gridElement) {
            return;
        }
        Array.from(gridElement.querySelectorAll(':scope > .sc-item, :scope > .sc-empty')).forEach(function (itemElement) {
            itemElement.remove();
        });
        if (message) {
            appendShortcutPanelMessage(gridElement, message);
            return;
        }
        var visibleConfigs = shortcutConfigs.filter(matchesCurrentContext);
        if (!visibleConfigs.length) {
            appendShortcutPanelMessage(gridElement, 'No shortcuts are configured for this screen.');
            return;
        }
        visibleConfigs.forEach(function (config) {
            var itemElement = document.createElement('div');
            var keyElement = document.createElement('kbd');
            var labelElement = document.createElement('span');
            itemElement.className = 'sc-item';
            itemElement.title = config.description || config.label;
            keyElement.className = 'sc-key';
            keyElement.textContent = config.keyDisplay;
            labelElement.className = 'sc-label';
            labelElement.textContent = config.label;
            itemElement.appendChild(keyElement);
            itemElement.appendChild(labelElement);
            gridElement.appendChild(itemElement);
        });
    }

    function appendShortcutPanelMessage(gridElement, message) {
        var messageElement = document.createElement('div');
        messageElement.className = 'sc-empty';
        messageElement.textContent = message;
        gridElement.appendChild(messageElement);
    }

    function applyShortcutTooltips() {
        shortcutConfigs.forEach(function (config) {
            var selectors = [config.targetSelector, config.fallbackSelector].filter(Boolean);
            selectors.forEach(function (selector) {
                queryVisibleElements(selector, document, true).forEach(function (element) {
                    var tooltipText = config.keyDisplay + ' - ' + config.label;
                    if (config.description) {
                        tooltipText += ': ' + config.description;
                    }
                    element.setAttribute('data-shortcut-code', config.code);
                    element.setAttribute('data-shortcut-key', config.keyDisplay);
                    if (!element.getAttribute('title')) {
                        element.setAttribute('title', tooltipText);
                    }
                    Array.from(element.querySelectorAll('kbd')).forEach(function (keyElement) {
                        keyElement.textContent = config.keyDisplay;
                    });
                });
            });
        });
    }

    function scheduleTooltipApply() {
        if (tooltipApplyTimer) {
            window.clearTimeout(tooltipApplyTimer);
        }
        tooltipApplyTimer = window.setTimeout(function () {
            tooltipApplyTimer = null;
            applyShortcutTooltips();
            applyShortcutTextBindings();
        }, 150);
    }

    function applyShortcutTextBindings() {
        Array.from(document.querySelectorAll('[data-shortcut-template-code]')).forEach(function (element) {
            var config = getShortcutByCode(element.getAttribute('data-shortcut-template-code'));
            if (!config) {
                return;
            }
            element.textContent = renderShortcutTemplate(element.getAttribute('data-shortcut-template') || '{key}', config);
        });
        Array.from(document.querySelectorAll('[data-shortcut-title-code]')).forEach(function (element) {
            var config = getShortcutByCode(element.getAttribute('data-shortcut-title-code'));
            if (!config) {
                return;
            }
            element.setAttribute('title', renderShortcutTemplate(element.getAttribute('data-shortcut-title-template') || '{label} ({key})', config));
        });
    }

    function renderShortcutTemplate(template, config) {
        return String(template || '')
            .replace(/\{key\}/g, config.keyDisplay)
            .replace(/\{label\}/g, config.label)
            .replace(/\{description\}/g, config.description);
    }

    function installMutationObserver() {
        if (!window.MutationObserver || !document.body) {
            return;
        }
        var observer = new MutationObserver(scheduleTooltipApply);
        observer.observe(document.body, { childList: true, subtree: true });
    }

    function installClickTracking() {
        document.addEventListener('click', function (event) {
            // Skip form elements — clicking select/input/textarea must not steal focus
            // or trigger row.focus(), which closes native browser dropdowns immediately.
            var targetTag = (event.target.tagName || '').toUpperCase();
            if (targetTag === 'SELECT' || targetTag === 'OPTION' ||
                targetTag === 'INPUT'  || targetTag === 'TEXTAREA') {
                return;
            }
            var row = getRowFromEventTarget(event.target);
            if (!row) {
                return;
            }
            highlightRow(row);
            var triggerElement = findTriggerFromClick(event.target);
            if (triggerElement) {
                pendingElement = triggerElement;
            }
        }, true);
    }

    function installKeyboardHandler() {
        document.addEventListener('keydown', function (event) {
            var normalizedKey = normalizeEventKey(event);
            if (shouldDeferToInputScreeningScan(event, normalizedKey)) {
                return;
            }
            var candidates = shortcutsByKey.get(normalizedKey) || [];
            if (!candidates.length) {
                return;
            }
            var typingTarget = isTypingTarget();
            var modalOpen = Boolean(getTopModalRoot()) || isShortcutPanelOpen();
            for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex += 1) {
                var config = candidates[candidateIndex];
                if (!matchesCurrentContext(config)) {
                    continue;
                }
                if (typingTarget && !config.allowWhenTyping) {
                    continue;
                }
                if (modalOpen && !config.allowInModal) {
                    continue;
                }
                if (executeShortcut(config, event, normalizedKey)) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    return;
                }
            }
        }, true);
    }

    function shouldDeferToInputScreeningScan(event, normalizedKey) {
        if (normalizedKey !== 'Enter') {
            return false;
        }
        var rejectModal = document.getElementById('isRejectModal');
        if (rejectModal && rejectModal.classList.contains('open') && isVisibleElement(rejectModal, true)) {
            return true;
        }
        var trayVerificationModal = document.getElementById('trayVerificationModal');
        if (trayVerificationModal && isVisibleElement(trayVerificationModal, true)) {
            return true;
        }
        return false;
    }

    function executeShortcut(config, event, normalizedKey) {
        if (config.actionType === 'builtin') {
            return executeBuiltin(config, event, normalizedKey);
        }
        if (config.actionType === 'row_action') {
            return executeRowAction(config);
        }
        if (config.actionType === 'row_or_page_action') {
            return executeRowOrPageAction(config);
        }
        if (config.actionType === 'page_action') {
            return executePageAction(config.targetSelector || config.fallbackSelector);
        }
        if (config.actionType === 'focus') {
            return executeFocusAction(config.targetSelector || config.fallbackSelector);
        }
        return false;
    }

    function executeBuiltin(config, event, normalizedKey) {
        if (config.code === 'picktable_scan') {
            if (typeof window._gScanActivate === 'function') {
                window._gScanActivate();
                return true;
            }
            return executePageAction(config.targetSelector || config.fallbackSelector);
        }
        if (config.code === 'hard_refresh') {
            if (typeof window.hardRefreshPage === 'function') {
                window.hardRefreshPage();
            } else {
                window.location.reload();
            }
            return true;
        }
        if (config.code === 'close_active') {
            closeActiveSurface();
            clearPending();
            return true;
        }
        if (config.code === 'execute_pending') {
            return executePendingAction();
        }
        if (config.code === 'navigate_previous') {
            return moveRowSelection(-1);
        }
        if (config.code === 'navigate_next') {
            return moveRowSelection(1);
        }
        if (config.code === 'scroll_left') {
            return scrollActiveTable(-240);
        }
        if (config.code === 'scroll_right') {
            return scrollActiveTable(240);
        }
        if (config.code === 'jump_page') {
            return goToPage(Number(normalizedKey));
        }
        return false;
    }

    function executeRowAction(config) {
        if (!config.targetSelector) {
            return false;
        }
        lastTargetSelector = config.targetSelector;
        if (activeRow) {
            var activeElement = findElementInRow(activeRow, config.targetSelector);
            if (activeElement) {
                setPendingElement(activeElement, activeRow, config.targetSelector);
                return clickElement(activeElement);
            }
            return false;
        }
        var found = findFirstRowWithElement(config.targetSelector);
        if (!found) {
            return false;
        }
        setPendingElement(found.element, found.row, config.targetSelector);
        return true;
    }

    function executeRowOrPageAction(config) {
        if (config.targetSelector) {
            lastTargetSelector = config.targetSelector;
            if (activeRow) {
                var activeElement = findElementInRow(activeRow, config.targetSelector);
                if (activeElement) {
                    setPendingElement(activeElement, activeRow, config.targetSelector);
                    return clickElement(activeElement);
                }
            } else {
                var found = findFirstRowWithElement(config.targetSelector);
                if (found) {
                    setPendingElement(found.element, found.row, config.targetSelector);
                    return true;
                }
            }
        }
        return executePageAction(config.fallbackSelector || config.targetSelector);
    }

    function executePageAction(selector) {
        if (!selector) {
            return false;
        }
        var pageElement = findFirstVisibleElement(selector);
        if (!pageElement) {
            return false;
        }
        pendingElement = pageElement;
        return clickElement(pageElement);
    }

    function executeFocusAction(selector) {
        var focusElement = findFirstVisibleElement(selector);
        if (!focusElement || isDisabledElement(focusElement)) {
            return false;
        }
        focusElement.focus();
        pendingElement = focusElement;
        return true;
    }

    function executePendingAction() {
        var modalRoot = getTopModalRoot();
        if (modalRoot && pendingElement && !modalRoot.contains(pendingElement)) {
            pendingElement = null;
        }
        if (pendingElement && isVisibleElement(pendingElement) && !isDisabledElement(pendingElement)) {
            var elementToClick = pendingElement;
            pendingElement = null;
            return clickElement(elementToClick);
        }
        if (modalRoot && activeRow && !modalRoot.contains(activeRow)) {
            return false;
        }
        if (activeRow && lastTargetSelector) {
            var activeElement = findElementInRow(activeRow, lastTargetSelector);
            if (activeElement) {
                return clickElement(activeElement);
            }
        }
        return false;
    }

    function clickElement(element) {
        if (!element || isDisabledElement(element)) {
            return false;
        }
        element.click();
        return true;
    }

    function moveRowSelection(direction) {
        var rows = getNavigableRows();
        if (!rows.length) {
            return false;
        }
        var currentIndex = activeRow ? rows.indexOf(activeRow) : -1;
        var nextIndex;
        if (currentIndex < 0) {
            nextIndex = direction > 0 ? 0 : rows.length - 1;
        } else {
            nextIndex = Math.min(Math.max(currentIndex + direction, 0), rows.length - 1);
        }
        var nextRow = rows[nextIndex];
        if (!nextRow) {
            return false;
        }
        highlightRow(nextRow);
        if (lastTargetSelector) {
            pendingElement = findElementInRow(nextRow, lastTargetSelector);
        } else {
            pendingElement = null;
        }
        return true;
    }

    function scrollActiveTable(delta) {
        var root = getTopModalRoot() || document;
        var wrappers = queryVisibleElements('.table-responsive, .dataTables_scrollBody, .dataTables_wrapper .table-responsive, .table-scroll-wrapper', root, true);
        var scrollWrapper = wrappers.find(function (wrapper) {
            return wrapper.scrollWidth > wrapper.clientWidth;
        }) || wrappers[0];
        if (!scrollWrapper && root !== document) {
            scrollWrapper = queryVisibleElements('.table-responsive, .dataTables_scrollBody, .dataTables_wrapper .table-responsive, .table-scroll-wrapper', document, true)[0];
        }
        if (!scrollWrapper) {
            return false;
        }
        scrollWrapper.scrollLeft += delta;
        return true;
    }

    function goToPage(pageNumber) {
        if (!pageNumber || pageNumber < 1) {
            return false;
        }
        if (typeof jQuery !== 'undefined' && jQuery.fn && jQuery.fn.dataTable) {
            try {
                var dataTablesApi = jQuery.fn.dataTable.tables({ visible: true, api: true });
                if (dataTablesApi && dataTablesApi.length) {
                    var pageInfo = dataTablesApi.page.info();
                    if (pageNumber <= pageInfo.pages) {
                        dataTablesApi.page(pageNumber - 1).draw('page');
                        return true;
                    }
                }
            } catch (error) {
                return false;
            }
        }
        // Support both Bootstrap 4 (.page-item .page-link) and simple (<li><a>) pagination structures
        var pageLinks = Array.from(document.querySelectorAll('.pagination .page-item:not(.disabled) .page-link, .pagination li:not(.disabled):not(.active) a'));
        var pageLink = pageLinks.find(function (linkElement) {
            return linkElement.textContent.trim() === String(pageNumber) && isVisibleElement(linkElement);
        });
        if (!pageLink) {
            return false;
        }
        pageLink.click();
        return true;
    }

    function closeActiveSurface() {
        if (typeof window._gScanIsActive === 'function' && window._gScanIsActive()) {
            if (typeof window._gScanClose === 'function') {
                window._gScanClose();
                return true;
            }
        }
        if (closeShortcutPanel()) {
            return true;
        }
        if (document.querySelector('.swal2-container')) {
            var swalClose = document.querySelector('.swal2-close, .swal2-cancel, .swal2-confirm');
            if (swalClose) {
                swalClose.click();
                return true;
            }
            if (window.Swal) {
                window.Swal.close();
                return true;
            }
        }
        if (typeof jQuery !== 'undefined') {
            var modalSet = jQuery('.modal.show');
            if (modalSet.length) {
                modalSet.first().modal('hide');
                return true;
            }
        }
        var modalRoot = getTopModalRoot();
        if (modalRoot) {
            var closeButton = modalRoot.querySelector('[data-dismiss="modal"], [data-bs-dismiss="modal"], .close, .btn-close, .modal-close, .barcode-modal-close, .flag-modal-close');
            if (closeButton && isVisibleElement(closeButton)) {
                closeButton.click();
                return true;
            }
            modalRoot.style.display = 'none';
            modalRoot.classList.remove('show', 'open', 'active');
            return true;
        }
        return false;
    }

    function closeShortcutPanel() {
        var modalElement = document.getElementById('shortcutsModal');
        var backdropElement = document.getElementById('shortcutsBackdrop');
        var didClose = false;
        if (modalElement && getComputedStyle(modalElement).display !== 'none') {
            modalElement.style.display = 'none';
            didClose = true;
        }
        if (backdropElement && getComputedStyle(backdropElement).display !== 'none') {
            backdropElement.style.display = 'none';
            didClose = true;
        }
        return didClose;
    }

    function isShortcutPanelOpen() {
        var modalElement = document.getElementById('shortcutsModal');
        return Boolean(modalElement && getComputedStyle(modalElement).display !== 'none');
    }

    function getRowFromEventTarget(target) {
        if (!target || !target.closest) {
            return null;
        }
        var row = target.closest('tbody tr');
        if (!row || !isVisibleElement(row) || isDisabledRow(row)) {
            return null;
        }
        if (row.closest('#shortcutsModal, #globalScanStatus, .swal2-container')) {
            return null;
        }
        return row;
    }

    function findTriggerFromClick(target) {
        if (!actionSelectorText || !target || !target.closest) {
            return null;
        }
        try {
            var triggerElement = target.closest(actionSelectorText);
            return triggerElement && isVisibleElement(triggerElement) && !isDisabledElement(triggerElement) ? triggerElement : null;
        } catch (error) {
            return null;
        }
    }

    function getNavigableRows() {
        var root = getTopModalRoot();
        var scope = root || document;
        var rows = queryRows(scope);
        if (root) {
            return rows;
        }
        return rows.filter(function (row) {
            return !row.closest('.modal, .swal2-container, #shortcutsModal, #globalScanStatus');
        });
    }

    function queryRows(root) {
        var seenRows = new Set();
        return queryElements(ROW_QUERY, root)
            .filter(function (row) {
                if (seenRows.has(row)) {
                    return false;
                }
                seenRows.add(row);
                return isVisibleElement(row) && !isDisabledRow(row);
            });
    }

    function findFirstRowWithElement(selector) {
        var rows = getNavigableRows();
        for (var rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
            var element = findElementInRow(rows[rowIndex], selector);
            if (element) {
                return { row: rows[rowIndex], element: element };
            }
        }
        return null;
    }

    function findElementInRow(row, selector) {
        return queryVisibleElements(selector, row, true).find(function (element) {
            return !isDisabledElement(element);
        }) || null;
    }

    function findFirstVisibleElement(selector) {
        var root = getTopModalRoot();
        if (root) {
            var modalElement = queryVisibleElements(selector, root, true).find(function (element) {
                return !isDisabledElement(element);
            });
            if (modalElement) {
                return modalElement;
            }
        }
        return queryVisibleElements(selector, document, true).find(function (element) {
            return !isDisabledElement(element);
        }) || null;
    }

    function queryVisibleElements(selector, root, includeFixed) {
        return queryElements(selector, root).filter(function (element) {
            return isVisibleElement(element, includeFixed);
        });
    }

    function queryElements(selector, root) {
        if (!selector || !root || !root.querySelectorAll) {
            return [];
        }
        try {
            return Array.from(root.querySelectorAll(selector));
        } catch (error) {
            return [];
        }
    }

    function getTopModalRoot() {
        var modalRoots = queryElements(MODAL_ROOT_QUERY, document).filter(function (rootElement) {
            if (!isVisibleElement(rootElement, true)) {
                return false;
            }
            if (rootElement.id === 'shortcutsModal' || rootElement.id === 'globalScanStatus') {
                return false;
            }
            if (rootElement.closest && rootElement.closest('#shortcutsModal, #globalScanStatus')) {
                return false;
            }
            return true;
        });
        return modalRoots.length ? modalRoots[modalRoots.length - 1] : null;
    }

    function isVisibleElement(element, includeFixed) {
        if (!element) {
            return false;
        }
        var computedStyle = getComputedStyle(element);
        if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden' || computedStyle.opacity === '0') {
            return false;
        }
        if (element.getClientRects().length > 0) {
            return true;
        }
        return Boolean(includeFixed && computedStyle.position === 'fixed');
    }

    function isDisabledElement(element) {
        return Boolean(
            element && (
                element.disabled ||
                element.getAttribute('aria-disabled') === 'true' ||
                element.classList.contains('disabled') ||
                element.classList.contains('is-disabled')
            )
        );
    }

    function isDisabledRow(row) {
        return Boolean(
            row && (
                row.getAttribute('aria-disabled') === 'true' ||
                row.classList.contains('disabled') ||
                row.classList.contains('is-disabled') ||
                row.hidden
            )
        );
    }

    function highlightRow(row) {
        if (!row || !isVisibleElement(row)) {
            return;
        }
        clearRowHighlights(row);
        activeRow = row;
        row.classList.add('gkb-row-focus', 'dp-row-action-highlight');
        row.setAttribute('aria-selected', 'true');
        row.setAttribute('data-gkb-active', 'true');
        if (!row.hasAttribute('tabindex')) {
            row.setAttribute('tabindex', '-1');
        }
        try {
            row.focus({ preventScroll: true });
        } catch (error) {
            row.focus();
        }
        scrollRowIntoView(row);
        saveRowState(row);
    }

    function clearRowHighlights(exceptRow) {
        var selector = ROW_HIGHLIGHT_CLASSES.map(function (className) {
            return 'tr.' + className;
        }).join(', ');
        queryElements(selector, document).forEach(function (row) {
            if (exceptRow && row === exceptRow) {
                return;
            }
            ROW_HIGHLIGHT_CLASSES.forEach(function (className) {
                row.classList.remove(className);
            });
            row.removeAttribute('data-global-scan-active');
            row.removeAttribute('data-gkb-active');
            row.removeAttribute('aria-selected');
        });
    }

    function setPendingElement(element, row, selector) {
        pendingElement = element;
        if (selector) {
            lastTargetSelector = selector;
        }
        if (row) {
            highlightRow(row);
        }
    }

    function clearPending() {
        clearRowHighlights(null);
        activeRow = null;
        pendingElement = null;
        lastTargetSelector = '';
        saveRowState(null);
    }

    function scrollRowIntoView(row) {
        var navbarHeight = (document.querySelector('.navbar') || {}).offsetHeight || 60;
        var rowRect = row.getBoundingClientRect();
        if (rowRect.top < navbarHeight + 20 || rowRect.bottom > window.innerHeight - 20) {
            window.scrollTo({
                top: window.scrollY + rowRect.top - navbarHeight - 50,
                behavior: 'smooth'
            });
        }
    }

    function saveRowState(row) {
        if (!row) {
            sessionStorage.removeItem(SESSION_KEY);
            return;
        }
        var lotId = getRowValue(row, 'data-stock-lot-id') || getRowValue(row, 'data-lot-id');
        var batchId = getRowValue(row, 'data-batch-id');
        var trayId = getRowValue(row, 'data-tray-id');
        if (!lotId) {
            return;
        }
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({
            lot_id: lotId,
            batch_id: batchId || null,
            tray_id: trayId || null,
            module: document.body ? document.body.getAttribute('data-module') || 'unknown' : 'unknown',
            timestamp: Date.now()
        }));
    }

    function restoreSavedRowState() {
        window.setTimeout(function () {
            var storedValue = sessionStorage.getItem(SESSION_KEY);
            if (!storedValue) {
                return;
            }
            try {
                var context = JSON.parse(storedValue);
                
                // Clear if context is too old (5 minutes)
                if (!context.timestamp || Date.now() - context.timestamp > 300000) {
                    sessionStorage.removeItem(SESSION_KEY);
                    return;
                }
                
                // ✅ NEW: Check if there's active modal context - if not, clear stale highlights
                // This prevents highlights from persisting after modal close or browser refresh
                var hasActiveModal = !!(
                    document.querySelector('.modal.show') ||
                    document.querySelector('.modal[style*="display: block"]') ||
                    document.querySelector('.tray-scan-modal.open') ||
                    document.querySelector('[role="dialog"][style*="display: block"]')
                );
                
                // ✅ NEW: Check if this is a fresh page load (no referrer = direct navigation/refresh)
                var isFreshPageLoad = !document.referrer || document.referrer === window.location.href;
                
                // Clear highlights on fresh page load or when no modal is active
                if (isFreshPageLoad && !hasActiveModal) {
                    sessionStorage.removeItem(SESSION_KEY);
                    sessionStorage.removeItem('globalScanLotId');
                    sessionStorage.removeItem('globalScanTrayId');
                    sessionStorage.removeItem('globalScanModule');
                    return;
                }
                
                var row = findRowByLotId(context.lot_id);
                if (row) {
                    highlightRow(row);
                } else {
                    sessionStorage.removeItem(SESSION_KEY);
                    sessionStorage.removeItem('globalScanLotId');
                    sessionStorage.removeItem('globalScanTrayId');
                }
            } catch (error) {
                sessionStorage.removeItem(SESSION_KEY);
            }
        }, 100);
    }

    function findRowByLotId(lotId) {
        if (!lotId) {
            return null;
        }
        var rows = queryRows(document);
        return rows.find(function (row) {
            return getRowValue(row, 'data-stock-lot-id') === lotId || getRowValue(row, 'data-lot-id') === lotId;
        }) || null;
    }

    function getRowValue(row, attributeName) {
        if (!row) {
            return '';
        }
        var ownValue = row.getAttribute(attributeName);
        if (ownValue) {
            return ownValue;
        }
        var childElement = row.querySelector('[' + attributeName + ']');
        return childElement ? childElement.getAttribute(attributeName) || '' : '';
    }

    function isTypingTarget() {
        var activeElement = document.activeElement;
        if (!activeElement) {
            return false;
        }
        var tagName = activeElement.tagName ? activeElement.tagName.toLowerCase() : '';
        return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || activeElement.isContentEditable;
    }

    function matchesCurrentContext(config) {
        var contexts = Array.isArray(config.contexts) ? config.contexts : [];
        if (!contexts.length) {
            return true;
        }
        var currentPath = window.location.pathname.toLowerCase();
        return contexts.some(function (context) {
            var normalizedContext = String(context || '').trim().toLowerCase();
            if (!normalizedContext || normalizedContext === 'global' || normalizedContext === '*') {
                return true;
            }
            return currentPath.indexOf(normalizedContext) !== -1;
        });
    }
})();