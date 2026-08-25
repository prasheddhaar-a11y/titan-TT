(function () {
    'use strict';

    function isDPPickTablePage() {
        return !!document.querySelector('#order-listing');
    }

    function applyDPPickTableFixes() {
        if (!isDPPickTablePage()) {
            return;
        }

        const config = window.NORMAL_USER_FIX_CONFIG || {};

        // Only apply this fix when Edit is explicitly enabled.
        if (config.edit !== true) {
            return;
        }

        fixDPTypeOfInputBlur();
        

        document.querySelectorAll('#order-listing tbody tr').forEach(function (row) {
            const actionCell = row.querySelector('td:nth-child(4)');

            if (!actionCell) {
                return;
            }

            // Don't create duplicate Edit buttons.
            if (actionCell.querySelector('.normal-user-edit-btn')) {
                return;
            }

            const batchId = row.getAttribute('data-batch-id');

            if (!batchId) {
                return;
            }

            const editLink = document.createElement('a');

            editLink.href = '#';
            editLink.className = 'edit-qty-btn normal-user-edit-btn';
            editLink.setAttribute('data-batch-id', batchId);
            editLink.title = 'Edit';

            const image = document.createElement('img');

            image.src = '/static/assets/icons/edit.png';
            image.alt = 'Edit';
            image.style.width = '24px';
            image.style.marginRight = '8px';
            image.style.height = 'auto';

            editLink.appendChild(image);
            actionCell.appendChild(editLink);
        });
    }


    /*
     * GLOBAL DP EDIT HANDLER
     *
     * This handles Edit buttons created by this global file.
     * DP_PickTable.html does not need to be modified.
     */
    document.addEventListener('click', function (event) {

        const btn = event.target.closest('.normal-user-edit-btn');

        if (!btn) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        const row = btn.closest('tr');

        if (!row) {
            return;
        }

        const qtyCell = row.querySelector('td:nth-child(6)');
        const batchId = btn.getAttribute('data-batch-id');

        if (!qtyCell || !batchId) {
            return;
        }

        const oldQty = qtyCell.textContent.trim();

        // Prevent multiple inputs.
        if (qtyCell.querySelector('input')) {
            return;
        }

        /*
         * Use the existing DP helper functions if available.
         */
        if (typeof window.moveEditBinRowToTop === 'function') {
            window.moveEditBinRowToTop(row);
        }

        qtyCell.innerHTML = `
            <div style="
                display: flex;
                flex-direction: column;
                gap: 4px;
                align-items: flex-start;
            ">
                <input
                    type="number"
                    min="1"
                    class="form-control qty-input normal-user-qty-input"
                    value="${oldQty}"
                    placeholder="Enter quantity"
                    style="
                        width: 80px;
                        display: inline-block;
                        padding: 4px 6px;
                        font-size: 13px;
                    "
                />

                <small style="
                    color: #666;
                    font-size: 11px;
                    font-weight: 500;
                    margin-top: -2px;
                ">
                    Press Enter to update
                </small>
            </div>
        `;

        const qtyInput = qtyCell.querySelector('.qty-input');

        if (!qtyInput) {
            return;
        }

        let editCancelled = false;


        function restoreRow() {

            if (typeof window.restoreEditBinRow === 'function') {
                window.restoreEditBinRow();
            }
        }


        function revertChanges() {

            editCancelled = true;

            qtyCell.textContent = oldQty;

            restoreRow();
        }


        function saveQuantity() {

            const newQty = qtyInput.value.trim();

            if (
                !newQty ||
                isNaN(newQty) ||
                parseInt(newQty) <= 0
            ) {
                Swal.fire(
                    'Error',
                    'Enter a valid quantity.',
                    'error'
                );

                qtyInput.focus();

                return;
            }


            if (newQty === oldQty) {

                revertChanges();

                return;
            }


            fetch(
                '/dayplanning/update_batch_quantity_and_color/',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },

                    body: JSON.stringify({
                        batch_id: batchId,
                        total_batch_quantity: newQty
                    })
                }
            )
            .then(function (res) {
                return res.json();
            })
            .then(function (data) {

                if (data.success) {

                    qtyCell.textContent = newQty;

                    restoreRow();

                    Swal.fire({
                        icon: 'success',
                        title: 'Quantity Updated!',
                        text: `Quantity changed to ${newQty}`,
                        timer: 1000,
                        showConfirmButton: false
                    }).then(function () {
                        location.reload();
                    });

                } else {

                    Swal.fire(
                        'Error',
                        data.error || 'Update failed',
                        'error'
                    );

                    revertChanges();
                }
            })
            .catch(function () {

                Swal.fire(
                    'Error',
                    'Network error',
                    'error'
                );

                revertChanges();
            });
        }


        qtyInput.addEventListener(
            'keydown',
            function (ev) {

                if (ev.key === 'Enter') {

                    ev.preventDefault();
                    ev.stopPropagation();

                    saveQuantity();

                    return;
                }


                if (
                    ev.key === 'Escape' ||
                    ev.keyCode === 27
                ) {

                    ev.preventDefault();
                    ev.stopPropagation();
                    ev.stopImmediatePropagation();

                    qtyInput.value = oldQty;

                    revertChanges();
                }

            },
            true
        );


        qtyInput.addEventListener(
            'blur',
            function () {

                if (editCancelled) {
                    return;
                }

                setTimeout(function () {

                    if (editCancelled) {
                        return;
                    }

                    if (!qtyCell.contains(document.activeElement)) {
                        revertChanges();
                    }

                }, 150);
            }
        );


        qtyInput.focus();
        qtyInput.select();

    });


    /*
     * INITIAL LOAD
     */
    function init() {
        applyDPPickTableFixes();
    }


    if (document.readyState === 'loading') {

        document.addEventListener(
            'DOMContentLoaded',
            init
        );

    } else {

        init();

    }


    /*
     * Expose function so dynamically rebuilt tables
     * can call the same global fix.
     */
    window.applyNormalUserDPPickTableFixes =
        applyDPPickTableFixes;

})();

/*
 * FIX 2: Type of Input should be visible for normal DP users.
 *
 * The DP template applies:
 *   - blurred-heading -> Type of Input header
 *   - blurred-cell    -> Type of Input data cells
 *
 * We identify the column using data-heading instead of assuming
 * a fixed column number.
 */
function fixDPTypeOfInputBlur() {
    const table = document.querySelector('#order-listing');

    if (!table) {
        return;
    }

    /*
     * 1. Remove blur from the Type of Input header.
     */
    const typeHeader = table.querySelector(
        'thead th[data-heading="Type of Input"]'
    );

    if (!typeHeader) {
        return;
    }

    typeHeader.classList.remove('blurred-heading');

    /*
     * 2. Find the actual column position of Type of Input.
     */
    const headerCells = Array.from(
        table.querySelectorAll('thead th')
    );

    const typeColumnIndex = headerCells.indexOf(typeHeader);

    if (typeColumnIndex === -1) {
        return;
    }

    /*
     * 3. Remove blur from the corresponding data cells.
     */
    table.querySelectorAll('tbody tr').forEach(function (row) {

        const cells = row.querySelectorAll('td');

        const typeCell = cells[typeColumnIndex];

        if (!typeCell) {
            return;
        }

        typeCell.classList.remove('blurred-cell');
    });
}

/*
 * FIX 3: DP Pick Table Hold/Release Toggle
 *
 * Normal users do not receive the toggle from DP_PickTable.html
 * because the original template renders it only for admins.
 *
 * This global fix recreates the same toggle for normal DP users.
 *
 * Delete is still NOT created here.
 */

function fixDPPickTableHoldToggle() {
    const table = document.querySelector('#order-listing');

    if (!table) {
        return;
    }

    const config = window.NORMAL_USER_FIX_CONFIG || {};

    // Apply only for the normal-user rollout.
    if (config.edit !== true) {
        return;
    }

    table.querySelectorAll('tbody tr').forEach(function (row) {

        const snoCell = row.querySelector('td:first-child');

        if (!snoCell) {
            return;
        }

        const snoContainer = snoCell.querySelector('.dp-sno-cell');

        if (!snoContainer) {
            return;
        }

        // Do not create duplicate toggles.
        if (snoContainer.querySelector('.normal-user-hold-toggle')) {
            return;
        }

        /*
         * Existing row state:
         *
         * row-inactive = lot is currently on hold
         * no row-inactive = lot is active
         *
         * Admin version uses:
         * checked     -> active / released
         * unchecked   -> held
         */
        const isHeld = row.classList.contains('row-inactive');

        const label = document.createElement('label');

        label.className =
            'hold-toggle-switch normal-user-hold-toggle';

        label.style.marginBottom = '0';

        const checkbox = document.createElement('input');

        checkbox.type = 'checkbox';
        checkbox.className = 'hold-toggle-btn normal-user-hold-toggle-btn';

        // Active lot = checked
        // Held lot = unchecked
        checkbox.checked = !isHeld;

        const slider = document.createElement('span');

        slider.className = 'hold-slider';

        label.appendChild(checkbox);
        label.appendChild(slider);

        /*
         * Insert the toggle before the S.No value,
         * matching the admin DP Pick Table layout.
         */
        const snoValue = snoContainer.querySelector('.sno-value');

        if (snoValue) {
            snoContainer.insertBefore(label, snoValue);
        } else {
            snoContainer.insertBefore(label, snoContainer.firstChild);
        }
    });
}


/*
 * FIX 3: Handle Hold / Release for toggles created
 * by normal_user.js.
 *
 * Event delegation is used because DataTables / table refreshes
 * can recreate the table rows dynamically.
 */
document.addEventListener('click', function (event) {

    const toggle = event.target.closest(
        '.normal-user-hold-toggle-btn'
    );

    if (!toggle) {
        return;
    }

    const config = window.NORMAL_USER_FIX_CONFIG || {};

    if (config.edit !== true) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    const row = toggle.closest('tr');

    if (!row) {
        return;
    }

    const batchId = row.getAttribute('data-batch-id');

    if (!batchId) {
        console.warn(
            '[NORMAL USER DP] Batch ID not found for hold toggle'
        );
        return;
    }

    const previousState = !toggle.checked;

    /*
     * checked = true
     *     -> Unhold / Release
     *
     * checked = false
     *     -> Hold
     */
    const intendedState = toggle.checked;

    const modal = document.getElementById('holdRemarkModal');
    const remarkInput = document.getElementById('holdRemarkInput');
    const remarkError = document.getElementById('holdRemarkError');

    if (!modal || !remarkInput) {
        console.warn(
            '[NORMAL USER DP] Hold remark modal not found'
        );

        // Restore toggle if modal is unavailable.
        toggle.checked = previousState;

        return;
    }

    /*
     * Highlight the selected row using the existing
     * DP global helper if available.
     */
    if (typeof window.activateDpActionRow === 'function') {
        window.activateDpActionRow(row);
    }

    /*
     * Store the current normal-user toggle context.
     */
    window.normalUserDPHoldContext = {
        toggle: toggle,
        row: row,
        batchId: batchId,
        previousState: previousState,
        intendedState: intendedState
    };

    const title = modal.querySelector('h5');

    if (title) {
        title.textContent = intendedState
            ? 'Unholding Reason'
            : 'Holding Reason';
    }

    remarkInput.value = '';

    if (remarkError) {
        remarkError.textContent = '';
    }

    modal.style.display = 'flex';

    setTimeout(function () {
        remarkInput.focus();
    }, 50);
});


/*
 * FIX 3: Save Hold / Release remark
 *
 * This uses the same backend endpoint already used
 * by the existing DP Pick Table.
 */
document.addEventListener('click', function (event) {

    if (!event.target.closest('#saveHoldRemarkBtn')) {
        return;
    }

    const context = window.normalUserDPHoldContext;

    if (!context) {
        return;
    }

    const remarkInput =
        document.getElementById('holdRemarkInput');

    const remarkError =
        document.getElementById('holdRemarkError');

    const modal =
        document.getElementById('holdRemarkModal');

    if (!remarkInput) {
        return;
    }

    const remark = remarkInput.value.trim();

    if (!remark) {

        if (remarkError) {
            remarkError.textContent = 'Remark required!';
        }

        context.toggle.checked = context.previousState;

        if (typeof window.restoreDpActionRow === 'function') {
            window.restoreDpActionRow();
        }

        return;
    }

    const action = context.intendedState
        ? 'unhold'
        : 'hold';

    fetch('/dayplanning/save_hold_unhold_reason/', {
        method: 'POST',

        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },

        body: JSON.stringify({
            batch_id: context.batchId,
            remark: remark,
            action: action
        })
    })

    .then(function (res) {
        return res.json();
    })

    .then(function (data) {

        if (!data.success) {

            if (remarkError) {
                remarkError.textContent =
                    data.error || 'Failed to save reason!';
            }

            context.toggle.checked =
                context.previousState;

            return;
        }

        /*
         * Successfully saved.
         */
        if (action === 'hold') {

            context.toggle.checked = false;

            context.row.classList.add('row-inactive');

            context.row.querySelectorAll('td').forEach(
                function (td, index) {

                    if (index > 0) {
                        td.classList.add(
                            'row-inactive-blur'
                        );
                    }
                }
            );

        } else {

            context.toggle.checked = true;

            context.row.classList.remove('row-inactive');

            context.row.querySelectorAll('td').forEach(
                function (td) {

                    td.classList.remove(
                        'row-inactive-blur'
                    );
                }
            );
        }

        if (modal) {
            modal.style.display = 'none';
        }

        if (typeof window.restoreDpActionRow === 'function') {
            window.restoreDpActionRow();
        }

        window.normalUserDPHoldContext = null;

        /*
         * Reload so the server-rendered state and table
         * remain synchronized.
         */
        location.reload();
    })

    .catch(function (error) {

        console.error(
            '[NORMAL USER DP] Hold/Release error:',
            error
        );

        if (remarkError) {
            remarkError.textContent =
                'Network error. Please try again.';
        }

        context.toggle.checked =
            context.previousState;
    });
});


/*
 * FIX 3: Close Hold/Release modal without saving.
 */
document.addEventListener('click', function (event) {

    if (!event.target.closest('#closeHoldRemarkModal')) {
        return;
    }

    const context = window.normalUserDPHoldContext;

    if (!context) {
        return;
    }

    context.toggle.checked =
        context.previousState;

    const modal =
        document.getElementById('holdRemarkModal');

    if (modal) {
        modal.style.display = 'none';
    }

    if (typeof window.restoreDpActionRow === 'function') {
        window.restoreDpActionRow();
    }

    window.normalUserDPHoldContext = null;
});


/*
 * FIX 3: Apply after the page loads.
 */
function initNormalUserDPPickTableToggle() {

    const config = window.NORMAL_USER_FIX_CONFIG || {};

    if (config.edit !== true) {
        return;
    }

    fixDPPickTableHoldToggle();
}


if (document.readyState === 'loading') {

    document.addEventListener(
        'DOMContentLoaded',
        initNormalUserDPPickTableToggle
    );

} else {

    initNormalUserDPPickTableToggle();

}


/*
 * Expose globally so DataTables/table refreshes can
 * re-apply the toggle.
 */
window.fixDPPickTableHoldToggle =
    fixDPPickTableHoldToggle;

/*
 * FIX 4: DP Completed Table
 *
 * Normal users:
 *   - Edit button   -> REMOVE
 *   - Delete icon   -> REMOVE
 *   - View/Eye      -> KEEP
 *
 * This fix is handled globally from normal_user.js.
 * No changes are required in the DP Completed HTML.
 */

function fixDPCompletedTableActions() {

    /*
     * Identify the DP Completed page.
     */
    const pageText = document.body.innerText || '';

    if (!pageText.includes('Day Planning Completed Table')) {
        return;
    }

    /*
     * Find the DP table.
     */
    const table = document.querySelector('#order-listing');

    if (!table) {
        return;
    }

    /*
     * Find the Action column dynamically.
     *
     * This avoids depending on a fixed column number.
     */
    const headers = Array.from(
        table.querySelectorAll('thead th')
    );

    const actionColumnIndex = headers.findIndex(function (header) {

        return header.textContent
            .trim()
            .toLowerCase() === 'action';

    });

    if (actionColumnIndex === -1) {
        return;
    }


    /*
     * Process every row in the Completed table.
     */
    table.querySelectorAll('tbody tr').forEach(function (row) {

        const cells = row.querySelectorAll('td');

        const actionCell = cells[actionColumnIndex];

        if (!actionCell) {
            return;
        }


        /*
         * -----------------------------------------
         * REMOVE EDIT ICON
         * -----------------------------------------
         */

        actionCell.querySelectorAll(
            '.edit-qty-btn, ' +
            '.normal-user-edit-btn, ' +
            '[title="Edit"], ' +
            'img[alt="Edit"], ' +
            'img[alt="Edit Disabled"]'
        ).forEach(function (element) {

            const editButton =
                element.closest('a, button');

            if (editButton) {
                editButton.remove();
            } else {
                element.remove();
            }

        });


        /*
         * -----------------------------------------
         * REMOVE DELETE ICON
         * -----------------------------------------
         *
         * Actual DP Completed HTML:
         *
         * <span>
         *     <img alt="Delete Disabled">
         * </span>
         *
         * Therefore remove the complete wrapper span.
         */

        actionCell.querySelectorAll(
            'img[alt="Delete Disabled"]'
        ).forEach(function (deleteIcon) {

            const deleteWrapper =
                deleteIcon.closest('span');

            if (deleteWrapper) {

                deleteWrapper.remove();

            } else {

                deleteIcon.remove();

            }

        });


        /*
         * Also handle any normal Delete icon
         * if it is rendered dynamically.
         */
        actionCell.querySelectorAll(
            'img[alt="Delete"], ' +
            '.delete-btn, ' +
            '.delete-icon, ' +
            '[title="Delete"], ' +
            '[title="delete"], ' +
            '.fa-trash, ' +
            '.fa-trash-alt'
        ).forEach(function (element) {

            const deleteButton =
                element.closest('a, button');

            if (deleteButton) {

                deleteButton.remove();

            } else {

                element.remove();

            }

        });

    });
}


/*
 * Initialize DP Completed Table fixes.
 */
function initDPCompletedTableActionsFix() {

    fixDPCompletedTableActions();

}


/*
 * Run after DOM is ready.
 */
if (document.readyState === 'loading') {

    document.addEventListener(
        'DOMContentLoaded',
        initDPCompletedTableActionsFix
    );

} else {

    initDPCompletedTableActionsFix();

}


/*
 * Expose globally so the fix can be
 * re-applied after table refresh/rebuild.
 */
window.fixDPCompletedTableActions =
    fixDPCompletedTableActions;