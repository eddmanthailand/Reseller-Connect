/* Global Alert System */
(function() {
    // Create alert container if it doesn't exist
    function ensureAlertContainer() {
        let container = document.getElementById('globalAlertContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'globalAlertContainer';
            document.body.appendChild(container);
        }
        return container;
    }

    // Icons for different alert types
    const alertIcons = {
        success: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>`,
        error: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>`,
        warning: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>`,
        info: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="16" x2="12" y2="12"/>
            <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>`
    };

    // Close icon
    const closeIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>`;

    // Show alert function
    window.showAlert = function(message, type = 'info', duration = 4000) {
        const container = ensureAlertContainer();
        
        // Create alert element
        const alert = document.createElement('div');
        alert.className = `global-alert ${type} show`;
        
        alert.innerHTML = `
            <div class="global-alert-icon">${alertIcons[type] || alertIcons.info}</div>
            <div class="global-alert-content">
                <div class="global-alert-message">${message}</div>
            </div>
            <button class="global-alert-close">${closeIcon}</button>
        `;
        
        // Close button handler
        const closeBtn = alert.querySelector('.global-alert-close');
        closeBtn.addEventListener('click', () => hideAlert(alert));
        
        // Add to container
        container.appendChild(alert);
        
        // Auto hide after duration
        if (duration > 0) {
            setTimeout(() => hideAlert(alert), duration);
        }
        
        return alert;
    };

    // Hide alert with animation
    function hideAlert(alert) {
        if (!alert || alert.classList.contains('hiding')) return;
        
        alert.classList.add('hiding');
        setTimeout(() => {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, 300);
    }

    // Expose hideAlert globally
    window.hideAlert = hideAlert;

    // Shorthand functions
    window.showSuccess = function(message, duration) {
        return showAlert(message, 'success', duration);
    };

    window.showError = function(message, duration) {
        return showAlert(message, 'error', duration);
    };

    window.showWarning = function(message, duration) {
        return showAlert(message, 'warning', duration);
    };

    window.showInfo = function(message, duration) {
        return showAlert(message, 'info', duration);
    };

    // Alias for backward compatibility
    window.showGlobalAlert = function(message, type, duration) {
        return showAlert(message, type, duration);
    };

    // Confirm alert with callback
    window.showConfirmAlert = function(message, onConfirm, onCancel) {
        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        
        // Create confirm dialog
        const dialog = document.createElement('div');
        dialog.className = 'confirm-dialog';
        
        dialog.innerHTML = `
            <div class="confirm-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
            </div>
            <div class="confirm-message">${message}</div>
            <div class="confirm-buttons">
                <button class="confirm-btn cancel">ยกเลิก</button>
                <button class="confirm-btn confirm">ยืนยัน</button>
            </div>
        `;
        
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        
        // Show with animation
        setTimeout(() => {
            overlay.classList.add('show');
        }, 10);
        
        // Handle buttons
        const confirmBtn = dialog.querySelector('.confirm-btn.confirm');
        const cancelBtn = dialog.querySelector('.confirm-btn.cancel');
        
        function closeDialog() {
            overlay.classList.remove('show');
            setTimeout(() => {
                if (overlay.parentNode) {
                    overlay.parentNode.removeChild(overlay);
                }
            }, 300);
        }
        
        confirmBtn.addEventListener('click', () => {
            closeDialog();
            if (typeof onConfirm === 'function') {
                onConfirm();
            }
        });
        
        cancelBtn.addEventListener('click', () => {
            closeDialog();
            if (typeof onCancel === 'function') {
                onCancel();
            }
        });
        
        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeDialog();
                if (typeof onCancel === 'function') {
                    onCancel();
                }
            }
        });
    };
})();
