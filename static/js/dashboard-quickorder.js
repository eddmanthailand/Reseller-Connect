// ==================== QUICK ORDER SECTION ====================

let quickOrderItems = [];
let quickOrderSearchTimeout = null;
let quickOrderSalesChannels = [];

async function loadQuickOrderPage() {
    quickOrderItems = [];
    renderQuickOrderItems();
    updateQuickOrderSummary();
    _labelPasteContext = 'quick';

    try {
        const response = await fetch(`${API_URL}/sales-channels`);
        if (response.ok) {
            quickOrderSalesChannels = await response.json();
            const channelSelect = document.getElementById('quickOrderChannel');
            channelSelect.innerHTML = '<option value="">-- เลือกช่องทาง --</option>' +
                quickOrderSalesChannels.map(ch => `<option value="${ch.id}">${ch.name}</option>`).join('');
        }
    } catch (error) {
        console.error('Error loading sales channels:', error);
    }
}

function searchQuickOrderProducts(keyword) {
    clearTimeout(quickOrderSearchTimeout);
    const resultsDiv = document.getElementById('quickOrderProductResults');
    
    if (!keyword || keyword.length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }
    
    quickOrderSearchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`${API_URL}/admin/products?search=${encodeURIComponent(keyword)}&limit=15`);
            if (!response.ok) throw new Error('Failed to search products');
            const data = await response.json();
            const products = data.products || data;
            
            if (products.length === 0) {
                resultsDiv.innerHTML = '<div style="padding: 16px; text-align: center; color: #9ca3af;">ไม่พบสินค้า</div>';
            } else {
                resultsDiv.innerHTML = products.map(p => `
                    <div onclick="selectQuickOrderProduct(${p.id})" style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;" onmouseover="this.style.background='rgba(168,85,247,0.1)'" onmouseout="this.style.background='transparent'">
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <img src="${p.image_url || '/static/images/placeholder.png'}" alt="" style="width: 40px; height: 40px; object-fit: cover; border-radius: 6px; background: rgba(255,255,255,0.1);">
                            <div style="flex: 1; min-width: 0;">
                                <strong style="font-size: 14px; color: #fff; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(p.name)}</strong>
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

async function selectQuickOrderProduct(productId) {
    document.getElementById('quickOrderProductResults').style.display = 'none';
    document.getElementById('quickOrderProductSearch').value = '';
    
    try {
        const response = await fetch(`${API_URL}/admin/products/${productId}/skus-with-stock`);
        if (!response.ok) throw new Error('Failed to load product SKUs');
        const data = await response.json();
        
        if (data.skus && data.skus.length > 0) {
            if (data.skus.length === 1) {
                addQuickOrderItem(data.product, data.skus[0]);
            } else {
                showQuickOrderSkuSelector(data.product, data.skus);
            }
        } else {
            showGlobalAlert('สินค้านี้ยังไม่มี SKU', 'error');
        }
    } catch (error) {
        console.error('Error loading product:', error);
        showGlobalAlert('ไม่สามารถโหลดข้อมูลสินค้าได้', 'error');
    }
}

function showQuickOrderSkuSelector(product, skus) {
    const resultsDiv = document.getElementById('quickOrderProductResults');
    resultsDiv.innerHTML = `
        <div style="padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1);">
            <strong style="font-size: 14px;">${escapeHtml(product.name)}</strong>
            <div style="font-size: 12px; color: #9ca3af;">เลือก SKU:</div>
        </div>
        ${skus.map(sku => `
            <div onclick="addQuickOrderItemFromSku(${product.id}, ${sku.id}, '${escapeHtml(sku.sku_code)}', '${escapeHtml(sku.variant_name || '')}', ${sku.price}, '${escapeHtml(product.name)}', '${product.image_url || ''}')" style="padding: 10px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;" onmouseover="this.style.background='rgba(168,85,247,0.1)'" onmouseout="this.style.background='transparent'">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 13px; color: #fff;">${escapeHtml(sku.sku_code)}</div>
                        <div style="font-size: 11px; color: #9ca3af;">${escapeHtml(sku.variant_name || '-')}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 13px; color: #ffffff; font-weight: 600;">฿${formatNumber(sku.price)}</div>
                        <div style="font-size: 11px; color: ${sku.total_stock > 0 ? '#10b981' : '#ef4444'};">คงเหลือ: ${sku.total_stock || 0}</div>
                    </div>
                </div>
            </div>
        `).join('')}
    `;
    resultsDiv.style.display = 'block';
}

function addQuickOrderItemFromSku(productId, skuId, skuCode, variantName, price, productName, imageUrl) {
    document.getElementById('quickOrderProductResults').style.display = 'none';
    
    const existingIndex = quickOrderItems.findIndex(item => item.sku_id === skuId);
    if (existingIndex >= 0) {
        quickOrderItems[existingIndex].quantity += 1;
    } else {
        quickOrderItems.push({
            product_id: productId,
            sku_id: skuId,
            sku_code: skuCode,
            variant_name: variantName,
            product_name: productName,
            image_url: imageUrl,
            price: price,
            quantity: 1
        });
    }
    
    renderQuickOrderItems();
    updateQuickOrderSummary();
}

function addQuickOrderItem(product, sku) {
    addQuickOrderItemFromSku(product.id, sku.id, sku.sku_code, sku.variant_name || '', sku.price, product.name, product.image_url);
}

function updateQuickOrderItemQty(skuId, delta) {
    const itemIndex = quickOrderItems.findIndex(item => item.sku_id === skuId);
    if (itemIndex >= 0) {
        quickOrderItems[itemIndex].quantity += delta;
        if (quickOrderItems[itemIndex].quantity <= 0) {
            quickOrderItems.splice(itemIndex, 1);
        }
        renderQuickOrderItems();
        updateQuickOrderSummary();
    }
}

function removeQuickOrderItem(skuId) {
    quickOrderItems = quickOrderItems.filter(item => item.sku_id !== skuId);
    renderQuickOrderItems();
    updateQuickOrderSummary();
}

function renderQuickOrderItems() {
    const container = document.getElementById('quickOrderItems');
    
    if (quickOrderItems.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; opacity: 0.6; border: 2px dashed rgba(255,255,255,0.2); border-radius: 12px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.4; margin-bottom: 8px;">
                    <circle cx="9" cy="21" r="1"></circle>
                    <circle cx="20" cy="21" r="1"></circle>
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
                </svg>
                <p>ค้นหาและเลือกสินค้าเพื่อเพิ่มลงรายการ</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = quickOrderItems.map(item => `
        <div style="display: flex; gap: 12px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; border: 1px solid rgba(255,255,255,0.05);">
            <img src="${item.image_url || '/static/images/placeholder.png'}" alt="" style="width: 50px; height: 50px; object-fit: cover; border-radius: 8px; background: rgba(255,255,255,0.1);">
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(item.product_name)}</div>
                <div style="font-size: 12px; color: #9ca3af;">${escapeHtml(item.sku_code)} ${item.variant_name ? '| ' + escapeHtml(item.variant_name) : ''}</div>
                <div style="font-size: 13px; color: #ffffff; font-weight: 600; margin-top: 4px;">฿${formatNumber(item.price)} x ${item.quantity} = ฿${formatNumber(item.price * item.quantity)}</div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <button type="button" onclick="updateQuickOrderItemQty(${item.sku_id}, -1)" style="width: 28px; height: 28px; border: none; border-radius: 6px; background: rgba(239,68,68,0.2); color: #ffffff; cursor: pointer; font-size: 16px; font-weight: 700;">-</button>
                    <span style="min-width: 24px; text-align: center; font-weight: 600;">${item.quantity}</span>
                    <button type="button" onclick="updateQuickOrderItemQty(${item.sku_id}, 1)" style="width: 28px; height: 28px; border: none; border-radius: 6px; background: rgba(16,185,129,0.2); color: #10b981; cursor: pointer; font-size: 16px; font-weight: 700;">+</button>
                </div>
                <button type="button" onclick="removeQuickOrderItem(${item.sku_id})" style="background: none; border: none; color: #ffffff; cursor: pointer; font-size: 11px; opacity: 0.8;">ลบ</button>
            </div>
        </div>
    `).join('');
}

function updateQuickOrderSummary() {
    const itemCount = quickOrderItems.length;
    const totalQty = quickOrderItems.reduce((sum, item) => sum + item.quantity, 0);
    const totalAmount = quickOrderItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    
    document.getElementById('quickOrderItemCount').textContent = `${itemCount} รายการ`;
    document.getElementById('quickOrderTotalQty').textContent = `${totalQty} ชิ้น`;
    document.getElementById('quickOrderTotal').textContent = `฿${formatNumber(totalAmount)}`;
    
    const channelSelected = document.getElementById('quickOrderChannel').value;
    document.getElementById('btnCreateQuickOrder').disabled = quickOrderItems.length === 0 || !channelSelected;
}

async function createQuickOrder() {
    const channelId = document.getElementById('quickOrderChannel').value;
    const platform = document.getElementById('quickOrderPlatform').value;
    const trackingNumber = document.getElementById('quickOrderTracking').value.trim();
    const customerName = document.getElementById('quickOrderCustomerName').value.trim();
    const customerPhone = document.getElementById('quickOrderCustomerPhone').value.trim();
    const notes = document.getElementById('quickOrderNotes').value.trim();
    const shippingAddress = (document.getElementById('qoShippingAddress')?.value || '').trim();
    const shippingSubdistrict = (document.getElementById('qoShippingSubdistrict')?.value || '').trim();
    const shippingDistrict = (document.getElementById('qoShippingDistrict')?.value || '').trim();
    const shippingProvince = (document.getElementById('qoShippingProvince')?.value || '').trim();
    const shippingPostal = (document.getElementById('qoShippingPostal')?.value || '').trim();
    
    if (!channelId) {
        showGlobalAlert('กรุณาเลือกช่องทางขาย', 'error');
        return;
    }
    
    if (quickOrderItems.length === 0) {
        showGlobalAlert('กรุณาเพิ่มสินค้าอย่างน้อย 1 รายการ', 'error');
        return;
    }
    
    const btn = document.getElementById('btnCreateQuickOrder');
    btn.disabled = true;
    btn.innerHTML = '<span>กำลังสร้างคำสั่งซื้อ...</span>';
    
    try {
        const response = await fetch(`${API_URL}/admin/quick-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sales_channel_id: parseInt(channelId),
                platform: platform || null,
                tracking_number: trackingNumber || null,
                customer_name: customerName || null,
                customer_phone: customerPhone || null,
                notes: notes || null,
                shipping_name: customerName || null,
                shipping_phone: customerPhone || null,
                shipping_address: shippingAddress || null,
                shipping_subdistrict: shippingSubdistrict || null,
                shipping_district: shippingDistrict || null,
                shipping_province: shippingProvince || null,
                shipping_postal: shippingPostal || null,
                items: quickOrderItems.map(item => ({
                    sku_id: item.sku_id,
                    quantity: item.quantity,
                    price: item.price
                }))
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const statusMsg = trackingNumber ? ' (สถานะ: กำลังจัดส่ง)' : '';
            const custMsg = result.customer_status === 'new' ? ' · บันทึกลูกค้าใหม่แล้ว' : result.customer_status === 'existing' ? ' · อัปเดตลูกค้าเดิม' : '';
            showGlobalAlert(`สร้างคำสั่งซื้อสำเร็จ! เลขที่: ${result.order_number}${statusMsg}${custMsg}`, 'success');
            quickOrderItems = [];
            document.getElementById('quickOrderPlatform').value = '';
            document.getElementById('quickOrderTracking').value = '';
            document.getElementById('quickOrderCustomerName').value = '';
            document.getElementById('quickOrderCustomerPhone').value = '';
            document.getElementById('quickOrderNotes').value = '';
            document.getElementById('quickOrderChannel').value = '';
            const sect = document.getElementById('qoAddressSection');
            if (sect) { sect.style.display = 'none'; }
            ['qoShippingAddress','qoShippingSubdistrict','qoShippingDistrict','qoShippingProvince','qoShippingPostal'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            const badge = document.getElementById('qoCustomerBadge');
            if (badge) badge.style.display = 'none';
            renderQuickOrderItems();
            updateQuickOrderSummary();
        } else {
            showGlobalAlert(result.error || 'ไม่สามารถสร้างคำสั่งซื้อได้', 'error');
        }
    } catch (error) {
        console.error('Error creating quick order:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
            <path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>สร้างคำสั่งซื้อ`;
        updateQuickOrderSummary();
    }
}

// Event listener for channel selection
document.addEventListener('change', function(e) {
    if (e.target && e.target.id === 'quickOrderChannel') {
        updateQuickOrderSummary();
    }
});

// ─── Quick Orders (in orders page) ──────────────────────────────────────────

let currentOrdersMode = 'reseller';
let currentQuickOrdersStatus = '';

function switchOrdersMode(mode) {
    currentOrdersMode = mode;
    const resellerSection = document.getElementById('ordersResellerSection');
    const quickSection = document.getElementById('ordersQuickSection');
    const btnReseller = document.getElementById('ordersModeBtnReseller');
    const btnQuick = document.getElementById('ordersModeBtnQuick');

    if (mode === 'reseller') {
        resellerSection.style.display = '';
        quickSection.style.display = 'none';
        btnReseller.style.background = '';
        btnReseller.style.border = '';
        btnQuick.style.background = 'rgba(255,255,255,0.1)';
        btnQuick.style.border = '1px solid rgba(255,255,255,0.2)';
    } else {
        resellerSection.style.display = 'none';
        quickSection.style.display = '';
        btnQuick.style.background = '';
        btnQuick.style.border = '';
        btnReseller.style.background = 'rgba(255,255,255,0.1)';
        btnReseller.style.border = '1px solid rgba(255,255,255,0.2)';
        loadQuickOrders(currentQuickOrdersStatus);
    }
}

function _platformBadge(platform) {
    const map = {
        shopee: { label: 'Shopee', color: '#ee4d2d' },
        lazada: { label: 'Lazada', color: '#0f146d' },
        tiktok: { label: 'TikTok', color: '#010101' },
        line: { label: 'LINE', color: '#06c755' },
        facebook: { label: 'Facebook', color: '#1877f2' },
        onsale: { label: 'หน้าร้าน', color: '#7c3aed' },
        other: { label: 'อื่นๆ', color: '#6b7280' }
    };
    if (!platform) return '';
    const p = map[platform] || { label: platform, color: '#6b7280' };
    return `<span style="background:${p.color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;margin-right:6px;">${p.label}</span>`;
}

async function loadQuickOrders(status = '') {
    currentQuickOrdersStatus = status;
    const container = document.getElementById('quickOrdersContainer');
    container.innerHTML = '<div style="text-align:center;padding:40px;opacity:0.6;">กำลังโหลดข้อมูล...</div>';

    document.querySelectorAll('#quickOrderStatusTabs .status-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.status === status);
    });

    try {
        let url = `${API_URL}/admin/quick-orders`;
        if (status) url += `?status=${status}`;
        const res = await fetch(url);
        const orders = await res.json();
        renderQuickOrders(orders);
    } catch (e) {
        container.innerHTML = '<div class="empty-state">ไม่สามารถโหลดข้อมูลได้</div>';
    }
}

function renderQuickOrders(orders) {
    const container = document.getElementById('quickOrdersContainer');
    if (!orders || orders.length === 0) {
        container.innerHTML = '<div class="empty-state">ไม่มีออเดอร์ขายด่วน</div>';
        return;
    }

    const statusLabels = {
        paid: 'รอจัดส่ง', shipped: 'กำลังจัดส่ง', delivered: 'จัดส่งสำเร็จ',
        returned: 'ตีกลับ', stock_restored: 'คืนสต็อกแล้ว', cancelled: 'ยกเลิก'
    };
    const statusColors = {
        paid: '#f59e0b', shipped: '#0ea5e9', delivered: '#10b981',
        returned: '#ef4444', stock_restored: '#6b7280', cancelled: '#6b7280'
    };

    let html = `<table class="orders-table"><thead><tr>
        <th>เลขที่</th><th>แพลตฟอร์ม / ช่องทาง</th><th>Tracking</th>
        <th>สินค้า</th><th>ยอดรวม</th><th>สถานะ</th><th>วันที่</th><th style="text-align:center;">Actions</th>
    </tr></thead><tbody>`;

    orders.forEach(order => {
        const statusLabel = statusLabels[order.status] || order.status;
        const statusColor = statusColors[order.status] || '#6b7280';
        const orderDate = new Date(order.created_at).toLocaleDateString('th-TH');
        const orderNo = order.order_number || `#${order.id}`;
        const tracking = order.tracking_number || '-';
        const trackingLink = order.tracking_number && order.platform === 'lazada'
            ? `<a href="https://track.lazada.co.th/tracking?tradeOrderId=${order.tracking_number}" target="_blank" style="color:#0ea5e9;font-size:12px;">${order.tracking_number} ↗</a>`
            : order.tracking_number
                ? `<span style="font-size:12px;font-family:monospace;">${order.tracking_number}</span>`
                : '<span style="opacity:0.4;font-size:12px;">ยังไม่มี</span>';

        let actions = `<button class="action-btn btn-review" onclick="viewQuickOrderDetails(${order.id})" style="padding:5px 10px;font-size:12px;">ดู</button>`;

        if (order.status === 'paid') {
            actions += `<button class="action-btn" onclick="showQuickOrderShipModal(${order.id})" style="padding:5px 10px;font-size:12px;background:rgba(14,165,233,0.2);color:#0ea5e9;border:1px solid rgba(14,165,233,0.3);border-radius:6px;cursor:pointer;margin-left:4px;">จัดส่ง</button>`;
        }
        if (order.status === 'shipped') {
            actions += `<button class="action-btn" onclick="confirmQuickOrderDelivered(${order.id})" style="padding:5px 10px;font-size:12px;background:rgba(16,185,129,0.2);color:#10b981;border:1px solid rgba(16,185,129,0.3);border-radius:6px;cursor:pointer;margin-left:4px;">รับแล้ว</button>`;
            actions += `<button class="action-btn" onclick="confirmQuickOrderReturned(${order.id})" style="padding:5px 10px;font-size:12px;background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.3);border-radius:6px;cursor:pointer;margin-left:4px;">ตีกลับ</button>`;
        }
        if (order.status === 'returned') {
            actions += `<button class="action-btn" onclick="showRestoreStockModal(${order.id}, '${orderNo}')" style="padding:5px 10px;font-size:12px;background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid rgba(168,85,247,0.3);border-radius:6px;cursor:pointer;margin-left:4px;">คืนสต็อก</button>`;
        }

        html += `<tr>
            <td style="font-weight:600;font-size:13px;">${orderNo}</td>
            <td>${_platformBadge(order.platform)}<span style="font-size:12px;opacity:0.8;">${order.channel_name || '-'}</span></td>
            <td>${trackingLink}</td>
            <td style="font-size:12px;">${order.item_count} รายการ</td>
            <td style="font-weight:600;">฿${formatNumber(order.final_amount)}</td>
            <td><span style="background:${statusColor}22;color:${statusColor};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">${statusLabel}</span></td>
            <td style="font-size:12px;">${orderDate}</td>
            <td style="text-align:center;">${actions}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function viewQuickOrderDetails(orderId) {
    viewOrderDetails(orderId);
}

function showQuickOrderShipModal(orderId) {
    const tracking = prompt('กรอกเลข Tracking No. สำหรับการจัดส่ง:');
    if (!tracking || !tracking.trim()) return;
    updateQuickOrderStatus(orderId, 'shipped', tracking.trim());
}

async function confirmQuickOrderDelivered(orderId) {
    if (!confirm('ยืนยันว่าสินค้าจัดส่งสำเร็จแล้ว?')) return;
    await updateQuickOrderStatus(orderId, 'delivered');
}

async function confirmQuickOrderReturned(orderId) {
    if (!confirm('ยืนยันว่าสินค้าถูกตีกลับ?\nระบบจะเปลี่ยนสถานะเป็น "ตีกลับ" และคุณสามารถคืนสต็อกได้ภายหลัง')) return;
    await updateQuickOrderStatus(orderId, 'returned');
}

async function updateQuickOrderStatus(orderId, newStatus, trackingNumber = null) {
    try {
        const body = { status: newStatus };
        if (trackingNumber) body.tracking_number = trackingNumber;
        const res = await fetch(`${API_URL}/admin/quick-orders/${orderId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await res.json();
        if (res.ok) {
            showGlobalAlert(result.message || 'อัปเดตสำเร็จ', 'success');
            loadQuickOrders(currentQuickOrdersStatus);
        } else {
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (e) {
        showGlobalAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error');
    }
}

function showRestoreStockModal(orderId, orderNo) {
    if (!confirm(`คืนสต็อกสำหรับออเดอร์ ${orderNo}?\n\nสินค้าที่ถูกตีกลับจะถูกเพิ่มกลับเข้า warehouse ต้นทาง\nการดำเนินการนี้ไม่สามารถยกเลิกได้`)) return;
    restoreQuickOrderStock(orderId);
}

async function restoreQuickOrderStock(orderId) {
    try {
        const res = await fetch(`${API_URL}/admin/quick-orders/${orderId}/restore-stock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await res.json();
        if (res.ok) {
            showGlobalAlert('คืนสต็อกสำเร็จ', 'success');
            loadQuickOrders(currentQuickOrdersStatus);
        } else {
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (e) {
        showGlobalAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error');
    }
}

// ─── Label OCR (Gemini Vision) ───────────────────────────────────────────────

let _ocrExtracted = null;
let _labelPasteContext = null; // 'quick' | 'customer' | null

function handleLabelDrop(event, type) {
    event.preventDefault();
    const zoneId = type === 'quick' ? 'qoLabelZone' : 'custLabelZone';
    const zone = document.getElementById(zoneId);
    if (zone) {
        zone.style.borderColor = type === 'quick' ? 'rgba(99,102,241,0.5)' : '#c7c7cc';
        zone.style.background   = type === 'quick' ? 'rgba(99,102,241,0.15)' : '#ffffff';
        if (type === 'customer') zone.style.color = '#636366';
    }
    const files = event.dataTransfer?.files;
    if (files && files.length > 0 && files[0].type.startsWith('image/')) {
        _processLabelFile(files[0], type);
    }
}

async function _processLabelFile(file, type) {
    if (!file || !file.type.startsWith('image/')) {
        showGlobalAlert('กรุณาเลือกไฟล์รูปภาพเท่านั้น', 'error');
        return;
    }

    if (type === 'quick') {
        const statusDiv  = document.getElementById('labelScanStatus');
        const statusMsg  = document.getElementById('labelScanMsg');
        const resultCard = document.getElementById('labelOcrResult');
        const zone       = document.getElementById('qoLabelZone');
        if (statusDiv)  { statusDiv.style.display = 'block'; }
        if (statusMsg)  { statusMsg.textContent = 'กำลังวิเคราะห์ใบปะหน้า...'; }
        if (resultCard) { resultCard.style.display = 'none'; }
        if (zone) { zone.style.opacity = '0.6'; zone.style.pointerEvents = 'none'; }
        try {
            const formData = new FormData();
            formData.append('image', file);
            const res = await fetch(`${API_URL}/admin/quick-order/parse-label`, { method: 'POST', body: formData });
            const result = await res.json();
            if (!res.ok) { showGlobalAlert(result.error || 'ไม่สามารถอ่านใบปะหน้าได้', 'error'); return; }
            _ocrExtracted = result.data;
            renderOcrResultCard(result.data);
        } catch (e) {
            showGlobalAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error');
        } finally {
            if (statusDiv) { statusDiv.style.display = 'none'; }
            if (zone) { zone.style.opacity = '1'; zone.style.pointerEvents = 'auto'; }
            const inp = document.getElementById('labelImageInput');
            if (inp) inp.value = '';
        }

    } else if (type === 'customer') {
        const statusEl = document.getElementById('customerScanStatus');
        const zone     = document.getElementById('custLabelZone');
        if (statusEl) { statusEl.style.display = 'block'; statusEl.textContent = '⏳ กำลังอ่านข้อมูลจากรูป...'; statusEl.style.color = '#8b5cf6'; }
        if (zone) { zone.style.opacity = '0.6'; zone.style.pointerEvents = 'none'; }

        const preview = document.getElementById('custLabelPreview');
        if (preview) {
            const reader = new FileReader();
            reader.onload = e => {
                preview.src = e.target.result;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }

        try {
            const formData = new FormData();
            formData.append('image', file);
            const res  = await fetch('/api/admin/quick-order/parse-label', { method: 'POST', body: formData });
            const resp = await res.json();
            if (!res.ok) throw new Error(resp.error || 'ล้มเหลว');
            const data = resp.data || {};
            if (data.customer_name)  document.getElementById('custName').value        = data.customer_name;
            if (data.customer_phone) document.getElementById('custPhone').value       = data.customer_phone;
            if (data.address)        document.getElementById('custAddress').value     = data.address;
            if (data.subdistrict)    document.getElementById('custSubdistrict').value = data.subdistrict;
            if (data.district)       document.getElementById('custDistrict').value    = data.district;
            if (data.province)       document.getElementById('custProvince').value    = data.province;
            if (data.postal_code)    document.getElementById('custPostal').value      = data.postal_code;
            if (data.platform)       document.getElementById('custSource').value      = data.platform;
            if (statusEl) { statusEl.style.color = '#16a34a'; statusEl.textContent = '✅ อ่านข้อมูลสำเร็จ ตรวจสอบและบันทึกได้เลย'; }
            if (data.customer_phone) checkCustomerPhoneDuplicate(data.customer_phone);
        } catch (e) {
            if (statusEl) { statusEl.style.color = '#ef4444'; statusEl.textContent = '❌ อ่านไม่ได้: ' + e.message; }
        } finally {
            if (zone) { zone.style.opacity = '1'; zone.style.pointerEvents = 'auto'; }
            const inp = document.getElementById('customerLabelInput');
            if (inp) inp.value = '';
        }
    }
}

async function handleLabelImageUpload(input) {
    if (input.files && input.files[0]) await _processLabelFile(input.files[0], 'quick');
}

function renderOcrResultCard(data) {
    const platformLabels = {
        shopee: '🛍️ Shopee', lazada: '📦 Lazada',
        tiktok: '🎵 TikTok', other: 'อื่นๆ'
    };
    const fields = [
        { label: 'แพลตฟอร์ม', value: platformLabels[data.platform] || data.platform },
        { label: 'Tracking', value: data.tracking_number },
        { label: 'ชื่อลูกค้า', value: data.customer_name },
        { label: 'เบอร์โทร', value: data.customer_phone },
        { label: 'ที่อยู่', value: data.address },
        { label: 'จังหวัด', value: data.province },
        { label: 'รหัสไปรษณีย์', value: data.postal_code },
    ].filter(f => f.value && f.value !== 'null');

    const dataDiv = document.getElementById('labelOcrData');
    dataDiv.innerHTML = fields.map(f => `
        <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:8px 10px;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:rgba(255,255,255,0.5);margin-bottom:3px;">${f.label}</div>
            <div style="font-weight:600;color:#ffffff;font-size:13px;">${f.value}</div>
        </div>
    `).join('');

    document.getElementById('labelOcrResult').style.display = 'block';
    document.getElementById('labelOcrResult').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

let _qoPhoneLookupTimer = null;

function qoPhoneInputChanged(phone) {
    clearTimeout(_qoPhoneLookupTimer);
    const badge = document.getElementById('qoCustomerBadge');
    if (!phone || phone.length < 9) {
        if (badge) badge.style.display = 'none';
        return;
    }
    _qoPhoneLookupTimer = setTimeout(async () => {
        try {
            const res = await fetch(`/api/admin/customers/check-phone?phone=${encodeURIComponent(phone)}`);
            const data = await res.json();
            if (!badge) return;
            if (data.exists) {
                badge.style.cssText = 'display:inline-flex;align-items:center;gap:5px;font-size:11px;background:rgba(52,211,153,0.15);border:1px solid rgba(52,211,153,0.4);color:#34d399;border-radius:20px;padding:3px 10px;margin-top:5px;';
                badge.innerHTML = `✓ ลูกค้าเก่า — ${data.name || 'ไม่ระบุชื่อ'}`;
                const nameInput = document.getElementById('quickOrderCustomerName');
                if (nameInput && !nameInput.value.trim() && data.name) nameInput.value = data.name;
            } else {
                badge.style.cssText = 'display:inline-flex;align-items:center;gap:5px;font-size:11px;background:rgba(148,163,184,0.12);border:1px solid rgba(148,163,184,0.3);color:rgba(255,255,255,0.5);border-radius:20px;padding:3px 10px;margin-top:5px;';
                badge.innerHTML = '+ ลูกค้าใหม่';
            }
        } catch(e) {}
    }, 600);
}

function applyOcrToForm() {
    if (!_ocrExtracted) return;
    const d = _ocrExtracted;

    if (d.platform) {
        const el = document.getElementById('quickOrderPlatform');
        if (el) el.value = d.platform;
    }
    if (d.tracking_number) {
        const el = document.getElementById('quickOrderTracking');
        if (el) el.value = d.tracking_number;
    }
    if (d.customer_name) {
        const el = document.getElementById('quickOrderCustomerName');
        if (el) el.value = d.customer_name;
    }
    if (d.customer_phone) {
        const el = document.getElementById('quickOrderCustomerPhone');
        if (el) el.value = d.customer_phone;
        qoPhoneInputChanged(d.customer_phone);
    }

    const hasAddress = d.address || d.province || d.district || d.subdistrict || d.postal_code;
    if (hasAddress) {
        const sect = document.getElementById('qoAddressSection');
        if (sect) sect.style.display = 'block';
        if (d.address)       { const el = document.getElementById('qoShippingAddress');     if (el) el.value = d.address; }
        if (d.subdistrict)   { const el = document.getElementById('qoShippingSubdistrict'); if (el) el.value = d.subdistrict; }
        if (d.district)      { const el = document.getElementById('qoShippingDistrict');    if (el) el.value = d.district; }
        if (d.province)      { const el = document.getElementById('qoShippingProvince');    if (el) el.value = d.province; }
        if (d.postal_code)   { const el = document.getElementById('qoShippingPostal');      if (el) el.value = d.postal_code; }
    }

    if (d.customer_status === 'existing' && d.existing_customer) {
        const badge = document.getElementById('qoCustomerBadge');
        if (badge) {
            badge.style.cssText = 'display:inline-flex;align-items:center;gap:5px;font-size:11px;background:rgba(52,211,153,0.15);border:1px solid rgba(52,211,153,0.4);color:#34d399;border-radius:20px;padding:3px 10px;margin-top:5px;';
            badge.innerHTML = `✓ ลูกค้าเก่า — ${d.existing_customer.name || 'ไม่ระบุชื่อ'}`;
        }
    }

    updateQuickOrderSummary();
    document.getElementById('labelOcrResult').style.display = 'none';
    showGlobalAlert('กรอกข้อมูลจากใบปะหน้าสำเร็จ', 'success');
    _ocrExtracted = null;
}

function dismissOcrResult() {
    document.getElementById('labelOcrResult').style.display = 'none';
    _ocrExtracted = null;
}

async function requestNewSlip(orderId) {
    const reason = prompt('เหตุผลในการขอสลิปใหม่:', 'สลิปไม่ชัด');
    if (!reason) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/request-new-slip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ reason })
        });
        
        const result = await response.json();
        if (response.ok) {
            showGlobalAlert('ขอสลิปใหม่สำเร็จ — แจ้งเตือนสมาชิกแล้ว', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error requesting new slip:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

// =====================================================
// SHIPPING SETTINGS FUNCTIONS
// =====================================================

let shippingRates = [];
let shippingPromos = [];
let editingRateId = null;
let editingPromoId = null;

async function loadShippingSettingsPage() {
    await Promise.all([loadShippingRates(), loadShippingPromos(), loadShippingProviders()]);
}

async function loadShippingRates() {
    try {
        const response = await fetch(`${API_URL}/shipping-rates`);
        if (!response.ok) throw new Error('Failed to load shipping rates');
        shippingRates = await response.json();
        renderShippingRates();
    } catch (error) {
        console.error('Error loading shipping rates:', error);
        document.getElementById('shippingRatesTableBody').innerHTML = 
            '<tr><td colspan="3" style="text-align: center; color: #ef4444;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

function renderShippingRates() {
    const tbody = document.getElementById('shippingRatesTableBody');
    if (!tbody) return;
    
    if (shippingRates.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: rgba(255,255,255,0.5);">ยังไม่มีอัตราค่าส่ง</td></tr>';
        return;
    }
    
    tbody.innerHTML = shippingRates.map(rate => {
        const minWeight = rate.min_weight >= 1000 ? `${(rate.min_weight/1000).toFixed(1)} กก.` : `${rate.min_weight} ก.`;
        const maxWeight = rate.max_weight === null ? 'ขึ้นไป' : 
            (rate.max_weight >= 1000 ? `${(rate.max_weight/1000).toFixed(1)} กก.` : `${rate.max_weight} ก.`);
        
        return `
            <tr>
                <td>${minWeight} - ${maxWeight}</td>
                <td>฿${rate.rate.toLocaleString()}</td>
                <td>
                    <button class="action-btn btn-edit" onclick="editShippingRate(${rate.id})" title="แก้ไข">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="action-btn btn-delete" onclick="deleteShippingRate(${rate.id})" title="ลบ">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function loadShippingPromos() {
    try {
        const response = await fetch(`${API_URL}/shipping-promotions`);
        if (!response.ok) throw new Error('Failed to load shipping promotions');
        shippingPromos = await response.json();
        renderShippingPromos();
    } catch (error) {
        console.error('Error loading shipping promotions:', error);
        document.getElementById('shippingPromosTableBody').innerHTML = 
            '<tr><td colspan="6" style="text-align: center; color: #ef4444;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

function renderShippingPromos() {
    const tbody = document.getElementById('shippingPromosTableBody');
    if (!tbody) return;
    
    if (shippingPromos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: rgba(255,255,255,0.5);">ยังไม่มีโปรโมชั่น</td></tr>';
        return;
    }
    
    tbody.innerHTML = shippingPromos.map(promo => {
        const minOrderValue = promo.min_order_value || 0;
        const discountAmount = promo.discount_amount || 0;
        
        let conditionText = `ซื้อขั้นต่ำ ฿${minOrderValue.toLocaleString()}`;
        
        let discountText = '';
        if (promo.promo_type === 'free_shipping') {
            discountText = '<span style="color: #22c55e;">ส่งฟรี</span>';
        } else if (promo.promo_type === 'discount_amount') {
            discountText = `ลด ฿${discountAmount.toLocaleString()}`;
        } else if (promo.promo_type === 'discount_percent') {
            discountText = `ลด ${discountAmount}%`;
        }
        
        const statusClass = promo.is_active ? 'status-active' : 'status-inactive';
        const statusText = promo.is_active ? 'ใช้งาน' : 'ปิดใช้งาน';
        
        const brands = promo.brands || [];
        const brandsText = brands.length === 0
            ? '<span style="color: rgba(255,255,255,0.5); font-size: 12px;">ทุกแบรนด์</span>'
            : brands.map(b => `<span style="background: rgba(168,85,247,0.25); border: 1px solid rgba(168,85,247,0.4); color: #e9d5ff; border-radius: 4px; padding: 1px 6px; font-size: 11px; margin: 1px; display: inline-block;">${escapeHtml(b.name)}</span>`).join('');
        
        return `
            <tr>
                <td>${escapeHtml(promo.name)}</td>
                <td>${brandsText}</td>
                <td>${conditionText}</td>
                <td>${discountText}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>
                    <button class="action-btn btn-edit" onclick="editShippingPromo(${promo.id})" title="แก้ไข">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="action-btn btn-delete" onclick="deleteShippingPromo(${promo.id})" title="ลบ">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function showAddShippingRateModal() {
    editingRateId = null;
    const modalHtml = `
        <div class="modal-overlay" id="shippingRateModal" onclick="closeShippingRateModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>เพิ่มช่วงน้ำหนัก</h3>
                    <button class="modal-close" onclick="closeShippingRateModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">น้ำหนักต่ำสุด (กรัม)</label>
                        <input type="number" id="rateMinWeight" class="form-input" min="0" value="0">
                    </div>
                    <div class="form-group">
                        <label class="form-label">น้ำหนักสูงสุด (กรัม)</label>
                        <input type="number" id="rateMaxWeight" class="form-input" min="1" placeholder="เว้นว่างสำหรับไม่จำกัด">
                        <small style="opacity: 0.6;">เว้นว่างสำหรับน้ำหนักมากกว่าที่กำหนด</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">ราคา (บาท)</label>
                        <input type="number" id="ratePrice" class="form-input" min="0" step="0.01" value="0">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary" onclick="closeShippingRateModal()">ยกเลิก</button>
                    <button class="btn-primary btn-success" onclick="saveShippingRate()">บันทึก</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function editShippingRate(id) {
    const rate = shippingRates.find(r => r.id === id);
    if (!rate) return;
    
    editingRateId = id;
    const modalHtml = `
        <div class="modal-overlay" id="shippingRateModal" onclick="closeShippingRateModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>แก้ไขช่วงน้ำหนัก</h3>
                    <button class="modal-close" onclick="closeShippingRateModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">น้ำหนักต่ำสุด (กรัม)</label>
                        <input type="number" id="rateMinWeight" class="form-input" min="0" value="${rate.min_weight}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">น้ำหนักสูงสุด (กรัม)</label>
                        <input type="number" id="rateMaxWeight" class="form-input" min="1" value="${rate.max_weight || ''}" placeholder="เว้นว่างสำหรับไม่จำกัด">
                        <small style="opacity: 0.6;">เว้นว่างสำหรับน้ำหนักมากกว่าที่กำหนด</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">ราคา (บาท)</label>
                        <input type="number" id="ratePrice" class="form-input" min="0" step="0.01" value="${rate.rate}">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary" onclick="closeShippingRateModal()">ยกเลิก</button>
                    <button class="btn-primary btn-success" onclick="saveShippingRate()">บันทึก</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeShippingRateModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('shippingRateModal');
    if (modal) modal.remove();
}

async function saveShippingRate() {
    const minWeight = parseInt(document.getElementById('rateMinWeight').value) || 0;
    const maxWeightVal = document.getElementById('rateMaxWeight').value;
    const maxWeight = maxWeightVal ? parseInt(maxWeightVal) : null;
    const rate = parseFloat(document.getElementById('ratePrice').value) || 0;
    
    const data = { min_weight: minWeight, max_weight: maxWeight, rate: rate };
    
    try {
        let response;
        if (editingRateId) {
            response = await fetch(`${API_URL}/shipping-rates/${editingRateId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch(`${API_URL}/shipping-rates`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }
        
        if (response.ok) {
            closeShippingRateModal();
            showGlobalAlert(editingRateId ? 'อัปเดตอัตราค่าส่งสำเร็จ' : 'เพิ่มอัตราค่าส่งสำเร็จ', 'success');
            await loadShippingRates();
        } else {
            const result = await response.json();
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving shipping rate:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function deleteShippingRate(id) {
    if (!confirm('ต้องการลบอัตราค่าส่งนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/shipping-rates/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showGlobalAlert('ลบอัตราค่าส่งสำเร็จ', 'success');
            await loadShippingRates();
        } else {
            showGlobalAlert('ไม่สามารถลบได้', 'error');
        }
    } catch (error) {
        console.error('Error deleting shipping rate:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function buildPromoBrandCheckboxes(selectedBrandIds = []) {
    try {
        const res = await fetch(`${API_URL}/brands`);
        const brandList = res.ok ? await res.json() : [];
        if (brandList.length === 0) return '<p style="color: rgba(255,255,255,0.5); font-size: 12px;">ยังไม่มีแบรนด์</p>';
        return brandList.map(b => `
            <label style="display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer;">
                <input type="checkbox" class="promo-brand-cb" value="${b.id}" ${selectedBrandIds.includes(b.id) ? 'checked' : ''}>
                <span style="font-size: 13px;">${escapeHtml(b.name)}</span>
            </label>
        `).join('');
    } catch {
        return '<p style="color: #ef4444; font-size: 12px;">โหลดแบรนด์ไม่สำเร็จ</p>';
    }
}

async function showAddShippingPromoModal() {
    editingPromoId = null;
    const brandCheckboxes = await buildPromoBrandCheckboxes([]);
    const modalHtml = `
        <div class="modal-overlay" id="shippingPromoModal" onclick="closeShippingPromoModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>เพิ่มโปรโมชั่น</h3>
                    <button class="modal-close" onclick="closeShippingPromoModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">ชื่อโปรโมชั่น</label>
                        <input type="text" id="promoName" class="form-input" placeholder="เช่น ส่งฟรีเมื่อซื้อครบ 800 บาท">
                    </div>
                    <div class="form-group">
                        <label class="form-label">ประเภทโปรโมชั่น</label>
                        <select id="promoType" class="form-input" onchange="updatePromoFields()">
                            <option value="free_shipping">ส่งฟรี</option>
                            <option value="discount_amount">ลดราคาค่าส่ง (บาท)</option>
                            <option value="discount_percent">ลดราคาค่าส่ง (%)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">ยอดซื้อขั้นต่ำ (บาท)</label>
                        <input type="number" id="promoMinAmount" class="form-input" min="0" step="0.01" value="0">
                    </div>
                    <div class="form-group" id="promoDiscountGroup" style="display: none;">
                        <label class="form-label" id="promoDiscountLabel">ส่วนลด</label>
                        <input type="number" id="promoDiscountValue" class="form-input" min="0" step="0.01" value="0">
                    </div>
                    <div class="form-group">
                        <label class="form-label">แบรนด์ที่ใช้โปรโมชั่นได้</label>
                        <p style="color: rgba(255,255,255,0.5); font-size: 12px; margin: 0 0 8px;">ไม่เลือก = ใช้ได้กับทุกแบรนด์</p>
                        <div id="promoBrandsContainer" style="max-height: 160px; overflow-y: auto; background: rgba(255,255,255,0.05); border-radius: 8px; padding: 8px 12px; border: 1px solid rgba(255,255,255,0.1);">
                            ${brandCheckboxes}
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label" style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" id="promoIsActive" checked>
                            เปิดใช้งานโปรโมชั่น
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary" onclick="closeShippingPromoModal()">ยกเลิก</button>
                    <button class="btn-primary btn-success" onclick="saveShippingPromo()">บันทึก</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function updatePromoFields() {
    const promoType = document.getElementById('promoType').value;
    const discountGroup = document.getElementById('promoDiscountGroup');
    const discountLabel = document.getElementById('promoDiscountLabel');
    
    if (promoType === 'free_shipping') {
        discountGroup.style.display = 'none';
    } else if (promoType === 'discount_amount') {
        discountGroup.style.display = 'block';
        discountLabel.textContent = 'ส่วนลด (บาท)';
    } else if (promoType === 'discount_percent') {
        discountGroup.style.display = 'block';
        discountLabel.textContent = 'ส่วนลด (%)';
    }
}

async function editShippingPromo(id) {
    const promo = shippingPromos.find(p => p.id === id);
    if (!promo) return;
    
    editingPromoId = id;
    const showDiscount = promo.promo_type !== 'free_shipping';
    const selectedBrandIds = (promo.brands || []).map(b => b.id);
    const brandCheckboxes = await buildPromoBrandCheckboxes(selectedBrandIds);
    
    const modalHtml = `
        <div class="modal-overlay" id="shippingPromoModal" onclick="closeShippingPromoModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>แก้ไขโปรโมชั่น</h3>
                    <button class="modal-close" onclick="closeShippingPromoModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">ชื่อโปรโมชั่น</label>
                        <input type="text" id="promoName" class="form-input" value="${escapeHtml(promo.name)}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">ประเภทโปรโมชั่น</label>
                        <select id="promoType" class="form-input" onchange="updatePromoFields()">
                            <option value="free_shipping" ${promo.promo_type === 'free_shipping' ? 'selected' : ''}>ส่งฟรี</option>
                            <option value="discount_amount" ${promo.promo_type === 'discount_amount' ? 'selected' : ''}>ลดราคาค่าส่ง (บาท)</option>
                            <option value="discount_percent" ${promo.promo_type === 'discount_percent' ? 'selected' : ''}>ลดราคาค่าส่ง (%)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">ยอดซื้อขั้นต่ำ (บาท)</label>
                        <input type="number" id="promoMinAmount" class="form-input" min="0" step="0.01" value="${promo.min_order_value || 0}">
                    </div>
                    <div class="form-group" id="promoDiscountGroup" style="display: ${showDiscount ? 'block' : 'none'};">
                        <label class="form-label" id="promoDiscountLabel">${promo.promo_type === 'discount_percent' ? 'ส่วนลด (%)' : 'ส่วนลด (บาท)'}</label>
                        <input type="number" id="promoDiscountValue" class="form-input" min="0" step="0.01" value="${promo.discount_amount || 0}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">แบรนด์ที่ใช้โปรโมชั่นได้</label>
                        <p style="color: rgba(255,255,255,0.5); font-size: 12px; margin: 0 0 8px;">ไม่เลือก = ใช้ได้กับทุกแบรนด์</p>
                        <div id="promoBrandsContainer" style="max-height: 160px; overflow-y: auto; background: rgba(255,255,255,0.05); border-radius: 8px; padding: 8px 12px; border: 1px solid rgba(255,255,255,0.1);">
                            ${brandCheckboxes}
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label" style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" id="promoIsActive" ${promo.is_active ? 'checked' : ''}>
                            เปิดใช้งานโปรโมชั่น
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary" onclick="closeShippingPromoModal()">ยกเลิก</button>
                    <button class="btn-primary btn-success" onclick="saveShippingPromo()">บันทึก</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeShippingPromoModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('shippingPromoModal');
    if (modal) modal.remove();
}

async function saveShippingPromo() {
    const name = document.getElementById('promoName').value.trim();
    const promoType = document.getElementById('promoType').value;
    const minAmount = parseFloat(document.getElementById('promoMinAmount').value) || 0;
    const discountValue = parseFloat(document.getElementById('promoDiscountValue') ? document.getElementById('promoDiscountValue').value : 0) || 0;
    const isActive = document.getElementById('promoIsActive').checked;
    
    const brandCbs = document.querySelectorAll('.promo-brand-cb:checked');
    const brandIds = Array.from(brandCbs).map(cb => parseInt(cb.value));
    
    if (!name) {
        showGlobalAlert('กรุณากรอกชื่อโปรโมชั่น', 'error');
        return;
    }
    
    const data = {
        name: name,
        promo_type: promoType,
        min_order_value: minAmount,
        discount_amount: promoType === 'free_shipping' ? 0 : discountValue,
        is_active: isActive,
        brand_ids: brandIds
    };
    
    try {
        let response;
        if (editingPromoId) {
            response = await fetch(`${API_URL}/shipping-promotions/${editingPromoId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch(`${API_URL}/shipping-promotions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }
        
        if (response.ok) {
            closeShippingPromoModal();
            showGlobalAlert(editingPromoId ? 'อัปเดตโปรโมชั่นสำเร็จ' : 'เพิ่มโปรโมชั่นสำเร็จ', 'success');
            await loadShippingPromos();
        } else {
            const result = await response.json();
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving shipping promo:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function deleteShippingPromo(id) {
    if (!confirm('ต้องการลบโปรโมชั่นนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/shipping-promotions/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showGlobalAlert('ลบโปรโมชั่นสำเร็จ', 'success');
            await loadShippingPromos();
        } else {
            showGlobalAlert('ไม่สามารถลบได้', 'error');
        }
    } catch (error) {
        console.error('Error deleting shipping promo:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

// =====================================================
// SHIPPING PROVIDERS FUNCTIONS
// =====================================================

let shippingProviders = [];
let editingProviderId = null;

async function loadShippingProviders() {
    try {
        const response = await fetch(`${API_URL}/shipping-providers`);
        if (!response.ok) throw new Error('Failed to load shipping providers');
        shippingProviders = await response.json();
        renderShippingProviders();
    } catch (error) {
        console.error('Error loading shipping providers:', error);
        document.getElementById('shippingProvidersTableBody').innerHTML = 
            '<tr><td colspan="5" style="text-align: center; color: #ef4444;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

function renderShippingProviders() {
    const tbody = document.getElementById('shippingProvidersTableBody');
    if (!tbody) return;
    
    if (shippingProviders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: rgba(255,255,255,0.5);">ยังไม่มีบริษัทขนส่ง</td></tr>';
        return;
    }
    
    tbody.innerHTML = shippingProviders.map(provider => `
        <tr>
            <td><strong>${provider.name}</strong></td>
            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">
                ${provider.tracking_url ? `<a href="${provider.tracking_url}" target="_blank" style="color: #a78bfa;">${provider.tracking_url}</a>` : '<span style="color: rgba(255,255,255,0.4);">-</span>'}
            </td>
            <td>${provider.display_order}</td>
            <td>
                <span class="status-badge ${provider.is_active ? 'active' : 'inactive'}">
                    ${provider.is_active ? 'ใช้งาน' : 'ปิด'}
                </span>
            </td>
            <td>
                <button class="action-btn btn-edit" onclick="editShippingProvider(${provider.id})" title="แก้ไข">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="action-btn btn-delete" onclick="deleteShippingProvider(${provider.id})" title="ลบ">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </td>
        </tr>
    `).join('');
}

function showAddShippingProviderModal() {
    editingProviderId = null;
    document.getElementById('shippingProviderModalTitle').textContent = 'เพิ่มบริษัทขนส่ง';
    document.getElementById('providerName').value = '';
    document.getElementById('providerTrackingUrl').value = '';
    document.getElementById('providerDisplayOrder').value = '0';
    document.getElementById('providerIsActive').checked = true;
    document.getElementById('shippingProviderModal').style.display = 'flex';
}

function editShippingProvider(id) {
    const provider = shippingProviders.find(p => p.id === id);
    if (!provider) return;
    
    editingProviderId = id;
    document.getElementById('shippingProviderModalTitle').textContent = 'แก้ไขบริษัทขนส่ง';
    document.getElementById('providerName').value = provider.name;
    document.getElementById('providerTrackingUrl').value = provider.tracking_url || '';
    document.getElementById('providerDisplayOrder').value = provider.display_order || 0;
    document.getElementById('providerIsActive').checked = provider.is_active;
    document.getElementById('shippingProviderModal').style.display = 'flex';
}

function closeShippingProviderModal() {
    document.getElementById('shippingProviderModal').style.display = 'none';
    editingProviderId = null;
}

async function saveShippingProvider() {
    const data = {
        name: document.getElementById('providerName').value.trim(),
        tracking_url: document.getElementById('providerTrackingUrl').value.trim() || null,
        display_order: parseInt(document.getElementById('providerDisplayOrder').value) || 0,
        is_active: document.getElementById('providerIsActive').checked
    };
    
    if (!data.name) {
        showGlobalAlert('กรุณาระบุชื่อบริษัทขนส่ง', 'error');
        return;
    }
    
    try {
        let response;
        if (editingProviderId) {
            response = await fetch(`${API_URL}/shipping-providers/${editingProviderId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch(`${API_URL}/shipping-providers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }
        
        if (response.ok) {
            closeShippingProviderModal();
            showGlobalAlert(editingProviderId ? 'อัปเดตบริษัทขนส่งสำเร็จ' : 'เพิ่มบริษัทขนส่งสำเร็จ', 'success');
            await loadShippingProviders();
        } else {
            const result = await response.json();
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving shipping provider:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function deleteShippingProvider(id) {
    if (!confirm('ต้องการลบบริษัทขนส่งนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/shipping-providers/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showGlobalAlert('ลบบริษัทขนส่งสำเร็จ', 'success');
            await loadShippingProviders();
        } else {
            showGlobalAlert('ไม่สามารถลบได้', 'error');
        }
    } catch (error) {
        console.error('Error deleting shipping provider:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

