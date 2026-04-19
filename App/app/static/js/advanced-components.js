/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║            PROCUREAPP - ADVANCED COMPONENTS UTILITIES v1.0               ║
 * ║                    Modal, Toast, and Helper Functions                     ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

// ═════════════════════════════════════════════════════════════════════════
// 1. MODAL MANAGER
// ═════════════════════════════════════════════════════════════════════════

const ModalManager = {
  activeModals: [],

  /**
   * Open a modal dialog
   * @param {Object} options - Modal options
   * @param {string} options.title - Modal title
   * @param {string} options.content - HTML content or text
   * @param {string} options.type - 'success', 'danger', 'warning', 'info', 'default'
   * @param {boolean} options.centered - Center modal on screen
   * @param {Array} options.buttons - Array of button objects
   * @param {Function} options.onClose - Callback when modal closes
   */
  open: function(options = {}) {
    const {
      title = 'Dialog',
      content = '',
      type = 'default',
      centered = true,
      buttons = [],
      onClose = null,
      size = 'md' // sm, md, lg
    } = options;

    // Create modal backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop show';
    backdrop.id = `modal-backdrop-${Date.now()}`;

    // Create modal content
    const modal = document.createElement('div');
    modal.className = `modal-content modal-${size}`;
    if (type !== 'default') {
      modal.classList.add(`modal-${type}`);
    }

    // Modal header
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `
      <h5>${title}</h5>
      <button type="button" class="btn-close" aria-label="Close">×</button>
    `;

    // Modal body
    const body = document.createElement('div');
    body.className = 'modal-body';
    body.innerHTML = content;

    // Modal footer with buttons
    const footer = document.createElement('div');
    footer.className = 'modal-footer';
    
    buttons.forEach(btn => {
      const button = document.createElement('button');
      button.className = `btn ${btn.className || 'btn-secondary'}`;
      button.textContent = btn.text;
      button.onclick = (e) => {
        e.preventDefault();
        if (btn.action) btn.action();
        ModalManager.close(backdrop.id);
      };
      footer.appendChild(button);
    });

    // Assemble modal
    modal.appendChild(header);
    modal.appendChild(body);
    if (buttons.length > 0) {
      modal.appendChild(footer);
    }
    backdrop.appendChild(modal);

    // Add to DOM
    document.body.appendChild(backdrop);
    this.activeModals.push(backdrop.id);

    // Close button handler
    header.querySelector('.btn-close').onclick = () => {
      ModalManager.close(backdrop.id);
    };

    // Backdrop click to close
    backdrop.onclick = (e) => {
      if (e.target === backdrop) {
        ModalManager.close(backdrop.id);
      }
    };

    // Keyboard escape to close
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        ModalManager.close(backdrop.id);
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);

    // On close callback
    if (onClose) {
      backdrop.onClose = onClose;
    }

    return backdrop.id;
  },

  /**
   * Close a modal
   * @param {string} id - Modal backdrop ID
   */
  close: function(id) {
    const backdrop = document.getElementById(id);
    if (backdrop) {
      backdrop.classList.remove('show');
      setTimeout(() => {
        backdrop.remove();
        if (backdrop.onClose) backdrop.onClose();
      }, 200);
      this.activeModals = this.activeModals.filter(m => m !== id);
    }
  },

  /**
   * Close all open modals
   */
  closeAll: function() {
    const modals = [...this.activeModals];
    modals.forEach(id => this.close(id));
  },

  /**
   * Confirmation dialog
   */
  confirm: function(options = {}) {
    const {
      title = 'Confirm',
      message = 'Are you sure?',
      confirmText = 'Confirm',
      cancelText = 'Cancel',
      onConfirm = null,
      onCancel = null,
      type = 'warning'
    } = options;

    return this.open({
      title: title,
      content: `<p class="modal-description">${message}</p>`,
      type: type,
      size: 'sm',
      buttons: [
        {
          text: cancelText,
          className: 'btn-outline-secondary',
          action: onCancel
        },
        {
          text: confirmText,
          className: 'btn-danger',
          action: onConfirm
        }
      ]
    });
  },

  /**
   * Alert dialog
   */
  alert: function(options = {}) {
    const {
      title = 'Alert',
      message = '',
      buttonText = 'OK',
      type = 'info'
    } = options;

    return this.open({
      title: title,
      content: `<p>${message}</p>`,
      type: type,
      size: 'sm',
      buttons: [
        {
          text: buttonText,
          className: 'btn-primary',
          action: null
        }
      ]
    });
  },

  /**
   * Delete confirmation dialog
   */
  delete: function(options = {}) {
    const {
      title = 'Delete Item',
      message = 'This action cannot be undone.',
      itemName = '',
      onDelete = null
    } = options;

    const content = `
      <div class="modal-icon danger">
        <i class="bi bi-trash-fill"></i>
      </div>
      <p class="text-center mb-0">${message}</p>
      ${itemName ? `<p class="text-center text-danger fw-bold">${itemName}</p>` : ''}
    `;

    return this.open({
      title: title,
      content: content,
      type: 'danger',
      size: 'sm',
      buttons: [
        {
          text: 'Cancel',
          className: 'btn-outline-secondary',
          action: null
        },
        {
          text: 'Delete',
          className: 'btn-danger',
          action: onDelete
        }
      ]
    });
  }
};

// ═════════════════════════════════════════════════════════════════════════
// 2. TOAST NOTIFICATION MANAGER
// ═════════════════════════════════════════════════════════════════════════

const ToastManager = {
  toasts: [],
  container: null,

  /**
   * Initialize toast container
   */
  init: function() {
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  /**
   * Show a toast notification
   * @param {Object} options - Toast options
   * @param {string} options.type - 'success', 'danger', 'warning', 'info'
   * @param {string} options.title - Toast title
   * @param {string} options.message - Toast message
   * @param {number} options.duration - Auto-dismiss duration in ms (0 = no auto-dismiss)
   */
  show: function(options = {}) {
    this.init();

    const {
      type = 'info',
      title = 'Notification',
      message = '',
      duration = 4000
    } = options;

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} show`;
    toast.innerHTML = `
      <div class="toast-icon">
        <i class="bi ${this.getIcon(type)}"></i>
      </div>
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        <div class="toast-message">${message}</div>
      </div>
      <button type="button" class="toast-close" aria-label="Close">×</button>
    `;

    // Add to container
    this.container.appendChild(toast);
    this.toasts.push(toast);

    // Close button handler
    toast.querySelector('.toast-close').onclick = () => {
      this.removeToast(toast);
    };

    // Auto-dismiss
    if (duration > 0) {
      setTimeout(() => {
        this.removeToast(toast);
      }, duration);
    }

    return toast;
  },

  /**
   * Remove a toast
   */
  removeToast: function(toast) {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => {
      toast.remove();
      this.toasts = this.toasts.filter(t => t !== toast);
    }, 300);
  },

  /**
   * Get icon class for type
   */
  getIcon: function(type) {
    const icons = {
      'success': 'bi-check-circle-fill',
      'danger': 'bi-exclamation-circle-fill',
      'warning': 'bi-exclamation-triangle-fill',
      'info': 'bi-info-circle-fill'
    };
    return icons[type] || icons['info'];
  },

  /**
   * Shorthand methods
   */
  success: function(title, message = '', duration = 4000) {
    return this.show({ type: 'success', title, message, duration });
  },

  error: function(title, message = '', duration = 4000) {
    return this.show({ type: 'danger', title, message, duration });
  },

  warning: function(title, message = '', duration = 4000) {
    return this.show({ type: 'warning', title, message, duration });
  },

  info: function(title, message = '', duration = 4000) {
    return this.show({ type: 'info', title, message, duration });
  }
};

// ═════════════════════════════════════════════════════════════════════════
// 3. LOADING STATE MANAGER
// ═════════════════════════════════════════════════════════════════════════

const LoadingManager = {
  /**
   * Show loading overlay
   * @param {string} message - Loading message
   */
  show: function(message = 'Loading...') {
    let overlay = document.getElementById('loading-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'loading-overlay';
      overlay.className = 'loading-overlay';
      overlay.innerHTML = `
        <div class="loading-overlay-content">
          <div class="loading-overlay-icon">
            <i class="bi bi-hourglass-split"></i>
          </div>
          <div class="loading-overlay-text">${message}</div>
        </div>
      `;
      document.body.appendChild(overlay);
    } else {
      overlay.querySelector('.loading-overlay-text').textContent = message;
    }
    overlay.classList.add('show');
  },

  /**
   * Hide loading overlay
   */
  hide: function() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
      overlay.classList.remove('show');
    }
  },

  /**
   * Set button loading state
   */
  setButtonLoading: function(buttonId, isLoading = true) {
    const button = document.getElementById(buttonId);
    if (button) {
      if (isLoading) {
        button.classList.add('loading');
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = '';
      } else {
        button.classList.remove('loading');
        button.disabled = false;
        button.textContent = button.dataset.originalText || 'Submit';
      }
    }
  }
};

// ═════════════════════════════════════════════════════════════════════════
// 4. ADVANCED SEARCH HELPER
// ═════════════════════════════════════════════════════════════════════════

const AdvancedSearchHelper = {
  /**
   * Build query string from form
   */
  buildQuery: function(formId) {
    const form = document.getElementById(formId);
    if (!form) return {};

    const formData = new FormData(form);
    const params = {};

    formData.forEach((value, key) => {
      if (value) {
        if (params[key]) {
          if (!Array.isArray(params[key])) {
            params[key] = [params[key]];
          }
          params[key].push(value);
        } else {
          params[key] = value;
        }
      }
    });

    return params;
  },

  /**
   * Get query string
   */
  getQueryString: function(params) {
    const query = new URLSearchParams();
    Object.keys(params).forEach(key => {
      const value = params[key];
      if (Array.isArray(value)) {
        value.forEach(v => query.append(key, v));
      } else {
        query.append(key, value);
      }
    });
    return '?' + query.toString();
  },

  /**
   * Clear search filters
   */
  clearFilters: function(formId) {
    const form = document.getElementById(formId);
    if (form) {
      form.reset();
    }
  },

  /**
   * Save search preset
   */
  savePreset: function(presetName, params) {
    const presets = JSON.parse(localStorage.getItem('searchPresets') || '{}');
    presets[presetName] = params;
    localStorage.setItem('searchPresets', JSON.stringify(presets));
    ToastManager.success('Search Preset', `Saved "${presetName}" successfully`);
  },

  /**
   * Load search preset
   */
  loadPreset: function(presetName, formId) {
    const presets = JSON.parse(localStorage.getItem('searchPresets') || '{}');
    if (presets[presetName]) {
      const form = document.getElementById(formId);
      if (form) {
        Object.keys(presets[presetName]).forEach(key => {
          const field = form.querySelector(`[name="${key}"]`);
          if (field) {
            field.value = presets[presetName][key];
          }
        });
      }
      ToastManager.success('Search Preset', `Loaded "${presetName}" successfully`);
    }
  }
};

// ═════════════════════════════════════════════════════════════════════════
// 5. FORM HELPER UTILITIES
// ═════════════════════════════════════════════════════════════════════════

const FormHelper = {
  /**
   * Validate form and show errors
   */
  validate: function(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;

    let isValid = true;
    const fields = form.querySelectorAll('[required]');

    fields.forEach(field => {
      if (!field.value.trim()) {
        field.classList.add('is-invalid');
        field.classList.remove('is-valid');
        isValid = false;
      } else {
        field.classList.add('is-valid');
        field.classList.remove('is-invalid');
      }
    });

    return isValid;
  },

  /**
   * Clear form errors
   */
  clearErrors: function(formId) {
    const form = document.getElementById(formId);
    if (form) {
      form.querySelectorAll('.is-invalid, .is-valid').forEach(field => {
        field.classList.remove('is-invalid', 'is-valid');
      });
    }
  },

  /**
   * Set field error
   */
  setError: function(fieldId, message) {
    const field = document.getElementById(fieldId);
    if (field) {
      field.classList.add('is-invalid');
      const feedback = field.nextElementSibling;
      if (feedback && feedback.classList.contains('invalid-feedback')) {
        feedback.textContent = message;
      }
    }
  },

  /**
   * Set field success
   */
  setSuccess: function(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
      field.classList.add('is-valid');
      field.classList.remove('is-invalid');
    }
  }
};

// ═════════════════════════════════════════════════════════════════════════
// 6. INITIALIZATION
// ═════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function() {
  // Initialize toast system
  ToastManager.init();

  // Handle flash messages from Flask
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    const type = alert.classList.contains('alert-success') ? 'success'
      : alert.classList.contains('alert-danger') ? 'danger'
        : alert.classList.contains('alert-warning') ? 'warning'
          : 'info';

    const title = alert.classList.contains('alert-success') ? 'Success'
      : alert.classList.contains('alert-danger') ? 'Error'
        : alert.classList.contains('alert-warning') ? 'Warning'
          : 'Information';

    const message = alert.textContent.trim();

    if (message && !alert.classList.contains('no-toast')) {
      ToastManager.show({
        type: type,
        title: title,
        message: message
      });
      alert.style.display = 'none';
    }
  });
});

// ═════════════════════════════════════════════════════════════════════════
// END OF UTILITIES
// ═════════════════════════════════════════════════════════════════════════
