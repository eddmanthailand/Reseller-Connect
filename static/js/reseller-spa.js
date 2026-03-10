const RESELLER_API_URL = '/api';

function getTierSVG(tier, size = 22) {
    const configs = {
        'Bronze':   { fill: '#c07830', stroke: '#8b5520' },
        'Silver':   { fill: '#8fabbe', stroke: '#607d93' },
        'Gold':     { fill: '#e8a020', stroke: '#b07808' },
        'Platinum': { fill: '#18b8d0', stroke: '#0890aa' }
    };
    const c = configs[tier] || configs['Bronze'];
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${size}" height="${size}" style="display:inline-block;vertical-align:middle;flex-shrink:0"><path d="M12 2L20.66 7v10L12 22 3.34 17V7Z" fill="${c.fill}" stroke="${c.stroke}" stroke-width="1.5" stroke-linejoin="round"/><path d="M12 6L17.2 9v6L12 18 6.8 15V9Z" fill="rgba(255,255,255,0.2)" stroke="none"/></svg>`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function getTrackingUrl(provider, trackingNumber) {
    if (!provider || !trackingNumber) return null;
    const providerLower = provider.toLowerCase();
    const trackingUrls = {
        'thailand post': `https://track.thailandpost.co.th/?trackNumber=${trackingNumber}`,
        'ไปรษณีย์ไทย': `https://track.thailandpost.co.th/?trackNumber=${trackingNumber}`,
        'kerry express': `https://th.kerryexpress.com/th/track/?track=${trackingNumber}`,
        'kerry': `https://th.kerryexpress.com/th/track/?track=${trackingNumber}`,
        'flash express': `https://flashexpress.com/fle/tracking?se=${trackingNumber}`,
        'flash': `https://flashexpress.com/fle/tracking?se=${trackingNumber}`,
        'j&t express': `https://www.jtexpress.co.th/index/query/gzquery.html?billcode=${trackingNumber}`,
        'j&t': `https://www.jtexpress.co.th/index/query/gzquery.html?billcode=${trackingNumber}`,
        'shopee express': `https://spx.co.th/th/tracking?code=${trackingNumber}`,
        'spx': `https://spx.co.th/th/tracking?code=${trackingNumber}`,
        'best express': `https://www.best-inc.co.th/track?bills=${trackingNumber}`,
        'best': `https://www.best-inc.co.th/track?bills=${trackingNumber}`,
        'ninja van': `https://www.ninjavan.co/th-th/tracking?id=${trackingNumber}`,
        'ninjavan': `https://www.ninjavan.co/th-th/tracking?id=${trackingNumber}`,
        'dhl': `https://www.dhl.com/th-th/home/tracking.html?tracking-id=${trackingNumber}`
    };
    return trackingUrls[providerLower] || null;
}

let currentUser = null;
let customers = [];
let products = [];
let cartItems = [];
let allOrders = [];
let currentOrderFilter = 'all';

document.addEventListener('DOMContentLoaded', function() {
    init();
});

async function init() {
    try {
        await loadCurrentUser();
        handleStripeReturn();
        await loadThailandProvinces();
        setupNavigation();
        handleHashNavigation();
        window.addEventListener('hashchange', handleHashNavigation);
        
        loadDashboardData();
        loadCartBadge();
        loadResellerChatUnreadCount();
        
        // Start periodic unread check (every 30 seconds)
        setInterval(loadResellerChatUnreadCount, 30000);
    } catch (error) {
        console.error('Initialization error:', error);
        // Only redirect if truly unauthenticated (not on generic errors)
        if (error.message === 'Not authenticated' || error.status === 401) {
            window.location.href = '/login';
        }
    }
}

function handleHashNavigation() {
    const hash = window.location.hash.substring(1) || 'home';
    const validPages = ['home', 'catalog', 'cart', 'checkout', 'orders', 'customers', 'profile', 'mto-catalog', 'chat', 'promo-wallet'];
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

let previousPageBeforeChat = 'home';

function switchPage(pageName) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });

    document.querySelectorAll('.page-content').forEach(page => {
        page.classList.toggle('active', page.id === `page-${pageName}`);
    });

    // Sync Bottom Tab Bar
    document.querySelectorAll('.bottom-tab-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });

    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.remove('active');
        const overlay = document.querySelector('.sidebar-overlay');
        if (overlay) overlay.classList.remove('active');
        
        // Chat fullscreen mode on mobile
        if (pageName === 'chat') {
            // Store previous page for back navigation
            const currentHash = window.location.hash.substring(1);
            if (currentHash && currentHash !== 'chat') {
                previousPageBeforeChat = currentHash;
            }
            document.body.classList.add('chat-fullscreen-mode');
            setupChatFullscreenBackButton();
        } else {
            document.body.classList.remove('chat-fullscreen-mode');
        }
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
        case 'checkout':
            loadCheckout();
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
        case 'mto-catalog':
            loadMtoCatalog();
            break;
        case 'promo-wallet':
            loadPromoWallet();
            break;
        case 'chat':
            initResellerChat();
            loadResellerChatUnreadCount();
            break;
    }
}

function setupChatFullscreenBackButton() {
    const pageHeader = document.querySelector('#page-chat .page-header');
    if (!pageHeader) return;
    
    // Add back button if not exists
    let backBtn = pageHeader.querySelector('.chat-back-btn');
    if (!backBtn) {
        backBtn = document.createElement('button');
        backBtn.className = 'chat-back-btn';
        backBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>';
        backBtn.style.cssText = 'background: none; border: none; color: white; padding: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 50%;';
        backBtn.onclick = exitChatFullscreen;
        pageHeader.insertBefore(backBtn, pageHeader.firstChild);
    }
}

function exitChatFullscreen() {
    document.body.classList.remove('chat-fullscreen-mode');
    window.location.hash = previousPageBeforeChat || 'home';
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
    
    const displayName = currentUser.full_name || currentUser.username || 'สมาชิก';
    document.getElementById('userName').textContent = displayName;
    document.getElementById('userAvatar').textContent = displayName.charAt(0).toUpperCase();
    document.getElementById('welcomeText').textContent = `ยินดีต้อนรับ, ${displayName}`;
    
    const tierName = currentUser.reseller_tier || 'Bronze';
    
    document.getElementById('tierIcon').innerHTML = getTierSVG(tierName, 18);
    document.getElementById('userTier').textContent = tierName;
    
    ['catalog', 'profile'].forEach(prefix => {
        const iconEl = document.getElementById(`${prefix}TierIcon`);
        const nameEl = document.getElementById(`${prefix}TierName`);
        if (iconEl) iconEl.innerHTML = getTierSVG(tierName, 20);
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
            
            document.getElementById('statTotalSpent').textContent = formatCurrency(data.tier_progress?.total_purchases ?? data.all_time_stats?.total ?? 0);
            document.getElementById('statTotalOrders').textContent = `${data.all_time_stats?.orders || 0} คำสั่งซื้อ`;
            
            const pendingTotal = Object.values(data.pending_orders || {}).reduce((a, b) => a + b, 0);
            document.getElementById('statPendingOrders').textContent = pendingTotal;
            
            const pendingPayment = (data.pending_orders?.pending_payment || 0) + (data.pending_orders?.under_review || 0);
            document.getElementById('statPendingDetail').textContent = pendingPayment > 0 ? `รอชำระเงิน ${pendingPayment}` : 'ไม่มี';
            
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
    
    const tierDescriptions = { 
        'Bronze': 'ระดับเริ่มต้น', 
        'Silver': 'ระดับเงิน', 
        'Gold': 'ระดับทอง', 
        'Platinum': 'ระดับสูงสุด' 
    };
    
    const currentTier = tierProgress.current_tier || 'Bronze';
    document.getElementById('homeTierBadgeIcon').innerHTML = getTierSVG(currentTier, 48);
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
        'under_review': 'รอตรวจสอบ',
        'preparing': 'เตรียมสินค้า',
        'shipped': 'กำลังจัดส่ง',
        'delivered': 'ได้รับสินค้าแล้ว',
        'failed_delivery': 'จัดส่งไม่สำเร็จ',
        'cancelled': 'ยกเลิก'
    };
    
    const statusColors = {
        'pending_payment': '#f59e0b',
        'under_review': '#60a5fa',
        'preparing': '#a78bfa',
        'shipped': '#22d3ee',
        'delivered': '#4ade80',
        'failed_delivery': '#f87171',
        'cancelled': '#6b7280'
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

let activeStockFilter = 'all';

async function loadProducts() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/products`);
        if (!response.ok) throw new Error('Failed to load products');
        
        const data = await response.json();
        products = data.products || [];
        buildFilterDropdowns(products, data.categories || []);
        renderProducts(products);
    } catch (error) {
        console.error('Error loading products:', error);
    }
}

function buildFilterDropdowns(productList, categories) {
    const brandSel = document.getElementById('productBrandFilter');
    const catSel = document.getElementById('productCategoryFilter');
    if (!brandSel || !catSel) return;

    const brands = [...new Map(
        productList.filter(p => p.brand_name).map(p => [p.brand_name, p.brand_name])
    ).entries()].map(([k]) => k).sort();

    brandSel.innerHTML = '<option value="">แบรนด์ทั้งหมด</option>' +
        brands.map(b => `<option value="${b}">${b}</option>`).join('');

    catSel.innerHTML = '<option value="">หมวดหมู่ทั้งหมด</option>' +
        categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
}

function setStockFilter(btn) {
    document.querySelectorAll('.stock-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStockFilter = btn.dataset.stock;
    filterProducts();
}

function filterProducts() {
    const searchVal = (document.getElementById('productSearch')?.value || '').toLowerCase().trim();
    const brandVal = document.getElementById('productBrandFilter')?.value || '';
    const catVal = document.getElementById('productCategoryFilter')?.value || '';

    const filtered = products.filter(p => {
        if (searchVal) {
            const haystack = [
                p.name, p.parent_sku, p.brand_name,
                ...(p.category_names || [])
            ].filter(Boolean).join(' ').toLowerCase();
            if (!haystack.includes(searchVal)) return false;
        }
        if (brandVal && p.brand_name !== brandVal) return false;
        if (catVal && !(p.category_ids || []).includes(parseInt(catVal))) return false;
        if (activeStockFilter === 'in' && !(p.total_stock > 0)) return false;
        if (activeStockFilter === 'out' && p.total_stock > 0) return false;
        return true;
    });

    const countEl = document.getElementById('catalogResultCount');
    if (countEl) {
        const hasFilter = searchVal || brandVal || catVal || activeStockFilter !== 'all';
        countEl.textContent = hasFilter ? `พบ ${filtered.length} รายการ จาก ${products.length} รายการ` : '';
    }

    renderProducts(filtered);
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

async function viewProduct(productId) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/products/${productId}`);
        if (!response.ok) throw new Error('Failed to load product');
        
        const product = await response.json();
        openProductModal(product);
    } catch (error) {
        console.error('Error loading product:', error);
        showAlert('ไม่สามารถโหลดข้อมูลสินค้าได้', 'error');
    }
}

let currentProductSkus = [];
let selectedSkuId = null;
let currentProductCustomizations = [];

function openProductModal(product) {
    // Reset customizations
    selectedCustomizations = {};
    currentProductCustomizations = product.customizations || [];
    document.getElementById('productModalTitle').textContent = product.name;
    
    // Transform SKUs to include variant_values
    currentProductSkus = (product.skus || []).map(sku => {
        const variantValues = {};
        if (sku.options) {
            sku.options.forEach(opt => {
                variantValues[opt.option_name] = opt.option_value;
            });
        }
        return {
            ...sku,
            variant_values: variantValues,
            final_price: sku.discounted_price || sku.price
        };
    });
    
    // Find first SKU with stock > 0
    const firstAvailableSku = currentProductSkus.find(s => s.stock > 0);
    selectedSkuId = firstAvailableSku ? firstAvailableSku.id : (currentProductSkus.length > 0 ? currentProductSkus[0].id : null);
    
    const hasOptions = product.options && product.options.length > 0;
    
    // Build a map of option values with stock info
    const optionStockMap = {};
    currentProductSkus.forEach(sku => {
        Object.entries(sku.variant_values || {}).forEach(([optName, optVal]) => {
            const key = `${optName}:${optVal}`;
            if (!optionStockMap[key]) {
                optionStockMap[key] = { totalStock: 0 };
            }
            optionStockMap[key].totalStock += (sku.stock || 0);
        });
    });
    
    let optionsHtml = '';
    if (hasOptions) {
        optionsHtml = product.options.map(opt => {
            const values = opt.values || [];
            return `
            <div class="product-modal-options">
                <div class="product-modal-option-label">${opt.name}</div>
                <div class="product-modal-option-buttons">
                    ${values.map((val, idx) => {
                        const valStr = typeof val === 'object' ? val.value : val;
                        const stockKey = `${opt.name}:${valStr}`;
                        const stockInfo = optionStockMap[stockKey] || { totalStock: 0 };
                        const isOutOfStock = stockInfo.totalStock <= 0;
                        const isFirstAvailable = !isOutOfStock && idx === values.findIndex(v => {
                            const vs = typeof v === 'object' ? v.value : v;
                            const sk = `${opt.name}:${vs}`;
                            return (optionStockMap[sk]?.totalStock || 0) > 0;
                        });
                        return `
                        <button type="button" class="option-btn ${isFirstAvailable ? 'active' : ''} ${isOutOfStock ? 'out-of-stock' : ''}"
                                data-option="${opt.name}" data-value="${valStr}"
                                onclick="selectOption(this, '${opt.name}', '${valStr}')"
                                ${isOutOfStock ? 'disabled' : ''}>
                            <span class="option-btn-label">${valStr}</span>
                            ${isOutOfStock ? '<span class="option-sold-out-badge">หมด</span>' : ''}
                        </button>
                    `}).join('')}
                </div>
            </div>
        `}).join('');
    }
    
    const firstSku = currentProductSkus[0] || {};
    const price = firstSku.final_price || firstSku.discounted_price || firstSku.price || 0;
    const originalPrice = firstSku.price || 0;
    const discount = product.discount_percent || 0;
    const stock = firstSku.stock || 0;
    
    // Get main image from images array
    const mainImage = product.images && product.images.length > 0 ? product.images[0].image_url : null;
    
    // Build customizations HTML
    let customizationsHtml = '';
    if (product.customizations && product.customizations.length > 0) {
        customizationsHtml = product.customizations.map(c => `
            <div style="margin-bottom: 18px;">
                <div style="font-size: 13px; font-weight: 600; color: #1d1d1f; margin-bottom: 10px;">
                    ${c.name} ${c.is_required ? '<span style="color:#ef4444;">*</span>' : ''}
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                    ${(c.choices || []).map((ch) => {
                        const hasExtraPrice = ch.extra_price && ch.extra_price > 0;
                        return `
                        <button type="button" class="customization-btn"
                                data-customization="${c.id}" data-choice="${ch.id}"
                                onclick="toggleCustomization(this, ${c.id}, ${ch.id}, ${c.allow_multiple})"
                                style="padding: 9px 16px; border-radius: 20px; border: 1.5px solid #d2d2d7;
                                       background: #ffffff; color: #1d1d1f; cursor: pointer; font-size: 13px; font-weight: 500;
                                       transition: all 0.18s; display: flex; align-items: center; gap: 6px;">
                            <span class="customization-check" style="display: none; color: #15803d; font-weight: 700;">✓</span>
                            <span>${ch.label}</span>
                            ${hasExtraPrice ? `<span style="background: #dcfce7; color: #15803d;
                                               padding: 2px 7px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                                               +฿${ch.extra_price.toLocaleString()}</span>` : ''}
                        </button>
                    `}).join('')}
                </div>
            </div>
        `).join('');
    }
    
    // Build gallery thumbnails
    let modalGalleryHtml = '';
    if (product.images && product.images.length > 1) {
        modalGalleryHtml = `
            <div class="product-modal-gallery">
                ${product.images.map((img, idx) => `
                    <img src="${img.image_url}" alt="สินค้า ${idx+1}"
                         onclick="changeMainImage('${img.image_url}')"
                         class="gallery-thumb ${idx === 0 ? 'active' : ''}">
                `).join('')}
            </div>
        `;
    }

    // Size chart button
    let sizeChartHtml = '';
    if (product.size_chart_image_url) {
        sizeChartHtml = `
            <div style="margin-top: 4px;">
                <button onclick="showSizeChart('${product.size_chart_image_url}')"
                        style="background: transparent; border: 1.5px solid #d2d2d7; color: #1d1d1f;
                               padding: 8px 18px; border-radius: 20px; cursor: pointer; font-size: 12px; font-weight: 500;">
                    📏 ดูตารางไซส์
                </button>
            </div>
        `;
    }

    // Description
    const descHtml = product.description ? `
        <hr class="product-modal-divider">
        <div style="font-size: 13px; color: #86868b; line-height: 1.6; white-space: pre-line;">${product.description}</div>
    ` : '';

    document.getElementById('productModalContent').innerHTML = `
        <div class="product-modal-grid">
            <div class="product-modal-images">
                ${mainImage
                    ? `<img id="modalMainImage" src="${mainImage}" alt="${product.name}" class="product-modal-main-image">`
                    : `<div style="width: 100%; height: 240px; background: #f2f2f7; display: flex; align-items: center; justify-content: center; border-radius: 12px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#aeaeb2" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
                       </div>`
                }
                ${modalGalleryHtml}
            </div>
            <div class="product-modal-info">
                ${product.brand_name ? `<div class="product-modal-brand">${product.brand_name}</div>` : ''}
                <h3 class="product-modal-name">${product.name}</h3>
                <div class="product-modal-sku">${product.parent_sku || ''}</div>

                <hr class="product-modal-divider">

                <div class="product-modal-price-section">
                    ${discount > 0 ? `
                        <div class="product-modal-price-label">ราคาปกติ</div>
                        <div class="product-modal-original-price">฿${originalPrice.toLocaleString()}</div>
                        <div class="product-modal-discount-label">
                            ราคาสำหรับคุณ
                            <span class="product-modal-discount-badge">ประหยัด ${discount}%</span>
                        </div>
                    ` : `<div class="product-modal-price-label">ราคา</div>`}
                    <div id="modalPrice" class="product-modal-final-price">฿${price.toLocaleString()}</div>
                </div>

                ${optionsHtml ? `<hr class="product-modal-divider">${optionsHtml}` : ''}
                ${customizationsHtml ? `<hr class="product-modal-divider">${customizationsHtml}` : ''}
                ${sizeChartHtml}
                ${descHtml}

                <div id="modalStock" style="font-size: 12px; color: #aeaeb2; margin-top: 16px;">
                    ${stock > 0 ? `มีสินค้า ${stock} ชิ้น` : '<span style="color:#ef4444; font-weight: 500;">สินค้าหมด</span>'}
                </div>
            </div>
        </div>

        <div class="product-modal-sticky-footer">
            <div class="sticky-footer-price">
                <div class="label">ราคารวม</div>
                <div id="stickyPrice" class="price">฿${price.toLocaleString()}</div>
            </div>
            <div class="sticky-footer-qty">
                <button onclick="changeModalQty(-1)" aria-label="ลด">−</button>
                <input type="number" id="modalQty" value="1" min="1" readonly>
                <button onclick="changeModalQty(1)" aria-label="เพิ่ม">+</button>
            </div>
            <button onclick="addToCartFromModal()" class="sticky-footer-add-btn">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
                เพิ่มลงตะกร้า
            </button>
        </div>
    `;
    
    document.getElementById('productModal').classList.add('active');
    
    // Sync selectedSkuId with auto-selected options after modal is rendered
    setTimeout(() => {
        updateSelectedSku();
    }, 0);
}

function closeProductModal() {
    document.getElementById('productModal').classList.remove('active');
}

function selectOption(btn, optionName, value) {
    const parent = btn.parentElement;
    parent.querySelectorAll('.option-btn').forEach(b => {
        b.classList.remove('active');
    });
    btn.classList.add('active');
    updateSelectedSku();
}

function updateSelectedSku() {
    const selectedOptions = {};
    document.querySelectorAll('#productModalContent .option-btn.active').forEach(btn => {
        selectedOptions[btn.dataset.option] = btn.dataset.value;
    });
    
    const matchingSku = currentProductSkus.find(sku => {
        if (!sku.variant_values) return false;
        return Object.entries(selectedOptions).every(([key, val]) => 
            sku.variant_values[key] === val
        );
    });
    
    if (matchingSku) {
        selectedSkuId = matchingSku.id;
        const newPrice = `฿${(matchingSku.final_price || matchingSku.price).toLocaleString()}`;
        const priceEl = document.getElementById('modalPrice');
        if (priceEl) priceEl.textContent = newPrice;
        const stickyPriceEl = document.getElementById('stickyPrice');
        if (stickyPriceEl) stickyPriceEl.textContent = newPrice;
        const stockEl = document.getElementById('modalStock');
        if (stockEl) {
            const s = matchingSku.stock || 0;
            stockEl.innerHTML = s > 0
                ? `มีสินค้า ${s} ชิ้น`
                : '<span style="color:#ef4444; font-weight:500;">สินค้าหมด</span>';
        }
    }
}

function changeModalQty(delta) {
    const input = document.getElementById('modalQty');
    let val = parseInt(input.value) || 1;
    val = Math.max(1, val + delta);
    input.value = val;
}

function changeMainImage(imageUrl) {
    const mainImg = document.getElementById('modalMainImage');
    if (mainImg) {
        mainImg.src = imageUrl;
    }
    document.querySelectorAll('.gallery-thumb').forEach(thumb => {
        const isActive = thumb.src === imageUrl || thumb.src.endsWith(imageUrl);
        thumb.classList.toggle('active', isActive);
    });
}

function showSizeChart(imageUrl) {
    const overlay = document.createElement('div');
    overlay.id = 'sizeChartOverlay';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.9); display: flex; align-items: center; justify-content: center; z-index: 10000;';
    overlay.innerHTML = `
        <div style="position: relative; max-width: 90%; max-height: 90%;">
            <button onclick="closeSizeChart()" 
                    style="position: absolute; top: -40px; right: 0; background: var(--primary); border: none; 
                           color: white; width: 36px; height: 36px; border-radius: 50%; cursor: pointer; 
                           font-size: 20px; display: flex; align-items: center; justify-content: center;
                           box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                &times;
            </button>
            <img src="${imageUrl}" style="max-width: 100%; max-height: 80vh; object-fit: contain; border-radius: 12px; background: white;">
        </div>
    `;
    document.body.appendChild(overlay);
}

function closeSizeChart() {
    const overlay = document.getElementById('sizeChartOverlay');
    if (overlay) overlay.remove();
}

let selectedCustomizations = {};

function toggleCustomization(btn, customizationId, choiceId, allowMultiple) {
    if (!selectedCustomizations[customizationId]) {
        selectedCustomizations[customizationId] = [];
    }
    
    const btns = document.querySelectorAll(`.customization-btn[data-customization="${customizationId}"]`);
    
    if (allowMultiple) {
        const idx = selectedCustomizations[customizationId].indexOf(choiceId);
        if (idx > -1) {
            selectedCustomizations[customizationId].splice(idx, 1);
            btn.style.background = '#ffffff';
            btn.style.borderColor = '#d2d2d7';
            btn.style.color = '#1d1d1f';
            const check = btn.querySelector('.customization-check');
            if (check) check.style.display = 'none';
        } else {
            selectedCustomizations[customizationId].push(choiceId);
            btn.style.background = '#1d1d1f';
            btn.style.borderColor = '#1d1d1f';
            btn.style.color = '#ffffff';
            const check = btn.querySelector('.customization-check');
            if (check) { check.style.display = 'inline'; check.style.color = '#ffffff'; }
        }
    } else {
        btns.forEach(b => {
            b.style.background = '#ffffff';
            b.style.borderColor = '#d2d2d7';
            b.style.color = '#1d1d1f';
            const check = b.querySelector('.customization-check');
            if (check) check.style.display = 'none';
        });
        selectedCustomizations[customizationId] = [choiceId];
        btn.style.background = '#1d1d1f';
        btn.style.borderColor = '#1d1d1f';
        btn.style.color = '#ffffff';
        const check = btn.querySelector('.customization-check');
        if (check) { check.style.display = 'inline'; check.style.color = '#ffffff'; }
    }
}

async function addToCartFromModal() {
    if (!selectedSkuId) {
        showAlert('กรุณาเลือกตัวเลือกสินค้า', 'error');
        return;
    }
    
    // Check required customizations
    const missingRequired = currentProductCustomizations
        .filter(c => c.is_required)
        .filter(c => !selectedCustomizations[c.id] || selectedCustomizations[c.id].length === 0);
    
    if (missingRequired.length > 0) {
        showAlert(`กรุณาเลือก: ${missingRequired.map(c => c.name).join(', ')}`, 'error');
        return;
    }
    
    const quantity = parseInt(document.getElementById('modalQty').value) || 1;
    
    // Real-time stock check before adding to cart
    const selectedSku = currentProductSkus.find(s => s.id === selectedSkuId);
    if (selectedSku) {
        const availableStock = selectedSku.stock || 0;
        if (availableStock <= 0) {
            showAlert('สินค้าหมด ไม่สามารถเพิ่มลงตะกร้าได้', 'error');
            return;
        }
        if (quantity > availableStock) {
            showAlert(`สต็อกไม่พอ เหลือเพียง ${availableStock} ชิ้น`, 'error');
            return;
        }
    }
    
    // Build customization data
    const customizationData = Object.keys(selectedCustomizations).length > 0 
        ? selectedCustomizations 
        : null;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                sku_id: selectedSkuId, 
                quantity,
                customization_data: customizationData
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('เพิ่มสินค้าลงตะกร้าแล้ว', 'success');
            loadCartBadge();
            closeProductModal();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error adding to cart:', error);
        showAlert('เกิดข้อผิดพลาดในการเพิ่มสินค้า', 'error');
    }
}


async function loadCart() {
    const container = document.getElementById('cartContent');
    container.innerHTML = `
        <div style="text-align: center; padding: 40px;">
            <div style="width: 40px; height: 40px; border: 3px solid rgba(168,85,247,0.3); border-top-color: var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px;"></div>
            <p style="opacity: 0.6;">กำลังโหลดตะกร้า...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`);
        if (!response.ok) throw new Error('Failed to load cart');
        
        const data = await response.json();
        cartItems = data.items || [];
        renderCart();
    } catch (error) {
        console.error('Error loading cart:', error);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #f87171;">
                <p>เกิดข้อผิดพลาดในการโหลดตะกร้า</p>
                <button class="btn-secondary" style="margin-top: 12px;" onclick="loadCart()">ลองใหม่</button>
            </div>
        `;
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
    
    const cartItemsHtml = cartItems.map(item => {
        // SKU variant options
        const skuOptionsHtml = (item.sku_options && item.sku_options.length > 0) ?
            `<div class="cart-item-options">${item.sku_options.map(opt => 
                `<span class="sku-option-tag">${opt.option_name}: ${opt.option_value}</span>`
            ).join('')}</div>` : '';
        
        // Customizations (resolved names from API)
        let customizationsHtml = '';
        if (item.customizations && item.customizations.length > 0) {
            const custTags = item.customizations.map(c => 
                `<span class="customization-tag">${c.name}: ${c.value}</span>`
            ).join('');
            customizationsHtml = `<div class="cart-item-customizations">${custTags}</div>`;
        }
        
        const hasTierDiscount = item.tier_discount_percent > 0;
        const priceHtml = hasTierDiscount
            ? `<div class="cart-item-price">
                   <span style="text-decoration:line-through;opacity:0.45;font-size:12px;font-weight:400;">฿${item.unit_price.toLocaleString()}</span>
                   <span style="margin-left:6px;">฿${item.final_price.toLocaleString()}</span>
                   <span style="margin-left:6px;font-size:11px;background:rgba(74,222,128,0.18);color:#4ade80;border-radius:4px;padding:1px 6px;">-${item.tier_discount_percent}%</span>
               </div>`
            : `<div class="cart-item-price">฿${item.final_price.toLocaleString()}</div>`;

        return `
        <div class="cart-item">
            <img class="cart-item-image" src="${item.image_url || ''}" onerror="this.style.display='none'" alt="">
            <div class="cart-item-info">
                <div class="cart-item-name">${item.product_name}</div>
                <div class="cart-item-sku">${item.sku_code}</div>
                ${skuOptionsHtml}
                ${customizationsHtml}
                ${priceHtml}
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
    `}).join('');

    const retailTotal = cartItems.reduce((s, i) => s + (i.unit_price || 0) * (i.quantity || 0), 0);
    const tierSavings = retailTotal - total;
    const tierSavingsHtml = tierSavings > 0
        ? `<div class="cart-summary-row" style="color:#4ade80;font-size:13px;">
               <span>ส่วนลดระดับสมาชิก</span>
               <span>-฿${tierSavings.toLocaleString()}</span>
           </div>`
        : '';

    container.innerHTML = `
        <div class="cart-grid">
            <div class="cart-items-list">
                ${cartItemsHtml}
            </div>
            <div class="cart-summary">
                <h3 style="margin-bottom: 16px;">สรุปคำสั่งซื้อ</h3>
                <div class="cart-summary-row">
                    <span>รวมสินค้า</span>
                    <span>${cartItems.length} รายการ</span>
                </div>
                ${tierSavings > 0 ? `<div class="cart-summary-row" style="font-size:13px;opacity:0.6;">
                    <span>ราคาปกติ</span>
                    <span>฿${retailTotal.toLocaleString()}</span>
                </div>` : ''}
                ${tierSavingsHtml}
                <div class="cart-summary-row">
                    <span>ยอดรวม</span>
                    <span class="cart-summary-total">฿${total.toLocaleString()}</span>
                </div>
                <div style="font-size:11px;opacity:0.5;text-align:right;margin-top:2px;margin-bottom:8px;">* โปรโมชันเพิ่มเติมจะแสดงในหน้าชำระเงิน</div>
                <button class="btn-primary" style="width: 100%; margin-top: 8px;" onclick="proceedToCheckout()">
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
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity: qty })
        });
        
        if (response.ok) {
            loadCart();
            loadCartBadge();
        } else {
            const result = await response.json();
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error updating cart:', error);
        showAlert('เกิดข้อผิดพลาดในการอัพเดทตะกร้า', 'error');
    }
}

async function removeFromCart(itemId) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart/${itemId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showAlert('ลบสินค้าออกจากตะกร้าแล้ว', 'success');
            loadCart();
            loadCartBadge();
        } else {
            showAlert('เกิดข้อผิดพลาดในการลบสินค้า', 'error');
        }
    } catch (error) {
        console.error('Error removing from cart:', error);
        showAlert('เกิดข้อผิดพลาดในการลบสินค้า', 'error');
    }
}

function proceedToCheckout() {
    window.location.hash = 'checkout';
}

let checkoutData = { items: [], total: 0, retailTotal: 0, tierSavings: 0, customers: [], selfAddress: null };

async function loadCheckout() {
    _checkoutPayMethod = 'stripe';
    selectCheckoutPayment('stripe');
    try {
        const [cartRes, customersRes, profileRes] = await Promise.all([
            fetch(`${RESELLER_API_URL}/reseller/cart`),
            fetch(`${RESELLER_API_URL}/reseller/customers`),
            fetch(`${RESELLER_API_URL}/reseller/profile`)
        ]);
        
        if (!cartRes.ok) throw new Error('Failed to load cart');
        
        const cartData = await cartRes.json();
        checkoutData.items = cartData.items || [];
        checkoutData.total = cartData.total || 0;
        // Track retail total (before tier discount) for "best discount wins" logic
        checkoutData.retailTotal = checkoutData.items.reduce((s, i) => s + (i.unit_price || 0) * (i.quantity || 0), 0);
        checkoutData.tierSavings = checkoutData.retailTotal - checkoutData.total;
        _appliedCoupon = null;
        
        if (checkoutData.items.length === 0) {
            window.location.hash = 'cart';
            showAlert('ตะกร้าว่างเปล่า กรุณาเลือกสินค้า', 'error');
            return;
        }
        
        if (customersRes.ok) {
            const customersData = await customersRes.json();
            checkoutData.customers = customersData.customers || customersData || [];
        }
        
        if (profileRes.ok) {
            const profileData = await profileRes.json();
            checkoutData.selfAddress = profileData.profile || profileData;
        }
        
        renderCheckout();
    } catch (error) {
        console.error('Error loading checkout:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
    }
}

function renderCheckout() {
    document.getElementById('checkoutItemCount').textContent = checkoutData.items.length;
    
    const customerSelect = document.getElementById('checkoutCustomer');
    customerSelect.innerHTML = '<option value="">-- เลือกลูกค้า --</option>' +
        checkoutData.customers.map(c => 
            `<option value="${c.id}">${c.full_name} - ${c.phone || 'ไม่มีเบอร์'}</option>`
        ).join('');
    
    const selfCard = document.getElementById('selfAddressCard');
    const addr = checkoutData.selfAddress;
    const hasAddress = addr && (addr.address || addr.province);
    
    if (hasAddress) {
        const fullAddress = [addr.address, addr.subdistrict, addr.district, addr.province, addr.postal_code]
            .filter(Boolean).join(' ');
        selfCard.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 12px;">
                <div style="width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, var(--primary), #ec4899); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" style="width: 20px; height: 20px;"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
                </div>
                <div style="flex: 1;">
                    <div style="font-weight: 600; font-size: 15px; margin-bottom: 4px;">${addr.brand_name || addr.full_name || 'ที่อยู่ร้าน'}</div>
                    <div style="font-size: 13px; opacity: 0.8; margin-bottom: 2px;">📱 ${addr.phone || '-'}</div>
                    <div style="font-size: 13px; opacity: 0.7;">${fullAddress}</div>
                </div>
            </div>
        `;
    } else {
        selfCard.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <div style="width: 48px; height: 48px; border-radius: 12px; background: rgba(251,191,36,0.2); display: flex; align-items: center; justify-content: center; margin: 0 auto 12px;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" style="width: 24px; height: 24px;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                </div>
                <div style="font-weight: 500; margin-bottom: 4px; color: #ffffff;">ยังไม่ได้ตั้งค่าที่อยู่ร้าน</div>
                <div style="font-size: 13px; opacity: 0.7; margin-bottom: 16px;">กรุณาไปตั้งค่าที่อยู่ร้านก่อนใช้งาน</div>
                <button onclick="window.location.hash='profile'" class="btn-primary" style="padding: 10px 20px; font-size: 13px;">
                    🔧 ไปตั้งค่าโปรไฟล์
                </button>
            </div>
        `;
    }
    
    renderCheckoutItems();
    updateCheckoutSummary();
    validateCheckout();
}


function renderCheckoutItems() {
    const container = document.getElementById('checkoutItems');
    container.innerHTML = checkoutData.items.map(item => {
        // SKU variant options (e.g., สี: ขาว, ไซส์: 2XL)
        const skuOptionsHtml = (item.sku_options && item.sku_options.length > 0) ?
            item.sku_options.map(opt => `<span class="sku-option-tag">${opt.option_name}: ${opt.option_value}</span>`).join('') : '';
        
        // Customization data (resolved names from API)
        let customizationsHtml = '';
        if (item.customizations && item.customizations.length > 0) {
            customizationsHtml = item.customizations.map(c => 
                `<span class="customization-tag">${c.name}: ${c.value}</span>`
            ).join('');
        }
        
        return `
            <div class="checkout-item">
                <img class="checkout-item-image" src="${item.image_url || '/static/images/no-image.png'}" alt="${item.product_name}">
                <div class="checkout-item-info">
                    <div class="checkout-item-name">${item.product_name}</div>
                    <div class="checkout-item-sku">${item.sku_code || ''}</div>
                    ${skuOptionsHtml ? `<div class="checkout-item-options">${skuOptionsHtml}</div>` : ''}
                    ${customizationsHtml ? `<div class="checkout-item-customizations">${customizationsHtml}</div>` : ''}
                </div>
                <div class="checkout-item-price">
                    <div class="price">฿${(item.final_price * item.quantity).toLocaleString()}</div>
                    <div class="qty">x${item.quantity}</div>
                </div>
            </div>
        `;
    }).join('');
}

function updateCheckoutSummary() {
    document.getElementById('summarySubtotal').textContent = `฿${checkoutData.retailTotal > checkoutData.total ? checkoutData.retailTotal.toLocaleString() : checkoutData.total.toLocaleString()}`;
    calculateShippingCost();
}

async function calculateShippingCost() {
    const shippingEl = document.getElementById('summaryShipping');
    const totalEl = document.getElementById('summaryTotal');
    const promoRow = document.getElementById('shippingPromoRow');
    const promoName = document.getElementById('shippingPromoName');
    const promoSaved = document.getElementById('shippingPromoSaved');
    
    let totalWeight = 0;
    const brandIdSet = new Set();
    checkoutData.items.forEach(item => {
        const weight = item.weight || 100;
        totalWeight += weight * item.quantity;
        if (item.brand_id) brandIdSet.add(item.brand_id);
    });
    
    try {
        const res = await fetch(`${RESELLER_API_URL}/calculate-shipping`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                total_weight: totalWeight,
                order_total: checkoutData.total,
                brand_ids: Array.from(brandIdSet)
            })
        });
        
        if (!res.ok) throw new Error('Failed to calculate shipping');
        
        const data = await res.json();
        checkoutData.shippingCost = data.shipping_cost;
        checkoutData.originalShipping = data.original_shipping;
        checkoutData.promoApplied = data.promo_applied;
        
        if (data.shipping_cost === 0 && data.promo_applied) {
            shippingEl.innerHTML = '<span style="text-decoration: line-through; opacity: 0.5;">฿' + data.original_shipping.toLocaleString() + '</span> <span style="color: #22c55e;">ฟรี!</span>';
        } else {
            shippingEl.textContent = `฿${data.shipping_cost.toLocaleString()}`;
        }
        
        if (data.promo_applied && data.original_shipping > data.shipping_cost) {
            promoName.textContent = data.promo_applied;
            if (data.shipping_cost === 0) {
                // Free shipping — show label only, no amount (shipping row already shows ฟรี!)
                promoSaved.textContent = '✓ ฟรี!';
                promoSaved.style.fontWeight = '600';
            } else {
                // Partial discount — show amount saved
                promoSaved.textContent = `-฿${(data.original_shipping - data.shipping_cost).toLocaleString()}`;
                promoSaved.style.fontWeight = '600';
            }
            promoRow.style.display = 'flex';
        } else {
            promoRow.style.display = 'none';
        }
        
        const grandTotal = checkoutData.total + data.shipping_cost;
        totalEl.textContent = `฿${grandTotal.toLocaleString()}`;
        
        if (!_appliedCoupon) checkAutoPromotion();
        else loadPromptPayQR();
        
    } catch (error) {
        console.error('Error calculating shipping:', error);
        shippingEl.textContent = '฿0';
        totalEl.textContent = `฿${checkoutData.total.toLocaleString()}`;
        checkoutData.shippingCost = 0;
        if (!_appliedCoupon) checkAutoPromotion();
        else loadPromptPayQR();
    }
}

let _appliedCoupon = null;
let _autoPromoData = null;  // promo from checkAutoPromotion (no coupon)

function _buildDiscountPayload(couponCode = '') {
    const cartItems = checkoutData.items || [];
    return {
        coupon_code: couponCode,
        cart_total: checkoutData.total,
        retail_total: checkoutData.retailTotal || checkoutData.total,
        tier_savings: checkoutData.tierSavings || 0,
        brand_ids: [...new Set(cartItems.map(i => i.brand_id).filter(id => id))],
        category_ids: [...new Set(cartItems.map(i => i.category_id).filter(id => id))],
        product_ids: [...new Set(cartItems.map(i => i.product_id).filter(id => id))],
        cart_qty: cartItems.reduce((s, i) => s + (i.quantity || 0), 0)
    };
}

async function checkAutoPromotion() {
    try {
        const res = await fetch(`${RESELLER_API_URL}/reseller/cart/preview-discount`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_buildDiscountPayload(''))
        });
        if (!res.ok) return;
        const data = await res.json();
        _autoPromoData = data;
        if (!_appliedCoupon) updateSummaryWithDiscount(data);
    } catch (e) { /* non-critical, fail silently */ }
}

async function applyCouponCode() {
    const code = (document.getElementById('couponCodeInput').value || '').trim().toUpperCase();
    if (!code) { showCouponMsg('กรุณากรอกรหัสคูปอง', '#ef4444'); return; }
    showCouponMsg('กำลังตรวจสอบ...', 'rgba(255,255,255,0.5)');
    try {
        const res = await fetch(`${RESELLER_API_URL}/reseller/cart/preview-discount`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_buildDiscountPayload(code))
        });
        const data = await res.json();
        if (!res.ok) { showCouponMsg(data.error || 'คูปองไม่ถูกต้อง', '#ef4444'); return; }
        if (data.coupon_error) { showCouponMsg(data.coupon_error, '#ef4444'); return; }
        if (!data.coupon) { showCouponMsg('คูปองไม่ถูกต้องหรือหมดอายุแล้ว', '#ef4444'); return; }
        _appliedCoupon = { code, data };
        document.getElementById('removeCouponBtn').style.display = 'inline-block';
        document.getElementById('couponCodeInput').disabled = true;
        updateSummaryWithDiscount(data);
        showCouponMsg(`✓ ประหยัด ฿${Number(data.coupon.discount).toLocaleString()}`, '#4ade80');
    } catch (e) {
        showCouponMsg('เกิดข้อผิดพลาด กรุณาลองใหม่', '#ef4444');
    }
}

function removeCoupon() {
    _appliedCoupon = null;
    document.getElementById('couponCodeInput').value = '';
    document.getElementById('couponCodeInput').disabled = false;
    document.getElementById('removeCouponBtn').style.display = 'none';
    document.getElementById('couponDiscountRow').style.display = 'none';
    document.getElementById('couponMessage').textContent = '';
    // Restore auto-promo display (if any)
    if (_autoPromoData) {
        updateSummaryWithDiscount(_autoPromoData);
    } else {
        document.getElementById('autoPromoRow').style.display = 'none';
        const ship = checkoutData.shippingCost || 0;
        const sub = checkoutData.total || 0;
        checkoutData.finalTotal = sub + ship;
        document.getElementById('summaryTotal').textContent = `฿${checkoutData.finalTotal.toLocaleString()}`;
        loadPromptPayQR();
    }
}

function showCouponMsg(msg, color) {
    const el = document.getElementById('couponMessage');
    if (el) { el.textContent = msg; el.style.color = color; }
}

function updateSummaryWithDiscount(data) {
    const ship = checkoutData.shippingCost || 0;
    const autoRow = document.getElementById('autoPromoRow');
    const couponRow = document.getElementById('couponDiscountRow');
    const promo = data.promotion;
    const coupon = data.coupon;

    // Show promo row — when promo wins over tier, also update subtotal to show retail price
    const promoWinsNote = document.getElementById('promoWinsNote');
    const promoWinsNoteText = document.getElementById('promoWinsNoteText');
    if (promo && promo.discount > 0) {
        document.getElementById('autoPromoName').textContent = promo.name || 'โปรโมชัน';
        document.getElementById('autoPromoSaved').textContent = `-฿${Number(promo.discount).toLocaleString()}`;
        autoRow.style.display = 'flex';
        // Update subtotal to show retail price (promo is applied on retail)
        const tierSavings = checkoutData.tierSavings || 0;
        const promoDiscount = Number(promo.discount);
        if (data.retail_total && data.retail_total > checkoutData.total && tierSavings > 0) {
            document.getElementById('summarySubtotal').textContent = `฿${Number(data.retail_total).toLocaleString()}`;
            // Show explanation note: promo wins over tier
            if (promoWinsNote && promoWinsNoteText) {
                promoWinsNoteText.textContent =
                    `โปรโมชันนี้ให้ส่วนลด ฿${promoDiscount.toLocaleString()} ` +
                    `มากกว่าส่วนลดระดับสมาชิก ฿${tierSavings.toLocaleString()} ` +
                    `ระบบจึงเลือกส่วนลดที่ดีที่สุดให้คุณโดยอัตโนมัติ`;
                promoWinsNote.style.display = 'block';
            }
        } else {
            if (promoWinsNote) promoWinsNote.style.display = 'none';
        }
    } else {
        autoRow.style.display = 'none';
        if (promoWinsNote) promoWinsNote.style.display = 'none';
        // Restore subtotal to tier price
        document.getElementById('summarySubtotal').textContent = `฿${checkoutData.total.toLocaleString()}`;
    }

    if (coupon && coupon.discount > 0) {
        document.getElementById('couponDiscountName').textContent = `คูปอง ${coupon.code || ''}`;
        document.getElementById('couponDiscountSaved').textContent = `-฿${Number(coupon.discount).toLocaleString()}`;
        couponRow.style.display = 'flex';
    } else {
        couponRow.style.display = 'none';
    }
    const finalAmt = data.final_total !== undefined ? data.final_total : (checkoutData.total || 0);
    checkoutData.finalTotal = finalAmt + ship;
    document.getElementById('summaryTotal').textContent = `฿${checkoutData.finalTotal.toLocaleString()}`;
    loadPromptPayQR();
}

async function openCouponWalletPicker() {
    const modal = document.getElementById('couponWalletModal');
    const list = document.getElementById('couponWalletList');
    modal.style.display = 'block';
    list.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.5);padding:24px;">กำลังโหลด...</div>';
    try {
        const res = await fetch(`${RESELLER_API_URL}/reseller/coupons/wallet`);
        const coupons = await res.json();
        if (!Array.isArray(coupons) || !coupons.length) {
            list.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.5);padding:24px;">ไม่มีคูปองในกระเป๋า</div>';
            return;
        }
        list.innerHTML = coupons.map(c => {
            const expires = c.end_date ? new Date(c.end_date).toLocaleDateString('th-TH') : 'ไม่มีกำหนด';
            const isReady = c.status === 'ready';
            const statusLabel = c.status === 'used' ? 'ใช้แล้ว' : c.status === 'expired' ? 'หมดอายุ' : '';
            const desc = c.discount_type === 'percent' ? `ลด ${c.discount_value}%${c.max_discount > 0 ? ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})` : ''}` :
                         c.discount_type === 'fixed' ? `ลด ฿${Number(c.discount_value).toLocaleString()}` :
                         c.discount_type === 'free_shipping' ? 'ฟรีค่าจัดส่ง' : c.discount_type;
            return `<div style="background:rgba(255,255,255,0.07);border-radius:12px;padding:14px;${!isReady ? 'opacity:0.5;' : ''}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                        <div style="font-weight:700;color:#ffffff;font-size:${_ccFz(c.code)};letter-spacing:1px;word-break:break-all;">${c.code}</div>
                        <div style="color:white;font-size:13px;margin-top:2px;">${c.name || desc}</div>
                        <div style="color:rgba(255,255,255,0.6);font-size:12px;margin-top:2px;">${desc}${c.min_spend > 0 ? ` · ขั้นต่ำ ฿${Number(c.min_spend).toLocaleString()}` : ''}</div>
                        ${c.applies_to && c.applies_to !== 'all' ? `<div style="font-size:10px;color:rgba(255,255,255,0.4);margin-top:2px;">${c.applies_to === 'brand' ? '🏷️' : '📦'} ${(c.applies_to_names && c.applies_to_names.length) ? c.applies_to_names.slice(0,2).join(', ') + (c.applies_to_names.length > 2 ? ` +${c.applies_to_names.length-2}` : '') : 'เฉพาะบางรายการ'}</div>` : ''}
                        <div style="color:rgba(255,255,255,0.4);font-size:11px;margin-top:2px;">หมดอายุ: ${expires}</div>
                    </div>
                    ${isReady ? `<button onclick="selectWalletCoupon('${c.code}')" style="background:linear-gradient(135deg,#a855f7,#ec4899);border:none;color:white;padding:8px 14px;border-radius:8px;font-size:13px;cursor:pointer;white-space:nowrap;">เลือก</button>` : `<span style="color:#ef4444;font-size:12px;">${statusLabel}</span>`}
                </div>
            </div>`;
        }).join('');
    } catch (e) {
        list.innerHTML = '<div style="text-align:center;color:#ef4444;padding:24px;">โหลดไม่สำเร็จ</div>';
    }
}

async function selectWalletCoupon(code) {
    document.getElementById('couponWalletModal').style.display = 'none';
    document.getElementById('couponCodeInput').value = code;
    await applyCouponCode();
}

async function loadPromoWallet() {
    const autoList = document.getElementById('promoWalletAutoList');
    const couponList = document.getElementById('promoWalletCouponList');
    if (!autoList || !couponList) return;

    autoList.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:20px 0;">กำลังโหลด...</div>';
    couponList.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:20px 0;">กำลังโหลด...</div>';

    const [promos, coupons] = await Promise.all([
        fetch(`${RESELLER_API_URL}/reseller/promotions/active`).then(r => r.json()).catch(() => []),
        fetch(`${RESELLER_API_URL}/reseller/coupons/wallet`).then(r => r.json()).catch(() => [])
    ]);

    // Render auto-promotions
    if (!Array.isArray(promos) || !promos.length) {
        autoList.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.35);padding:20px 0;font-size:13px;">ยังไม่มีโปรโมชันที่ใช้ได้ในขณะนี้</div>';
    } else {
        autoList.innerHTML = promos.map(p => {
            const condParts = [];
            if (p.condition_min_spend > 0) condParts.push(`ซื้อครบ ฿${Number(p.condition_min_spend).toLocaleString()}`);
            if (p.condition_min_qty > 0) condParts.push(`จำนวน ${p.condition_min_qty} ชิ้นขึ้นไป`);
            const condText = condParts.join(' & ') || 'ทุกออเดอร์';
            const rewardText = p.reward_type === 'discount_percent' ? `ลด ${p.reward_value}%`
                : p.reward_type === 'discount_fixed' ? `ลด ฿${Number(p.reward_value).toLocaleString()}`
                : p.reward_type === 'free_item' ? `ของแถม ${p.reward_qty || 1} ชิ้น` : '';
            const stackText = p.is_stackable ? '<span style="background:rgba(168,85,247,0.2);color:#c084fc;padding:2px 8px;border-radius:10px;font-size:11px;">+ใช้กับคูปองได้</span>' : '';
            const dateText = p.end_date ? `หมดอายุ ${new Date(p.end_date).toLocaleDateString('th-TH')}` : '';
            return `
            <div style="background:rgba(255,255,255,0.06);border:1px solid rgba(168,85,247,0.2);border-radius:16px;padding:16px 18px;display:flex;align-items:center;gap:14px;">
                <div style="width:48px;height:48px;background:linear-gradient(135deg,#7c3aed,#a855f7);border-radius:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                </div>
                <div style="flex:1;min-width:0;">
                    <div style="font-weight:700;color:white;font-size:14px;margin-bottom:4px;">${p.name}</div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                        <span style="background:rgba(59,130,246,0.15);color:#93c5fd;padding:2px 8px;border-radius:10px;font-size:11px;border:1px solid rgba(59,130,246,0.2);">${condText}</span>
                        <span style="background:rgba(34,197,94,0.15);color:#86efac;padding:2px 8px;border-radius:10px;font-size:11px;border:1px solid rgba(34,197,94,0.2);">${rewardText}</span>
                        ${stackText}
                    </div>
                    ${dateText ? `<div style="font-size:11px;color:rgba(255,255,255,0.35);margin-top:4px;">${dateText}</div>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    // Render coupon wallet as ticket cards
    const readyCoupons = Array.isArray(coupons) ? coupons.filter(c => c.status === 'ready') : [];
    const usedCoupons = Array.isArray(coupons) ? coupons.filter(c => c.status === 'used') : [];
    const expiredCoupons = Array.isArray(coupons) ? coupons.filter(c => c.status !== 'ready' && c.status !== 'used') : [];

    // Update badge
    const badge = document.getElementById('bottomPromoBadge');
    if (badge) {
        if (readyCoupons.length > 0) { badge.textContent = readyCoupons.length; badge.style.display = ''; }
        else { badge.style.display = 'none'; }
    }

    const typeColors = { percent: ['#7c3aed','#a78bfa'], fixed: ['#0e7490','#67e8f9'], free_shipping: ['#065f46','#6ee7b7'] };
    const typeLabels = { percent: 'ลด %', fixed: 'ลดคงที่', free_shipping: 'ส่งฟรี' };
    const fmtWalletDate = d => d ? new Date(d).toLocaleDateString('th-TH',{day:'numeric',month:'short',year:'2-digit'}) : '';

    const renderCouponTicket = (c, isReady) => {
        const [bg1, bg2] = typeColors[c.discount_type] || ['#4c1d95','#a78bfa'];
        const typeLabel = typeLabels[c.discount_type] || c.discount_type;
        const desc = c.discount_type === 'percent' ? `ลด ${c.discount_value}%${c.max_discount > 0 ? ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})` : ''}`
            : c.discount_type === 'fixed' ? `ลด ฿${Number(c.discount_value).toLocaleString()}`
            : 'ฟรีค่าจัดส่ง';
        const expires = c.end_date ? new Date(c.end_date).toLocaleDateString('th-TH') : 'ไม่มีกำหนด';
        const statusLabel = isReady ? 'พร้อมใช้' : c.status === 'used' ? 'ใช้แล้ว' : 'หมดอายุ';
        const statusColor = isReady ? '#4ade80' : '#9ca3af';
        const useBtn = isReady ? `<button onclick="usePromoWalletCoupon('${c.code}')" style="background:linear-gradient(135deg,#a855f7,#ec4899);border:none;color:white;padding:6px 12px;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;">ใช้เลย</button>` : '';
        return `
        <div style="display:flex;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,${isReady ? '0.12' : '0.06'});${!isReady ? 'opacity:0.55;' : ''}min-height:88px;">
            <div style="width:100px;flex-shrink:0;background:linear-gradient(135deg,${bg1},${bg2});display:flex;flex-direction:column;align-items:center;justify-content:center;padding:12px 8px;">
                <div style="font-family:'Courier New',monospace;font-size:${_ccFz(c.code,true)};font-weight:800;letter-spacing:0.5px;color:white;text-align:center;word-break:break-all;line-height:1.3;">${c.code}</div>
                <div style="font-size:10px;color:rgba(255,255,255,0.7);margin-top:3px;text-align:center;">${typeLabel}</div>
            </div>
            <div style="flex:1;background:rgba(255,255,255,0.06);padding:12px 14px;display:flex;flex-direction:column;justify-content:space-between;min-width:0;">
                <div>
                    <div style="font-weight:700;color:white;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${c.name || desc}</div>
                    <div style="font-size:12px;color:rgba(255,255,255,0.55);margin-top:2px;">${desc}${c.min_spend > 0 ? ' · ขั้นต่ำ ฿'+Number(c.min_spend).toLocaleString() : ''}</div>
                    ${c.applies_to && c.applies_to !== 'all' ? `<div style="font-size:10px;color:rgba(255,255,255,0.4);margin-top:3px;">${c.applies_to === 'brand' ? '🏷️' : '📦'} ${(c.applies_to_names && c.applies_to_names.length) ? c.applies_to_names.slice(0,2).join(', ') + (c.applies_to_names.length > 2 ? ` +${c.applies_to_names.length-2}` : '') : 'เฉพาะบางรายการ'}</div>` : ''}
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;gap:8px;">
                    <div>
                        <div style="font-size:11px;color:rgba(255,255,255,0.35);">หมดอายุ ${expires}</div>
                        <div style="font-size:11px;color:${statusColor};font-weight:600;">${statusLabel}</div>
                    </div>
                    ${useBtn}
                </div>
            </div>
        </div>`;
    };

    // Active coupons
    if (!readyCoupons.length && !usedCoupons.length && !expiredCoupons.length) {
        couponList.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.35);padding:20px 0;font-size:13px;">ยังไม่มีคูปอง</div>';
        return;
    }

    let html = '';

    if (readyCoupons.length) {
        html += readyCoupons.map(c => renderCouponTicket(c, true)).join('');
    } else {
        html += '<div style="text-align:center;color:rgba(255,255,255,0.3);padding:16px 0;font-size:13px;">ไม่มีคูปองที่พร้อมใช้งาน</div>';
    }

    // History section
    if (usedCoupons.length || expiredCoupons.length) {
        html += `<div style="margin-top:20px;margin-bottom:12px;">
            <div style="display:flex;align-items:center;gap:10px;">
                <div style="flex:1;height:1px;background:rgba(255,255,255,0.1);"></div>
                <span style="font-size:12px;color:rgba(255,255,255,0.35);font-weight:600;white-space:nowrap;">📋 ประวัติการใช้คูปอง</span>
                <div style="flex:1;height:1px;background:rgba(255,255,255,0.1);"></div>
            </div>
        </div>`;
        // Used coupons with detail
        usedCoupons.forEach(c => {
            const desc = c.discount_type === 'percent' ? `ลด ${c.discount_value}%${c.max_discount > 0 ? ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})` : ''}`
                : c.discount_type === 'fixed' ? `ลด ฿${Number(c.discount_value).toLocaleString()}`
                : 'ฟรีค่าจัดส่ง';
            const usedDate = c.used_at ? fmtWalletDate(c.used_at) : '';
            const orderNum = c.used_in_order_number ? `#${c.used_in_order_number}` : '';
            html += `
            <div style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:14px;opacity:0.7;">
                <div style="width:36px;height:36px;background:rgba(74,222,128,0.15);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:16px;">✅</div>
                <div style="flex:1;min-width:0;">
                    <div style="font-family:'Courier New',monospace;font-size:12px;font-weight:800;color:rgba(255,255,255,0.7);letter-spacing:1px;">${escapeHtmlChat(c.code)}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:1px;">${escapeHtmlChat(c.name || desc)}</div>
                </div>
                <div style="text-align:right;flex-shrink:0;">
                    <div style="font-size:11px;color:#4ade80;font-weight:600;">ใช้แล้ว</div>
                    ${usedDate ? `<div style="font-size:10px;color:rgba(255,255,255,0.35);margin-top:1px;">${usedDate}</div>` : ''}
                    ${orderNum ? `<div style="font-size:10px;color:rgba(255,255,255,0.3);">ออเดอร์ ${orderNum}</div>` : ''}
                </div>
            </div>`;
        });
        // Expired coupons
        expiredCoupons.forEach(c => html += renderCouponTicket(c, false));
    }

    couponList.innerHTML = html;
}

function usePromoWalletCoupon(code) {
    window.location.hash = 'cart';
    setTimeout(() => {
        const input = document.getElementById('couponCodeInput');
        if (input) { input.value = code; applyCouponCode(); }
    }, 400);
}

async function loadProfileCouponWallet() {
    const container = document.getElementById('profileCouponWallet');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:16px 0;">กำลังโหลด...</div>';
    try {
        const res = await fetch(`${RESELLER_API_URL}/reseller/coupons/wallet`);
        const coupons = await res.json();
        if (!Array.isArray(coupons) || !coupons.length) {
            container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:16px 0;">ยังไม่มีคูปอง</div>';
            return;
        }
        container.innerHTML = coupons.map(c => {
            const expires = c.end_date ? new Date(c.end_date).toLocaleDateString('th-TH') : 'ไม่มีกำหนด';
            const isReady = c.status === 'ready';
            const statusColor = isReady ? '#4ade80' : '#ef4444';
            const statusLabel = c.status === 'ready' ? 'พร้อมใช้' : c.status === 'used' ? `ใช้แล้ว${c.used_in_order_number ? ' ('+c.used_in_order_number+')' : ''}` : 'หมดอายุ';
            const desc = c.discount_type === 'percent' ? `ลด ${c.discount_value}%${c.max_discount > 0 ? ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})` : ''}` :
                         c.discount_type === 'fixed' ? `ลด ฿${Number(c.discount_value).toLocaleString()}` :
                         c.discount_type === 'free_shipping' ? 'ฟรีค่าจัดส่ง' : c.discount_type;
            return `<div style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:14px;${!isReady ? 'opacity:0.55;' : ''}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:700;color:#ffffff;font-size:${_ccFz(c.code)};letter-spacing:1px;word-break:break-all;">${c.code}</div>
                        <div style="color:white;font-size:13px;margin-top:3px;">${c.name || desc}</div>
                        <div style="color:rgba(255,255,255,0.55);font-size:12px;margin-top:2px;">${desc}${c.min_spend > 0 ? ` · ขั้นต่ำ ฿${Number(c.min_spend).toLocaleString()}` : ''}</div>
                        ${c.applies_to && c.applies_to !== 'all' ? `<div style="font-size:10px;color:rgba(255,255,255,0.4);margin-top:2px;">${c.applies_to === 'brand' ? '🏷️' : '📦'} ${(c.applies_to_names && c.applies_to_names.length) ? c.applies_to_names.slice(0,2).join(', ') + (c.applies_to_names.length > 2 ? ` +${c.applies_to_names.length-2}` : '') : 'เฉพาะบางรายการ'}</div>` : ''}
                        <div style="color:rgba(255,255,255,0.35);font-size:11px;margin-top:2px;">หมดอายุ: ${expires}</div>
                    </div>
                    <span style="font-size:11px;font-weight:600;color:${statusColor};white-space:nowrap;">${statusLabel}</span>
                </div>
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<div style="text-align:center;color:#ef4444;padding:16px 0;">โหลดไม่สำเร็จ</div>';
    }
}

async function loadPromptPayQR() {
    const loadingDiv = document.getElementById('promptpayQRLoading');
    const contentDiv = document.getElementById('promptpayQRContent');
    const errorDiv = document.getElementById('promptpayQRError');
    
    if (!loadingDiv) return;
    
    loadingDiv.style.display = 'block';
    contentDiv.style.display = 'none';
    errorDiv.style.display = 'none';
    
    try {
        const shippingCost = checkoutData.shippingCost || 0;
        const amount = checkoutData.finalTotal || ((checkoutData.total || 0) + shippingCost);
        const res = await fetch(`${RESELLER_API_URL}/promptpay-qr?amount=${amount}`);
        
        if (!res.ok) {
            throw new Error('Failed to generate QR');
        }
        
        const data = await res.json();
        
        document.getElementById('promptpayQRImage').src = data.qr_image;
        document.getElementById('promptpayAccountName').textContent = data.account_name || 'PromptPay';
        document.getElementById('promptpayAmount').textContent = `฿${amount.toLocaleString()}`;
        
        loadingDiv.style.display = 'none';
        contentDiv.style.display = 'block';
    } catch (error) {
        console.error('Error loading PromptPay QR:', error);
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'block';
    }
}

function downloadQRCode() {
    const img = document.getElementById('promptpayQRImage');
    const amountEl = document.getElementById('promptpayAmount');
    if (!img || !img.src) return;

    const amountText = amountEl ? amountEl.textContent.trim() : '';

    const canvas = document.createElement('canvas');
    const padding = 24;
    const headerH = 44;
    const footerH = amountText ? 48 : 0;
    const qrSize = 280;

    canvas.width = qrSize + padding * 2;
    canvas.height = headerH + qrSize + footerH + padding * 2;

    const ctx = canvas.getContext('2d');

    // White background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Header: "EKG-Shop"
    ctx.fillStyle = '#7c3aed';
    ctx.font = 'bold 22px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('EKG-Shop', canvas.width / 2, padding + 28);

    // Draw QR image
    const qrY = padding + headerH;
    ctx.drawImage(img, padding, qrY, qrSize, qrSize);

    // Footer: amount
    if (amountText) {
        ctx.fillStyle = '#16a34a';
        ctx.font = 'bold 20px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`ยอดชำระ ${amountText}`, canvas.width / 2, qrY + qrSize + 34);
    }

    // Download as PNG via Blob
    canvas.toBlob(blob => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = 'promptpay-qr.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    }, 'image/png');
}

function toggleShippingType() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked').value;
    document.getElementById('customerShippingSection').style.display = shippingType === 'customer' ? 'block' : 'none';
    document.getElementById('selfShippingSection').style.display = shippingType === 'self' ? 'block' : 'none';
    document.getElementById('selectedCustomerInfo').style.display = 'none';
    document.getElementById('checkoutCustomer').value = '';
    validateCheckout();
}

function selectCheckoutCustomer() {
    const customerId = document.getElementById('checkoutCustomer').value;
    const infoDiv = document.getElementById('selectedCustomerInfo');
    
    if (!customerId) {
        infoDiv.style.display = 'none';
        validateCheckout();
        return;
    }
    
    const customer = checkoutData.customers.find(c => c.id == customerId);
    if (customer) {
        const fullAddress = [customer.address, customer.subdistrict, customer.district, customer.province, customer.postal_code]
            .filter(Boolean).join(' ');
        infoDiv.innerHTML = `
            <div class="address-name">${customer.full_name}</div>
            <div class="address-phone">${customer.phone || '-'}</div>
            <div class="address-detail">${fullAddress || 'ไม่มีที่อยู่'}</div>
        `;
        infoDiv.style.display = 'block';
    }
    validateCheckout();
}

function openAddCustomerFromCheckout() {
    openAddCustomerModal();
}

let customerSearchTimeout = null;
let selectedPaymentSlip = null;

function searchCustomersForCheckout(keyword) {
    clearTimeout(customerSearchTimeout);
    const resultsDiv = document.getElementById('customerSearchResults');
    
    if (!keyword || keyword.length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }
    
    customerSearchTimeout = setTimeout(() => {
        const filtered = checkoutData.customers.filter(c => 
            (c.full_name && c.full_name.toLowerCase().includes(keyword.toLowerCase())) ||
            (c.phone && c.phone.includes(keyword))
        );
        
        if (filtered.length === 0) {
            resultsDiv.innerHTML = `
                <div style="padding: 24px; text-align: center;">
                    <div style="width: 40px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; margin: 0 auto 12px;">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
                    </div>
                    <div style="opacity: 0.6; font-size: 13px;">ไม่พบลูกค้าที่ตรงกับ "${escapeHtml(keyword)}"</div>
                </div>
            `;
        } else {
            resultsDiv.innerHTML = filtered.slice(0, 10).map(c => {
                const shortAddress = [c.district, c.province].filter(Boolean).join(', ') || 'ไม่มีที่อยู่';
                return `
                <div onclick="selectCustomerFromSearch(${c.id})" 
                     style="padding: 14px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.08); transition: all 0.2s; display: flex; align-items: center; gap: 12px;" 
                     onmouseover="this.style.background='rgba(168,85,247,0.15)'" 
                     onmouseout="this.style.background='transparent'">
                    <div style="width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, rgba(168,85,247,0.3), rgba(236,72,153,0.3)); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" style="width: 18px; height: 18px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(c.full_name)}</div>
                        <div style="font-size: 12px; opacity: 0.7; display: flex; gap: 8px; flex-wrap: wrap;">
                            <span>📱 ${c.phone || '-'}</span>
                            <span>📍 ${shortAddress}</span>
                        </div>
                    </div>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px; opacity: 0.4; flex-shrink: 0;"><polyline points="9 18 15 12 9 6"></polyline></svg>
                </div>
            `}).join('');
        }
        resultsDiv.style.display = 'block';
    }, 200);
}

function showAllCustomers() {
    const resultsDiv = document.getElementById('customerSearchResults');
    const customers = checkoutData.customers || [];
    
    if (customers.length === 0) {
        resultsDiv.innerHTML = `
            <div style="padding: 24px; text-align: center;">
                <div style="width: 40px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; margin: 0 auto 12px;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px; opacity: 0.5;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle></svg>
                </div>
                <div style="opacity: 0.6; font-size: 13px;">ยังไม่มีลูกค้าในระบบ</div>
                <button type="button" class="btn-primary" onclick="openAddCustomerFromCheckout(); document.getElementById('customerSearchResults').style.display='none';" style="margin-top: 12px; padding: 8px 16px; font-size: 12px;">+ เพิ่มลูกค้าใหม่</button>
            </div>
        `;
    } else {
        resultsDiv.innerHTML = `
            <div style="padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 12px; opacity: 0.6;">
                รายชื่อลูกค้าทั้งหมด (${customers.length} คน)
            </div>
        ` + customers.map(c => {
            const shortAddress = [c.district, c.province].filter(Boolean).join(', ') || 'ไม่มีที่อยู่';
            return `
            <div onclick="selectCustomerFromSearch(${c.id})" 
                 style="padding: 14px 16px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.08); transition: all 0.2s; display: flex; align-items: center; gap: 12px;" 
                 onmouseover="this.style.background='rgba(168,85,247,0.15)'" 
                 onmouseout="this.style.background='transparent'">
                <div style="width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, rgba(168,85,247,0.3), rgba(236,72,153,0.3)); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" style="width: 18px; height: 18px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                </div>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; font-size: 14px; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(c.full_name)}</div>
                    <div style="font-size: 12px; opacity: 0.7; display: flex; gap: 8px; flex-wrap: wrap;">
                        <span>📱 ${c.phone || '-'}</span>
                        <span>📍 ${shortAddress}</span>
                    </div>
                </div>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px; opacity: 0.4; flex-shrink: 0;"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </div>
        `}).join('');
    }
    resultsDiv.style.display = 'block';
}

function selectCustomerFromSearch(customerId) {
    document.getElementById('customerSearchResults').style.display = 'none';
    
    const customerSelect = document.getElementById('checkoutCustomer');
    if (!customerSelect.querySelector(`option[value="${customerId}"]`)) {
        const customer = checkoutData.customers.find(c => c.id == customerId);
        if (customer) {
            const option = document.createElement('option');
            option.value = customer.id;
            option.textContent = `${customer.full_name} - ${customer.phone || 'ไม่มีเบอร์'}`;
            customerSelect.appendChild(option);
        }
    }
    customerSelect.value = customerId;
    
    const customer = checkoutData.customers.find(c => c.id == customerId);
    if (customer) {
        document.getElementById('customerSearchInput').value = customer.full_name;
    }
    
    selectCheckoutCustomer();
}

function clearSelectedCustomer() {
    document.getElementById('checkoutCustomer').value = '';
    document.getElementById('customerSearchInput').value = '';
    document.getElementById('selectedCustomerInfo').style.display = 'none';
    validateCheckout();
}

function previewPaymentSlip(input) {
    const file = input.files[0];
    if (!file) return;
    
    selectedPaymentSlip = file;
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('slipPreviewArea').innerHTML = `
            <img src="${e.target.result}" alt="Payment Slip" style="max-width: 100%; max-height: 200px; border-radius: 8px; margin-bottom: 8px;">
            <p style="font-size: 12px; opacity: 0.7;">${escapeHtml(file.name)}</p>
            <button type="button" onclick="removePaymentSlip()" style="padding: 6px 12px; background: #ef4444; color: white; border: none; border-radius: 6px; font-size: 11px; cursor: pointer; margin-top: 8px;">ลบสลิป</button>
        `;
    };
    reader.readAsDataURL(file);
    validateCheckout();
}

function removePaymentSlip() {
    selectedPaymentSlip = null;
    document.getElementById('paymentSlipInput').value = '';
    document.getElementById('slipPreviewArea').innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="width: 40px; height: 40px; opacity: 0.5; margin-bottom: 8px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
        <p style="opacity: 0.6; font-size: 13px;">คลิกเพื่ออัปโหลดสลิป หรือลากไฟล์มาวาง</p>
    `;
    validateCheckout();
}

function validateCheckout() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked')?.value;
    const btn = document.getElementById('btnPlaceOrder');
    if (!btn) return;
    
    let isValid = false;
    let reason = '';
    
    if (shippingType === 'customer') {
        const customerId = document.getElementById('checkoutCustomer').value;
        isValid = !!customerId;
        if (!isValid) reason = 'กรุณาเลือกลูกค้าที่จะจัดส่ง';
    } else if (shippingType === 'self') {
        isValid = checkoutData.selfAddress && 
            (checkoutData.selfAddress.address || checkoutData.selfAddress.province);
        if (!isValid) reason = 'กรุณาตั้งค่าที่อยู่ร้านก่อน';
    }

    let helper = document.getElementById('checkoutValidationHelper');
    if (!helper) {
        helper = document.createElement('div');
        helper.id = 'checkoutValidationHelper';
        helper.style.cssText = 'font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 8px; text-align: center;';
        btn.parentNode.insertBefore(helper, btn.nextSibling);
    }

    if (!isValid) {
        btn.disabled = true;
        const btnText = document.getElementById('btnPlaceOrderText');
        if (btnText) btnText.textContent = 'กรุณากรอกข้อมูลให้ครบ';
        helper.textContent = reason;
        helper.style.display = 'block';
    } else {
        helper.textContent = '';
        helper.style.display = 'none';
        btn.disabled = false;
        const btnText = document.getElementById('btnPlaceOrderText');
        if (btnText) btnText.textContent = 'ยืนยันและชำระเงิน';
    }
}

async function placeOrder() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked').value;
    const paymentMethod = 'promptpay';
    const notes = document.getElementById('orderNotes').value;
    
    // Validation with clear error messages
    const missingFields = [];
    
    let shippingData = {};
    if (shippingType === 'customer') {
        const customerId = document.getElementById('checkoutCustomer').value;
        if (!customerId) {
            missingFields.push('เลือกลูกค้าที่จะจัดส่ง');
        } else {
            const customer = checkoutData.customers.find(c => c.id == customerId);
            if (customer) {
                shippingData = {
                    customer_id: customer.id,
                    shipping_name: customer.full_name,
                    shipping_phone: customer.phone,
                    shipping_address: customer.address,
                    shipping_province: customer.province,
                    shipping_district: customer.district,
                    shipping_subdistrict: customer.subdistrict,
                    shipping_postal_code: customer.postal_code
                };
            }
        }
    } else {
        const addr = checkoutData.selfAddress;
        if (!addr || (!addr.address && !addr.province)) {
            missingFields.push('กรุณาตั้งค่าที่อยู่ร้านค้าของคุณในหน้าโปรไฟล์ก่อน');
        } else {
            shippingData = {
                shipping_name: addr.brand_name || addr.full_name,
                shipping_phone: addr.phone,
                shipping_address: addr.address,
                shipping_province: addr.province,
                shipping_district: addr.district,
                shipping_subdistrict: addr.subdistrict,
                shipping_postal_code: addr.postal_code
            };
        }
    }
    
    if (missingFields.length > 0) {
        showAlert('กรุณากรอกข้อมูลให้ครบ:\n• ' + missingFields.join('\n• '), 'error');
        return;
    }
    
    try {
        document.getElementById('btnPlaceOrder').disabled = true;
        document.getElementById('btnPlaceOrder').innerHTML = '<span>กำลังสร้างคำสั่งซื้อ...</span>';
        
        const orderPayload = {
            payment_method: paymentMethod,
            notes: notes,
            shipping_fee: checkoutData.shippingCost || 0,
            ...shippingData
        };
        if (_appliedCoupon) orderPayload.coupon_code = _appliedCoupon.code;
        const response = await fetch(`${RESELLER_API_URL}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderPayload)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const orderId = result.order?.id;

            // Auto-upload slip if attached
            if (selectedPaymentSlip && orderId) {
                document.getElementById('btnPlaceOrder').innerHTML = '<span>กำลังอัปโหลดสลิป...</span>';
                try {
                    const formData = new FormData();
                    formData.append('slip_image', selectedPaymentSlip);
                    formData.append('amount', checkoutData.finalTotal || ((checkoutData.total || 0) + (checkoutData.shippingCost || 0)));

                    const slipRes = await fetch(`${RESELLER_API_URL}/orders/${orderId}/payment-slips`, {
                        method: 'POST',
                        body: formData
                    });

                    if (slipRes.ok) {
                        showAlert('สร้างคำสั่งซื้อและอัปโหลดสลิปสำเร็จ! รอ admin ตรวจสอบ', 'success');
                    } else {
                        const slipErr = await slipRes.json();
                        showAlert('สร้างคำสั่งซื้อสำเร็จ แต่อัปโหลดสลิปไม่สำเร็จ: ' + (slipErr.error || 'กรุณาอัปโหลดใหม่จากหน้าประวัติ'), 'warning');
                    }
                } catch (slipError) {
                    console.error('Slip upload error:', slipError);
                    showAlert('สร้างคำสั่งซื้อสำเร็จ แต่อัปโหลดสลิปไม่สำเร็จ กรุณาอัปโหลดใหม่จากหน้าประวัติ', 'warning');
                }
            } else {
                showAlert('สร้างคำสั่งซื้อสำเร็จ!', 'success');
            }

            selectedPaymentSlip = null;
            loadCartBadge();
            window.location.hash = 'orders';
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ', 'error');
            document.getElementById('btnPlaceOrder').disabled = false;
            document.getElementById('btnPlaceOrder').innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"></path><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                ยืนยันคำสั่งซื้อ
            `;
        }
    } catch (error) {
        console.error('Error placing order:', error);
        showAlert('เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ', 'error');
        document.getElementById('btnPlaceOrder').disabled = false;
    }
}

async function placeOrderAndPayWithStripe() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked').value;
    const notes = document.getElementById('orderNotes').value;
    const btn = document.getElementById('btnStripeCheckout');

    const missingFields = [];
    let shippingData = {};
    if (shippingType === 'customer') {
        const customerId = document.getElementById('checkoutCustomer').value;
        if (!customerId) {
            missingFields.push('เลือกลูกค้าที่จะจัดส่ง');
        } else {
            const customer = checkoutData.customers.find(c => c.id == customerId);
            if (customer) {
                shippingData = {
                    customer_id: customer.id,
                    shipping_name: customer.full_name,
                    shipping_phone: customer.phone,
                    shipping_address: customer.address,
                    shipping_province: customer.province,
                    shipping_district: customer.district,
                    shipping_subdistrict: customer.subdistrict,
                    shipping_postal_code: customer.postal_code
                };
            }
        }
    } else {
        const addr = checkoutData.selfAddress;
        if (!addr || (!addr.address && !addr.province)) {
            missingFields.push('กรุณาตั้งค่าที่อยู่ร้านค้าของคุณในหน้าโปรไฟล์ก่อน');
        } else {
            shippingData = {
                shipping_name: addr.brand_name || addr.full_name,
                shipping_phone: addr.phone,
                shipping_address: addr.address,
                shipping_province: addr.province,
                shipping_district: addr.district,
                shipping_subdistrict: addr.subdistrict,
                shipping_postal_code: addr.postal_code
            };
        }
    }

    if (missingFields.length > 0) {
        showAlert('กรุณากรอกข้อมูลให้ครบ:\n• ' + missingFields.join('\n• '), 'error');
        return;
    }

    if (btn) { btn.disabled = true; btn.textContent = 'กำลังสร้างคำสั่งซื้อ...'; }

    try {
        const orderPayload = {
            payment_method: 'stripe',
            notes: notes,
            shipping_fee: checkoutData.shippingCost || 0,
            ...shippingData
        };
        if (_appliedCoupon) orderPayload.coupon_code = _appliedCoupon.code;

        const res = await fetch(`${RESELLER_API_URL}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderPayload)
        });
        const result = await res.json();
        if (!res.ok) {
            showAlert(result.error || 'ไม่สามารถสร้างคำสั่งซื้อได้', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> ชำระเงินด้วยบัตร'; }
            return;
        }

        const orderId = result.order?.id;
        if (!orderId) {
            showAlert('ไม่พบเลขคำสั่งซื้อ', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> ชำระเงินด้วยบัตร'; }
            return;
        }

        if (btn) btn.textContent = 'กำลังเชื่อมต่อ Stripe...';
        const stripeRes = await fetch(`${RESELLER_API_URL}/orders/${orderId}/stripe-checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const stripeData = await stripeRes.json();
        if (stripeRes.ok && stripeData.checkout_url) {
            window.location.href = stripeData.checkout_url;
        } else {
            showAlert(stripeData.error || 'ไม่สามารถสร้าง Stripe session ได้', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> ชำระเงินด้วยบัตร'; }
        }
    } catch (err) {
        console.error('Stripe checkout error:', err);
        showAlert('เกิดข้อผิดพลาด กรุณาลองใหม่', 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> ชำระเงินด้วยบัตร'; }
    }
}

// ── Stripe Unified Payment ────────────────────────────────────────────────────
let _stripeInstance = null;
let _stripeElements = null;
let _paymentEl      = null;

async function _initCheckoutPaymentEl() {
    if (_stripeElements) return;
    try {
        const res  = await fetch(`${RESELLER_API_URL}/stripe/config`);
        const data = await res.json();
        if (!data.publishable_key) throw new Error('ไม่พบ Stripe publishable key');

        _stripeInstance = Stripe(data.publishable_key);

        const amount = Math.max(Math.round((checkoutData.totalCost || 0) * 100), 100);

        const appearance = {
            theme: 'night',
            variables: {
                colorPrimary: '#6366f1',
                colorBackground: '#1a1035',
                colorText: '#ffffff',
                colorDanger: '#f87171',
                fontFamily: 'Prompt, sans-serif',
                borderRadius: '8px',
                spacingUnit: '5px'
            },
            rules: {
                '.Input': { border: '1px solid rgba(255,255,255,0.2)', backgroundColor: 'rgba(255,255,255,0.06)' },
                '.Input:focus': { border: '1px solid #6366f1', boxShadow: '0 0 0 3px rgba(99,102,241,0.25)' },
                '.Label': { color: 'rgba(255,255,255,0.55)', fontSize: '12px' }
            }
        };

        _stripeElements = _stripeInstance.elements({
            mode: 'payment',
            amount,
            currency: 'thb',
            appearance,
            locale: 'th'
        });

        _paymentEl = _stripeElements.create('payment', {
            layout: { type: 'tabs', defaultCollapsed: false }
        });

        _paymentEl.on('change', e => {
            const errEl = document.getElementById('stripe-card-errors');
            if (errEl) errEl.textContent = e.error ? e.error.message : '';
        });

        const loadingEl = document.getElementById('stripePaymentLoading');
        if (loadingEl) loadingEl.style.display = 'none';

        _paymentEl.mount('#stripe-payment-element');

        validateCheckout();

    } catch (err) {
        console.error('Stripe Payment Element init error:', err);
        const loadingEl = document.getElementById('stripePaymentLoading');
        if (loadingEl) loadingEl.textContent = 'โหลดระบบชำระเงินไม่สำเร็จ กรุณา refresh หน้า';
    }
}

async function handleStripeReturn() {
    const params = new URLSearchParams(window.location.search);
    const piId   = params.get('payment_intent');
    const status = params.get('redirect_status');
    if (!piId) return;

    window.history.replaceState({}, '', window.location.pathname + window.location.hash);

    if (status === 'succeeded') {
        try {
            const res  = await fetch(`${RESELLER_API_URL}/stripe/verify-return`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pi_id: piId })
            });
            const data = await res.json();
            if (data.success) {
                loadCartBadge();
                showAlert(`ชำระเงินสำเร็จ! ออเดอร์ ${data.order_number || ''} กำลังดำเนินการ`, 'success');
                window.location.hash = 'orders';
            } else {
                showAlert(data.message || 'กำลังตรวจสอบการชำระเงิน...', 'success');
                window.location.hash = 'orders';
            }
        } catch (e) {
            console.error('Stripe return verify error:', e);
        }
    } else if (status === 'failed') {
        showAlert('การชำระเงินไม่สำเร็จ กรุณาลองใหม่', 'error');
    }
}

function _getShippingData() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked')?.value;
    const missingFields = [];
    let shippingData = {};

    if (shippingType === 'customer') {
        const customerId = document.getElementById('checkoutCustomer')?.value;
        if (!customerId) {
            missingFields.push('เลือกลูกค้าที่จะจัดส่ง');
        } else {
            const customer = checkoutData.customers.find(c => c.id == customerId);
            if (customer) {
                shippingData = {
                    customer_id: customer.id,
                    shipping_name: customer.full_name,
                    shipping_phone: customer.phone,
                    shipping_address: customer.address,
                    shipping_province: customer.province,
                    shipping_district: customer.district,
                    shipping_subdistrict: customer.subdistrict,
                    shipping_postal_code: customer.postal_code
                };
            }
        }
    } else if (shippingType === 'self') {
        const addr = checkoutData.selfAddress;
        if (!addr || (!addr.address && !addr.province)) {
            missingFields.push('กรุณาตั้งค่าที่อยู่ร้านค้าของคุณในหน้าโปรไฟล์ก่อน');
        } else {
            shippingData = {
                shipping_name: addr.brand_name || addr.full_name,
                shipping_phone: addr.phone,
                shipping_address: addr.address,
                shipping_province: addr.province,
                shipping_district: addr.district,
                shipping_subdistrict: addr.subdistrict,
                shipping_postal_code: addr.postal_code
            };
        }
    } else {
        missingFields.push('เลือกประเภทการจัดส่ง');
    }

    return { missingFields, shippingData };
}

let _checkoutPayMethod = 'stripe';

function selectCheckoutPayment(method) {
    _checkoutPayMethod = method;
    const stripeBtn = document.getElementById('pmBtnStripe');
    const codBtn    = document.getElementById('pmBtnCOD');
    const note      = document.getElementById('checkoutNote');
    const btnText   = document.getElementById('btnPlaceOrderText');
    if (!stripeBtn || !codBtn) return;
    if (method === 'cod') {
        codBtn.style.border    = '2px solid #22c55e';
        codBtn.style.background = 'rgba(34,197,94,0.18)';
        codBtn.style.color     = '#4ade80';
        stripeBtn.style.border    = '2px solid rgba(255,255,255,0.12)';
        stripeBtn.style.background = 'rgba(255,255,255,0.05)';
        stripeBtn.style.color     = 'rgba(255,255,255,0.5)';
        if (btnText) btnText.textContent = 'ยืนยันสั่งซื้อ (COD)';
        if (note) note.textContent = 'ชำระเงินปลายทางผ่าน iShip — ร้านจะบันทึก Tracking หลังจัดส่ง';
    } else {
        stripeBtn.style.border    = '2px solid rgba(168,85,247,0.6)';
        stripeBtn.style.background = 'rgba(168,85,247,0.15)';
        stripeBtn.style.color     = 'white';
        codBtn.style.border    = '2px solid rgba(255,255,255,0.12)';
        codBtn.style.background = 'rgba(255,255,255,0.05)';
        codBtn.style.color     = 'rgba(255,255,255,0.5)';
        if (btnText) btnText.textContent = 'ยืนยันและชำระเงิน';
        if (note) note.textContent = 'ข้อมูลชำระเงินถูกเข้ารหัสโดย Stripe — ไม่ผ่านระบบของเรา';
    }
}

function placeOrderDispatch() {
    if (_checkoutPayMethod === 'cod') {
        placeOrderCOD();
    } else {
        placeOrderWithStripe();
    }
}

async function placeOrderCOD() {
    const { missingFields, shippingData } = _getShippingData();
    if (missingFields.length > 0) {
        showAlert('กรุณากรอกข้อมูลให้ครบ:\n• ' + missingFields.join('\n• '), 'error');
        return;
    }
    const btn     = document.getElementById('btnPlaceOrder');
    const btnText = document.getElementById('btnPlaceOrderText');
    btn.disabled  = true;
    btnText.textContent = 'กำลังสร้างคำสั่งซื้อ...';
    try {
        const order = await _createOrder('cod', shippingData);
        btn.disabled  = false;
        btnText.textContent = 'ยืนยันสั่งซื้อ (COD)';
        await loadCartBadge();
        showAlert(`สั่งซื้อสำเร็จ! เลขที่ ${order.order_number}\nทีมงานจะเตรียมสินค้าและแจ้งเลข Tracking ให้ทราบ`, 'success');
        window.location.hash = 'orders';
        loadOrders();
    } catch (err) {
        console.error('COD order error:', err);
        showAlert(err.message || 'เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ', 'error');
        btn.disabled  = false;
        btnText.textContent = 'ยืนยันสั่งซื้อ (COD)';
    }
}

async function _createOrder(paymentMethod, shippingData) {
    const notes = document.getElementById('orderNotes')?.value || '';
    const orderPayload = {
        payment_method: paymentMethod,
        notes,
        shipping_fee: checkoutData.shippingCost || 0,
        ...shippingData
    };
    if (_appliedCoupon) orderPayload.coupon_code = _appliedCoupon.code;

    const res    = await fetch(`${RESELLER_API_URL}/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderPayload)
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || 'ไม่สามารถสร้างคำสั่งซื้อได้');
    return result.order;
}

async function placeOrderWithStripe() {
    const { missingFields, shippingData } = _getShippingData();
    if (missingFields.length > 0) {
        showAlert('กรุณากรอกข้อมูลให้ครบ:\n• ' + missingFields.join('\n• '), 'error');
        return;
    }

    const btn     = document.getElementById('btnPlaceOrder');
    const btnText = document.getElementById('btnPlaceOrderText');
    btn.disabled  = true;
    btnText.textContent = 'กำลังสร้างคำสั่งซื้อ...';

    try {
        const order = await _createOrder('stripe', shippingData);
        btn.disabled  = false;
        btnText.textContent = 'ยืนยันและชำระเงิน';
        showCardPaymentModal(order.id);
    } catch (err) {
        console.error('Create order error:', err);
        showAlert(err.message || 'เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ', 'error');
        btn.disabled  = false;
        btnText.textContent = 'ยืนยันและชำระเงิน';
    }
}
// ─────────────────────────────────────────────────────────────────────────────

async function loadCartBadge() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`);
        if (response.ok) {
            const data = await response.json();
            const items = data.items || [];
            const totalQty = items.reduce((sum, item) => sum + (item.quantity || 0), 0);
            const badge = document.getElementById('cartBadge');
            const bottomBadge = document.getElementById('bottomCartBadge');
            
            if (totalQty > 0) {
                const displayQty = totalQty > 99 ? '99+' : totalQty;
                if (badge) {
                    badge.textContent = displayQty;
                    badge.style.display = 'block';
                }
                if (bottomBadge) {
                    bottomBadge.textContent = displayQty;
                    bottomBadge.style.display = 'block';
                }
            } else {
                if (badge) badge.style.display = 'none';
                if (bottomBadge) bottomBadge.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading cart badge:', error);
    }
}

async function loadOrders() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/orders`);
        if (!response.ok) throw new Error('Failed to load orders');
        
        const data = await response.json();
        allOrders = Array.isArray(data) ? data : (data.orders || []);
        updateOrderStatusCounts();
        
        const container = document.getElementById('ordersList');
        if (container) {
            filterOrdersByStatus(currentOrderFilter);
        } else {
            renderOrders(allOrders);
        }
    } catch (error) {
        console.error('Error loading orders:', error);
    }
}

function updateOrderStatusCounts() {
    const counts = {
        all: allOrders.length,
        pending_payment: 0,
        under_review: 0,
        preparing: 0,
        shipped: 0,
        delivered: 0,
        failed_delivery: 0,
        cancelled: 0
    };
    
    allOrders.forEach(order => {
        if (counts.hasOwnProperty(order.status)) {
            counts[order.status]++;
        }
    });
    
    Object.keys(counts).forEach(status => {
        const el = document.getElementById(`count-${status}`);
        if (el) el.textContent = counts[status];
    });
}

function filterOrdersByStatus(status) {
    currentOrderFilter = status;
    
    const tabs = document.querySelectorAll('.status-tab');
    if (tabs.length > 0) {
        tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.status === status);
        });
    }
    
    let filtered = allOrders;
    if (status !== 'all') {
        filtered = allOrders.filter(o => o.status === status);
    }
    
    renderOrders(filtered);
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
    
    const isStripeOrder = (o) => o.payment_method === 'stripe' || o.payment_method === 'stripe_promptpay';

    const getStatusLabel = (o) => {
        if (o.status === 'pending_payment') return 'รอชำระเงิน';
        const labels = {
            'pending_payment': 'รอชำระเงิน',
            'under_review': 'รอตรวจสอบ',
            'preparing': 'เตรียมสินค้า',
            'shipped': 'กำลังจัดส่ง',
            'delivered': 'ได้รับสินค้าแล้ว',
            'failed_delivery': 'จัดส่งไม่สำเร็จ',
            'cancelled': 'ยกเลิก'
        };
        return labels[o.status] || o.status;
    };

    const statusColors = {
        'pending_payment': '#f59e0b',
        'under_review': '#3b82f6',
        'preparing': '#8b5cf6',
        'shipped': '#0ea5e9',
        'delivered': '#10b981',
        'failed_delivery': '#ef4444',
        'cancelled': '#6b7280'
    };

    const getPendingButtons = (order) => {
        if (!['pending_payment'].includes(order.status)) return '';
        return `
            <div style="display:flex; gap:8px; margin-top:4px;">
                <button class="order-card-btn" onclick="event.stopPropagation(); showCardPaymentModal(${order.id})" style="flex:1; background:#000; border-radius:10px; color:#fff; font-weight:600;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
                    ชำระเงิน
                </button>
            </div>`;
    };
    
    container.innerHTML = orders.map(order => `
        <div class="order-card-mobile" onclick="viewResellerOrderDetails(${order.id})">
            <div class="order-card-header">
                <span class="order-card-number">${order.order_number || '#' + order.id}</span>
                <span class="order-card-status" style="background: ${statusColors[order.status] || '#6b7280'};">${getStatusLabel(order)}</span>
            </div>
            <div class="order-card-details">
                <span class="order-card-date">${new Date(order.created_at).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                <span class="order-card-amount">฿${(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</span>
            </div>
            ${getPendingButtons(order)}
        </div>
    `).join('');
}

async function viewResellerOrderDetails(orderId) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/orders/${orderId}`);
        if (!response.ok) throw new Error('Failed to load order');
        
        const order = await response.json();
        
        const isStripe = order.payment_method === 'stripe' || order.payment_method === 'stripe_promptpay';
        const statusLabels = {
            'pending_payment': 'รอชำระเงิน',
            'under_review': 'รอตรวจสอบ',
            'preparing': 'เตรียมสินค้า',
            'shipped': 'กำลังจัดส่ง',
            'delivered': 'ได้รับสินค้าแล้ว',
            'failed_delivery': 'จัดส่งไม่สำเร็จ',
            'cancelled': 'ยกเลิก'
        };
        
        const statusColors = {
            'pending_payment': '#f59e0b',
            'under_review': '#3b82f6',
            'preparing': '#8b5cf6',
            'shipped': '#0ea5e9',
            'delivered': '#10b981',
            'failed_delivery': '#ef4444',
            'cancelled': '#6b7280'
        };
        
        let itemsHtml = '';
        if (order.items && order.items.length > 0) {
            itemsHtml = order.items.map(item => {
                let variantText = '';
                if (item.variant_values) {
                    variantText = item.variant_values;
                }
                
                let customizationHtml = '';
                if (item.customization_data) {
                    try {
                        const customizations = typeof item.customization_data === 'string' 
                            ? JSON.parse(item.customization_data) 
                            : item.customization_data;
                        if (Array.isArray(customizations) && customizations.length > 0) {
                            customizationHtml = customizations.map(c => 
                                `<span style="background: rgba(168,85,247,0.2); padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-right: 4px;">${escapeHtml(c.name)}: ${escapeHtml(c.choice)}</span>`
                            ).join('');
                        }
                    } catch(e) {}
                }
                
                return `
                    <div style="padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div style="flex: 1;">
                                <div style="font-weight: 500;">${escapeHtml(item.product_name || 'Product')}</div>
                                <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-top: 2px;">
                                    ${escapeHtml(item.sku_code || '')} ${variantText ? `| ${escapeHtml(variantText)}` : ''} x${item.quantity}
                                </div>
                                ${customizationHtml ? `<div style="margin-top: 4px;">${customizationHtml}</div>` : ''}
                            </div>
                            <span style="font-weight: 600; white-space: nowrap;">฿${(item.subtotal || item.unit_price * item.quantity || 0).toLocaleString('th-TH')}</span>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        let shipmentsHtml = '';
        if (order.shipments && order.shipments.length > 0) {
            shipmentsHtml = `
                <div style="margin-top: 16px;">
                    <h4 style="margin-bottom: 10px; font-size: 14px;">การจัดส่ง</h4>
                    ${order.shipments.map(s => {
                        const shipmentStatus = s.status === 'pending' ? 'รอจัดส่ง' : s.status === 'shipped' ? 'จัดส่งแล้ว' : 'ลูกค้ารับแล้ว';
                        const shipmentColor = s.status === 'pending' ? '#f59e0b' : s.status === 'shipped' ? '#8b5cf6' : '#10b981';
                        const trackingUrl = getTrackingUrl(s.shipping_provider, s.tracking_number);
                        return `
                            <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-size: 13px; font-weight: 500;">${escapeHtml(s.warehouse_name)}</span>
                                    <span style="background: ${shipmentColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px;">${shipmentStatus}</span>
                                </div>
                                ${s.tracking_number ? `
                                    <div style="font-size: 12px; color: rgba(255,255,255,0.7); display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                                        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                                            <span><strong>${escapeHtml(s.shipping_provider || 'ขนส่ง')}:</strong> ${escapeHtml(s.tracking_number)}</span>
                                            <button onclick="navigator.clipboard.writeText('${escapeHtml(s.tracking_number)}').then(()=>{this.textContent='✓ คัดลอกแล้ว';this.style.color='#34d399';setTimeout(()=>{this.textContent='คัดลอก';this.style.color='rgba(255,255,255,0.5)';},1500)})" style="background:none;border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.5);padding:1px 7px;border-radius:5px;font-size:10px;cursor:pointer;white-space:nowrap;transition:all 0.15s;">คัดลอก</button>
                                        </div>
                                        ${trackingUrl ? `<a href="${trackingUrl}" target="_blank" style="color: #a855f7; text-decoration: none; font-size: 11px; white-space: nowrap; flex-shrink: 0;">ติดตามพัสดุ →</a>` : ''}
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }
        
        let slipsHtml = '';
        
        let recipientHtml = '';
        const recipient = order.customer || order.reseller;
        if (recipient) {
            const addressParts = [
                recipient.address,
                recipient.subdistrict,
                recipient.district,
                recipient.province,
                recipient.postal_code
            ].filter(Boolean);
            recipientHtml = `
                <div style="margin-top: 16px;">
                    <h4 style="margin-bottom: 10px; font-size: 14px;">ข้อมูลผู้รับ</h4>
                    <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; font-size: 13px;">
                        <div style="font-weight: 500; margin-bottom: 4px;">${escapeHtml(recipient.full_name || recipient.name || '')}</div>
                        <div style="color: rgba(255,255,255,0.7);">${escapeHtml(recipient.phone || '')}</div>
                        ${addressParts.length > 0 ? `<div style="color: rgba(255,255,255,0.6); margin-top: 4px; line-height: 1.4;">${escapeHtml(addressParts.join(' '))}</div>` : ''}
                    </div>
                </div>
            `;
        }
        
        let rejectionNoticeHtml = '';
        if (order.status === 'pending_payment') {
            rejectionNoticeHtml = `
                <div style="background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); border-radius: 10px; padding: 12px 14px; margin-bottom: 16px; display:flex; align-items:flex-start; gap:10px;">
                    <span style="font-size:18px; flex-shrink:0;">⏳</span>
                    <div>
                        <div style="color: #fbbf24; font-weight: 600; margin-bottom: 4px; font-size: 13px;">รอชำระเงิน</div>
                        <div style="color: rgba(255,255,255,0.65); font-size: 12px; line-height: 1.5;">กรุณาชำระเงินภายใน 24 ชม. มิฉะนั้นระบบจะยกเลิกคำสั่งซื้ออัตโนมัติ</div>
                    </div>
                </div>
            `;
        }
        
        let refundHtml = '';
        if (order.refund) {
            const rf = order.refund;
            const rfAmount = (rf.refund_amount || 0).toLocaleString('th-TH', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            const rfDate = rf.completed_at
                ? new Date(rf.completed_at).toLocaleString('th-TH', {day:'numeric', month:'short', year:'numeric'})
                : (rf.created_at ? new Date(rf.created_at).toLocaleString('th-TH', {day:'numeric', month:'short', year:'numeric'}) : '');
            const isDone = rf.status === 'completed';
            refundHtml = `
                <div style="margin-top: 16px;">
                    <h4 style="margin-bottom: 8px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: rgba(255,255,255,0.5);">การคืนเงิน</h4>
                    <div style="background: ${isDone ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.1)'}; border: 1px solid ${isDone ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}; border-radius: 12px; padding: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: ${rf.slip_url ? '12px' : '0'};">
                            <div>
                                <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 2px;">ยอดคืนเงิน</div>
                                <div style="font-size: 20px; font-weight: 700; color: ${isDone ? '#34d399' : '#ffffff'};">฿${rfAmount}</div>
                            </div>
                            <span style="background: ${isDone ? 'rgba(16,185,129,0.25)' : 'rgba(245,158,11,0.25)'}; color: ${isDone ? '#34d399' : '#ffffff'}; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600;">
                                ${isDone ? '✅ คืนเงินสำเร็จ' : '⏳ รอดำเนินการ'}
                            </span>
                        </div>
                        ${rf.slip_url ? `
                            <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 12px;">
                                <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 8px;">สลิปคืนเงินจาก Admin</div>
                                <img src="${rf.slip_url}" alt="สลิปคืนเงิน"
                                    onclick="window.open('${rf.slip_url}', '_blank')"
                                    style="width: 100%; max-height: 260px; object-fit: contain; border-radius: 10px; background: rgba(0,0,0,0.3); cursor: pointer; border: 1px solid rgba(255,255,255,0.1);">
                                ${rfDate ? `<div style="font-size: 11px; color: rgba(255,255,255,0.4); margin-top: 6px; text-align: right;">${rfDate}</div>` : ''}
                            </div>
                        ` : `
                            <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px; font-size: 12px; color: rgba(255,255,255,0.5);">
                                Admin จะดำเนินการโอนเงินและส่งสลิปในเร็ว ๆ นี้
                            </div>
                        `}
                    </div>
                </div>
            `;
        }

        let actionsHtml = '';
        if (order.status === 'pending_payment') {
            actionsHtml = `
                <div style="margin-top: 16px;">
                    <button class="btn" onclick="closeOrderModal(); showCardPaymentModal(${orderId})" style="width: 100%; padding: 15px; font-size: 15px; font-weight: 700; background: #000; border: none; border-radius: 12px; color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; font-family:-apple-system,BlinkMacSystemFont,'Prompt',sans-serif;">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
                        ชำระเงิน
                    </button>
                    <p style="text-align:center; font-size:11px; color:rgba(255,255,255,0.35); margin-top:8px;">สินค้าจองไว้ไม่เกิน 24 ชม.</p>
                </div>
            `;
        }
        
        const itemTotal = (order.final_amount || 0) - (order.shipping_fee || 0);
        const shippingFee = order.shipping_fee || 0;
        const grandTotal = order.final_amount || 0;

        const summaryHtml = `
            <div style="background: rgba(255,255,255,0.05); border-radius: 10px; padding: 14px; margin-bottom: 4px;">
                ${itemsHtml || '<p style="opacity: 0.6; text-align: center; font-size: 13px;">ไม่มีรายการ</p>'}
                <div style="border-top: 1px solid rgba(255,255,255,0.15); margin-top: 10px; padding-top: 10px;">
                    ${order.discount_amount > 0 ? `
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 4px;">
                        <span>ส่วนลดสมาชิก</span>
                        <span style="color: #34d399;">-฿${order.discount_amount.toLocaleString('th-TH')}</span>
                    </div>` : ''}
                    ${order.promotion_discount > 0 ? `
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 4px;">
                        <span>⚡ โปรโมชัน</span>
                        <span style="color: #4ade80;">-฿${order.promotion_discount.toLocaleString('th-TH')}</span>
                    </div>` : ''}
                    ${order.coupon_discount > 0 ? `
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 4px;">
                        <span>🎟 คูปองส่วนลด</span>
                        <span style="color: #4ade80;">-฿${order.coupon_discount.toLocaleString('th-TH')}</span>
                    </div>` : ''}
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 4px;">
                        <span>ค่าจัดส่ง</span>
                        <span>${shippingFee > 0 ? `฿${shippingFee.toLocaleString('th-TH')}` : '<span style="color: #34d399;">ฟรี</span>'}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 15px; margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.1);">
                        <span>ยอดรวมทั้งหมด</span>
                        <span style="color: #ffffff;">฿${grandTotal.toLocaleString('th-TH')}</span>
                    </div>
                </div>
            </div>
        `;

        const modalHtml = `
            <div id="orderDetailModal" style="position: fixed; inset: 0; background: linear-gradient(160deg, #1a0a2e 0%, #0d0a1e 100%); z-index: 10002; display: flex; flex-direction: column; animation: slideUpFull 0.28s cubic-bezier(.4,0,.2,1);">
                <style>@keyframes slideUpFull { from { transform: translateY(100%); opacity: 0.5; } to { transform: translateY(0); opacity: 1; } }</style>
                <div style="flex-shrink: 0; padding: 16px 20px 12px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.3); display: flex; align-items: center; gap: 12px; backdrop-filter: blur(10px);">
                    <button onclick="closeOrderModal()" style="background: rgba(255,255,255,0.1); border: none; color: white; width: 36px; height: 36px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="18" height="18"><polyline points="15 18 9 12 15 6"></polyline></svg>
                    </button>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 700; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${order.order_number || '#' + order.id}</div>
                        <div style="font-size: 11px; color: rgba(255,255,255,0.5);">${new Date(order.created_at).toLocaleString('th-TH', {day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})}</div>
                    </div>
                    <span style="background: ${statusColors[order.status] || '#6b7280'}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; white-space: nowrap; flex-shrink: 0;">${statusLabels[order.status] || order.status}</span>
                </div>
                <div style="flex: 1; overflow-y: auto; padding: 20px; -webkit-overflow-scrolling: touch;">
                    ${rejectionNoticeHtml}
                    ${order.notes ? `<div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; font-size: 13px; color: rgba(255,255,255,0.7);">📝 ${escapeHtml(order.notes)}</div>` : ''}
                    <h4 style="margin-bottom: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: rgba(255,255,255,0.5);">รายการสินค้า</h4>
                    ${summaryHtml}
                    ${recipientHtml}
                    ${shipmentsHtml}
                    ${slipsHtml}
                    ${refundHtml}
                    ${actionsHtml}
                    <div style="height: 24px;"></div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        console.error('Error loading order details:', error);
        showAlert('ไม่สามารถโหลดรายละเอียดได้', 'error');
    }
}

function closeOrderModal() {
    const modal = document.getElementById('orderDetailModal');
    if (modal) modal.remove();
}

async function payOrderWithStripe(orderId) {
    await showCardPaymentModal(orderId);
}

let _modalStripe         = null;
let _ppPollingTimer      = null;
let _modalStripeElements = null;

async function showCardPaymentModal(orderId) {
    const existing = document.getElementById('stripeCardModal');
    if (existing) existing.remove();
    _modalStripeElements = null;

    const modal = document.createElement('div');
    modal.id = 'stripeCardModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);backdrop-filter:blur(8px);z-index:10010;display:flex;align-items:flex-end;justify-content:center;padding:0;';
    modal.innerHTML = `
        <div id="stripeCardModalSheet" style="background:#fff;border-radius:20px 20px 0 0;width:100%;max-width:480px;position:relative;max-height:92vh;overflow-y:auto;box-shadow:0 -4px 32px rgba(0,0,0,0.18);font-family:-apple-system,BlinkMacSystemFont,'Prompt',sans-serif;">
            <div style="width:36px;height:4px;background:#d1d1d6;border-radius:2px;margin:12px auto 0;"></div>
            <div style="padding:20px 24px 32px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;">
                    <div>
                        <h3 style="font-size:20px;font-weight:700;color:#1d1d1f;margin:0 0 2px;">ชำระเงิน</h3>
                        <p id="cardModalOrderNum" style="font-size:13px;color:#6e6e73;margin:0;"></p>
                    </div>
                    <button onclick="closeCardPaymentModal()" style="background:rgba(0,0,0,0.06);border:none;color:#3c3c43;width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px;">&times;</button>
                </div>

                <div id="cardModalLoading" style="text-align:center;padding:40px 0;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#86868b" stroke-width="2" style="width:28px;height:28px;animation:spin 1s linear infinite;"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>
                    <p style="margin-top:10px;font-size:13px;color:#86868b;">กำลังโหลด...</p>
                </div>

                <div id="cardTabContent" style="display:none;">
                    <div style="margin:0 0 8px;">
                        <div id="modal-payment-element" style="min-height:80px;"></div>
                        <div id="modal-card-errors" style="color:#ff3b30;font-size:12px;min-height:16px;margin-top:6px;"></div>
                    </div>
                    <button id="btnModalPay" onclick="submitCardPaymentModal(${orderId})" style="width:100%;margin-top:12px;padding:16px;background:#000;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;letter-spacing:-0.2px;font-family:-apple-system,BlinkMacSystemFont,'Prompt',sans-serif;">
                        ชำระเงิน
                    </button>
                    <div id="cardModalFooter" style="border-top:1px solid #f2f2f7;margin:16px 0 0;padding-top:14px;">
                        <button onclick="payLaterFromModal(${orderId})" style="width:100%;padding:12px;background:transparent;border:none;color:#6e6e73;font-size:14px;font-weight:500;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,'Prompt',sans-serif;">
                            ชำระเงินภายหลัง
                        </button>
                        <p style="text-align:center;color:#aeaeb2;font-size:11px;margin:6px 0 0;line-height:1.5;padding:0 8px;">
                            สินค้าจองไว้ให้ไม่เกิน 24 ชม. — หากยังไม่ชำระระบบจะยกเลิกอัตโนมัติ
                        </p>
                    </div>
                </div>
                <p style="text-align:center;color:#aeaeb2;font-size:11px;margin-top:12px;">🔒 ชำระเงินผ่าน Stripe — ข้อมูลไม่ผ่านระบบของเรา</p>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener('click', e => {
        if (e.target === modal) closeCardPaymentModal();
    });

    try {
        if (!_modalStripe) {
            const cfgRes  = await fetch(`${RESELLER_API_URL}/stripe/config`);
            const cfgData = await cfgRes.json();
            if (!cfgData.publishable_key) throw new Error('ไม่พบ Stripe key');
            _modalStripe = Stripe(cfgData.publishable_key);
        }

        const [orderRes, piRes] = await Promise.all([
            fetch(`${RESELLER_API_URL}/orders/${orderId}`),
            fetch(`${RESELLER_API_URL}/orders/${orderId}/stripe-payment-intent`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
        ]);

        if (orderRes.ok) {
            const oData = await orderRes.json();
            const o = oData.order || oData;
            const num = o.order_number || `#${orderId}`;
            const amt = o.final_amount ? `฿${Number(o.final_amount).toLocaleString('th-TH', {minimumFractionDigits:2})}` : '';
            document.getElementById('cardModalOrderNum').textContent = `${num}${amt ? ' — ' + amt : ''}`;
        }

        const piData = await piRes.json();
        if (!piRes.ok) throw new Error(piData.error || 'ไม่สามารถสร้าง payment intent');

        const appearance = {
            theme: 'stripe',
            variables: {
                colorPrimary: '#000000',
                colorBackground: '#ffffff',
                colorText: '#1d1d1f',
                colorDanger: '#ff3b30',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Prompt", sans-serif',
                borderRadius: '10px',
                spacingUnit: '4px',
                fontSizeBase: '14px'
            },
            rules: {
                '.Input': { border: '1.5px solid #d1d1d6', boxShadow: 'none', backgroundColor: '#ffffff', padding: '11px 12px' },
                '.Input:focus': { border: '1.5px solid #000000', boxShadow: '0 0 0 3px rgba(0,0,0,0.06)' },
                '.Label': { color: '#3c3c43', fontSize: '12px', fontWeight: '500', marginBottom: '6px' },
                '.Tab': { border: '1.5px solid #e5e5ea', backgroundColor: '#f9f9f9' },
                '.Tab--selected': { borderColor: '#000', backgroundColor: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' },
                '.Tab:hover': { backgroundColor: '#f2f2f7' }
            }
        };

        _modalStripeElements = _modalStripe.elements({
            clientSecret: piData.client_secret,
            appearance,
            locale: 'th'
        });

        const payEl = _modalStripeElements.create('payment', {
            layout: { type: 'tabs', defaultCollapsed: false }
        });
        payEl.on('change', e => {
            const errEl = document.getElementById('modal-card-errors');
            if (errEl) errEl.textContent = e.error ? e.error.message : '';
        });

        document.getElementById('cardModalLoading').style.display = 'none';
        document.getElementById('cardTabContent').style.display = 'block';
        payEl.mount('#modal-payment-element');

    } catch (err) {
        console.error('Modal init error:', err);
        showAlert('ไม่สามารถโหลด Stripe ได้ กรุณาลองใหม่', 'error');
        modal.remove();
        _modalStripeElements = null;
    }
}

function payLaterFromModal(orderId) {
    closeCardPaymentModal();
    showAlert('สั่งซื้อเรียบร้อย! สินค้าจองไว้ให้ 24 ชม. กรุณาชำระเงินก่อนหมดเวลา', 'success');
    loadCartBadge();
    window.location.hash = 'orders';
    setTimeout(() => loadOrders && loadOrders(), 300);
}

function switchPaymentTab(tab, orderId) {
    const btnCard = document.getElementById('tabBtnCard');
    const btnPP   = document.getElementById('tabBtnPP');
    const cardTab = document.getElementById('cardTabContent');
    const ppTab   = document.getElementById('promptpayTabContent');
    const footer  = document.getElementById('cardModalFooter');

    if (tab === 'card') {
        btnCard.style.background = '#000'; btnCard.style.color = '#fff'; btnCard.style.borderColor = '#000';
        btnPP.style.background   = '#fff'; btnPP.style.color   = '#3c3c43'; btnPP.style.borderColor = '#e5e5ea';
        cardTab.style.display = 'block';
        ppTab.style.display   = 'none';
        footer.style.display  = 'block';
        if (_ppPollingTimer) { clearInterval(_ppPollingTimer); _ppPollingTimer = null; }
    } else {
        btnPP.style.background   = '#000'; btnPP.style.color   = '#fff'; btnPP.style.borderColor = '#000';
        btnCard.style.background = '#fff'; btnCard.style.color = '#3c3c43'; btnCard.style.borderColor = '#e5e5ea';
        cardTab.style.display = 'none';
        ppTab.style.display   = 'block';
        footer.style.display  = 'none';
        _loadStripePromptPayQR(orderId);
    }
}

async function _loadStripePromptPayQR(orderId) {
    const loadEl  = document.getElementById('ppQRLoading');
    const contEl  = document.getElementById('ppQRContent');
    const errEl   = document.getElementById('ppQRError');
    if (!loadEl) return;
    loadEl.style.display  = 'block';
    contEl.style.display  = 'none';
    errEl.style.display   = 'none';

    try {
        const res  = await fetch(`${RESELLER_API_URL}/orders/${orderId}/stripe-promptpay-intent`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'สร้าง QR ไม่สำเร็จ');

        loadEl.style.display = 'none';
        contEl.style.display = 'block';
        document.getElementById('ppQRImage').src     = data.qr_url;
        document.getElementById('ppQRAmount').textContent = `฿${Number(data.amount).toLocaleString('th-TH', {minimumFractionDigits:2})}`;

        _ppPollingTimer = setInterval(async () => {
            try {
                const statusRes  = await fetch(`${RESELLER_API_URL}/orders/${orderId}`);
                const statusData = await statusRes.json();
                const order      = statusData.order || statusData;
                const pollingEl  = document.getElementById('ppPollingStatus');
                if (order.status === 'under_review' || order.status === 'preparing' || order.status === 'shipped' || order.status === 'delivered') {
                    if (_ppPollingTimer) { clearInterval(_ppPollingTimer); _ppPollingTimer = null; }
                    if (pollingEl) pollingEl.innerHTML = '✅ ชำระเงินสำเร็จ! กำลังอัปเดต...';
                    setTimeout(() => { closeCardPaymentModal(); loadOrders && loadOrders(); window.location.hash = 'orders'; }, 1500);
                }
            } catch(e) {}
        }, 3000);
    } catch (e) {
        loadEl.style.display = 'none';
        errEl.style.display  = 'block';
        const p = errEl.querySelector('p');
        if (p) p.textContent = e.message;
    }
}

function closeCardPaymentModal() {
    const modal = document.getElementById('stripeCardModal');
    if (modal) modal.remove();
    _modalStripeElements = null;
    if (_ppPollingTimer) { clearInterval(_ppPollingTimer); _ppPollingTimer = null; }
}

async function submitCardPaymentModal(orderId) {
    if (!_modalStripe || !_modalStripeElements) {
        showAlert('Stripe ยังโหลดไม่เสร็จ กรุณารอสักครู่', 'error');
        return;
    }
    const btn = document.getElementById('btnModalPay');
    if (btn) { btn.disabled = true; btn.textContent = 'กำลังประมวลผลบัตร...'; }

    try {
        const returnUrl = window.location.origin + window.location.pathname;
        const { error, paymentIntent } = await _modalStripe.confirmPayment({
            elements: _modalStripeElements,
            confirmParams: { return_url: returnUrl },
            redirect: 'if_required'
        });

        if (error) {
            const errEl = document.getElementById('modal-card-errors');
            if (errEl) errEl.textContent = error.message;
            if (btn) { btn.disabled = false; btn.textContent = 'ชำระเงิน'; }
            return;
        }

        closeCardPaymentModal();
        loadCartBadge();

        fetch(`${RESELLER_API_URL}/orders/${orderId}/stripe-card-confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pi_id: paymentIntent?.id })
        }).catch(() => {});

        showAlert('ชำระเงินสำเร็จ! 🎉', 'success');
        window.location.hash = 'home';

    } catch (err) {
        console.error('Modal card payment error:', err);
        showAlert(err.message || 'เกิดข้อผิดพลาด กรุณาลองใหม่', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'ชำระเงิน'; }
    }
}

function openPaymentSlipModal(orderId) {
    const modalHtml = `
        <div id="paymentSlipModal" style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 10003; display: flex; align-items: center; justify-content: center; padding: 20px;">
            <div style="background: linear-gradient(135deg, rgba(30,20,50,0.98), rgba(20,10,40,0.98)); border: 1px solid rgba(168,85,247,0.3); border-radius: 16px; max-width: 400px; width: 100%; position: relative;">
                <button onclick="closePaymentSlipModal()" style="position: absolute; top: 12px; right: 12px; background: none; border: none; color: white; font-size: 24px; cursor: pointer; padding: 5px; line-height: 1;">&times;</button>
                <div style="padding: 24px;">
                    <h3 style="margin-bottom: 16px; font-size: 16px;">อัพโหลดสลิปชำระเงิน</h3>
                    <div style="text-align: center; padding: 24px; border: 2px dashed rgba(168,85,247,0.5); border-radius: 12px; margin-bottom: 16px; cursor: pointer;" onclick="document.getElementById('slipFileInput').click()">
                        <input type="file" id="slipFileInput" accept="image/*" style="display: none;" onchange="previewSlipImage(this)">
                        <div id="slipPreviewContainer" style="display: none;">
                            <img id="slipPreviewImg" style="max-width: 100%; max-height: 200px; border-radius: 8px;">
                        </div>
                        <div id="slipUploadPlaceholder">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 48px; height: 48px; margin-bottom: 8px; opacity: 0.5;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                            <p style="color: rgba(255,255,255,0.6); font-size: 13px;">คลิกเพื่อเลือกรูปสลิป</p>
                        </div>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="font-size: 13px; display: block; margin-bottom: 6px;">ยอดที่โอน (บาท)</label>
                        <input type="number" id="slipAmount" class="form-input" placeholder="ระบุยอดที่โอน" style="width: 100%;">
                    </div>
                    <button onclick="uploadPaymentSlip(${orderId})" id="btnUploadSlip" class="btn" style="width: 100%; padding: 12px; background: linear-gradient(135deg, #a855f7, #ec4899);">
                        อัพโหลดสลิป
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closePaymentSlipModal() {
    const modal = document.getElementById('paymentSlipModal');
    if (modal) modal.remove();
}

function previewSlipImage(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            document.getElementById('slipPreviewImg').src = e.target.result;
            document.getElementById('slipPreviewContainer').style.display = 'block';
            document.getElementById('slipUploadPlaceholder').style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

async function uploadPaymentSlip(orderId) {
    const fileInput = document.getElementById('slipFileInput');
    const amount = document.getElementById('slipAmount').value;
    
    if (!fileInput.files || !fileInput.files[0]) {
        showAlert('กรุณาเลือกรูปสลิป', 'error');
        return;
    }
    
    const btn = document.getElementById('btnUploadSlip');
    btn.disabled = true;
    btn.textContent = 'กำลังอัพโหลด...';
    
    try {
        const formData = new FormData();
        formData.append('slip_image', fileInput.files[0]);
        if (amount) formData.append('amount', amount);
        
        const response = await fetch(`${RESELLER_API_URL}/orders/${orderId}/payment-slips`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            showAlert('ส่งสลิปสำเร็จ! รอ admin ตรวจสอบสลิป', 'success');
            closePaymentSlipModal();
            closeOrderModal();
            loadOrders();
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
            btn.disabled = false;
            btn.textContent = 'อัพโหลดสลิป';
        }
    } catch (error) {
        console.error('Error uploading slip:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
        btn.disabled = false;
        btn.textContent = 'อัพโหลดสลิป';
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
    
    populateProvinceSelect('customerProvince');
    document.getElementById('customerDistrict').innerHTML = '<option value="">-- เลือกเขต/อำเภอ --</option>';
    document.getElementById('customerSubdistrict').innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
    document.getElementById('customerPostalCode').value = '';
    
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
        subdistrict: getSelectedText('customerSubdistrict'),
        district: getSelectedText('customerDistrict'),
        province: getSelectedText('customerProvince'),
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
        
        const profileDisplayName = profile.full_name || profile.username || 'สมาชิก';
        document.getElementById('profileName').textContent = profileDisplayName;
        document.getElementById('profileUsername').textContent = profile.username || '';
        document.getElementById('profileAvatar').textContent = profileDisplayName.charAt(0).toUpperCase();
        
        document.getElementById('profileTierIcon').innerHTML = getTierSVG(profile.tier_name || 'Bronze', 20);
        document.getElementById('profileTierName').textContent = profile.tier_name || '-';
        
        document.getElementById('brandName').value = profile.brand_name || '';
        document.getElementById('profilePhone').value = profile.phone || '';
        document.getElementById('profileEmail').value = profile.email || '';
        document.getElementById('profileAddress').value = profile.address || '';
        document.getElementById('profilePostalCode').value = profile.postal_code || '';
        const bankSel = document.getElementById('profileBankName');
        if (bankSel) bankSel.value = profile.bank_name || '';
        const bankAcc = document.getElementById('profileBankAccountNumber');
        if (bankAcc) bankAcc.value = profile.bank_account_number || '';
        const bankName = document.getElementById('profileBankAccountName');
        if (bankName) bankName.value = profile.bank_account_name || '';
        const ppNum = document.getElementById('profilePromptpayNumber');
        if (ppNum) ppNum.value = profile.promptpay_number || '';
        
        populateProvinceSelect('profileProvince');
        
        if (profile.province) {
            await setProfileAddressFromText(profile.province, profile.district, profile.subdistrict, profile.postal_code);
        }
        loadProfileCouponWallet();
    } catch (error) {
        console.error('Error loading profile:', error);
    }
}

async function setProfileAddressFromText(provinceName, districtName, subdistrictName, postalCode) {
    const provinceSelect = document.getElementById('profileProvince');
    const districtSelect = document.getElementById('profileDistrict');
    const subdistrictSelect = document.getElementById('profileSubdistrict');
    
    const province = thailandProvinces.find(p => p.provinceNameTh === provinceName);
    if (province) {
        provinceSelect.value = province.provinceCode;
        
        const distResponse = await fetch(`${RESELLER_API_URL}/thailand/districts/${province.provinceCode}`);
        if (distResponse.ok) {
            const districts = await distResponse.json();
            thailandDistricts['profile'] = districts;
            districtSelect.innerHTML = '<option value="">-- เลือกเขต/อำเภอ --</option>';
            districts.forEach(d => {
                const option = document.createElement('option');
                option.value = d.districtCode;
                option.textContent = d.districtNameTh;
                option.dataset.name = d.districtNameTh;
                districtSelect.appendChild(option);
            });
            
            const district = districts.find(d => d.districtNameTh === districtName);
            if (district) {
                districtSelect.value = district.districtCode;
                
                const subResponse = await fetch(`${RESELLER_API_URL}/thailand/subdistricts/${district.districtCode}`);
                if (subResponse.ok) {
                    const subdistricts = await subResponse.json();
                    thailandSubdistricts['profile'] = subdistricts;
                    subdistrictSelect.innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
                    subdistricts.forEach(s => {
                        const option = document.createElement('option');
                        option.value = s.subdistrictCode;
                        option.textContent = s.subdistrictNameTh;
                        option.dataset.name = s.subdistrictNameTh;
                        option.dataset.postalCode = s.postalCode;
                        subdistrictSelect.appendChild(option);
                    });
                    
                    const subdistrict = subdistricts.find(s => s.subdistrictNameTh === subdistrictName);
                    if (subdistrict) {
                        subdistrictSelect.value = subdistrict.subdistrictCode;
                    }
                }
            }
        }
    }
    
    if (postalCode) {
        document.getElementById('profilePostalCode').value = postalCode;
    }
}

async function handleSaveProfile(event) {
    event.preventDefault();
    
    const profileData = {
        brand_name: document.getElementById('brandName').value,
        phone: document.getElementById('profilePhone').value,
        email: document.getElementById('profileEmail').value,
        address: document.getElementById('profileAddress').value,
        subdistrict: getSelectedText('profileSubdistrict'),
        district: getSelectedText('profileDistrict'),
        province: getSelectedText('profileProvince'),
        postal_code: document.getElementById('profilePostalCode').value,
        bank_name: document.getElementById('profileBankName')?.value || '',
        bank_account_number: document.getElementById('profileBankAccountNumber')?.value || '',
        bank_account_name: document.getElementById('profileBankAccountName')?.value || '',
        promptpay_number: document.getElementById('profilePromptpayNumber')?.value || '',
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

let thailandProvinces = [];
let thailandDistricts = {};
let thailandSubdistricts = {};

async function loadThailandProvinces() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/thailand/provinces`);
        if (response.ok) {
            thailandProvinces = await response.json();
        }
    } catch (error) {
        console.error('Error loading provinces:', error);
    }
}

function populateProvinceSelect(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = '<option value="">-- เลือกจังหวัด --</option>';
    thailandProvinces.forEach(p => {
        const option = document.createElement('option');
        option.value = p.provinceCode;
        option.textContent = p.provinceNameTh;
        option.dataset.name = p.provinceNameTh;
        select.appendChild(option);
    });
}

async function loadProfileDistricts() {
    const provinceSelect = document.getElementById('profileProvince');
    const districtSelect = document.getElementById('profileDistrict');
    const subdistrictSelect = document.getElementById('profileSubdistrict');
    const postalCodeInput = document.getElementById('profilePostalCode');
    
    districtSelect.innerHTML = '<option value="">-- เลือกเขต/อำเภอ --</option>';
    subdistrictSelect.innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
    postalCodeInput.value = '';
    
    const provinceCode = parseInt(provinceSelect.value);
    if (!provinceCode) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/thailand/districts/${provinceCode}`);
        if (response.ok) {
            const districts = await response.json();
            thailandDistricts['profile'] = districts;
            districts.forEach(d => {
                const option = document.createElement('option');
                option.value = d.districtCode;
                option.textContent = d.districtNameTh;
                option.dataset.name = d.districtNameTh;
                districtSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading districts:', error);
    }
}

async function loadProfileSubdistricts() {
    const districtSelect = document.getElementById('profileDistrict');
    const subdistrictSelect = document.getElementById('profileSubdistrict');
    const postalCodeInput = document.getElementById('profilePostalCode');
    
    subdistrictSelect.innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
    postalCodeInput.value = '';
    
    const districtCode = parseInt(districtSelect.value);
    if (!districtCode) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/thailand/subdistricts/${districtCode}`);
        if (response.ok) {
            const subdistricts = await response.json();
            thailandSubdistricts['profile'] = subdistricts;
            subdistricts.forEach(s => {
                const option = document.createElement('option');
                option.value = s.subdistrictCode;
                option.textContent = s.subdistrictNameTh;
                option.dataset.name = s.subdistrictNameTh;
                option.dataset.postalCode = s.postalCode;
                subdistrictSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading subdistricts:', error);
    }
}

function updateProfilePostalCode() {
    const subdistrictSelect = document.getElementById('profileSubdistrict');
    const postalCodeInput = document.getElementById('profilePostalCode');
    
    const selectedOption = subdistrictSelect.options[subdistrictSelect.selectedIndex];
    if (selectedOption && selectedOption.dataset.postalCode) {
        postalCodeInput.value = selectedOption.dataset.postalCode;
    } else {
        postalCodeInput.value = '';
    }
}

async function loadCustomerDistricts() {
    const provinceSelect = document.getElementById('customerProvince');
    const districtSelect = document.getElementById('customerDistrict');
    const subdistrictSelect = document.getElementById('customerSubdistrict');
    const postalCodeInput = document.getElementById('customerPostalCode');
    
    districtSelect.innerHTML = '<option value="">-- เลือกเขต/อำเภอ --</option>';
    subdistrictSelect.innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
    postalCodeInput.value = '';
    
    const provinceCode = parseInt(provinceSelect.value);
    if (!provinceCode) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/thailand/districts/${provinceCode}`);
        if (response.ok) {
            const districts = await response.json();
            thailandDistricts['customer'] = districts;
            districts.forEach(d => {
                const option = document.createElement('option');
                option.value = d.districtCode;
                option.textContent = d.districtNameTh;
                option.dataset.name = d.districtNameTh;
                districtSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading districts:', error);
    }
}

async function loadCustomerSubdistricts() {
    const districtSelect = document.getElementById('customerDistrict');
    const subdistrictSelect = document.getElementById('customerSubdistrict');
    const postalCodeInput = document.getElementById('customerPostalCode');
    
    subdistrictSelect.innerHTML = '<option value="">-- เลือกแขวง/ตำบล --</option>';
    postalCodeInput.value = '';
    
    const districtCode = parseInt(districtSelect.value);
    if (!districtCode) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/thailand/subdistricts/${districtCode}`);
        if (response.ok) {
            const subdistricts = await response.json();
            thailandSubdistricts['customer'] = subdistricts;
            subdistricts.forEach(s => {
                const option = document.createElement('option');
                option.value = s.subdistrictCode;
                option.textContent = s.subdistrictNameTh;
                option.dataset.name = s.subdistrictNameTh;
                option.dataset.postalCode = s.postalCode;
                subdistrictSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading subdistricts:', error);
    }
}

function updateCustomerPostalCode() {
    const subdistrictSelect = document.getElementById('customerSubdistrict');
    const postalCodeInput = document.getElementById('customerPostalCode');
    
    const selectedOption = subdistrictSelect.options[subdistrictSelect.selectedIndex];
    if (selectedOption && selectedOption.dataset.postalCode) {
        postalCodeInput.value = selectedOption.dataset.postalCode;
    } else {
        postalCodeInput.value = '';
    }
}

function getSelectedText(selectId) {
    const select = document.getElementById(selectId);
    if (!select || select.selectedIndex < 0) return '';
    const option = select.options[select.selectedIndex];
    return option.dataset.name || option.textContent || '';
}

// ===========================================
// MTO (Made-to-Order) Functions
// ===========================================

let mtoProducts = [];
let mtoQuotes = [];
let mtoOrders = [];
let currentMtoQuoteFilter = 'all';
let currentMtoOrderFilter = 'all';

async function loadMtoCatalog() {
    loadMtoProducts();
    loadResellerMtoQuotes();
    loadResellerMtoOrders();
}

async function loadMtoProducts() {
    const grid = document.getElementById('mtoCatalogGrid');
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/products`);
        if (!response.ok) throw new Error('Failed to load products');
        
        mtoProducts = await response.json();
        
        if (mtoProducts.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"></path></svg>
                    <h3>ยังไม่มีสินค้าสั่งผลิต</h3>
                    <p>กรุณารอสินค้าใหม่เร็วๆ นี้</p>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = mtoProducts.map(product => `
            <div class="mto-product-card">
                <img src="${product.image_url || '/static/images/placeholder.png'}" alt="${product.name}" class="mto-product-image" onerror="this.src='/static/images/placeholder.png'">
                <div class="mto-product-info">
                    <div class="mto-product-name">${product.name}</div>
                    <div class="mto-product-meta">
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                            ${product.production_days || 14} วันผลิต
                        </span>
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"></path></svg>
                            ขั้นต่ำ ${product.min_order_qty || 10} ชิ้น
                        </span>
                    </div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 12px;">
                        มัดจำ ${product.deposit_percent || 50}%
                    </div>
                    <div class="mto-product-actions">
                        <button class="btn-request-quote" onclick="openMtoRequestModal(${product.id})">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                            ขอใบเสนอราคา
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading MTO products:', error);
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <h3>ไม่สามารถโหลดข้อมูลได้</h3>
                <p>${error.message}</p>
            </div>
        `;
    }
}

function searchMtoCatalog() {
    const query = document.getElementById('mtoCatalogSearch').value.toLowerCase();
    const grid = document.getElementById('mtoCatalogGrid');
    const filtered = mtoProducts.filter(p => p.name.toLowerCase().includes(query));
    
    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <h3>ไม่พบสินค้า</h3>
                <p>ลองค้นหาด้วยคำอื่น</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = filtered.map(product => `
        <div class="mto-product-card">
            <img src="${product.image_url || '/static/images/placeholder.png'}" alt="${product.name}" class="mto-product-image" onerror="this.src='/static/images/placeholder.png'">
            <div class="mto-product-info">
                <div class="mto-product-name">${product.name}</div>
                <div class="mto-product-meta">
                    <span>${product.production_days || 14} วันผลิต</span>
                    <span>ขั้นต่ำ ${product.min_order_qty || 10} ชิ้น</span>
                </div>
                <div class="mto-product-actions">
                    <button class="btn-request-quote" onclick="openMtoRequestModal(${product.id})">ขอใบเสนอราคา</button>
                </div>
            </div>
        </div>
    `).join('');
}

function switchMtoTab(tabName) {
    document.querySelectorAll('.mto-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    
    document.querySelectorAll('.mto-tab-content').forEach(content => {
        const isActive = content.id === `mto-tab-${tabName}`;
        content.classList.toggle('active', isActive);
        content.style.display = isActive ? 'block' : 'none';
    });
    
    if (tabName === 'quotes') loadResellerMtoQuotes();
    if (tabName === 'mto-orders') loadResellerMtoOrders();
}

async function openMtoRequestModal(productId) {
    const product = mtoProducts.find(p => p.id === productId);
    if (!product) return;
    
    document.getElementById('mtoProductId').value = productId;
    document.getElementById('mtoPreviewImage').src = product.image_url || '/static/images/placeholder.png';
    document.getElementById('mtoPreviewName').textContent = product.name;
    document.getElementById('mtoPreviewMeta').textContent = `${product.production_days || 14} วันผลิต | มัดจำ ${product.deposit_percent || 50}%`;
    
    // Reset matrix items
    window.mtoMatrixItems = [];
    window.mtoHasMinQtyError = false;
    
    // Load product details with options for Matrix Grid
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/products/${productId}/details`);
        if (response.ok) {
            const data = await response.json();
            const container = document.getElementById('mtoSkuSelection');
            
            if (data.options && data.options.length > 0) {
                container.innerHTML = renderMtoMatrixGrid(data);
            } else {
                container.innerHTML = `
                    <div class="form-group">
                        <label>จำนวนที่ต้องการ *</label>
                        <input type="number" id="mtoRequestQty" min="${product.min_order_qty || 1}" value="${product.min_order_qty || 10}" required>
                    </div>
                `;
            }
        } else {
            // Fallback to simple quantity input
            const container = document.getElementById('mtoSkuSelection');
            container.innerHTML = `
                <div class="form-group">
                    <label>จำนวนที่ต้องการ *</label>
                    <input type="number" id="mtoRequestQty" min="${product.min_order_qty || 1}" value="${product.min_order_qty || 10}" required>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading product details:', error);
        const container = document.getElementById('mtoSkuSelection');
        container.innerHTML = `
            <div class="form-group">
                <label>จำนวนที่ต้องการ *</label>
                <input type="number" id="mtoRequestQty" min="${product.min_order_qty || 1}" value="${product.min_order_qty || 10}" required>
            </div>
        `;
    }
    
    document.getElementById('mtoRequestNotes').value = '';
    document.getElementById('mtoRequestModal').classList.add('active');
}

function renderMtoMatrixGrid(data) {
    const options = data.options || [];
    const skus = data.skus || [];
    
    if (options.length === 0) return '<p style="color: rgba(255,255,255,0.5);">ไม่มีตัวเลือกสินค้า</p>';
    
    const primaryOption = options[0];
    const primaryValues = primaryOption.values || [];
    
    if (options.length === 1) {
        return `
            <div class="mto-matrix-wrapper">
                <div class="mto-matrix-info" style="margin-bottom: 12px; padding: 10px; background: rgba(168,85,247,0.15); border-radius: 8px; font-size: 12px; color: rgba(255,255,255,0.9);">
                    <strong>${primaryOption.name}:</strong> แต่ละค่าต้องมีจำนวนขั้นต่ำตามที่กำหนด
                </div>
                <table class="mto-matrix-table" style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr>
                            <th style="text-align: left; padding: 10px; background: rgba(0,0,0,0.3); color: white;">${primaryOption.name}</th>
                            <th style="text-align: center; padding: 10px; background: rgba(0,0,0,0.3); color: white; width: 70px;">ขั้นต่ำ</th>
                            <th style="text-align: center; padding: 10px; background: rgba(0,0,0,0.3); color: white; width: 90px;">จำนวน</th>
                            <th style="text-align: center; padding: 10px; background: rgba(0,0,0,0.3); color: white;">ราคา/ชิ้น</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${primaryValues.map(val => {
                            const sku = skus.find(s => s.option_values && s.option_values.some(ov => ov.id === val.id));
                            const skuId = sku ? sku.id : 0;
                            const price = sku ? sku.price : 0;
                            return `
                                <tr data-primary-value="${val.id}">
                                    <td style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); color: white;">${val.value}</td>
                                    <td style="padding: 10px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.7); font-size: 12px;" data-min-qty="${val.min_order_qty || 1}">${val.min_order_qty || 1}</td>
                                    <td style="padding: 10px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1);">
                                        <input type="number" class="mto-qty-input" data-sku-id="${skuId}" data-primary-value="${val.id}" min="0" value="0" oninput="updateMtoMatrixSummary()" style="width: 70px; padding: 6px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; color: white; text-align: center;">
                                    </td>
                                    <td style="padding: 10px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.7);">${formatNumber(price)} ฿</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
                <div id="mtoMatrixSummary" class="mto-matrix-summary" style="margin-top: 16px; padding: 12px; background: rgba(0,0,0,0.3); border-radius: 8px;"></div>
            </div>
        `;
    }
    
    const secondaryOption = options[1];
    const secondaryValues = secondaryOption.values || [];
    
    let html = `
        <div class="mto-matrix-wrapper" style="overflow-x: auto;">
            <div class="mto-matrix-info" style="margin-bottom: 12px; padding: 10px; background: rgba(168,85,247,0.15); border-radius: 8px; font-size: 12px; color: rgba(255,255,255,0.9);">
                <strong>${primaryOption.name}:</strong> แต่ละ${primaryOption.name}ต้องมีจำนวนรวมขั้นต่ำตามคอลัมน์ "ขั้นต่ำ"
            </div>
            <table class="mto-matrix-table" style="width: 100%; border-collapse: collapse; min-width: 400px;">
                <thead>
                    <tr>
                        <th style="text-align: left; padding: 10px; background: rgba(0,0,0,0.3); color: white;">${primaryOption.name}</th>
                        <th style="text-align: center; padding: 10px; background: rgba(0,0,0,0.3); color: rgba(255,255,255,0.7); font-size: 11px; width: 50px;">ขั้นต่ำ</th>
                        ${secondaryValues.map(sv => `
                            <th style="text-align: center; padding: 10px; background: rgba(0,0,0,0.3); color: white; font-size: 12px;">${sv.value}</th>
                        `).join('')}
                        <th style="text-align: center; padding: 10px; background: rgba(168,85,247,0.2); color: #a855f7; font-size: 12px; width: 60px;">รวม</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    primaryValues.forEach(pv => {
        html += `
            <tr data-primary-value="${pv.id}">
                <td style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); color: white; font-weight: 500;">${pv.value}</td>
                <td style="padding: 10px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); font-size: 11px;" data-min-qty="${pv.min_order_qty || 1}">${pv.min_order_qty || 1}</td>
        `;
        
        secondaryValues.forEach(sv => {
            const sku = skus.find(s => {
                if (!s.option_values) return false;
                return s.option_values.some(ov => ov.id === pv.id) && s.option_values.some(ov => ov.id === sv.id);
            });
            const skuId = sku ? sku.id : 0;
            
            html += `
                <td style="padding: 6px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <input type="number" class="mto-qty-input" data-sku-id="${skuId}" data-primary-value="${pv.id}" data-secondary-value="${sv.id}" min="0" value="0" oninput="updateMtoMatrixSummary()" style="width: 50px; padding: 6px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; color: white; text-align: center; font-size: 13px;">
                </td>
            `;
        });
        
        html += `
                <td class="row-total" style="padding: 10px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(168,85,247,0.1); color: #a855f7; font-weight: 600;" data-row="${pv.id}">0</td>
            </tr>
        `;
    });
    
    html += `
                </tbody>
            </table>
            <div id="mtoMatrixSummary" class="mto-matrix-summary" style="margin-top: 16px; padding: 12px; background: rgba(0,0,0,0.3); border-radius: 8px;"></div>
        </div>
    `;
    
    return html;
}

function updateMtoMatrixSummary() {
    const inputs = document.querySelectorAll('.mto-qty-input');
    const primaryTotals = {};
    let grandTotal = 0;
    const skuItems = [];
    let hasMinQtyError = false;
    
    inputs.forEach(input => {
        const qty = parseInt(input.value) || 0;
        const skuId = input.dataset.skuId;
        const primaryValue = input.dataset.primaryValue;
        
        if (!primaryTotals[primaryValue]) {
            primaryTotals[primaryValue] = { total: 0, minQty: 0 };
        }
        primaryTotals[primaryValue].total += qty;
        grandTotal += qty;
        
        if (qty > 0 && skuId && skuId !== '0') {
            skuItems.push({ sku_id: parseInt(skuId), quantity: qty });
        }
    });
    
    document.querySelectorAll('.row-total').forEach(cell => {
        const rowId = cell.dataset.row;
        if (primaryTotals[rowId]) {
            cell.textContent = primaryTotals[rowId].total;
        }
    });
    
    const minQtyCells = document.querySelectorAll('[data-min-qty]');
    let errors = [];
    
    minQtyCells.forEach(cell => {
        const row = cell.closest('tr');
        const primaryValue = row.dataset.primaryValue;
        const minQty = parseInt(cell.dataset.minQty) || 1;
        const rowTotal = primaryTotals[primaryValue]?.total || 0;
        
        if (rowTotal > 0 && rowTotal < minQty) {
            hasMinQtyError = true;
            const rowLabel = row.querySelector('td:first-child')?.textContent || primaryValue;
            errors.push(`${rowLabel}: ต้องมีอย่างน้อย ${minQty} ชิ้น (ปัจจุบัน ${rowTotal})`);
            row.style.background = 'rgba(239,68,68,0.15)';
        } else {
            row.style.background = '';
        }
    });
    
    const summaryDiv = document.getElementById('mtoMatrixSummary');
    if (summaryDiv) {
        let summaryHtml = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: rgba(255,255,255,0.7);">จำนวนรวม:</span>
                <span style="color: white; font-size: 18px; font-weight: 600;">${grandTotal} ชิ้น</span>
            </div>
        `;
        
        if (errors.length > 0) {
            summaryHtml += `
                <div style="margin-top: 10px; padding: 10px; background: rgba(239,68,68,0.2); border-radius: 6px; border: 1px solid rgba(239,68,68,0.4);">
                    <div style="color: #f87171; font-size: 12px; margin-bottom: 4px; font-weight: 500;">ไม่ถึงขั้นต่ำ:</div>
                    ${errors.map(e => `<div style="color: rgba(255,255,255,0.8); font-size: 11px;">• ${e}</div>`).join('')}
                </div>
            `;
        }
        
        summaryDiv.innerHTML = summaryHtml;
    }
    
    window.mtoMatrixItems = skuItems;
    window.mtoHasMinQtyError = hasMinQtyError;
}

function closeMtoRequestModal() {
    document.getElementById('mtoRequestModal').classList.remove('active');
}

async function handleSubmitMtoRequest(event) {
    event.preventDefault();
    
    const productId = document.getElementById('mtoProductId').value;
    const notes = document.getElementById('mtoRequestNotes').value;
    
    // Check for min quantity errors
    if (window.mtoHasMinQtyError) {
        showAlert('จำนวนไม่ถึงขั้นต่ำ กรุณาตรวจสอบใหม่', 'error');
        return;
    }
    
    // Collect items from matrix or simple input
    let items = [];
    
    if (window.mtoMatrixItems && window.mtoMatrixItems.length > 0) {
        items = window.mtoMatrixItems;
    } else {
        const qtyInput = document.getElementById('mtoRequestQty');
        if (qtyInput) {
            items.push({ quantity: parseInt(qtyInput.value) || 1 });
        }
    }
    
    if (items.length === 0) {
        showAlert('กรุณาระบุจำนวนอย่างน้อย 1 รายการ', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/quotation-requests`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_id: parseInt(productId),
                items: items,
                notes: notes
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to submit request');
        }
        
        showAlert('ส่งคำขอใบเสนอราคาเรียบร้อยแล้ว', 'success');
        closeMtoRequestModal();
        switchMtoTab('quotes');
    } catch (error) {
        showAlert(error.message, 'error');
    }
}

async function loadResellerMtoQuotes() {
    const container = document.getElementById('mtoQuotesList');
    try {
        let url = `${RESELLER_API_URL}/reseller/mto/quotations`;
        if (currentMtoQuoteFilter !== 'all') {
            url += `?status=${currentMtoQuoteFilter}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load quotes');
        
        mtoQuotes = await response.json();
        
        // Update badge
        const pendingCount = mtoQuotes.filter(q => q.status === 'quoted').length;
        const badge = document.getElementById('quotesBadge');
        if (pendingCount > 0) {
            badge.textContent = pendingCount;
            badge.style.display = 'inline';
        } else {
            badge.style.display = 'none';
        }
        
        if (mtoQuotes.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path></svg>
                    <h3>ไม่มีใบเสนอราคา</h3>
                    <p>เลือกสินค้าจากแคตตาล็อกเพื่อขอใบเสนอราคา</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = mtoQuotes.map(quote => `
            <div class="mto-quote-card">
                <div class="mto-card-header">
                    <div>
                        <div class="mto-card-title">${quote.product_name}</div>
                        <div class="mto-card-date">${formatDate(quote.created_at)}</div>
                    </div>
                    <span class="mto-status-badge mto-status-${quote.status}">${getMtoQuoteStatusText(quote.status)}</span>
                </div>
                <div class="mto-card-items">
                    ${(quote.items || []).map(item => `
                        <div class="mto-card-item">
                            <span>${item.sku_code || 'ไม่ระบุ'} ${item.variant_name ? `(${item.variant_name})` : ''}</span>
                            <span>x ${item.quantity}</span>
                        </div>
                    `).join('')}
                    ${quote.total_amount ? `
                        <div class="mto-card-summary">
                            <span>รวมทั้งสิ้น</span>
                            <span>฿${formatNumber(quote.total_amount)}</span>
                        </div>
                    ` : ''}
                </div>
                <div class="mto-card-actions">
                    ${quote.status === 'quoted' ? `
                        <button class="btn-mto-action btn-mto-primary" onclick="acceptMtoQuote(${quote.id})">ตอบรับใบเสนอราคา</button>
                        <button class="btn-mto-action btn-mto-danger" onclick="rejectMtoQuote(${quote.id})">ปฏิเสธ</button>
                    ` : quote.status === 'pending' ? `
                        <button class="btn-mto-action btn-mto-secondary" disabled>รอใบเสนอราคา...</button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading quotes:', error);
        container.innerHTML = `<div class="empty-state"><h3>เกิดข้อผิดพลาด</h3><p>${error.message}</p></div>`;
    }
}

function filterResellerMtoQuotes(status) {
    currentMtoQuoteFilter = status;
    document.querySelectorAll('#mto-tab-quotes .filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === status);
    });
    loadResellerMtoQuotes();
}

async function acceptMtoQuote(quoteId) {
    if (!confirm('ยืนยันการตอบรับใบเสนอราคานี้?')) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/quotations/${quoteId}/accept`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to accept quote');
        }
        
        showAlert('ตอบรับใบเสนอราคาเรียบร้อย กรุณาชำระเงินมัดจำ', 'success');
        loadResellerMtoQuotes();
        switchMtoTab('mto-orders');
    } catch (error) {
        showAlert(error.message, 'error');
    }
}

async function rejectMtoQuote(quoteId) {
    if (!confirm('ยืนยันการปฏิเสธใบเสนอราคานี้?')) return;
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/quotations/${quoteId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error('Failed to reject quote');
        
        showAlert('ปฏิเสธใบเสนอราคาแล้ว', 'info');
        loadResellerMtoQuotes();
    } catch (error) {
        showAlert(error.message, 'error');
    }
}

async function loadResellerMtoOrders() {
    const container = document.getElementById('resellerMtoOrdersList');
    try {
        let url = `${RESELLER_API_URL}/reseller/mto/orders`;
        if (currentMtoOrderFilter !== 'all') {
            url += `?status=${currentMtoOrderFilter}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load orders');
        
        mtoOrders = await response.json();
        
        // Update badges
        const actionNeeded = mtoOrders.filter(o => ['awaiting_deposit', 'balance_requested'].includes(o.status)).length;
        const tabBadge = document.getElementById('mtoOrdersBadgeTab');
        const navBadge = document.getElementById('mtoOrdersBadge');
        
        [tabBadge, navBadge].forEach(badge => {
            if (badge) {
                if (actionNeeded > 0) {
                    badge.textContent = actionNeeded;
                    badge.style.display = 'inline';
                } else {
                    badge.style.display = 'none';
                }
            }
        });
        
        if (mtoOrders.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                    <h3>ยังไม่มีออเดอร์สั่งผลิต</h3>
                    <p>ตอบรับใบเสนอราคาเพื่อเริ่มกระบวนการผลิต</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = mtoOrders.map(order => {
            let progressPercent = 0;
            let progressText = '';
            
            if (order.status === 'production' && order.expected_completion_date) {
                const start = new Date(order.payment_confirmed_at);
                const end = new Date(order.expected_completion_date);
                const now = new Date();
                const total = end - start;
                const elapsed = now - start;
                progressPercent = Math.min(100, Math.max(0, (elapsed / total) * 100));
                const daysLeft = Math.ceil((end - now) / (1000 * 60 * 60 * 24));
                progressText = daysLeft > 0 ? `เหลืออีก ${daysLeft} วัน` : 'ใกล้เสร็จ';
            }
            
            return `
                <div class="mto-order-card">
                    <div class="mto-card-header">
                        <div>
                            <div class="mto-card-title">${order.mto_order_number || `MTO-${order.id}`}</div>
                            <div class="mto-card-date">${order.product_name}</div>
                        </div>
                        <span class="mto-status-badge mto-status-${order.status}">${getMtoOrderStatusText(order.status)}</span>
                    </div>
                    
                    ${order.status === 'production' ? `
                        <div class="mto-progress">
                            <div class="mto-progress-bar">
                                <div class="mto-progress-fill" style="width: ${progressPercent}%;"></div>
                            </div>
                            <div class="mto-progress-text">
                                <span>กำลังผลิต</span>
                                <span>${progressText}</span>
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="mto-card-items">
                        <div class="mto-card-item">
                            <span>ยอดรวม</span>
                            <span>฿${formatNumber(order.total_amount || 0)}</span>
                        </div>
                        <div class="mto-card-item">
                            <span>มัดจำ (${order.deposit_percent || 50}%)</span>
                            <span style="color: ${order.deposit_paid ? '#22c55e' : '#ffffff'}">
                                ฿${formatNumber(order.deposit_amount || 0)} ${order.deposit_paid ? '✓' : '(รอชำระ)'}
                            </span>
                        </div>
                        <div class="mto-card-item">
                            <span>ยอดคงเหลือ</span>
                            <span style="color: ${order.balance_paid ? '#22c55e' : 'rgba(255,255,255,0.7)'}">
                                ฿${formatNumber(order.balance_amount || 0)} ${order.balance_paid ? '✓' : ''}
                            </span>
                        </div>
                    </div>
                    
                    <div class="mto-card-actions">
                        ${order.status === 'awaiting_deposit' ? `
                            <button class="btn-mto-action btn-mto-primary" onclick="openMtoPayment(${order.id}, 'deposit', ${order.deposit_amount})">ชำระมัดจำ</button>
                        ` : order.status === 'balance_requested' ? `
                            <button class="btn-mto-action btn-mto-primary" onclick="openMtoPayment(${order.id}, 'balance', ${order.balance_amount})">ชำระยอดเหลือ</button>
                        ` : ''}
                        <button class="btn-mto-action btn-mto-secondary" onclick="viewMtoOrderDetail(${order.id})">ดูรายละเอียด</button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading orders:', error);
        container.innerHTML = `<div class="empty-state"><h3>เกิดข้อผิดพลาด</h3><p>${error.message}</p></div>`;
    }
}

function filterResellerMtoOrders(status) {
    currentMtoOrderFilter = status;
    document.querySelectorAll('#mto-tab-mto-orders .filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === status);
    });
    loadResellerMtoOrders();
}

async function openMtoPayment(orderId, paymentType, amount) {
    document.getElementById('mtoPaymentOrderId').value = orderId;
    document.getElementById('mtoPaymentType').value = paymentType;
    document.getElementById('mtoPaymentTitle').textContent = paymentType === 'deposit' ? 'ชำระมัดจำ' : 'ชำระยอดเหลือ';
    document.getElementById('mtoPaymentAmount').textContent = `฿${formatNumber(amount)}`;
    
    // Generate QR code
    const qrContainer = document.getElementById('mtoQrCode');
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/orders/${orderId}/qr-code?payment_type=${paymentType}`);
        if (response.ok) {
            const data = await response.json();
            qrContainer.innerHTML = `<img src="${data.qr_code}" alt="PromptPay QR" style="max-width: 200px;">`;
        } else {
            qrContainer.innerHTML = '<p style="color: #666;">ไม่สามารถสร้าง QR Code ได้</p>';
        }
    } catch (error) {
        qrContainer.innerHTML = '<p style="color: #666;">กรุณาโอนเงินตามรายละเอียดที่แจ้ง</p>';
    }
    
    document.getElementById('mtoPaymentSlip').value = '';
    document.getElementById('mtoPaymentModal').classList.add('active');
}

function closeMtoPaymentModal() {
    document.getElementById('mtoPaymentModal').classList.remove('active');
}

async function handleSubmitMtoPayment(event) {
    event.preventDefault();
    
    const orderId = document.getElementById('mtoPaymentOrderId').value;
    const paymentType = document.getElementById('mtoPaymentType').value;
    const slipFile = document.getElementById('mtoPaymentSlip').files[0];
    
    if (!slipFile) {
        showAlert('กรุณาอัปโหลดหลักฐานการโอน', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('payment_type', paymentType);
    formData.append('slip', slipFile);
    
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/mto/orders/${orderId}/payment`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to submit payment');
        }
        
        showAlert('อัปโหลดหลักฐานการชำระเงินเรียบร้อย รอการตรวจสอบ', 'success');
        closeMtoPaymentModal();
        loadResellerMtoOrders();
    } catch (error) {
        showAlert(error.message, 'error');
    }
}

async function viewMtoOrderDetail(orderId) {
    const order = mtoOrders.find(o => o.id === orderId);
    if (!order) return;
    
    const content = document.getElementById('mtoOrderDetailContent');
    content.innerHTML = `
        <div style="padding: 20px; background: rgba(0,0,0,0.2); border-radius: 12px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; color: white;">${order.mto_order_number || `MTO-${order.id}`}</h3>
                <span class="mto-status-badge mto-status-${order.status}">${getMtoOrderStatusText(order.status)}</span>
            </div>
            <p style="color: rgba(255,255,255,0.7); margin: 0;">สินค้า: ${order.product_name}</p>
        </div>
        
        <div class="mto-timeline" style="padding: 20px;">
            ${getMtoOrderTimeline(order)}
        </div>
        
        <div style="padding: 20px; background: rgba(0,0,0,0.2); border-radius: 12px;">
            <h4 style="margin: 0 0 12px 0; color: white;">สรุปยอดเงิน</h4>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <span style="color: rgba(255,255,255,0.7);">ยอดรวมทั้งหมด</span>
                <span style="color: white; font-weight: 600;">฿${formatNumber(order.total_amount || 0)}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <span style="color: rgba(255,255,255,0.7);">มัดจำ (${order.deposit_percent || 50}%)</span>
                <span style="color: ${order.deposit_paid ? '#22c55e' : '#ffffff'};">
                    ฿${formatNumber(order.deposit_amount || 0)} ${order.deposit_paid ? '✓ ชำระแล้ว' : ''}
                </span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0;">
                <span style="color: rgba(255,255,255,0.7);">ยอดคงเหลือ</span>
                <span style="color: ${order.balance_paid ? '#22c55e' : 'rgba(255,255,255,0.7)'};">
                    ฿${formatNumber(order.balance_amount || 0)} ${order.balance_paid ? '✓ ชำระแล้ว' : ''}
                </span>
            </div>
        </div>
    `;
    
    document.getElementById('mtoOrderDetailModal').classList.add('active');
}

function closeMtoOrderDetailModal() {
    document.getElementById('mtoOrderDetailModal').classList.remove('active');
}

function getMtoOrderTimeline(order) {
    const steps = [
        { key: 'created', label: 'สร้างคำสั่งซื้อ', date: order.created_at },
        { key: 'deposit', label: 'ชำระมัดจำ', date: order.deposit_paid ? order.deposit_paid_at : null },
        { key: 'production', label: 'เริ่มผลิต', date: order.production_started_at },
        { key: 'balance', label: 'ชำระยอดเหลือ', date: order.balance_paid ? order.balance_paid_at : null },
        { key: 'shipped', label: 'จัดส่ง', date: order.shipped_at },
        { key: 'fulfilled', label: 'เสร็จสิ้น', date: order.fulfilled_at }
    ];
    
    return steps.map((step, index) => `
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
            <div style="width: 24px; height: 24px; border-radius: 50%; background: ${step.date ? 'var(--primary)' : 'rgba(255,255,255,0.2)'}; display: flex; align-items: center; justify-content: center;">
                ${step.date ? '✓' : index + 1}
            </div>
            <div>
                <div style="color: ${step.date ? 'white' : 'rgba(255,255,255,0.5)'}; font-weight: 500;">${step.label}</div>
                <div style="font-size: 12px; color: rgba(255,255,255,0.5);">${step.date ? formatDate(step.date) : '-'}</div>
            </div>
        </div>
    `).join('');
}

function getMtoQuoteStatusText(status) {
    const statusMap = {
        'pending': 'รอใบเสนอราคา',
        'quoted': 'ได้รับใบเสนอราคา',
        'accepted': 'ตอบรับแล้ว',
        'rejected': 'ปฏิเสธ',
        'expired': 'หมดอายุ'
    };
    return statusMap[status] || status;
}

function getMtoOrderStatusText(status) {
    const statusMap = {
        'awaiting_deposit': 'รอชำระมัดจำ',
        'deposit_pending': 'รอตรวจสอบมัดจำ',
        'deposit_paid': 'ชำระมัดจำแล้ว',
        'production': 'กำลังผลิต',
        'balance_requested': 'รอชำระยอดเหลือ',
        'balance_pending': 'รอตรวจสอบยอดเหลือ',
        'balance_paid': 'ชำระยอดเหลือแล้ว',
        'ready_to_ship': 'พร้อมจัดส่ง',
        'shipped': 'จัดส่งแล้ว',
        'fulfilled': 'เสร็จสิ้น',
        'cancelled': 'ยกเลิก'
    };
    return statusMap[status] || status;
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatNumber(num) {
    return new Intl.NumberFormat('th-TH').format(num || 0);
}

// ==================== RESELLER CHAT SYSTEM ====================

let resellerChatThreadId = null;
let resellerChatPollingInterval = null;
let resellerLastMessageId = 0;
let resellerPendingAttachments = [];
let resellerOldestMessageId = 0;
let resellerHasMoreMessages = true;
let resellerLoadingOlder = false;
let resellerAllMessages = [];
let resellerMsgLoading = false;

async function initResellerChat() {
    try {
        resellerLastMessageId = 0;
        resellerOldestMessageId = 0;
        resellerHasMoreMessages = true;
        resellerLoadingOlder = false;
        resellerAllMessages = [];
        resellerChatOtherLastRead = 0;

        const container = document.getElementById('resellerChatMessages');
        if (container) {
            container.innerHTML = '';
            delete container.dataset.scrollSetup;
        }

        const response = await fetch(`/api/chat/start/${currentUserId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });
        const data = await response.json();
        
        if (response.ok) {
            resellerChatThreadId = data.thread_id;
            await loadResellerChatMessages();
            startResellerChatPolling();
            loadResellerBotStatus();
        }
    } catch (error) {
        console.error('Error initializing chat:', error);
    }
}

async function loadResellerBotStatus() {
    if (!resellerChatThreadId) return;
    try {
        const res = await fetch(`/api/chat/threads/${resellerChatThreadId}/bot-status`, { credentials: 'include' });
        if (!res.ok) return;
        const data = await res.json();
        const badge = document.getElementById('resellerBotStatusBadge');
        const dot   = document.getElementById('resellerBotStatusDot');
        const text  = document.getElementById('resellerBotStatusText');
        if (!badge) return;
        if (data.status === 'active') {
            dot.style.background  = '#4ade80';
            text.textContent      = `🤖 ${data.bot_name || 'บอท'}: ออนไลน์`;
        } else if (data.status === 'paused') {
            dot.style.background  = '#f59e0b';
            text.textContent      = `🤖 ${data.bot_name || 'บอท'}: พักชั่วคราว`;
        } else {
            dot.style.background  = '#6b7280';
            text.textContent      = `🤖 ${data.bot_name || 'บอท'}: ปิดอยู่`;
        }
        badge.style.display = 'flex';
    } catch (_) {}
}

async function loadResellerChatMessages() {
    if (!resellerChatThreadId) return;
    if (resellerMsgLoading) return;
    resellerMsgLoading = true;
    
    try {
        const container = document.getElementById('resellerChatMessages');
        if (!container) return;

        if (resellerLastMessageId === 0) {
            const response = await fetch(`/api/chat/threads/${resellerChatThreadId}/messages?limit=50`, {
                credentials: 'include'
            });
            const data = await response.json();
            const messages = data.messages || data;
            resellerHasMoreMessages = data.has_more || false;
            resellerChatOtherLastRead = data.other_last_read || 0;

            if (messages.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px; color: rgba(255,255,255,0.4);">
                        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 16px; opacity: 0.3;">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                        </svg>
                        <p>ยังไม่มีข้อความ</p>
                        <p style="font-size: 13px; margin-top: 8px;">เริ่มสนทนากับแอดมินได้เลย!</p>
                    </div>
                `;
                return;
            }

            resellerAllMessages = messages;
            resellerOldestMessageId = messages[0].id;
            messages.forEach(msg => {
                resellerLastMessageId = Math.max(resellerLastMessageId, msg.id);
            });

            renderResellerAllMessages();
            container.scrollTop = container.scrollHeight;
            setupResellerChatScroll();
        } else {
            const response = await fetch(`/api/chat/threads/${resellerChatThreadId}/messages?since_id=${resellerLastMessageId}`, {
                credentials: 'include'
            });
            const data = await response.json();
            const messages = data.messages || data;
            resellerChatOtherLastRead = data.other_last_read || 0;

            if (messages.length === 0) {
                updateResellerReadReceipts();
                return;
            }

            const hasIncoming = messages.some(m => Number(m.sender_id) !== Number(currentUserId));
            if (hasIncoming) cancelBotTypingIndicator();

            messages.forEach(msg => {
                resellerAllMessages.push(msg);
                const isMine = Number(msg.sender_id) === Number(currentUserId);
                const isRead = isMine && msg.id <= resellerChatOtherLastRead;

                const lastMsg = resellerAllMessages.length >= 2 ? resellerAllMessages[resellerAllMessages.length - 2] : null;
                const msgDate = new Date(msg.created_at).toDateString();
                const lastDate = lastMsg ? new Date(lastMsg.created_at).toDateString() : null;
                if (!lastDate || msgDate !== lastDate) {
                    const dateLabel = formatResellerChatDateSeparator(msg.created_at);
                    container.insertAdjacentHTML('beforeend', `
                        <div style="display: flex; align-items: center; gap: 12px; margin: 16px 0;">
                            <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
                            <div style="font-size: 12px; color: rgba(255,255,255,0.4); white-space: nowrap;">${dateLabel}</div>
                            <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
                        </div>
                    `);
                }

                container.insertAdjacentHTML('beforeend', buildResellerMessageHtml(msg, isMine, isRead));
                resellerLastMessageId = Math.max(resellerLastMessageId, msg.id);
            });

            updateResellerReadReceipts();
            container.scrollTop = container.scrollHeight;
        }
    } catch (error) {
        console.error('Error loading messages:', error);
    } finally {
        resellerMsgLoading = false;
    }
}

let resellerChatOtherLastRead = 0;

function buildResellerMessageHtml(msg, isMine, isRead) {
    let orderCardHtml = '';
    if (msg.order) {
        const o = msg.order;
        const statusLabels = {
            'pending_payment': 'รอชำระเงิน', 'under_review': 'รอตรวจสอบ',
            'preparing': 'เตรียมสินค้า', 'shipped': 'กำลังจัดส่ง',
            'delivered': 'ได้รับสินค้าแล้ว', 'failed_delivery': 'จัดส่งไม่สำเร็จ',
            'cancelled': 'ยกเลิก'
        };
        const statusColors = {
            'pending_payment': '#f59e0b', 'under_review': '#3b82f6',
            'preparing': '#8b5cf6', 'shipped': '#0ea5e9',
            'delivered': '#10b981', 'failed_delivery': '#ef4444',
            'cancelled': '#6b7280'
        };
        const fmtN = n => Number(n || 0).toLocaleString('th-TH');
        const items = Array.isArray(o.items) ? o.items.filter(it => it && it.product_name) : [];
        const displayItems = items;
        const moreCount = 0;
        const shipping = o.shipping_fee || 0;
        const grandTotal = o.final_amount || 0;

        const itemsListHtml = displayItems.map(it => `
            <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.07);">
                ${it.image_url
                    ? `<img src="${escapeHtmlChat(it.image_url)}" style="width:36px;height:36px;border-radius:6px;object-fit:cover;flex-shrink:0;" onerror="this.style.display='none'">`
                    : `<div style="width:36px;height:36px;border-radius:6px;background:rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:16px;">📦</div>`}
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtmlChat(it.product_name)}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.5);">x${it.quantity} &nbsp;·&nbsp; ฿${fmtN(it.subtotal)}</div>
                </div>
            </div>
        `).join('');

        orderCardHtml = `
            <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; overflow: hidden; margin-bottom: ${msg.content ? '8px' : '0'}; cursor: pointer; min-width: 240px; max-width: 280px;" onclick="viewResellerOrderDetails(${o.id})">
                <div style="padding: 10px 12px 0; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 13px; font-weight: 700;">${escapeHtmlChat(o.order_number || '#' + o.id)}</span>
                    <span style="background: ${statusColors[o.status] || '#6b7280'}; color: white; padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 600;">${statusLabels[o.status] || o.status}</span>
                </div>
                <div style="padding: 8px 12px;">
                    ${itemsListHtml}
                    ${moreCount > 0 ? `<div style="font-size:11px;color:rgba(255,255,255,0.4);padding-top:4px;">+${moreCount} รายการอื่น...</div>` : ''}
                </div>
                <div style="padding: 0 12px 10px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; margin-top: 2px;">
                    ${o.discount_amount > 0 ? `<div style="display:flex;justify-content:space-between;font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:2px;"><span>ส่วนลด</span><span style="color:#34d399;">-฿${fmtN(o.discount_amount)}</span></div>` : ''}
                    <div style="display:flex;justify-content:space-between;font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px;">
                        <span>ค่าจัดส่ง</span>
                        <span>${shipping > 0 ? `฿${fmtN(shipping)}` : '<span style="color:#34d399;">ฟรี</span>'}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700;">
                        <span>ยอดรวม</span>
                        <span style="color:#ffffff;">฿${fmtN(grandTotal)}</span>
                    </div>
                </div>
                <div style="background: rgba(168,85,247,0.15); padding: 7px 12px; text-align: center; font-size: 11px; color: rgba(255,255,255,0.6);">กดเพื่อดูรายละเอียด →</div>
            </div>
        `;
    }

    let productCardHtml = '';
    if (msg.product) {
        const p = msg.product;
        const hasDiscount = p.discount_percent && p.discount_percent > 0;
        const fmtNum = (n) => n != null ? Number(n).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2}) : '0';
        const tierPrice = hasDiscount ? (p.tier_min_price === p.tier_max_price ? `฿${fmtNum(p.tier_min_price)}` : `฿${fmtNum(p.tier_min_price)} - ฿${fmtNum(p.tier_max_price)}`) : '';
        const originalPrice = p.min_price === p.max_price ? `฿${fmtNum(p.min_price)}` : `฿${fmtNum(p.min_price)} - ฿${fmtNum(p.max_price)}`;
        productCardHtml = `
            <div style="background: rgba(255,255,255,0.08); border-radius: 10px; overflow: hidden; margin-bottom: ${msg.content ? '8px' : '0'}; border: 1px solid rgba(255,255,255,0.1); cursor: pointer; -webkit-transform: translateZ(0); transform: translateZ(0); width: 220px; max-width: 100%;" onclick="viewProduct(${p.id})">
                <div style="position:relative;">
                    ${p.image_url ? `<img src="${p.image_url}" style="width: 100%; max-height: 200px; object-fit: contain; display: block; background: rgba(0,0,0,0.15);" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
                    <div style="height:80px;background:rgba(255,255,255,0.05);display:${p.image_url ? 'none' : 'flex'};align-items:center;justify-content:center;font-size:28px;">📦</div>
                </div>
                <div style="padding: 10px;">
                    <div style="font-size: 13px; font-weight: 600; margin-bottom: 4px;">${escapeHtmlChat(p.name)}</div>
                    ${hasDiscount ? `
                        <div style="font-size: 14px; font-weight: 700; color: #ffffff;">${tierPrice}</div>
                        <div style="font-size: 11px; text-decoration: line-through; opacity: 0.5;">${originalPrice}</div>
                        <div style="font-size: 10px; color: #34d399; margin-top: 2px;">ส่วนลด ${p.discount_percent}%</div>
                    ` : `<div style="font-size: 14px; font-weight: 700; color: #ffffff;">${originalPrice}</div>`}
                </div>
            </div>
        `;
    }

    let couponCardHtml = '';
    if (msg.coupon) {
        const c = msg.coupon;
        const fmtDisc = c.discount_type === 'percent'
            ? `ลด ${c.discount_value}%${c.max_discount ? ` (สูงสุด ฿${Number(c.max_discount).toLocaleString('th-TH')})` : ''}`
            : c.discount_type === 'free_shipping' ? 'ฟรีค่าจัดส่ง'
            : `ลด ฿${Number(c.discount_value).toLocaleString('th-TH')}`;
        const couponNote = isMine
            ? '<div style="font-size:11px;color:#38ef7d;margin-top:6px;font-weight:600;">✓ ส่งคูปองให้ Admin แล้ว</div>'
            : '<div style="font-size:11px;color:#38ef7d;margin-top:6px;font-weight:600;">✓ คูปองถูกเพิ่มเข้า wallet ของคุณแล้ว</div>';
        couponCardHtml = `
            <div style="width:100%;border-radius:14px;overflow:hidden;">
                <div style="background:linear-gradient(135deg,#11998e,#38ef7d);padding:12px 16px 10px;">
                    <div style="font-size:10px;color:rgba(255,255,255,0.75);letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">คูปองส่วนลด</div>
                    <div style="font-size:20px;font-weight:800;color:#fff;letter-spacing:2px;word-break:break-all;">${escapeHtmlChat(c.code)}</div>
                    <div style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.9);">${fmtDisc}</div>
                </div>
                <div style="background:rgba(17,153,142,0.25);border:1px dashed rgba(56,239,125,0.45);border-top:none;border-radius:0 0 14px 14px;padding:10px 16px;">
                    <div style="font-size:12px;color:rgba(255,255,255,0.8);">${escapeHtmlChat(c.name || '')}</div>
                    ${c.min_spend ? `<div style="font-size:11px;color:rgba(255,255,255,0.6);margin-top:2px;">ขั้นต่ำ ฿${Number(c.min_spend).toLocaleString('th-TH')}</div>` : ''}
                    ${c.end_date ? `<div style="font-size:10px;color:rgba(255,255,255,0.5);margin-top:2px;">ถึง ${new Date(c.end_date).toLocaleDateString('th-TH',{day:'numeric',month:'short',year:'2-digit'})}</div>` : ''}
                    ${couponNote}
                </div>
            </div>`;
    }

    const hasOrderCard = !!orderCardHtml;
    const hasCouponCard = !!couponCardHtml;
    const hasSpecialCard = !!(orderCardHtml || couponCardHtml);

    let bubbleStyle;
    if (hasCouponCard && !hasOrderCard) {
        bubbleStyle = `width: min(290px, calc(100vw - 72px)); padding: 0; background: transparent; ${isMine ? 'border-bottom-right-radius: 4px;' : 'border-bottom-left-radius: 4px;'}`;
    } else if (hasOrderCard) {
        bubbleStyle = `max-width: 85%; padding: 0; border-radius: 16px; overflow: hidden; ${isMine ? 'background: linear-gradient(135deg, #667eea, #764ba2); border-bottom-right-radius: 4px;' : 'background: #3a3a3c; border-bottom-left-radius: 4px;'}`;
    } else {
        bubbleStyle = `max-width: 80%; padding: 12px 16px; border-radius: 16px; ${isMine ? 'background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; border-bottom-right-radius: 4px;' : 'background: #3a3a3c; color: #fff; border-bottom-left-radius: 4px;'}`;
    }

    const isBot = !!msg.is_bot;
    const quickReplies = (isBot && msg.quick_replies) ? (typeof msg.quick_replies === 'string' ? JSON.parse(msg.quick_replies) : msg.quick_replies) : [];

    let quickReplyHtml = '';
    if (!isMine && quickReplies.length > 0) {
        quickReplyHtml = `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">` +
            quickReplies.map(qr => `<button data-qr="${escapeHtmlChat(qr)}" onclick="resellerChatQuickReply(this.dataset.qr)" style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.25);color:#fff;padding:5px 12px;border-radius:20px;font-size:12px;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.22)'" onmouseout="this.style.background='rgba(255,255,255,0.1)'">${escapeHtmlChat(qr)}</button>`).join('') +
            `</div>`;
    }

    const botBadge = isBot && !isMine ? `<div style="font-size:10px;color:rgba(255,255,255,0.5);margin-bottom:3px;display:flex;align-items:center;gap:3px;"><span style="background:rgba(139,92,246,0.4);border-radius:4px;padding:1px 5px;font-size:9px;letter-spacing:0.5px;">🤖 Bot</span></div>` : '';

    return `
        <div style="display: flex; ${isMine ? 'justify-content: flex-end' : 'justify-content: flex-start'}; flex-direction:column; align-items:${isMine ? 'flex-end' : 'flex-start'};" data-msg-id="${msg.id}" data-sender-id="${msg.sender_id}">
            ${botBadge}
            <div style="${bubbleStyle}">
                ${msg.is_broadcast ? `<div style="font-size: 10px; opacity: 0.6; margin-bottom: 4px; ${hasOrderCard ? 'padding: 4px 12px 0;' : hasCouponCard ? 'padding: 4px 0 4px;' : ''}">📢 ประกาศ</div>` : ''}
                ${couponCardHtml}
                ${orderCardHtml}
                ${productCardHtml}
                ${msg.content && !hasSpecialCard ? `<div style="font-size: 14px; line-height: 1.6; word-break: break-word;">${renderResellerChatContent(msg.content)}</div>` : ''}
                ${hasOrderCard && msg.content ? `<div style="padding: 6px 12px 10px; font-size: 12px; line-height: 1.4; word-break: break-word; color: rgba(255,255,255,0.7);">${renderResellerChatContent(msg.content)}</div>` : ''}
                ${hasCouponCard && !hasOrderCard && msg.content ? `<div style="margin-top:6px;font-size:12px;line-height:1.4;word-break:break-word;color:rgba(255,255,255,0.85);background:rgba(17,153,142,0.15);border:1px solid rgba(56,239,125,0.2);border-radius:10px;padding:8px 12px;">${renderResellerChatContent(msg.content)}</div>` : ''}
                ${msg.attachments && msg.attachments.length > 0 ? msg.attachments.map(att =>
                    att.file_type && att.file_type.startsWith('image/')
                        ? `<img src="${att.file_url}" style="max-width: 200px; border-radius: 8px; margin-top: 8px; cursor: pointer; ${hasOrderCard ? 'margin: 8px 12px;' : ''}" onclick="window.open('${att.file_url}', '_blank')">`
                        : `<a href="${att.file_url}" target="_blank" style="display: block; margin-top: 8px; color: #60a5fa; ${hasOrderCard ? 'padding: 0 12px;' : ''}">📎 ${escapeHtmlChat(att.file_name)}</a>`
                ).join('') : ''}
                <div style="font-size: 10px; opacity: 0.6; text-align: right; ${hasOrderCard ? 'padding: 0 10px 8px;' : hasCouponCard ? 'margin-top: 4px;' : 'margin-top: 6px;'}" class="reseller-msg-meta">${formatChatTimestamp(msg.created_at)}${isRead ? ' <span style="color: #60a5fa; opacity: 1;">อ่านแล้ว</span>' : ''}</div>
            </div>
            ${quickReplyHtml}
        </div>
    `;
}

function renderResellerAllMessages() {
    const container = document.getElementById('resellerChatMessages');
    if (!container) return;
    container.innerHTML = '';

    let lastDateStr = null;
    resellerAllMessages.forEach(msg => {
        const msgDate = new Date(msg.created_at).toDateString();
        if (msgDate !== lastDateStr) {
            lastDateStr = msgDate;
            const dateLabel = formatResellerChatDateSeparator(msg.created_at);
            container.insertAdjacentHTML('beforeend', `
                <div style="display: flex; align-items: center; gap: 12px; margin: 16px 0;">
                    <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.4); white-space: nowrap;">${dateLabel}</div>
                    <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
                </div>
            `);
        }

        const isMine = Number(msg.sender_id) === Number(currentUserId);
        const isRead = isMine && msg.id <= resellerChatOtherLastRead;
        container.insertAdjacentHTML('beforeend', buildResellerMessageHtml(msg, isMine, isRead));
    });
}

function updateResellerReadReceipts() {
    const container = document.getElementById('resellerChatMessages');
    if (!container) return;
    container.querySelectorAll('[data-msg-id]').forEach(el => {
        const msgId = parseInt(el.dataset.msgId);
        const senderId = parseInt(el.dataset.senderId);
        if (Number(senderId) === Number(currentUserId)) {
            const metaEl = el.querySelector('.reseller-msg-meta');
            if (metaEl && !metaEl.querySelector('span') && msgId <= resellerChatOtherLastRead) {
                metaEl.insertAdjacentHTML('beforeend', ' <span style="color: #60a5fa; opacity: 1;">อ่านแล้ว</span>');
            }
        }
    });
}

function formatResellerChatDateSeparator(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) return 'วันนี้';
    if (date.toDateString() === yesterday.toDateString()) return 'เมื่อวาน';

    const months = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear() + 543}`;
}

async function loadOlderResellerMessages() {
    if (resellerLoadingOlder || !resellerHasMoreMessages || !resellerChatThreadId || resellerOldestMessageId <= 0) return;
    resellerLoadingOlder = true;

    const container = document.getElementById('resellerChatMessages');
    const loadingEl = document.createElement('div');
    loadingEl.id = 'resellerOlderLoading';
    loadingEl.style.cssText = 'text-align: center; padding: 12px; color: rgba(255,255,255,0.4); font-size: 13px;';
    loadingEl.textContent = 'กำลังโหลด...';
    container.insertBefore(loadingEl, container.firstChild);

    const prevScrollHeight = container.scrollHeight;

    try {
        const response = await fetch(`/api/chat/threads/${resellerChatThreadId}/messages?before_id=${resellerOldestMessageId}&limit=50`, { credentials: 'include' });
        const data = await response.json();
        const messages = data.messages || data;
        resellerHasMoreMessages = data.has_more || false;

        const loadEl = document.getElementById('resellerOlderLoading');
        if (loadEl) loadEl.remove();

        if (messages.length > 0) {
            resellerOldestMessageId = messages[0].id;
            resellerAllMessages = [...messages, ...resellerAllMessages];

            renderResellerAllMessages();

            const newScrollHeight = container.scrollHeight;
            container.scrollTop = newScrollHeight - prevScrollHeight;
        }
    } catch (e) {
        console.error('Error loading older messages:', e);
        const loadEl = document.getElementById('resellerOlderLoading');
        if (loadEl) loadEl.remove();
    }
    resellerLoadingOlder = false;
}

function setupResellerChatScroll() {
    const container = document.getElementById('resellerChatMessages');
    if (!container || container.dataset.scrollSetup) return;
    container.dataset.scrollSetup = 'true';
    container.addEventListener('scroll', function() {
        if (container.scrollTop < 50 && !resellerLoadingOlder && resellerHasMoreMessages) {
            loadOlderResellerMessages();
        }
    });
}

function _ccFz(code, panelMode) {
    const n = (code || '').length;
    if (panelMode) return n <= 7 ? '13px' : n <= 10 ? '11px' : n <= 14 ? '9px' : '8px';
    return n <= 10 ? '15px' : n <= 14 ? '13px' : '11px';
}

function escapeHtmlChat(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderResellerChatContent(text) {
    if (!text) return '';
    let html = escapeHtmlChat(text).replace(/\n/g, '<br>');
    const imgTag = (url) =>
        `<a href="${url}" target="_blank" style="display:block;margin:4px 0;">` +
        `<img src="${url}" style="max-width:100%;max-height:220px;border-radius:10px;object-fit:contain;cursor:zoom-in;border:1px solid rgba(255,255,255,0.15);" ` +
        `onerror="this.style.display='none'"></a>`;
    html = html.replace(/(\/storage\/[^<>\s"']+\.(?:jpg|jpeg|png|gif|webp))/gi, (m) => imgTag(m));
    html = html.replace(/(https?:\/\/[^<>\s"']+\.(?:jpg|jpeg|png|gif|webp))/gi, (m) => imgTag(m));
    return html;
}

function formatChatTimestamp(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
        return date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
        return 'เมื่อวาน ' + date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    } else {
        return date.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) + ' ' + date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    }
}

let resellerSelectedChatProduct = null;
let resellerChatProductSearchTimeout = null;

let _botTypingTimer = null;

function _renderBotTypingIndicator() {
    const container = document.getElementById('resellerChatMessages');
    if (!container) return;
    if (container.querySelector('#botTypingIndicator')) return;
    const div = document.createElement('div');
    div.id = 'botTypingIndicator';
    div.style.cssText = 'display:flex;align-items:flex-end;gap:8px;margin-bottom:12px;';
    div.innerHTML = `
        <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#a855f7,#ec4899);display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;">🤖</div>
        <div style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:18px 18px 18px 4px;padding:10px 14px;max-width:70%;">
            <div style="font-size:12px;color:rgba(255,255,255,0.5);margin-bottom:4px;">กำลังประมวลผล รอสักครู่นะคะ</div>
            <div style="display:flex;gap:4px;align-items:center;">
                <span style="width:7px;height:7px;border-radius:50%;background:rgba(168,85,247,0.7);animation:botDot 1.2s infinite 0s;display:inline-block;"></span>
                <span style="width:7px;height:7px;border-radius:50%;background:rgba(168,85,247,0.7);animation:botDot 1.2s infinite 0.2s;display:inline-block;"></span>
                <span style="width:7px;height:7px;border-radius:50%;background:rgba(168,85,247,0.7);animation:botDot 1.2s infinite 0.4s;display:inline-block;"></span>
            </div>
        </div>`;
    if (!document.getElementById('botDotStyle')) {
        const style = document.createElement('style');
        style.id = 'botDotStyle';
        style.textContent = '@keyframes botDot{0%,80%,100%{transform:scale(0.6);opacity:0.4}40%{transform:scale(1);opacity:1}}';
        document.head.appendChild(style);
    }
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

let _botTypingMaxTimer = null;
let _botFastPollInterval = null;

function showBotTypingIndicatorDelayed(ms) {
    clearTimeout(_botTypingTimer);
    clearTimeout(_botTypingMaxTimer);
    _botTypingTimer = setTimeout(() => {
        _renderBotTypingIndicator();
        _botTypingMaxTimer = setTimeout(() => cancelBotTypingIndicator(), 90000);
        // Fast-poll every 2s while waiting for bot reply
        if (_botFastPollInterval) clearInterval(_botFastPollInterval);
        _botFastPollInterval = setInterval(() => {
            if (resellerChatThreadId) loadResellerChatMessages();
        }, 2000);
    }, ms || 800);
}

function cancelBotTypingIndicator() {
    clearTimeout(_botTypingTimer);
    clearTimeout(_botTypingMaxTimer);
    if (_botFastPollInterval) { clearInterval(_botFastPollInterval); _botFastPollInterval = null; }
    _botTypingTimer = null;
    _botTypingMaxTimer = null;
    const el = document.getElementById('botTypingIndicator');
    if (el) el.remove();
}

async function sendResellerChatMessage() {
    if (!resellerChatThreadId) {
        await initResellerChat();
    }
    
    const input = document.getElementById('resellerChatInput');
    const content = input.value.trim();
    
    if (!content && resellerPendingAttachments.length === 0 && !resellerSelectedChatProduct && !resellerSelectedChatOrder && !resellerSelectedChatCoupon) return;
    
    try {
        const body = {
            content: content,
            attachments: resellerPendingAttachments
        };
        if (resellerSelectedChatProduct) {
            body.product_id = resellerSelectedChatProduct.id;
        }
        if (resellerSelectedChatOrder) {
            body.order_id = resellerSelectedChatOrder.id;
        }
        if (resellerSelectedChatCoupon) {
            body.coupon_id = resellerSelectedChatCoupon.id;
        }

        input.value = '';
        input.style.height = 'auto';

        const response = await fetch(`/api/chat/threads/${resellerChatThreadId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body)
        });

        if (response.ok) {
            resellerPendingAttachments = [];
            resellerSelectedChatProduct = null;
            resellerSelectedChatOrder = null;
            resellerSelectedChatCoupon = null;
            document.getElementById('resellerChatAttachmentPreview').style.display = 'none';
            document.getElementById('resellerChatAttachmentPreview').innerHTML = '';
            document.getElementById('resellerChatProductPreview').style.display = 'none';
            document.getElementById('resellerChatOrderPreview').style.display = 'none';
            document.getElementById('resellerChatCouponPreview').style.display = 'none';
            await loadResellerChatMessages();
            // Bot now replies async — show typing indicator until polling picks up bot reply
            showBotTypingIndicatorDelayed(400);
        } else {
            const error = await response.json();
            showGlobalAlert('error', error.error || 'ไม่สามารถส่งข้อความได้');
        }
    } catch (error) {
        cancelBotTypingIndicator();
        showGlobalAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function resellerChatQuickReply(text) {
    const input = document.getElementById('resellerChatInput');
    if (input) { input.value = text; }
    await sendResellerChatMessage();
}

async function resellerRequestAdmin() {
    if (!resellerChatThreadId) return;
    const btn = document.getElementById('btnRequestAdmin');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ กำลังส่ง...'; }
    try {
        const res = await fetch(`/api/chat/threads/${resellerChatThreadId}/request-admin`, {
            method: 'POST', credentials: 'include'
        });
        if (res.ok) {
            const statusEl = document.getElementById('resellerNeedsAdminStatus');
            if (statusEl) statusEl.style.display = 'flex';
            if (btn) { btn.disabled = true; btn.textContent = '🙋 รอ Admin ตอบกลับ'; btn.style.opacity = '0.6'; }
            await loadResellerChatMessages();
        } else {
            if (btn) { btn.disabled = false; btn.textContent = '🙋 ขอคุยกับ Admin'; }
        }
    } catch (e) {
        if (btn) { btn.disabled = false; btn.textContent = '🙋 ขอคุยกับ Admin'; }
    }
}

let resellerChatProductSelections = [];

function openResellerChatProductSearch() {
    document.getElementById('resellerChatProductModal').style.display = 'flex';
    document.getElementById('resellerChatProductSearchInput').value = '';
    document.getElementById('resellerChatProductSearchStatus').style.display = 'none';
    document.getElementById('resellerChatProductSearchResults').innerHTML = `
        <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
            <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
        </div>`;
    resellerChatProductSelections = [];
    updateResellerChatProductSelectedBar();
    setTimeout(() => document.getElementById('resellerChatProductSearchInput').focus(), 100);
}

function closeResellerChatProductModal() {
    document.getElementById('resellerChatProductModal').style.display = 'none';
}

function searchResellerChatProducts() {
    clearTimeout(resellerChatProductSearchTimeout);
    const q = document.getElementById('resellerChatProductSearchInput').value.trim();
    const statusEl = document.getElementById('resellerChatProductSearchStatus');
    const fmtNum = (n) => n != null ? Number(n).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2}) : '0';
    if (q.length < 1) {
        statusEl.style.display = 'none';
        document.getElementById('resellerChatProductSearchResults').innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
                <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
            </div>`;
        return;
    }
    statusEl.style.display = 'block';
    statusEl.innerHTML = '<span style="display: inline-flex; align-items: center; gap: 6px;"><span class="chat-product-spinner"></span> กำลังค้นหา...</span>';
    resellerChatProductSearchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/chat/products/search?q=${encodeURIComponent(q)}`, { credentials: 'include' });
            const products = await response.json();
            const container = document.getElementById('resellerChatProductSearchResults');
            
            if (!Array.isArray(products) || products.length === 0) {
                statusEl.textContent = 'ไม่พบสินค้า';
                container.innerHTML = `
                    <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
                        <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 10px; opacity: 0.4;"><path d="M9.172 16.172a4 4 0 015.656 0"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><circle cx="12" cy="12" r="10"/></svg>
                        <p style="margin: 0; font-size: 14px;">ไม่พบสินค้าที่ตรงกัน</p>
                    </div>`;
                return;
            }
            
            statusEl.textContent = `พบ ${products.length} รายการ`;
            container.innerHTML = products.map(p => {
                const isSelected = resellerChatProductSelections.some(s => s.id === p.id);
                const hasDiscount = p.discount_percent && p.discount_percent > 0;
                const priceDisplay = hasDiscount
                    ? `<span style="color: #ffffff; font-weight: 600;">฿${fmtNum(p.tier_min_price)}</span> <span style="text-decoration: line-through; opacity: 0.4; font-size: 11px;">฿${fmtNum(p.min_price)}</span>`
                    : `<span style="color: #ffffff; font-weight: 600;">฿${fmtNum(p.min_price)}</span>`;
                const stockColor = (p.total_stock || 0) > 0 ? '#34d399' : '#f87171';
                const stockText = (p.total_stock || 0) > 0 ? `${p.total_stock} ชิ้น` : 'หมด';
                return `
                    <div onclick="toggleResellerChatProductSelect(${p.id}, '${escapeHtmlChat(p.name).replace(/'/g, "\\'")}', '${p.image_url || ''}', ${p.min_price || 0}, ${hasDiscount ? p.tier_min_price : p.min_price || 0}, ${p.discount_percent || 0})"
                         id="resellerChatProdItem_${p.id}"
                         style="display: flex; gap: 12px; align-items: center; padding: 10px 12px; border-radius: 10px; cursor: pointer; transition: all 0.2s; margin-bottom: 4px; border: 1.5px solid ${isSelected ? 'rgba(102,126,234,0.5)' : 'transparent'}; background: ${isSelected ? 'rgba(102,126,234,0.1)' : 'transparent'};"
                         onmouseover="if(!this.classList.contains('selected'))this.style.background='rgba(255,255,255,0.05)'" onmouseout="if(!this.classList.contains('selected'))this.style.background='transparent'">
                        <div style="position: relative; flex-shrink: 0;">
                            ${p.image_url ? `<img src="${p.image_url}" style="width: 52px; height: 52px; object-fit: cover; border-radius: 8px;">` : '<div style="width: 52px; height: 52px; background: rgba(255,255,255,0.05); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.15); font-size: 22px;">📦</div>'}
                            <div data-check="1" style="position: absolute; top: -4px; right: -4px; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; transition: all 0.2s; ${isSelected ? 'background: linear-gradient(135deg, #667eea, #764ba2); color: white; box-shadow: 0 0 0 2px rgba(102,126,234,0.3);' : 'background: rgba(255,255,255,0.1); color: transparent;'}">${isSelected ? '✓' : ''}</div>
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: white;">${escapeHtmlChat(p.name)}</div>
                            <div style="display: flex; align-items: center; gap: 8px; margin-top: 3px;">
                                <span style="font-size: 11px; opacity: 0.45;">${p.brand_name || ''}</span>
                                ${p.sku_count ? `<span style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.5);">${p.sku_count} SKU</span>` : ''}
                                <span style="font-size: 10px; color: ${stockColor};">● ${stockText}</span>
                            </div>
                            <div style="font-size: 13px; margin-top: 4px;">${priceDisplay}${hasDiscount ? ` <span style="color: #34d399; font-size: 11px; font-weight: 500;">-${p.discount_percent}%</span>` : ''}</div>
                        </div>
                    </div>`;
            }).join('');
        } catch (error) {
            console.error('Error searching products:', error);
            statusEl.textContent = 'เกิดข้อผิดพลาด';
        }
    }, 300);
}

function toggleResellerChatProductSelect(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    const idx = resellerChatProductSelections.findIndex(s => s.id === id);
    if (idx >= 0) {
        resellerChatProductSelections.splice(idx, 1);
    } else {
        resellerChatProductSelections.push({ id, name, imageUrl, originalPrice, tierPrice, discountPercent });
    }
    const item = document.getElementById(`resellerChatProdItem_${id}`);
    if (item) {
        const isNowSelected = resellerChatProductSelections.some(s => s.id === id);
        item.style.border = isNowSelected ? '1.5px solid rgba(102,126,234,0.5)' : '1.5px solid transparent';
        item.style.background = isNowSelected ? 'rgba(102,126,234,0.1)' : 'transparent';
        const checkEl = item.querySelector('[data-check]');
        if (checkEl) {
            if (isNowSelected) {
                checkEl.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
                checkEl.style.color = 'white';
                checkEl.textContent = '✓';
            } else {
                checkEl.style.background = 'rgba(255,255,255,0.1)';
                checkEl.style.color = 'transparent';
                checkEl.textContent = '';
            }
        }
    }
    updateResellerChatProductSelectedBar();
}

function updateResellerChatProductSelectedBar() {
    const bar = document.getElementById('resellerChatProductSelectedBar');
    const countEl = document.getElementById('resellerChatProductSelectedCount');
    const thumbsEl = document.getElementById('resellerChatProductSelectedThumbs');
    if (resellerChatProductSelections.length === 0) {
        bar.style.display = 'none';
        return;
    }
    bar.style.display = 'block';
    countEl.textContent = resellerChatProductSelections.length;
    thumbsEl.innerHTML = resellerChatProductSelections.map(s => `
        <div style="position: relative; flex-shrink: 0;" title="${escapeHtmlChat(s.name)}">
            ${s.imageUrl ? `<img src="${s.imageUrl}" style="width: 28px; height: 28px; object-fit: cover; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);">` : '<div style="width: 28px; height: 28px; background: rgba(255,255,255,0.1); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px;">📦</div>'}
            <div onclick="event.stopPropagation(); removeResellerChatProductFromSelection(${s.id})" style="position: absolute; top: -5px; right: -5px; width: 14px; height: 14px; background: #ef4444; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 8px; color: white; cursor: pointer; line-height: 1;">×</div>
        </div>
    `).join('');
}

function removeResellerChatProductFromSelection(id) {
    resellerChatProductSelections = resellerChatProductSelections.filter(s => s.id !== id);
    const item = document.getElementById(`resellerChatProdItem_${id}`);
    if (item) {
        item.style.border = '1.5px solid transparent';
        item.style.background = 'transparent';
        const checkEl = item.querySelector('[data-check]');
        if (checkEl) {
            checkEl.style.background = 'rgba(255,255,255,0.1)';
            checkEl.style.color = 'transparent';
            checkEl.textContent = '';
        }
    }
    updateResellerChatProductSelectedBar();
}

function clearResellerChatProductSelection() {
    resellerChatProductSelections.forEach(s => {
        const item = document.getElementById(`resellerChatProdItem_${s.id}`);
        if (item) {
            item.style.border = '1.5px solid transparent';
            item.style.background = 'transparent';
            const checkEl = item.querySelector('[data-check]');
            if (checkEl) {
                checkEl.style.background = 'rgba(255,255,255,0.1)';
                checkEl.style.color = 'transparent';
                checkEl.textContent = '';
            }
        }
    });
    resellerChatProductSelections = [];
    updateResellerChatProductSelectedBar();
}

async function sendSelectedResellerChatProducts() {
    if (!resellerChatThreadId || resellerChatProductSelections.length === 0) return;
    closeResellerChatProductModal();
    for (const product of resellerChatProductSelections) {
        try {
            await fetch(`/api/chat/threads/${resellerChatThreadId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ content: '', product_id: product.id })
            });
        } catch (e) { console.error('Error sending product:', e); }
    }
    resellerChatProductSelections = [];
    updateResellerChatProductSelectedBar();
    loadResellerChatMessages();
}

function selectResellerChatProduct(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    resellerSelectedChatProduct = { id, name, imageUrl, originalPrice, tierPrice, discountPercent };
    const preview = document.getElementById('resellerChatProductPreview');
    const img = document.getElementById('resellerChatProductImg');
    const nameEl = document.getElementById('resellerChatProductName');
    const priceEl = document.getElementById('resellerChatProductPrice');
    const fmtNum = (n) => n != null ? Number(n).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2}) : '0';
    if (imageUrl) { img.src = imageUrl; img.style.display = 'block'; } else { img.style.display = 'none'; }
    nameEl.textContent = name;
    if (discountPercent > 0) {
        priceEl.textContent = `฿${fmtNum(originalPrice)}`;
    }
    
    preview.style.display = 'block';
    closeResellerChatProductModal();
}

function removeResellerChatProduct() {
    resellerSelectedChatProduct = null;
    document.getElementById('resellerChatProductPreview').style.display = 'none';
}

async function handleResellerChatFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/chat/upload', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            resellerPendingAttachments.push(result);
            updateResellerChatAttachmentPreview();
        } else {
            showGlobalAlert('error', result.error || 'อัปโหลดไม่สำเร็จ');
        }
    } catch (error) {
        showGlobalAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
    
    event.target.value = '';
}

function updateResellerChatAttachmentPreview() {
    const container = document.getElementById('resellerChatAttachmentPreview');
    if (resellerPendingAttachments.length === 0) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    
    container.style.display = 'flex';
    container.style.gap = '8px';
    container.style.flexWrap = 'wrap';
    
    container.innerHTML = resellerPendingAttachments.map((att, i) => `
        <div style="position: relative; padding: 8px 12px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 12px;">
            ${att.file_type && att.file_type.startsWith('image/') ? '🖼️' : '📎'} ${escapeHtmlChat(att.file_name)}
            <button onclick="removeResellerChatAttachment(${i})" style="position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; background: #ef4444; border: none; color: white; cursor: pointer; font-size: 12px; line-height: 1;">×</button>
        </div>
    `).join('');
}

function removeResellerChatAttachment(index) {
    resellerPendingAttachments.splice(index, 1);
    updateResellerChatAttachmentPreview();
}

function startResellerChatPolling() {
    if (resellerChatPollingInterval) clearInterval(resellerChatPollingInterval);
    resellerChatPollingInterval = setInterval(() => {
        if (resellerChatThreadId) {
            loadResellerChatMessages();
        }
        loadResellerChatUnreadCount();
    }, 5000);
}

function stopResellerChatPolling() {
    if (resellerChatPollingInterval) {
        clearInterval(resellerChatPollingInterval);
        resellerChatPollingInterval = null;
    }
}

async function loadResellerChatUnreadCount() {
    try {
        const response = await fetch('/api/chat/unread-count', { credentials: 'include' });
        const data = await response.json();

        const badge = document.getElementById('resellerChatBadge');
        const bottomBadge = document.getElementById('bottomChatBadge');
        const chatNavItem = document.querySelector('.nav-item[data-page="chat"]');
        const bottomChatTab = document.querySelector('.bottom-tab-item[data-page="chat"]');
        const count = data.unread_count || 0;
        const countText = count > 99 ? '99+' : count;

        if (badge) {
            if (count > 0) {
                badge.textContent = countText;
                badge.style.display = 'flex';
                badge.classList.add('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.add('chat-nav-active');
            } else {
                badge.style.display = 'none';
                badge.classList.remove('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.remove('chat-nav-active');
            }
        }

        if (bottomBadge) {
            if (count > 0) {
                bottomBadge.textContent = countText;
                bottomBadge.style.display = 'flex';
                bottomBadge.classList.add('animated');
                if (bottomChatTab) bottomChatTab.style.color = '#ef4444';
            } else {
                bottomBadge.style.display = 'none';
                bottomBadge.classList.remove('animated');
                if (bottomChatTab) bottomChatTab.style.color = '';
            }
        }
    } catch (error) {
        console.error('Error loading unread count:', error);
    }
}

/* ─── Chat Plus Menu ─────────────────────────────────────── */
let resellerChatPlusMenuOpen = false;

function toggleResellerChatPlusMenu() {
    resellerChatPlusMenuOpen ? closeResellerChatPlusMenu() : openResellerChatPlusMenuFn();
}

function openResellerChatPlusMenuFn() {
    resellerChatPlusMenuOpen = true;
    const menu = document.getElementById('resellerChatPlusMenu');
    const iconPlus = document.getElementById('resellerChatPlusIconPlus');
    const iconX = document.getElementById('resellerChatPlusIconX');
    if (menu) menu.style.display = 'block';
    if (iconPlus) iconPlus.style.display = 'none';
    if (iconX) iconX.style.display = 'block';
    setTimeout(() => document.addEventListener('click', resellerChatPlusOutsideClick), 50);
}

function closeResellerChatPlusMenu() {
    resellerChatPlusMenuOpen = false;
    const menu = document.getElementById('resellerChatPlusMenu');
    const iconPlus = document.getElementById('resellerChatPlusIconPlus');
    const iconX = document.getElementById('resellerChatPlusIconX');
    if (menu) menu.style.display = 'none';
    if (iconPlus) iconPlus.style.display = 'block';
    if (iconX) iconX.style.display = 'none';
    document.removeEventListener('click', resellerChatPlusOutsideClick);
}

function resellerChatPlusOutsideClick(e) {
    const btn = document.getElementById('resellerChatPlusBtn');
    const menu = document.getElementById('resellerChatPlusMenu');
    if (btn && !btn.contains(e.target) && menu && !menu.contains(e.target)) {
        closeResellerChatPlusMenu();
    }
}

function openResellerChatGallery() {
    closeResellerChatPlusMenu();
    const el = document.getElementById('resellerChatFileInput');
    if (el) { el.value = ''; el.click(); }
}

function openResellerChatCamera() {
    closeResellerChatPlusMenu();
    const el = document.getElementById('resellerChatCameraInput');
    if (el) { el.value = ''; el.click(); }
}

/* ─── Chat Order Picker ─────────────────────────────────── */
let resellerSelectedChatOrder = null;

async function openResellerChatOrderPicker() {
    closeResellerChatPlusMenu();
    const modal = document.getElementById('resellerChatOrderPickerModal');
    if (!modal) return;
    modal.style.display = 'flex';

    const listEl = document.getElementById('resellerChatOrderPickerList');
    listEl.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.4);">
        <div style="width: 24px; height: 24px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: chatSpinAnim 0.6s linear infinite; margin: 0 auto 12px;"></div>
        <div style="font-size: 13px;">กำลังโหลด...</div>
    </div>`;

    try {
        const res = await fetch(`${RESELLER_API_URL}/reseller/recent-orders?limit=5`, { credentials: 'include' });
        const orders = await res.json();

        const sL = { 'pending_payment': 'รอชำระเงิน', 'under_review': 'รอตรวจสอบ', 'preparing': 'เตรียมสินค้า', 'shipped': 'กำลังจัดส่ง', 'delivered': 'ได้รับสินค้าแล้ว', 'failed_delivery': 'จัดส่งไม่สำเร็จ', 'cancelled': 'ยกเลิก' };
        const sC = { 'pending_payment': '#f59e0b', 'under_review': '#3b82f6', 'preparing': '#8b5cf6', 'shipped': '#0ea5e9', 'delivered': '#10b981', 'failed_delivery': '#ef4444', 'cancelled': '#6b7280' };

        if (!Array.isArray(orders) || orders.length === 0) {
            listEl.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.4);">
                <div style="font-size: 32px; margin-bottom: 10px;">📋</div>
                <div style="font-size: 13px;">ยังไม่มีคำสั่งซื้อ</div>
            </div>`;
            return;
        }

        listEl.innerHTML = orders.map(o => `
            <div onclick="selectResellerChatOrder(${o.id}, '${escapeHtmlChat(o.order_number)}', '${o.status}', ${o.final_amount})"
                 style="padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.06); cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: background 0.15s;"
                 onmouseover="this.style.background='rgba(255,255,255,0.05)'" onmouseout="this.style.background='transparent'"
                 ontouchstart="this.style.background='rgba(255,255,255,0.05)'" ontouchend="this.style.background='transparent'">
                <div>
                    <div style="font-size: 14px; font-weight: 700; color: white;">${escapeHtmlChat(o.order_number)}</div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.45); margin-top: 3px;">${new Date(o.created_at).toLocaleDateString('th-TH', {day:'numeric', month:'short', year:'numeric'})}</div>
                </div>
                <div style="text-align: right;">
                    <div style="margin-bottom: 5px;">
                        <span style="background: ${sC[o.status] || '#6b7280'}; color: white; padding: 2px 10px; border-radius: 20px; font-size: 10px; font-weight: 600;">${sL[o.status] || o.status}</span>
                    </div>
                    <div style="font-size: 14px; font-weight: 700; color: #ffffff;">฿${Number(o.final_amount || 0).toLocaleString('th-TH')}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        listEl.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: #ef4444; font-size: 13px;">เกิดข้อผิดพลาด กรุณาลองใหม่</div>`;
    }
}

function closeResellerChatOrderPicker() {
    const modal = document.getElementById('resellerChatOrderPickerModal');
    if (modal) modal.style.display = 'none';
}

function selectResellerChatOrder(id, orderNumber, status, finalAmount) {
    resellerSelectedChatOrder = { id, order_number: orderNumber, status, final_amount: finalAmount };
    closeResellerChatOrderPicker();
    const preview = document.getElementById('resellerChatOrderPreview');
    const previewText = document.getElementById('resellerChatOrderPreviewText');
    if (preview) preview.style.display = 'block';
    if (previewText) previewText.textContent = `${orderNumber}  ·  ฿${Number(finalAmount).toLocaleString('th-TH')}`;
}

function removeResellerChatOrder() {
    resellerSelectedChatOrder = null;
    const preview = document.getElementById('resellerChatOrderPreview');
    if (preview) preview.style.display = 'none';
}

/* ─── Chat Coupon Picker (Reseller) ─────────────────────────────────── */
let resellerSelectedChatCoupon = null;

async function openResellerChatCouponPicker() {
    const modal = document.getElementById('resellerChatCouponModal');
    if (!modal) return;
    modal.style.display = 'flex';
    const list = document.getElementById('resellerChatCouponList');
    list.innerHTML = `<div style="text-align:center;padding:40px;color:rgba(255,255,255,0.4);">
        <div style="width:24px;height:24px;border:2px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin 0.6s linear infinite;margin:0 auto 12px;"></div>
        <div style="font-size:13px;">กำลังโหลด...</div></div>`;
    try {
        const r = await fetch('/api/reseller/coupons/wallet', { credentials: 'include' });
        const data = await r.json();
        const coupons = Array.isArray(data) ? data : (data.coupons || []);
        const active = coupons.filter(c => c.is_active && !c.is_used);
        if (!active.length) {
            list.innerHTML = `<div style="text-align:center;padding:40px;color:rgba(255,255,255,0.4);"><div style="font-size:32px;margin-bottom:10px;">🎟️</div><div>ยังไม่มีคูปองใน wallet</div></div>`;
            return;
        }
        const fmtDisc = c => c.discount_type === 'percent' ? `ลด ${c.discount_value}%` : c.discount_type === 'free_shipping' ? 'ฟรีค่าจัดส่ง' : `ลด ฿${Number(c.discount_value).toLocaleString('th-TH')}`;
        list.innerHTML = active.map(c => `
            <div onclick="selectResellerChatCoupon(${JSON.stringify(c).replace(/"/g,'&quot;')})"
                 style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.15s;"
                 onmouseover="this.style.background='rgba(255,255,255,0.05)'" onmouseout="this.style.background='transparent'"
                 ontouchstart="this.style.background='rgba(255,255,255,0.05)'" ontouchend="this.style.background='transparent'">
                <div>
                    <div style="font-size:13px;font-weight:700;color:#38ef7d;">${escapeHtmlChat(c.code)}</div>
                    <div style="font-size:12px;color:rgba(255,255,255,0.65);">${escapeHtmlChat(c.name || '')}</div>
                    ${c.min_spend ? `<div style="font-size:11px;color:rgba(255,255,255,0.4);">ขั้นต่ำ ฿${Number(c.min_spend).toLocaleString('th-TH')}</div>` : ''}
                </div>
                <div style="text-align:right;flex-shrink:0;margin-left:12px;">
                    <div style="font-size:12px;font-weight:600;color:#38ef7d;">${fmtDisc(c)}</div>
                    ${c.end_date ? `<div style="font-size:10px;color:rgba(255,255,255,0.35);">ถึง ${new Date(c.end_date).toLocaleDateString('th-TH',{day:'numeric',month:'short'})}</div>` : ''}
                </div>
            </div>`).join('');
    } catch(e) {
        list.innerHTML = `<div style="text-align:center;padding:40px;color:#f87171;">โหลดข้อมูลไม่สำเร็จ</div>`;
    }
}

function selectResellerChatCoupon(c) {
    resellerSelectedChatCoupon = c;
    document.getElementById('resellerChatCouponModal').style.display = 'none';
    const fmtDisc = c.discount_type === 'percent' ? `ลด ${c.discount_value}%` : c.discount_type === 'free_shipping' ? 'ฟรีค่าจัดส่ง' : `ลด ฿${Number(c.discount_value).toLocaleString('th-TH')}`;
    const preview = document.getElementById('resellerChatCouponPreview');
    const text = document.getElementById('resellerChatCouponPreviewText');
    if (preview && text) {
        text.textContent = `${c.code} · ${fmtDisc}`;
        preview.style.display = 'block';
    }
}

function removeResellerChatCoupon() {
    resellerSelectedChatCoupon = null;
    const preview = document.getElementById('resellerChatCouponPreview');
    if (preview) preview.style.display = 'none';
}
