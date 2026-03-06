
async function loadOrders(status = '') {
    currentOrdersStatus = status;
    const container = document.getElementById('ordersContainer');
    
    try {
        let url = `${API_URL}/admin/orders`;
        if (status) url += `?status=${status}`;
        
        const response = await fetch(url);
        allOrders = await response.json();
        
        renderOrders();
        updateOrderCounts();
    } catch (error) {
        console.error('Error loading orders:', error);
        container.innerHTML = '<div class="empty-state">ไม่สามารถโหลดข้อมูลได้</div>';
    }
}

function renderOrders() {
    const container = document.getElementById('ordersContainer');
    
    if (allOrders.length === 0) {
        container.innerHTML = '<div class="empty-state">ไม่มีคำสั่งซื้อ</div>';
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
    
    const statusColors = {
        'pending_payment': '#f59e0b',
        'under_review': '#3b82f6',
        'preparing': '#8b5cf6',
        'paid': '#22c55e',
        'shipped': '#0ea5e9',
        'delivered': '#10b981',
        'failed_delivery': '#ef4444',
        'rejected': '#ef4444',
        'cancelled': '#6b7280',
        'pending_refund': '#f97316',
        'refunded': '#10b981'
    };
    
    let html = `
        <table class="orders-table">
            <thead>
                <tr>
                    <th>เลขที่คำสั่งซื้อ</th>
                    <th>ลูกค้า</th>
                    <th>ช่องทาง</th>
                    <th>ยอดรวม</th>
                    <th>สถานะ</th>
                    <th>วันที่</th>
                    <th style="text-align: center;">Actions</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    allOrders.forEach(order => {
        const statusLabel = statusLabels[order.status] || order.status;
        const statusColor = statusColors[order.status] || '#6b7280';
        const orderDate = new Date(order.created_at).toLocaleDateString('th-TH');
        const orderNumber = order.order_number || `#${order.id}`;
        const channelName = order.channel_name || '-';
        
        let actionButtons = `<button class="action-btn btn-review" onclick="viewOrderDetails(${order.id})" style="padding: 6px 12px; font-size: 12px;">ดูรายละเอียด</button>`;
        
        if (order.status === 'under_review') {
            actionButtons = `
                <div style="display: flex; gap: 6px; justify-content: center;">
                    <button class="action-btn" onclick="updateOrderStatus(${order.id}, 'paid')" style="padding: 6px 10px; font-size: 11px; background: #22c55e; color: white; border: none; border-radius: 6px; cursor: pointer;">อนุมัติ</button>
                    <button class="action-btn" onclick="updateOrderStatus(${order.id}, 'rejected')" style="padding: 6px 10px; font-size: 11px; background: #ef4444; color: white; border: none; border-radius: 6px; cursor: pointer;">ปฏิเสธ</button>
                    <button class="action-btn" onclick="viewOrderDetails(${order.id})" style="padding: 6px 10px; font-size: 11px; background: rgba(255,255,255,0.1); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; cursor: pointer;">ดู</button>
                </div>
            `;
        } else if (order.status === 'pending_payment') {
            actionButtons = `
                <div style="display: flex; gap: 6px; justify-content: center;">
                    <button class="action-btn" onclick="viewOrderDetails(${order.id})" style="padding: 6px 12px; font-size: 11px; background: rgba(255,255,255,0.1); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; cursor: pointer;">ดูรายละเอียด</button>
                </div>
            `;
        }
        
        html += `
            <tr>
                <td style="font-weight: 600; color: #ffffff;">${orderNumber}</td>
                <td>${escapeHtml(order.reseller_name || order.username || 'N/A')}</td>
                <td><span style="font-size: 11px; padding: 2px 8px; background: rgba(255,255,255,0.1); border-radius: 4px;">${escapeHtml(channelName)}</span></td>
                <td style="font-weight: 600;">฿${parseFloat(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</td>
                <td><span style="background: ${statusColor}; color: white; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 500;">${statusLabel}</span></td>
                <td style="font-size: 12px; opacity: 0.8;">${orderDate}</td>
                <td>${actionButtons}</td>
            </tr>
        `;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

async function updateOrderCounts() {
    try {
        const response = await fetch(`${API_URL}/admin/orders/counts`);
        const counts = await response.json();

        const setCount = (id, status) => {
            const el = document.getElementById(id);
            if (!el) return;
            const n = counts[status] || 0;
            el.textContent = n;
            el.style.display = n > 0 ? 'inline' : 'none';
        };

        setCount('reviewCount', 'under_review');
        setCount('pendingPaymentCount', 'pending_payment');
        setCount('preparingCount', 'preparing');
        setCount('shippedCount', 'shipped');
        setCount('deliveredCount', 'delivered');
        setCount('failedCount', 'failed_delivery');
        setCount('cancelledCount', 'cancelled');
        setCount('pendingRefundCount', 'pending_refund');

        const reviewCount = counts['under_review'] || 0;
        const pendingBadge = document.getElementById('pendingOrderCount');
        if (pendingBadge) {
            pendingBadge.textContent = reviewCount;
            pendingBadge.style.display = reviewCount > 0 ? 'inline' : 'none';
        }
    } catch (error) {
        console.error('Error updating order counts:', error);
    }
}

let shippingProvidersCache = [];

async function loadShippingProvidersForOrder() {
    if (shippingProvidersCache.length > 0) return shippingProvidersCache;
    try {
        const response = await fetch(`${API_URL}/shipping-providers`);
        shippingProvidersCache = await response.json();
        return shippingProvidersCache.filter(p => p.is_active);
    } catch (error) {
        console.error('Error loading shipping providers:', error);
        return [];
    }
}

async function viewOrderDetails(orderId) {
    try {
        const [orderResponse, providers] = await Promise.all([
            fetch(`${API_URL}/orders/${orderId}`),
            loadShippingProvidersForOrder()
        ]);
        const order = await orderResponse.json();
        
        // Check for API error
        if (order.error || !orderResponse.ok) {
            showGlobalAlert(order.error || 'ไม่สามารถโหลดรายละเอียดคำสั่งซื้อได้', 'error');
            return;
        }
        
        // Store order data for printing immediately after fetch
        window.currentOrderData = order;
        
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
        
        const statusColors = {
            'pending_payment': '#f59e0b',
            'under_review': '#3b82f6',
            'preparing': '#8b5cf6',
            'paid': '#22c55e',
            'shipped': '#0ea5e9',
            'delivered': '#10b981',
            'failed_delivery': '#ef4444',
            'rejected': '#ef4444',
            'cancelled': '#6b7280',
            'pending_refund': '#f97316',
            'refunded': '#10b981'
        };
        
        // Build items HTML - Modern card style
        let itemsHtml = '';
        if (order.items && order.items.length > 0) {
            itemsHtml = order.items.map(item => {
                const variantDisplay = item.variant_name ? ` (${item.variant_name})` : '';
                const customizationDisplay = item.customization_labels && item.customization_labels.length > 0 
                    ? `<div style="color: #a5f3fc; font-size: 11px; margin-top: 4px;">${item.customization_labels.map(l => escapeHtml(l)).join(', ')}</div>` 
                    : '';
                return `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.08);">
                    <div style="flex: 1;">
                        <div style="color: #fff; font-weight: 500;">${escapeHtml(item.product_name || 'Product')}${escapeHtml(variantDisplay)}</div>
                        <div style="color: rgba(255,255,255,0.6); font-size: 12px; margin-top: 2px;">SKU: ${escapeHtml(item.sku_code || '-')} | จำนวน: ${item.quantity}</div>
                        ${customizationDisplay}
                    </div>
                    <div style="color: #fff; font-weight: 600; font-size: 15px;">฿${parseFloat(item.subtotal || item.unit_price * item.quantity).toLocaleString('th-TH')}</div>
                </div>
            `;
            }).join('');
        }
        
        // Build shipments HTML - Modern design
        let shipmentsHtml = '';
        if (order.shipments && order.shipments.length > 0) {
            shipmentsHtml = `
                <div style="margin-top: 24px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px;">
                        <svg width="20" height="20" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M5 17H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-1"/><polygon points="12 15 17 21 7 21 12 15"/></svg>
                        <h4 style="color: #fff; font-size: 16px; font-weight: 600; margin: 0;">การจัดส่ง (${order.shipments.length} พัสดุ)</h4>
                    </div>
                    ${order.shipments.map((shipment, idx) => {
                        const shipmentStatusLabel = shipment.status === 'pending' ? 'รอจัดส่ง' : shipment.status === 'shipped' ? 'จัดส่งแล้ว' : 'ส่งสำเร็จ';
                        const shipmentStatusColor = shipment.status === 'pending' ? 'linear-gradient(135deg, #f59e0b, #d97706)' : shipment.status === 'shipped' ? 'linear-gradient(135deg, #8b5cf6, #7c3aed)' : 'linear-gradient(135deg, #10b981, #059669)';
                        
                        let trackingLinkHtml = '';
                        if (shipment.tracking_url) {
                            trackingLinkHtml = `<a href="${escapeHtml(shipment.tracking_url)}" target="_blank" style="color: #a5f3fc; text-decoration: none; font-size: 12px; display: inline-flex; align-items: center; gap: 4px;">
                                <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                                ติดตามพัสดุ
                            </a>`;
                        }
                        
                        return `
                            <div style="background: linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03)); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-bottom: 12px; backdrop-filter: blur(10px);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <div style="width: 32px; height: 32px; background: linear-gradient(135deg, #6366f1, #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                            <svg width="16" height="16" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                                        </div>
                                        <span style="color: #fff; font-weight: 600;">${escapeHtml(shipment.warehouse_name)}</span>
                                    </div>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <button onclick="printShippingLabel(${idx})" style="font-size: 11px; padding: 6px 12px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight: 500;">
                                            พิมพ์ใบปะหน้า
                                        </button>
                                        <span style="background: ${shipmentStatusColor}; color: #fff; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 500;">${shipmentStatusLabel}</span>
                                    </div>
                                </div>
                                <div style="font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 12px; padding: 8px 12px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                                    ${shipment.items.map(i => `<span style="color: #fff;">${escapeHtml(i.product_name)}</span> <span style="color: rgba(255,255,255,0.5);">x${i.quantity}</span>`).join(', ')}
                                </div>
                                ${order.status === 'paid' || shipment.status === 'pending' ? `
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px;">
                                        <select id="provider_${shipment.id}" style="font-size: 13px; padding: 10px 12px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; outline: none;">
                                            <option value="" style="background: #1a1a2e;">-- เลือกขนส่ง --</option>
                                            ${providers.map(p => `<option value="${escapeHtml(p.name)}" style="background: #1a1a2e;">${escapeHtml(p.name)}</option>`).join('')}
                                        </select>
                                        <input type="text" id="tracking_${shipment.id}" placeholder="เลขพัสดุ" value="${escapeHtml(shipment.tracking_number || '')}" style="font-size: 13px; padding: 10px 12px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; outline: none;">
                                    </div>
                                    <button onclick="updateShipmentTracking(${orderId}, ${shipment.id})" style="width: 100%; margin-top: 12px; font-size: 13px; padding: 12px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                                        ${shipment.tracking_number ? 'อัปเดตเลขพัสดุ' : 'บันทึกเลขพัสดุ'}
                                    </button>
                                ` : `
                                    <div style="display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: #fff; margin-top: 8px;">
                                        <div><span style="color: rgba(255,255,255,0.6);">ขนส่ง:</span> <strong>${escapeHtml(shipment.shipping_provider || '-')}</strong></div>
                                        <div><span style="color: rgba(255,255,255,0.6);">เลขพัสดุ:</span> <strong>${escapeHtml(shipment.tracking_number || '-')}</strong></div>
                                        ${trackingLinkHtml}
                                    </div>
                                `}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }
        
        // Build payment slips HTML
        let slipHtml = '';
        if (order.payment_slips && order.payment_slips.length > 0) {
            slipHtml = `
                <div style="margin-top: 24px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <svg width="18" height="18" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
                        <h4 style="color: #fff; font-size: 16px; font-weight: 600; margin: 0;">หลักฐานการชำระเงิน</h4>
                    </div>
                    ${order.payment_slips.map(slip => `
                        <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                            <div class="slip-image-frame">
                                <img src="${slip.slip_image_url}" alt="Payment Slip" onclick="viewSlipFullscreen('${slip.slip_image_url}')">
                            </div>
                            <div style="margin-top: 12px; display: flex; align-items: center; gap: 12px; font-size: 13px; color: #fff;">
                                <span style="background: ${slip.status === 'approved' ? 'linear-gradient(135deg, #22c55e, #16a34a)' : slip.status === 'rejected' ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 'linear-gradient(135deg, #f59e0b, #d97706)'}; color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">${slip.status === 'approved' ? 'อนุมัติแล้ว' : slip.status === 'rejected' ? 'ปฏิเสธ' : 'รอตรวจสอบ'}</span>
                                ${slip.amount ? `<span>ยอด: <strong>฿${parseFloat(slip.amount).toLocaleString('th-TH')}</strong></span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        // Build refund section
        let refundHtml = '';
        if (order.refund) {
            const rf = order.refund;
            const rfAmount = (rf.refund_amount || 0).toLocaleString('th-TH', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            const rfDate = rf.completed_at
                ? new Date(rf.completed_at).toLocaleString('th-TH', {day:'numeric', month:'short', year:'numeric'})
                : (rf.created_at ? new Date(rf.created_at).toLocaleString('th-TH', {day:'numeric', month:'short', year:'numeric'}) : '');
            const isDone = rf.status === 'completed';
            const bankInfo = [rf.bank_name, rf.bank_account_name, rf.bank_account_number].filter(Boolean).join(' · ');
            refundHtml = `
                <div style="margin-top: 24px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <svg width="18" height="18" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                        <h4 style="color: #fff; font-size: 16px; font-weight: 600; margin: 0;">การคืนเงิน</h4>
                        <span style="background: ${isDone ? 'linear-gradient(135deg,#22c55e,#16a34a)' : 'linear-gradient(135deg,#f59e0b,#d97706)'}; color: #fff; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; margin-left: auto;">
                            ${isDone ? '✅ คืนเงินสำเร็จ' : '⏳ รอดำเนินการ'}
                        </span>
                    </div>
                    <div style="background: ${isDone ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.08)'}; border: 1px solid ${isDone ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}; border-radius: 12px; padding: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                            <div>
                                <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">ยอดที่คืน</div>
                                <div style="font-size: 22px; font-weight: 700; color: ${isDone ? '#34d399' : '#ffffff'};">฿${rfAmount}</div>
                            </div>
                            ${rfDate ? `<div style="font-size: 11px; color: rgba(255,255,255,0.4); text-align: right;">${rfDate}</div>` : ''}
                        </div>
                        ${bankInfo ? `<div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 12px; padding: 8px 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">โอนไปยัง: ${escapeHtml(bankInfo)}</div>` : ''}
                        ${rf.slip_url ? `
                            <div>
                                <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 8px;">สลิปการคืนเงิน</div>
                                <img src="${rf.slip_url}" alt="สลิปคืนเงิน"
                                    onclick="viewSlipFullscreen('${rf.slip_url}')"
                                    style="width: 100%; max-height: 280px; object-fit: contain; border-radius: 10px; background: rgba(0,0,0,0.3); cursor: pointer; border: 1px solid rgba(255,255,255,0.1);">
                            </div>
                        ` : `
                            <div style="font-size: 12px; color: rgba(255,255,255,0.45); padding-top: 4px;">
                                ยังไม่ได้อัปโหลดสลิป
                            </div>
                        `}
                    </div>
                </div>
            `;
        }

        // Build action buttons based on order status
        let actionsHtml = '';
        if (order.status === 'under_review') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;">
                    <button onclick="approveOrder(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยืนยันการชำระเงิน
                    </button>
                    <button onclick="requestNewSlip(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ขอสลิปใหม่
                    </button>
                </div>
            `;
        } else if (order.status === 'pending_payment') {
            actionsHtml = `
                <div style="margin-top: 24px;">
                    <button onclick="cancelOrderAdmin(${orderId},'${escapeHtml(order.order_number||'#'+orderId)}','${order.status}')" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิกคำสั่งซื้อ
                    </button>
                </div>
            `;
        } else if (order.status === 'preparing') {
            actionsHtml = `
                <div style="margin-top: 24px;">
                    <button onclick="cancelOrderAdmin(${orderId},'${escapeHtml(order.order_number||'#'+orderId)}','${order.status}')" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิกคำสั่งซื้อ
                    </button>
                </div>
            `;
        } else if (order.status === 'shipped') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-top: 24px;">
                    <button onclick="markDelivered(${orderId})" style="padding: 12px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer;">
                        ส่งสำเร็จ
                    </button>
                    <button onclick="markFailedDelivery(${orderId})" style="padding: 12px; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer;">
                        จัดส่งไม่สำเร็จ
                    </button>
                    <button onclick="cancelOrderAdmin(${orderId},'${escapeHtml(order.order_number||'#'+orderId)}','shipped')" style="padding: 12px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer;">
                        ยกเลิก+คืนเงิน
                    </button>
                </div>
            `;
        } else if (order.status === 'failed_delivery') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;">
                    <button onclick="reshipOrder(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        จัดส่งใหม่
                    </button>
                    <button onclick="cancelOrderAdmin(${orderId},'${escapeHtml(order.order_number||'#'+orderId)}','${order.status}')" style="padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิก / คืนเงิน
                    </button>
                </div>
            `;
        } else if (order.status === 'pending_refund') {
            actionsHtml = `
                <div style="margin-top: 24px;">
                    <div style="background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.3); border-radius: 10px; padding: 12px 16px; margin-bottom: 14px; font-size: 13px; color: #f97316;">
                        ⚠️ ออเดอร์นี้ถูกยกเลิกแล้ว — รอดำเนินการคืนสต็อกและคืนเงิน
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <button onclick="openReturnStockModal(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: #fff; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer;">
                            📦 รับสินค้าคืนคลัง
                        </button>
                        <button onclick="closeModal('orderDetailModal'); openRefundModal(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #f97316, #ea580c); color: #fff; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer;">
                            💸 ดำเนินการคืนเงิน
                        </button>
                    </div>
                </div>
            `;
        } else if (order.status === 'refunded') {
            actionsHtml = `
                <div style="margin-top: 24px; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 10px; padding: 14px 16px; text-align: center;">
                    <div style="font-size: 22px; margin-bottom: 6px;">✅</div>
                    <div style="color: #10b981; font-size: 14px; font-weight: 600;">คืนเงินสำเร็จแล้ว</div>
                </div>
            `;
        }
        
        // Build reseller info section - Modern card
        let resellerHtml = '';
        if (order.reseller_name) {
            const resellerFullAddress = [order.reseller_address, order.reseller_subdistrict, order.reseller_district, order.reseller_province, order.reseller_postal_code].filter(Boolean).join(' ');
            resellerHtml = `
                <div style="background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(139,92,246,0.05)); border: 1px solid rgba(139,92,246,0.3); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <div style="width: 28px; height: 28px; background: linear-gradient(135deg, #8b5cf6, #7c3aed); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                            <svg width="14" height="14" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        </div>
                        <h4 style="color: #fff; font-size: 14px; font-weight: 600; margin: 0;">ผู้สั่ง (Reseller)</h4>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; color: #fff;">
                        <div><span style="color: rgba(255,255,255,0.6);">ชื่อ:</span> <strong>${escapeHtml(order.reseller_name)}</strong></div>
                        <div><span style="color: rgba(255,255,255,0.6);">Tier:</span> <strong>${escapeHtml(order.reseller_tier_name || '-')}</strong></div>
                        ${order.reseller_brand_name ? `<div><span style="color: rgba(255,255,255,0.6);">ร้าน:</span> <strong>${escapeHtml(order.reseller_brand_name)}</strong></div>` : ''}
                        <div><span style="color: rgba(255,255,255,0.6);">โทร:</span> <strong>${escapeHtml(order.reseller_phone || '-')}</strong></div>
                        ${order.reseller_email ? `<div style="grid-column: span 2;"><span style="color: rgba(255,255,255,0.6);">อีเมล:</span> <strong>${escapeHtml(order.reseller_email)}</strong></div>` : ''}
                    </div>
                    ${resellerFullAddress ? `<div style="font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1);"><span style="color: rgba(255,255,255,0.6);">ที่อยู่:</span> ${escapeHtml(resellerFullAddress)}</div>` : ''}
                </div>
            `;
        }
        
        // Build customer (recipient) info section
        let customerHtml = '';
        if (order.customer) {
            const c = order.customer;
            const fullAddress = [c.address, c.subdistrict, c.district, c.province, c.postal_code].filter(Boolean).join(' ');
            customerHtml = `
                <div style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(34,197,94,0.05)); border: 1px solid rgba(34,197,94,0.3); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <div style="width: 28px; height: 28px; background: linear-gradient(135deg, #22c55e, #16a34a); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                            <svg width="14" height="14" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                        </div>
                        <h4 style="color: #fff; font-size: 14px; font-weight: 600; margin: 0;">ผู้รับ (ลูกค้าปลายทาง)</h4>
                    </div>
                    <div style="font-size: 13px; color: #fff;">
                        <div style="margin-bottom: 6px;"><span style="color: rgba(255,255,255,0.6);">ชื่อ:</span> <strong>${escapeHtml(c.full_name || '-')}</strong></div>
                        <div style="margin-bottom: 6px;"><span style="color: rgba(255,255,255,0.6);">โทร:</span> <strong>${escapeHtml(c.phone || '-')}</strong></div>
                        <div><span style="color: rgba(255,255,255,0.6);">ที่อยู่:</span> ${escapeHtml(fullAddress || '-')}</div>
                    </div>
                </div>
            `;
        } else {
            // Fallback: Use reseller as recipient (same as shipping label)
            const resellerRecipientAddress = [order.reseller_address, order.reseller_subdistrict, order.reseller_district, order.reseller_province, order.reseller_postal_code].filter(Boolean).join(' ');
            customerHtml = `
                <div style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(34,197,94,0.05)); border: 1px solid rgba(34,197,94,0.3); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <div style="width: 28px; height: 28px; background: linear-gradient(135deg, #22c55e, #16a34a); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                            <svg width="14" height="14" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                        </div>
                        <h4 style="color: #fff; font-size: 14px; font-weight: 600; margin: 0;">ผู้รับ (Reseller รับเอง)</h4>
                    </div>
                    <div style="font-size: 13px; color: #fff;">
                        <div style="margin-bottom: 6px;"><span style="color: rgba(255,255,255,0.6);">ชื่อ:</span> <strong>${escapeHtml(order.reseller_name || '-')}</strong></div>
                        <div style="margin-bottom: 6px;"><span style="color: rgba(255,255,255,0.6);">โทร:</span> <strong>${escapeHtml(order.reseller_phone || '-')}</strong></div>
                        <div><span style="color: rgba(255,255,255,0.6);">ที่อยู่:</span> ${escapeHtml(resellerRecipientAddress || '-')}</div>
                    </div>
                </div>
            `;
        }
        
        // Build complete modal content
        const modalContent = `
            <div style="padding: 24px; max-height: 80vh; overflow-y: auto; color: #fff;">
                <!-- Header -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <div>
                        <h2 style="color: #fff; font-size: 22px; font-weight: 700; margin: 0 0 4px 0;">${order.order_number || 'คำสั่งซื้อ #' + order.id}</h2>
                        <p style="color: rgba(255,255,255,0.6); font-size: 13px; margin: 0;">${new Date(order.created_at).toLocaleString('th-TH')}</p>
                    </div>
                    <span style="background: ${statusColors[order.status] || '#6b7280'}; color: #fff; padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 600;">${statusLabels[order.status] || order.status}</span>
                </div>
                
                <!-- Info cards -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
                    ${resellerHtml}
                    ${customerHtml}
                </div>
                
                <!-- Order meta -->
                <div style="display: flex; gap: 20px; margin-bottom: 20px; font-size: 13px; color: #fff;">
                    <div><span style="color: rgba(255,255,255,0.6);">ช่องทาง:</span> <strong>${escapeHtml(order.channel_name || '-')}</strong></div>
                    ${order.notes ? `<div><span style="color: rgba(255,255,255,0.6);">หมายเหตุ:</span> ${escapeHtml(order.notes)}</div>` : ''}
                </div>
                
                <!-- Items section -->
                <div style="background: linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02)); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <svg width="18" height="18" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
                        <h4 style="color: #fff; font-size: 15px; font-weight: 600; margin: 0;">รายการสินค้า</h4>
                    </div>
                    ${itemsHtml || '<p style="color: rgba(255,255,255,0.5); text-align: center; padding: 20px 0;">ไม่มีรายการ</p>'}
                    <div style="padding: 10px 0 0; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);">
                        ${order.discount_amount > 0 ? `
                        <div style="display:flex;justify-content:space-between;font-size:13px;color:rgba(255,255,255,0.65);margin-bottom:4px;">
                            <span>ส่วนลดสมาชิก</span><span style="color:#34d399;">-฿${parseFloat(order.discount_amount).toLocaleString('th-TH')}</span>
                        </div>` : ''}
                        ${parseFloat(order.promotion_discount || 0) > 0 ? `
                        <div style="display:flex;justify-content:space-between;font-size:13px;color:rgba(255,255,255,0.65);margin-bottom:4px;">
                            <span>⚡ โปรโมชัน</span><span style="color:#4ade80;">-฿${parseFloat(order.promotion_discount).toLocaleString('th-TH')}</span>
                        </div>` : ''}
                        ${parseFloat(order.coupon_discount || 0) > 0 ? `
                        <div style="display:flex;justify-content:space-between;font-size:13px;color:rgba(255,255,255,0.65);margin-bottom:4px;">
                            <span>🎟 คูปองส่วนลด</span><span style="color:#4ade80;">-฿${parseFloat(order.coupon_discount).toLocaleString('th-TH')}</span>
                        </div>` : ''}
                        ${parseFloat(order.shipping_fee || 0) > 0 ? `
                        <div style="display:flex;justify-content:space-between;font-size:13px;color:rgba(255,255,255,0.65);margin-bottom:4px;">
                            <span>ค่าจัดส่ง</span><span>฿${parseFloat(order.shipping_fee).toLocaleString('th-TH')}</span>
                        </div>` : ''}
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 12px 0 0; margin-top: 4px; border-top: 2px solid rgba(255,255,255,0.15);">
                        <span style="color: #fff; font-size: 16px; font-weight: 600;">ยอดรวมทั้งหมด</span>
                        <span style="color: #fff; font-size: 20px; font-weight: 700;">฿${parseFloat(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</span>
                    </div>
                </div>
                
                ${shipmentsHtml}
                ${slipHtml}
                ${refundHtml}
                ${actionsHtml}
            </div>
        `;
        
        showModal(modalContent);
    } catch (error) {
        console.error('Error loading order details:', error);
        showGlobalAlert('ไม่สามารถโหลดรายละเอียดคำสั่งซื้อได้', 'error');
    }
}

async function updateShipmentTracking(orderId, shipmentId) {
    const provider = document.getElementById(`provider_${shipmentId}`).value;
    const tracking = document.getElementById(`tracking_${shipmentId}`).value.trim();
    
    if (!provider || !tracking) {
        showGlobalAlert('กรุณาเลือกขนส่งและใส่เลขพัสดุ', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/orders/${orderId}/shipments/${shipmentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shipping_provider: provider,
                tracking_number: tracking,
                status: 'shipped'
            })
        });
        
        if (response.ok) {
            showGlobalAlert('บันทึกเลขพัสดุสำเร็จ', 'success');
            viewOrderDetails(orderId);
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error updating shipment:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function approveOrder(orderId) {
    if (!confirm('ยืนยันการชำระเงินและอนุมัติคำสั่งซื้อนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });
        
        if (response.ok) {
            showGlobalAlert('อนุมัติคำสั่งซื้อสำเร็จ — สถานะเปลี่ยนเป็น "ที่ต้องจัดส่ง"', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error approving order:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function rejectOrder(orderId) {
    const reason = prompt('เหตุผลในการปฏิเสธ:');
    if (reason === null) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/reject`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        if (response.ok) {
            showGlobalAlert('ปฏิเสธสลิปสำเร็จ — ออเดอร์กลับเป็น "รอชำระเงิน"', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error rejecting order:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function updateOrderStatus(orderId, newStatus) {
    if (newStatus === 'paid') {
        await approveOrder(orderId);
    } else if (newStatus === 'rejected') {
        await rejectOrder(orderId);
    }
}

function cancelOrderAdmin(orderId, orderNumber, orderStatus) {
    document.getElementById('cancelOrderId').value = orderId;
    document.getElementById('cancelOrderNumber').textContent = orderNumber || `#${orderId}`;
    document.getElementById('cancelOrderReason').value = '';
    const modal = document.getElementById('cancelOrderModal');
    if (modal) modal.style.display = 'flex';
}

function closeCancelOrderModal() {
    const modal = document.getElementById('cancelOrderModal');
    if (modal) modal.style.display = 'none';
}

async function submitCancelOrder() {
    const orderId = document.getElementById('cancelOrderId').value;
    const reason = document.getElementById('cancelOrderReason').value.trim();
    if (!reason) {
        showGlobalAlert('กรุณาระบุเหตุผลการยกเลิก', 'error');
        return;
    }
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ reason })
        });
        const data = await response.json();
        if (response.ok) {
            closeCancelOrderModal();
            closeModal();
            if (data.requires_refund) {
                showGlobalAlert('ยกเลิกคำสั่งซื้อสำเร็จ — ออเดอร์อยู่ในสถานะ "รอคืนเงิน" กรุณาดำเนินการต่อในหน้าออเดอร์', 'success');
            } else {
                showGlobalAlert('ยกเลิกคำสั่งซื้อสำเร็จ', 'success');
            }
            loadOrders(currentOrdersStatus);
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (err) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function openRefundModal(orderId) {
    document.getElementById('refundOrderId').value = orderId;
    document.getElementById('refundSlipPreview').style.display = 'none';
    document.getElementById('refundSlipInput').value = '';
    document.getElementById('refundQrSection').style.display = 'none';
    document.getElementById('refundNoAccountWarning').style.display = 'none';
    document.getElementById('refundWeightInfo').textContent = '';

    const slipLabel = document.getElementById('refundSlipLabel');
    const submitBtn = document.getElementById('refundSubmitBtn');
    slipLabel.style.opacity = '1';
    slipLabel.style.cursor = 'pointer';
    slipLabel.style.pointerEvents = 'auto';
    submitBtn.disabled = false;
    submitBtn.style.opacity = '1';
    submitBtn.style.cursor = 'pointer';

    document.getElementById('refundModal').style.display = 'flex';

    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/refund-info`, { credentials: 'include' });
        const d = await resp.json();
        if (!resp.ok) { showGlobalAlert(d.error || 'โหลดข้อมูลไม่ได้', 'error'); return; }

        document.getElementById('refundOrderNumber').textContent = d.order_number || `#${orderId}`;
        document.getElementById('refundTotalPaid').textContent = `฿${(d.final_amount||0).toLocaleString('th-TH',{minimumFractionDigits:2})}`;
        document.getElementById('refundShippingDeducted').textContent = `-฿${(d.shipping_fee||0).toLocaleString('th-TH',{minimumFractionDigits:2})}`;
        document.getElementById('refundAmount').textContent = `฿${(d.refund_amount||0).toLocaleString('th-TH',{minimumFractionDigits:2})}`;
        document.getElementById('refundTotalPaidVal').value = d.final_amount || 0;
        document.getElementById('refundShippingVal').value = d.shipping_fee || 0;
        document.getElementById('refundAmountVal').value = d.refund_amount || 0;

        // Show weight info below "หักค่าขนส่ง"
        const wg = d.total_weight_g || 0;
        const tier = d.rate_tier;
        if (wg > 0 && tier) {
            const maxLabel = tier.max_weight ? `${tier.max_weight.toLocaleString()}g` : 'ขึ้นไป';
            document.getElementById('refundWeightInfo').textContent =
                `น้ำหนักรวม ${wg.toLocaleString()}g (${tier.min_weight.toLocaleString()}–${maxLabel})`;
        } else if (wg === 0) {
            document.getElementById('refundWeightInfo').textContent = 'ไม่มีข้อมูลน้ำหนักสินค้า';
        }

        const r = d.reseller || {};
        const hasAccount = !!(r.bank_account_number || r.promptpay_number);
        let bankHtml = '';
        if (r.bank_name || r.bank_account_number) {
            bankHtml += `<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" style="flex-shrink:0;"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
                <span>${escapeHtml(r.bank_name||'-')} — ${escapeHtml(r.bank_account_number||'-')}</span></div>`;
            bankHtml += `<div style="margin-left:21px;color:rgba(255,255,255,0.7);">${escapeHtml(r.bank_account_name||'')}</div>`;
        }
        if (r.promptpay_number) {
            bankHtml += `<div style="display:flex;gap:8px;align-items:center;margin-top:${r.bank_account_number ? '8' : '0'}px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" style="flex-shrink:0;"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>
                <span style="color:#34d399;">PromptPay: ${escapeHtml(r.promptpay_number)}</span></div>`;
        }
        if (!hasAccount) {
            bankHtml = '<span style="color:rgba(255,255,255,0.4);font-size:12px;">สมาชิกยังไม่ได้บันทึกข้อมูลบัญชี</span>';
        }
        document.getElementById('refundBankDetails').innerHTML = bankHtml;

        // Disable slip + confirm if no account info
        if (!hasAccount) {
            document.getElementById('refundNoAccountWarning').style.display = 'block';
            slipLabel.style.opacity = '0.35';
            slipLabel.style.cursor = 'not-allowed';
            slipLabel.style.pointerEvents = 'none';
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.35';
            submitBtn.style.cursor = 'not-allowed';
        }

        if (r.promptpay_number && d.refund_amount > 0) {
            try {
                const qrResp = await fetch(`${API_URL}/admin/orders/${orderId}/refund-qr?amount=${d.refund_amount}`, { credentials: 'include' });
                const qrData = await qrResp.json();
                if (qrResp.ok && qrData.qr_image) {
                    document.getElementById('refundQrImage').src = qrData.qr_image;
                    document.getElementById('refundQrName').textContent = qrData.account_name || '';
                    document.getElementById('refundQrPhone').textContent = qrData.promptpay_number || '';
                    document.getElementById('refundQrSection').style.display = 'block';
                }
            } catch(e) {}
        }
    } catch(err) {
        showGlobalAlert('เกิดข้อผิดพลาดในการโหลดข้อมูลคืนเงิน', 'error');
    }
}

function closeRefundModal() {
    document.getElementById('refundModal').style.display = 'none';
}

function downloadRefundQr() {
    const img = document.getElementById('refundQrImage');
    if (!img || !img.src || img.src === window.location.href) return;

    const accountName = document.getElementById('refundQrName').textContent.trim() || '';
    const phone      = document.getElementById('refundQrPhone').textContent.trim() || '';
    const amount     = parseFloat(document.getElementById('refundAmountVal').value || 0);
    const orderNum   = document.getElementById('refundOrderNumber').textContent.trim() || '';
    const amountText = `฿${amount.toLocaleString('th-TH', { minimumFractionDigits: 2 })}`;

    const QR_SIZE  = 220;
    const PAD      = 24;
    const W        = QR_SIZE + PAD * 2;
    const LINE_H   = 22;
    const HEADER_H = 54;
    const FOOTER_H = PAD + LINE_H * 3 + PAD;
    const H        = HEADER_H + QR_SIZE + FOOTER_H;

    const canvas = document.createElement('canvas');
    canvas.width  = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');

    // background
    ctx.fillStyle = '#1a0a2e';
    ctx.fillRect(0, 0, W, H);

    // header band
    const grad = ctx.createLinearGradient(0, 0, W, HEADER_H);
    grad.addColorStop(0, '#7c3aed');
    grad.addColorStop(1, '#a855f7');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, HEADER_H);

    // header text
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 15px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('PromptPay', W / 2, 22);
    ctx.font = '12px sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,0.75)';
    ctx.fillText(orderNum, W / 2, 40);

    // QR image
    ctx.drawImage(img, PAD, HEADER_H, QR_SIZE, QR_SIZE);

    // footer — amount
    const FY = HEADER_H + QR_SIZE + 16;
    ctx.font = 'bold 20px sans-serif';
    ctx.fillStyle = '#fbbf24';
    ctx.textAlign = 'center';
    ctx.fillText(amountText, W / 2, FY);

    // account name
    ctx.font = '13px sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fillText(accountName, W / 2, FY + LINE_H);

    // phone
    ctx.font = '12px sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.fillText(phone, W / 2, FY + LINE_H * 2);

    const filename = `QR_คืนเงิน_${orderNum}_${accountName}.png`.replace(/\s+/g, '_');
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function previewRefundSlip(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('refundSlipImg').src = e.target.result;
        document.getElementById('refundSlipPreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

async function submitRefund() {
    const btn = document.getElementById('refundSubmitBtn');
    if (btn.disabled) return;
    const orderId = document.getElementById('refundOrderId').value;
    const slipInput = document.getElementById('refundSlipInput');
    if (!slipInput.files[0]) {
        showGlobalAlert('กรุณาแนบสลิปการโอนก่อน', 'error');
        return;
    }
    btn.textContent = 'กำลังบันทึก...';
    btn.disabled = true;

    const slipFile = slipInput.files[0];
    const reader = new FileReader();
    reader.onload = async (e) => {
        const slipData = e.target.result;
        const bankInfo = {};
        const bankDetails = document.getElementById('refundBankDetails').textContent;
        try {
            const resp = await fetch(`${API_URL}/admin/orders/${orderId}/refund-info`, { credentials: 'include' });
            const d = await resp.json();
            const r = d.reseller || {};
            const payload = {
                refund_amount: parseFloat(document.getElementById('refundAmountVal').value),
                shipping_deducted: parseFloat(document.getElementById('refundShippingVal').value),
                total_paid: parseFloat(document.getElementById('refundTotalPaidVal').value),
                bank_name: r.bank_name || '',
                bank_account_number: r.bank_account_number || '',
                bank_account_name: r.bank_account_name || '',
                promptpay_number: r.promptpay_number || '',
                slip_data: slipData,
            };
            const saveResp = await fetch(`${API_URL}/admin/orders/${orderId}/refund`, {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const saveData = await saveResp.json();
            if (saveResp.ok) {
                closeRefundModal();
                showGlobalAlert('💸 บันทึกการคืนเงินสำเร็จ แจ้งสมาชิกในแชทแล้ว', 'success');
                loadOrders(currentOrdersStatus);
            } else {
                showGlobalAlert(saveData.error || 'เกิดข้อผิดพลาด', 'error');
            }
        } catch(err) {
            showGlobalAlert('เกิดข้อผิดพลาด', 'error');
        } finally {
            btn.textContent = 'ยืนยันคืนเงิน';
            btn.disabled = false;
        }
    };
    reader.readAsDataURL(slipFile);
}

async function openReturnStockModal(orderId) {
    const modal = document.getElementById('returnStockModal');
    if (!modal) return;
    document.getElementById('returnStockOrderId').value = orderId;
    document.getElementById('returnStockItems').innerHTML = '<div style="color: rgba(255,255,255,0.6); text-align: center; padding: 20px;">กำลังโหลด...</div>';
    modal.style.display = 'flex';
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/return-stock-info`, { credentials: 'include' });
        const d = await resp.json();
        if (!resp.ok) { showGlobalAlert(d.error || 'โหลดข้อมูลไม่ได้', 'error'); modal.style.display = 'none'; return; }
        document.getElementById('returnStockOrderNumber').textContent = d.order_number || `#${orderId}`;
        if (!d.was_shipped) {
            document.getElementById('returnStockItems').innerHTML = `
                <div style="background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.3); border-radius: 10px; padding: 14px; color: #f97316; font-size: 13px; text-align: center;">
                    ออเดอร์นี้ยังไม่เคยจัดส่ง — ไม่มีสินค้าที่ต้องรับคืน
                </div>`;
            return;
        }
        let html = '';
        if (!d.items || d.items.length === 0) {
            html = '<div style="color: rgba(255,255,255,0.5); text-align: center; padding: 20px;">ไม่พบรายการสินค้า</div>';
        } else {
            d.items.forEach((item, i) => {
                const hasHistory = item.return_history && item.return_history.length > 0;
                const historyHtml = hasHistory ? item.return_history.map(h => {
                    const isGood = h.type === 'return_from_order';
                    const color = isGood ? '#22c55e' : '#f97316';
                    const icon = isGood ? '✅' : '⚠️';
                    return `<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
                        <div>
                            <span style="font-size:11px;color:${color};">${icon} ${h.qty} ชิ้น — ${escapeHtml(h.label)}</span>
                            <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-top:1px;">${escapeHtml(h.notes)}</div>
                        </div>
                        <div style="text-align:right;flex-shrink:0;margin-left:8px;">
                            <div style="font-size:10px;color:rgba(255,255,255,0.35);">${escapeHtml(h.date)}</div>
                            <div style="font-size:10px;color:rgba(255,255,255,0.3);">${escapeHtml(h.admin_name)}</div>
                        </div>
                    </div>`;
                }).join('') : '';

                const allDone = item.max_returnable <= 0;
                html += `
                <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 14px; margin-bottom: 10px; ${allDone ? 'opacity:0.6;' : ''}">
                    <div style="font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 2px;">${escapeHtml(item.product_name)}</div>
                    ${item.variant_options ? `<div style="font-size: 12px; color: rgba(255,255,255,0.75); margin-bottom: 2px;">${escapeHtml(item.variant_options)}</div>` : ''}
                    <div style="font-size: 12px; color: rgba(255,255,255,0.45); margin-bottom: 6px;">SKU: ${escapeHtml(item.sku_code || '-')}</div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.5); margin-bottom: ${hasHistory ? '8px' : '10px'};">
                        คลัง: ${escapeHtml(item.warehouse_name || '-')} | ส่งออกไป: ${item.shipped_qty} ชิ้น | บันทึกแล้ว: ${item.already_accounted} ชิ้น
                    </div>
                    ${hasHistory ? `
                    <div style="background:rgba(0,0,0,0.2);border-radius:7px;padding:8px 10px;margin-bottom:10px;">
                        <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px;font-weight:600;">ประวัติการบันทึก</div>
                        ${historyHtml}
                    </div>` : ''}
                    ${allDone ? `<div style="font-size:12px;color:#22c55e;text-align:center;padding:6px;background:rgba(34,197,94,0.1);border-radius:6px;">✅ บันทึกครบแล้ว (${item.shipped_qty} ชิ้น)</div>` : `
                    <div style="display:flex;flex-direction:column;gap:8px;">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <label style="font-size:12px;color:rgba(255,255,255,0.7);white-space:nowrap;min-width:80px;">เหตุผล:</label>
                            <select id="returnReason_${i}" onchange="onReturnReasonChange(${i})"
                                style="flex:1;padding:6px 10px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:6px;color:#fff;font-size:12px;">
                                <option value="good">✅ สภาพดี — บันทึกคืนคลัง</option>
                                <option value="damaged">⚠️ มีตำหนิ — ไม่คืนคลัง</option>
                                <option value="lost">❌ สูญหาย — ไม่คืนคลัง</option>
                                <option value="other">✏️ อื่นๆ — บันทึกคืนคลัง</option>
                            </select>
                        </div>
                        <div id="returnCustomNote_${i}" style="display:none;">
                            <input type="text" id="returnCustomNoteText_${i}" placeholder="ระบุเหตุผล..."
                                style="width:100%;box-sizing:border-box;padding:6px 10px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:6px;color:#fff;font-size:12px;">
                        </div>
                        <div style="display:flex;align-items:center;gap:10px;">
                            <label style="font-size:12px;color:rgba(255,255,255,0.7);white-space:nowrap;min-width:80px;">จำนวน:</label>
                            <input type="number" id="returnQty_${i}" min="0" max="${item.max_returnable}" value="${item.max_returnable}"
                                data-sku-id="${item.sku_id}" data-warehouse-id="${item.warehouse_id}"
                                oninput="if(parseInt(this.value)>parseInt(this.max)){this.value=this.max;showGlobalAlert('จำนวนต้องไม่เกิน ${item.max_returnable} ชิ้น','warning');}"
                                style="width:80px;padding:6px 10px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:6px;color:#fff;font-size:13px;text-align:center;">
                            <span style="font-size:12px;color:rgba(255,255,255,0.5);">/ ${item.max_returnable} ชิ้น</span>
                        </div>
                    </div>`}
                </div>`;
            });
        }
        document.getElementById('returnStockItems').innerHTML = html;
        window._returnStockItemCount = d.items ? d.items.length : 0;
    } catch(e) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
        modal.style.display = 'none';
    }
}

function closeReturnStockModal() {
    const modal = document.getElementById('returnStockModal');
    if (modal) modal.style.display = 'none';
}

function onReturnReasonChange(i) {
    const reason = document.getElementById(`returnReason_${i}`)?.value;
    const noteEl = document.getElementById(`returnCustomNote_${i}`);
    if (noteEl) noteEl.style.display = reason === 'other' ? 'block' : 'none';
}

async function submitReturnStock() {
    const orderId = document.getElementById('returnStockOrderId').value;
    const count = window._returnStockItemCount || 0;
    const items = [];
    for (let i = 0; i < count; i++) {
        const input = document.getElementById(`returnQty_${i}`);
        if (!input) continue;
        const qty = parseInt(input.value) || 0;
        const reason = document.getElementById(`returnReason_${i}`)?.value || 'good';
        const customNote = document.getElementById(`returnCustomNoteText_${i}`)?.value?.trim() || '';
        if (qty > 0) {
            if (qty > parseInt(input.max || 0)) {
                showGlobalAlert(`จำนวนสินค้าเกินที่จัดส่งไป (สูงสุด ${input.max} ชิ้น)`, 'error');
                return;
            }
            items.push({
                sku_id: parseInt(input.dataset.skuId),
                warehouse_id: parseInt(input.dataset.warehouseId),
                return_qty: qty,
                reason,
                custom_note: customNote
            });
        }
    }
    if (items.length === 0) {
        showGlobalAlert('กรุณาระบุจำนวนสินค้าที่ต้องการบันทึก', 'error');
        return;
    }
    const btn = document.getElementById('returnStockSubmitBtn');
    btn.textContent = 'กำลังบันทึก...';
    btn.disabled = true;
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/return-stock`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items })
        });
        const data = await resp.json();
        if (resp.ok) {
            closeReturnStockModal();
            showGlobalAlert(data.message || 'รับสินค้าคืนคลังสำเร็จ', 'success');
            loadOrders(currentOrdersStatus);
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch(e) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    } finally {
        btn.textContent = 'ยืนยันรับสินค้าคืน';
        btn.disabled = false;
    }
}

async function markDelivered(orderId) {
    if (!confirm('ยืนยันว่าลูกค้าได้รับสินค้าแล้ว?')) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/mark-delivered`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showGlobalAlert('อัปเดตสถานะสำเร็จ - จัดส่งสำเร็จ', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error marking delivered:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function markFailedDelivery(orderId) {
    const reason = prompt('เหตุผลที่จัดส่งไม่สำเร็จ:', 'สินค้าตีกลับ');
    if (!reason) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/mark-failed-delivery`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        if (response.ok) {
            showGlobalAlert('อัปเดตสถานะสำเร็จ - จัดส่งไม่สำเร็จ', 'warning');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error marking failed delivery:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function reshipOrder(orderId) {
    if (!confirm('เริ่มจัดส่งใหม่สำหรับคำสั่งซื้อนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/reship`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showGlobalAlert('เริ่มจัดส่งใหม่สำเร็จ', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error reshipping order:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function printShippingLabel(shipmentIndex) {
    const order = window.currentOrderData;
    if (!order || !order.shipments || !order.shipments[shipmentIndex]) {
        showGlobalAlert('ไม่พบข้อมูล Shipment', 'error');
        return;
    }
    
    const shipment = order.shipments[shipmentIndex];
    const orderNumber = order.order_number || `ORD-${order.id}`;
    const orderDate = new Date(order.created_at).toLocaleDateString('th-TH', { 
        year: 'numeric', month: 'short', day: 'numeric' 
    });
    
    // Sender info (from reseller or store)
    const senderName = order.reseller_brand_name || order.reseller_name || 'ร้านค้า';
    const senderPhone = order.reseller_phone || '-';
    const senderAddress = [order.reseller_address, order.reseller_subdistrict, order.reseller_district, order.reseller_province].filter(Boolean).join(' ') || '-';
    
    // Recipient info (customer or reseller if no customer)
    let recipientName = '-', recipientPhone = '-', recipientAddress = '-';
    if (order.customer) {
        recipientName = order.customer.full_name || '-';
        recipientPhone = order.customer.phone || '-';
        recipientAddress = [order.customer.address, order.customer.subdistrict, order.customer.district, order.customer.province, order.customer.postal_code].filter(Boolean).join(' ') || '-';
    } else {
        // Fallback to reseller as recipient
        recipientName = order.reseller_name || '-';
        recipientPhone = order.reseller_phone || '-';
        recipientAddress = [order.reseller_address, order.reseller_subdistrict, order.reseller_district, order.reseller_province, order.reseller_postal_code].filter(Boolean).join(' ') || '-';
    }
    
    // Shipment info
    const warehouseName = shipment.warehouse_name || 'คลังสินค้า';
    const shippingProvider = shipment.shipping_provider || '';
    const trackingNumber = shipment.tracking_number || '';
    
    // Items
    const totalQty = shipment.items.reduce((sum, i) => sum + i.quantity, 0);
    const itemsHtml = shipment.items.map((item, idx) => {
        const variantDisplay = item.variant_name ? ` (${item.variant_name})` : '';
        const customizationDisplay = item.customization_labels && item.customization_labels.length > 0 
            ? `<div style="font-size: 11px; color: #6b21a8; margin-top: 3px;">${item.customization_labels.join(', ')}</div>` 
            : '';
        return `
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center; vertical-align: top;">
                <span style="display: inline-block; width: 18px; height: 18px; border: 2px solid #333; border-radius: 3px; vertical-align: middle;"></span>
            </td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; vertical-align: top;">${idx + 1}. ${item.product_name || 'สินค้า'}${variantDisplay}${customizationDisplay}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; font-size: 11px; color: #666; vertical-align: top;">${item.sku_code || ''}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center; font-weight: bold; vertical-align: top;">x ${item.quantity}</td>
        </tr>
    `;
    }).join('');
    
    // Open print window
    const printWindow = window.open('', '_blank', 'width=800,height=1100');
    printWindow.document.write(`
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ใบปะหน้าพัสดุ - ${orderNumber}</title>
    <style>
        @page { size: A4; margin: 10mm; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Sarabun', 'Segoe UI', sans-serif; font-size: 14px; color: #333; }
        .page { width: 190mm; min-height: 277mm; margin: 0 auto; }
        .half { height: 138.5mm; padding: 15px; }
        .shipping-half { border-bottom: 3px dashed #999; }
        .packing-half { }
        .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 2px solid #333; }
        .provider-box { background: #f0f0f0; padding: 8px 15px; border-radius: 5px; font-size: 16px; font-weight: bold; }
        .tracking-box { text-align: center; }
        .tracking-number { font-size: 16px; font-weight: bold; letter-spacing: 1px; margin-bottom: 4px; }
        .barcode-container { display: flex; justify-content: center; margin: 6px 0 2px; }
        .barcode-container svg { max-width: 260px; height: 60px; }
        .addresses { display: flex; gap: 20px; margin-bottom: 15px; }
        .address-box { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 8px; }
        .address-box h4 { font-size: 12px; color: #666; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .address-box .name { font-size: 16px; font-weight: bold; margin-bottom: 5px; }
        .address-box .phone { color: #333; margin-bottom: 5px; }
        .address-box .addr { font-size: 13px; line-height: 1.4; }
        .order-info { display: flex; justify-content: space-between; padding: 10px; background: #f5f5f5; border-radius: 5px; font-size: 13px; }
        .packing-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .packing-title { font-size: 18px; font-weight: bold; }
        .warehouse-badge { background: #e0e7ff; color: #3730a3; padding: 5px 12px; border-radius: 5px; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
        th { background: #f0f0f0; padding: 10px; text-align: left; font-size: 12px; border-bottom: 2px solid #ddd; }
        .summary { display: flex; justify-content: space-between; padding: 10px; background: #f5f5f5; border-radius: 5px; }
        .signature { display: flex; gap: 30px; margin-top: auto; }
        .sig-box { flex: 1; }
        .sig-line { border-bottom: 1px solid #333; height: 25px; margin-bottom: 5px; }
        .sig-label { font-size: 11px; color: #666; }
        @media print { 
            body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            .page { width: 100%; }
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script>
</head>
<body>
    <div class="page">
        <!-- Top Half: Shipping Info -->
        <div class="half shipping-half">
            <div class="header">
                <div class="provider-box">${shippingProvider || '-- ขนส่ง --'}</div>
                <div class="tracking-box">
                    ${trackingNumber ? `
                        <div class="tracking-number">${trackingNumber}</div>
                        <div class="barcode-container">
                            <svg id="barcode-main"></svg>
                        </div>
                    ` : '<div style="color: #999; font-size: 13px;">-- ยังไม่มีเลขพัสดุ --</div>'}
                </div>
            </div>
            
            <div class="addresses">
                <div class="address-box">
                    <h4>ผู้ส่ง</h4>
                    <div class="name">${senderName}</div>
                    <div class="phone">โทร: ${senderPhone}</div>
                    <div class="addr">${senderAddress}</div>
                </div>
                <div class="address-box">
                    <h4>ผู้รับ</h4>
                    <div class="name">${recipientName}</div>
                    <div class="phone">โทร: ${recipientPhone}</div>
                    <div class="addr">${recipientAddress}</div>
                </div>
            </div>
            
            <div class="order-info">
                <span><strong>Order:</strong> ${orderNumber}</span>
                <span><strong>วันที่:</strong> ${orderDate}</span>
                <span><strong>จำนวน:</strong> ${totalQty} ชิ้น</span>
            </div>
        </div>
        
        <!-- Bottom Half: Packing List -->
        <div class="half packing-half">
            <div class="packing-header">
                <div class="packing-title">ใบจัดสินค้า</div>
                <div class="warehouse-badge">คลัง: ${warehouseName}</div>
            </div>
            
            <div style="margin-bottom: 10px; font-size: 13px;">
                <strong>Order:</strong> ${orderNumber} | <strong>วันที่:</strong> ${orderDate}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th style="width: 40px; text-align: center;">✓</th>
                        <th>รายการสินค้า</th>
                        <th style="width: 120px;">SKU</th>
                        <th style="width: 60px; text-align: center;">จำนวน</th>
                    </tr>
                </thead>
                <tbody>
                    ${itemsHtml}
                </tbody>
            </table>
            
            <div class="summary">
                <span><strong>รวมทั้งหมด:</strong> ${totalQty} ชิ้น</span>
                <span><strong>ผู้รับ:</strong> ${recipientName}</span>
            </div>
            
            <div class="signature">
                <div class="sig-box">
                    <div class="sig-line"></div>
                    <div class="sig-label">ผู้จัดสินค้า</div>
                </div>
                <div class="sig-box">
                    <div class="sig-line"></div>
                    <div class="sig-label">วันที่/เวลา</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        window.onload = function() {
            var barcodeEl = document.getElementById('barcode-main');
            if (barcodeEl && typeof JsBarcode !== 'undefined') {
                try {
                    JsBarcode('#barcode-main', '${trackingNumber}', {
                        format: 'CODE128',
                        width: 2,
                        height: 55,
                        displayValue: false,
                        margin: 0
                    });
                } catch(e) {
                    barcodeEl.parentElement.style.display = 'none';
                }
            }
            setTimeout(function() {
                window.print();
            }, 500);
        };
    </script>
</body>
</html>
    `);
    printWindow.document.close();
}

function showModal(content) {
    let modal = document.getElementById('dynamicModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'dynamicModal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 600px;">
                <button class="modal-close" onclick="closeModal()">&times;</button>
                <div id="dynamicModalContent"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    document.getElementById('dynamicModalContent').innerHTML = content;
    modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('dynamicModal');
    if (modal) modal.classList.remove('active');
}

// Orders status tabs
document.addEventListener('DOMContentLoaded', function() {
    const orderStatusTabs = document.getElementById('orderStatusTabs');
    if (orderStatusTabs) {
        orderStatusTabs.addEventListener('click', function(e) {
            if (e.target.classList.contains('status-tab')) {
                orderStatusTabs.querySelectorAll('.status-tab').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                loadOrders(e.target.dataset.status);
            }
        });
    }
});

