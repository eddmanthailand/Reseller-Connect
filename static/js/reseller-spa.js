const RESELLER_API_URL = '/api';

let currentUser = null;
let customers = [];
let products = [];
let cartItems = [];

document.addEventListener('DOMContentLoaded', function() {
    init();
});

async function init() {
    try {
        await loadCurrentUser();
        setupNavigation();
        handleHashNavigation();
        window.addEventListener('hashchange', handleHashNavigation);
        
        loadDashboardData();
        loadCartBadge();
    } catch (error) {
        console.error('Initialization error:', error);
        window.location.href = '/login';
    }
}

function handleHashNavigation() {
    const hash = window.location.hash.substring(1) || 'home';
    const validPages = ['home', 'catalog', 'cart', 'orders', 'customers', 'profile'];
    if (validPages.includes(hash)) {
        switchPage(hash);
    }
}

function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            if (page) {
                window.location.hash = page;
            }
        });
    });
}

function switchPage(pageName) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });

    document.querySelectorAll('.page-content').forEach(page => {
        page.classList.toggle('active', page.id === `page-${pageName}`);
    });

    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.remove('active');
        document.querySelector('.sidebar-overlay').classList.remove('active');
    }

    switch (pageName) {
        case 'home':
            loadDashboardData();
            break;
        case 'catalog':
            loadProducts();
            break;
        case 'cart':
            loadCart();
            break;
        case 'orders':
            loadOrders();
            break;
        case 'customers':
            loadCustomers();
            break;
        case 'profile':
            loadProfile();
            break;
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    sidebar.classList.toggle('active');
    overlay.classList.toggle('active');
}

async function loadCurrentUser() {
    const response = await fetch(`${RESELLER_API_URL}/me`);
    if (!response.ok) throw new Error('Not authenticated');
    
    currentUser = await response.json();
    
    document.getElementById('userName').textContent = currentUser.full_name;
    document.getElementById('userAvatar').textContent = currentUser.full_name.charAt(0).toUpperCase();
    document.getElementById('welcomeText').textContent = `ยินดีต้อนรับ, ${currentUser.full_name}`;
    
    const tierIcons = { 'Bronze': '🥉', 'Silver': '🥈', 'Gold': '🥇', 'Platinum': '💎' };
    const tierName = currentUser.reseller_tier || 'Bronze';
    
    document.getElementById('tierIcon').textContent = tierIcons[tierName] || '🏷️';
    document.getElementById('userTier').textContent = tierName;
    
    ['catalog', 'profile'].forEach(prefix => {
        const iconEl = document.getElementById(`${prefix}TierIcon`);
        const nameEl = document.getElementById(`${prefix}TierName`);
        if (iconEl) iconEl.textContent = tierIcons[tierName] || '🏷️';
        if (nameEl) nameEl.textContent = tierName;
    });
}

async function loadDashboardData() {
    try {
        const [dashboardRes, productsRes, customersRes, ordersRes, cartRes] = await Promise.all([
            fetch(`${RESELLER_API_URL}/reseller/dashboard-stats`),
            fetch(`${RESELLER_API_URL}/reseller/products?limit=8`),
            fetch(`${RESELLER_API_URL}/reseller/customers`),
            fetch(`${RESELLER_API_URL}/reseller/recent-orders?limit=5`),
            fetch(`${RESELLER_API_URL}/reseller/cart`)
        ]);
        
        if (dashboardRes.ok) {
            const data = await dashboardRes.json();
            
            document.getElementById('statMonthTotal').textContent = formatCurrency(data.month_stats?.total || 0);
            document.getElementById('statMonthOrders').textContent = `${data.month_stats?.orders || 0} คำสั่งซื้อ`;
            
            document.getElementById('statTotalSpent').textContent = formatCurrency(data.all_time_stats?.total || 0);
            document.getElementById('statTotalOrders').textContent = `${data.all_time_stats?.orders || 0} คำสั่งซื้อ`;
            
            const pendingTotal = Object.values(data.pending_orders || {}).reduce((a, b) => a + b, 0);
            document.getElementById('statPendingOrders').textContent = pendingTotal;
            
            const pendingPayment = data.pending_orders?.pending_payment || 0;
            const underReview = data.pending_orders?.under_review || 0;
            let pendingText = [];
            if (pendingPayment > 0) pendingText.push(`รอชำระ ${pendingPayment}`);
            if (underReview > 0) pendingText.push(`รอตรวจ ${underReview}`);
            document.getElementById('statPendingDetail').textContent = pendingText.join(', ') || 'ไม่มี';
            
            updateTierProgress(data.tier_progress, data.all_time_stats?.total || 0);
        }
        
        if (cartRes.ok) {
            const cartData = await cartRes.json();
            const cartCount = (cartData.items || []).reduce((sum, item) => sum + item.quantity, 0);
            document.getElementById('statCartCount').textContent = cartCount;
        }
        
        if (customersRes.ok) {
            const data = await customersRes.json();
            const customerCount = (data.customers || []).length;
            const el = document.getElementById('statCustomers');
            if (el) el.textContent = customerCount;
        }
        
        if (ordersRes.ok) {
            const data = await ordersRes.json();
            renderRecentOrders(data.orders || []);
        }
        
        if (productsRes.ok) {
            const data = await productsRes.json();
            renderFeaturedProducts(data.products || []);
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

function formatCurrency(amount) {
    return `฿${(amount || 0).toLocaleString()}`;
}

function updateTierProgress(tierProgress, totalPurchases) {
    if (!tierProgress) return;
    
    const tierIcons = { 'Bronze': '🥉', 'Silver': '🥈', 'Gold': '🥇', 'Platinum': '💎' };
    const tierDescriptions = { 
        'Bronze': 'ระดับเริ่มต้น', 
        'Silver': 'ระดับเงิน', 
        'Gold': 'ระดับทอง', 
        'Platinum': 'ระดับสูงสุด' 
    };
    
    const currentTier = tierProgress.current_tier || 'Bronze';
    document.getElementById('homeTierBadgeIcon').textContent = tierIcons[currentTier] || '🥉';
    document.getElementById('homeTierName').textContent = currentTier;
    document.getElementById('homeTierDescription').textContent = tierProgress.tier_description || tierDescriptions[currentTier] || '';
    document.getElementById('homeTotalPurchases').textContent = formatCurrency(tierProgress.total_purchases || totalPurchases);
    
    if (tierProgress.next_tier) {
        document.getElementById('homeNextTierInfo').style.display = 'block';
        document.getElementById('homeNextTierName').textContent = tierProgress.next_tier;
        
        const remaining = tierProgress.amount_to_next || 0;
        document.getElementById('homeAmountToNext').textContent = `อีก ${formatCurrency(remaining)} สู่ระดับถัดไป`;
        
        const progress = tierProgress.progress_percent || 0;
        document.getElementById('homeTierProgressBar').style.width = `${progress}%`;
    } else {
        document.getElementById('homeNextTierInfo').style.display = 'none';
        document.getElementById('homeAmountToNext').textContent = 'ระดับสูงสุดแล้ว!';
        document.getElementById('homeTierProgressBar').style.width = '100%';
    }
}

function renderRecentOrders(orders) {
    const container = document.getElementById('recentOrdersList');
    
    if (!orders || orders.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="padding: 30px;">
                <p>ยังไม่มีคำสั่งซื้อ</p>
            </div>
        `;
        return;
    }
    
    const statusLabels = {
        'pending_payment': 'รอชำระเงิน',
        'pending_verification': 'รอตรวจสอบ',
        'paid': 'ชำระแล้ว',
        'processing': 'กำลังจัดส่ง',
        'shipped': 'จัดส่งแล้ว',
        'completed': 'เสร็จสิ้น',
        'cancelled': 'ยกเลิก'
    };
    
    const statusColors = {
        'pending_payment': '#fbbf24',
        'pending_verification': '#60a5fa',
        'paid': '#4ade80',
        'processing': '#a78bfa',
        'shipped': '#22d3ee',
        'completed': '#4ade80',
        'cancelled': '#f87171'
    };
    
    container.innerHTML = orders.map(order => `
        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(255,255,255,0.1); border-radius: 10px; cursor: pointer;" onclick="switchPage('orders')">
            <div style="width: 36px; height: 36px; border-radius: 8px; background: ${statusColors[order.status] || '#666'}20; display: flex; align-items: center; justify-content: center;">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="${statusColors[order.status] || '#666'}" stroke-width="2" width="18" height="18"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            </div>
            <div style="flex: 1;">
                <div style="font-weight: 600; font-size: 14px;">#${order.order_number}</div>
                <div style="font-size: 12px; color: rgba(255,255,255,0.6);">${new Date(order.created_at).toLocaleDateString('th-TH')}</div>
            </div>
            <div style="text-align: right;">
                <div style="font-weight: 600; color: #4ade80;">${formatCurrency(order.final_amount || 0)}</div>
                <div style="font-size: 11px; padding: 2px 8px; border-radius: 8px; background: ${statusColors[order.status] || '#666'}20; color: ${statusColors[order.status] || '#666'};">${statusLabels[order.status] || order.status}</div>
            </div>
        </div>
    `).join('');
}

function renderFeaturedProducts(products) {
    const container = document.getElementById('featuredProducts');
    
    if (!products || products.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>ยังไม่มีสินค้า</p></div>';
        return;
    }
    
    container.innerHTML = products.slice(0, 4).map(product => `
        <div class="product-card" onclick="viewProduct(${product.id})">
            ${product.image_url 
                ? `<img src="${product.image_url}" alt="${product.name}" class="product-image">`
                : `<div class="product-image placeholder"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg></div>`
            }
            <div class="product-info">
                <div class="product-brand">${product.brand_name || ''}</div>
                <div class="product-name">${product.name}</div>
                <div class="product-price">
                    ฿${(product.discounted_min_price || product.min_price || 0).toLocaleString()}
                    ${product.discount_percent > 0 ? `<span class="product-price-original">฿${(product.min_price || 0).toLocaleString()}</span><span class="product-discount">-${product.discount_percent}%</span>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

async function loadProducts() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/products`);
        if (!response.ok) throw new Error('Failed to load products');
        
        const data = await response.json();
        products = data.products || [];
        renderProducts(products);
    } catch (error) {
        console.error('Error loading products:', error);
    }
}

function renderProducts(productsToRender) {
    const container = document.getElementById('productGrid');
    
    if (!productsToRender || productsToRender.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>ไม่พบสินค้า</p></div>';
        return;
    }
    
    container.innerHTML = productsToRender.map(product => `
        <div class="product-card" onclick="viewProduct(${product.id})">
            ${product.image_url 
                ? `<img src="${product.image_url}" alt="${product.name}" class="product-image">`
                : `<div class="product-image placeholder"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg></div>`
            }
            <div class="product-info">
                <div class="product-brand">${product.brand_name || ''}</div>
                <div class="product-name">${product.name}</div>
                <div class="product-price">
                    ฿${(product.discounted_min_price || product.min_price || 0).toLocaleString()}
                    ${product.discount_percent > 0 ? `<span class="product-price-original">฿${(product.min_price || 0).toLocaleString()}</span><span class="product-discount">-${product.discount_percent}%</span>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

function viewProduct(productId) {
    window.location.href = `/reseller/product/${productId}`;
}

document.getElementById('productSearch')?.addEventListener('input', function() {
    const search = this.value.toLowerCase();
    const filtered = products.filter(p => 
        p.name.toLowerCase().includes(search) || 
        (p.brand_name && p.brand_name.toLowerCase().includes(search))
    );
    renderProducts(filtered);
});

async function loadCart() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`);
        if (!response.ok) throw new Error('Failed to load cart');
        
        const data = await response.json();
        cartItems = data.items || [];
        renderCart();
    } catch (error) {
        console.error('Error loading cart:', error);
    }
}

function renderCart() {
    const container = document.getElementById('cartContent');
    document.getElementById('cartItemCount').textContent = `${cartItems.length} รายการ`;
    
    if (!cartItems || cartItems.length === 0) {
        container.innerHTML = `
            <div class="cart-empty">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                <h3>ตะกร้าว่างเปล่า</h3>
                <p>เลือกสินค้าเพื่อเพิ่มลงตะกร้า</p>
                <button class="btn-primary" style="margin-top: 16px;" onclick="switchPage('catalog')">เลือกซื้อสินค้า</button>
            </div>
        `;
        return;
    }
    
    const total = cartItems.reduce((sum, item) => sum + (item.final_price * item.quantity), 0);
    
    container.innerHTML = `
        <div style="display: grid; grid-template-columns: 1fr 300px; gap: 24px;">
            <div>
                ${cartItems.map(item => `
                    <div class="cart-item">
                        <div class="cart-item-image" style="display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.3);">
                            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                        </div>
                        <div class="cart-item-info">
                            <div class="cart-item-name">${item.product_name}</div>
                            <div class="cart-item-sku">${item.sku_code}</div>
                            <div class="cart-item-price">฿${item.final_price.toLocaleString()}</div>
                            <div class="cart-item-qty">
                                <button class="qty-btn" onclick="updateCartQty(${item.id}, ${item.quantity - 1})">-</button>
                                <span>${item.quantity}</span>
                                <button class="qty-btn" onclick="updateCartQty(${item.id}, ${item.quantity + 1})">+</button>
                                <button class="btn-icon delete" onclick="removeFromCart(${item.id})" style="margin-left: auto;">
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
            <div class="cart-summary">
                <h3 style="margin-bottom: 16px;">สรุปคำสั่งซื้อ</h3>
                <div class="cart-summary-row">
                    <span>รวมสินค้า</span>
                    <span>${cartItems.length} รายการ</span>
                </div>
                <div class="cart-summary-row">
                    <span>ยอดรวม</span>
                    <span class="cart-summary-total">฿${total.toLocaleString()}</span>
                </div>
                <button class="btn-primary" style="width: 100%; margin-top: 16px;" onclick="proceedToCheckout()">
                    ดำเนินการสั่งซื้อ
                </button>
            </div>
        </div>
    `;
}

async function updateCartQty(itemId, qty) {
    if (qty < 1) {
        removeFromCart(itemId);
        return;
    }
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart/items/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity: qty })
        });
        
        if (response.ok) {
            loadCart();
            loadCartBadge();
        }
    } catch (error) {
        console.error('Error updating cart:', error);
    }
}

async function removeFromCart(itemId) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart/items/${itemId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadCart();
            loadCartBadge();
        }
    } catch (error) {
        console.error('Error removing from cart:', error);
    }
}

function proceedToCheckout() {
    window.location.href = '/reseller/checkout';
}

async function loadCartBadge() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`);
        if (response.ok) {
            const data = await response.json();
            const count = (data.items || []).length;
            const badge = document.getElementById('cartBadge');
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'block';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading cart badge:', error);
    }
}

async function loadOrders() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/orders`);
        if (!response.ok) throw new Error('Failed to load orders');
        
        const data = await response.json();
        const orders = data.orders || [];
        renderOrders(orders);
    } catch (error) {
        console.error('Error loading orders:', error);
    }
}

function renderOrders(orders) {
    const container = document.getElementById('ordersList');
    
    if (!orders || orders.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 64px; height: 64px; margin-bottom: 16px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                <h3>ยังไม่มีคำสั่งซื้อ</h3>
                <p>เริ่มต้นสั่งซื้อสินค้าได้เลย</p>
            </div>
        `;
        return;
    }
    
    const statusLabels = {
        'pending_payment': 'รอชำระเงิน',
        'pending_verification': 'รอตรวจสอบ',
        'paid': 'ชำระแล้ว',
        'processing': 'กำลังจัดส่ง',
        'shipped': 'จัดส่งแล้ว',
        'completed': 'เสร็จสิ้น',
        'cancelled': 'ยกเลิก'
    };
    
    const statusClass = {
        'pending_payment': 'pending',
        'pending_verification': 'pending',
        'paid': 'paid',
        'processing': 'paid',
        'shipped': 'paid',
        'completed': 'paid',
        'cancelled': 'cancelled'
    };
    
    container.innerHTML = orders.map(order => `
        <div class="order-card">
            <div class="order-header">
                <span class="order-number">#${order.order_number}</span>
                <span class="order-status ${statusClass[order.status] || 'pending'}">${statusLabels[order.status] || order.status}</span>
            </div>
            <div style="display: flex; justify-content: space-between; color: rgba(255,255,255,0.6); font-size: 13px;">
                <span>${new Date(order.created_at).toLocaleDateString('th-TH')}</span>
                <span style="color: #22c55e; font-weight: 600;">฿${(order.final_amount || 0).toLocaleString()}</span>
            </div>
        </div>
    `).join('');
}

async function loadCustomers() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/customers`);
        if (!response.ok) throw new Error('Failed to load customers');
        
        const data = await response.json();
        customers = data.customers || [];
        renderCustomers(customers);
    } catch (error) {
        console.error('Error loading customers:', error);
    }
}

function renderCustomers(customersToRender) {
    const container = document.getElementById('customersGrid');
    
    if (!customersToRender || customersToRender.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle></svg>
                <h3>ยังไม่มีข้อมูลลูกค้า</h3>
                <p>คลิก "เพิ่มลูกค้า" เพื่อเริ่มต้น</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = customersToRender.map(customer => `
        <div class="customer-card">
            <div class="customer-header">
                <div class="customer-name">${customer.full_name}</div>
                <div class="customer-actions">
                    <button class="btn-icon" onclick="editCustomer(${customer.id})" title="แก้ไข">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    </button>
                    <button class="btn-icon delete" onclick="deleteCustomer(${customer.id}, '${customer.full_name}')" title="ลบ">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </div>
            </div>
            <div class="customer-info">
                ${customer.phone ? `<div class="info-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>${customer.phone}</div>` : ''}
                ${customer.email ? `<div class="info-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>${customer.email}</div>` : ''}
                ${customer.address || customer.province ? `<div class="info-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg><span>${[customer.address, customer.subdistrict, customer.district, customer.province, customer.postal_code].filter(Boolean).join(' ')}</span></div>` : ''}
            </div>
        </div>
    `).join('');
}

function searchCustomers() {
    const search = document.getElementById('customerSearch').value.toLowerCase();
    const filtered = customers.filter(c => 
        c.full_name.toLowerCase().includes(search) ||
        (c.phone && c.phone.includes(search)) ||
        (c.email && c.email.toLowerCase().includes(search))
    );
    renderCustomers(filtered);
}

function openAddCustomerModal() {
    document.getElementById('customerModalTitle').textContent = 'เพิ่มลูกค้าใหม่';
    document.getElementById('customerForm').reset();
    document.getElementById('customerId').value = '';
    document.getElementById('customerModal').classList.add('active');
}

function closeCustomerModal() {
    document.getElementById('customerModal').classList.remove('active');
}

async function editCustomer(id) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/customers/${id}`);
        if (!response.ok) throw new Error('Failed to load customer');
        
        const data = await response.json();
        const customer = data.customer;
        
        document.getElementById('customerModalTitle').textContent = 'แก้ไขข้อมูลลูกค้า';
        document.getElementById('customerId').value = customer.id;
        document.getElementById('customerName').value = customer.full_name || '';
        document.getElementById('customerPhone').value = customer.phone || '';
        document.getElementById('customerEmail').value = customer.email || '';
        document.getElementById('customerAddress').value = customer.address || '';
        document.getElementById('customerSubdistrict').value = customer.subdistrict || '';
        document.getElementById('customerDistrict').value = customer.district || '';
        document.getElementById('customerProvince').value = customer.province || '';
        document.getElementById('customerPostalCode').value = customer.postal_code || '';
        document.getElementById('customerNotes').value = customer.notes || '';
        
        document.getElementById('customerModal').classList.add('active');
    } catch (error) {
        console.error('Error loading customer:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
    }
}

async function handleSaveCustomer(event) {
    event.preventDefault();
    
    const customerId = document.getElementById('customerId').value;
    const customerData = {
        full_name: document.getElementById('customerName').value,
        phone: document.getElementById('customerPhone').value,
        email: document.getElementById('customerEmail').value,
        address: document.getElementById('customerAddress').value,
        subdistrict: document.getElementById('customerSubdistrict').value,
        district: document.getElementById('customerDistrict').value,
        province: document.getElementById('customerProvince').value,
        postal_code: document.getElementById('customerPostalCode').value,
        notes: document.getElementById('customerNotes').value
    };
    
    try {
        const url = customerId ? `${RESELLER_API_URL}/reseller/customers/${customerId}` : `${RESELLER_API_URL}/reseller/customers`;
        const method = customerId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(customerData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert(customerId ? 'อัปเดตข้อมูลสำเร็จ' : 'เพิ่มลูกค้าสำเร็จ', 'success');
            closeCustomerModal();
            loadCustomers();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving customer:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function deleteCustomer(id, name) {
    if (!confirm(`คุณต้องการลบลูกค้า "${name}" ใช่หรือไม่?`)) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/customers/${id}`, { method: 'DELETE' });
        const result = await response.json();
        
        if (response.ok) {
            showAlert('ลบลูกค้าสำเร็จ', 'success');
            loadCustomers();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting customer:', error);
        showAlert('เกิดข้อผิดพลาดในการลบ', 'error');
    }
}

async function loadProfile() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/profile`);
        if (!response.ok) throw new Error('Failed to load profile');
        
        const data = await response.json();
        const profile = data.profile;
        
        document.getElementById('profileName').textContent = profile.full_name;
        document.getElementById('profileUsername').textContent = profile.username;
        document.getElementById('profileAvatar').textContent = profile.full_name.charAt(0).toUpperCase();
        
        const tierIcons = { 'Bronze': '🥉', 'Silver': '🥈', 'Gold': '🥇', 'Platinum': '💎' };
        document.getElementById('profileTierIcon').textContent = tierIcons[profile.tier_name] || '🏷️';
        document.getElementById('profileTierName').textContent = profile.tier_name || '-';
        
        document.getElementById('brandName').value = profile.brand_name || '';
        document.getElementById('profilePhone').value = profile.phone || '';
        document.getElementById('profileEmail').value = profile.email || '';
        document.getElementById('profileAddress').value = profile.address || '';
        document.getElementById('profileSubdistrict').value = profile.subdistrict || '';
        document.getElementById('profileDistrict').value = profile.district || '';
        document.getElementById('profileProvince').value = profile.province || '';
        document.getElementById('profilePostalCode').value = profile.postal_code || '';
    } catch (error) {
        console.error('Error loading profile:', error);
    }
}

async function handleSaveProfile(event) {
    event.preventDefault();
    
    const profileData = {
        brand_name: document.getElementById('brandName').value,
        phone: document.getElementById('profilePhone').value,
        email: document.getElementById('profileEmail').value,
        address: document.getElementById('profileAddress').value,
        subdistrict: document.getElementById('profileSubdistrict').value,
        district: document.getElementById('profileDistrict').value,
        province: document.getElementById('profileProvince').value,
        postal_code: document.getElementById('profilePostalCode').value
    };
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/profile`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profileData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('บันทึกข้อมูลสำเร็จ', 'success');
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving profile:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function handleLogout() {
    try {
        await fetch(`${RESELLER_API_URL}/logout`, { method: 'POST' });
    } catch (e) {
        console.log('Logout request sent');
    }
    window.location.href = '/login';
}
