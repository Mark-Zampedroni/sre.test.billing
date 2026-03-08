/**
 * Billing Extractor Frontend
 */

const API_BASE = '/api';
let currentBillingId = null;
let connectionLost = false;

// ═══════════════════════════════════════════════════════════════════════════
// API Helper with Error Handling
// ═══════════════════════════════════════════════════════════════════════════

async function apiCall(url, options = {}) {
    try {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            if (resp.status >= 500) {
                showToast(`Server Error (${resp.status})`, 'error');
                throw new Error(`Server error: ${resp.status}`);
            }
            throw new Error(`HTTP ${resp.status}`);
        }
        connectionLost = false;
        return resp;
    } catch (e) {
        if (e.name === 'TypeError' || e.message.includes('fetch')) {
            showToast('Connection failed', 'error');
        } else if (e.message.includes('500') || e.message.includes('502') || e.message.includes('503')) {
            showToast('Server unavailable', 'error');
        }
        connectionLost = true;
        throw e;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initUpload();
    loadDashboard();
    startDashboardPolling();
});

// ═══════════════════════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════════════════════

function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const view = item.dataset.view;
            switchView(view);
        });
    });
}

function switchView(viewName) {
    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewName);
    });
    
    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === `view-${viewName}`);
    });
    
    // Load view data
    switch(viewName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'pending':
            loadBillings('pending');
            break;
        case 'confirmed':
            loadBillings('confirmed');
            break;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Dashboard
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
    loadStats();
    loadRecentBillings();
}

async function loadStats() {
    const container = document.getElementById('stats-container');
    
    try {
        const resp = await apiCall(`${API_BASE}/stats`);
        const data = await resp.json();
        
        container.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${data.total_billings}</div>
                <div class="stat-label">Total Uploads</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${data.pending}</div>
                <div class="stat-label">Pending Review</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${data.confirmed}</div>
                <div class="stat-label">Confirmed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">€${data.total_confirmed_amount.toLocaleString()}</div>
                <div class="stat-label">Total Confirmed</div>
            </div>
        `;
    } catch (e) {
        container.innerHTML = '<p class="error">Backend unavailable</p>';
    }
}

async function loadRecentBillings() {
    const container = document.getElementById('recent-billings');
    
    try {
        const resp = await apiCall(`${API_BASE}/billings`);
        const data = await resp.json();
        
        const recent = data.billings.slice(0, 5);
        
        if (recent.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No billings yet. Upload your first file!</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = recent.map(b => renderBillingCard(b)).join('');
    } catch (e) {
        container.innerHTML = '<p class="error">Backend unavailable</p>';
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Billings List
// ═══════════════════════════════════════════════════════════════════════════

async function loadBillings(status = null) {
    const containerId = status ? `${status}-list` : 'recent-billings';
    const container = document.getElementById(containerId);
    
    container.innerHTML = '<div class="spinner"></div>';
    
    try {
        const url = status ? `${API_BASE}/billings?status=${status}` : `${API_BASE}/billings`;
        const resp = await apiCall(url);
        const data = await resp.json();
        
        if (data.billings.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No ${status || ''} billings found</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = data.billings.map(b => renderBillingCard(b, status !== 'confirmed')).join('');
    } catch (e) {
        container.innerHTML = '<p class="error">Backend unavailable</p>';
    }
}

function renderBillingCard(billing, showActions = true) {
    const amount = billing.total ? `€${billing.total.toLocaleString()}` : '—';
    const statusClass = {
        'confirmed': 'confirmed',
        'pending': 'pending', 
        'processing': 'processing',
        'error': 'error'
    }[billing.status] || 'pending';
    
    const isProcessing = billing.status === 'processing';
    const isError = billing.status === 'error';
    
    return `
        <div class="billing-card ${isProcessing ? 'processing' : ''} ${isError ? 'error' : ''}">
            <div class="billing-info">
                <div class="billing-vendor">
                    ${isProcessing ? 'Processing...' : (billing.vendor || 'Unknown Vendor')}
                    <span class="file-type-badge">${billing.file_type}</span>
                </div>
                <div class="billing-meta">
                    <span>${billing.date || (isProcessing ? 'Processing...' : 'No date')}</span>
                    <span>${billing.filename}</span>
                    <span class="status-badge ${statusClass}">${billing.status}</span>
                </div>
                ${isError ? `<div class="error-message">${billing.error_message || 'Processing failed'}</div>` : ''}
            </div>
            <div class="billing-amount">${isProcessing ? '...' : amount}</div>
            <div class="billing-actions">
                ${isProcessing ? `
                    <span class="processing-spinner"></span>
                ` : isError ? `
                    <button class="btn btn-secondary btn-sm" onclick="retryBilling('${billing.id}')">
                        Retry
                    </button>
                ` : billing.status === 'pending' ? `
                    <button class="btn btn-secondary btn-sm" onclick="editBilling('${billing.id}')">
                        Edit
                    </button>
                ` : `
                    <button class="btn btn-secondary btn-sm" onclick="viewBilling('${billing.id}')">
                        View
                    </button>
                `}
                <button class="btn btn-danger btn-sm" onclick="deleteBilling('${billing.id}')">
                    Delete
                </button>
            </div>
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════════════════
// Upload
// ═══════════════════════════════════════════════════════════════════════════

function initUpload() {
    const zone = document.getElementById('upload-zone');
    const input = document.getElementById('file-input');
    
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });
    
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    
    input.addEventListener('change', () => {
        handleFiles(input.files);
        input.value = '';
    });
}

async function handleFiles(files) {
    const progress = document.getElementById('upload-progress');
    progress.classList.remove('hidden');
    
    for (const file of files) {
        progress.innerHTML = `
            <div class="spinner"></div>
            <p style="text-align: center; margin-top: 1rem;">Uploading ${file.name}...</p>
        `;
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const resp = await apiCall(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });
            
            const data = await resp.json();
            
            showToast(`${file.name} uploaded, processing...`, 'success');
            
        } catch (e) {
            showToast(`Error: ${e.message}`, 'error');
        }
    }
    
    progress.classList.add('hidden');
    
    // Redirect to dashboard to show processing files
    switchView('dashboard');
    loadStats();
    loadRecentBillings();
}

// ═══════════════════════════════════════════════════════════════════════════
// Periodic Dashboard Refresh
// ═══════════════════════════════════════════════════════════════════════════

let lastBillingStates = {};
let dashboardPollInterval = null;

function startDashboardPolling() {
    if (dashboardPollInterval) return;
    dashboardPollInterval = setInterval(refreshDashboardIfChanged, 2000);
}

function stopDashboardPolling() {
    if (dashboardPollInterval) {
        clearInterval(dashboardPollInterval);
        dashboardPollInterval = null;
    }
}

async function refreshDashboardIfChanged() {
    // Only poll if dashboard is visible
    const dashboardView = document.getElementById('view-dashboard');
    if (!dashboardView.classList.contains('active')) return;
    
    try {
        const resp = await apiCall(`${API_BASE}/billings`);
        const data = await resp.json();
        let hasChanges = false;
        
        // Check for state changes
        for (const billing of data.billings) {
            const prevState = lastBillingStates[billing.id];
            if (prevState && prevState !== billing.status) {
                hasChanges = true;
            }
            lastBillingStates[billing.id] = billing.status;
        }
        
        // Also refresh if we have processing items
        const hasProcessing = data.billings.some(b => b.status === 'processing');
        
        if (hasChanges || hasProcessing) {
            loadStats();
            loadRecentBillings();
        }
    } catch (e) {
        // Error already shown by apiCall
        console.error('Dashboard poll error:', e);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Edit Modal
// ═══════════════════════════════════════════════════════════════════════════

async function editBilling(id) {
    currentBillingId = id;
    const modal = document.getElementById('edit-modal');
    const container = document.getElementById('edit-form-container');
    
    modal.classList.add('active');
    container.innerHTML = '<div class="spinner"></div>';
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${id}`);
        const billing = await resp.json();
        
        container.innerHTML = `
            <form id="edit-form">
                <div class="form-row">
                    <div class="form-group">
                        <label>Vendor</label>
                        <input type="text" name="vendor" value="${billing.vendor || ''}">
                    </div>
                    <div class="form-group">
                        <label>Invoice Number</label>
                        <input type="text" name="invoice_number" value="${billing.invoice_number || ''}">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Date</label>
                        <input type="text" name="date" value="${billing.date || ''}">
                    </div>
                    <div class="form-group">
                        <label>Due Date</label>
                        <input type="text" name="due_date" value="${billing.due_date || ''}">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Subtotal</label>
                        <input type="number" step="0.01" name="subtotal" value="${billing.subtotal || ''}">
                    </div>
                    <div class="form-group">
                        <label>Tax</label>
                        <input type="number" step="0.01" name="tax" value="${billing.tax || ''}">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Total</label>
                        <input type="number" step="0.01" name="total" value="${billing.total || ''}">
                    </div>
                    <div class="form-group">
                        <label>Currency</label>
                        <select name="currency">
                            <option value="EUR" ${billing.currency === 'EUR' ? 'selected' : ''}>EUR</option>
                            <option value="USD" ${billing.currency === 'USD' ? 'selected' : ''}>USD</option>
                            <option value="GBP" ${billing.currency === 'GBP' ? 'selected' : ''}>GBP</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Extracted Text (readonly)</label>
                    <textarea name="raw_text" rows="6" readonly style="opacity: 0.7;">${billing.raw_text || ''}</textarea>
                </div>
            </form>
        `;
    } catch (e) {
        container.innerHTML = '<p class="error">Failed to load billing</p>';
    }
}

async function viewBilling(id) {
    currentBillingId = id;
    const modal = document.getElementById('edit-modal');
    const container = document.getElementById('edit-form-container');
    
    modal.classList.add('active');
    container.innerHTML = '<div class="spinner"></div>';
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${id}`);
        const billing = await resp.json();
        
        container.innerHTML = `
            <div class="billing-detail">
                <div class="form-row">
                    <div class="form-group">
                        <label>Vendor</label>
                        <p style="color: var(--text);">${billing.vendor || '—'}</p>
                    </div>
                    <div class="form-group">
                        <label>Invoice Number</label>
                        <p style="color: var(--text);">${billing.invoice_number || '—'}</p>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Date</label>
                        <p style="color: var(--text);">${billing.date || '—'}</p>
                    </div>
                    <div class="form-group">
                        <label>Total</label>
                        <p style="color: var(--success); font-size: 1.25rem; font-weight: bold;">
                            ${billing.currency} ${billing.total?.toLocaleString() || '—'}
                        </p>
                    </div>
                </div>
            </div>
        `;
        
        // Hide edit buttons for view mode
        document.querySelector('.modal-footer').innerHTML = `
            <button class="btn btn-secondary" onclick="closeModal()">Close</button>
        `;
    } catch (e) {
        container.innerHTML = '<p class="error">Failed to load billing</p>';
    }
}

function closeModal() {
    document.getElementById('edit-modal').classList.remove('active');
    currentBillingId = null;
    
    // Restore footer buttons
    document.querySelector('.modal-footer').innerHTML = `
        <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button class="btn btn-danger" onclick="rejectBilling()">Reject</button>
        <button class="btn btn-primary" onclick="saveBilling()">Save</button>
        <button class="btn btn-success" onclick="confirmBilling()">Confirm</button>
    `;
}

async function saveBilling() {
    if (!currentBillingId) return;
    
    const form = document.getElementById('edit-form');
    const formData = new FormData(form);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        if (key === 'raw_text') continue;
        if (value !== '') {
            if (['subtotal', 'tax', 'total'].includes(key)) {
                data[key] = parseFloat(value);
            } else {
                data[key] = value;
            }
        }
    }
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${currentBillingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!resp.ok) throw new Error('Failed to save');
        
        showToast('Billing saved', 'success');
        loadDashboard();
    } catch (e) {
        showToast('Failed to save', 'error');
    }
}

async function confirmBilling() {
    if (!currentBillingId) return;
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${currentBillingId}/confirm`, {
            method: 'POST'
        });
        
        if (!resp.ok) throw new Error('Failed to confirm');
        
        showToast('Billing confirmed!', 'success');
        closeModal();
        loadDashboard();
        loadBillings('pending');
    } catch (e) {
        showToast('Failed to confirm', 'error');
    }
}

async function rejectBilling() {
    if (!currentBillingId) return;
    
    if (!confirm('Reject this billing?')) return;
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${currentBillingId}/reject`, {
            method: 'POST'
        });
        
        if (!resp.ok) throw new Error('Failed to reject');
        
        showToast('Billing rejected', 'success');
        closeModal();
        loadDashboard();
        loadBillings('pending');
    } catch (e) {
        showToast('Failed to reject', 'error');
    }
}

async function deleteBilling(id) {
    if (!confirm('Delete this billing?')) return;
    
    try {
        const resp = await fetch(`${API_BASE}/billings/${id}`, {
            method: 'DELETE'
        });
        
        if (!resp.ok) throw new Error('Failed to delete');
        
        showToast('Billing deleted', 'success');
        loadDashboard();
        loadBillings('pending');
        loadBillings('confirmed');
    } catch (e) {
        showToast('Failed to delete', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Toast
// ═══════════════════════════════════════════════════════════════════════════

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    
    // Error toasts stay longer and shake
    const duration = type === 'error' ? 5000 : 3000;
    if (type === 'error') {
        toast.style.animation = 'shake 0.5s ease-in-out';
        setTimeout(() => { toast.style.animation = ''; }, 500);
    }
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

// Add shake animation for errors
if (!document.getElementById('toast-shake-style')) {
    const style = document.createElement('style');
    style.id = 'toast-shake-style';
    style.textContent = `
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
            20%, 40%, 60%, 80% { transform: translateX(5px); }
        }
    `;
    document.head.appendChild(style);
}

// Close modal on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// Close modal on overlay click
document.querySelector('.modal-overlay')?.addEventListener('click', closeModal);
