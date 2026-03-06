// ==========================================
// Brands Page Functions
// ==========================================

let brandsData = [];

async function loadBrandsPage() {
    const tableBody = document.getElementById('brandsTableBody');
    const countEl = document.getElementById('brandCount');
    
    try {
        const response = await fetch(`${API_URL}/brands`);
        brandsData = await response.json();
        
        if (countEl) countEl.textContent = brandsData.length;
        
        if (brandsData.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 30px; opacity: 0.6;">ยังไม่มีแบรนด์</td></tr>';
            return;
        }
        
        let html = '';
        brandsData.forEach(brand => {
            html += `
                <tr>
                    <td><strong>${brand.name}</strong></td>
                    <td style="opacity: 0.7;">${brand.description || '-'}</td>
                    <td>
                        <button class="btn-edit" onclick="editBrand(${brand.id})" style="margin-right: 6px;">แก้ไข</button>
                        <button class="btn-delete" onclick="deleteBrand(${brand.id}, '${brand.name}')">ลบ</button>
                    </td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    } catch (error) {
        console.error('Error loading brands:', error);
        tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

async function handleBrandSubmit(event) {
    event.preventDefault();
    
    const editId = document.getElementById('editBrandId').value;
    const name = document.getElementById('brandName').value.trim();
    const description = document.getElementById('brandDescription').value.trim();
    
    if (!name) {
        showAlert('กรุณากรอกชื่อแบรนด์', 'error');
        return;
    }
    
    try {
        const url = editId ? `${API_URL}/brands/${editId}` : `${API_URL}/brands`;
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        
        if (response.ok) {
            showAlert(editId ? 'แก้ไขแบรนด์สำเร็จ' : 'เพิ่มแบรนด์สำเร็จ', 'success');
            resetBrandForm();
            loadBrandsPage();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving brand:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function editBrand(id) {
    const brand = brandsData.find(b => b.id === id);
    if (!brand) return;
    
    document.getElementById('editBrandId').value = brand.id;
    document.getElementById('brandName').value = brand.name;
    document.getElementById('brandDescription').value = brand.description || '';
    
    document.querySelector('#page-brands .card h3').textContent = 'แก้ไขแบรนด์';
}

async function deleteBrand(id, name) {
    if (!confirm(`ลบแบรนด์ "${name}"?`)) return;
    
    try {
        const response = await fetch(`${API_URL}/brands/${id}`, { method: 'DELETE' });
        
        if (response.ok) {
            showAlert('ลบแบรนด์สำเร็จ', 'success');
            loadBrandsPage();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting brand:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function resetBrandForm() {
    document.getElementById('editBrandId').value = '';
    document.getElementById('brandName').value = '';
    document.getElementById('brandDescription').value = '';
    document.querySelector('#page-brands .card h3').textContent = 'เพิ่มแบรนด์ใหม่';
}

// ==========================================
// Categories Page Functions
// ==========================================

let categoriesData = [];

async function loadCategoriesPage() {
    const tableBody = document.getElementById('categoriesTableBody');
    const countEl = document.getElementById('categoryCount');
    
    try {
        const response = await fetch(`${API_URL}/categories`);
        categoriesData = await response.json();
        
        if (countEl) countEl.textContent = categoriesData.length;
        
        if (categoriesData.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 30px; opacity: 0.6;">ยังไม่มีหมวดหมู่</td></tr>';
            return;
        }
        
        let html = '';
        categoriesData.forEach(cat => {
            html += `
                <tr>
                    <td><strong>${cat.name}</strong></td>
                    <td style="opacity: 0.7;">${cat.description || '-'}</td>
                    <td>
                        <button class="btn-edit" onclick="editCategory(${cat.id})" style="margin-right: 6px;">แก้ไข</button>
                        <button class="btn-delete" onclick="deleteCategory(${cat.id}, '${cat.name}')">ลบ</button>
                    </td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    } catch (error) {
        console.error('Error loading categories:', error);
        tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

async function handleCategorySubmit(event) {
    event.preventDefault();
    
    const editId = document.getElementById('editCategoryId').value;
    const name = document.getElementById('categoryName').value.trim();
    const description = document.getElementById('categoryDescription').value.trim();
    
    if (!name) {
        showAlert('กรุณากรอกชื่อหมวดหมู่', 'error');
        return;
    }
    
    try {
        const url = editId ? `${API_URL}/categories/${editId}` : `${API_URL}/categories`;
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        
        if (response.ok) {
            showAlert(editId ? 'แก้ไขหมวดหมู่สำเร็จ' : 'เพิ่มหมวดหมู่สำเร็จ', 'success');
            resetCategoryForm();
            loadCategoriesPage();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving category:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function editCategory(id) {
    const cat = categoriesData.find(c => c.id === id);
    if (!cat) return;
    
    document.getElementById('editCategoryId').value = cat.id;
    document.getElementById('categoryName').value = cat.name;
    document.getElementById('categoryDescription').value = cat.description || '';
    
    document.querySelector('#page-categories .card h3').textContent = 'แก้ไขหมวดหมู่';
}

async function deleteCategory(id, name) {
    if (!confirm(`ลบหมวดหมู่ "${name}"?`)) return;
    
    try {
        const response = await fetch(`${API_URL}/categories/${id}`, { method: 'DELETE' });
        
        if (response.ok) {
            showAlert('ลบหมวดหมู่สำเร็จ', 'success');
            loadCategoriesPage();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting category:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function resetCategoryForm() {
    document.getElementById('editCategoryId').value = '';
    document.getElementById('categoryName').value = '';
    document.getElementById('categoryDescription').value = '';
    document.querySelector('#page-categories .card h3').textContent = 'เพิ่มหมวดหมู่ใหม่';
}

// ==================== DASHBOARD STATS ====================
let salesChart = null;

async function loadDashboardStats() {
    try {
        const response = await fetch(`${API_URL}/admin/dashboard-stats`);
        if (!response.ok) throw new Error('Failed to load dashboard stats');
        
        const data = await response.json();
        
        // Update sales stats
        const salesTodayEl = document.getElementById('salesToday');
        const salesMonthEl = document.getElementById('salesMonth');
        const salesAllEl = document.getElementById('salesAll');
        const ordersTodayEl = document.getElementById('ordersToday');
        const ordersMonthEl = document.getElementById('ordersMonth');
        const pendingOrdersEl = document.getElementById('pendingOrders');
        const lowStockEl = document.getElementById('lowStock');
        const lowStockSkusEl = document.getElementById('lowStockSkus');
        const outOfStockEl = document.getElementById('outOfStock');
        const outOfStockSkusEl = document.getElementById('outOfStockSkus');
        
        if (salesTodayEl) salesTodayEl.textContent = formatCurrency(data.sales_today.total);
        if (salesMonthEl) salesMonthEl.textContent = formatCurrency(data.sales_month.total);
        if (salesAllEl) salesAllEl.textContent = formatCurrency(data.sales_all.total);
        if (ordersTodayEl) ordersTodayEl.textContent = `${data.sales_today.count} ออเดอร์`;
        if (ordersMonthEl) ordersMonthEl.textContent = `${data.sales_month.count} ออเดอร์`;
        if (pendingOrdersEl) pendingOrdersEl.textContent = data.pending_orders;
        if (outOfStockEl) outOfStockEl.textContent = data.out_of_stock_skus || 0;
        if (lowStockEl) lowStockEl.textContent = data.low_stock_skus || 0;
        if (lowStockSkusEl) lowStockSkusEl.textContent = data.out_of_stock ? `${data.out_of_stock} สินค้าหมด` : '';
        if (outOfStockSkusEl) outOfStockSkusEl.textContent = data.low_stock ? `${data.low_stock} สินค้าใกล้หมด` : '';
        
        // Render sales chart
        renderSalesChart(data.sales_7_days);
        
        // Render recent orders
        renderRecentOrders(data.recent_orders);
        
        // Render top products
        renderTopProducts(data.top_products);
        
        // Load sales history and brand sales
        loadSalesHistory();
        loadBrandSales();
        
    } catch (error) {
        console.error('Error loading dashboard stats:', error);
    }
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('th-TH', {
        style: 'currency',
        currency: 'THB',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount);
}

function renderSalesChart(salesData) {
    const ctx = document.getElementById('salesChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (salesChart) {
        salesChart.destroy();
    }
    
    const labels = salesData.map(d => {
        const date = new Date(d.date);
        return date.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
    });
    
    const values = salesData.map(d => d.total);
    
    salesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'ยอดขาย',
                data: values,
                backgroundColor: 'rgba(139, 92, 246, 0.6)',
                borderColor: 'rgba(139, 92, 246, 1)',
                borderWidth: 2,
                borderRadius: 8,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleFont: { size: 14 },
                    bodyFont: { size: 13 },
                    callbacks: {
                        label: function(context) {
                            return formatCurrency(context.raw);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        callback: function(value) {
                            if (value >= 1000) {
                                return (value / 1000) + 'k';
                            }
                            return value;
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                }
            }
        }
    });
}

function renderRecentOrders(orders) {
    const container = document.getElementById('recentOrdersList');
    if (!container) return;
    
    if (!orders || orders.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <p>ยังไม่มีออเดอร์</p>
            </div>
        `;
        return;
    }
    
    const statusLabels = {
        'pending_payment': 'รอชำระเงิน',
        'under_review': 'รอตรวจสอบ',
        'preparing': 'ที่ต้องจัดส่ง',
        'paid': 'ชำระแล้ว',
        'shipped': 'กำลังจัดส่ง',
        'delivered': 'จัดส่งสำเร็จ',
        'failed_delivery': 'จัดส่งไม่สำเร็จ',
        'rejected': 'ปฏิเสธ',
        'cancelled': 'ยกเลิก',
        'pending_refund': 'รอคืนเงิน',
        'refunded': 'คืนเงินสำเร็จ'
    };
    
    let html = '';
    orders.forEach(order => {
        const statusClass = order.status.replace('_', '-');
        const statusLabel = statusLabels[order.status] || order.status;
        const timeAgo = order.created_at ? getTimeAgo(new Date(order.created_at)) : '';
        
        html += `
            <div class="order-item" onclick="switchPage('orders')">
                <div class="order-info">
                    <span class="order-number">${order.order_number}</span>
                    <span class="order-customer">${order.customer_name || 'ไม่ระบุชื่อ'} - ${timeAgo}</span>
                </div>
                <div class="order-meta">
                    <span class="order-amount">${formatCurrency(order.final_amount)}</span>
                    <span class="order-status ${order.status}">${statusLabel}</span>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function renderTopProducts(products) {
    const container = document.getElementById('topProductsList');
    if (!container) return;
    
    if (!products || products.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                <p>ยังไม่มีข้อมูลสินค้าขายดี</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    products.forEach((product, index) => {
        html += `
            <div class="product-item">
                <span class="product-rank">${index + 1}</span>
                <div class="product-info">
                    <span class="product-name">${product.name}</span>
                    <span class="product-sold">ขายแล้ว ${product.total_sold} ชิ้น</span>
                </div>
                <span class="product-revenue">${formatCurrency(product.revenue)}</span>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function getTimeAgo(date) {
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'เมื่อสักครู่';
    if (minutes < 60) return `${minutes} นาทีที่แล้ว`;
    if (hours < 24) return `${hours} ชั่วโมงที่แล้ว`;
    if (days < 7) return `${days} วันที่แล้ว`;
    return date.toLocaleDateString('th-TH');
}

// ==================== SALES HISTORY ====================
let salesSearchTimeout = null;

function debounceSearchSales() {
    clearTimeout(salesSearchTimeout);
    salesSearchTimeout = setTimeout(loadSalesHistory, 300);
}

async function loadSalesHistory() {
    try {
        const period = document.getElementById('salesPeriodFilter')?.value || '7days';
        const channelId = document.getElementById('salesChannelFilter')?.value || '';
        const status = document.getElementById('salesStatusFilter')?.value || '';
        const search = document.getElementById('salesSearchInput')?.value || '';
        const startDate = document.getElementById('salesStartDate')?.value || '';
        const endDate = document.getElementById('salesEndDate')?.value || '';
        
        // Show/hide custom date range
        const customDateRange = document.getElementById('customDateRange');
        if (customDateRange) {
            customDateRange.style.display = period === 'custom' ? 'flex' : 'none';
        }
        
        // Build query params
        let params = `period=${period}`;
        if (period === 'custom' && startDate && endDate) {
            params += `&start_date=${startDate}&end_date=${endDate}`;
        }
        if (channelId) params += `&channel_id=${channelId}`;
        if (status) params += `&status=${status}`;
        if (search) params += `&search=${encodeURIComponent(search)}`;
        
        const response = await fetch(`${API_URL}/admin/sales-history?${params}`);
        if (!response.ok) throw new Error('Failed to load sales history');
        
        const data = await response.json();
        
        // Populate channels dropdown
        const channelFilter = document.getElementById('salesChannelFilter');
        if (channelFilter && data.channels) {
            const currentValue = channelFilter.value;
            channelFilter.innerHTML = '<option value="">ทั้งหมด</option>';
            data.channels.forEach(ch => {
                channelFilter.innerHTML += `<option value="${ch.id}" ${currentValue == ch.id ? 'selected' : ''}>${ch.name}</option>`;
            });
        }
        
        // Update summary
        document.getElementById('salesSummaryTotal').textContent = formatCurrency(data.summary.total);
        document.getElementById('salesSummaryCount').textContent = data.summary.count;
        document.getElementById('salesSummaryPaid').textContent = formatCurrency(data.summary.paid_total);
        
        // Render table
        renderSalesHistoryTable(data.orders);
        
    } catch (error) {
        console.error('Error loading sales history:', error);
    }
}

function renderSalesHistoryTable(orders) {
    const tbody = document.getElementById('salesHistoryBody');
    if (!tbody) return;
    
    const statusLabels = {
        'pending_payment': 'รอชำระเงิน',
        'under_review': 'รอตรวจสอบ',
        'preparing': 'ที่ต้องจัดส่ง',
        'paid': 'ชำระแล้ว',
        'shipped': 'กำลังจัดส่ง',
        'delivered': 'จัดส่งสำเร็จ',
        'failed_delivery': 'จัดส่งไม่สำเร็จ',
        'rejected': 'ปฏิเสธ',
        'cancelled': 'ยกเลิก',
        'pending_refund': 'รอคืนเงิน',
        'refunded': 'คืนเงินสำเร็จ'
    };
    
    if (!orders || orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="loading-placeholder">ไม่พบข้อมูลออเดอร์</td></tr>';
        return;
    }
    
    let html = '';
    orders.forEach(order => {
        const date = order.created_at ? new Date(order.created_at).toLocaleDateString('th-TH', {day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit'}) : '-';
        html += `
            <tr onclick="switchPage('orders')">
                <td><strong>${order.order_number}</strong></td>
                <td>${order.customer_name || '-'}</td>
                <td>${order.channel_name || '-'}</td>
                <td>${order.item_count} รายการ</td>
                <td>${formatCurrency(order.final_amount)}</td>
                <td><span class="order-status ${order.status}">${statusLabels[order.status] || order.status}</span></td>
                <td>${date}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// ==================== BRAND SALES ====================
async function loadBrandSales() {
    try {
        const period = document.getElementById('brandPeriodFilter')?.value || 'this_month';
        const brandId = document.getElementById('brandFilter')?.value || '';
        const startDate = document.getElementById('brandStartDate')?.value || '';
        const endDate = document.getElementById('brandEndDate')?.value || '';
        
        // Show/hide custom date range
        const customDateRange = document.getElementById('brandCustomDateRange');
        if (customDateRange) {
            customDateRange.style.display = period === 'custom' ? 'flex' : 'none';
        }
        
        // Build query params
        let params = `period=${period}`;
        if (period === 'custom' && startDate && endDate) {
            params += `&start_date=${startDate}&end_date=${endDate}`;
        }
        if (brandId) params += `&brand_id=${brandId}`;
        
        const response = await fetch(`${API_URL}/admin/brand-sales?${params}`);
        if (!response.ok) throw new Error('Failed to load brand sales');
        
        const data = await response.json();
        
        // Populate brands dropdown
        const brandFilter = document.getElementById('brandFilter');
        if (brandFilter && data.all_brands) {
            const currentValue = brandFilter.value;
            brandFilter.innerHTML = '<option value="">ทั้งหมด</option>';
            data.all_brands.forEach(br => {
                brandFilter.innerHTML += `<option value="${br.id}" ${currentValue == br.id ? 'selected' : ''}>${br.name}</option>`;
            });
        }
        
        // Update summary
        document.getElementById('brandSummaryTotal').textContent = formatCurrency(data.summary.total_revenue);
        document.getElementById('brandSummarySold').textContent = `${data.summary.total_sold.toLocaleString()} ชิ้น`;
        
        // Render brand sales grid
        renderBrandSalesGrid(data.brands);
        
    } catch (error) {
        console.error('Error loading brand sales:', error);
    }
}

function renderBrandSalesGrid(brands) {
    const container = document.getElementById('brandSalesGrid');
    if (!container) return;
    
    if (!brands || brands.length === 0) {
        container.innerHTML = '<div class="loading-placeholder">ไม่พบข้อมูลยอดขาย</div>';
        return;
    }
    
    let html = '';
    brands.forEach((brand, index) => {
        html += `
            <div class="brand-sales-item">
                <div class="brand-name">
                    <span class="rank">${index + 1}</span>
                    ${brand.name}
                </div>
                <div class="brand-stats">
                    <div class="brand-stat">
                        <span class="brand-stat-value revenue">${formatCurrency(brand.revenue)}</span>
                        <span class="brand-stat-label">ยอดขาย</span>
                    </div>
                    <div class="brand-stat">
                        <span class="brand-stat-value">${brand.total_sold.toLocaleString()}</span>
                        <span class="brand-stat-label">ชิ้น</span>
                    </div>
                    <div class="brand-stat">
                        <span class="brand-stat-value">${brand.order_count}</span>
                        <span class="brand-stat-label">ออเดอร์</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

