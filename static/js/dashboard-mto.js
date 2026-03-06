// ==================== ACTIVITY LOGS FUNCTIONS ====================

let activityLogPage = 1;
let activityLogSearchTimeout = null;

async function loadActivityLogs(page = 1) {
    activityLogPage = page;
    const container = document.getElementById('activityLogsTableBody');
    if (!container) return;
    
    container.innerHTML = '<tr><td colspan="7" style="text-align: center;">กำลังโหลด...</td></tr>';
    
    const category = document.getElementById('logCategoryFilter')?.value || '';
    const dateFrom = document.getElementById('logDateFrom')?.value || '';
    const dateTo = document.getElementById('logDateTo')?.value || '';
    const search = document.getElementById('logSearchInput')?.value || '';
    
    let url = `${API_URL}/activity-logs?page=${page}&per_page=50`;
    if (category) url += `&category=${encodeURIComponent(category)}`;
    if (dateFrom) url += `&date_from=${encodeURIComponent(dateFrom)}`;
    if (dateTo) url += `&date_to=${encodeURIComponent(dateTo)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    
    try {
        const response = await fetch(url, { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to fetch logs');
        
        const data = await response.json();
        renderActivityLogs(data.logs);
        renderLogPagination(data);
    } catch (error) {
        console.error('Error loading activity logs:', error);
        container.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #ff6b6b;">เกิดข้อผิดพลาดในการโหลดข้อมูล</td></tr>';
    }
}

function renderActivityLogs(logs) {
    const container = document.getElementById('activityLogsTableBody');
    if (!container) return;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.6);">ไม่พบข้อมูล</td></tr>';
        return;
    }
    
    const categoryLabels = {
        'auth': { label: 'เข้าสู่ระบบ', color: '#4CAF50' },
        'user': { label: 'จัดการผู้ใช้', color: '#2196F3' },
        'application': { label: 'ใบสมัคร', color: '#9C27B0' },
        'product': { label: 'สินค้า', color: '#FF9800' },
        'stock': { label: 'สต็อก', color: '#00BCD4' },
        'order': { label: 'คำสั่งซื้อ', color: '#E91E63' },
        'settings': { label: 'การตั้งค่า', color: '#607D8B' }
    };
    
    const actionLabels = {
        'login': 'เข้าสู่ระบบ',
        'logout': 'ออกจากระบบ',
        'create': 'สร้าง',
        'update': 'แก้ไข',
        'delete': 'ลบ',
        'approve': 'อนุมัติ',
        'reject': 'ปฏิเสธ',
        'view': 'ดู',
        'export': 'ส่งออก',
        'import': 'นำเข้า',
        'transfer': 'โอน',
        'adjust': 'ปรับ'
    };
    
    container.innerHTML = logs.map(log => {
        const categoryInfo = categoryLabels[log.action_category] || { label: log.action_category, color: '#888' };
        const actionLabel = actionLabels[log.action_type] || log.action_type;
        const datetime = log.created_at ? new Date(log.created_at).toLocaleString('th-TH') : '-';
        
        return `
            <tr>
                <td style="font-size: 12px; white-space: nowrap;">${datetime}</td>
                <td style="font-size: 13px;">${log.user_name || 'ระบบ'}</td>
                <td><span style="padding: 3px 8px; border-radius: 12px; background: ${categoryInfo.color}20; color: ${categoryInfo.color}; font-size: 11px;">${categoryInfo.label}</span></td>
                <td style="font-size: 13px;">${actionLabel}</td>
                <td style="font-size: 13px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${log.description || ''}">${log.description || '-'}</td>
                <td style="font-size: 12px;">${log.target_name || '-'}</td>
                <td style="font-size: 11px; color: rgba(255,255,255,0.5);">${log.ip_address || '-'}</td>
            </tr>
        `;
    }).join('');
}

function renderLogPagination(data) {
    const infoEl = document.getElementById('logPaginationInfo');
    const paginationEl = document.getElementById('logPagination');
    
    if (infoEl) {
        const start = (data.page - 1) * data.per_page + 1;
        const end = Math.min(data.page * data.per_page, data.total);
        infoEl.textContent = `แสดง ${data.total > 0 ? start : 0}-${end} จาก ${data.total} รายการ`;
    }
    
    if (paginationEl) {
        let html = '';
        
        if (data.page > 1) {
            html += `<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;" onclick="loadActivityLogs(${data.page - 1})">ก่อนหน้า</button>`;
        }
        
        const startPage = Math.max(1, data.page - 2);
        const endPage = Math.min(data.total_pages, data.page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            const active = i === data.page ? 'background: rgba(255,255,255,0.3);' : '';
            html += `<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px; ${active}" onclick="loadActivityLogs(${i})">${i}</button>`;
        }
        
        if (data.page < data.total_pages) {
            html += `<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;" onclick="loadActivityLogs(${data.page + 1})">ถัดไป</button>`;
        }
        
        paginationEl.innerHTML = html;
    }
}

function debounceLogSearch() {
    if (activityLogSearchTimeout) {
        clearTimeout(activityLogSearchTimeout);
    }
    activityLogSearchTimeout = setTimeout(() => {
        loadActivityLogs(1);
    }, 500);
}

function clearLogFilters() {
    const categoryFilter = document.getElementById('logCategoryFilter');
    const dateFrom = document.getElementById('logDateFrom');
    const dateTo = document.getElementById('logDateTo');
    const searchInput = document.getElementById('logSearchInput');
    
    if (categoryFilter) categoryFilter.value = '';
    if (dateFrom) dateFrom.value = '';
    if (dateTo) dateTo.value = '';
    if (searchInput) searchInput.value = '';
    
    loadActivityLogs(1);
}

// ==========================================
// Made-to-Order (MTO) Functions
// ==========================================

let currentMtoRequestsFilter = 'all';
let currentMtoQuotationsFilter = 'all';
let currentMtoOrdersFilter = 'all';

async function loadMtoRequests(status = null) {
    const tbody = document.getElementById('mtoRequestsTableBody');
    if (!tbody) return;
    
    try {
        const url = status && status !== 'all' 
            ? `/api/admin/mto/quotation-requests?status=${status}` 
            : '/api/admin/mto/quotation-requests';
        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();
        
        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.5);">ไม่มีคำขอใบเสนอราคา</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(req => `
            <tr>
                <td><strong>${req.request_number || '-'}</strong></td>
                <td>${req.reseller_name || '-'}</td>
                <td>${req.item_count || 0} รายการ</td>
                <td>${req.total_qty || 0} ชิ้น</td>
                <td>${getMtoRequestStatusBadge(req.status)}</td>
                <td>${formatThaiDate(req.created_at)}</td>
                <td>
                    <button class="btn-icon" onclick="viewMtoRequest(${req.id})" title="ดูรายละเอียด">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    ${req.status === 'pending' ? `
                    <button class="btn-icon" style="color: #10b981;" onclick="createQuotationFromRequest(${req.id})" title="สร้างใบเสนอราคา">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18v-6"/><path d="M9 15h6"/></svg>
                    </button>` : ''}
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Error loading MTO requests:', error);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาด</td></tr>';
    }
}

function filterMtoRequests(status) {
    currentMtoRequestsFilter = status;
    document.querySelectorAll('#page-mto-requests .status-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.status === status);
    });
    loadMtoRequests(status);
}

async function loadMtoQuotations(status = null) {
    const tbody = document.getElementById('mtoQuotationsTableBody');
    if (!tbody) return;
    
    try {
        const url = status && status !== 'all' 
            ? `/api/admin/mto/quotations?status=${status}` 
            : '/api/admin/mto/quotations';
        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();
        
        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.5);">ไม่มีใบเสนอราคา</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(q => `
            <tr>
                <td><strong>${q.quote_number || '-'}</strong></td>
                <td>${q.reseller_name || '-'}</td>
                <td>฿${Number(q.total_amount || 0).toLocaleString()}</td>
                <td>฿${Number(q.deposit_amount || 0).toLocaleString()} (${q.deposit_percent}%)</td>
                <td>${getMtoQuotationStatusBadge(q.status)}</td>
                <td>${q.valid_until ? formatThaiDate(q.valid_until) : '-'}</td>
                <td>
                    <button class="btn-icon" onclick="viewMtoQuotation(${q.id})" title="ดูรายละเอียด">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    ${q.status === 'draft' ? `
                    <button class="btn-icon" style="color: #10b981;" onclick="sendMtoQuotation(${q.id})" title="ส่งใบเสนอราคา">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                    </button>` : ''}
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Error loading MTO quotations:', error);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาด</td></tr>';
    }
}

function filterMtoQuotations(status) {
    currentMtoQuotationsFilter = status;
    document.querySelectorAll('#page-mto-quotations .status-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.status === status);
    });
    loadMtoQuotations(status);
}

async function loadMtoOrders(status = null) {
    const tbody = document.getElementById('mtoOrdersTableBody');
    if (!tbody) return;
    
    try {
        const url = status && status !== 'all' 
            ? `/api/admin/mto/orders?status=${status}` 
            : '/api/admin/mto/orders';
        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();
        
        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.5);">ไม่มีคำสั่งซื้อ</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(o => `
            <tr>
                <td><strong>${o.order_number || '-'}</strong></td>
                <td>${o.reseller_name || '-'}</td>
                <td>฿${Number(o.total_amount || 0).toLocaleString()}</td>
                <td>
                    <div style="font-size: 12px;">
                        <span style="color: #10b981;">มัดจำ: ฿${Number(o.deposit_paid || 0).toLocaleString()}</span>
                        / <span style="color: rgba(255,255,255,0.8);">คงเหลือ: ฿${Number(o.balance_amount || 0).toLocaleString()}</span>
                    </div>
                </td>
                <td>${getMtoOrderStatusBadge(o.status)}</td>
                <td>${o.expected_completion_date ? formatThaiDate(o.expected_completion_date) : '-'}</td>
                <td>
                    <button class="btn-icon" onclick="viewMtoOrder(${o.id})" title="ดูรายละเอียด">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    <button class="btn-icon" style="color: #a855f7;" onclick="showMtoOrderStatusModal(${o.id}, '${o.status}')" title="อัปเดตสถานะ">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
                    </button>
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Error loading MTO orders:', error);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาด</td></tr>';
    }
}

function filterMtoOrders(status) {
    currentMtoOrdersFilter = status;
    document.querySelectorAll('#page-mto-orders .status-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.status === status);
    });
    loadMtoOrders(status);
}

async function loadMtoPayments() {
    const tbody = document.getElementById('mtoPaymentsTableBody');
    if (!tbody) return;
    
    try {
        const response = await fetch('/api/admin/mto/payments?status=pending', { credentials: 'include' });
        const data = await response.json();
        
        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.5);">ไม่มีรายการรอตรวจสอบ</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(p => `
            <tr>
                <td><strong>${p.order_number || '-'}</strong></td>
                <td>${p.reseller_name || '-'}</td>
                <td><span class="badge" style="background: ${p.payment_type === 'deposit' ? '#3b82f6' : '#f59e0b'};">${p.payment_type === 'deposit' ? 'มัดจำ' : 'ยอดเหลือ'}</span></td>
                <td>฿${Number(p.amount || 0).toLocaleString()}</td>
                <td>${p.slip_image_url ? `<a href="${p.slip_image_url}" target="_blank" style="color: #60a5fa;">ดูสลิป</a>` : '-'}</td>
                <td>${formatThaiDate(p.created_at)}</td>
                <td><button class="btn-primary" style="padding: 6px 12px; font-size: 12px;" onclick="confirmMtoPayment(${p.id})">ยืนยัน</button></td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Error loading MTO payments:', error);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาด</td></tr>';
    }
}

async function confirmMtoPayment(paymentId) {
    if (!confirm('ยืนยันการชำระเงินนี้?')) return;
    
    try {
        const response = await fetch(`/api/admin/mto/payments/${paymentId}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            credentials: 'include'
        });
        
        const result = await response.json();
        if (response.ok) {
            showAlert('success', 'ยืนยันการชำระเงินสำเร็จ');
            loadMtoPayments();
            loadMtoOrders();
        } else {
            showAlert('error', result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function sendMtoQuotation(quoteId) {
    if (!confirm('ส่งใบเสนอราคานี้ให้ Reseller?')) return;
    
    try {
        const response = await fetch(`/api/admin/mto/quotations/${quoteId}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            credentials: 'include'
        });
        
        const result = await response.json();
        if (response.ok) {
            showAlert('success', 'ส่งใบเสนอราคาสำเร็จ');
            loadMtoQuotations();
            loadMtoRequests();
        } else {
            showAlert('error', result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

function getMtoRequestStatusBadge(status) {
    const statusMap = {
        'pending': { label: 'รอดำเนินการ', color: '#f59e0b' },
        'quoted': { label: 'เสนอราคาแล้ว', color: '#10b981' },
        'cancelled': { label: 'ยกเลิก', color: '#ef4444' }
    };
    const s = statusMap[status] || { label: status, color: '#6b7280' };
    return `<span class="badge" style="background: ${s.color};">${s.label}</span>`;
}

function getMtoQuotationStatusBadge(status) {
    const statusMap = {
        'draft': { label: 'แบบร่าง', color: '#6b7280' },
        'sent': { label: 'ส่งแล้ว', color: '#3b82f6' },
        'accepted': { label: 'ยอมรับ', color: '#10b981' },
        'rejected': { label: 'ปฏิเสธ', color: '#ef4444' },
        'expired': { label: 'หมดอายุ', color: '#9ca3af' }
    };
    const s = statusMap[status] || { label: status, color: '#6b7280' };
    return `<span class="badge" style="background: ${s.color};">${s.label}</span>`;
}

function getMtoOrderStatusBadge(status) {
    const statusMap = {
        'awaiting_deposit': { label: 'รอมัดจำ', color: '#f59e0b' },
        'deposit_paid': { label: 'ชำระมัดจำแล้ว', color: '#3b82f6' },
        'production': { label: 'กำลังผลิต', color: '#8b5cf6' },
        'balance_requested': { label: 'รอชำระยอดเหลือ', color: '#f59e0b' },
        'balance_paid': { label: 'ชำระครบ', color: '#10b981' },
        'ready_to_ship': { label: 'พร้อมส่ง', color: '#06b6d4' },
        'shipped': { label: 'จัดส่งแล้ว', color: '#10b981' },
        'fulfilled': { label: 'สำเร็จ', color: '#22c55e' }
    };
    const s = statusMap[status] || { label: status, color: '#6b7280' };
    return `<span class="badge" style="background: ${s.color};">${s.label}</span>`;
}

async function viewMtoRequest(requestId) {
    try {
        const response = await fetch(`/api/admin/mto/quotation-requests/${requestId}`, { credentials: 'include' });
        const data = await response.json();
        if (!response.ok) { showAlert('error', data.error || 'เกิดข้อผิดพลาด'); return; }
        
        let itemsHtml = data.items.map(item => `
            <tr>
                <td><div style="display: flex; align-items: center; gap: 10px;">
                    ${item.image_url ? `<img src="${item.image_url}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;">` : ''}
                    <div><strong>${item.product_name}</strong>${item.sku_code ? `<br><small style="color: rgba(255,255,255,0.6);">${item.sku_code}</small>` : ''}</div>
                </div></td>
                <td>${item.quantity} ชิ้น</td>
                <td>฿${Number(item.base_price || 0).toLocaleString()}</td>
                <td>${item.production_days || 0} วัน</td>
            </tr>
        `).join('');
        
        const modalHtml = `
            <div class="modal-overlay active" id="mtoRequestModal" onclick="if(event.target===this)this.remove()">
                <div class="modal" style="max-width: 700px;">
                    <div class="modal-header"><h3>คำขอใบเสนอราคา ${data.request_number}</h3><button class="modal-close" onclick="document.getElementById('mtoRequestModal').remove()">&times;</button></div>
                    <div class="modal-body" style="max-height: 60vh; overflow-y: auto;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
                            <div><label style="color: rgba(255,255,255,0.6); font-size: 12px;">Reseller</label><p style="margin: 4px 0;"><strong>${data.reseller_name}</strong></p><p style="margin: 0; font-size: 13px;">${data.email || ''} ${data.phone || ''}</p><p style="margin: 4px 0; font-size: 13px;">ระดับ: ${data.tier_name || '-'}</p></div>
                            <div><label style="color: rgba(255,255,255,0.6); font-size: 12px;">สถานะ</label><p style="margin: 4px 0;">${getMtoRequestStatusBadge(data.status)}</p><label style="color: rgba(255,255,255,0.6); font-size: 12px; margin-top: 8px; display: block;">วันที่ขอ</label><p style="margin: 4px 0;">${formatThaiDate(data.created_at)}</p></div>
                        </div>
                        ${data.notes ? `<div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; margin-bottom: 16px;"><strong>หมายเหตุ:</strong> ${data.notes}</div>` : ''}
                        <h4 style="margin: 16px 0 8px;">รายการสินค้า</h4>
                        <table class="data-table" style="width: 100%;"><thead><tr><th>สินค้า</th><th>จำนวน</th><th>ราคา/ชิ้น</th><th>ระยะเวลาผลิต</th></tr></thead><tbody>${itemsHtml}</tbody></table>
                    </div>
                    <div class="modal-footer">
                        ${data.status === 'pending' ? `<button class="btn-primary" onclick="createQuotationFromRequest(${data.id}); document.getElementById('mtoRequestModal').remove();">สร้างใบเสนอราคา</button>` : ''}
                        <button class="btn-secondary" onclick="document.getElementById('mtoRequestModal').remove()">ปิด</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) { showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message); }
}

async function createQuotationFromRequest(requestId) {
    showAlert('info', 'ฟีเจอร์สร้างใบเสนอราคากำลังพัฒนา');
}

async function viewMtoQuotation(quoteId) {
    try {
        const response = await fetch(`/api/mto/quotations/${quoteId}`, { credentials: 'include' });
        const data = await response.json();
        if (!response.ok) { showAlert('error', data.error || 'เกิดข้อผิดพลาด'); return; }
        
        let itemsHtml = data.items.map(item => `<tr><td><div style="display: flex; align-items: center; gap: 10px;">${item.image_url ? `<img src="${item.image_url}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;">` : ''}<div><strong>${item.product_name}</strong>${item.option_text ? `<br><small style="color: rgba(255,255,255,0.6);">${item.option_text}</small>` : ''}</div></div></td><td>${item.quantity}</td><td>฿${Number(item.final_price || 0).toLocaleString()}</td><td>฿${Number(item.line_total || 0).toLocaleString()}</td></tr>`).join('');
        
        const modalHtml = `<div class="modal-overlay active" id="mtoQuoteModal" onclick="if(event.target===this)this.remove()"><div class="modal" style="max-width: 700px;"><div class="modal-header"><h3>ใบเสนอราคา ${data.quote_number}</h3><button class="modal-close" onclick="document.getElementById('mtoQuoteModal').remove()">&times;</button></div><div class="modal-body" style="max-height: 60vh; overflow-y: auto;"><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;"><div><label style="color: rgba(255,255,255,0.6); font-size: 12px;">Reseller</label><p style="margin: 4px 0;"><strong>${data.reseller_name}</strong></p></div><div><label style="color: rgba(255,255,255,0.6); font-size: 12px;">สถานะ</label><p style="margin: 4px 0;">${getMtoQuotationStatusBadge(data.status)}</p></div></div><h4 style="margin: 16px 0 8px;">รายการสินค้า</h4><table class="data-table" style="width: 100%;"><thead><tr><th>สินค้า</th><th>จำนวน</th><th>ราคา/ชิ้น</th><th>รวม</th></tr></thead><tbody>${itemsHtml}</tbody></table><div style="margin-top: 16px; text-align: right;"><p>ยอดรวม: <strong>฿${Number(data.total_amount || 0).toLocaleString()}</strong></p><p>มัดจำ (${data.deposit_percent}%): <strong style="color: #3b82f6;">฿${Number(data.deposit_amount || 0).toLocaleString()}</strong></p><p>ยอดคงเหลือ: <strong style="color: #f59e0b;">฿${Number(data.balance_amount || 0).toLocaleString()}</strong></p></div></div><div class="modal-footer">${data.status === 'draft' ? `<button class="btn-primary" onclick="sendMtoQuotation(${data.id}); document.getElementById('mtoQuoteModal').remove();">ส่งใบเสนอราคา</button>` : ''}<button class="btn-secondary" onclick="document.getElementById('mtoQuoteModal').remove()">ปิด</button></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) { showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message); }
}

async function viewMtoOrder(orderId) {
    try {
        const response = await fetch(`/api/mto/orders/${orderId}`, { credentials: 'include' });
        const data = await response.json();
        if (!response.ok) { showAlert('error', data.error || 'เกิดข้อผิดพลาด'); return; }
        
        let itemsHtml = data.items.map(item => `<tr><td><div style="display: flex; align-items: center; gap: 10px;">${item.image_url ? `<img src="${item.image_url}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;">` : ''}<div><strong>${item.product_name}</strong>${item.option_text ? `<br><small style="color: rgba(255,255,255,0.6);">${item.option_text}</small>` : ''}</div></div></td><td>${item.quantity}</td><td>฿${Number(item.unit_price || 0).toLocaleString()}</td><td>฿${Number(item.line_total || 0).toLocaleString()}</td></tr>`).join('');
        
        let timelineHtml = (data.timeline || []).map(t => `<div style="display: flex; align-items: flex-start; gap: 12px; padding: 8px 0;"><div style="width: 24px; height: 24px; border-radius: 50%; background: ${t.completed ? '#10b981' : 'rgba(255,255,255,0.2)'}; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">${t.completed ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>' : ''}</div><div><p style="margin: 0; font-weight: 500;">${t.label}</p>${t.date ? `<small style="color: rgba(255,255,255,0.6);">${formatThaiDate(t.date)}</small>` : ''}</div></div>`).join('');
        
        const modalHtml = `<div class="modal-overlay active" id="mtoOrderModal" onclick="if(event.target===this)this.remove()"><div class="modal" style="max-width: 800px;"><div class="modal-header"><h3>คำสั่งซื้อ ${data.order_number}</h3><button class="modal-close" onclick="document.getElementById('mtoOrderModal').remove()">&times;</button></div><div class="modal-body" style="max-height: 60vh; overflow-y: auto;"><div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px;"><div><h4 style="margin: 0 0 12px;">รายการสินค้า</h4><table class="data-table" style="width: 100%;"><thead><tr><th>สินค้า</th><th>จำนวน</th><th>ราคา/ชิ้น</th><th>รวม</th></tr></thead><tbody>${itemsHtml}</tbody></table><div style="margin-top: 16px; text-align: right;"><p>ยอดรวม: <strong>฿${Number(data.total_amount || 0).toLocaleString()}</strong></p><p>มัดจำ: <span style="color: #10b981;">฿${Number(data.deposit_paid || 0).toLocaleString()}</span> / ฿${Number(data.deposit_amount || 0).toLocaleString()}</p><p>ยอดเหลือ: <span style="color: #f59e0b;">฿${Number(data.balance_paid || 0).toLocaleString()}</span> / ฿${Number(data.balance_amount || 0).toLocaleString()}</p></div></div><div style="background: rgba(255,255,255,0.05); padding: 16px; border-radius: 8px;"><h4 style="margin: 0 0 12px;">Timeline</h4>${timelineHtml}</div></div></div><div class="modal-footer"><button class="btn-primary" onclick="showMtoOrderStatusModal(${data.id}, '${data.status}'); document.getElementById('mtoOrderModal').remove();">อัปเดตสถานะ</button><button class="btn-secondary" onclick="document.getElementById('mtoOrderModal').remove()">ปิด</button></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) { showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message); }
}

function showMtoOrderStatusModal(orderId, currentStatus) {
    const statuses = [
        { value: 'awaiting_deposit', label: 'รอมัดจำ' },
        { value: 'deposit_paid', label: 'ชำระมัดจำแล้ว' },
        { value: 'production', label: 'กำลังผลิต' },
        { value: 'balance_requested', label: 'เรียกเก็บยอดเหลือ' },
        { value: 'balance_paid', label: 'ชำระครบ' },
        { value: 'ready_to_ship', label: 'พร้อมส่ง' },
        { value: 'shipped', label: 'จัดส่งแล้ว' }
    ];
    const optionsHtml = statuses.map(s => `<option value="${s.value}" ${s.value === currentStatus ? 'selected' : ''}>${s.label}</option>`).join('');
    
    // Show modal immediately with loading state for providers
    const modalHtml = `<div class="modal-overlay active" id="mtoStatusModal" onclick="if(event.target===this)this.remove()"><div class="modal" style="max-width: 400px;"><div class="modal-header"><h3>อัปเดตสถานะ</h3><button class="modal-close" onclick="document.getElementById('mtoStatusModal').remove()">&times;</button></div><div class="modal-body"><div class="form-group"><label class="form-label">สถานะใหม่</label><select id="mtoNewStatus" class="form-control">${optionsHtml}</select></div><div id="shippingFields" style="display: none;"><div class="form-group"><label class="form-label">บริษัทขนส่ง</label><select id="mtoShippingProvider" class="form-control"><option value="">กำลังโหลด...</option></select></div><div class="form-group"><label class="form-label">เลขพัสดุ</label><input type="text" id="mtoTrackingNumber" class="form-control"></div></div></div><div class="modal-footer"><button class="btn-primary" onclick="updateMtoOrderStatus(${orderId})">บันทึก</button><button class="btn-secondary" onclick="document.getElementById('mtoStatusModal').remove()">ยกเลิก</button></div></div></div>`;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('mtoNewStatus').addEventListener('change', function() { document.getElementById('shippingFields').style.display = this.value === 'shipped' ? 'block' : 'none'; });
    
    // Show shipping fields if current status is already shipped
    if (currentStatus === 'shipped') {
        document.getElementById('shippingFields').style.display = 'block';
    }
    
    // Load shipping providers asynchronously
    fetch('/api/shipping-providers', { credentials: 'include' })
        .then(res => res.ok ? res.json() : [])
        .then(providers => {
            const select = document.getElementById('mtoShippingProvider');
            if (select) {
                let html = '<option value="">-- เลือกบริษัทขนส่ง --</option>';
                html += providers.filter(p => p.is_active).map(p => `<option value="${p.name}">${p.name}</option>`).join('');
                select.innerHTML = html;
            }
        })
        .catch(() => {
            const select = document.getElementById('mtoShippingProvider');
            if (select) select.innerHTML = '<option value="">-- เลือกบริษัทขนส่ง --</option>';
        });
}

async function updateMtoOrderStatus(orderId) {
    const newStatus = document.getElementById('mtoNewStatus').value;
    const data = { status: newStatus };
    if (newStatus === 'shipped') {
        data.shipping_provider = document.getElementById('mtoShippingProvider').value;
        data.tracking_number = document.getElementById('mtoTrackingNumber').value;
    }
    
    try {
        const response = await fetch(`/api/admin/mto/orders/${orderId}/update-status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (response.ok) {
            showAlert('success', 'อัปเดตสถานะสำเร็จ');
            document.getElementById('mtoStatusModal').remove();
            loadMtoOrders();
        } else { showAlert('error', result.error || 'เกิดข้อผิดพลาด'); }
    } catch (error) { showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message); }
}

async function loadMtoStats() {
    try {
        const response = await fetch('/api/admin/mto/stats', { credentials: 'include' });
        const data = await response.json();
        const pendingRequests = (data.requests?.pending_requests || 0);
        const mtoRequestsBadge = document.getElementById('mtoRequestsCount');
        if (mtoRequestsBadge) {
            mtoRequestsBadge.textContent = pendingRequests;
            mtoRequestsBadge.style.display = pendingRequests > 0 ? 'inline-block' : 'none';
        }
    } catch (error) { console.error('Error loading MTO stats:', error); }
}

// ==========================================
// MTO Products Management Functions
// ==========================================

let mtoProductOptions = [];
let mtoProductImages = [];

async function loadMtoProducts(status = null) {
    const tbody = document.getElementById('mtoProductsTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: rgba(255,255,255,0.5);">กำลังโหลด...</td></tr>';
    
    try {
        let url = '/api/admin/mto/products';
        if (status && status !== 'all') url += `?status=${status}`;
        
        const response = await fetch(url, { credentials: 'include' });
        const products = await response.json();
        
        if (!products.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: rgba(255,255,255,0.5);">ไม่มีสินค้าสั่งผลิต</td></tr>';
            return;
        }
        
        const countBadge = document.getElementById('mtoProductAllCount');
        if (countBadge) countBadge.textContent = products.length;
        
        tbody.innerHTML = products.map(p => `
            <tr>
                <td>
                    <img src="${p.image_url || '/static/images/no-image.png'}" 
                         style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; background: rgba(255,255,255,0.1);"
                         onerror="this.src='/static/images/no-image.png'">
                </td>
                <td><strong>${escapeHtml(p.name)}</strong></td>
                <td style="font-size: 12px; color: rgba(255,255,255,0.7);">${escapeHtml(p.parent_sku)}</td>
                <td>${escapeHtml(p.brand_name || '-')}</td>
                <td>${p.production_days || 0} วัน</td>
                <td>${p.deposit_percent || 50}%</td>
                <td>
                    <span class="status-badge status-${p.status}">
                        ${p.status === 'active' ? 'เปิดใช้งาน' : p.status === 'inactive' ? 'ปิดใช้งาน' : 'แบบร่าง'}
                    </span>
                </td>
                <td>
                    <div style="display: flex; gap: 6px;">
                        <button class="btn-icon" onclick="editMtoProduct(${p.id})" title="แก้ไข">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="btn-icon btn-danger" onclick="deleteMtoProduct(${p.id}, '${escapeHtml(p.name)}')" title="ลบ">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาด: ' + error.message + '</td></tr>';
    }
}

function filterMtoProducts(status) {
    document.querySelectorAll('#page-mto-products .status-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    loadMtoProducts(status);
}

async function showCreateMtoProductModal() {
    mtoProductOptions = [];
    mtoProductImages = [];
    
    document.getElementById('mtoProductId').value = '';
    document.getElementById('mtoProductName').value = '';
    document.getElementById('mtoProductSpu').value = '';
    document.getElementById('mtoProductDescription').value = '';
    document.getElementById('mtoProductionDays').value = '7';
    document.getElementById('mtoDepositPercent').value = '50';
    document.getElementById('mtoProductStatus').value = 'draft';
    document.getElementById('mtoOptionsContainer').innerHTML = '';
    document.getElementById('mtoSkuPreview').innerHTML = '<p style="color: rgba(255,255,255,0.5); text-align: center; padding: 20px;">เพิ่มตัวเลือกสินค้าเพื่อสร้าง SKU</p>';
    document.getElementById('mtoImagePreview').innerHTML = '';
    document.getElementById('mtoProductModalTitle').textContent = 'สร้างสินค้าสั่งผลิต';
    
    await loadBrandsForMtoProduct();
    
    document.getElementById('mtoProductModal').style.display = 'flex';
}

async function loadBrandsForMtoProduct() {
    try {
        const response = await fetch('/api/brands', { credentials: 'include' });
        const brands = await response.json();
        
        const select = document.getElementById('mtoProductBrand');
        select.innerHTML = '<option value="">-- เลือกแบรนด์ --</option>' + 
            brands.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
    } catch (error) {
        console.error('Error loading brands:', error);
    }
}

function closeMtoProductModal() {
    document.getElementById('mtoProductModal').style.display = 'none';
}

function addMtoOption() {
    const container = document.getElementById('mtoOptionsContainer');
    const optIndex = container.children.length;
    const isFirstOption = optIndex === 0;
    
    const optionHtml = `
        <div class="mto-option-row" data-index="${optIndex}" style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="display: flex; gap: 12px; margin-bottom: 10px;">
                <div style="flex: 1;">
                    <label style="font-size: 12px; color: rgba(255,255,255,0.7);">ชื่อตัวเลือก ${isFirstOption ? '(เช่น สี) *' : ''}</label>
                    <input type="text" class="form-input mto-option-name" placeholder="${isFirstOption ? 'เช่น สี' : 'เช่น ขนาด'}" onchange="updateMtoSkuPreview()">
                </div>
                <button type="button" class="btn btn-danger" onclick="removeMtoOption(this)" style="align-self: flex-end; padding: 8px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="mto-option-values" style="display: flex; flex-wrap: wrap; gap: 8px;">
                <!-- Values will be added here -->
            </div>
            <button type="button" class="btn btn-secondary" onclick="addMtoOptionValue(this, ${isFirstOption})" style="margin-top: 8px; font-size: 11px; padding: 4px 10px;">
                + เพิ่มค่า
            </button>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', optionHtml);
}

function removeMtoOption(btn) {
    btn.closest('.mto-option-row').remove();
    updateMtoSkuPreview();
}

function addMtoOptionValue(btn, showMinQty = false) {
    const valuesContainer = btn.previousElementSibling;
    const valueHtml = `
        <div class="mto-value-chip" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(168,85,247,0.2); padding: 6px 10px; border-radius: 6px;">
            <input type="text" class="mto-value-input" placeholder="ค่า" style="width: 80px; background: transparent; border: none; color: #fff; font-size: 12px;" onchange="updateMtoSkuPreview()">
            ${showMinQty ? '<input type="number" class="mto-min-qty" placeholder="ขั้นต่ำ" min="0" value="1" style="width: 60px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; color: #fff; font-size: 11px; padding: 2px 4px;" title="จำนวนขั้นต่ำ">' : ''}
            <button type="button" onclick="this.parentElement.remove(); updateMtoSkuPreview();" style="background: none; border: none; color: rgba(255,255,255,0.5); cursor: pointer; padding: 2px;">&times;</button>
        </div>
    `;
    valuesContainer.insertAdjacentHTML('beforeend', valueHtml);
}

function updateMtoSkuPreview() {
    const container = document.getElementById('mtoSkuPreview');
    const optionRows = document.querySelectorAll('.mto-option-row');
    
    if (optionRows.length === 0) {
        container.innerHTML = '<p style="color: rgba(255,255,255,0.5); text-align: center; padding: 20px;">เพิ่มตัวเลือกสินค้าเพื่อสร้าง SKU</p>';
        return;
    }
    
    const options = [];
    optionRows.forEach((row, idx) => {
        const name = row.querySelector('.mto-option-name').value || `ตัวเลือก ${idx + 1}`;
        const valueInputs = row.querySelectorAll('.mto-value-input');
        const values = [];
        valueInputs.forEach(input => {
            if (input.value.trim()) {
                const minQtyInput = input.nextElementSibling;
                values.push({
                    value: input.value.trim(),
                    min_order_qty: minQtyInput && minQtyInput.classList.contains('mto-min-qty') ? parseInt(minQtyInput.value) || 0 : 0
                });
            }
        });
        if (values.length > 0) {
            options.push({ name, values });
        }
    });
    
    if (options.length === 0) {
        container.innerHTML = '<p style="color: rgba(255,255,255,0.5); text-align: center; padding: 20px;">กรุณาเพิ่มค่าตัวเลือก</p>';
        return;
    }
    
    // Generate combinations
    const combinations = cartesianProduct(options.map(o => o.values.map(v => v.value)));
    const spu = document.getElementById('mtoProductSpu').value || 'SPU';
    
    let html = `<table class="data-table" style="font-size: 12px;">
        <thead>
            <tr>
                <th>SKU Code</th>
                ${options.map(o => `<th>${escapeHtml(o.name)}</th>`).join('')}
                <th>ราคา (บาท)</th>
            </tr>
        </thead>
        <tbody>`;
    
    combinations.forEach((combo, idx) => {
        const skuCode = `${spu}-${idx + 1}`;
        html += `<tr>
            <td>${skuCode}</td>
            ${combo.map(v => `<td>${escapeHtml(v)}</td>`).join('')}
            <td><input type="number" class="sku-price-input form-input" data-idx="${idx}" value="0" min="0" step="0.01" style="width: 100px;"></td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

function cartesianProduct(arrays) {
    if (arrays.length === 0) return [[]];
    return arrays.reduce((acc, curr) => 
        acc.flatMap(a => curr.map(c => [...a, c])), [[]]
    );
}

function handleMtoProductImages(input) {
    const preview = document.getElementById('mtoImagePreview');
    const files = input.files;
    
    for (let file of files) {
        const reader = new FileReader();
        reader.onload = function(e) {
            mtoProductImages.push(e.target.result);
            renderMtoImagePreview();
        };
        reader.readAsDataURL(file);
    }
}

function renderMtoImagePreview() {
    const preview = document.getElementById('mtoImagePreview');
    preview.innerHTML = mtoProductImages.map((img, idx) => `
        <div style="position: relative; display: inline-block;">
            <img src="${img}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 6px;">
            <button type="button" onclick="removeMtoImage(${idx})" style="position: absolute; top: -6px; right: -6px; background: #ef4444; border: none; border-radius: 50%; width: 18px; height: 18px; color: #fff; font-size: 12px; cursor: pointer;">&times;</button>
        </div>
    `).join('');
}

function removeMtoImage(idx) {
    mtoProductImages.splice(idx, 1);
    renderMtoImagePreview();
}

async function saveMtoProduct() {
    const productId = document.getElementById('mtoProductId').value;
    const name = document.getElementById('mtoProductName').value.trim();
    const parentSku = document.getElementById('mtoProductSpu').value.trim();
    const brandId = document.getElementById('mtoProductBrand').value;
    const description = document.getElementById('mtoProductDescription').value.trim();
    const productionDays = parseInt(document.getElementById('mtoProductionDays').value) || 7;
    const depositPercent = parseInt(document.getElementById('mtoDepositPercent').value) || 50;
    const status = document.getElementById('mtoProductStatus').value;
    
    if (!name || !parentSku || !brandId) {
        showAlert('error', 'กรุณากรอกข้อมูลที่จำเป็น');
        return;
    }
    
    // Collect options
    const options = [];
    document.querySelectorAll('.mto-option-row').forEach((row, idx) => {
        const optName = row.querySelector('.mto-option-name').value.trim();
        if (!optName) return;
        
        const values = [];
        row.querySelectorAll('.mto-value-chip').forEach(chip => {
            const valInput = chip.querySelector('.mto-value-input');
            const minQtyInput = chip.querySelector('.mto-min-qty');
            if (valInput && valInput.value.trim()) {
                values.push({
                    value: valInput.value.trim(),
                    min_order_qty: minQtyInput ? parseInt(minQtyInput.value) || 0 : 0
                });
            }
        });
        
        if (values.length > 0) {
            options.push({ name: optName, values });
        }
    });
    
    const data = {
        name, parent_sku: parentSku, brand_id: parseInt(brandId),
        description, production_days: productionDays, deposit_percent: depositPercent,
        status, options, images: mtoProductImages
    };
    
    try {
        const url = productId ? `/api/admin/mto/products/${productId}` : '/api/admin/mto/products';
        const method = productId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', result.message || 'บันทึกสำเร็จ');
            closeMtoProductModal();
            loadMtoProducts();
        } else {
            showAlert('error', result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

function editMtoProduct(productId) {
    window.location.href = `/admin/mto/products/edit/${productId}`;
}

async function deleteMtoProduct(productId, productName) {
    if (!confirm(`ต้องการลบสินค้า "${productName}" หรือไม่?`)) return;
    
    try {
        const response = await fetch(`/api/admin/mto/products/${productId}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': csrfToken },
            credentials: 'include'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', result.message || 'ลบสำเร็จ');
            loadMtoProducts();
        } else {
            showAlert('error', result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

