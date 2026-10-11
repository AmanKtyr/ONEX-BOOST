/**
 * ONEXIVAGYM Management Software
 * Role-Based Permissions & Sub-Admin Matrix Controller
 * 
 * Provides:
 * 1. Automatic Module Access & Privilege selection when a Designated Role is chosen.
 * 2. Quick Presets toolbar support (Full Admin, Manager, Front Desk, Trainer, Accounts, Inventory, Marketing, View Only, Clear All).
 * 3. Bidirectional syncing between Role select and Presets.
 * 4. Column Select-All checkboxes (View, Add, Change, Delete) with indeterminate states.
 * 5. Row-level Select-All / Deselect-All toggle switches.
 * 6. Live permission counter ("X Permissions Selected").
 * 7. Live search & filter for module rows.
 * 8. Dynamic Role badge & description preview.
 * 9. Password visibility toggle & strength meter.
 * 10. Password confirmation match validation.
 * 11. Photo reset & preview handling.
 * 12. Robust form validation before submission.
 */

(function () {
    'use strict';

    // Role Metadata: titles, descriptions, icons, badge classes, and associated preset
    const ROLE_CONFIG = {
        admin: {
            title: 'Full Administrator',
            icon: 'mdi-shield-crown',
            badgeClass: 'badge-soft-danger',
            desc: 'Unrestricted administrative authority across all gym operations, finance, members, and configurations.',
            preset: 'full-admin'
        },
        subadmin: {
            title: 'Gym Sub-Admin',
            icon: 'mdi-shield-account',
            badgeClass: 'badge-soft-primary',
            desc: 'Comprehensive operational control over gym members, trainers, schedules, billing, and reporting.',
            preset: 'subadmin'
        },
        manager: {
            title: 'Operations Manager',
            icon: 'mdi-briefcase-account',
            badgeClass: 'badge-soft-warning',
            desc: 'Oversees daily gym floor workflows, trainer shifts, member enrollments, and operational management.',
            preset: 'manager'
        },
        front_desk: {
            title: 'Front Desk & Reception',
            icon: 'mdi-desk',
            badgeClass: 'badge-soft-info',
            desc: 'Manages walk-in enquiries, new memberships, daily check-ins, fee collections, and events.',
            preset: 'front-desk'
        },
        trainer: {
            title: 'Fitness Coach & Trainer',
            icon: 'mdi-dumbbell',
            badgeClass: 'badge-soft-success',
            desc: 'Focuses on client training, diet schedules, workout regimens, attendance logs, and workout routines.',
            preset: 'trainer'
        },
        accounts: {
            title: 'Financial Accountant',
            icon: 'mdi-cash-multiple',
            badgeClass: 'badge-soft-success',
            desc: 'Full authority over billing invoices, member dues, payment receipts, vouchers, and gym expenditures.',
            preset: 'accounts'
        },
        inventory: {
            title: 'Equipment & Store In-Charge',
            icon: 'mdi-package-variant-closed',
            badgeClass: 'badge-soft-secondary',
            desc: 'Manages gym machines maintenance, repair logs, supplement sales inventory, and utility purchases.',
            preset: 'inventory'
        },
        marketing: {
            title: 'Marketing & CRM Lead',
            icon: 'mdi-bullhorn-outline',
            badgeClass: 'badge-soft-info',
            desc: 'Drives member lead acquisition, follow-up calls, trial passes, outbound marketing, and workshops.',
            preset: 'marketing'
        }
    };

    // Preset Definitions: Mapping module row keys to enabled privileges: ['view', 'add', 'change', 'delete']
    // Module key format: data-model ? `${app}_${model}` : app
    const PRESET_DEFINITIONS = {
        'full-admin': {
            name: 'Full Admin',
            matchAll: ['view', 'add', 'change', 'delete'],
            role: 'admin'
        },
        'subadmin': {
            name: 'Sub-Admin',
            role: 'subadmin',
            modules: {
                enquiry: ['view', 'add', 'change', 'delete'],
                members: ['view', 'add', 'change', 'delete'],
                trainers: ['view', 'add', 'change', 'delete'],
                attendance: ['view', 'add', 'change', 'delete'],
                billing: ['view', 'add', 'change', 'delete'],
                expenses: ['view', 'add', 'change', 'delete'],
                inventory: ['view', 'add', 'change', 'delete'],
                events: ['view', 'add', 'change', 'delete'],
                management_membershipplan: ['view', 'add', 'change', 'delete'],
                management_dietplan: ['view', 'add', 'change', 'delete'],
                management_workoutplan: ['view', 'add', 'change', 'delete'],
                settings: ['view', 'change']
            }
        },
        'manager': {
            name: 'Manager',
            role: 'manager',
            modules: {
                enquiry: ['view', 'add', 'change'],
                members: ['view', 'add', 'change'],
                trainers: ['view', 'add', 'change'],
                attendance: ['view', 'add', 'change'],
                billing: ['view', 'add', 'change'],
                expenses: ['view', 'add', 'change'],
                inventory: ['view', 'add', 'change'],
                events: ['view', 'add', 'change'],
                management_membershipplan: ['view', 'add', 'change'],
                management_dietplan: ['view', 'add', 'change'],
                management_workoutplan: ['view', 'add', 'change'],
                settings: ['view']
            }
        },
        'front-desk': {
            name: 'Front Desk',
            role: 'front_desk',
            modules: {
                enquiry: ['view', 'add', 'change'],
                members: ['view', 'add', 'change'],
                attendance: ['view', 'add', 'change'],
                billing: ['view', 'add'],
                events: ['view', 'add'],
                trainers: ['view'],
                management_membershipplan: ['view']
            }
        },
        'trainer': {
            name: 'Trainer',
            role: 'trainer',
            modules: {
                members: ['view'],
                trainers: ['view'],
                attendance: ['view', 'add'],
                management_dietplan: ['view', 'add', 'change'],
                management_workoutplan: ['view', 'add', 'change'],
                events: ['view']
            }
        },
        'accounts': {
            name: 'Accounts',
            role: 'accounts',
            modules: {
                billing: ['view', 'add', 'change', 'delete'],
                expenses: ['view', 'add', 'change', 'delete'],
                members: ['view'],
                management_membershipplan: ['view']
            }
        },
        'inventory': {
            name: 'Inventory',
            role: 'inventory',
            modules: {
                inventory: ['view', 'add', 'change', 'delete'],
                expenses: ['view', 'add']
            }
        },
        'marketing': {
            name: 'Marketing',
            role: 'marketing',
            modules: {
                enquiry: ['view', 'add', 'change', 'delete'],
                events: ['view', 'add', 'change'],
                members: ['view']
            }
        },
        'view-only': {
            name: 'View Only',
            matchAll: ['view'],
            role: null
        },
        'clear-all': {
            name: 'Clear All',
            matchAll: [],
            role: null
        }
    };

    let activePresetKey = null;

    /**
     * Initializes the sub-admin page components
     */
    function init() {
        setupRoleSelect();
        setupPresetButtons();
        setupColumnHeaders();
        setupRowSwitches();
        setupSearchFilter();
        setupPasswordTools();
        setupPhotoReset();
        setupFormValidation();

        // Initial sync of UI states
        syncAllUIStates();

        // Check if permissions need auto-initialization (e.g. create mode)
        handleInitialRoleSetup();
    }

    /**
     * Get unique key for a table row (e.g. 'enquiry' or 'management_membershipplan')
     */
    function getRowKey(row) {
        const app = row.dataset.app || '';
        const model = row.dataset.model || '';
        return model ? `${app}_${model}` : app;
    }

    /**
     * Handles changes to the Designated Role dropdown
     */
    function setupRoleSelect() {
        const roleSelect = document.getElementById('id_role_select');
        if (!roleSelect) return;

        roleSelect.addEventListener('change', function () {
            const role = this.value;
            applyRole(role, true);
        });
    }

    /**
     * Apply role metadata preview and corresponding permissions preset
     */
    function applyRole(role, autoApplyPermissions = true) {
        updateRoleBadgeAndDesc(role);

        if (!role) {
            updatePresetIndicator(null);
            clearActivePresetButtons();
            return;
        }

        const config = ROLE_CONFIG[role];
        if (config && config.preset) {
            if (autoApplyPermissions) {
                applyPreset(config.preset, false); // Don't re-trigger role select update
            } else {
                highlightPresetButton(config.preset);
            }
        }
    }

    /**
     * Update dynamic role preview badge and description
     */
    function updateRoleBadgeAndDesc(role) {
        const badgeEl = document.getElementById('role-badge-preview');
        const descEl = document.getElementById('role-desc-preview');
        if (!badgeEl || !descEl) return;

        const config = ROLE_CONFIG[role];
        if (config) {
            badgeEl.className = `role-badge-preview ${config.badgeClass} mt-2`;
            badgeEl.innerHTML = `<i class="mdi ${config.icon}"></i> ${config.title}`;
            badgeEl.style.display = 'inline-flex';
            descEl.textContent = config.desc;
        } else {
            badgeEl.style.display = 'none';
            descEl.textContent = 'Select a designated operational staff role for this account.';
        }
    }

    /**
     * Setup preset toolbar buttons
     */
    function setupPresetButtons() {
        const presetButtons = document.querySelectorAll('.btn-preset');
        presetButtons.forEach(btn => {
            btn.addEventListener('click', function () {
                const presetKey = this.dataset.preset;
                if (!presetKey) return;
                applyPreset(presetKey, true);
            });
        });
    }

    /**
     * Applies a permission preset across all rows in the matrix
     */
    function applyPreset(presetKey, syncRoleDropdown = true) {
        const preset = PRESET_DEFINITIONS[presetKey];
        if (!preset) return;

        activePresetKey = presetKey;
        const rows = document.querySelectorAll('#perm-matrix-table tbody tr');

        rows.forEach(row => {
            // Ignore search empty row if present
            if (row.classList.contains('perm-empty-search-row')) return;

            const rowKey = getRowKey(row);
            let allowedActions = [];

            if (preset.matchAll !== undefined) {
                allowedActions = preset.matchAll;
            } else if (preset.modules && preset.modules[rowKey]) {
                allowedActions = preset.modules[rowKey];
            }

            setRowPermission(row, 'view', allowedActions.includes('view'));
            setRowPermission(row, 'add', allowedActions.includes('add'));
            setRowPermission(row, 'change', allowedActions.includes('change'));
            setRowPermission(row, 'delete', allowedActions.includes('delete'));
        });

        // Sync role dropdown if preset specifies a role and user requested sync
        if (syncRoleDropdown && preset.role) {
            const roleSelect = document.getElementById('id_role_select');
            if (roleSelect && roleSelect.value !== preset.role) {
                roleSelect.value = preset.role;
                updateRoleBadgeAndDesc(preset.role);
            }
        }

        // Highlight preset button
        highlightPresetButton(presetKey);

        // Update indicator & counters
        updatePresetIndicator(preset.name);
        syncAllUIStates();
    }

    /**
     * Sets checked state on a specific permission checkbox in a row
     */
    function setRowPermission(row, permType, isChecked) {
        const checkbox = row.querySelector(`.perm-checkbox.${permType}-perm`);
        if (checkbox) {
            checkbox.checked = isChecked;
        }
    }

    /**
     * Highlight the active preset button
     */
    function highlightPresetButton(presetKey) {
        const presetButtons = document.querySelectorAll('.btn-preset');
        presetButtons.forEach(btn => {
            if (btn.dataset.preset === presetKey) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    /**
     * Clear active highlight from all preset buttons
     */
    function clearActivePresetButtons() {
        const presetButtons = document.querySelectorAll('.btn-preset');
        presetButtons.forEach(btn => btn.classList.remove('active'));
    }

    /**
     * Update the "Preset Applied" indicator
     */
    function updatePresetIndicator(presetName, isCustomized = false) {
        const indicator = document.getElementById('preset-applied-indicator');
        const nameEl = document.getElementById('preset-applied-name');
        if (!indicator || !nameEl) return;

        if (!presetName) {
            indicator.style.display = 'none';
            return;
        }

        indicator.style.display = 'inline-flex';
        nameEl.textContent = presetName;

        if (isCustomized) {
            indicator.innerHTML = `<i class="mdi mdi-tune-variant me-1"></i> Preset: <strong id="preset-applied-name">${presetName}</strong> <span class="ms-1 text-muted">(Customized)</span>`;
        } else {
            indicator.innerHTML = `<i class="mdi mdi-check-circle-outline me-1"></i> Preset Applied: <strong id="preset-applied-name">${presetName}</strong> (Customizable)`;
        }
    }

    /**
     * Setup column Select-All checkboxes in table headers
     */
    function setupColumnHeaders() {
        const cols = ['view', 'add', 'change', 'delete'];

        cols.forEach(col => {
            const headerCheckbox = document.getElementById(`select-all-${col}`);
            if (!headerCheckbox) return;

            headerCheckbox.addEventListener('change', function () {
                const isChecked = this.checked;
                const checkboxes = document.querySelectorAll(`.perm-checkbox.${col}-perm`);
                checkboxes.forEach(cb => {
                    cb.checked = isChecked;
                });

                markPresetCustomized();
                syncAllUIStates();
            });
        });

        // Listen for individual checkbox changes anywhere in the matrix
        const table = document.getElementById('perm-matrix-table');
        if (table) {
            table.addEventListener('change', function (e) {
                if (e.target.classList.contains('perm-checkbox')) {
                    markPresetCustomized();
                    syncAllUIStates();
                }
            });
        }
    }

    /**
     * Setup row switch buttons ("Select All" / "Deselect All" per row)
     */
    function setupRowSwitches() {
        const table = document.getElementById('perm-matrix-table');
        if (!table) return;

        table.addEventListener('click', function (e) {
            const btn = e.target.closest('.row-switch-btn');
            if (!btn) return;

            const row = btn.closest('tr');
            if (!row) return;

            const rowCheckboxes = row.querySelectorAll('.perm-checkbox');
            if (!rowCheckboxes.length) return;

            const allChecked = Array.from(rowCheckboxes).every(cb => cb.checked);
            const targetState = !allChecked;

            rowCheckboxes.forEach(cb => {
                cb.checked = targetState;
            });

            markPresetCustomized();
            syncAllUIStates();
        });
    }

    /**
     * Marks the current preset as customized when checkboxes are manually toggled
     */
    function markPresetCustomized() {
        if (activePresetKey && PRESET_DEFINITIONS[activePresetKey]) {
            updatePresetIndicator(PRESET_DEFINITIONS[activePresetKey].name, true);
        }
    }

    /**
     * Synchronize all UI indicators: counts, headers, and row buttons
     */
    function syncAllUIStates() {
        updateSelectedCounter();
        syncColumnHeaders();
        syncRowButtons();
    }

    /**
     * Update the live selected permissions count badge
     */
    function updateSelectedCounter() {
        const counterEl = document.getElementById('selected-perm-count');
        if (!counterEl) return;

        const totalSelected = document.querySelectorAll('.perm-checkbox:checked').length;
        const totalPossible = document.querySelectorAll('.perm-checkbox').length;

        if (totalPossible > 0 && totalSelected === totalPossible) {
            counterEl.textContent = `All Permissions Selected (${totalSelected})`;
            counterEl.className = 'badge badge-soft-success px-3 py-2';
        } else if (totalSelected > 0) {
            counterEl.textContent = `${totalSelected} Permission${totalSelected === 1 ? '' : 's'} Selected`;
            counterEl.className = 'badge badge-soft-primary px-3 py-2';
        } else {
            counterEl.textContent = '0 Permissions Selected';
            counterEl.className = 'badge badge-soft-secondary px-3 py-2';
        }
    }

    /**
     * Sync column headers checked / indeterminate states
     */
    function syncColumnHeaders() {
        const cols = ['view', 'add', 'change', 'delete'];

        cols.forEach(col => {
            const headerCheckbox = document.getElementById(`select-all-${col}`);
            if (!headerCheckbox) return;

            const checkboxes = Array.from(document.querySelectorAll(`.perm-checkbox.${col}-perm`));
            if (!checkboxes.length) {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = false;
                return;
            }

            const checkedCount = checkboxes.filter(cb => cb.checked).length;

            if (checkedCount === 0) {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = false;
            } else if (checkedCount === checkboxes.length) {
                headerCheckbox.checked = true;
                headerCheckbox.indeterminate = false;
            } else {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = true;
            }
        });
    }

    /**
     * Sync all row button texts and active styles
     */
    function syncRowButtons() {
        const rows = document.querySelectorAll('#perm-matrix-table tbody tr');
        rows.forEach(row => {
            const btn = row.querySelector('.row-switch-btn');
            if (!btn) return;

            const rowCheckboxes = row.querySelectorAll('.perm-checkbox');
            if (!rowCheckboxes.length) return;

            const allChecked = Array.from(rowCheckboxes).every(cb => cb.checked);
            if (allChecked) {
                btn.textContent = 'Deselect All';
                btn.classList.add('active');
            } else {
                btn.textContent = 'Select All';
                btn.classList.remove('active');
            }
        });
    }

    /**
     * Setup search and filter input for modules
     */
    function setupSearchFilter() {
        const searchInput = document.getElementById('perm-search-input');
        const permTable = document.getElementById('perm-matrix-table');
        if (!searchInput || !permTable) return;

        searchInput.addEventListener('input', function () {
            const q = this.value.trim().toLowerCase();
            const rows = permTable.querySelectorAll('tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                if (row.classList.contains('perm-empty-search-row')) return;

                const title = row.querySelector('.perm-module-title')?.textContent.toLowerCase() || '';
                const desc = row.querySelector('.perm-module-desc')?.textContent.toLowerCase() || '';
                const app = row.dataset.app?.toLowerCase() || '';
                const model = row.dataset.model?.toLowerCase() || '';

                const matches = !q || title.includes(q) || desc.includes(q) || app.includes(q) || model.includes(q);
                row.style.display = matches ? '' : 'none';
                if (matches) visibleCount++;
            });

            // Handle empty state row
            let emptyRow = permTable.querySelector('.perm-empty-search-row');
            if (visibleCount === 0) {
                if (!emptyRow) {
                    emptyRow = document.createElement('tr');
                    emptyRow.className = 'perm-empty-search-row';
                    emptyRow.innerHTML = `<td colspan="6" class="text-center py-4 text-muted"><i class="mdi mdi-magnify me-1"></i> No matching gym modules found for "<strong>${q}</strong>".</td>`;
                    permTable.querySelector('tbody').appendChild(emptyRow);
                } else {
                    emptyRow.style.display = '';
                    emptyRow.querySelector('td').innerHTML = `<i class="mdi mdi-magnify me-1"></i> No matching gym modules found for "<strong>${q}</strong>".`;
                }
            } else if (emptyRow) {
                emptyRow.style.display = 'none';
            }
        });
    }

    /**
     * Setup password visibility toggles, strength meter, and match validation
     */
    function setupPasswordTools() {
        setupPasswordToggle('toggle-password-btn', 'id_password');
        setupPasswordToggle('toggle-confirm-password-btn', 'id_confirm_password');

        const pwdInput = document.getElementById('id_password');
        const confirmPwdInput = document.getElementById('id_confirm_password');

        if (pwdInput) {
            pwdInput.addEventListener('input', function () {
                updatePasswordStrength(this.value);
                checkPasswordMatch();
            });
        }

        if (confirmPwdInput) {
            confirmPwdInput.addEventListener('input', function () {
                checkPasswordMatch();
            });
        }
    }

    /**
     * Helper for password visibility toggling
     */
    function setupPasswordToggle(btnId, inputId) {
        const btn = document.getElementById(btnId);
        const input = document.getElementById(inputId);
        if (!btn || !input) return;

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            const icon = btn.querySelector('i');
            if (icon) {
                icon.className = isPassword ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline';
            }
        });
    }

    /**
     * Password strength meter algorithm
     */
    function updatePasswordStrength(password) {
        const textEl = document.getElementById('password-meter-text');
        const segments = document.querySelectorAll('.meter-segment');
        if (!segments.length) return;

        if (!password) {
            segments.forEach(s => s.style.background = '#e2e8f0');
            if (textEl) {
                textEl.textContent = 'Enter password';
                textEl.style.color = '#64748b';
            }
            return;
        }

        let score = 0;
        if (password.length >= 6) score++;
        if (password.length >= 8) score++;
        if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
        if (/[0-9]/.test(password) && /[^A-Za-z0-9]/.test(password)) score++;

        const colors = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981'];
        const labels = ['Too Weak', 'Fair', 'Good', 'Strong'];

        segments.forEach((seg, idx) => {
            seg.style.background = idx < score ? colors[score - 1] : '#e2e8f0';
        });

        if (textEl) {
            textEl.textContent = labels[score - 1] || 'Weak';
            textEl.style.color = colors[score - 1] || '#ef4444';
        }
    }

    /**
     * Verify that password and confirm password match
     */
    function checkPasswordMatch() {
        const pwd = document.getElementById('id_password');
        const confirmPwd = document.getElementById('id_confirm_password');
        const hint = document.getElementById('password-match-hint');
        if (!confirmPwd || !hint) return;

        const val1 = pwd ? pwd.value : '';
        const val2 = confirmPwd.value;

        if (!val2) {
            hint.innerHTML = '';
            return;
        }

        if (val1 === val2) {
            hint.innerHTML = '<span class="text-success small"><i class="mdi mdi-check-circle-outline"></i> Passwords match</span>';
        } else {
            hint.innerHTML = '<span class="text-danger small"><i class="mdi mdi-close-circle-outline"></i> Passwords do not match</span>';
        }
    }

    /**
     * Setup Photo Reset button
     */
    function setupPhotoReset() {
        const resetBtn = document.getElementById('reset-photo-btn');
        const photoInput = document.getElementById('id_photo');
        const previewBox = document.getElementById('preview_id_photo');
        const avatarImg = document.getElementById('avatar-img-preview');

        if (resetBtn && photoInput && avatarImg) {
            resetBtn.addEventListener('click', function (e) {
                e.preventDefault();
                photoInput.value = '';
                const defaultAvatar = previewBox?.dataset.defaultAvatar || '';
                if (defaultAvatar) {
                    avatarImg.src = defaultAvatar;
                }
            });
        }
    }

    /**
     * Robust client-side validation before form submission
     */
    function setupFormValidation() {
        const form = document.getElementById('subadmin-form');
        if (!form) return;

        form.addEventListener('submit', function (e) {
            const pwd = document.getElementById('id_password');
            const confirmPwd = document.getElementById('id_confirm_password');

            if (pwd && confirmPwd) {
                if (pwd.value && pwd.value !== confirmPwd.value) {
                    e.preventDefault();
                    if (window.Swal) {
                        Swal.fire({
                            icon: 'error',
                            title: 'Password Mismatch',
                            text: 'Account password and confirm password do not match. Please verify.'
                        });
                    } else {
                        alert('Account password and confirm password do not match. Please verify.');
                    }
                    confirmPwd.focus();
                    return false;
                }
            }

            const checkedPerms = document.querySelectorAll('.perm-checkbox:checked');
            if (checkedPerms.length === 0) {
                // If no permissions are selected, warn user
                const allowEmpty = confirm('No module permissions are selected for this sub-admin. They will not be able to access operational modules. Do you wish to proceed?');
                if (!allowEmpty) {
                    e.preventDefault();
                    return false;
                }
            }

            // Provide visual submit feedback
            const submitBtn = document.getElementById('submit-subadmin-btn');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Saving Sub-Admin...';
            }
        });
    }

    /**
     * Handle initial role setup on page load
     */
    function handleInitialRoleSetup() {
        const roleSelect = document.getElementById('id_role_select');
        if (!roleSelect) return;

        const currentRole = roleSelect.value;
        const checkedCount = document.querySelectorAll('.perm-checkbox:checked').length;

        if (currentRole) {
            updateRoleBadgeAndDesc(currentRole);

            // If no permissions are checked yet (e.g. creating new sub-admin with default 'subadmin' selected),
            // auto-select the privileges for this role!
            if (checkedCount === 0) {
                applyRole(currentRole, true);
            } else {
                // Permissions already exist (e.g. edit mode). Just sync the preset button highlight if matching.
                const config = ROLE_CONFIG[currentRole];
                if (config && config.preset) {
                    highlightPresetButton(config.preset);
                    updatePresetIndicator(PRESET_DEFINITIONS[config.preset]?.name, false);
                }
            }
        }
    }

    // Initialize on DOMContentLoaded or immediately if already loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();