// ==================== WAREHOUSE MANAGEMENT ====================

async function loadWarehousesPage() {
    try {
        const response = await fetch(`${API_URL}/admin/warehouses`);
        if (!response.ok) throw new Error('Failed to load warehouses');
        const warehouses = await response.json();
        console.log('Loaded', warehouses.length, 'warehouses');
        
        const tbody = document.getElementById('warehousesTableBody');
        const countEl = document.getElementById('warehouseCount');
        
        if (countEl) countEl.textContent = warehouses.length;
        
        if (!tbody) return;
        
        if (warehouses.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 30px; opacity: 0.6;">ยังไม่มีโกดัง</td></tr>';
            return;
        }
        
        tbody.innerHTML = warehouses.map(w => `
            <tr>
                <td><strong>${escapeHtml(w.name)}</strong></td>
                <td>${w.address ? escapeHtml(w.address) : '-'}<br>
                    <small style="opacity: 0.6;">${[w.subdistrict, w.district, w.province, w.postal_code].filter(Boolean).join(', ') || ''}</small>
                </td>
                <td>${w.phone ? escapeHtml(w.phone) : '-'}</td>
                <td>${w.contact_name ? escapeHtml(w.contact_name) : '-'}</td>
                <td>
                    <span class="status-badge ${w.is_active ? 'active' : 'inactive'}" style="padding: 4px 10px; border-radius: 12px; font-size: 11px; ${w.is_active ? 'background: rgba(34,197,94,0.2); color: #22c55e;' : 'background: rgba(239,68,68,0.2); color: #ef4444;'}">
                        ${w.is_active ? 'ใช้งาน' : 'ปิดใช้งาน'}
                    </span>
                </td>
                <td>
                    <button onclick="editWarehouse(${w.id})" class="btn-icon" title="แก้ไข">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                        </svg>
                    </button>
                    <button onclick="deleteWarehouse(${w.id}, '${escapeHtml(w.name)}')" class="btn-icon delete" title="ลบ">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
                            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                        </svg>
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading warehouses:', error);
        showGlobalAlert('ไม่สามารถโหลดข้อมูลโกดังได้', 'error');
    }
}

async function handleWarehouseSubmit(event) {
    event.preventDefault();
    
    const editId = document.getElementById('editWarehouseId').value;
    const data = {
        name: document.getElementById('warehouseName').value.trim(),
        address: document.getElementById('warehouseAddress').value.trim(),
        province: document.getElementById('warehouseProvince').value.trim(),
        district: document.getElementById('warehouseDistrict').value.trim(),
        subdistrict: document.getElementById('warehouseSubdistrict').value.trim(),
        postal_code: document.getElementById('warehousePostalCode').value.trim(),
        phone: document.getElementById('warehousePhone').value.trim(),
        contact_name: document.getElementById('warehouseContactName').value.trim()
    };
    
    if (!data.name) {
        showGlobalAlert('กรุณาระบุชื่อโกดัง', 'error');
        return;
    }
    
    try {
        const url = editId ? `${API_URL}/admin/warehouses/${editId}` : `${API_URL}/admin/warehouses`;
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to save warehouse');
        }
        
        showGlobalAlert(editId ? 'อัปเดตโกดังเรียบร้อย' : 'เพิ่มโกดังเรียบร้อย', 'success');
        resetWarehouseForm();
        loadWarehousesPage();
    } catch (error) {
        console.error('Error saving warehouse:', error);
        showGlobalAlert(error.message || 'ไม่สามารถบันทึกโกดังได้', 'error');
    }
}

async function editWarehouse(id) {
    try {
        const response = await fetch(`${API_URL}/admin/warehouses/${id}`);
        if (!response.ok) throw new Error('Failed to load warehouse');
        const w = await response.json();
        
        document.getElementById('editWarehouseId').value = w.id;
        document.getElementById('warehouseName').value = w.name || '';
        document.getElementById('warehouseAddress').value = w.address || '';
        document.getElementById('warehouseProvince').value = w.province || '';
        document.getElementById('warehouseDistrict').value = w.district || '';
        document.getElementById('warehouseSubdistrict').value = w.subdistrict || '';
        document.getElementById('warehousePostalCode').value = w.postal_code || '';
        document.getElementById('warehousePhone').value = w.phone || '';
        document.getElementById('warehouseContactName').value = w.contact_name || '';
        
        document.getElementById('warehouseFormTitle').textContent = 'แก้ไขโกดัง';
        document.getElementById('warehouseName').focus();
    } catch (error) {
        console.error('Error loading warehouse:', error);
        showGlobalAlert('ไม่สามารถโหลดข้อมูลโกดังได้', 'error');
    }
}

async function deleteWarehouse(id, name) {
    if (!confirm(`คุณต้องการลบโกดัง "${name}" ใช่หรือไม่?`)) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/warehouses/${id}`, { method: 'DELETE' });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to delete warehouse');
        }
        
        showGlobalAlert('ลบโกดังเรียบร้อย', 'success');
        loadWarehousesPage();
    } catch (error) {
        console.error('Error deleting warehouse:', error);
        showGlobalAlert(error.message || 'ไม่สามารถลบโกดังได้', 'error');
    }
}

function resetWarehouseForm() {
    document.getElementById('warehouseForm').reset();
    document.getElementById('editWarehouseId').value = '';
    document.getElementById('warehouseFormTitle').textContent = 'เพิ่มโกดังใหม่';
}

// ==================== STOCK TRANSFER FUNCTIONS ====================

let transferSkuData = null;
let transferSearchTimeout = null;
let selectedTransferProductData = null;

async function loadStockTransferPage() {
    await loadWarehouseDropdowns('transfer');
    loadTransferHistory();
}

async function loadWarehouseDropdowns(prefix) {
    try {
        const response = await fetch(`${API_URL}/admin/warehouses`);
        if (!response.ok) throw new Error('Failed to load warehouses');
        const warehouses = await response.json();
        const activeWarehouses = warehouses.filter(w => w.is_active);
        
        const fromSelect = document.getElementById(`${prefix}FromWarehouse`) || document.getElementById(`${prefix}Warehouse`);
        const toSelect = document.getElementById(`${prefix}ToWarehouse`);
        
        if (fromSelect) {
            fromSelect.innerHTML = '<option value="">-- เลือกโกดัง --</option>';
            activeWarehouses.forEach(w => {
                fromSelect.innerHTML += `<option value="${w.id}">${w.name}</option>`;
            });
        }
        
        if (toSelect) {
            toSelect.innerHTML = '<option value="">-- เลือกโกดัง --</option>';
            activeWarehouses.forEach(w => {
                toSelect.innerHTML += `<option value="${w.id}">${w.name}</option>`;
            });
        }
        
        // For product-based adjustment
        const productAdjustSelect = document.getElementById('productAdjustWarehouse');
        if (productAdjustSelect && prefix === 'productAdjust') {
            productAdjustSelect.innerHTML = '<option value="">-- เลือกโกดัง --</option>';
            activeWarehouses.forEach(w => {
                productAdjustSelect.innerHTML += `<option value="${w.id}">${w.name}</option>`;
            });
        }
        
        const historyWarehouse = document.getElementById('historyWarehouse');
        if (historyWarehouse) {
            historyWarehouse.innerHTML = '<option value="">ทุกโกดัง</option>';
            activeWarehouses.forEach(w => {
                historyWarehouse.innerHTML += `<option value="${w.id}">${w.name}</option>`;
            });
        }
    } catch (error) {
        console.error('Error loading warehouses:', error);
    }
}

function searchProductForTransfer(keyword) {
    clearTimeout(transferSearchTimeout);
    if (!keyword || keyword.length < 2) {
        document.getElementById('transferProductResults').style.display = 'none';
        return;
    }
    
    transferSearchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`${API_URL}/admin/products?search=${encodeURIComponent(keyword)}&limit=20`);
            if (!response.ok) throw new Error('Failed to search products');
            const data = await response.json();
            const products = data.products || data;
            
            const resultsDiv = document.getElementById('transferProductResults');
            if (products.length === 0) {
                resultsDiv.innerHTML = '<div style="padding: 16px; text-align: center; color: #9ca3af;">ไม่พบสินค้า</div>';
            } else {
                resultsDiv.innerHTML = products.map(p => `
                    <div class="sku-result-item" onclick="selectProductForTransfer(${p.id})" style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <img src="${p.image_url || '/static/images/placeholder.png'}" alt="" style="width: 40px; height: 40px; object-fit: cover; border-radius: 6px; background: rgba(255,255,255,0.1);">
                            <div>
                                <strong style="font-size: 14px; color: #fff;">${escapeHtml(p.name)}</strong>
                                <div style="font-size: 12px; color: #9ca3af;">${escapeHtml(p.parent_sku)} | ${p.sku_count || '-'} SKU</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            resultsDiv.style.display = 'block';
        } catch (error) {
            console.error('Error searching products:', error);
        }
    }, 300);
}

async function selectProductForTransfer(productId) {
    document.getElementById('transferProductResults').style.display = 'none';
    document.getElementById('transferProductSearch').value = '';
    
    try {
        const response = await fetch(`${API_URL}/admin/products/${productId}/skus-with-stock`);
        if (!response.ok) throw new Error('Failed to load product SKUs');
        const data = await response.json();
        
        selectedTransferProductData = {
            product: data.product,
            skus: data.skus,
            warehouses: data.warehouses
        };
        
        const product = data.product;
        document.getElementById('transferSelectedProductImage').src = product.image_url || '/static/images/placeholder.png';
        document.getElementById('transferSelectedProductName').textContent = product.name;
        document.getElementById('transferSelectedProductSku').textContent = `Parent SKU: ${product.parent_sku || '-'}`;
        document.getElementById('transferSelectedProductSkuCount').textContent = `${data.skus.length} SKU`;
        document.getElementById('transferSelectedProductCard').style.display = 'block';
        
        updateTransferSkuTable();
    } catch (error) {
        console.error('Error loading product:', error);
        showGlobalAlert('ไม่สามารถโหลดข้อมูลสินค้าได้', 'error');
    }
}

function clearTransferSelectedProduct() {
    selectedTransferProductData = null;
    document.getElementById('transferSelectedProductCard').style.display = 'none';
    document.getElementById('transferProductSearch').value = '';
    document.getElementById('transferSkuTableBody').innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 30px; color: #9ca3af;">เลือกโกดังต้นทางเพื่อดู SKU</td></tr>';
}

function updateTransferSkuTable() {
    if (!selectedTransferProductData) return;
    
    const fromWarehouseId = document.getElementById('transferFromWarehouse').value;
    const tbody = document.getElementById('transferSkuTableBody');
    
    if (!fromWarehouseId) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 30px; color: #9ca3af;">เลือกโกดังต้นทางเพื่อดู SKU</td></tr>';
        return;
    }
    
    const rows = selectedTransferProductData.skus.map(sku => {
        const warehouseStock = sku.warehouses ? sku.warehouses.find(ws => ws.warehouse_id == fromWarehouseId) : null;
        const stockInWarehouse = warehouseStock ? warehouseStock.stock : 0;
        
        const stockBg = stockInWarehouse === 0 ? 'rgba(239,68,68,0.2)' : (stockInWarehouse <= 5 ? 'rgba(245,158,11,0.2)' : 'rgba(16,185,129,0.2)');
        const stockBorder = stockInWarehouse === 0 ? '#ef4444' : (stockInWarehouse <= 5 ? '#f59e0b' : '#10b981');
        
        return `
            <tr data-sku-id="${sku.id}">
                <td style="padding: 12px 16px; color: #fff;"><strong>${escapeHtml(sku.sku_code)}</strong></td>
                <td style="padding: 12px 16px; color: #e5e7eb;">${escapeHtml(sku.variant_display || '-')}</td>
                <td style="padding: 12px 16px; text-align: center;">
                    <span style="display: inline-block; min-width: 50px; padding: 4px 10px; background: ${stockBg}; border: 1px solid ${stockBorder}; border-radius: 6px; font-weight: 700; color: #fff;">${stockInWarehouse}</span>
                </td>
                <td style="padding: 12px 16px; text-align: center;">
                    <input type="number" class="form-input sku-transfer-qty" min="0" max="${stockInWarehouse}" value="0" 
                           style="width: 100px; text-align: center; padding: 8px; font-size: 14px;" ${stockInWarehouse === 0 ? 'disabled' : ''}>
                </td>
            </tr>
        `;
    }).join('');
    
    tbody.innerHTML = rows || '<tr><td colspan="4" style="text-align: center; padding: 30px; color: #9ca3af;">ไม่มี SKU</td></tr>';
}

async function submitBulkTransfer() {
    if (!selectedTransferProductData) {
        showGlobalAlert('กรุณาเลือกสินค้าก่อน', 'error');
        return;
    }
    
    const fromWarehouseId = document.getElementById('transferFromWarehouse').value;
    const toWarehouseId = document.getElementById('transferToWarehouse').value;
    const notes = document.getElementById('transferNotes').value.trim();
    
    if (!fromWarehouseId || !toWarehouseId) {
        showGlobalAlert('กรุณาเลือกโกดังต้นทางและปลายทาง', 'error');
        return;
    }
    
    if (fromWarehouseId === toWarehouseId) {
        showGlobalAlert('โกดังต้นทางและปลายทางต้องไม่ซ้ำกัน', 'error');
        return;
    }
    
    const transfers = [];
    const rows = document.querySelectorAll('#transferSkuTableBody tr');
    rows.forEach(row => {
        const skuId = parseInt(row.dataset.skuId);
        const qtyInput = row.querySelector('.sku-transfer-qty');
        const qty = parseInt(qtyInput?.value) || 0;
        if (qty > 0) {
            transfers.push({
                sku_id: skuId,
                from_warehouse_id: parseInt(fromWarehouseId),
                to_warehouse_id: parseInt(toWarehouseId),
                quantity: qty,
                notes: notes
            });
        }
    });
    
    if (transfers.length === 0) {
        showGlobalAlert('กรุณากรอกจำนวนอย่างน้อย 1 รายการ', 'error');
        return;
    }
    
    try {
        let successCount = 0;
        for (const transfer of transfers) {
            const response = await fetch(`${API_URL}/admin/stock-transfers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transfer)
            });
            if (response.ok) successCount++;
        }
        
        showGlobalAlert(`ย้ายสต็อกสำเร็จ ${successCount} รายการ`, 'success');
        clearTransferSelectedProduct();
        loadTransferHistory();
    } catch (error) {
        console.error('Error transferring stock:', error);
        showGlobalAlert(error.message || 'ไม่สามารถย้ายสต็อกได้', 'error');
    }
}

async function loadTransferHistory() {
    const dateFrom = document.getElementById('transferDateFrom')?.value;
    const dateTo = document.getElementById('transferDateTo')?.value;
    
    let url = `${API_URL}/admin/stock-transfers?`;
    if (dateFrom) url += `date_from=${dateFrom}&`;
    if (dateTo) url += `date_to=${dateTo}&`;
    
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load transfers');
        const transfers = await response.json();
        
        const tbody = document.getElementById('transferHistoryBody');
        if (!tbody) return;
        
        if (transfers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 30px; opacity: 0.6;">ไม่มีข้อมูล</td></tr>';
            return;
        }
        
        tbody.innerHTML = transfers.map(t => `
            <tr>
                <td style="color: #fff;">${formatDateTime(t.created_at)}</td>
                <td style="color: #fff;"><strong>${escapeHtml(t.sku_code)}</strong><br><small style="color: #e5e7eb;">${escapeHtml(t.product_name)}</small></td>
                <td style="color: #fff;">${escapeHtml(t.from_warehouse_name)}</td>
                <td style="color: #fff;">${escapeHtml(t.to_warehouse_name)}</td>
                <td style="text-align: center;">
                    <span style="display: inline-block; min-width: 50px; padding: 4px 10px; background: rgba(139,92,246,0.2); border: 1px solid #a78bfa; border-radius: 6px; font-weight: 700; color: #fff;">${t.quantity}</span>
                </td>
                <td style="color: #fff;">${t.created_by_name || '-'}</td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading transfer history:', error);
    }
}

// ==================== STOCK ADJUSTMENT FUNCTIONS ====================

let adjustSkuData = null;
let adjustSearchTimeout = null;
let bulkRowId = 1;
let bulkSearchTimeouts = {};
let bulkSkuCache = {};

// Product-based adjustment state
let productAdjustSearchTimeout = null;
let selectedProductData = null;

async function loadStockAdjustmentPage() {
    loadAdjustmentHistory();
    
    // Check for pre-selected product from URL parameters (e.g., from product edit page)
    const hash = window.location.hash;
    if (hash.includes('?')) {
        const params = new URLSearchParams(hash.split('?')[1]);
        const productId = params.get('product_id');
        
        if (productId) {
            // Auto-select the product for adjustment
            setTimeout(() => {
                selectProductForAdjust(parseInt(productId));
            }, 300);
            
            // Clear URL parameters after processing
            history.replaceState(null, '', hash.split('?')[0]);
        }
    }
}

function searchSkuForAdjust(keyword) {
    clearTimeout(adjustSearchTimeout);
    if (!keyword || keyword.length < 2) {
        document.getElementById('adjustSkuResults').style.display = 'none';
        return;
    }
    
    adjustSearchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`${API_URL}/admin/skus/search?keyword=${encodeURIComponent(keyword)}`);
            if (!response.ok) throw new Error('Failed to search SKUs');
            const skus = await response.json();
            
            const resultsDiv = document.getElementById('adjustSkuResults');
            if (skus.length === 0) {
                resultsDiv.innerHTML = '<div class="sku-result-item" style="opacity: 0.6;">ไม่พบ SKU</div>';
            } else {
                resultsDiv.innerHTML = skus.map(s => `
                    <div class="sku-result-item" onclick="selectAdjustSku(${s.id}, '${escapeHtml(s.sku_code)}', '${escapeHtml(s.product_name)}')">
                        <strong>${escapeHtml(s.sku_code)}</strong> - ${escapeHtml(s.product_name)}
                        <span class="stock-badge">สต็อก: ${s.total_stock}</span>
                    </div>
                `).join('');
            }
            resultsDiv.style.display = 'block';
        } catch (error) {
            console.error('Error searching SKUs:', error);
        }
    }, 300);
}

async function selectAdjustSku(skuId, skuCode, productName) {
    document.getElementById('adjustSkuId').value = skuId;
    document.getElementById('adjustSkuSearch').value = skuCode;
    document.getElementById('adjustSkuResults').style.display = 'none';
    
    try {
        const response = await fetch(`${API_URL}/admin/skus/${skuId}/warehouse-stock`);
        if (!response.ok) throw new Error('Failed to load SKU stock');
        adjustSkuData = await response.json();
        
        document.getElementById('adjustSkuDetails').innerHTML = `
            <strong>${escapeHtml(adjustSkuData.sku_code)}</strong> - ${escapeHtml(adjustSkuData.product_name)}<br>
            <small>สต็อกรวม: ${adjustSkuData.total_stock}</small>
        `;
        document.getElementById('adjustSkuInfo').style.display = 'block';
        
        updateAdjustStock();
    } catch (error) {
        console.error('Error loading SKU stock:', error);
    }
}

function updateAdjustStock() {
    if (!adjustSkuData) return;
    
    const warehouseId = document.getElementById('adjustWarehouse').value;
    const stockInfoDiv = document.getElementById('adjustWarehouseStock');
    
    if (warehouseId && adjustSkuData.warehouses) {
        const warehouse = adjustSkuData.warehouses.find(w => w.warehouse_id == warehouseId);
        const stock = warehouse ? warehouse.stock : 0;
        stockInfoDiv.innerHTML = `<span class="stock-available">สต็อกในโกดังนี้: <strong>${stock}</strong></span>`;
        stockInfoDiv.style.display = 'block';
    } else {
        stockInfoDiv.style.display = 'none';
    }
}

async function handleStockAdjustment(event) {
    event.preventDefault();
    
    const data = {
        sku_id: parseInt(document.getElementById('adjustSkuId').value),
        warehouse_id: parseInt(document.getElementById('adjustWarehouse').value),
        quantity: parseInt(document.getElementById('adjustQuantity').value),
        adjustment_type: document.getElementById('adjustType').value,
        notes: document.getElementById('adjustNotes').value.trim()
    };
    
    if (!data.sku_id) {
        showGlobalAlert('กรุณาเลือก SKU', 'error');
        return;
    }
    if (!data.warehouse_id) {
        showGlobalAlert('กรุณาเลือกโกดัง', 'error');
        return;
    }
    if (!data.adjustment_type) {
        showGlobalAlert('กรุณาเลือกประเภทการปรับ', 'error');
        return;
    }
    if (!data.quantity || data.quantity <= 0) {
        showGlobalAlert('กรุณาระบุจำนวนที่ถูกต้อง', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/admin/stock-adjustments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to adjust stock');
        }
        
        const result = await response.json();
        showGlobalAlert(`ปรับสต็อกเรียบร้อย (สต็อกใหม่: ${result.new_stock})`, 'success');
        resetAdjustmentForm();
        loadAdjustmentHistory();
    } catch (error) {
        console.error('Error adjusting stock:', error);
        showGlobalAlert(error.message || 'ไม่สามารถปรับสต็อกได้', 'error');
    }
}

function resetAdjustmentForm() {
    const form = document.getElementById('stockAdjustmentForm');
    if (form) {
        form.reset();
        const skuId = document.getElementById('adjustSkuId');
        if (skuId) skuId.value = '';
        const skuInfo = document.getElementById('adjustSkuInfo');
        if (skuInfo) skuInfo.style.display = 'none';
        const stockInfo = document.getElementById('adjustWarehouseStock');
        if (stockInfo) stockInfo.style.display = 'none';
    }
    adjustSkuData = null;
}

// ==================== BULK ADJUSTMENT FUNCTIONS ====================

function addBulkAdjustmentRow() {
    bulkRowId++;
    const container = document.getElementById('bulkSkuContainer');
    const newRow = document.createElement('div');
    newRow.className = 'bulk-sku-row';
    newRow.setAttribute('data-row-id', bulkRowId);
    newRow.style.cssText = 'padding: 16px; background: rgba(255,255,255,0.03); border-radius: 10px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.08);';
    newRow.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <span style="font-size: 13px; color: #9ca3af;">รายการที่ ${bulkRowId}</span>
            <button type="button" class="btn-icon" onclick="removeBulkAdjustmentRow(${bulkRowId})" title="ลบรายการ" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 6h18"></path>
                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                </svg>
            </button>
        </div>
        <div style="position: relative; margin-bottom: 12px;">
            <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">ค้นหา SKU *</label>
            <input type="text" class="form-input bulk-sku-search" style="padding: 12px; font-size: 14px; width: 100%;" placeholder="พิมพ์ชื่อสินค้าหรือรหัส SKU..." oninput="searchSkuForBulkAdjust(this, ${bulkRowId})">
            <div class="bulk-sku-results"></div>
            <input type="hidden" class="bulk-sku-id">
            <div class="bulk-sku-name" style="font-size: 12px; color: #9ca3af; margin-top: 4px; min-height: 18px;"></div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div>
                <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">สต็อกปัจจุบัน</label>
                <div class="bulk-current-stock" style="padding: 12px; font-size: 16px; font-weight: 600; text-align: center; background: rgba(255,255,255,0.05); border-radius: 8px; color: #9ca3af;">-</div>
            </div>
            <div>
                <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">จำนวนที่ปรับ *</label>
                <input type="number" class="form-input bulk-quantity" min="1" placeholder="0" style="padding: 12px; font-size: 16px; text-align: center; width: 100%;">
            </div>
        </div>
    `;
    container.appendChild(newRow);
    updateBulkAdjustSummary();
}

function removeBulkAdjustmentRow(rowId) {
    const row = document.querySelector(`.bulk-sku-row[data-row-id="${rowId}"]`);
    if (row) {
        const container = document.getElementById('bulkSkuContainer');
        if (container.children.length > 1) {
            row.remove();
        } else {
            row.querySelector('.bulk-sku-search').value = '';
            row.querySelector('.bulk-sku-id').value = '';
            row.querySelector('.bulk-sku-name').textContent = '';
            row.querySelector('.bulk-current-stock').textContent = '-';
            row.querySelector('.bulk-quantity').value = '';
        }
        delete bulkSkuCache[rowId];
    }
    updateBulkAdjustSummary();
}

function searchSkuForBulkAdjust(input, rowId) {
    const keyword = input.value.trim();
    clearTimeout(bulkSearchTimeouts[rowId]);
    
    const row = document.querySelector(`.bulk-sku-row[data-row-id="${rowId}"]`);
    const resultsDiv = row.querySelector('.bulk-sku-results');
    
    if (!keyword || keyword.length < 1) {
        resultsDiv.classList.remove('show');
        return;
    }
    
    bulkSearchTimeouts[rowId] = setTimeout(async () => {
        try {
            const response = await fetch(`${API_URL}/admin/skus/search?keyword=${encodeURIComponent(keyword)}`);
            const data = await response.json();
            
            if (!response.ok) {
                console.error('SKU search failed:', response.status, data);
                resultsDiv.innerHTML = '<div class="sku-result-item" style="opacity: 0.6; justify-content: center;">เกิดข้อผิดพลาด</div>';
                resultsDiv.classList.add('show');
                return;
            }
            
            if (data.length === 0) {
                resultsDiv.innerHTML = '<div class="sku-result-item" style="opacity: 0.6; justify-content: center;">ไม่พบ SKU</div>';
            } else {
                resultsDiv.innerHTML = data.slice(0, 10).map(s => `
                    <div class="sku-result-item" onclick="selectBulkSku(${rowId}, ${s.id}, '${escapeHtml(s.sku_code)}', '${escapeHtml(s.product_name)}', ${s.total_stock})">
                        <div><strong>${escapeHtml(s.sku_code)}</strong> - ${escapeHtml(s.product_name)}</div>
                        <span class="stock-badge">สต็อก: ${s.total_stock}</span>
                    </div>
                `).join('');
            }
            resultsDiv.classList.add('show');
        } catch (error) {
            console.error('Error searching SKUs:', error);
            resultsDiv.innerHTML = '<div class="sku-result-item" style="opacity: 0.6; justify-content: center;">เกิดข้อผิดพลาด</div>';
            resultsDiv.classList.add('show');
        }
    }, 200);
}

async function selectBulkSku(rowId, skuId, skuCode, productName, totalStock) {
    const row = document.querySelector(`.bulk-sku-row[data-row-id="${rowId}"]`);
    if (!row) return;
    
    row.querySelector('.bulk-sku-search').value = skuCode;
    row.querySelector('.bulk-sku-id').value = skuId;
    row.querySelector('.bulk-sku-name').textContent = productName;
    row.querySelector('.bulk-sku-results').classList.remove('show');
    
    const warehouseId = document.getElementById('bulkWarehouse').value;
    
    if (warehouseId) {
        try {
            const response = await fetch(`${API_URL}/admin/skus/${skuId}/warehouse-stock`);
            if (response.ok) {
                const data = await response.json();
                bulkSkuCache[rowId] = data;
                const warehouse = data.warehouses?.find(w => w.warehouse_id == warehouseId);
                const stock = warehouse ? warehouse.stock : 0;
                row.querySelector('.bulk-current-stock').textContent = stock;
            }
        } catch (error) {
            row.querySelector('.bulk-current-stock').textContent = totalStock;
        }
    } else {
        row.querySelector('.bulk-current-stock').textContent = totalStock;
    }
    
    updateBulkAdjustSummary();
}

function updateBulkAdjustSummary() {
    const rows = document.querySelectorAll('.bulk-sku-row');
    let count = 0;
    rows.forEach(row => {
        const skuId = row.querySelector('.bulk-sku-id')?.value;
        if (skuId) count++;
    });
    const summary = document.getElementById('bulkAdjustSummary');
    if (summary) {
        summary.textContent = `รายการที่เลือก: ${count} SKU`;
    }
}

async function handleBulkAdjustment(event) {
    event.preventDefault();
    
    const warehouseId = parseInt(document.getElementById('bulkWarehouse').value);
    const adjustType = document.getElementById('bulkAdjustType').value;
    const notes = document.getElementById('bulkAdjustNotes').value.trim();
    
    if (!warehouseId) {
        showGlobalAlert('กรุณาเลือกโกดัง', 'error');
        return;
    }
    if (!adjustType) {
        showGlobalAlert('กรุณาเลือกประเภทการปรับ', 'error');
        return;
    }
    
    const rows = document.querySelectorAll('.bulk-sku-row');
    const adjustments = [];
    
    rows.forEach(row => {
        const skuId = parseInt(row.querySelector('.bulk-sku-id')?.value);
        const quantity = parseInt(row.querySelector('.bulk-quantity')?.value);
        if (skuId && quantity && quantity > 0) {
            adjustments.push({ sku_id: skuId, quantity: quantity });
        }
    });
    
    if (adjustments.length === 0) {
        showGlobalAlert('กรุณาเลือก SKU และระบุจำนวนอย่างน้อย 1 รายการ', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/admin/stock-adjustments/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                warehouse_id: warehouseId,
                adjustment_type: adjustType,
                notes: notes,
                adjustments: adjustments
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to adjust stock');
        }
        
        const result = await response.json();
        showGlobalAlert(`ปรับสต็อกเรียบร้อย ${result.success_count} รายการ`, 'success');
        resetBulkAdjustmentForm();
        loadAdjustmentHistory();
    } catch (error) {
        console.error('Error bulk adjusting stock:', error);
        showGlobalAlert(error.message || 'ไม่สามารถปรับสต็อกได้', 'error');
    }
}

function resetBulkAdjustmentForm() {
    document.getElementById('bulkAdjustmentForm').reset();
    const container = document.getElementById('bulkSkuContainer');
    container.innerHTML = `
        <div class="bulk-sku-row" data-row-id="1" style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 10px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.08);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 13px; color: #9ca3af;">รายการที่ 1</span>
                <button type="button" class="btn-icon" onclick="removeBulkAdjustmentRow(1)" title="ลบรายการ" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 6h18"></path>
                        <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                        <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                    </svg>
                </button>
            </div>
            <div style="position: relative; margin-bottom: 12px;">
                <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">ค้นหา SKU *</label>
                <input type="text" class="form-input bulk-sku-search" style="padding: 12px; font-size: 14px; width: 100%;" placeholder="พิมพ์ชื่อสินค้าหรือรหัส SKU..." oninput="searchSkuForBulkAdjust(this, 1)">
                <div class="bulk-sku-results"></div>
                <input type="hidden" class="bulk-sku-id">
                <div class="bulk-sku-name" style="font-size: 12px; color: #9ca3af; margin-top: 4px; min-height: 18px;"></div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">สต็อกปัจจุบัน</label>
                    <div class="bulk-current-stock" style="padding: 12px; font-size: 16px; font-weight: 600; text-align: center; background: rgba(255,255,255,0.05); border-radius: 8px; color: #9ca3af;">-</div>
                </div>
                <div>
                    <label class="form-label" style="font-size: 13px; margin-bottom: 6px; display: block;">จำนวนที่ปรับ *</label>
                    <input type="number" class="form-input bulk-quantity" min="1" placeholder="0" style="padding: 12px; font-size: 16px; text-align: center; width: 100%;">
                </div>
            </div>
        </div>
    `;
    bulkRowId = 1;
    bulkSkuCache = {};
    updateBulkAdjustSummary();
}

const ADJUSTMENT_TYPE_LABELS = {
    'shopee_sale': 'ขาย Shopee',
    'lazada_sale': 'ขาย Lazada',
    'tiktok_sale': 'ขาย TikTok',
    'facebook_sale': 'ขาย Facebook',
    'line_sale': 'ขาย LINE',
    'offline_sale': 'ขายหน้าร้าน',
    'other_sale': 'ขายช่องทางอื่น',
    'damaged': 'ชำรุด/เสียหาย',
    'lost': 'สูญหาย',
    'expired': 'หมดอายุ',
    'miscount_decrease': 'นับผิด (ลด)',
    'miscount_increase': 'นับผิด (เพิ่ม)',
    'stock_in': 'รับเข้าสต็อก',
    'return': 'รับคืนสินค้า',
    'other_increase': 'อื่นๆ (เพิ่ม)',
    'other_decrease': 'อื่นๆ (ลด)',
    'transfer_in': 'ย้ายเข้า',
    'transfer_out': 'ย้ายออก'
};

// ==================== PRODUCT-BASED STOCK ADJUSTMENT ====================

function searchProductForAdjust(keyword) {
    clearTimeout(productAdjustSearchTimeout);
    if (!keyword || keyword.length < 2) {
        document.getElementById('productSearchResults').style.display = 'none';
        return;
    }
    
    productAdjustSearchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`${API_URL}/admin/products?search=${encodeURIComponent(keyword)}&limit=20`);
            if (!response.ok) throw new Error('Failed to search products');
            const data = await response.json();
            const products = data.products || data;
            
            const resultsDiv = document.getElementById('productSearchResults');
            if (products.length === 0) {
                resultsDiv.innerHTML = '<div style="padding: 16px; text-align: center; color: #9ca3af;">ไม่พบสินค้า</div>';
            } else {
                resultsDiv.innerHTML = products.map(p => `
                    <div class="sku-result-item" onclick="selectProductForAdjust(${p.id})" style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <img src="${p.image_url || '/static/images/placeholder.png'}" alt="" style="width: 40px; height: 40px; object-fit: cover; border-radius: 6px; background: rgba(255,255,255,0.1);">
                            <div>
                                <strong style="font-size: 14px;">${escapeHtml(p.name)}</strong>
                                <div style="font-size: 12px; color: #9ca3af;">${escapeHtml(p.parent_sku)} | ${p.sku_count || '-'} SKU</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            resultsDiv.style.display = 'block';
        } catch (error) {
            console.error('Error searching products:', error);
        }
    }, 300);
}

async function selectProductForAdjust(productId) {
    document.getElementById('productSearchResults').style.display = 'none';
    document.getElementById('productSearchForAdjust').value = '';
    
    try {
        const response = await fetch(`${API_URL}/admin/products/${productId}/skus-with-stock`);
        if (!response.ok) throw new Error('Failed to load product SKUs');
        selectedProductData = await response.json();
        
        // Update product card
        const product = selectedProductData.product;
        document.getElementById('selectedProductImage').src = product.image_url || '/static/images/placeholder.png';
        document.getElementById('selectedProductName').textContent = product.name;
        document.getElementById('selectedProductSku').textContent = `Parent SKU: ${product.parent_sku}`;
        
        // Count total rows (SKU x warehouse combinations)
        let totalRows = 0;
        selectedProductData.skus.forEach(sku => {
            totalRows += sku.warehouses.length || 1;
        });
        document.getElementById('selectedProductSkuCount').textContent = `${selectedProductData.sku_count} SKU | ${selectedProductData.warehouses.length} โกดัง`;
        
        // Render SKU table (one row per SKU x warehouse)
        renderProductSkuTable();
        
        // Show card
        document.getElementById('selectedProductCard').style.display = 'block';
    } catch (error) {
        console.error('Error loading product for adjustment:', error);
        showGlobalAlert('ไม่สามารถโหลดข้อมูลสินค้าได้', 'error');
    }
}

function renderProductSkuTable() {
    if (!selectedProductData) return;
    
    const tbody = document.getElementById('productSkuTableBody');
    const rows = [];
    
    // Generate one row per SKU x warehouse combination
    selectedProductData.skus.forEach(sku => {
        if (sku.warehouses && sku.warehouses.length > 0) {
            sku.warehouses.forEach(warehouse => {
                const stockBg = warehouse.stock <= 0 ? 'rgba(239,68,68,0.2)' : warehouse.stock <= 5 ? 'rgba(245,158,11,0.2)' : 'rgba(16,185,129,0.2)';
                const stockBorder = warehouse.stock <= 0 ? '#ef4444' : warehouse.stock <= 5 ? '#f59e0b' : '#10b981';
                rows.push(`
                    <tr data-sku-id="${sku.id}" data-warehouse-id="${warehouse.warehouse_id}">
                        <td style="padding: 10px 14px; font-size: 13px; color: #fff;"><strong>${escapeHtml(sku.sku_code)}</strong></td>
                        <td style="padding: 10px 14px; font-size: 12px; color: #e5e7eb;">${escapeHtml(sku.variant_display)}</td>
                        <td style="padding: 10px 14px; font-size: 13px; color: #fff;">${escapeHtml(warehouse.warehouse_name)}</td>
                        <td style="padding: 10px 14px; text-align: center;">
                            <span style="display: inline-block; min-width: 50px; padding: 6px 12px; background: ${stockBg}; border: 1px solid ${stockBorder}; border-radius: 6px; font-weight: 700; font-size: 14px; color: #fff;">${warehouse.stock}</span>
                        </td>
                        <td style="padding: 10px 14px; text-align: center;">
                            <input type="number" class="form-input sku-adjust-qty" min="0" placeholder="0" 
                                   style="width: 80px; padding: 8px; font-size: 14px; text-align: center; color: #fff;"
                                   oninput="updateProductAdjustSummary()">
                        </td>
                    </tr>
                `);
            });
        } else {
            // No warehouse data - show empty row
            rows.push(`
                <tr data-sku-id="${sku.id}" data-warehouse-id="">
                    <td style="padding: 10px 14px; font-size: 13px; color: #fff;"><strong>${escapeHtml(sku.sku_code)}</strong></td>
                    <td style="padding: 10px 14px; font-size: 12px; color: #e5e7eb;">${escapeHtml(sku.variant_display)}</td>
                    <td style="padding: 10px 14px; font-size: 13px; color: #9ca3af;">-</td>
                    <td style="padding: 10px 14px; text-align: center;">
                        <span style="display: inline-block; min-width: 50px; padding: 6px 12px; background: rgba(156,163,175,0.2); border: 1px solid #9ca3af; border-radius: 6px; font-weight: 700; font-size: 14px; color: #fff;">0</span>
                    </td>
                    <td style="padding: 10px 14px; text-align: center;">
                        <input type="number" class="form-input sku-adjust-qty" min="0" placeholder="0" 
                               style="width: 80px; padding: 8px; font-size: 14px; text-align: center; color: #fff;"
                               oninput="updateProductAdjustSummary()">
                    </td>
                </tr>
            `);
        }
    });
    
    tbody.innerHTML = rows.join('');
    updateProductAdjustSummary();
}

function updateProductSkuStocks() {
    if (!selectedProductData) return;
    
    const warehouseId = document.getElementById('productAdjustWarehouse').value;
    const tbody = document.getElementById('productSkuTableBody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const skuId = parseInt(row.dataset.skuId);
        const sku = selectedProductData.skus.find(s => s.id === skuId);
        if (sku) {
            const stockCell = row.querySelector('.sku-warehouse-stock');
            if (warehouseId) {
                const warehouse = sku.warehouses.find(w => w.warehouse_id == warehouseId);
                stockCell.textContent = warehouse ? warehouse.stock : 0;
            } else {
                stockCell.textContent = '-';
            }
        }
    });
}

function updateProductAdjustSummary() {
    const inputs = document.querySelectorAll('#productSkuTableBody .sku-adjust-qty');
    let count = 0;
    inputs.forEach(input => {
        if (input.value && parseInt(input.value) > 0) count++;
    });
    document.getElementById('productAdjustSummary').textContent = `รายการที่กรอกจำนวน: ${count} SKU`;
}

function fillAllSkuQuantity() {
    const qty = document.getElementById('fillAllQuantityValue').value || 1;
    const inputs = document.querySelectorAll('#productSkuTableBody .sku-adjust-qty');
    inputs.forEach(input => {
        input.value = qty;
    });
    updateProductAdjustSummary();
}

function clearAllSkuQuantity() {
    const inputs = document.querySelectorAll('#productSkuTableBody .sku-adjust-qty');
    inputs.forEach(input => {
        input.value = '';
    });
    updateProductAdjustSummary();
}

function clearSelectedProduct() {
    selectedProductData = null;
    document.getElementById('selectedProductCard').style.display = 'none';
    document.getElementById('productSearchForAdjust').value = '';
    document.getElementById('productSkuTableBody').innerHTML = '';
}

async function submitProductAdjustment() {
    if (!selectedProductData) {
        showGlobalAlert('กรุณาเลือกสินค้าก่อน', 'error');
        return;
    }
    
    const adjustType = document.getElementById('productAdjustType').value;
    const notes = document.getElementById('productAdjustNotes').value.trim();
    
    if (!adjustType) {
        showGlobalAlert('กรุณาเลือกประเภทการปรับ', 'error');
        return;
    }
    
    // Collect adjustments - each row has its own warehouse_id
    const adjustments = [];
    const rows = document.querySelectorAll('#productSkuTableBody tr');
    rows.forEach(row => {
        const skuId = parseInt(row.dataset.skuId);
        const warehouseId = row.getAttribute('data-warehouse-id');
        const qtyInput = row.querySelector('.sku-adjust-qty');
        const qty = parseInt(qtyInput.value) || 0;
        if (qty > 0 && warehouseId && warehouseId !== '' && warehouseId !== 'undefined') {
            adjustments.push({
                sku_id: skuId,
                warehouse_id: parseInt(warehouseId),
                quantity: qty,
                adjustment_type: adjustType,
                notes: notes
            });
        }
    });
    
    if (adjustments.length === 0) {
        showGlobalAlert('กรุณากรอกจำนวนอย่างน้อย 1 รายการ', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/admin/stock-adjustments/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ adjustments })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to submit adjustments');
        }
        
        const result = await response.json();
        showGlobalAlert(`บันทึกการปรับสต็อก ${result.success_count} รายการเรียบร้อย`, 'success');
        
        // Clear form and reload
        clearSelectedProduct();
        loadAdjustmentHistory();
    } catch (error) {
        console.error('Error submitting adjustments:', error);
        showGlobalAlert(error.message || 'เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function loadAdjustmentHistory() {
    const adjustType = document.getElementById('adjustFilterType')?.value;
    const dateFrom = document.getElementById('adjustDateFrom')?.value;
    const dateTo = document.getElementById('adjustDateTo')?.value;
    
    let url = `${API_URL}/admin/stock-adjustments?`;
    if (adjustType) url += `adjustment_type=${adjustType}&`;
    if (dateFrom) url += `date_from=${dateFrom}&`;
    if (dateTo) url += `date_to=${dateTo}&`;
    
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load adjustments');
        const adjustments = await response.json();
        
        const tbody = document.getElementById('adjustmentHistoryBody');
        if (!tbody) return;
        
        if (adjustments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 30px; opacity: 0.6;">ไม่มีข้อมูล</td></tr>';
            return;
        }
        
        tbody.innerHTML = adjustments.map(a => {
            const typeLabel = ADJUSTMENT_TYPE_LABELS[a.adjustment_type] || a.adjustment_type;
            const isDecrease = a.quantity_change < 0;
            const qtyBg = isDecrease ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)';
            const qtyBorder = isDecrease ? '#ef4444' : '#10b981';
            const qtySign = a.quantity_change > 0 ? '+' : '';
            return `
                <tr>
                    <td style="color: #fff;">${formatDateTime(a.created_at)}</td>
                    <td style="color: #fff;"><strong>${escapeHtml(a.sku_code)}</strong><br><small style="color: #e5e7eb;">${escapeHtml(a.product_name)}</small></td>
                    <td style="color: #fff;">${escapeHtml(a.warehouse_name)}</td>
                    <td><span class="type-badge" style="color: #fff;">${typeLabel}</span></td>
                    <td style="text-align: center;">
                        <span style="display: inline-block; min-width: 50px; padding: 4px 10px; background: ${qtyBg}; border: 1px solid ${qtyBorder}; border-radius: 6px; font-weight: 700; color: #fff;">${qtySign}${a.quantity_change}</span>
                    </td>
                    <td style="color: #fff;">${a.created_by_name || '-'}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading adjustment history:', error);
    }
}

// ==================== STOCK HISTORY FUNCTIONS ====================

async function loadStockHistoryPage() {
    await loadWarehouseDropdowns('history');
    loadStockHistory();
}

async function loadStockHistory() {
    const search = document.getElementById('historySearch')?.value;
    const warehouseId = document.getElementById('historyWarehouse')?.value;
    const changeType = document.getElementById('historyChangeType')?.value;
    const dateFrom = document.getElementById('historyDateFrom')?.value;
    const dateTo = document.getElementById('historyDateTo')?.value;
    
    let url = `${API_URL}/admin/stock-audit-log?`;
    if (warehouseId) url += `warehouse_id=${warehouseId}&`;
    if (changeType) url += `change_type=${changeType}&`;
    if (dateFrom) url += `date_from=${dateFrom}&`;
    if (dateTo) url += `date_to=${dateTo}&`;
    
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load stock history');
        let logs = await response.json();
        
        if (search) {
            const searchLower = search.toLowerCase();
            logs = logs.filter(l => 
                l.sku_code.toLowerCase().includes(searchLower) ||
                l.product_name.toLowerCase().includes(searchLower)
            );
        }
        
        const tbody = document.getElementById('stockHistoryBody');
        if (!tbody) return;
        
        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 30px; opacity: 0.6;">ไม่มีข้อมูล</td></tr>';
            return;
        }
        
        tbody.innerHTML = logs.map(l => {
            const typeLabel = ADJUSTMENT_TYPE_LABELS[l.change_type] || l.change_type;
            const change = l.quantity_after - l.quantity_before;
            const isDecrease = change < 0;
            const changeBg = isDecrease ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)';
            const changeBorder = isDecrease ? '#ef4444' : '#10b981';
            const changeSign = change > 0 ? '+' : '';
            return `
                <tr>
                    <td style="color: #fff;">${formatDateTime(l.created_at)}</td>
                    <td style="color: #fff;"><strong>${escapeHtml(l.sku_code)}</strong><br><small style="color: #e5e7eb;">${escapeHtml(l.product_name)}</small></td>
                    <td style="color: #fff;">${l.warehouse_name ? escapeHtml(l.warehouse_name) : '-'}</td>
                    <td><span class="type-badge" style="color: #fff;">${typeLabel}</span></td>
                    <td style="color: #fff; text-align: center;">${l.quantity_before}</td>
                    <td style="color: #fff; text-align: center;">${l.quantity_after}</td>
                    <td style="text-align: center;">
                        <span style="display: inline-block; min-width: 50px; padding: 4px 10px; background: ${changeBg}; border: 1px solid ${changeBorder}; border-radius: 6px; font-weight: 700; color: #fff;">${changeSign}${change}</span>
                    </td>
                    <td style="color: #fff;">${l.created_by_name || '-'}</td>
                    <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; color: #e5e7eb;">${l.notes ? escapeHtml(l.notes) : '-'}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading stock history:', error);
    }
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('th-TH', { 
        year: 'numeric', 
        month: '2-digit', 
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ==================== STOCK SUMMARY & ALERTS ====================

let stockMovementChart = null;

async function loadLowStockBadge() {
    try {
        const response = await fetch(`${API_URL}/admin/stock/low-stock-count`);
        if (!response.ok) return;
        const data = await response.json();
        
        const badge = document.getElementById('lowStockBadge');
        if (badge) {
            if (data.total_alerts > 0) {
                badge.textContent = data.total_alerts;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading low stock badge:', error);
    }
}

async function loadStockSummaryPage() {
    try {
        const response = await fetch(`${API_URL}/admin/stock/summary`);
        if (!response.ok) throw new Error('Failed to load summary');
        const data = await response.json();
        
        document.getElementById('summaryTotalStock').textContent = data.total_stock.toLocaleString();
        document.getElementById('summaryNormalStock').textContent = (data.stock_status.normal_stock || 0).toLocaleString();
        document.getElementById('summaryLowStock').textContent = (data.stock_status.low_stock || 0).toLocaleString();
        document.getElementById('summaryOutOfStock').textContent = (data.stock_status.out_of_stock || 0).toLocaleString();
        
        const warehouseList = document.getElementById('warehouseStockList');
        if (data.by_warehouse.length === 0) {
            warehouseList.innerHTML = '<div style="text-align: center; padding: 20px; color: #9ca3af;">ไม่มีโกดัง</div>';
        } else {
            warehouseList.innerHTML = data.by_warehouse.map(w => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <div>
                        <div style="font-weight: 600; color: #fff;">${escapeHtml(w.name)}</div>
                        <div style="font-size: 12px; color: #9ca3af;">${w.sku_count} SKU</div>
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: #ffffff;">${parseInt(w.stock).toLocaleString()}</div>
                </div>
            `).join('');
        }
        
        renderStockMovementChart(data.movements);
        loadLowStockItems();
        
    } catch (error) {
        console.error('Error loading stock summary:', error);
    }
}

function renderStockMovementChart(movements) {
    const ctx = document.getElementById('stockMovementChart');
    if (!ctx) return;
    
    if (stockMovementChart) {
        stockMovementChart.destroy();
    }
    
    const labels = movements.map(m => {
        const d = new Date(m.date);
        return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
    });
    const stockIn = movements.map(m => parseInt(m.stock_in) || 0);
    const stockOut = movements.map(m => parseInt(m.stock_out) || 0);
    
    stockMovementChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'เข้า',
                    data: stockIn,
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderRadius: 4,
                    barPercentage: 0.6,
                    categoryPercentage: 0.7
                },
                {
                    label: 'ออก',
                    data: stockOut,
                    backgroundColor: 'rgba(239, 68, 68, 0.7)',
                    borderRadius: 4,
                    barPercentage: 0.6,
                    categoryPercentage: 0.7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { 
                    beginAtZero: true, 
                    grid: { color: 'rgba(255,255,255,0.1)' }, 
                    ticks: { color: '#9ca3af', stepSize: 5 }
                },
                x: { 
                    grid: { display: false }, 
                    ticks: { color: '#9ca3af' } 
                }
            },
            plugins: {
                legend: { 
                    position: 'top',
                    labels: { color: '#fff', boxWidth: 12, padding: 15 } 
                }
            }
        }
    });
}

async function loadLowStockItems() {
    const filter = document.getElementById('lowStockFilter')?.value || 'all';
    
    try {
        const response = await fetch(`${API_URL}/admin/stock/low-stock-items?filter=${filter}`);
        if (!response.ok) throw new Error('Failed to load low stock items');
        const items = await response.json();
        
        const tbody = document.getElementById('lowStockItemsBody');
        if (!tbody) return;
        
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 30px; color: #9ca3af;">ไม่มีรายการสต็อกต่ำ</td></tr>';
            return;
        }
        
        tbody.innerHTML = items.map(item => {
            const stockBg = item.total_stock === 0 ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)';
            const stockBorder = item.total_stock === 0 ? '#ef4444' : '#f59e0b';
            return `
                <tr>
                    <td style="padding: 12px 16px; color: #fff;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <img src="${item.image_url || '/static/images/placeholder.png'}" style="width: 36px; height: 36px; border-radius: 6px; object-fit: cover;">
                            <span>${escapeHtml(item.product_name)}</span>
                        </div>
                    </td>
                    <td style="padding: 12px 16px; color: #e5e7eb;"><strong>${escapeHtml(item.sku_code)}</strong></td>
                    <td style="padding: 12px 16px; text-align: center;">
                        <span style="display: inline-block; min-width: 50px; padding: 4px 10px; background: ${stockBg}; border: 1px solid ${stockBorder}; border-radius: 6px; font-weight: 700; color: #fff;">${item.total_stock}</span>
                    </td>
                    <td style="padding: 12px 16px; text-align: center; color: #9ca3af;">${item.threshold}</td>
                    <td style="padding: 12px 16px; text-align: center;">
                        <button class="btn" style="padding: 6px 12px; font-size: 12px;" onclick="goToAdjustStock(${item.id})">เพิ่มสต็อก</button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading low stock items:', error);
    }
}

function goToAdjustStock(skuId) {
    navigateTo('stock-adjustment');
}

// ==================== STOCK IMPORT ====================

async function handleStockImport(event) {
    event.preventDefault();
    
    const fileInput = document.getElementById('importFile');
    const adjustType = document.getElementById('importAdjustType').value;
    const notes = document.getElementById('importNotes').value;
    
    if (!fileInput.files[0]) {
        showGlobalAlert('กรุณาเลือกไฟล์ CSV', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('adjustment_type', adjustType);
    formData.append('notes', notes);
    
    try {
        const response = await fetch(`${API_URL}/admin/stock/import`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        const resultCard = document.getElementById('importResultCard');
        const resultContent = document.getElementById('importResultContent');
        
        if (response.ok) {
            showGlobalAlert(result.message, 'success');
            resultContent.innerHTML = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
                    <div style="background: rgba(16,185,129,0.1); border: 1px solid #10b981; border-radius: 8px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 700; color: #10b981;">${result.success_count}</div>
                        <div style="font-size: 13px; color: #9ca3af;">สำเร็จ</div>
                    </div>
                    <div style="background: rgba(239,68,68,0.1); border: 1px solid #ef4444; border-radius: 8px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 700; color: #ef4444;">${result.error_count}</div>
                        <div style="font-size: 13px; color: #9ca3af;">ล้มเหลว</div>
                    </div>
                </div>
                ${result.errors && result.errors.length > 0 ? `
                    <div style="background: rgba(239,68,68,0.1); border-radius: 8px; padding: 12px; max-height: 200px; overflow-y: auto;">
                        <div style="font-weight: 600; color: #ef4444; margin-bottom: 8px;">รายการที่ผิดพลาด:</div>
                        ${result.errors.map(e => `<div style="font-size: 12px; color: #fca5a5; margin-bottom: 4px;">${escapeHtml(e)}</div>`).join('')}
                    </div>
                ` : ''}
            `;
            resultCard.style.display = 'block';
            document.getElementById('stockImportForm').reset();
            loadLowStockBadge();
        } else {
            showGlobalAlert(result.error || 'นำเข้าล้มเหลว', 'error');
            resultCard.style.display = 'none';
        }
    } catch (error) {
        console.error('Error importing stock:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการนำเข้า', 'error');
    }
}

// ==================== EXPORT FUNCTIONS ====================

function exportStockHistory() {
    const warehouseId = document.getElementById('historyWarehouse')?.value || '';
    const dateFrom = document.getElementById('historyDateFrom')?.value || '';
    const dateTo = document.getElementById('historyDateTo')?.value || '';
    
    let url = `${API_URL}/admin/stock/export?type=history`;
    if (warehouseId) url += `&warehouse_id=${warehouseId}`;
    if (dateFrom) url += `&date_from=${dateFrom}`;
    if (dateTo) url += `&date_to=${dateTo}`;
    
    window.location.href = url;
}

function exportCurrentStock() {
    window.location.href = `${API_URL}/admin/stock/export?type=current`;
}

function viewSlipFullscreen(imageUrl) {
    if (!imageUrl) {
        showGlobalAlert('ไม่พบภาพสลิป', 'error');
        return;
    }
    
    const modal = document.createElement('div');
    modal.id = 'slipFullscreenModal';
    modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 10000; display: flex; align-items: center; justify-content: center; cursor: zoom-out;';
    modal.onclick = () => modal.remove();
    
    modal.innerHTML = `
        <img src="${imageUrl}" alt="Payment Slip" style="max-width: 90%; max-height: 90%; object-fit: contain; border-radius: 8px; box-shadow: 0 10px 50px rgba(0,0,0,0.5);">
        <button onclick="event.stopPropagation(); this.parentElement.remove();" style="position: absolute; top: 20px; right: 20px; width: 40px; height: 40px; background: rgba(255,255,255,0.2); border: none; border-radius: 50%; color: #fff; font-size: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center;">×</button>
    `;
    
    document.body.appendChild(modal);
}

