const RESELLER_API_URL = '/api';

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
        await loadThailandProvinces();
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
    const validPages = ['home', 'catalog', 'cart', 'checkout', 'orders', 'customers', 'profile'];
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
        'under_review': 'รอตรวจสอบ',
        'preparing': 'เตรียมสินค้า',
        'shipped': 'กำลังจัดส่ง',
        'delivered': 'ได้รับสินค้าแล้ว',
        'failed_delivery': 'จัดส่งไม่สำเร็จ',
        'cancelled': 'ยกเลิก'
    };
    
    const statusColors = {
        'pending_payment': '#fbbf24',
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
            <div style="margin-bottom: 12px;">
                <label style="display: block; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 8px;">${opt.name}</label>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
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
                        <button type="button" class="option-btn ${isFirstAvailable ? 'active' : ''}" 
                                data-option="${opt.name}" data-value="${valStr}"
                                onclick="selectOption(this, '${opt.name}', '${valStr}')"
                                ${isOutOfStock ? 'disabled' : ''}
                                style="padding: 8px 16px; border-radius: 8px; border: 1px solid ${isOutOfStock ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.3)'}; 
                                       background: ${isFirstAvailable ? 'var(--primary)' : 'transparent'}; 
                                       color: ${isOutOfStock ? 'rgba(255,255,255,0.3)' : 'white'}; 
                                       cursor: ${isOutOfStock ? 'not-allowed' : 'pointer'};
                                       text-decoration: ${isOutOfStock ? 'line-through' : 'none'};
                                       position: relative;">
                            ${valStr}${isOutOfStock ? ' <span style="font-size:10px;">(หมด)</span>' : ''}
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
            <div style="margin-bottom: 16px;">
                <label style="display: block; font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 10px; font-weight: 500;">
                    ${c.name} ${c.is_required ? '<span style="color:#ef4444;">*</span>' : ''}
                </label>
                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                    ${(c.choices || []).map((ch, idx) => {
                        const hasExtraPrice = ch.extra_price && ch.extra_price > 0;
                        return `
                        <button type="button" class="customization-btn" 
                                data-customization="${c.id}" data-choice="${ch.id}"
                                onclick="toggleCustomization(this, ${c.id}, ${ch.id}, ${c.allow_multiple})"
                                style="padding: 10px 16px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.25); 
                                       background: rgba(255,255,255,0.05); color: white; cursor: pointer; font-size: 13px;
                                       transition: all 0.2s ease; display: flex; align-items: center; gap: 8px;
                                       backdrop-filter: blur(5px);">
                            <span class="customization-check" style="display: none; color: #22c55e; font-weight: bold;">✓</span>
                            <span>${ch.label}</span>
                            ${hasExtraPrice ? `<span style="background: linear-gradient(135deg, #22c55e, #16a34a); color: white; 
                                               padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                                               +฿${ch.extra_price.toLocaleString()}</span>` : ''}
                        </button>
                    `}).join('')}
                </div>
            </div>
        `).join('');
    }
    
    // Build image gallery HTML
    let galleryHtml = '';
    if (product.images && product.images.length > 1) {
        galleryHtml = `
            <div style="display: flex; gap: 8px; margin-top: 12px; justify-content: center;">
                ${product.images.map((img, idx) => `
                    <img src="${img.image_url}" alt="Product ${idx+1}" 
                         onclick="changeMainImage('${img.image_url}')"
                         style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; 
                                cursor: pointer; border: 2px solid ${idx === 0 ? 'var(--primary)' : 'transparent'};"
                         class="gallery-thumb">
                `).join('')}
            </div>
        `;
    }
    
    // Size chart HTML
    let sizeChartHtml = '';
    if (product.size_chart_image_url) {
        sizeChartHtml = `
            <div style="margin-top: 12px;">
                <button onclick="showSizeChart('${product.size_chart_image_url}')" 
                        style="background: transparent; border: 1px solid rgba(255,255,255,0.3); 
                               color: white; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 12px;">
                    📏 ดูตารางไซส์
                </button>
            </div>
        `;
    }
    
    document.getElementById('productModalContent').innerHTML = `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0; min-height: 400px;">
            <div style="padding: 16px; background: rgba(255,255,255,0.98); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                ${mainImage 
                    ? `<img id="modalMainImage" src="${mainImage}" alt="${product.name}" style="width: 100%; height: 320px; object-fit: contain;">`
                    : `<div style="width: 100%; height: 320px; background: rgba(0,0,0,0.05); display: flex; align-items: center; justify-content: center; border-radius: 8px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#ccc" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
                       </div>`
                }
                ${galleryHtml}
            </div>
            <div style="padding: 24px; max-height: 500px; overflow-y: auto;">
                <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 4px;">${product.brand_name || ''}</div>
                <h3 style="font-size: 20px; font-weight: 600; margin-bottom: 8px;">${product.name}</h3>
                <div style="font-size: 12px; color: rgba(255,255,255,0.5); margin-bottom: 16px;">SKU: ${product.parent_sku || '-'}</div>
                
                <div style="margin-bottom: 20px;">
                    ${discount > 0 ? `
                        <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 4px;">ราคาปกติ</div>
                        <div style="text-decoration: line-through; color: rgba(255,255,255,0.4); font-size: 18px; margin-bottom: 4px;">฿${originalPrice.toLocaleString()}</div>
                        <div style="font-size: 12px; color: #22c55e; margin-bottom: 4px;">ราคาสำหรับคุณ <span style="background: #ef4444; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 4px;">-${discount}%</span></div>
                    ` : '<div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 4px;">ราคา</div>'}
                    <span id="modalPrice" style="font-size: 28px; font-weight: 700; color: #22c55e;">฿${price.toLocaleString()}</span>
                </div>
                
                ${optionsHtml}
                ${customizationsHtml}
                ${sizeChartHtml}
                
                <div style="display: flex; align-items: center; gap: 12px; margin-top: 20px;">
                    <span style="font-size: 13px; color: rgba(255,255,255,0.7);">จำนวน:</span>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button onclick="changeModalQty(-1)" style="width: 32px; height: 32px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.3); background: transparent; color: white; cursor: pointer;">-</button>
                        <input type="number" id="modalQty" value="1" min="1" style="width: 60px; text-align: center; padding: 8px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.3); background: transparent; color: white;">
                        <button onclick="changeModalQty(1)" style="width: 32px; height: 32px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.3); background: transparent; color: white; cursor: pointer;">+</button>
                    </div>
                    <span id="modalStock" style="font-size: 12px; color: rgba(255,255,255,0.5);">คงเหลือ ${stock} ชิ้น</span>
                </div>
                
                <button onclick="addToCartFromModal()" style="width: 100%; margin-top: 20px; padding: 14px; background: linear-gradient(135deg, var(--primary), var(--secondary)); border: none; border-radius: 10px; color: white; font-size: 16px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                    เพิ่มลงตะกร้า
                </button>
            </div>
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
        b.style.background = 'transparent';
    });
    btn.classList.add('active');
    btn.style.background = 'var(--primary)';
    
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
        document.getElementById('modalPrice').textContent = `฿${(matchingSku.final_price || matchingSku.price).toLocaleString()}`;
        document.getElementById('modalStock').textContent = `คงเหลือ ${matchingSku.stock || 0} ชิ้น`;
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
        thumb.style.border = thumb.src === imageUrl ? '2px solid var(--primary)' : '2px solid transparent';
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
            btn.style.background = 'rgba(255,255,255,0.05)';
            btn.style.borderColor = 'rgba(255,255,255,0.25)';
            const check = btn.querySelector('.customization-check');
            if (check) check.style.display = 'none';
        } else {
            selectedCustomizations[customizationId].push(choiceId);
            btn.style.background = 'linear-gradient(135deg, rgba(168,85,247,0.3), rgba(236,72,153,0.3))';
            btn.style.borderColor = 'var(--primary)';
            const check = btn.querySelector('.customization-check');
            if (check) check.style.display = 'inline';
        }
    } else {
        btns.forEach(b => {
            b.style.background = 'rgba(255,255,255,0.05)';
            b.style.borderColor = 'rgba(255,255,255,0.25)';
            const check = b.querySelector('.customization-check');
            if (check) check.style.display = 'none';
        });
        selectedCustomizations[customizationId] = [choiceId];
        btn.style.background = 'linear-gradient(135deg, rgba(168,85,247,0.3), rgba(236,72,153,0.3))';
        btn.style.borderColor = 'var(--primary)';
        const check = btn.querySelector('.customization-check');
        if (check) check.style.display = 'inline';
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

document.getElementById('productSearch')?.addEventListener('input', function() {
    const search = this.value.toLowerCase();
    const filtered = products.filter(p => 
        p.name.toLowerCase().includes(search) || 
        (p.brand_name && p.brand_name.toLowerCase().includes(search))
    );
    renderProducts(filtered);
});

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
    
    container.innerHTML = `
        <div style="display: grid; grid-template-columns: 1fr 300px; gap: 24px;">
            <div>
                ${cartItems.map(item => {
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
                    
                    return `
                    <div class="cart-item">
                        <img class="cart-item-image" src="${item.image_url || ''}" onerror="this.style.display='none'" alt="">
                        <div class="cart-item-info">
                            <div class="cart-item-name">${item.product_name}</div>
                            <div class="cart-item-sku">${item.sku_code}</div>
                            ${skuOptionsHtml}
                            ${customizationsHtml}
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
                `}).join('')}
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

let checkoutData = { items: [], total: 0, customers: [], selfAddress: null };

async function loadCheckout() {
    try {
        const [cartRes, customersRes, profileRes, channelsRes] = await Promise.all([
            fetch(`${RESELLER_API_URL}/reseller/cart`),
            fetch(`${RESELLER_API_URL}/reseller/customers`),
            fetch(`${RESELLER_API_URL}/reseller/profile`),
            fetch(`${RESELLER_API_URL}/sales-channels`)
        ]);
        
        if (!cartRes.ok) throw new Error('Failed to load cart');
        
        const cartData = await cartRes.json();
        checkoutData.items = cartData.items || [];
        checkoutData.total = cartData.total || 0;
        
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
        
        if (channelsRes.ok) {
            checkoutData.salesChannels = await channelsRes.json();
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
    
    // Render sales channel buttons
    const channelContainer = document.getElementById('salesChannelButtons');
    const channelInput = document.getElementById('checkoutSalesChannel');
    if (channelContainer && checkoutData.salesChannels) {
        channelContainer.innerHTML = checkoutData.salesChannels.map(ch => `
            <button type="button" class="sales-channel-btn" data-channel="${ch.id}" onclick="selectSalesChannel(${ch.id})"
                    style="padding: 10px 18px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.2); 
                           background: rgba(255,255,255,0.05); color: white; cursor: pointer; font-size: 13px;
                           transition: all 0.2s ease; display: flex; align-items: center; gap: 8px;
                           backdrop-filter: blur(5px);">
                <span>${ch.name}</span>
            </button>
        `).join('');
    }
    
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
                <div style="font-weight: 500; margin-bottom: 4px; color: #fbbf24;">ยังไม่ได้ตั้งค่าที่อยู่ร้าน</div>
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

function selectSalesChannel(channelId) {
    document.getElementById('checkoutSalesChannel').value = channelId;
    document.querySelectorAll('.sales-channel-btn').forEach(btn => {
        if (btn.dataset.channel == channelId) {
            btn.style.background = 'linear-gradient(135deg, rgba(168,85,247,0.4), rgba(236,72,153,0.4))';
            btn.style.borderColor = 'var(--primary)';
        } else {
            btn.style.background = 'rgba(255,255,255,0.05)';
            btn.style.borderColor = 'rgba(255,255,255,0.2)';
        }
    });
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
    document.getElementById('summarySubtotal').textContent = `฿${checkoutData.total.toLocaleString()}`;
    calculateShippingCost();
}

async function calculateShippingCost() {
    const shippingEl = document.getElementById('summaryShipping');
    const totalEl = document.getElementById('summaryTotal');
    const promoRow = document.getElementById('shippingPromoRow');
    const promoName = document.getElementById('shippingPromoName');
    const promoSaved = document.getElementById('shippingPromoSaved');
    
    let totalWeight = 0;
    checkoutData.items.forEach(item => {
        const weight = item.weight || 100;
        totalWeight += weight * item.quantity;
    });
    
    try {
        const res = await fetch(`${RESELLER_API_URL}/calculate-shipping`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                total_weight: totalWeight,
                order_total: checkoutData.total
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
            promoSaved.textContent = `-฿${(data.original_shipping - data.shipping_cost).toLocaleString()}`;
            promoRow.style.display = 'flex';
        } else {
            promoRow.style.display = 'none';
        }
        
        const grandTotal = checkoutData.total + data.shipping_cost;
        totalEl.textContent = `฿${grandTotal.toLocaleString()}`;
        
        loadPromptPayQR();
        
    } catch (error) {
        console.error('Error calculating shipping:', error);
        shippingEl.textContent = '฿0';
        totalEl.textContent = `฿${checkoutData.total.toLocaleString()}`;
        checkoutData.shippingCost = 0;
        loadPromptPayQR();
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
        const amount = (checkoutData.total || 0) + shippingCost;
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
}

function removePaymentSlip() {
    selectedPaymentSlip = null;
    document.getElementById('paymentSlipInput').value = '';
    document.getElementById('slipPreviewArea').innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="width: 40px; height: 40px; opacity: 0.5; margin-bottom: 8px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
        <p style="opacity: 0.6; font-size: 13px;">คลิกเพื่ออัปโหลดสลิป หรือลากไฟล์มาวาง</p>
    `;
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
    
    btn.disabled = !isValid;
    
    // Show/hide helper text
    let helper = document.getElementById('checkoutValidationHelper');
    if (!helper) {
        helper = document.createElement('div');
        helper.id = 'checkoutValidationHelper';
        helper.style.cssText = 'font-size: 12px; color: #fbbf24; margin-top: 8px; text-align: center;';
        btn.parentNode.insertBefore(helper, btn.nextSibling);
    }
    helper.textContent = isValid ? '' : reason;
    helper.style.display = isValid ? 'none' : 'block';
}

async function placeOrder() {
    const shippingType = document.querySelector('input[name="shippingType"]:checked').value;
    const paymentMethod = document.querySelector('input[name="paymentMethod"]:checked').value;
    const notes = document.getElementById('orderNotes').value;
    const salesChannelId = document.getElementById('checkoutSalesChannel')?.value || null;
    
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
        
        const response = await fetch(`${RESELLER_API_URL}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                payment_method: paymentMethod,
                notes: notes,
                sales_channel_id: salesChannelId ? parseInt(salesChannelId) : null,
                ...shippingData
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('สร้างคำสั่งซื้อสำเร็จ!', 'success');
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

async function loadCartBadge() {
    try {
        const response = await fetch(`${RESELLER_API_URL}/reseller/cart`);
        if (response.ok) {
            const data = await response.json();
            const items = data.items || [];
            const totalQty = items.reduce((sum, item) => sum + (item.quantity || 0), 0);
            const badge = document.getElementById('cartBadge');
            if (totalQty > 0) {
                badge.textContent = totalQty > 99 ? '99+' : totalQty;
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
    
    container.innerHTML = orders.map(order => `
        <div class="order-card" style="background: rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-bottom: 12px; cursor: pointer;" onclick="viewResellerOrderDetails(${order.id})">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-weight: 600; color: #ffffff;">${order.order_number || '#' + order.id}</span>
                <span style="background: ${statusColors[order.status] || '#6b7280'}; color: white; padding: 4px 10px; border-radius: 6px; font-size: 11px;">${statusLabels[order.status] || order.status}</span>
            </div>
            <div style="display: flex; justify-content: space-between; color: rgba(255,255,255,0.6); font-size: 13px;">
                <span>${new Date(order.created_at).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                <span style="color: #22c55e; font-weight: 600;">฿${(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</span>
            </div>
            ${order.status === 'pending_payment' ? `
                <button class="btn" onclick="event.stopPropagation(); openPaymentSlipModal(${order.id})" style="width: 100%; margin-top: 12px; padding: 10px; font-size: 13px; background: linear-gradient(135deg, #a855f7, #ec4899);">
                    อัพโหลดสลิปชำระเงิน
                </button>
            ` : ''}
        </div>
    `).join('');
}

async function viewResellerOrderDetails(orderId) {
    try {
        const response = await fetch(`${RESELLER_API_URL}/orders/${orderId}`);
        if (!response.ok) throw new Error('Failed to load order');
        
        const order = await response.json();
        
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
                                    <div style="font-size: 12px; color: rgba(255,255,255,0.7); display: flex; justify-content: space-between; align-items: center;">
                                        <span><strong>${escapeHtml(s.shipping_provider || 'ขนส่ง')}:</strong> ${escapeHtml(s.tracking_number)}</span>
                                        ${trackingUrl ? `<a href="${trackingUrl}" target="_blank" style="color: #a855f7; text-decoration: none; font-size: 11px;">ติดตามพัสดุ →</a>` : ''}
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }
        
        let slipsHtml = '';
        if (order.payment_slips && order.payment_slips.length > 0) {
            slipsHtml = `
                <div style="margin-top: 16px;">
                    <h4 style="margin-bottom: 10px; font-size: 14px;">หลักฐานการชำระเงิน</h4>
                    ${order.payment_slips.map(slip => {
                        const slipStatus = slip.status === 'approved' ? 'อนุมัติ' : slip.status === 'rejected' ? 'ปฏิเสธ' : 'รอตรวจสอบ';
                        const slipColor = slip.status === 'approved' ? '#22c55e' : slip.status === 'rejected' ? '#ef4444' : '#f59e0b';
                        return `
                            <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
                                <img src="${slip.slip_image_url}" style="max-width: 100%; max-height: 200px; border-radius: 6px; cursor: pointer;" onclick="window.open('${slip.slip_image_url}', '_blank')">
                                <div style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                                    <span style="background: ${slipColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px;">${slipStatus}</span>
                                    ${slip.amount ? `<span style="font-size: 12px;">฿${parseFloat(slip.amount).toLocaleString('th-TH')}</span>` : ''}
                                </div>
                                ${slip.status === 'rejected' && slip.notes ? `<div style="font-size: 12px; color: #ef4444; margin-top: 4px;">${escapeHtml(slip.notes)}</div>` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }
        
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
        if (order.status === 'pending_payment' && order.payment_slips && order.payment_slips.some(s => s.status === 'rejected')) {
            const rejectedSlip = order.payment_slips.find(s => s.status === 'rejected');
            if (rejectedSlip && rejectedSlip.notes) {
                rejectionNoticeHtml = `
                    <div style="background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 12px; margin-bottom: 16px;">
                        <div style="color: #ef4444; font-weight: 500; margin-bottom: 4px; font-size: 13px;">⚠️ กรุณาอัพโหลดสลิปใหม่</div>
                        <div style="color: rgba(255,255,255,0.8); font-size: 12px;">เหตุผล: ${escapeHtml(rejectedSlip.notes)}</div>
                    </div>
                `;
            }
        }
        
        let actionsHtml = '';
        if (order.status === 'pending_payment') {
            actionsHtml = `
                <button class="btn" onclick="closeOrderModal(); openPaymentSlipModal(${orderId})" style="width: 100%; margin-top: 16px; padding: 12px; font-size: 14px; background: linear-gradient(135deg, #a855f7, #ec4899);">
                    อัพโหลดสลิปชำระเงิน
                </button>
            `;
        }
        
        const modalHtml = `
            <div id="orderDetailModal" style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px;">
                <div style="background: linear-gradient(135deg, rgba(30,20,50,0.98), rgba(20,10,40,0.98)); border: 1px solid rgba(168,85,247,0.3); border-radius: 16px; max-width: 500px; width: 100%; max-height: 85vh; overflow-y: auto; position: relative;">
                    <button onclick="closeOrderModal()" style="position: absolute; top: 12px; right: 12px; background: none; border: none; color: white; font-size: 24px; cursor: pointer; padding: 5px; line-height: 1;">&times;</button>
                    <div style="padding: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                            <h2 style="font-size: 18px;">${order.order_number || '#' + order.id}</h2>
                            <span style="background: ${statusColors[order.status] || '#6b7280'}; color: white; padding: 4px 12px; border-radius: 6px; font-size: 12px;">${statusLabels[order.status] || order.status}</span>
                        </div>
                        ${rejectionNoticeHtml}
                        <div style="font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 16px;">
                            <div>วันที่: ${new Date(order.created_at).toLocaleString('th-TH')}</div>
                            ${order.notes ? `<div style="margin-top: 4px;">หมายเหตุ: ${escapeHtml(order.notes)}</div>` : ''}
                        </div>
                        <h4 style="margin-bottom: 8px; font-size: 14px;">รายการสินค้า</h4>
                        <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px;">
                            ${itemsHtml || '<p style="opacity: 0.6; text-align: center;">ไม่มีรายการ</p>'}
                            <div style="display: flex; justify-content: space-between; padding-top: 10px; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.2); font-weight: 600;">
                                <span>ยอดรวม</span>
                                <span>฿${(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</span>
                            </div>
                        </div>
                        ${recipientHtml}
                        ${shipmentsHtml}
                        ${slipsHtml}
                        ${actionsHtml}
                    </div>
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

function openPaymentSlipModal(orderId) {
    const modalHtml = `
        <div id="paymentSlipModal" style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 1001; display: flex; align-items: center; justify-content: center; padding: 20px;">
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
            showAlert('อัพโหลดสลิปสำเร็จ รอตรวจสอบ', 'success');
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
        document.getElementById('profilePostalCode').value = profile.postal_code || '';
        
        populateProvinceSelect('profileProvince');
        
        if (profile.province) {
            await setProfileAddressFromText(profile.province, profile.district, profile.subdistrict, profile.postal_code);
        }
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
