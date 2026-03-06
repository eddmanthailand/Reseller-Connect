let allProducts = [];
let filteredProducts = [];
let selectedProducts = new Set();
let currentStatusFilter = 'all';
let brands = [];
let categories = [];

// Load products with Lazada-style features
async function loadProducts() {
    const productTableBody = document.getElementById('productTableBody');
    if (!productTableBody) return;

    try {
        const response = await fetch(`${API_URL}/products`);
        if (!response.ok) throw new Error('Failed to load products');

        allProducts = await response.json();
        
        // Load brands and categories for filters
        await loadFiltersData();
        
        // Apply filters and render
        applyFiltersAndRender();
        
        // Setup filter event listeners
        setupProductFilters();
        
    } catch (error) {
        console.error('Error loading products:', error);
        productTableBody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px;">
                    <div style="color: rgb(239, 68, 68); opacity: 0.8;">เกิดข้อผิดพลาดในการโหลดข้อมูลสินค้า</div>
                </td>
            </tr>
        `;
    }
}

// Load filter data (brands and categories)
async function loadFiltersData() {
    try {
        // Load brands
        const brandsRes = await fetch(`${API_URL}/brands`);
        if (brandsRes.ok) {
            brands = await brandsRes.json();
            const brandSelect = document.getElementById('filterBrand');
            if (brandSelect) {
                brandSelect.innerHTML = '<option value="">ทุกแบรนด์</option>';
                brands.forEach(brand => {
                    brandSelect.innerHTML += `<option value="${brand.id}">${brand.name}</option>`;
                });
            }
        }
        
        // Load categories (use tree endpoint and flatten)
        try {
            const categoriesRes = await fetch(`${API_URL}/categories/tree`);
            if (categoriesRes.ok) {
                const categoryTree = await categoriesRes.json();
                categories = flattenCategoryTree(categoryTree);
                const categorySelect = document.getElementById('filterCategory');
                if (categorySelect) {
                    categorySelect.innerHTML = '<option value="">ทุกหมวดหมู่</option>';
                    categories.forEach(cat => {
                        categorySelect.innerHTML += `<option value="${cat.id}">${cat.name}</option>`;
                    });
                }
            }
        } catch (e) {
            console.log('Categories not available, skipping...');
        }
    } catch (error) {
        console.error('Error loading filter data:', error);
    }
}

// Flatten category tree to array
function flattenCategoryTree(tree, result = []) {
    if (!tree || !Array.isArray(tree)) return result;
    tree.forEach(cat => {
        result.push({ id: cat.id, name: cat.name });
        if (cat.children && cat.children.length > 0) {
            flattenCategoryTree(cat.children, result);
        }
    });
    return result;
}

// Setup product filter event listeners
function setupProductFilters() {
    // Status tabs
    document.querySelectorAll('.status-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.status-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentStatusFilter = tab.dataset.status;
            applyFiltersAndRender();
        });
    });
    
    // Search
    const searchInput = document.getElementById('searchProduct');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(() => applyFiltersAndRender(), 300));
    }
    
    // Brand filter
    const brandFilter = document.getElementById('filterBrand');
    if (brandFilter) {
        brandFilter.addEventListener('change', () => applyFiltersAndRender());
    }
    
    // Category filter
    const categoryFilter = document.getElementById('filterCategory');
    if (categoryFilter) {
        categoryFilter.addEventListener('change', () => applyFiltersAndRender());
    }
    
    // Stock filter
    const stockFilter = document.getElementById('filterStock');
    if (stockFilter) {
        stockFilter.addEventListener('change', () => applyFiltersAndRender());
    }
    
    // Sort
    const sortSelect = document.getElementById('sortBy');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => applyFiltersAndRender());
    }
}

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Apply filters and render products
function applyFiltersAndRender() {
    const searchTerm = document.getElementById('searchProduct')?.value.toLowerCase() || '';
    const brandId = document.getElementById('filterBrand')?.value || '';
    const categoryId = document.getElementById('filterCategory')?.value || '';
    const stockFilter = document.getElementById('filterStock')?.value || '';
    const sortBy = document.getElementById('sortBy')?.value || 'newest';
    
    // Filter
    filteredProducts = allProducts.filter(product => {
        // Status filter
        if (currentStatusFilter !== 'all' && product.status !== currentStatusFilter) {
            return false;
        }
        
        // Search filter
        if (searchTerm) {
            const searchMatch = 
                (product.name || '').toLowerCase().includes(searchTerm) ||
                (product.parent_sku || '').toLowerCase().includes(searchTerm);
            if (!searchMatch) return false;
        }
        
        // Brand filter
        if (brandId && product.brand_id != brandId) {
            return false;
        }
        
        // Stock filter (coerce to number to handle string/number variations)
        const lowCount = Number(product.low_stock_count ?? 0);
        const outCount = Number(product.out_of_stock_count ?? 0);
        if (stockFilter === 'low' && lowCount === 0) {
            return false;
        }
        if (stockFilter === 'out' && outCount === 0) {
            return false;
        }
        
        return true;
    });
    
    // Sort
    filteredProducts.sort((a, b) => {
        switch (sortBy) {
            case 'oldest':
                return new Date(a.created_at) - new Date(b.created_at);
            case 'name_asc':
                return (a.name || '').localeCompare(b.name || '');
            case 'name_desc':
                return (b.name || '').localeCompare(a.name || '');
            default: // newest
                return new Date(b.created_at) - new Date(a.created_at);
        }
    });
    
    // Update counts
    updateStatusCounts();
    
    // Render
    renderProducts();
}

// Update status tab counts
function updateStatusCounts() {
    const counts = {
        all: allProducts.length,
        active: allProducts.filter(p => p.status === 'active').length,
        inactive: allProducts.filter(p => p.status === 'inactive').length,
        draft: allProducts.filter(p => p.status === 'draft').length
    };
    
    document.getElementById('countAll').textContent = counts.all;
    document.getElementById('countActive').textContent = counts.active;
    document.getElementById('countInactive').textContent = counts.inactive;
    document.getElementById('countDraft').textContent = counts.draft;
    document.getElementById('productCount').textContent = counts.all;
}

// Render products table
function renderProducts() {
    const productTableBody = document.getElementById('productTableBody');
    if (!productTableBody) return;
    
    productTableBody.innerHTML = '';
    
    if (filteredProducts.length === 0) {
        productTableBody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px;">
                    <div style="opacity: 0.6;">ยังไม่มีสินค้าในระบบ</div>
                    <div style="margin-top: 10px;">
                        <a href="/admin/products/create" style="color: rgba(255, 255, 255, 0.9);">สร้างสินค้าแรกของคุณ</a>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    filteredProducts.forEach(product => {
        const row = document.createElement('tr');
        row.className = 'product-row-parent';
        row.dataset.productId = product.id;

        const imageHtml = product.first_image_url 
            ? `<img src="${product.first_image_url}" alt="${product.name}" class="product-thumb">`
            : `<div class="product-thumb-placeholder">📦</div>`;
        
        const status = product.status || 'active';
        const isActive = status === 'active';
        
        const minPrice = product.min_price || 0;
        const maxPrice = product.max_price || 0;
        const priceDisplay = minPrice === maxPrice 
            ? `฿${minPrice.toLocaleString()}`
            : `฿${minPrice.toLocaleString()} - ฿${maxPrice.toLocaleString()}`;
        
        const totalStock = product.total_stock || 0;
        const outOfStockCount = product.out_of_stock_count || 0;
        const lowStockCount = product.low_stock_count || 0;
        
        // Build stock warning badge for product row
        let stockWarningBadge = '';
        if (outOfStockCount > 0) {
            stockWarningBadge = `<span class="stock-badge stock-badge-out" style="margin-left: 6px;">${outOfStockCount} หมด</span>`;
        } else if (lowStockCount > 0) {
            stockWarningBadge = `<span class="stock-badge stock-badge-low" style="margin-left: 6px;">${lowStockCount} ใกล้หมด</span>`;
        }
        
        row.innerHTML = `
            <td>
                <input type="checkbox" class="row-checkbox product-checkbox" 
                       data-product-id="${product.id}" 
                       ${selectedProducts.has(product.id) ? 'checked' : ''}
                       onchange="toggleProductSelection(${product.id}, this.checked)">
            </td>
            <td>${imageHtml}</td>
            <td>
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <strong style="font-size: 12px;">${product.name || '-'}</strong>
                    <span style="font-size: 11px; opacity: 0.7;">SKU: ${product.parent_sku || '-'}</span>
                    ${product.brand_name ? `<span style="font-size: 10px; opacity: 0.6; background: rgba(168, 85, 247, 0.2); padding: 2px 6px; border-radius: 4px; display: inline-block; width: fit-content;">${product.brand_name}</span>` : ''}
                </div>
                <span class="sku-count-badge" onclick="toggleSkuRows(${product.id})" style="margin-left: 8px;">
                    ${product.sku_count || 0} SKUs
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-left: 2px;"><path d="m6 9 6 6 6-6"/></svg>
                </span>
            </td>
            <td>
                <button class="edit-price-btn" onclick="openEditPriceModal(${product.id})">
                    <span style="font-size: 11px;">${priceDisplay}</span>
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                </button>
            </td>
            <td>
                <div class="stock-display-readonly" style="display: flex; align-items: center; gap: 6px;">
                    <span style="font-size: 11px; font-weight: 500;">${totalStock.toLocaleString()}</span>
                    ${stockWarningBadge}
                </div>
            </td>
            <td>
                <label class="toggle-switch">
                    <input type="checkbox" ${isActive ? 'checked' : ''} onchange="toggleProductStatus(${product.id}, this.checked)">
                    <span class="toggle-slider"></span>
                </label>
            </td>
            <td>
                <div class="action-btns">
                    <button onclick="toggleProductFeatured(${product.id}, ${!product.is_featured})" class="action-btn" title="${product.is_featured ? 'ยกเลิกโปรโมท' : 'ตั้งเป็นสินค้าโปรโมท'}" style="background:${product.is_featured ? 'rgba(251,191,36,0.25)' : 'rgba(255,255,255,0.07)'}; border:1px solid ${product.is_featured ? 'rgba(251,191,36,0.6)' : 'rgba(255,255,255,0.15)'}; color:${product.is_featured ? '#fbbf24' : 'rgba(255,255,255,0.5)'}; padding:4px 8px; border-radius:6px; font-size:14px; cursor:pointer;">★</button>
                    <a href="/admin/products/edit/${product.id}" class="action-btn btn-edit-sm">แก้ไข</a>
                    <button onclick="deleteProduct(${product.id}, '${(product.name || '').replace(/'/g, "\\'")}')" class="action-btn btn-delete-sm">ลบ</button>
                </div>
            </td>
        `;
        
        productTableBody.appendChild(row);
        
        // Add SKU rows (hidden by default)
        if (product.skus && product.skus.length > 0) {
            const threshold = product.low_stock_threshold || 5;
            product.skus.forEach(sku => {
                const skuRow = document.createElement('tr');
                skuRow.className = 'sku-row';
                skuRow.dataset.parentId = product.id;
                
                // Determine stock status
                const stock = sku.stock || 0;
                let stockStatusClass = '';
                let stockBadge = '';
                if (stock === 0) {
                    stockStatusClass = 'stock-out';
                    stockBadge = '<span class="stock-badge stock-badge-out">หมด</span>';
                } else if (stock <= threshold) {
                    stockStatusClass = 'stock-low';
                    stockBadge = '<span class="stock-badge stock-badge-low">ใกล้หมด</span>';
                }
                
                skuRow.innerHTML = `
                    <td></td>
                    <td></td>
                    <td style="padding-left: 48px;">
                        <span class="sku-indicator">└</span>
                        <span style="font-size: 11px;">${sku.sku_code || '-'}</span>
                        <span style="font-size: 10px; opacity: 0.6; margin-left: 8px;">${sku.variant_name || ''}</span>
                    </td>
                    <td>
                        <span class="sku-value-display">${(sku.price || 0).toLocaleString()}</span>
                    </td>
                    <td>
                        <div class="sku-stock-display ${stockStatusClass}">
                            <span class="sku-value-display">${stock.toLocaleString()}</span>
                            ${stockBadge}
                        </div>
                    </td>
                    <td>
                        <label class="toggle-switch">
                            <input type="checkbox" ${sku.is_active !== false ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </td>
                    <td></td>
                `;
                
                productTableBody.appendChild(skuRow);
            });
        }
    });
}

// Toggle SKU rows visibility
function toggleSkuRows(productId) {
    const parentRow = document.querySelector(`tr[data-product-id="${productId}"]`);
    const skuRows = document.querySelectorAll(`tr.sku-row[data-parent-id="${productId}"]`);
    
    const isExpanded = parentRow.classList.contains('expanded');
    
    if (isExpanded) {
        parentRow.classList.remove('expanded');
        skuRows.forEach(row => row.classList.remove('show'));
    } else {
        parentRow.classList.add('expanded');
        skuRows.forEach(row => row.classList.add('show'));
    }
}

// Toggle product selection
function toggleProductSelection(productId, isSelected) {
    if (isSelected) {
        selectedProducts.add(productId);
    } else {
        selectedProducts.delete(productId);
    }
    updateBulkActionsBar();
}

// Toggle select all
function toggleSelectAll(checkbox) {
    const isChecked = checkbox.checked;
    selectedProducts.clear();
    
    if (isChecked) {
        filteredProducts.forEach(p => selectedProducts.add(p.id));
    }
    
    document.querySelectorAll('.product-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });
    
    updateBulkActionsBar();
}

// Update bulk actions bar
function updateBulkActionsBar() {
    const bar = document.getElementById('bulkActionsBar');
    const countSpan = document.getElementById('selectedCount');
    
    if (selectedProducts.size > 0) {
        bar.classList.add('show');
        countSpan.textContent = selectedProducts.size;
    } else {
        bar.classList.remove('show');
    }
}

// Bulk update status
async function bulkUpdateStatus(newStatus) {
    if (selectedProducts.size === 0) return;
    
    const ids = Array.from(selectedProducts);
    
    try {
        await Promise.all(ids.map(id => 
            fetch(`${API_URL}/products/${id}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            })
        ));
        
        selectedProducts.clear();
        document.getElementById('selectAllProducts').checked = false;
        updateBulkActionsBar();
        await loadProducts();
    } catch (error) {
        console.error('Error bulk updating status:', error);
        alert('เกิดข้อผิดพลาดในการเปลี่ยนสถานะ');
    }
}

// Bulk delete
async function bulkDelete() {
    if (selectedProducts.size === 0) return;
    
    if (!confirm(`คุณต้องการลบ ${selectedProducts.size} รายการที่เลือกหรือไม่?`)) {
        return;
    }
    
    const ids = Array.from(selectedProducts);
    
    try {
        await Promise.all(ids.map(id => 
            fetch(`${API_URL}/products/${id}`, { method: 'DELETE' })
        ));
        
        selectedProducts.clear();
        document.getElementById('selectAllProducts').checked = false;
        updateBulkActionsBar();
        await loadProducts();
        alert('ลบสินค้าสำเร็จ!');
    } catch (error) {
        console.error('Error bulk deleting:', error);
        alert('เกิดข้อผิดพลาดในการลบสินค้า');
    }
}

// Toggle product featured (star button)
async function toggleProductFeatured(productId, isFeatured) {
    try {
        const response = await fetch(`${API_URL}/products/${productId}/featured`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_featured: isFeatured })
        });
        if (!response.ok) throw new Error('Failed');
        const product = allProducts.find(p => p.id === productId);
        if (product) product.is_featured = isFeatured;
        renderProducts();
        showAlert(isFeatured ? '★ ตั้งเป็นสินค้าโปรโมทแล้ว' : 'ยกเลิกการโปรโมทแล้ว', 'success');
    } catch (error) {
        showAlert('เกิดข้อผิดพลาด กรุณาลองใหม่', 'error');
    }
}

// Toggle product status (via toggle switch)
async function toggleProductStatus(productId, isActive) {
    const newStatus = isActive ? 'active' : 'inactive';
    
    try {
        const response = await fetch(`${API_URL}/products/${productId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update status');
        }
        
        // Update local state
        const product = allProducts.find(p => p.id === productId);
        if (product) {
            product.status = newStatus;
        }
        updateStatusCounts();
        
    } catch (error) {
        console.error('Error updating product status:', error);
        alert('เกิดข้อผิดพลาดในการเปลี่ยนสถานะ');
        // Reload to reset state
        await loadProducts();
    }
}

// Update SKU price inline
async function updateSkuPrice(skuId, newPrice) {
    try {
        const response = await fetch(`${API_URL}/skus/${skuId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ price: parseFloat(newPrice) || 0 })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update price');
        }
    } catch (error) {
        console.error('Error updating SKU price:', error);
        alert('เกิดข้อผิดพลาดในการอัพเดทราคา');
    }
}

// Update SKU stock inline
async function updateSkuStock(skuId, newStock) {
    try {
        const response = await fetch(`${API_URL}/skus/${skuId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stock: parseInt(newStock) || 0 })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update stock');
        }
    } catch (error) {
        console.error('Error updating SKU stock:', error);
        alert('เกิดข้อผิดพลาดในการอัพเดทสต็อก');
    }
}

// Delete product
async function deleteProduct(productId, productName) {
    if (!confirm(`คุณต้องการลบสินค้า "${productName}" ใช่หรือไม่?\n\nการลบสินค้าจะลบ SKUs ทั้งหมดที่เกี่ยวข้องด้วย`)) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/products/${productId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok) {
            alert('ลบสินค้าสำเร็จ!');
            await loadProducts();
        } else {
            alert(result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        console.error('Error deleting product:', error);
        alert('เกิดข้อผิดพลาดในการลบสินค้า');
    }
}

// Cycle product status (active -> inactive -> draft -> active)
async function cycleProductStatus(productId, currentStatus) {
    const statusOrder = ['active', 'inactive', 'draft'];
    const currentIndex = statusOrder.indexOf(currentStatus);
    const newStatus = statusOrder[(currentIndex + 1) % statusOrder.length];
    
    try {
        const response = await fetch(`${API_URL}/products/${productId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            await loadProducts();
        } else {
            alert(result.error || 'เกิดข้อผิดพลาด');
        }
    } catch (error) {
        console.error('Error updating product status:', error);
        alert('เกิดข้อผิดพลาดในการเปลี่ยนสถานะสินค้า');
    }
}

// Show alert message (uses global alert if alertBox not available)
function showAlert(message, type) {
    // Try global alert first (works on all pages)
    const globalAlert = document.getElementById('globalAlertBox');
    if (globalAlert) {
        globalAlert.textContent = message;
        globalAlert.className = `global-alert ${type} show`;
        
        setTimeout(() => {
            globalAlert.classList.remove('show');
        }, 4000);
        return;
    }
    
    // Fallback to old alertBox
    if (alertBox) {
        alertBox.textContent = message;
        alertBox.className = `alert ${type} show`;

        setTimeout(() => {
            alertBox.classList.remove('show');
        }, 5000);
    }
}

// ========== Price/Stock Modal Functions ==========
let currentEditingProduct = null;

// Open Edit Price Modal
function openEditPriceModal(productId) {
    const product = allProducts.find(p => p.id === productId);
    if (!product) return;
    
    currentEditingProduct = product;
    const modal = document.getElementById('editPriceModal');
    const skuList = document.getElementById('priceModalSkuList');
    
    // Render SKU list
    skuList.innerHTML = '';
    
    if (!product.skus || product.skus.length === 0) {
        skuList.innerHTML = '<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">ไม่มี SKU สำหรับสินค้านี้</div>';
    } else {
        product.skus.forEach(sku => {
            const itemHtml = `
                <div class="modal-sku-item" data-sku-id="${sku.id}">
                    <div class="modal-sku-image-placeholder">📦</div>
                    <div class="modal-sku-info">
                        <div class="modal-sku-name">${product.name}${sku.variant_name ? ',' + sku.variant_name : ''}</div>
                        <div class="modal-sku-code">Seller SKU: ${sku.sku_code || '-'}</div>
                    </div>
                    <div class="modal-sku-inputs">
                        <div class="modal-sku-input-group">
                            <label>฿</label>
                            <input type="number" class="modal-sku-input sku-price-input" 
                                   data-sku-id="${sku.id}" 
                                   value="${sku.price || 0}" 
                                   min="0" step="0.01">
                        </div>
                    </div>
                </div>
            `;
            skuList.innerHTML += itemHtml;
        });
    }
    
    // Setup search filter
    const searchInput = document.getElementById('priceModalSearch');
    searchInput.value = '';
    searchInput.oninput = () => filterModalSkus('priceModalSkuList', searchInput.value);
    
    modal.classList.add('active');
}

// Close Edit Price Modal
function closeEditPriceModal() {
    const modal = document.getElementById('editPriceModal');
    modal.classList.remove('active');
    currentEditingProduct = null;
}

// Save all prices
async function saveAllPrices() {
    const inputs = document.querySelectorAll('#priceModalSkuList .sku-price-input');
    const updates = [];
    
    inputs.forEach(input => {
        const skuId = input.dataset.skuId;
        const priceVal = parseFloat(input.value);
        const price = isNaN(priceVal) || priceVal < 0 ? 0 : Math.round(priceVal * 100) / 100;
        updates.push({ skuId, price });
    });
    
    if (updates.length === 0) {
        closeEditPriceModal();
        return;
    }
    
    try {
        const results = await Promise.all(updates.map(async u => {
            const response = await fetch(`${API_URL}/skus/${u.skuId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ price: u.price })
            });
            return response.ok;
        }));
        
        const failedCount = results.filter(r => !r).length;
        
        if (failedCount === 0) {
            showAlert('บันทึกราคาสำเร็จ', 'success');
        } else {
            showAlert(`บันทึกสำเร็จ ${results.length - failedCount}/${results.length} รายการ`, 'error');
        }
        
        closeEditPriceModal();
        await loadProducts();
    } catch (error) {
        console.error('Error saving prices:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึกราคา', 'error');
    }
}

// Stock editing from Product Management is disabled
// All stock changes must go through Stock Adjustment page for audit trail
function openEditStockModal(productId) {
    showAlert('กรุณาใช้หน้า "ปรับสต็อก" เพื่อแก้ไขสต็อกสินค้า เพื่อให้มีประวัติการเปลี่ยนแปลง', 'info');
}

function closeEditStockModal() {
    const modal = document.getElementById('editStockModal');
    if (modal) modal.classList.remove('active');
}

function saveAllStock() {
    showAlert('กรุณาใช้หน้า "ปรับสต็อก" เพื่อแก้ไขสต็อกสินค้า', 'info');
    closeEditStockModal();
}

// Filter modal SKUs by search term
function filterModalSkus(listId, searchTerm) {
    const items = document.querySelectorAll(`#${listId} .modal-sku-item`);
    const term = searchTerm.toLowerCase();
    
    items.forEach(item => {
        const name = item.querySelector('.modal-sku-name')?.textContent.toLowerCase() || '';
        const code = item.querySelector('.modal-sku-code')?.textContent.toLowerCase() || '';
        
        if (name.includes(term) || code.includes(term)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// ==========================================
// Assign Brands Modal Functions
// ==========================================

let allBrands = [];

// Open Assign Brands Modal
async function openAssignBrandsModal(userId, userName) {
    const modal = document.getElementById('assignBrandsModal');
    const userIdInput = document.getElementById('assignBrandsUserId');
    const userNameSpan = document.getElementById('assignBrandsUserName');
    const brandList = document.getElementById('brandCheckboxList');
    const noBrandsMessage = document.getElementById('noBrandsMessage');
    
    userIdInput.value = userId;
    userNameSpan.textContent = userName;
    
    try {
        // Load all brands
        const brandsResponse = await fetch(`${API_URL}/brands`);
        allBrands = await brandsResponse.json();
        
        // Load user's current assigned brands
        const userBrandsResponse = await fetch(`${API_URL}/admin-brand-access/${userId}`);
        const userBrands = await userBrandsResponse.json();
        const assignedBrandIds = userBrands.map(b => b.id);
        
        if (allBrands.length === 0) {
            brandList.innerHTML = '';
            noBrandsMessage.style.display = 'block';
        } else {
            noBrandsMessage.style.display = 'none';
            brandList.innerHTML = allBrands.map(brand => {
                const isChecked = assignedBrandIds.includes(brand.id);
                return `
                    <label class="brand-checkbox-item ${isChecked ? 'selected' : ''}" data-brand-id="${brand.id}">
                        <input type="checkbox" name="brands" value="${brand.id}" ${isChecked ? 'checked' : ''} 
                               onchange="this.parentElement.classList.toggle('selected', this.checked)">
                        <div>
                            <div class="brand-name">${brand.name}</div>
                            ${brand.description ? `<div class="brand-desc">${brand.description}</div>` : ''}
                        </div>
                    </label>
                `;
            }).join('');
        }
        
        modal.classList.add('active');
    } catch (error) {
        console.error('Error loading brands:', error);
        showAlert('ไม่สามารถโหลดข้อมูลแบรนด์ได้', 'error');
    }
}

// Close Assign Brands Modal
function closeAssignBrandsModal() {
    const modal = document.getElementById('assignBrandsModal');
    modal.classList.remove('active');
}

// Handle Assign Brands Form Submit
async function handleAssignBrands(event) {
    event.preventDefault();
    
    const userId = document.getElementById('assignBrandsUserId').value;
    const checkboxes = document.querySelectorAll('#brandCheckboxList input[name="brands"]:checked');
    const brandIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    try {
        const response = await fetch(`${API_URL}/admin-brand-access/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brand_ids: brandIds })
        });
        
        if (response.ok) {
            showAlert('บันทึกการกำหนดแบรนด์สำเร็จ', 'success');
            closeAssignBrandsModal();
            await loadUsers();
            renderUsers();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error assigning brands:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

// ==========================================
// Orders Page Functions
// ==========================================

let allOrders = [];
let currentOrdersStatus = '';
