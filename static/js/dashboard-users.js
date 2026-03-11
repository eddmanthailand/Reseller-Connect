async function loadUsers() {
    try {
        const response = await fetch(`${API_URL}/users`);
        users = await response.json();
        renderUsers();
    } catch (error) {
        console.error('Error loading users:', error);
        throw error;
    }
}

// Filter users based on search, role, and tier
function getFilteredUsers() {
    const searchTerm = document.getElementById('searchUser')?.value.toLowerCase() || '';
    const roleFilter = document.getElementById('filterRole')?.value || '';
    const tierFilter = document.getElementById('filterTier')?.value || '';
    
    return users.filter(user => {
        // Search filter
        const matchesSearch = !searchTerm || 
            user.full_name.toLowerCase().includes(searchTerm) ||
            user.username.toLowerCase().includes(searchTerm);
        
        // Role filter
        const matchesRole = !roleFilter || user.role === roleFilter;
        
        // Tier filter
        const matchesTier = !tierFilter || user.reseller_tier === tierFilter;
        
        return matchesSearch && matchesRole && matchesTier;
    });
}

// Render brand tags for user
function renderBrandTags(brands) {
    if (!brands || brands.length === 0) {
        return '<span class="no-brands">-</span>';
    }
    
    const maxShow = 2;
    let html = '<div class="brand-tags">';
    
    brands.slice(0, maxShow).forEach(brand => {
        html += `<span class="brand-tag">${brand.name}</span>`;
    });
    
    if (brands.length > maxShow) {
        html += `<span class="brand-tag brand-tag-more">+${brands.length - maxShow}</span>`;
    }
    
    html += '</div>';
    return html;
}

// Render users in table
function renderUsers() {
    if (!userTableBody) return;

    userTableBody.innerHTML = '';
    
    const filteredUsers = getFilteredUsers();
    
    if (filteredUsers.length === 0) {
        userTableBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">ไม่มีข้อมูลผู้ใช้</td></tr>';
        if (userCount) userCount.textContent = '0';
        return;
    }

    filteredUsers.forEach(user => {
        const row = document.createElement('tr');
        
        // Get role badge class
        let badgeClass = 'badge';
        if (user.role === 'Super Admin') badgeClass += ' badge-super-admin';
        else if (user.role === 'Assistant Admin') badgeClass += ' badge-assistant-admin';
        else if (user.role === 'Reseller') badgeClass += ' badge-reseller';
        
        // Brand column content
        let brandColumn = '<span class="no-brands">-</span>';
        if (user.role === 'Assistant Admin') {
            brandColumn = renderBrandTags(user.assigned_brands);
        }
        
        // Actions column
        let actionsHtml = `
            <button class="btn-edit" onclick="openEditUserModal(${user.id})" style="margin-right: 8px;">Edit</button>
            <button class="btn-delete" onclick="deleteUser(${user.id}, '${user.full_name}')">Delete</button>
        `;
        
        // Add assign brand button for Assistant Admin
        if (user.role === 'Assistant Admin') {
            actionsHtml = `
                <button class="btn-assign-brand" onclick="openAssignBrandsModal(${user.id}, '${user.full_name}')" style="margin-right: 6px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/><path d="M7 7h.01"/></svg>
                    แบรนด์
                </button>
                ${actionsHtml}
            `;
        }
        
        row.innerHTML = `
            <td>${user.full_name}</td>
            <td>${user.username}</td>
            <td>
                <span class="${badgeClass}">${user.role}</span>
                ${user.reseller_tier ? `<br><small style="color: rgba(255,255,255,0.6);">Tier: ${user.reseller_tier}</small>` : ''}
            </td>
            <td>${brandColumn}</td>
            <td>${actionsHtml}</td>
        `;
        
        userTableBody.appendChild(row);
    });

    // Update user count
    if (userCount) userCount.textContent = filteredUsers.length;
}

// Update statistics
function updateStats() {
    const totalUsersElement = document.getElementById('totalUsers');
    const adminCountElement = document.getElementById('adminCount');
    const resellerCountElement = document.getElementById('resellerCount');
    const silverCountElement = document.getElementById('silverCount');

    if (totalUsersElement) totalUsersElement.textContent = users.length;
    
    if (adminCountElement) {
        const adminCount = users.filter(u => u.role === 'Super Admin' || u.role === 'Assistant Admin').length;
        adminCountElement.textContent = adminCount;
    }
    
    if (resellerCountElement) {
        const resellerCount = users.filter(u => u.role === 'Reseller').length;
        resellerCountElement.textContent = resellerCount;
    }
    
    if (silverCountElement) {
        const silverCount = users.filter(u => u.reseller_tier === 'Silver').length;
        silverCountElement.textContent = silverCount;
    }
}

// Setup event listeners
function setupEventListeners() {
    // Navigation
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            // Allow external links to navigate normally
            if (item.classList.contains('nav-link-external')) {
                e.preventDefault();
                e.stopPropagation();
                window.open(item.href, '_blank');
                return false;
            }

            const targetPage = item.dataset.page;

            // No data-page means it's a real href link (e.g. /chat) — let browser navigate
            if (!targetPage) return;

            e.preventDefault();
            
            // Handle submenu toggle
            if (item.classList.contains('has-submenu')) {
                item.classList.toggle('expanded');
                const submenu = document.getElementById(`${targetPage}-submenu`);
                if (submenu) {
                    submenu.classList.toggle('open');
                    // If parent has no real page, auto-navigate to first submenu item when opening
                    const hasOwnPage = !!document.getElementById(`page-${targetPage}`);
                    if (!hasOwnPage && submenu.classList.contains('open') && submenu.style.display !== 'none') {
                        const firstChild = submenu.querySelector('.submenu-item[data-page]');
                        if (firstChild) {
                            switchPage(firstChild.dataset.page);
                            return;
                        }
                    }
                }
                if (!document.getElementById(`page-${targetPage}`)) return;
            }
            
            switchPage(targetPage);
        });
    });
    
    // Submenu item navigation
    document.querySelectorAll('.submenu-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetPage = item.dataset.page;
            if (targetPage) {
                switchPage(targetPage);
            }
        });
    });

    // Role selection change
    if (roleSelect) {
        roleSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const roleName = selectedOption.dataset.roleName;
            
            if (roleName === 'Reseller') {
                resellerTierGroup.classList.remove('hidden');
                resellerTierSelect.required = true;
            } else {
                resellerTierGroup.classList.add('hidden');
                resellerTierSelect.required = false;
                resellerTierSelect.value = '';
            }
        });
    }

    // Form submission
    if (createUserForm) {
        createUserForm.addEventListener('submit', handleCreateUser);
    }
    
    // User filter event listeners
    const searchUser = document.getElementById('searchUser');
    const filterRole = document.getElementById('filterRole');
    const filterTier = document.getElementById('filterTier');
    
    if (searchUser) {
        searchUser.addEventListener('input', () => renderUsers());
    }
    if (filterRole) {
        filterRole.addEventListener('change', () => renderUsers());
    }
    if (filterTier) {
        filterTier.addEventListener('change', () => renderUsers());
    }
}

// Navigate to a specific page
function navigateTo(pageName) {
    window.location.hash = pageName;
    switchPage(pageName);
}

// Switch between pages
function switchPage(pageName) {
    if (pageName !== 'quick-order') _labelPasteContext = null;

    // slip-review: dedicated slip review page
    if (pageName === 'slip-review') {
        navItems.forEach(item => item.classList.remove('active'));
        const slipNav = document.getElementById('slipReviewNavItem');
        if (slipNav) slipNav.classList.add('active');
        pages.forEach(page => {
            page.classList.toggle('active', page.id === 'page-slip-review');
        });
        loadSlipReview();
        return;
    }

    // Update navigation
    navItems.forEach(item => {
        if (item.dataset.page === pageName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update content
    pages.forEach(page => {
        if (page.id === `page-${pageName}`) {
            page.classList.add('active');
        } else {
            page.classList.remove('active');
        }
    });

    // Load data based on page
    if (pageName === 'home') {
        loadDashboardStats();
    } else if (pageName === 'products') {
        loadProducts();
    } else if (pageName === 'orders') {
        loadOrders();
    } else if (pageName === 'shipping-update') {
        loadShippingUpdatePage();
    } else if (pageName === 'tier-settings') {
        loadTierSettings();
        loadResellers();
    } else if (pageName === 'settings') {
        loadSettings();
    } else if (pageName === 'facebook-ads') {
        loadFacebookAdsPage();
    } else if (pageName === 'brands') {
        loadBrandsPage();
    } else if (pageName === 'categories') {
        loadCategoriesPage();
    } else if (pageName === 'warehouses') {
        loadWarehousesPage();
    } else if (pageName === 'stock-summary') {
        loadStockSummaryPage();
    } else if (pageName === 'stock-transfer') {
        loadStockTransferPage();
    } else if (pageName === 'stock-adjustment') {
        loadStockAdjustmentPage();
    } else if (pageName === 'stock-import') {
        // Stock import page doesn't need initial data load
    } else if (pageName === 'stock-history') {
        loadStockHistoryPage();
    } else if (pageName === 'quick-order') {
        loadQuickOrderPage();
    } else if (pageName === 'shipping-settings') {
        loadShippingSettingsPage();
    } else if (pageName === 'activity-logs') {
        loadActivityLogs();
    } else if (pageName === 'mto-products') {
        loadMtoProducts();
    } else if (pageName === 'mto-requests') {
        loadMtoRequests();
        loadMtoStats();
    } else if (pageName === 'mto-quotations') {
        loadMtoQuotations();
    } else if (pageName === 'mto-orders') {
        loadMtoOrders();
    } else if (pageName === 'mto-payments') {
        loadMtoPayments();
    } else if (pageName === 'chat') {
        loadChatThreadsAndAutoSelect();
        loadChatUnreadCount();
        startChatPolling();
        loadGlobalBotStatus();
    } else if (pageName === 'promotions') {
        loadPromotions();
    } else if (pageName === 'coupons') {
        loadCoupons();
    } else if (pageName === 'customers') {
        loadCustomers();
    }
}

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'NOTIFICATION_CLICK') {
            const hash = event.data.hash || '';
            if (hash) {
                const pageName = hash.replace('#', '');
                window.location.hash = pageName;
                switchPage(pageName);
            }
        }
    });
}

window.openChatThread = async function(threadId) {
    switchPage('chat');
    const threads = await loadChatThreads();
    if (threads && threads.length > 0) {
        const target = threads.find(t => t.id === threadId);
        if (target) {
            selectChatThread(target.id, target.reseller_name, target.tier_name || '', target.reseller_tier_id || null, target.bot_paused || false);
        }
    }
};

// Handle create user form submission
async function handleCreateUser(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const userData = {
        full_name: formData.get('fullName'),
        username: formData.get('username'),
        password: formData.get('password'),
        role_id: parseInt(formData.get('role'))
    };

    // Add reseller tier if role is Reseller
    const selectedRole = roleSelect.options[roleSelect.selectedIndex];
    if (selectedRole.dataset.roleName === 'Reseller') {
        const tierValue = formData.get('resellerTier');
        if (tierValue) {
            userData.reseller_tier_id = parseInt(tierValue);
        }
    }

    try {
        const response = await fetch(`${API_URL}/users`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });

        const result = await response.json();

        if (response.ok) {
            showAlert('สร้างผู้ใช้สำเร็จ!', 'success');
            event.target.reset();
            resellerTierGroup.classList.add('hidden');
            await loadUsers();
            updateStats();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error creating user:', error);
        showAlert('เกิดข้อผิดพลาดในการสร้างผู้ใช้', 'error');
    }
}

// Delete user
async function deleteUser(userId, userName) {
    if (!confirm(`คุณต้องการลบผู้ใช้ "${userName}" ใช่หรือไม่?`)) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/users/${userId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok) {
            showAlert('ลบผู้ใช้สำเร็จ!', 'success');
            await loadUsers();
            updateStats();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showAlert('เกิดข้อผิดพลาดในการลบผู้ใช้', 'error');
    }
}

// Open edit user modal
async function openEditUserModal(userId) {
    const modal = document.getElementById('editUserModal');
    if (!modal) return;
    
    try {
        const response = await fetch(`${API_URL}/users/${userId}`);
        if (!response.ok) throw new Error('Failed to load user');
        
        const user = await response.json();
        
        document.getElementById('editUserId').value = user.id;
        document.getElementById('editFullName').value = user.full_name;
        document.getElementById('editUsername').value = user.username;
        document.getElementById('editPassword').value = '';
        
        const editRoleSelect = document.getElementById('editRole');
        editRoleSelect.innerHTML = '';
        roles.forEach(role => {
            const option = document.createElement('option');
            option.value = role.id;
            option.textContent = role.name;
            option.dataset.roleName = role.name;
            if (role.id === user.role_id) option.selected = true;
            editRoleSelect.appendChild(option);
        });
        
        const editTierSelect = document.getElementById('editResellerTier');
        const editTierGroup = document.getElementById('editResellerTierGroup');
        const editManualOverrideGroup = document.getElementById('editManualOverrideGroup');
        const editManualOverride = document.getElementById('editManualOverride');
        
        editTierSelect.innerHTML = '<option value="">-- เลือก Tier --</option>';
        resellerTiers.forEach(tier => {
            const option = document.createElement('option');
            option.value = tier.id;
            option.textContent = tier.name;
            if (tier.id === user.reseller_tier_id) option.selected = true;
            editTierSelect.appendChild(option);
        });
        
        editManualOverride.checked = user.tier_manual_override === true;
        
        const shippingSection = document.getElementById('editResellerShippingSection');
        
        if (user.role === 'Reseller') {
            editTierGroup.classList.remove('hidden');
            editManualOverrideGroup.classList.remove('hidden');
            if (shippingSection) shippingSection.classList.remove('hidden');
            
            document.getElementById('editBrandName').value = user.brand_name || '';
            document.getElementById('editPhone').value = user.phone || '';
            document.getElementById('editEmail').value = user.email || '';
            document.getElementById('editAddress').value = user.address || '';
            document.getElementById('editSubdistrict').value = user.subdistrict || '';
            document.getElementById('editDistrict').value = user.district || '';
            document.getElementById('editProvince').value = user.province || '';
            document.getElementById('editPostalCode').value = user.postal_code || '';
        } else {
            editTierGroup.classList.add('hidden');
            editManualOverrideGroup.classList.add('hidden');
            if (shippingSection) shippingSection.classList.add('hidden');
        }
        
        editRoleSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption.dataset.roleName === 'Reseller') {
                editTierGroup.classList.remove('hidden');
                editManualOverrideGroup.classList.remove('hidden');
                if (shippingSection) shippingSection.classList.remove('hidden');
            } else {
                editTierGroup.classList.add('hidden');
                editManualOverrideGroup.classList.add('hidden');
                if (shippingSection) shippingSection.classList.add('hidden');
            }
        });
        
        modal.classList.add('active');
    } catch (error) {
        console.error('Error loading user:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูลผู้ใช้', 'error');
    }
}

// Close edit user modal
function closeEditUserModal() {
    const modal = document.getElementById('editUserModal');
    if (modal) modal.classList.remove('active');
}

// Handle edit user form submission
async function handleEditUser(event) {
    event.preventDefault();
    
    const userId = document.getElementById('editUserId').value;
    const editRoleSelect = document.getElementById('editRole');
    const selectedRole = editRoleSelect.options[editRoleSelect.selectedIndex];
    
    const userData = {
        full_name: document.getElementById('editFullName').value,
        username: document.getElementById('editUsername').value,
        role_id: parseInt(editRoleSelect.value)
    };
    
    const password = document.getElementById('editPassword').value;
    if (password) userData.password = password;
    
    if (selectedRole.dataset.roleName === 'Reseller') {
        const tierValue = document.getElementById('editResellerTier').value;
        userData.reseller_tier_id = tierValue ? parseInt(tierValue) : null;
        userData.tier_manual_override = document.getElementById('editManualOverride').checked;
        
        userData.brand_name = document.getElementById('editBrandName').value;
        userData.phone = document.getElementById('editPhone').value;
        userData.email = document.getElementById('editEmail').value;
        userData.address = document.getElementById('editAddress').value;
        userData.subdistrict = document.getElementById('editSubdistrict').value;
        userData.district = document.getElementById('editDistrict').value;
        userData.province = document.getElementById('editProvince').value;
        userData.postal_code = document.getElementById('editPostalCode').value;
    } else {
        userData.reseller_tier_id = null;
        userData.tier_manual_override = false;
    }
    
    try {
        const response = await fetch(`${API_URL}/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('แก้ไขผู้ใช้สำเร็จ!', 'success');
            closeEditUserModal();
            await loadUsers();
            updateStats();
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error updating user:', error);
        showAlert('เกิดข้อผิดพลาดในการแก้ไขผู้ใช้', 'error');
    }
}

// ===== Slip Review Functions =====

let _rejectTargetOrderId = null;

async function loadSlipReview() {
    const container = document.getElementById('slipReviewGrid');
    if (!container) return;
    container.innerHTML = '<div class="slip-empty-state"><p>กำลังโหลด...</p></div>';
    try {
        const res = await fetch('/api/admin/orders?status=under_review');
        if (!res.ok) throw new Error('Failed');
        const data = await res.json();
        const orders = data.orders || (Array.isArray(data) ? data : []);
        renderSlipCards(orders);
        const badge = document.getElementById('slipReviewBadge');
        if (badge) {
            badge.textContent = orders.length;
            badge.style.display = orders.length > 0 ? 'inline-flex' : 'none';
        }
    } catch (e) {
        container.innerHTML = '<div class="slip-empty-state"><p>โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่</p></div>';
    }
}

function renderSlipCards(orders) {
    const container = document.getElementById('slipReviewGrid');
    if (!container) return;

    if (!orders.length) {
        container.innerHTML = `
            <div class="slip-empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
                </svg>
                <p style="font-size:16px;font-weight:600;margin:0 0 4px;">ไม่มีสลิปรอตรวจสอบ</p>
                <p style="font-size:13px;opacity:0.6;margin:0;">สลิปใหม่จะปรากฏที่นี่เมื่อ reseller อัปโหลด</p>
            </div>`;
        return;
    }

    container.innerHTML = orders.map(o => {
        const dateStr = o.slip_created_at
            ? new Date(o.slip_created_at).toLocaleString('th-TH', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
            : '-';
        const amount = (o.slip_amount || o.final_amount || 0).toLocaleString('th-TH', { minimumFractionDigits: 2 });
        const imgHtml = o.slip_image_url
            ? `<img src="${o.slip_image_url}" class="slip-card-img" onclick="window.open('${o.slip_image_url}','_blank')" alt="สลิป" loading="lazy">`
            : `<div class="slip-card-no-img">ไม่มีรูปสลิป</div>`;

        return `
            <div class="slip-card">
                <div class="slip-card-header">
                    <div class="slip-card-top">
                        <div>
                            <div class="slip-card-order-num">${o.order_number || '#' + o.id}</div>
                            <div class="slip-card-reseller">${o.reseller_name || o.username || '-'}</div>
                        </div>
                        <div class="slip-card-amount">฿${amount}</div>
                    </div>
                    <div class="slip-card-date">ส่งสลิปเมื่อ ${dateStr}</div>
                </div>
                <div class="slip-card-img-wrap">${imgHtml}</div>
                <div class="slip-card-actions">
                    <button class="slip-btn-approve" onclick="approveSlip(${o.id})">✓ อนุมัติ</button>
                    <button class="slip-btn-reject" onclick="openRejectModal(${o.id})">✗ ปฏิเสธ</button>
                </div>
            </div>`;
    }).join('');
}

async function approveSlip(orderId) {
    if (!confirm('ยืนยันการอนุมัติสลิปนี้?\nสถานะจะเปลี่ยนเป็น "เตรียมสินค้า" และแจ้ง reseller ทันที')) return;
    try {
        const res = await fetch(`/api/admin/orders/${orderId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (res.ok) {
            showGlobalAlert('อนุมัติสลิปสำเร็จ — สถานะเปลี่ยนเป็นเตรียมสินค้า', 'success');
            loadSlipReview();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (e) {
        showGlobalAlert('เกิดข้อผิดพลาด กรุณาลองใหม่', 'error');
    }
}

function openRejectModal(orderId) {
    _rejectTargetOrderId = orderId;
    const modal = document.getElementById('rejectSlipModal');
    const input = document.getElementById('rejectReasonInput');
    if (input) input.value = '';
    if (modal) { modal.style.display = 'flex'; setTimeout(() => input && input.focus(), 100); }
}

function closeRejectModal() {
    _rejectTargetOrderId = null;
    const modal = document.getElementById('rejectSlipModal');
    if (modal) modal.style.display = 'none';
}

async function confirmRejectSlip() {
    if (!_rejectTargetOrderId) return;
    const reason = (document.getElementById('rejectReasonInput')?.value || '').trim();
    const orderId = _rejectTargetOrderId;
    closeRejectModal();
    try {
        const res = await fetch(`/api/admin/orders/${orderId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        const data = await res.json();
        if (res.ok) {
            showGlobalAlert('ปฏิเสธสลิปแล้ว — reseller จะได้รับการแจ้งเตือน', 'success');
            loadSlipReview();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (e) {
        showGlobalAlert('เกิดข้อผิดพลาด กรุณาลองใหม่', 'error');
    }
}

// Product Management State
