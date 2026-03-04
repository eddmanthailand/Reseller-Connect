// API Base URL (use window.API_URL set by template, fallback to '/api')
const API_URL = (typeof window !== 'undefined' && window.API_URL) ? window.API_URL : '/api';

// CSRF Token management
let csrfToken = null;

async function fetchCsrfToken() {
    try {
        const response = await fetch(`${API_URL}/csrf-token`, { credentials: 'include' });
        if (response.ok) {
            const data = await response.json();
            csrfToken = data.csrf_token;
        }
    } catch (error) {
        console.error('Failed to fetch CSRF token:', error);
    }
}

function getSecureFetchOptions(options = {}) {
    const headers = options.headers || {};
    if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
    }
    return {
        ...options,
        credentials: 'include',
        headers: headers
    };
}

// Utility function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Sidebar Toggle Function (Desktop)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const body = document.body;
    
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
        body.classList.toggle('sidebar-collapsed');
        
        // Save state to localStorage
        const isCollapsed = sidebar.classList.contains('collapsed');
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }
}

// Mobile Sidebar Toggle Function
function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    if (sidebar) {
        sidebar.classList.toggle('open');
        sidebar.classList.toggle('active');
    }
    if (overlay) {
        overlay.classList.toggle('active');
    }
}

// Restore sidebar state on page load
function restoreSidebarState() {
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    const sidebar = document.getElementById('sidebar');
    const body = document.body;
    
    if (isCollapsed && sidebar) {
        sidebar.classList.add('collapsed');
        body.classList.add('sidebar-collapsed');
    }
}

// Toggle submenu
function toggleSubmenu(element, event) {
    event.preventDefault();
    element.classList.toggle('open');
    // Get next sibling element which should be the submenu div
    const submenu = element.nextElementSibling;
    if (submenu && submenu.classList.contains('submenu')) {
        submenu.classList.toggle('open');
    }
}

// Global data
let roles = [];
let resellerTiers = [];
let users = [];

// DOM Elements - Form and User List
const roleSelect = document.getElementById('role');
const resellerTierSelect = document.getElementById('resellerTier');
const resellerTierGroup = document.getElementById('resellerTierGroup');
const createUserForm = document.getElementById('createUserForm');
const userTableBody = document.getElementById('userTableBody');
const alertBox = document.getElementById('alertBox');
const userCount = document.getElementById('userCount');

// Navigation
const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page-content');

// Initialize the application
async function init() {
    try {
        // Restore sidebar state first
        restoreSidebarState();
        
        // Fetch CSRF token for secure requests
        await fetchCsrfToken();
        
        await loadCurrentUser();
        await Promise.all([
            loadRoles(),
            loadResellerTiers(),
            loadUsers()
        ]);
        setupEventListeners();
        updateStats();
        
        // Load dashboard stats on init
        loadDashboardStats();
        
        // Load low stock badge
        loadLowStockBadge();
        
        // Handle hash navigation (e.g., /admin#products)
        handleHashNavigation();
        
        // Listen for hash changes
        window.addEventListener('hashchange', handleHashNavigation);

        // Global chat badge polling — runs on every page
        loadChatUnreadCount();
        setInterval(loadChatUnreadCount, 15000);
    } catch (error) {
        console.error('Initialization error:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
    }
}

// Handle hash navigation to switch pages
function handleHashNavigation() {
    const fullHash = window.location.hash.substring(1); // Remove the '#'
    if (fullHash) {
        // Extract page name before any query parameters
        const [pageName, queryString] = fullHash.split('?');
        const validPages = ['home', 'users', 'products', 'brands', 'categories', 'warehouses', 'stock-summary', 'stock-transfer', 'stock-adjustment', 'stock-import', 'stock-history', 'orders', 'shipping-update', 'quick-order', 'tier-settings', 'settings', 'facebook-ads', 'chat', 'mto-products', 'mto-requests', 'mto-quotations', 'mto-orders', 'mto-payments', 'activity-logs', 'shipping-settings', 'promotions', 'coupons'];
        if (validPages.includes(pageName)) {
            switchPage(pageName);
            // Auto-open order detail if order_id param is present
            if (pageName === 'orders' && queryString) {
                const params = new URLSearchParams(queryString);
                const orderId = params.get('order_id');
                if (orderId) {
                    setTimeout(() => viewOrderDetails(parseInt(orderId)), 600);
                    history.replaceState(null, '', window.location.pathname + '#orders');
                }
            }
        }
    }
}

// Load current user info
let currentUserRole = null;

async function loadCurrentUser() {
    try {
        const response = await fetch(`${API_URL}/me`);
        if (!response.ok) {
            throw new Error('Not authenticated');
        }
        const user = await response.json();
        currentUserRole = user.role;
        const currentUserElement = document.getElementById('currentUser');
        if (currentUserElement) {
            currentUserElement.textContent = `${user.full_name} (${user.role})`;
        }
        
        // Apply role-based UI restrictions
        applyRoleBasedUI(user.role);
        if (typeof agentInitVisibility === 'function') agentInitVisibility(user.role);
    } catch (error) {
        console.error('Error loading current user:', error);
        if (error.message === 'Not authenticated') {
            window.location.href = '/login';
        }
    }
}

function applyRoleBasedUI(role) {
    // Hide menu items restricted to Super Admin
    if (role !== 'Super Admin') {
        // Hide nav items with data-role="Super Admin"
        document.querySelectorAll('[data-role="Super Admin"]').forEach(el => {
            el.style.display = 'none';
        });
        
        // Hide user stats row on dashboard (for Assistant Admin)
        const userStatsRow = document.querySelector('.user-stats-row');
        if (userStatsRow) {
            userStatsRow.style.display = 'none';
        }
        
        // Remove has-submenu class from products menu since submenu is hidden
        const productsNav = document.querySelector('[data-page="products"]');
        if (productsNav) {
            productsNav.classList.remove('has-submenu');
        }
    }
}

// Handle logout
function handleLogout() {
    showConfirmAlert('คุณต้องการออกจากระบบหรือไม่?', () => {
        window.location.href = '/logout';
    });
}

// Load roles from API
async function loadRoles() {
    try {
        const response = await fetch(`${API_URL}/roles`);
        roles = await response.json();
        
        if (roleSelect) {
            // Clear existing options
            roleSelect.innerHTML = '<option value="">-- เลือกบทบาท --</option>';
            
            // Populate role dropdown
            roles.forEach(role => {
                const option = document.createElement('option');
                option.value = role.id;
                option.textContent = role.name;
                option.dataset.roleName = role.name;
                roleSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading roles:', error);
        throw error;
    }
}

// Load reseller tiers from API
async function loadResellerTiers() {
    try {
        const response = await fetch(`${API_URL}/reseller-tiers`);
        resellerTiers = await response.json();
        
        if (resellerTierSelect) {
            // Clear existing options
            resellerTierSelect.innerHTML = '<option value="">-- เลือก Tier --</option>';
            
            // Populate tier dropdown
            resellerTiers.forEach(tier => {
                const option = document.createElement('option');
                option.value = tier.id;
                option.textContent = tier.name;
                resellerTierSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading reseller tiers:', error);
        throw error;
    }
}

// Load users from API
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
            selectChatThread(target.id, target.reseller_name, target.tier_name || '', target.reseller_tier_id || null);
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

// Product Management State
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

// ==========================================
// Tier Settings Page Functions
// ==========================================

let tierData = [];

async function loadTierSettings() {
    const container = document.getElementById('tiersContainer');
    
    try {
        const response = await fetch(`${API_URL}/reseller-tiers`);
        tierData = await response.json();
        
        renderTierCards();
    } catch (error) {
        console.error('Error loading tiers:', error);
        container.innerHTML = '<div style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</div>';
    }
}

function renderTierCards() {
    const container = document.getElementById('tiersContainer');
    
    const tierColors = {
        'Bronze': 'bronze',
        'Silver': 'silver',
        'Gold': 'gold',
        'Platinum': 'platinum'
    };
    
    let html = '';
    
    tierData.forEach(tier => {
        const colorClass = tierColors[tier.name] || 'bronze';
        html += `
            <div class="tier-card">
                <div class="tier-header">
                    <span class="tier-badge ${colorClass}">${tier.name}</span>
                    <span class="tier-level">ระดับ ${tier.level_rank || 1}</span>
                </div>
                <div class="tier-form-row">
                    <label>ยอดซื้อขั้นต่ำ</label>
                    <div class="threshold-input-wrapper">
                        <input type="number" class="tier-input threshold-input" 
                               data-tier-id="${tier.id}" 
                               value="${tier.upgrade_threshold || 0}" 
                               min="0">
                        <span class="threshold-suffix">บาท</span>
                    </div>
                </div>
                <div class="tier-form-row">
                    <label>รายละเอียด</label>
                    <input type="text" class="tier-input description-input" 
                           data-tier-id="${tier.id}" 
                           value="${tier.description || ''}" 
                           placeholder="คำอธิบายระดับ (ไม่จำเป็น)">
                </div>
                <p class="info-text">ตัวแทนที่มียอดซื้อสะสมตั้งแต่ ${(tier.upgrade_threshold || 0).toLocaleString()} บาท จะได้รับระดับนี้</p>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

async function saveAllTiers() {
    const thresholdInputs = document.querySelectorAll('.threshold-input');
    const descriptionInputs = document.querySelectorAll('.description-input');
    
    const updates = [];
    thresholdInputs.forEach(input => {
        const tierId = input.dataset.tierId;
        const threshold = parseInt(input.value) || 0;
        const descInput = document.querySelector(`.description-input[data-tier-id="${tierId}"]`);
        const description = descInput ? descInput.value : '';
        
        updates.push({
            id: parseInt(tierId),
            upgrade_threshold: threshold,
            description: description
        });
    });
    
    try {
        const response = await fetch(`${API_URL}/reseller-tiers/bulk`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tiers: updates })
        });
        
        if (response.ok) {
            showTierAlert('บันทึกการตั้งค่าสำเร็จ', 'success');
            loadTierSettings();
        } else {
            const error = await response.json();
            showTierAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving tiers:', error);
        showTierAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function loadResellers() {
    const tableBody = document.getElementById('resellersTableBody');
    
    try {
        const response = await fetch(`${API_URL}/resellers`);
        const resellers = await response.json();
        
        if (resellers.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; opacity: 0.6;">ไม่มีข้อมูลตัวแทน</td></tr>';
            return;
        }
        
        const tierColors = {
            'Bronze': 'bronze',
            'Silver': 'silver',
            'Gold': 'gold',
            'Platinum': 'platinum'
        };
        
        let html = '';
        resellers.forEach(r => {
            const colorClass = tierColors[r.tier_name] || 'bronze';
            const manualBadge = r.tier_manual_override ? '<span class="manual-badge">Manual</span>' : '';
            
            html += `
                <tr>
                    <td>${r.username}</td>
                    <td>${r.full_name}</td>
                    <td><span class="tier-badge ${colorClass}">${r.tier_name}</span></td>
                    <td>${(r.total_purchases || 0).toLocaleString()} บาท</td>
                    <td>${manualBadge || '<span style="opacity: 0.5;">Auto</span>'}</td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    } catch (error) {
        console.error('Error loading resellers:', error);
        tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

async function checkAllUpgrades() {
    const resultDiv = document.getElementById('upgradeResult');
    resultDiv.innerHTML = '<p style="opacity: 0.6;">กำลังตรวจสอบ...</p>';
    
    try {
        const response = await fetch(`${API_URL}/users/check-tier-upgrades`, { method: 'POST' });
        const result = await response.json();
        
        if (result.upgraded && result.upgraded.length > 0) {
            let html = '<div class="upgrade-result"><h4>อัปเกรดสำเร็จ:</h4><ul>';
            result.upgraded.forEach(u => {
                html += `<li>${u.full_name}: ${u.old_tier} → ${u.new_tier}</li>`;
            });
            html += '</ul></div>';
            resultDiv.innerHTML = html;
            loadResellers();
        } else {
            resultDiv.innerHTML = '<p style="color: rgba(255,255,255,0.6); padding: 16px;">ไม่มีตัวแทนที่ต้องอัปเกรด</p>';
        }
        
        setTimeout(() => { resultDiv.innerHTML = ''; }, 5000);
    } catch (error) {
        console.error('Error checking upgrades:', error);
        resultDiv.innerHTML = '<p style="color: #ef4444;">เกิดข้อผิดพลาด</p>';
    }
}

function showTierAlert(message, type) {
    const alertBox = document.getElementById('tierAlertBox');
    if (!alertBox) return;
    
    alertBox.textContent = message;
    alertBox.className = `alert alert-${type}`;
    alertBox.style.display = 'block';
    
    setTimeout(() => { alertBox.style.display = 'none'; }, 3000);
}

// ==========================================
// Settings Page Functions
// ==========================================

let promptPayQrFile = null;
let salesChannels = [];

async function loadSettings() {
    loadPromptPaySettings();
    loadOrderNumberSettings();
    loadFacebookPixelSettings();
    loadChannels();
}

// ==================== FACEBOOK PIXEL SETTINGS ====================

async function loadFacebookPixelSettings() {
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('Loaded Facebook Pixel settings:', data);
            
            if (data.pixel_id) {
                document.getElementById('fbPixelId').value = data.pixel_id;
            }
            if (data.is_active !== undefined) {
                document.getElementById('fbPixelActive').checked = data.is_active;
            }
        }
    } catch (error) {
        console.error('Error loading Facebook Pixel settings:', error);
    }
}

async function saveFacebookPixelSettings() {
    const pixelId = document.getElementById('fbPixelId').value.trim();
    const accessToken = document.getElementById('fbAccessToken').value.trim();
    const isActive = document.getElementById('fbPixelActive').checked;
    
    if (isActive && !pixelId) {
        showAlert('กรุณากรอก Pixel ID ก่อนเปิดใช้งาน', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                pixel_id: pixelId,
                access_token: accessToken,
                is_active: isActive,
                track_page_view: true,
                track_lead: true,
                track_complete_registration: true
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('บันทึกการตั้งค่า Facebook Pixel สำเร็จ', 'success');
            // Clear access token field after save for security
            document.getElementById('fbAccessToken').value = '';
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving Facebook Pixel settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

// ==================== FACEBOOK ADS PAGE ====================

let fbAdsChart = null;

async function loadFacebookAdsPage() {
    // Set Landing Page URL - use custom domain
    const urlInput = document.getElementById('fbLandingUrl');
    if (urlInput) {
        urlInput.value = 'https://ekgshops.com/join';
    }
    
    // Load Pixel settings
    loadFbAdsPixelSettings();
    
    // Load stats
    loadFacebookAdsStats();
}

async function loadFbAdsPixelSettings() {
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            
            if (data.pixel_id) {
                const pixelInput = document.getElementById('fbAdsPixelId');
                if (pixelInput) pixelInput.value = data.pixel_id;
            }
            if (data.is_active !== undefined) {
                const activeCheck = document.getElementById('fbAdsPixelActive');
                if (activeCheck) activeCheck.checked = data.is_active;
            }
        }
    } catch (error) {
        console.error('Error loading Facebook Pixel settings:', error);
    }
}

async function saveFbAdsPixelSettings() {
    const pixelId = document.getElementById('fbAdsPixelId').value.trim();
    const accessToken = document.getElementById('fbAdsAccessToken').value.trim();
    const isActive = document.getElementById('fbAdsPixelActive').checked;
    
    if (isActive && !pixelId) {
        showAlert('กรุณากรอก Pixel ID ก่อนเปิดใช้งาน', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                pixel_id: pixelId,
                access_token: accessToken,
                is_active: isActive,
                track_page_view: true,
                track_lead: true,
                track_complete_registration: true
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('บันทึกการตั้งค่า Facebook Pixel สำเร็จ', 'success');
            document.getElementById('fbAdsAccessToken').value = '';
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving Facebook Pixel settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function loadFacebookAdsStats() {
    try {
        const response = await fetch(`${API_URL}/facebook-ads/stats`, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            console.error('Failed to load Facebook Ads stats');
            return;
        }
        
        const data = await response.json();
        
        // Update stats cards
        document.getElementById('fbStatsTodayVisits').textContent = data.today.visits;
        document.getElementById('fbStatsTodayRegs').textContent = data.today.registrations;
        document.getElementById('fbStatsTodayConv').textContent = data.today.conversion + '%';
        
        document.getElementById('fbStatsWeekVisits').textContent = data.week.visits;
        document.getElementById('fbStatsWeekRegs').textContent = data.week.registrations;
        document.getElementById('fbStatsWeekConv').textContent = data.week.conversion + '%';
        
        document.getElementById('fbStatsMonthVisits').textContent = data.month.visits;
        document.getElementById('fbStatsMonthRegs').textContent = data.month.registrations;
        document.getElementById('fbStatsMonthConv').textContent = data.month.conversion + '%';
        
        document.getElementById('fbStatsTotalVisits').textContent = data.total.visits;
        document.getElementById('fbStatsTotalRegs').textContent = data.total.registrations;
        document.getElementById('fbStatsTotalConv').textContent = data.total.conversion + '%';
        
        // Update chart
        renderFbAdsChart(data.chart);
        
        // Update recent registrations table
        renderFbRecentRegistrations(data.recent_registrations);
        
    } catch (error) {
        console.error('Error loading Facebook Ads stats:', error);
    }
}

function renderFbAdsChart(chartData) {
    const ctx = document.getElementById('fbAdsChart');
    if (!ctx) return;
    
    if (fbAdsChart) {
        fbAdsChart.destroy();
    }
    
    fbAdsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: 'ผู้เข้าชม',
                    data: chartData.visits,
                    borderColor: '#1877f2',
                    backgroundColor: 'rgba(24, 119, 242, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'สมัคร',
                    data: chartData.registrations,
                    borderColor: '#42b72a',
                    backgroundColor: 'rgba(66, 183, 42, 0.1)',
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: 'rgba(255,255,255,0.7)' }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: 'rgba(255,255,255,0.5)' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                x: {
                    ticks: { color: 'rgba(255,255,255,0.5)' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                }
            }
        }
    });
}

function renderFbRecentRegistrations(registrations) {
    const tbody = document.getElementById('fbRecentRegistrations');
    if (!tbody) return;
    
    if (!registrations || registrations.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; opacity: 0.5;">ยังไม่มีผู้สมัครจาก Facebook Ads</td></tr>';
        return;
    }
    
    tbody.innerHTML = registrations.map(reg => {
        const date = new Date(reg.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
        const statusBadge = reg.is_approved 
            ? '<span style="background: rgba(34,197,94,0.2); color: #22c55e; padding: 2px 8px; border-radius: 4px; font-size: 11px;">อนุมัติแล้ว</span>'
            : '<span style="background: rgba(251,191,36,0.2); color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-size: 11px;">รออนุมัติ</span>';
        
        return `<tr>
            <td>${reg.full_name || '-'}</td>
            <td>${reg.username}</td>
            <td>${date}</td>
            <td>${statusBadge}</td>
        </tr>`;
    }).join('');
}

function copyLandingUrl() {
    const urlInput = document.getElementById('fbLandingUrl');
    if (urlInput) {
        urlInput.select();
        navigator.clipboard.writeText(urlInput.value).then(() => {
            showAlert('คัดลอก URL สำเร็จ', 'success');
        }).catch(() => {
            document.execCommand('copy');
            showAlert('คัดลอก URL สำเร็จ', 'success');
        });
    }
}

async function loadPromptPaySettings() {
    try {
        const response = await fetch(`${API_URL}/promptpay-settings`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('Loaded PromptPay settings:', data);
            
            if (data.account_name) {
                document.getElementById('accountName').value = data.account_name;
            }
            if (data.account_number) {
                document.getElementById('accountNumber').value = data.account_number;
            }
            if (data.qr_image_url) {
                const preview = document.getElementById('qrPreview');
                const placeholder = document.getElementById('qrPlaceholder');
                preview.src = data.qr_image_url;
                preview.style.display = 'block';
                if (placeholder) placeholder.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading PromptPay settings:', error);
    }
}

async function loadChannels() {
    const container = document.getElementById('channelList');
    
    try {
        const response = await fetch(`${API_URL}/sales-channels`);
        salesChannels = await response.json();
        
        if (salesChannels.length === 0) {
            container.innerHTML = '<p style="text-align: center; opacity: 0.6;">ยังไม่มีช่องทางการขาย</p>';
            return;
        }
        
        let html = '';
        salesChannels.forEach(channel => {
            html += `
                <div class="channel-item">
                    <div class="channel-info">
                        <span class="channel-name">${channel.name}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <label class="toggle-switch">
                            <input type="checkbox" ${channel.is_active ? 'checked' : ''} onchange="toggleChannel(${channel.id}, this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                        <button class="btn-icon delete" onclick="deleteChannel(${channel.id})">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/></svg>
                        </button>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading channels:', error);
        container.innerHTML = '<p style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</p>';
    }
}

async function addChannel() {
    const nameInput = document.getElementById('newChannelName');
    const name = nameInput.value.trim();
    
    if (!name) {
        showAlert('กรุณากรอกชื่อช่องทาง', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/sales-channels`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        
        if (response.ok) {
            nameInput.value = '';
            loadChannels();
            showAlert('เพิ่มช่องทางสำเร็จ', 'success');
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error adding channel:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function toggleChannel(channelId, isActive) {
    try {
        await fetch(`${API_URL}/sales-channels/${channelId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });
    } catch (error) {
        console.error('Error toggling channel:', error);
    }
}

async function deleteChannel(channelId) {
    if (!confirm('ลบช่องทางนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/sales-channels/${channelId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadChannels();
            showAlert('ลบช่องทางสำเร็จ', 'success');
        }
    } catch (error) {
        console.error('Error deleting channel:', error);
    }
}

// PromptPay form submit handler
async function savePromptPaySettings() {
    console.log('savePromptPaySettings called');
    
    const accountName = document.getElementById('accountName').value;
    const accountNumber = document.getElementById('accountNumber').value;
    
    console.log('Saving PromptPay:', { accountName, accountNumber });
    
    try {
        let qrUrl = null;
        
        if (promptPayQrFile) {
            const formData = new FormData();
            formData.append('file', promptPayQrFile);
            formData.append('type', 'promptpay_qr');
            
            const uploadResponse = await fetch(`${API_URL}/upload`, {
                method: 'POST',
                credentials: 'include',
                body: formData
            });
            
            if (uploadResponse.ok) {
                const uploadResult = await uploadResponse.json();
                qrUrl = uploadResult.url;
            }
        }
        
        const settingsData = {
            account_name: accountName,
            account_number: accountNumber
        };
        if (qrUrl) settingsData.qr_image_url = qrUrl;
        
        console.log('Sending data:', settingsData);
        
        const response = await fetch(`${API_URL}/promptpay-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(settingsData)
        });
        
        console.log('Response status:', response.status);
        
        if (response.ok) {
            const result = await response.json();
            console.log('Save success:', result);
            showAlert('บันทึกการตั้งค่า PromptPay สำเร็จ', 'success');
            promptPayQrFile = null;
        } else {
            const errorText = await response.text();
            console.error('Save failed:', response.status, errorText);
            try {
                const error = JSON.parse(errorText);
                showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
            } catch {
                showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
            }
        }
    } catch (error) {
        console.error('Error saving PromptPay settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

// ==================== ORDER NUMBER SETTINGS ====================

async function loadOrderNumberSettings() {
    const prefixInput = document.getElementById('orderPrefix');
    const digitSelect = document.getElementById('orderDigitCount');
    const previewDiv = document.getElementById('orderNumberPreview');
    
    if (!prefixInput || !digitSelect || !previewDiv) return;
    
    try {
        const response = await fetch(`${API_URL}/order-number-settings`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            prefixInput.value = data.prefix || 'ORD';
            digitSelect.value = data.digit_count || 4;
            previewDiv.textContent = data.preview || 'ORD-2512-0001';
        } else {
            console.error('Failed to load order number settings:', response.status);
            updateOrderPreview();
        }
    } catch (error) {
        console.error('Error loading order number settings:', error);
        updateOrderPreview();
    }
}

function updateOrderPreview() {
    const prefix = document.getElementById('orderPrefix').value.toUpperCase().trim() || 'ORD';
    const digitCount = parseInt(document.getElementById('orderDigitCount').value) || 4;
    
    const now = new Date();
    const yymm = String(now.getFullYear()).slice(-2) + String(now.getMonth() + 1).padStart(2, '0');
    const sequence = '1'.padStart(digitCount, '0');
    
    const preview = `${prefix}-${yymm}-${sequence}`;
    document.getElementById('orderNumberPreview').textContent = preview;
}

async function saveOrderNumberSettings() {
    const prefixInput = document.getElementById('orderPrefix');
    const digitSelect = document.getElementById('orderDigitCount');
    const previewDiv = document.getElementById('orderNumberPreview');
    
    if (!prefixInput || !digitSelect) {
        showAlert('ไม่พบฟอร์มตั้งค่า', 'error');
        return;
    }
    
    const prefix = prefixInput.value.toUpperCase().trim();
    const digitCount = parseInt(digitSelect.value);
    
    if (!prefix || prefix.length > 10) {
        showAlert('คำนำหน้าต้องมี 1-10 ตัวอักษร', 'error');
        return;
    }
    
    if (!/^[A-Z0-9]+$/.test(prefix)) {
        showAlert('คำนำหน้าต้องเป็นตัวอักษรภาษาอังกฤษหรือตัวเลขเท่านั้น', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/order-number-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prefix: prefix,
                digit_count: digitCount
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.settings) {
                prefixInput.value = result.settings.prefix || prefix;
                digitSelect.value = result.settings.digit_count || digitCount;
                if (result.settings.preview && previewDiv) {
                    previewDiv.textContent = result.settings.preview;
                }
            }
            showAlert('บันทึกการตั้งค่าเลขที่คำสั่งซื้อสำเร็จ', 'success');
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving order number settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก กรุณาลองใหม่', 'error');
    }
}

// QR Code upload handler
function handleQrUpload(event) {
    const file = event.target.files[0];
    if (file) {
        promptPayQrFile = file;
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('qrPreview');
            const placeholder = document.getElementById('qrPlaceholder');
            preview.src = e.target.result;
            preview.style.display = 'block';
            placeholder.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
}

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

// ==================== CHAT SYSTEM ====================

let currentChatThreadId = null;
let showingArchivedThreads = false;
let oldestMessageId = 0;
let chatHasMore = false;
let loadingOlderMessages = false;
let chatPollingInterval = null;
let lastMessageId = 0;
let chatQuickReplies = [];
let pendingChatAttachments = [];
let selectedChatProduct = null;
let chatProductSearchTimeout = null;
let currentChatResellerTierId = null;

async function loadChatThreadsAndAutoSelect() {
    const threads = await loadChatThreads();
    if (threads && threads.length > 0 && !currentChatThreadId) {
        const firstThread = threads.find(t => t.unread_count > 0) || threads[0];
        selectChatThread(firstThread.id, firstThread.reseller_name, firstThread.tier_name || '', firstThread.reseller_tier_id || null);
    }
}

async function loadChatThreads() {
    try {
        let url = '/api/chat/threads';
        if (showingArchivedThreads) url += '?archived=true';
        const response = await fetch(url, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            console.error('Chat threads API error:', response.status);
            const container = document.getElementById('chatThreadsList');
            if (container) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.5);">
                        <p>ไม่สามารถโหลดข้อมูลได้</p>
                    </div>
                `;
            }
            return [];
        }
        
        const threads = await response.json();
        
        const container = document.getElementById('chatThreadsList');
        if (!container) return [];
        
        if (!Array.isArray(threads) || threads.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.5);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 12px; opacity: 0.3;">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <p>${showingArchivedThreads ? 'ไม่มีการสนทนาที่ซ่อน' : 'ยังไม่มีการสนทนา'}</p>
                </div>
            `;
            return [];
        }
        
        const isAdmin = document.getElementById('btnToggleArchived') !== null;
        container.innerHTML = threads.map(thread => `
            <div class="chat-thread-item ${currentChatThreadId === thread.id ? 'active' : ''}" 
                 onclick="selectChatThread(${thread.id}, '${escapeHtml(thread.reseller_name)}', '${escapeHtml(thread.tier_name || '')}', ${thread.reseller_tier_id || 'null'})"
                 style="display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 8px; cursor: pointer; background: ${thread.needs_admin ? 'rgba(251,191,36,0.08)' : currentChatThreadId === thread.id ? 'rgba(102,126,234,0.2)' : 'transparent'}; transition: background 0.2s; border-left: ${thread.needs_admin ? '3px solid #fbbf24' : '3px solid transparent'};">
                <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; flex-shrink: 0; position:relative;">
                    ${thread.reseller_name.charAt(0).toUpperCase()}
                    ${thread.needs_admin ? '<span style="position:absolute;top:-4px;right:-4px;background:#fbbf24;border-radius:50%;width:16px;height:16px;font-size:10px;display:flex;align-items:center;justify-content:center;">🙋</span>' : ''}
                </div>
                <div style="flex: 1; min-width: 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600; font-size: 14px;">${escapeHtml(thread.reseller_name)}${thread.needs_admin ? ' <span style="background:#fbbf24;color:#000;font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700;margin-left:4px;">รอ Admin</span>' : ''}</span>
                        ${thread.unread_count > 0 ? `<span style="background: #ef4444; color: white; font-size: 11px; padding: 2px 6px; border-radius: 10px; min-width: 18px; text-align: center;">${thread.unread_count}</span>` : ''}
                    </div>
                    <div style="font-size: 12px; opacity: 0.6; margin-top: 2px;">${thread.tier_name || 'ไม่ระบุ Tier'}</div>
                    <div style="font-size: 12px; opacity: 0.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 4px;">${escapeHtml(thread.last_message_preview || 'ยังไม่มีข้อความ')}</div>
                </div>
                ${isAdmin ? `<button onclick="${showingArchivedThreads ? `unarchiveChatThread(${thread.id}, event)` : `archiveChatThread(${thread.id}, event)`}" style="flex-shrink: 0; width: 28px; height: 28px; border: none; background: rgba(255,255,255,0.08); border-radius: 6px; color: rgba(255,255,255,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.15)';this.style.color='rgba(255,255,255,0.8)'" onmouseout="this.style.background='rgba(255,255,255,0.08)';this.style.color='rgba(255,255,255,0.4)'" title="${showingArchivedThreads ? 'แสดง' : 'ซ่อน'}">
                    ${showingArchivedThreads
                        ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
                        : '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'}
                </button>` : ''}
            </div>
        `).join('');
        
        return threads;
        
    } catch (error) {
        console.error('Error loading chat threads:', error);
        return [];
    }
}

async function toggleArchivedThreads() {
    showingArchivedThreads = !showingArchivedThreads;
    const btn = document.getElementById('btnToggleArchived');
    if (btn) btn.textContent = showingArchivedThreads ? '💬 แชททั้งหมด' : '📁 ซ่อนแล้ว';
    loadChatThreads();
}

async function archiveChatThread(threadId, event) {
    event.stopPropagation();
    if (!confirm('ซ่อนการสนทนานี้? (จะกลับมาเมื่อมีข้อความใหม่)')) return;
    try {
        const resp = await fetch(`/api/chat/threads/${threadId}/archive`, {
            method: 'POST', credentials: 'include'
        });
        if (resp.ok) {
            showAlert('ซ่อนการสนทนาแล้ว', 'success');
            loadChatThreads();
        }
    } catch(e) { console.error(e); }
}

async function unarchiveChatThread(threadId, event) {
    event.stopPropagation();
    try {
        const resp = await fetch(`/api/chat/threads/${threadId}/unarchive`, {
            method: 'POST', credentials: 'include'
        });
        if (resp.ok) {
            showAlert('แสดงการสนทนาอีกครั้ง', 'success');
            loadChatThreads();
        }
    } catch(e) { console.error(e); }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function selectChatThread(threadId, resellerName, tierName, resellerTierId) {
    currentChatThreadId = threadId;
    lastMessageId = 0;
    oldestMessageId = 0;
    chatHasMore = false;
    currentChatResellerTierId = resellerTierId || null;
    selectedChatProduct = null;
    const productPreview = document.getElementById('chatProductPreview');
    if (productPreview) productPreview.style.display = 'none';
    
    document.getElementById('chatHeader').style.display = 'block';
    document.getElementById('chatInputArea').style.display = 'block';
    document.getElementById('chatAvatarInitial').textContent = resellerName.charAt(0).toUpperCase();
    document.getElementById('chatResellerName').textContent = resellerName;
    document.getElementById('chatResellerTier').textContent = tierName || 'ไม่ระบุ Tier';
    
    const chatGrid = document.querySelector('.admin-chat-grid');
    if (chatGrid) chatGrid.classList.add('chat-thread-open');
    
    await loadChatMessages(threadId);
    loadChatThreads();
    loadQuickReplyButtons();
    startChatPolling();
}

function adminChatGoBack() {
    const chatGrid = document.querySelector('.admin-chat-grid');
    if (chatGrid) chatGrid.classList.remove('chat-thread-open');
}

function formatChatDateSeparator(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (date.toDateString() === today.toDateString()) return 'วันนี้';
    if (date.toDateString() === yesterday.toDateString()) return 'เมื่อวาน';
    
    const months = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear() + 543}`;
}

function renderChatMessageHtml(msg, otherLastRead) {
    const isMine = Number(msg.sender_id) === Number(currentUserId);
    const isRead = isMine && msg.id <= otherLastRead;
    
    let productCardHtml = '';
    if (msg.product) {
        const p = msg.product;
        const hasDiscount = p.discount_percent && p.discount_percent > 0;
        const tierPrice = hasDiscount ? (p.tier_min_price === p.tier_max_price ? `฿${formatNumber(p.tier_min_price)}` : `฿${formatNumber(p.tier_min_price)} - ฿${formatNumber(p.tier_max_price)}`) : '';
        const originalPrice = p.min_price === p.max_price ? `฿${formatNumber(p.min_price)}` : `฿${formatNumber(p.min_price)} - ฿${formatNumber(p.max_price)}`;
        productCardHtml = `
            <div style="background: rgba(255,255,255,0.08); border-radius: 10px; overflow: hidden; margin-bottom: ${msg.content ? '8px' : '0'}; border: 1px solid rgba(255,255,255,0.1); cursor: pointer;" onclick="navigateToProduct(${p.id})"
                ${p.image_url ? `<img src="${p.image_url}" style="width: 100%; height: 140px; object-fit: cover;">` : '<div style="width: 100%; height: 80px; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.3);">ไม่มีรูป</div>'}
                <div style="padding: 10px;">
                    <div style="font-size: 13px; font-weight: 600; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.name)}</div>
                    ${hasDiscount ? `
                        <div style="font-size: 14px; font-weight: 700; color: #ffffff;">${tierPrice}</div>
                        <div style="font-size: 11px; text-decoration: line-through; opacity: 0.5;">${originalPrice}</div>
                        <div style="font-size: 10px; color: #34d399; margin-top: 2px;">ส่วนลด ${p.discount_percent}%</div>
                    ` : `
                        <div style="font-size: 14px; font-weight: 700; color: #ffffff;">${originalPrice}</div>
                    `}
                </div>
            </div>
        `;
    }
    
    const isBot = !!msg.is_bot;
    const botBadge = isBot ? '<span style="display:inline-block;background:rgba(139,92,246,0.4);border-radius:4px;padding:1px 5px;font-size:9px;margin-bottom:4px;letter-spacing:0.5px;">🤖 Bot</span><br>' : '';

    return `
        <div style="display: flex; ${isMine ? 'justify-content: flex-end' : 'justify-content: flex-start'}; flex-direction:column; align-items:${isMine ? 'flex-end' : 'flex-start'};">
            ${isBot && !isMine ? `<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-bottom:2px;padding-left:2px;"><span style="background:rgba(139,92,246,0.35);border-radius:4px;padding:1px 6px;font-size:9px;">🤖 Bot</span></div>` : ''}
            <div style="max-width: 70%; padding: 12px 16px; border-radius: 16px; ${isBot && !isMine ? 'background:#2d2235; border:1px solid rgba(139,92,246,0.3);' : isMine ? 'background: linear-gradient(135deg, #667eea, #764ba2);' : 'background: #3a3a3c;'} color: #fff; ${isMine ? 'border-bottom-right-radius: 4px;' : 'border-bottom-left-radius: 4px;'}">
                ${msg.is_broadcast ? '<div style="font-size: 10px; opacity: 0.6; margin-bottom: 4px;">📢 Broadcast</div>' : ''}
                ${productCardHtml}
                ${msg.content ? `<div style="font-size: 14px; line-height: 1.5;">${escapeHtml(msg.content)}</div>` : ''}
                ${msg.attachments && msg.attachments.length > 0 ? msg.attachments.map(att => 
                    att.file_type && att.file_type.startsWith('image/') 
                        ? `<img src="${att.file_url}" style="max-width: 200px; border-radius: 8px; margin-top: 8px; cursor: pointer;" onclick="window.open('${att.file_url}', '_blank')">`
                        : `<a href="${att.file_url}" target="_blank" style="display: block; margin-top: 8px; color: #60a5fa;">📎 ${escapeHtml(att.file_name)}</a>`
                ).join('') : ''}
                <div style="font-size: 10px; opacity: 0.5; margin-top: 6px; text-align: right;">${formatChatTime(msg.created_at)}${isRead ? ' <span style="color: #60a5fa; opacity: 1;">อ่านแล้ว</span>' : ''}</div>
            </div>
        </div>
    `;
}

function renderDateSeparator(dateLabel) {
    return `<div style="display: flex; align-items: center; gap: 12px; margin: 16px 0;">
        <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
        <div style="font-size: 12px; color: rgba(255,255,255,0.4); white-space: nowrap;">${dateLabel}</div>
        <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
    </div>`;
}

function renderMessagesWithDateSeparators(messages, otherLastRead, existingLastDate) {
    let html = '';
    let lastDate = existingLastDate || '';
    messages.forEach(msg => {
        const msgDate = new Date(msg.created_at).toDateString();
        if (msgDate !== lastDate) {
            lastDate = msgDate;
            html += renderDateSeparator(formatChatDateSeparator(msg.created_at));
        }
        html += renderChatMessageHtml(msg, otherLastRead);
    });
    return html;
}

async function loadChatMessages(threadId) {
    try {
        let url;
        if (lastMessageId > 0) {
            url = `/api/chat/threads/${threadId}/messages?since_id=${lastMessageId}`;
        } else {
            url = `/api/chat/threads/${threadId}/messages`;
        }
        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();
        const messages = data.messages || data;
        const otherLastRead = data.other_last_read || 0;
        chatHasMore = data.has_more || false;
        
        const container = document.getElementById('chatMessagesContainer');
        if (!container) return;
        
        if (lastMessageId === 0) {
            container.innerHTML = '';
            const html = renderMessagesWithDateSeparators(messages, otherLastRead, '');
            container.insertAdjacentHTML('beforeend', html);
            if (messages.length > 0) {
                oldestMessageId = messages[0].id;
            }
            setupChatScrollListener(container, threadId);
        } else {
            messages.forEach(msg => {
                const msgDate = new Date(msg.created_at).toDateString();
                const lastChild = container.lastElementChild;
                const lastMsgDateAttr = lastChild ? lastChild.dataset?.msgDate : '';
                if (msgDate !== lastMsgDateAttr) {
                    container.insertAdjacentHTML('beforeend', renderDateSeparator(formatChatDateSeparator(msg.created_at)));
                }
                const msgEl = document.createElement('div');
                msgEl.dataset.msgDate = msgDate;
                msgEl.innerHTML = renderChatMessageHtml(msg, otherLastRead);
                container.appendChild(msgEl);
            });
        }
        
        messages.forEach(msg => {
            lastMessageId = Math.max(lastMessageId, msg.id);
        });
        
        container.scrollTop = container.scrollHeight;
        
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

async function loadOlderChatMessages(threadId) {
    if (loadingOlderMessages || !chatHasMore || oldestMessageId <= 0) return;
    loadingOlderMessages = true;
    
    const container = document.getElementById('chatMessagesContainer');
    if (!container) { loadingOlderMessages = false; return; }
    
    const loader = document.createElement('div');
    loader.id = 'chatLoadingOlder';
    loader.style.cssText = 'text-align: center; padding: 12px; color: rgba(255,255,255,0.4); font-size: 12px;';
    loader.textContent = 'กำลังโหลด...';
    container.prepend(loader);
    
    const prevScrollHeight = container.scrollHeight;
    
    try {
        const response = await fetch(`/api/chat/threads/${threadId}/messages?before_id=${oldestMessageId}`, { credentials: 'include' });
        const data = await response.json();
        const messages = data.messages || data;
        chatHasMore = data.has_more || false;
        
        const loaderEl = document.getElementById('chatLoadingOlder');
        if (loaderEl) loaderEl.remove();
        
        if (messages.length > 0) {
            const html = renderMessagesWithDateSeparators(messages, data.other_last_read || 0, '');
            container.insertAdjacentHTML('afterbegin', html);
            oldestMessageId = messages[0].id;
            container.scrollTop = container.scrollHeight - prevScrollHeight;
        }
    } catch (error) {
        console.error('Error loading older messages:', error);
        const loaderEl = document.getElementById('chatLoadingOlder');
        if (loaderEl) loaderEl.remove();
    }
    
    loadingOlderMessages = false;
}

function setupChatScrollListener(container, threadId) {
    container.onscroll = function() {
        if (container.scrollTop < 50 && chatHasMore && !loadingOlderMessages) {
            loadOlderChatMessages(threadId);
        }
    };
}

function formatChatTime(dateStr) {
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

async function sendChatMessage() {
    if (!currentChatThreadId) return;
    
    const input = document.getElementById('chatMessageInput');
    const content = input.value.trim();
    
    if (!content && pendingChatAttachments.length === 0 && !selectedChatProduct) return;
    
    try {
        const body = {
            content: content,
            attachments: pendingChatAttachments
        };
        if (selectedChatProduct) {
            body.product_id = selectedChatProduct.id;
        }
        
        const response = await fetch(`/api/chat/threads/${currentChatThreadId}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify(body)
        });
        
        if (response.ok) {
            input.value = '';
            input.style.height = 'auto';
            pendingChatAttachments = [];
            selectedChatProduct = null;
            document.getElementById('chatAttachmentPreview').style.display = 'none';
            document.getElementById('chatAttachmentPreview').innerHTML = '';
            document.getElementById('chatProductPreview').style.display = 'none';
            await loadChatMessages(currentChatThreadId);
            loadChatThreads();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถส่งข้อความได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function handleChatFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/chat/upload', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken },
            credentials: 'include',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            pendingChatAttachments.push(result);
            updateChatAttachmentPreview();
        } else {
            showAlert('error', result.error || 'อัปโหลดไม่สำเร็จ');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
    
    event.target.value = '';
}

function updateChatAttachmentPreview() {
    const container = document.getElementById('chatAttachmentPreview');
    if (pendingChatAttachments.length === 0) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    
    container.style.display = 'flex';
    container.style.gap = '8px';
    container.style.flexWrap = 'wrap';
    
    container.innerHTML = pendingChatAttachments.map((att, i) => `
        <div style="position: relative; padding: 8px 12px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 12px;">
            ${att.file_type && att.file_type.startsWith('image/') ? '🖼️' : '📎'} ${escapeHtml(att.file_name)}
            <button onclick="removeChatAttachment(${i})" style="position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; background: #ef4444; border: none; color: white; cursor: pointer; font-size: 12px; line-height: 1;">×</button>
        </div>
    `).join('');
}

function removeChatAttachment(index) {
    pendingChatAttachments.splice(index, 1);
    updateChatAttachmentPreview();
}

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('th-TH', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

let chatProductSelections = [];

function openChatProductSearch() {
    document.getElementById('chatProductModal').style.display = 'flex';
    document.getElementById('chatProductSearchInput').value = '';
    document.getElementById('chatProductSearchStatus').style.display = 'none';
    document.getElementById('chatProductSearchResults').innerHTML = `
        <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
            <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
        </div>`;
    chatProductSelections = [];
    updateChatProductSelectedBar();
    setTimeout(() => document.getElementById('chatProductSearchInput').focus(), 100);
}

function closeChatProductModal() {
    document.getElementById('chatProductModal').style.display = 'none';
}

function searchChatProducts() {
    clearTimeout(chatProductSearchTimeout);
    const q = document.getElementById('chatProductSearchInput').value.trim();
    const statusEl = document.getElementById('chatProductSearchStatus');
    if (q.length < 1) {
        statusEl.style.display = 'none';
        document.getElementById('chatProductSearchResults').innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
                <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
            </div>`;
        return;
    }
    statusEl.style.display = 'block';
    statusEl.innerHTML = '<span style="display: inline-flex; align-items: center; gap: 6px;"><span class="chat-product-spinner"></span> กำลังค้นหา...</span>';
    chatProductSearchTimeout = setTimeout(async () => {
        try {
            let url = `/api/chat/products/search?q=${encodeURIComponent(q)}`;
            if (currentChatResellerTierId) {
                url += `&tier_id=${currentChatResellerTierId}`;
            }
            const response = await fetch(url, { credentials: 'include' });
            const products = await response.json();
            const container = document.getElementById('chatProductSearchResults');
            
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
                const isSelected = chatProductSelections.some(s => s.id === p.id);
                const hasDiscount = p.discount_percent && p.discount_percent > 0;
                const priceDisplay = hasDiscount
                    ? `<span style="color: #ffffff; font-weight: 600;">฿${formatNumber(p.tier_min_price)}</span> <span style="text-decoration: line-through; opacity: 0.4; font-size: 11px;">฿${formatNumber(p.min_price)}</span>`
                    : `<span style="color: #ffffff; font-weight: 600;">฿${formatNumber(p.min_price)}</span>`;
                const stockColor = (p.total_stock || 0) > 0 ? '#34d399' : '#f87171';
                const stockText = (p.total_stock || 0) > 0 ? `${p.total_stock} ชิ้น` : 'หมด';
                return `
                    <div onclick="toggleChatProductSelect(${p.id}, '${escapeHtml(p.name).replace(/'/g, "\\'")}', '${p.image_url || ''}', ${p.min_price || 0}, ${hasDiscount ? p.tier_min_price : p.min_price || 0}, ${p.discount_percent || 0})"
                         id="chatProdItem_${p.id}"
                         style="display: flex; gap: 12px; align-items: center; padding: 10px 12px; border-radius: 10px; cursor: pointer; transition: all 0.2s; margin-bottom: 4px; border: 1.5px solid ${isSelected ? 'rgba(102,126,234,0.5)' : 'transparent'}; background: ${isSelected ? 'rgba(102,126,234,0.1)' : 'transparent'};"
                         onmouseover="if(!this.classList.contains('selected'))this.style.background='rgba(255,255,255,0.05)'" onmouseout="if(!this.classList.contains('selected'))this.style.background='transparent'">
                        <div style="position: relative; flex-shrink: 0;">
                            ${p.image_url ? `<img src="${p.image_url}" style="width: 52px; height: 52px; object-fit: cover; border-radius: 8px;">` : '<div style="width: 52px; height: 52px; background: rgba(255,255,255,0.05); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.15); font-size: 22px;">📦</div>'}
                            <div data-check="1" style="position: absolute; top: -4px; right: -4px; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; transition: all 0.2s; ${isSelected ? 'background: linear-gradient(135deg, #667eea, #764ba2); color: white; box-shadow: 0 0 0 2px rgba(102,126,234,0.3);' : 'background: rgba(255,255,255,0.1); color: transparent;'}">${isSelected ? '✓' : ''}</div>
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: white;">${escapeHtml(p.name)}</div>
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

function toggleChatProductSelect(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    const idx = chatProductSelections.findIndex(s => s.id === id);
    if (idx >= 0) {
        chatProductSelections.splice(idx, 1);
    } else {
        chatProductSelections.push({ id, name, imageUrl, originalPrice, tierPrice, discountPercent });
    }
    const item = document.getElementById(`chatProdItem_${id}`);
    if (item) {
        const isNowSelected = chatProductSelections.some(s => s.id === id);
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
    updateChatProductSelectedBar();
}

function updateChatProductSelectedBar() {
    const bar = document.getElementById('chatProductSelectedBar');
    const countEl = document.getElementById('chatProductSelectedCount');
    const thumbsEl = document.getElementById('chatProductSelectedThumbs');
    if (chatProductSelections.length === 0) {
        bar.style.display = 'none';
        return;
    }
    bar.style.display = 'block';
    countEl.textContent = chatProductSelections.length;
    thumbsEl.innerHTML = chatProductSelections.map(s => `
        <div style="position: relative; flex-shrink: 0;" title="${escapeHtml(s.name)}">
            ${s.imageUrl ? `<img src="${s.imageUrl}" style="width: 28px; height: 28px; object-fit: cover; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);">` : '<div style="width: 28px; height: 28px; background: rgba(255,255,255,0.1); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px;">📦</div>'}
            <div onclick="event.stopPropagation(); removeChatProductFromSelection(${s.id})" style="position: absolute; top: -5px; right: -5px; width: 14px; height: 14px; background: #ef4444; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 8px; color: white; cursor: pointer; line-height: 1;">×</div>
        </div>
    `).join('');
}

function removeChatProductFromSelection(id) {
    chatProductSelections = chatProductSelections.filter(s => s.id !== id);
    const item = document.getElementById(`chatProdItem_${id}`);
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
    updateChatProductSelectedBar();
}

function clearChatProductSelection() {
    chatProductSelections.forEach(s => {
        const item = document.getElementById(`chatProdItem_${s.id}`);
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
    chatProductSelections = [];
    updateChatProductSelectedBar();
}

async function sendSelectedChatProducts() {
    if (!currentChatThreadId || chatProductSelections.length === 0) return;
    closeChatProductModal();
    for (const product of chatProductSelections) {
        try {
            await fetch(`/api/chat/threads/${currentChatThreadId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
                credentials: 'include',
                body: JSON.stringify({ content: '', product_id: product.id })
            });
        } catch (e) { console.error('Error sending product:', e); }
    }
    chatProductSelections = [];
    updateChatProductSelectedBar();
    loadChatMessages(currentChatThreadId);
}

function navigateToProduct(productId) {
    window.location.hash = 'products';
    switchPage('products');
    let attempts = 0;
    const maxAttempts = 30;
    const tryHighlight = () => {
        attempts++;
        const row = document.querySelector(`tr[data-product-id="${productId}"]`);
        if (row) {
            row.classList.remove('highlight-flash');
            void row.offsetWidth;
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('highlight-flash');
            setTimeout(() => row.classList.remove('highlight-flash'), 15000);
        } else if (attempts < maxAttempts) {
            setTimeout(tryHighlight, 500);
        }
    };
    setTimeout(tryHighlight, 500);
}

function selectChatProduct(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    selectedChatProduct = { id, name, imageUrl, originalPrice, tierPrice, discountPercent };
    const preview = document.getElementById('chatProductPreview');
    const img = document.getElementById('chatProductPreviewImg');
    const nameEl = document.getElementById('chatProductPreviewName');
    const priceEl = document.getElementById('chatProductPreviewPrice');
    if (imageUrl) { img.src = imageUrl; img.style.display = 'block'; } else { img.style.display = 'none'; }
    nameEl.textContent = name;
    if (discountPercent > 0) {
        priceEl.innerHTML = `฿${formatNumber(tierPrice)} <span style="text-decoration: line-through; opacity: 0.5; font-size: 11px;">฿${formatNumber(originalPrice)}</span>`;
    } else {
        priceEl.textContent = `฿${formatNumber(originalPrice)}`;
    }
    preview.style.display = 'block';
    closeChatProductModal();
}

function removeChatProduct() {
    selectedChatProduct = null;
    document.getElementById('chatProductPreview').style.display = 'none';
}

function startChatPolling() {
    if (chatPollingInterval) clearInterval(chatPollingInterval);
    chatPollingInterval = setInterval(() => {
        if (currentChatThreadId) {
            loadChatMessages(currentChatThreadId);
        }
        loadChatUnreadCount();
    }, 5000);
}

function stopChatPolling() {
    if (chatPollingInterval) {
        clearInterval(chatPollingInterval);
        chatPollingInterval = null;
    }
}

async function loadChatUnreadCount() {
    try {
        const response = await fetch('/api/chat/unread-count', { credentials: 'include' });
        const data = await response.json();
        
        const badge = document.getElementById('chatUnreadCount');
        const chatNavItem = document.querySelector('a.nav-item[href="/chat"]');

        if (badge) {
            if (data.unread_count > 0) {
                badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                badge.style.display = 'inline';
                badge.classList.add('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.add('chat-nav-active');
            } else {
                badge.style.display = 'none';
                badge.classList.remove('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.remove('chat-nav-active');
            }
        }
    } catch (error) {
        console.error('Error loading unread count:', error);
    }
}

// Quick Replies
async function loadQuickReplyButtons() {
    try {
        const response = await fetch('/api/chat/quick-replies', { credentials: 'include' });
        chatQuickReplies = await response.json();
        
        const container = document.getElementById('quickReplyButtons');
        if (!container) return;
        
        container.innerHTML = chatQuickReplies.slice(0, 5).map(qr => `
            <button onclick="insertQuickReply('${escapeHtml(qr.content)}')" class="btn btn-sm" style="font-size: 11px; padding: 4px 8px;">
                ${escapeHtml(qr.title)}
            </button>
        `).join('');
    } catch (error) {
        console.error('Error loading quick replies:', error);
    }
}

function insertQuickReply(content) {
    const input = document.getElementById('chatMessageInput');
    input.value = content;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
    input.focus();
}

// Broadcast Modal
function openBroadcastModal() {
    document.getElementById('broadcastModal').style.display = 'flex';
    loadTiersForBroadcast();
}

function closeBroadcastModal() {
    document.getElementById('broadcastModal').style.display = 'none';
    document.getElementById('broadcastTitle').value = '';
    document.getElementById('broadcastContent').value = '';
}

function toggleBroadcastTier() {
    const target = document.getElementById('broadcastTarget').value;
    document.getElementById('broadcastTierSelect').style.display = target === 'tier' ? 'block' : 'none';
}

async function loadTiersForBroadcast() {
    try {
        const response = await fetch('/api/tiers', { credentials: 'include' });
        const tiers = await response.json();
        
        const select = document.getElementById('broadcastTierId');
        select.innerHTML = '<option value="">เลือก Tier</option>' + 
            tiers.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
    } catch (error) {
        console.error('Error loading tiers:', error);
    }
}

async function sendBroadcast() {
    const title = document.getElementById('broadcastTitle').value.trim();
    const content = document.getElementById('broadcastContent').value.trim();
    const targetType = document.getElementById('broadcastTarget').value;
    const targetTierId = document.getElementById('broadcastTierId').value || null;
    
    if (!content) {
        showAlert('error', 'กรุณากรอกข้อความ');
        return;
    }
    
    try {
        const response = await fetch('/api/chat/broadcast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                title,
                content,
                target_type: targetType,
                target_tier_id: targetTierId
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', result.message || 'ส่ง Broadcast สำเร็จ');
            closeBroadcastModal();
            loadChatThreads();
        } else {
            showAlert('error', result.error || 'ไม่สามารถส่ง Broadcast ได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Quick Replies Management Modal
function openQuickRepliesModal() {
    document.getElementById('quickRepliesModal').style.display = 'flex';
    loadQuickRepliesList();
}

function closeQuickRepliesModal() {
    document.getElementById('quickRepliesModal').style.display = 'none';
}

async function loadQuickRepliesList() {
    try {
        const response = await fetch('/api/chat/quick-replies', { credentials: 'include' });
        const replies = await response.json();
        
        const container = document.getElementById('quickRepliesList');
        
        if (replies.length === 0) {
            container.innerHTML = '<div style="text-align: center; padding: 20px; color: rgba(255,255,255,0.5);">ยังไม่มี Quick Reply</div>';
            return;
        }
        
        container.innerHTML = replies.map(qr => `
            <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(255,255,255,0.05); border-radius: 8px; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="font-weight: 600;">${escapeHtml(qr.title)}</div>
                    <div style="font-size: 12px; opacity: 0.6;">${qr.shortcut ? 'Shortcut: ' + escapeHtml(qr.shortcut) : ''}</div>
                    <div style="font-size: 13px; margin-top: 4px; opacity: 0.8;">${escapeHtml(qr.content.substring(0, 100))}${qr.content.length > 100 ? '...' : ''}</div>
                </div>
                <button onclick="deleteQuickReply(${qr.id})" class="btn btn-sm" style="color: #ef4444;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading quick replies:', error);
    }
}

function showAddQuickReplyForm() {
    document.getElementById('addQuickReplyForm').style.display = 'block';
}

function hideAddQuickReplyForm() {
    document.getElementById('addQuickReplyForm').style.display = 'none';
    document.getElementById('newQuickReplyTitle').value = '';
    document.getElementById('newQuickReplyShortcut').value = '';
    document.getElementById('newQuickReplyContent').value = '';
}

async function saveQuickReply() {
    const title = document.getElementById('newQuickReplyTitle').value.trim();
    const shortcut = document.getElementById('newQuickReplyShortcut').value.trim();
    const content = document.getElementById('newQuickReplyContent').value.trim();
    
    if (!title || !content) {
        showAlert('error', 'กรุณากรอกชื่อและข้อความ');
        return;
    }
    
    try {
        const response = await fetch('/api/chat/quick-replies', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({ title, shortcut, content })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', 'เพิ่ม Quick Reply สำเร็จ');
            hideAddQuickReplyForm();
            loadQuickRepliesList();
            loadQuickReplyButtons();
        } else {
            showAlert('error', result.error || 'ไม่สามารถบันทึกได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function deleteQuickReply(replyId) {
    if (!confirm('ต้องการลบ Quick Reply นี้หรือไม่?')) return;
    
    try {
        const response = await fetch(`/api/chat/quick-replies/${replyId}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': csrfToken },
            credentials: 'include'
        });
        
        if (response.ok) {
            showAlert('success', 'ลบสำเร็จ');
            loadQuickRepliesList();
            loadQuickReplyButtons();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถลบได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function searchChatMessages() {
    const query = document.getElementById('chatSearchInput').value.trim();
    if (!query || query.length < 2) {
        showAlert('error', 'กรุณากรอกคำค้นอย่างน้อย 2 ตัวอักษร');
        return;
    }
    
    try {
        const response = await fetch(`/api/chat/search?q=${encodeURIComponent(query)}`, {
            credentials: 'include'
        });
        const results = await response.json();
        
        if (results.length === 0) {
            showAlert('info', 'ไม่พบข้อความที่ค้นหา');
            return;
        }
        
        const firstResult = results[0];
        selectChatThread(firstResult.thread_id, firstResult.reseller_name || firstResult.sender_name, '');
        
        showAlert('success', `พบ ${results.length} ข้อความ`);
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Reseller Search/Picker for Chat
let allResellersForChat = [];

async function loadAllResellersForChat() {
    try {
        const response = await fetch('/api/resellers?limit=1000', { credentials: 'include' });
        const data = await response.json();
        allResellersForChat = data.resellers || data;
        return allResellersForChat;
    } catch (error) {
        console.error('Error loading resellers:', error);
        return [];
    }
}

function toggleResellerPickerDropdown() {
    const dropdown = document.getElementById('resellerPickerDropdown');
    if (dropdown.style.display === 'none') {
        showResellerPickerDropdown();
    } else {
        dropdown.style.display = 'none';
    }
}

async function showResellerPickerDropdown(searchTerm = '') {
    const dropdown = document.getElementById('resellerPickerDropdown');
    dropdown.style.display = 'block';
    dropdown.innerHTML = '<div style="padding: 12px; text-align: center; color: rgba(255,255,255,0.5); font-size: 12px;">กำลังโหลด...</div>';
    
    if (allResellersForChat.length === 0) {
        await loadAllResellersForChat();
    }
    
    let filtered = allResellersForChat;
    if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filtered = allResellersForChat.filter(r => 
            (r.full_name && r.full_name.toLowerCase().includes(term)) ||
            (r.email && r.email.toLowerCase().includes(term)) ||
            (r.phone && r.phone.includes(term))
        );
    }
    
    if (filtered.length === 0) {
        dropdown.innerHTML = '<div style="padding: 12px; text-align: center; color: rgba(255,255,255,0.5); font-size: 12px;">ไม่พบตัวแทน</div>';
        return;
    }
    
    const tierIcons = { 'Bronze': '🥉', 'Silver': '🥈', 'Gold': '🥇', 'Platinum': '💎' };
    
    dropdown.innerHTML = filtered.slice(0, 50).map(r => `
        <div onclick="startChatWithReseller(${r.id}, '${escapeHtml(r.full_name || '')}', '${escapeHtml(r.tier_name || 'Bronze')}')" 
             style="padding: 10px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 10px; transition: background 0.2s;"
             onmouseover="this.style.background='rgba(168,85,247,0.2)'" onmouseout="this.style.background='transparent'">
            <div style="width: 36px; height: 36px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; color: white;">
                ${escapeHtml((r.full_name || '?').charAt(0).toUpperCase())}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 500; font-size: 13px; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.full_name || 'ไม่ระบุชื่อ')}</div>
                <div style="font-size: 11px; color: rgba(255,255,255,0.5);">${tierIcons[r.tier_name] || '🏷️'} ${escapeHtml(r.tier_name || 'Bronze')}</div>
            </div>
        </div>
    `).join('');
}

function searchResellersForChat(searchTerm) {
    if (searchTerm.length >= 1) {
        showResellerPickerDropdown(searchTerm);
    } else {
        document.getElementById('resellerPickerDropdown').style.display = 'none';
    }
}

async function startChatWithReseller(resellerId, resellerName, tierName) {
    document.getElementById('resellerPickerDropdown').style.display = 'none';
    document.getElementById('chatResellerSearchInput').value = '';
    
    try {
        const response = await fetch(`/api/chat/start/${resellerId}`, {
            method: 'POST',
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            selectChatThread(data.thread_id, resellerName, tierName);
            loadChatThreads();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถเริ่มแชทได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const dropdown = document.getElementById('resellerPickerDropdown');
    const searchInput = document.getElementById('chatResellerSearchInput');
    const pickerBtn = e.target.closest('button[onclick*="toggleResellerPickerDropdown"]');
    
    if (dropdown && dropdown.style.display !== 'none') {
        if (!dropdown.contains(e.target) && e.target !== searchInput && !pickerBtn) {
            dropdown.style.display = 'none';
        }
    }
});

// ─── Shipping Update Page ─────────────────────────────────────────────────────

function copyTrackingNumber(el, tn) {
    navigator.clipboard.writeText(tn).then(() => {
        el.textContent = 'คัดลอกแล้ว';
        el.style.color = '#34d399';
        setTimeout(() => {
            el.textContent = 'คัดลอก';
            el.style.color = 'rgba(255,255,255,0.5)';
        }, 1800);
    }).catch(() => {
        el.textContent = 'ไม่สำเร็จ';
    });
}

async function loadShippingUpdatePage() {
    const container = document.getElementById('shippingUpdateContent');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:48px;color:rgba(255,255,255,0.5);font-size:13px;">กำลังโหลด...</div>';

    try {
        const resp = await fetch(`${API_URL}/admin/orders/shipped`, { credentials: 'include' });
        const orders = await resp.json();

        const badge = document.getElementById('shippingUpdateCount');
        if (badge) {
            badge.textContent = orders.length;
            badge.style.display = orders.length > 0 ? 'inline' : 'none';
        }

        if (!orders.length) {
            container.innerHTML = `
                <div style="text-align:center;padding:72px 20px;color:rgba(255,255,255,0.35);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="display:block;margin:0 auto 14px;opacity:0.3;">
                        <rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/>
                        <circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>
                    </svg>
                    <div style="font-size:14px;font-weight:500;color:rgba(255,255,255,0.45);">ไม่มีคำสั่งซื้อที่กำลังจัดส่งในขณะนี้</div>
                </div>`;
            return;
        }

        const rows = orders.map(order => {
            const shipments = order.shipments || [];
            const sh = shipments[0] || {};
            const orderNum = escapeHtml(order.order_number || '#' + order.id);
            const resellerName = escapeHtml(order.reseller_name || '-');

            let daysLabel = '';
            if (sh.shipped_at) {
                const diff = Math.floor((Date.now() - new Date(sh.shipped_at)) / 86400000);
                daysLabel = diff === 0 ? 'ส่งวันนี้' : `${diff} วันที่แล้ว`;
            }
            const shippedDate = sh.shipped_at
                ? new Date(sh.shipped_at).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' })
                : '-';

            const shipmentsHtml = shipments.length > 0 ? shipments.map(s => {
                const tn = escapeHtml(s.tracking_number || '');
                const provider = escapeHtml(s.shipping_provider || 'ไม่ระบุ');
                const tUrl = escapeHtml(s.tracking_url || '');
                return `
                <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:rgba(0,0,0,0.2);border-radius:10px;flex-wrap:wrap;row-gap:6px;">
                    <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                        <span style="font-size:12px;font-weight:600;color:#ffffff;">${provider}</span>
                    </div>
                    <div style="flex:1;display:flex;align-items:center;gap:6px;min-width:0;flex-wrap:wrap;row-gap:4px;">
                        <span style="font-family:monospace;font-size:12px;color:#ffffff;background:rgba(255,255,255,0.08);padding:3px 10px;border-radius:6px;letter-spacing:0.5px;word-break:break-all;">${tn || '-'}</span>
                        ${tn ? `<button onclick="copyTrackingNumber(this,'${tn}')" style="background:none;border:none;color:rgba(255,255,255,0.5);font-size:11px;cursor:pointer;padding:0;white-space:nowrap;flex-shrink:0;">คัดลอก</button>` : ''}
                    </div>
                    ${tUrl ? `<a href="${tUrl}" target="_blank" style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:#ffffff;font-weight:500;text-decoration:none;background:rgba(129,140,248,0.2);border:1px solid rgba(129,140,248,0.4);padding:4px 10px;border-radius:7px;white-space:nowrap;flex-shrink:0;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        ติดตามพัสดุ
                    </a>` : ''}
                </div>`;
            }).join('') : `<div style="font-size:12px;color:rgba(255,255,255,0.35);padding:8px 0;">ยังไม่มีข้อมูลพัสดุ</div>`;

            return `
            <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:16px 18px;margin-bottom:10px;">

                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px;flex-wrap:wrap;row-gap:8px;">
                    <div style="display:flex;align-items:center;gap:10px;min-width:0;">
                        <div style="width:38px;height:38px;flex-shrink:0;border-radius:10px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.3);display:flex;align-items:center;justify-content:center;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                        </div>
                        <div style="min-width:0;">
                            <div style="font-size:14px;font-weight:700;color:#ffffff;">${orderNum}</div>
                            <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-top:2px;display:flex;align-items:center;gap:4px;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                ${resellerName}
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end;row-gap:4px;">
                        <span style="display:inline-flex;align-items:center;gap:5px;background:rgba(14,165,233,0.15);border:1px solid rgba(14,165,233,0.35);color:#ffffff;font-size:10px;font-weight:600;padding:3px 9px;border-radius:20px;">
                            <span style="width:5px;height:5px;border-radius:50%;background:#38bdf8;flex-shrink:0;"></span>
                            กำลังจัดส่ง
                        </span>
                        ${shippedDate !== '-' ? `<div style="text-align:right;"><div style="font-size:11px;color:rgba(255,255,255,0.7);">${shippedDate}</div>${daysLabel ? `<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-top:1px;">${daysLabel}</div>` : ''}</div>` : ''}
                    </div>
                </div>

                <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">
                    ${shipmentsHtml}
                </div>

                <div id="shipping-actions-${order.id}" style="display:flex;gap:8px;flex-wrap:wrap;">
                    <button onclick="showShippingConfirm(${order.id},'${orderNum}','delivered')"
                        style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        จัดส่งสำเร็จ
                    </button>
                    <button onclick="showShippingConfirm(${order.id},'${orderNum}','return')"
                        style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.45);color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
                        สินค้าตีกลับ
                    </button>
                </div>
            </div>`;
        }).join('');

        container.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
                <span style="font-size:13px;color:rgba(255,255,255,0.6);">กำลังจัดส่งอยู่</span>
                <span style="background:rgba(14,165,233,0.2);border:1px solid rgba(14,165,233,0.4);color:#ffffff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;">${orders.length} รายการ</span>
            </div>
            ${rows}`;

    } catch (err) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:#f87171;">เกิดข้อผิดพลาดในการโหลดข้อมูล</div>';
        console.error('loadShippingUpdatePage error:', err);
    }
}

function showShippingConfirm(orderId, orderNum, action) {
    const actionsDiv = document.getElementById(`shipping-actions-${orderId}`);
    if (!actionsDiv) return;

    const isDelivered = action === 'delivered';
    const label    = isDelivered ? 'ยืนยันจัดส่งสำเร็จ?' : 'ยืนยันสินค้าตีกลับ?';
    const color    = isDelivered ? '#10b981' : '#ef4444';
    const colorBg  = isDelivered ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
    const colorBdr = isDelivered ? 'rgba(16,185,129,0.45)' : 'rgba(239,68,68,0.45)';
    const iconSvg  = isDelivered
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>`;

    const onConfirm = isDelivered
        ? `markShippingDelivered(${orderId},'${orderNum}')`
        : `openFailedDeliveryModal(${orderId},'${orderNum}');restoreShippingActions(${orderId},'${orderNum}')`;

    actionsDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;width:100%;background:${colorBg};border:1px solid ${colorBdr};border-radius:10px;padding:10px 14px;flex-wrap:wrap;row-gap:8px;">
            <span style="flex:1;font-size:12px;font-weight:600;color:#ffffff;display:flex;align-items:center;gap:6px;">
                ${iconSvg} ${label}
            </span>
            <div style="display:flex;gap:6px;flex-shrink:0;">
                <button onclick="${onConfirm}"
                    style="padding:6px 16px;background:${color};border:none;color:#ffffff;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;">
                    ยืนยัน
                </button>
                <button onclick="restoreShippingActions(${orderId},'${orderNum}')"
                    style="padding:6px 14px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);color:#ffffff;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;">
                    ยกเลิก
                </button>
            </div>
        </div>`;
}

function restoreShippingActions(orderId, orderNum) {
    const actionsDiv = document.getElementById(`shipping-actions-${orderId}`);
    if (!actionsDiv) return;
    actionsDiv.innerHTML = `
        <button onclick="showShippingConfirm(${orderId},'${orderNum}','delivered')"
            style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            จัดส่งสำเร็จ
        </button>
        <button onclick="showShippingConfirm(${orderId},'${orderNum}','return')"
            style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.45);color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
            สินค้าตีกลับ
        </button>`;
    actionsDiv.style.display = 'flex';
    actionsDiv.style.gap = '8px';
    actionsDiv.style.flexWrap = 'wrap';
}

async function markShippingDelivered(orderId, orderNumber) {
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/mark-delivered`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await resp.json();
        if (resp.ok) {
            showGlobalAlert(`✅ อัปเดต ${orderNumber} เป็นจัดส่งสำเร็จแล้ว`, 'success');
            loadShippingUpdatePage();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (err) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function openFailedDeliveryModal(orderId, orderNumber) {
    document.getElementById('failedDeliveryOrderId').value = orderId;
    document.getElementById('failedDeliveryReason').value = '';
    const modal = document.getElementById('failedDeliveryModal');
    if (modal) { modal.style.display = 'flex'; }
}

function closeFailedDeliveryModal() {
    const modal = document.getElementById('failedDeliveryModal');
    if (modal) { modal.style.display = 'none'; }
}

async function confirmFailedDelivery() {
    const orderId = document.getElementById('failedDeliveryOrderId').value;
    const reason = document.getElementById('failedDeliveryReason').value.trim();
    if (!reason) {
        showGlobalAlert('กรุณากรอกเหตุผล', 'error');
        return;
    }
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/mark-failed-delivery`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        const data = await resp.json();
        if (resp.ok) {
            closeFailedDeliveryModal();
            showGlobalAlert('📦 บันทึกสินค้าตีกลับเรียบร้อย', 'success');
            loadShippingUpdatePage();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (err) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);

// ==================== MARKETING MODULE ====================

let _promoData = [], _couponData = [];
let _mktTiers = [], _mktBrands = [], _mktCategories = [];
let _editingPromoId = null, _editingCouponId = null;

async function _mktLoadMeta() {
    if (_mktTiers.length) return;
    const [t, b, c] = await Promise.all([
        fetch('/api/reseller-tiers').then(r => r.json()).catch(() => []),
        fetch('/api/brands').then(r => r.json()).catch(() => []),
        fetch('/api/categories').then(r => r.json()).catch(() => [])
    ]);
    _mktTiers = Array.isArray(t) ? t : [];
    _mktBrands = Array.isArray(b) ? b : [];
    _mktCategories = Array.isArray(c) ? c : [];
}

function _fmtDiscount(promo) {
    if (promo.reward_type === 'discount_percent') return `ลด ${promo.reward_value}%`;
    if (promo.reward_type === 'discount_fixed') return `ลด ฿${Number(promo.reward_value).toLocaleString()}`;
    if (promo.reward_type === 'free_item') return `ของแถม ${promo.reward_qty || 1} ชิ้น`;
    return promo.reward_type;
}
function _fmtCondition(promo) {
    const parts = [];
    if (promo.condition_min_spend > 0) parts.push(`ซื้อครบ ฿${Number(promo.condition_min_spend).toLocaleString()}`);
    if (promo.condition_min_qty > 0) parts.push(`จำนวน ${promo.condition_min_qty} ชิ้นขึ้นไป`);
    return parts.join(' & ') || 'ทุกออเดอร์';
}
function _fmtCouponDiscount(c) {
    if (c.discount_type === 'percent') {
        let s = `ลด ${c.discount_value}%`;
        if (c.max_discount > 0) s += ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})`;
        return s;
    }
    if (c.discount_type === 'fixed') return `ลด ฿${Number(c.discount_value).toLocaleString()}`;
    if (c.discount_type === 'free_shipping') return 'ส่งฟรี';
    return c.discount_type;
}

// ── Promotions ──────────────────────────────────────────────────

async function loadPromotions() {
    try {
        const data = await fetch('/api/admin/promotions').then(r => r.json());
        _promoData = Array.isArray(data) ? data : [];
        const active = _promoData.filter(p => p.is_active).length;
        const inactive = _promoData.length - active;
        document.getElementById('promoStats').innerHTML = `
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#fff;">${_promoData.length}</div>
                <div class="mkt-stat-lbl">ทั้งหมด</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#4ade80;">${active}</div>
                <div class="mkt-stat-lbl">กำลังใช้งาน</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#9ca3af;">${inactive}</div>
                <div class="mkt-stat-lbl">ปิดอยู่</div>
            </div>
        `;
        if (!_promoData.length) {
            document.getElementById('promoTableWrap').innerHTML = `<div class="empty-state"><p>ยังไม่มีโปรโมชัน — กดปุ่ม "สร้างโปรโมชัน" เพื่อเริ่มต้น</p></div>`;
            return;
        }
        const cards = _promoData.map(p => {
            const chips = [];
            if (p.condition_min_spend > 0) chips.push(`<span class="promo-chip chip-condition">ซื้อครบ ฿${Number(p.condition_min_spend).toLocaleString()}</span>`);
            if (p.condition_min_qty > 0) chips.push(`<span class="promo-chip chip-condition">${p.condition_min_qty} ชิ้นขึ้นไป</span>`);
            chips.push(`<span class="promo-chip chip-reward">${_fmtDiscount(p)}</span>`);
            if (p.is_stackable) chips.push(`<span class="promo-chip chip-stackable">+คูปองได้</span>`);
            if (p.target_brand_name) chips.push(`<span class="promo-chip chip-brand">${p.target_brand_name}</span>`);
            if (p.min_tier_name) chips.push(`<span class="promo-chip chip-tier">${p.min_tier_name}+</span>`);
            const dateStr = p.end_date ? `หมดอายุ ${new Date(p.end_date).toLocaleDateString('th-TH')}` : 'ไม่มีกำหนดหมดอายุ';
            return `
            <div class="promo-card">
                <div class="promo-card-top">
                    <div class="promo-card-name">${p.name}</div>
                    <label class="toggle-switch" style="flex-shrink:0;">
                        <input type="checkbox" ${p.is_active ? 'checked' : ''} onchange="togglePromotion(${p.id}, this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="promo-chip-row">${chips.join('')}</div>
                <div class="promo-card-footer">
                    <div class="promo-card-date">${dateStr}</div>
                    <div class="promo-card-actions">
                        <button class="action-btn btn-review" onclick="openPromoModal(${p.id})">แก้ไข</button>
                        <button class="action-btn" style="background:rgba(239,68,68,0.2);color:#ef4444;" onclick="deletePromotion(${p.id})">ลบ</button>
                    </div>
                </div>
            </div>`;
        }).join('');
        document.getElementById('promoTableWrap').innerHTML = `<div class="promo-grid">${cards}</div>`;
    } catch (e) {
        document.getElementById('promoTableWrap').innerHTML = `<div class="empty-state"><p>เกิดข้อผิดพลาด</p></div>`;
    }
}

async function openPromoModal(id = null) {
    _editingPromoId = id;
    await _mktLoadMeta();

    const tierOptions = `<option value="">ทุกระดับ</option>` + _mktTiers.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    const brandOptions = `<option value="">ทุกแบรนด์</option>` + _mktBrands.map(b => `<option value="${b.id}">${b.name}</option>`).join('');

    let promo = {};
    if (id) {
        promo = _promoData.find(p => p.id === id) || {};
    }

    const html = `
    <div id="promoModal" class="modal" style="display:flex; z-index:10005;">
      <div class="apple-modal-content">

        <div class="apple-modal-header">
            <h3 class="apple-modal-title">${id ? 'แก้ไขโปรโมชัน' : 'สร้างโปรโมชันใหม่'}</h3>
            <button class="apple-modal-close" onclick="closePromoModal()">&times;</button>
        </div>

        <div class="apple-modal-body">

            <div class="apple-section" style="margin-top:16px;">
                <div class="apple-field">
                    <label class="apple-field-label">ชื่อโปรโมชัน <span style="color:#ec4899;">*</span></label>
                    <input id="pName" class="apple-input" value="${promo.name || ''}" placeholder="เช่น ซื้อครบ 1,000 ลด 10%">
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เงื่อนไข</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ซื้อครบ (฿)</label>
                        <input id="pMinSpend" class="apple-input" type="number" min="0" value="${promo.condition_min_spend || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">จำนวนขั้นต่ำ (ชิ้น)</label>
                        <input id="pMinQty" class="apple-input" type="number" min="0" value="${promo.condition_min_qty || 0}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">รางวัล</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ประเภทรางวัล</label>
                        <select id="pRewardType" class="apple-select" onchange="updatePromoRewardUI()">
                            <option value="discount_percent" ${promo.reward_type === 'discount_percent' ? 'selected' : ''}>ลดเป็น %</option>
                            <option value="discount_fixed" ${promo.reward_type === 'discount_fixed' ? 'selected' : ''}>ลดคงที่ (฿)</option>
                            <option value="free_item" ${promo.reward_type === 'free_item' ? 'selected' : ''}>ของแถม (GWP)</option>
                        </select>
                    </div>
                    <div id="pRewardValWrap" class="apple-field">
                        <label class="apple-field-label" id="pRewardValLabel">ส่วนลด (%)</label>
                        <input id="pRewardVal" class="apple-input" type="number" min="0" value="${promo.reward_value || 0}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เป้าหมาย</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">เฉพาะแบรนด์</label>
                        <select id="pBrand" class="apple-select">${brandOptions}</select>
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ระดับสมาชิกขั้นต่ำ</label>
                        <select id="pTier" class="apple-select">${tierOptions}</select>
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ช่วงเวลา</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">วันเริ่ม</label>
                        <input id="pStart" class="apple-input" type="datetime-local" value="${promo.start_date ? promo.start_date.substring(0,16) : ''}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">วันสิ้นสุด</label>
                        <input id="pEnd" class="apple-input" type="datetime-local" value="${promo.end_date ? promo.end_date.substring(0,16) : ''}">
                    </div>
                </div>
                <div class="apple-field" style="margin-top:10px;">
                    <label class="apple-field-label">ลำดับความสำคัญ <span class="apple-field-hint">(ตัวเลขสูง = ใช้ก่อน)</span></label>
                    <input id="pPriority" class="apple-input" type="number" value="${promo.priority || 0}" min="0">
                </div>
            </div>

            <div class="apple-section" style="margin-bottom:20px;">
                <span class="apple-section-label">การตั้งค่า</span>
                <div class="apple-toggle-card">
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">ใช้ร่วมกับคูปองได้</div>
                            <div class="apple-toggle-desc">ลูกค้าสามารถใช้คูปองซ้อนกับโปรโมชันนี้</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="pStackable" ${promo.is_stackable ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">เปิดใช้งาน</div>
                            <div class="apple-toggle-desc">โปรโมชันจะแสดงและใช้งานได้ทันที</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="pActive" ${promo.is_active !== false ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

        </div>

        <div class="apple-modal-footer">
            <button class="apple-btn-cancel" onclick="closePromoModal()">ยกเลิก</button>
            <button class="apple-btn-save" onclick="savePromotion()">บันทึก</button>
        </div>

      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);

    // Restore select values
    if (promo.target_brand_id) document.getElementById('pBrand').value = promo.target_brand_id;
    if (promo.min_tier_id) document.getElementById('pTier').value = promo.min_tier_id;
    updatePromoRewardUI();
}

function updatePromoRewardUI() {
    const type = document.getElementById('pRewardType').value;
    const label = document.getElementById('pRewardValLabel');
    const wrap = document.getElementById('pRewardValWrap');
    if (type === 'discount_percent') { label.textContent = 'ส่วนลด (%)'; wrap.style.display = ''; }
    else if (type === 'discount_fixed') { label.textContent = 'ส่วนลด (฿)'; wrap.style.display = ''; }
    else { wrap.style.display = 'none'; }
}

function closePromoModal() {
    const m = document.getElementById('promoModal');
    if (m) m.remove();
}

async function savePromotion() {
    const body = {
        name: document.getElementById('pName').value.trim(),
        promo_type: document.getElementById('pRewardType').value,
        condition_min_spend: parseFloat(document.getElementById('pMinSpend').value) || 0,
        condition_min_qty: parseInt(document.getElementById('pMinQty').value) || 0,
        reward_type: document.getElementById('pRewardType').value,
        reward_value: parseFloat(document.getElementById('pRewardVal').value) || 0,
        target_brand_id: document.getElementById('pBrand').value || null,
        min_tier_id: document.getElementById('pTier').value || null,
        start_date: document.getElementById('pStart').value || null,
        end_date: document.getElementById('pEnd').value || null,
        priority: parseInt(document.getElementById('pPriority').value) || 0,
        is_stackable: document.getElementById('pStackable').checked,
        is_active: document.getElementById('pActive').checked
    };
    if (!body.name) { showGlobalAlert('กรุณาระบุชื่อโปรโมชัน', 'error'); return; }
    const url = _editingPromoId ? `/api/admin/promotions/${_editingPromoId}` : '/api/admin/promotions';
    const method = _editingPromoId ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) {
            showGlobalAlert(_editingPromoId ? 'แก้ไขโปรโมชันเรียบร้อย' : 'สร้างโปรโมชันเรียบร้อย', 'success');
            closePromoModal();
            loadPromotions();
        } else {
            const d = await res.json();
            showGlobalAlert(d.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch { showGlobalAlert('เกิดข้อผิดพลาด', 'error'); }
}

async function togglePromotion(id, isActive) {
    const promo = _promoData.find(p => p.id === id);
    if (!promo) return;
    await fetch(`/api/admin/promotions/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ...promo, is_active: isActive })
    });
    loadPromotions();
}

async function deletePromotion(id) {
    if (!confirm('ลบโปรโมชันนี้?')) return;
    const res = await fetch(`/api/admin/promotions/${id}`, { method: 'DELETE' });
    if (res.ok) { showGlobalAlert('ลบเรียบร้อย', 'success'); loadPromotions(); }
    else showGlobalAlert('เกิดข้อผิดพลาด', 'error');
}

// ── Coupons ─────────────────────────────────────────────────────

async function loadCoupons() {
    try {
        const data = await fetch('/api/admin/coupons').then(r => r.json());
        _couponData = Array.isArray(data) ? data : [];
        const active = _couponData.filter(c => c.is_active).length;
        const totalUsed = _couponData.reduce((s, c) => s + (c.usage_count || 0), 0);
        document.getElementById('couponStats').innerHTML = `
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#fff;">${_couponData.length}</div>
                <div class="mkt-stat-lbl">ทั้งหมด</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#4ade80;">${active}</div>
                <div class="mkt-stat-lbl">กำลังใช้งาน</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#ffffff;">${totalUsed}</div>
                <div class="mkt-stat-lbl">ใช้ไปแล้ว</div>
            </div>
        `;
        if (!_couponData.length) {
            document.getElementById('couponTableWrap').innerHTML = `<div class="empty-state"><p>ยังไม่มีคูปอง — กดปุ่ม "สร้างคูปอง" เพื่อเริ่มต้น</p></div>`;
            return;
        }
        const typeColors = { percent: ['#7c3aed','#a78bfa'], fixed: ['#0e7490','#67e8f9'], free_shipping: ['#065f46','#6ee7b7'] };
        const typeLabels = { percent: 'ลด %', fixed: 'ลดคงที่', free_shipping: 'ส่งฟรี' };
        const cards = _couponData.map(c => {
            const [bg1, bg2] = typeColors[c.discount_type] || ['#4c1d95','#a78bfa'];
            const typeLabel = typeLabels[c.discount_type] || c.discount_type;
            const quota = c.total_quota > 0 ? `${c.usage_count || 0}/${c.total_quota}` : `${c.usage_count || 0}/∞`;
            const claimed = c.claimed_count || 0;
            const dateStr = c.end_date ? `หมดอายุ ${new Date(c.end_date).toLocaleDateString('th-TH')}` : 'ไม่มีกำหนด';
            const codeLen = (c.code || '').length;
            const codeFontSize = codeLen <= 7 ? '13px' : codeLen <= 10 ? '11px' : codeLen <= 14 ? '9px' : '8px';
            return `
            <div class="coupon-ticket" style="${!c.is_active ? 'opacity:0.5;' : ''}">
                <div class="coupon-ticket-left" style="background:linear-gradient(135deg,${bg1},${bg2});">
                    <div class="coupon-ticket-code" style="font-size:${codeFontSize};line-height:1.3;">${c.code}</div>
                    <div class="coupon-ticket-type">${typeLabel}</div>
                </div>
                <div class="coupon-ticket-right">
                    <div>
                        <div class="coupon-ticket-name">${c.name || _fmtCouponDiscount(c)}</div>
                        <div class="coupon-ticket-desc">${_fmtCouponDiscount(c)}${c.min_spend > 0 ? ' · ขั้นต่ำ ฿'+Number(c.min_spend).toLocaleString() : ''}</div>
                        ${c.applies_to && c.applies_to !== 'all' ? `<div style="margin-top:3px;font-size:10px;color:rgba(255,255,255,0.5);">${c.applies_to === 'brand' ? '🏷️ แบรนด์' : '📦 สินค้า'}: ${(c.applies_to_names && c.applies_to_names.length) ? c.applies_to_names.slice(0,2).join(', ') + (c.applies_to_names.length > 2 ? ` +${c.applies_to_names.length-2}` : '') : (c.applies_to_ids?.length || 0) + ' รายการ'}</div>` : ''}
                    </div>
                    <div class="coupon-ticket-footer">
                        <div>
                            <div class="coupon-ticket-meta">${dateStr}</div>
                            <div class="coupon-ticket-meta">เก็บแล้ว ${claimed} · ใช้แล้ว ${quota}</div>
                        </div>
                        <div class="coupon-ticket-actions">
                            <label class="toggle-switch">
                                <input type="checkbox" ${c.is_active ? 'checked' : ''} onchange="toggleCoupon(${c.id}, this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                            <button class="action-btn btn-review" onclick="openCouponModal(${c.id})">แก้ไข</button>
                            <button class="action-btn" style="background:rgba(34,197,94,0.25);color:#fff;" onclick="openDistributeModal(${c.id})" title="แจกให้สมาชิก">แจก</button>
                            <button class="action-btn" style="background:rgba(239,68,68,0.25);color:#fff;" onclick="deleteCoupon(${c.id})">ลบ</button>
                        </div>
                    </div>
                </div>
            </div>`;
        }).join('');
        document.getElementById('couponTableWrap').innerHTML = `<div class="coupon-grid">${cards}</div>`;
    } catch (e) {
        document.getElementById('couponTableWrap').innerHTML = `<div class="empty-state"><p>เกิดข้อผิดพลาด</p></div>`;
    }
}

async function openCouponModal(id = null) {
    _editingCouponId = id;
    await _mktLoadMeta();
    const tierOptions = `<option value="">ทุกระดับ</option>` + _mktTiers.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    let c = {};
    if (id) c = _couponData.find(x => x.id === id) || {};

    const html = `
    <div id="couponModal" class="modal" style="display:flex; z-index:10005;">
      <div class="apple-modal-content">

        <div class="apple-modal-header">
            <h3 class="apple-modal-title">${id ? 'แก้ไขคูปอง' : 'สร้างคูปองใหม่'}</h3>
            <button class="apple-modal-close" onclick="closeCouponModal()">&times;</button>
        </div>

        <div class="apple-modal-body">

            <div class="apple-section" style="margin-top:16px;">
                <span class="apple-section-label">รหัส & ชื่อ</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">รหัสคูปอง <span style="color:#ec4899;">*</span></label>
                        <input id="cCode" class="apple-input apple-input-code" value="${c.code || ''}" placeholder="SALE20" ${id ? 'readonly' : ''}>
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ชื่อคูปอง</label>
                        <input id="cName" class="apple-input" value="${c.name || ''}" placeholder="ลด 20% สำหรับสมาชิก">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ส่วนลด</span>
                <div class="apple-row-2" style="margin-bottom:10px;">
                    <div class="apple-field">
                        <label class="apple-field-label">ประเภท</label>
                        <select id="cType" class="apple-select" onchange="updateCouponUI()">
                            <option value="percent" ${c.discount_type === 'percent' ? 'selected' : ''}>ลดเป็น %</option>
                            <option value="fixed" ${c.discount_type === 'fixed' ? 'selected' : ''}>ลดคงที่ (฿)</option>
                            <option value="free_shipping" ${c.discount_type === 'free_shipping' ? 'selected' : ''}>ส่งฟรี</option>
                        </select>
                    </div>
                    <div id="cValWrap" class="apple-field">
                        <label class="apple-field-label" id="cValLabel">มูลค่าส่วนลด</label>
                        <input id="cVal" class="apple-input" type="number" min="0" value="${c.discount_value || 0}">
                    </div>
                </div>
                <div id="cMaxWrap" class="apple-field">
                    <label class="apple-field-label">ลดสูงสุด (฿) <span class="apple-field-hint">0 = ไม่จำกัด</span></label>
                    <input id="cMax" class="apple-input" type="number" min="0" value="${c.max_discount || 0}">
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เงื่อนไข</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ซื้อขั้นต่ำ (฿)</label>
                        <input id="cMinSpend" class="apple-input" type="number" min="0" value="${c.min_spend || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ระดับสมาชิกขั้นต่ำ</label>
                        <select id="cTier" class="apple-select">${tierOptions}</select>
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ใช้ได้กับ</span>
                <div class="apple-field" style="margin-bottom:10px;">
                    <label class="apple-field-label">ขอบเขตสินค้า</label>
                    <select id="cAppliesTo" class="apple-select" onchange="updateCouponAppliesTo()">
                        <option value="all" ${(!c.applies_to || c.applies_to === 'all') ? 'selected' : ''}>ทั้งหมด</option>
                        <option value="brand" ${c.applies_to === 'brand' ? 'selected' : ''}>เฉพาะแบรนด์</option>
                        <option value="product" ${c.applies_to === 'product' ? 'selected' : ''}>เฉพาะสินค้า</option>
                    </select>
                </div>
                <div id="cAppliesToPanel" style="display:none;">
                    <div id="cAppliesToSearch" style="margin-bottom:8px;">
                        <input id="cAppliesToSearchInput" class="apple-input" placeholder="ค้นหา..." oninput="filterCouponAppliesTo(this.value)" style="margin-bottom:6px;">
                    </div>
                    <div id="cAppliesToList" style="max-height:180px;overflow-y:auto;border:1px solid rgba(255,255,255,0.1);border-radius:10px;background:rgba(255,255,255,0.04);"></div>
                </div>
                <div id="cAppliesToSelected" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ขีดจำกัดการใช้งาน</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">จำนวนสิทธิ์ทั้งหมด <span class="apple-field-hint">0 = ไม่จำกัด</span></label>
                        <input id="cQuota" class="apple-input" type="number" min="0" value="${c.total_quota || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">จำกัดต่อสมาชิก (ครั้ง)</label>
                        <input id="cPerUser" class="apple-input" type="number" min="1" value="${c.per_user_limit || 1}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ช่วงเวลา</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">วันเริ่ม</label>
                        <input id="cStart" class="apple-input" type="datetime-local" value="${c.start_date ? c.start_date.substring(0,16) : ''}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">วันสิ้นสุด</label>
                        <input id="cEnd" class="apple-input" type="datetime-local" value="${c.end_date ? c.end_date.substring(0,16) : ''}">
                    </div>
                </div>
            </div>

            <div class="apple-section" style="margin-bottom:20px;">
                <span class="apple-section-label">การตั้งค่า</span>
                <div class="apple-toggle-card">
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">ใช้ร่วมกับโปรโมชันได้</div>
                            <div class="apple-toggle-desc">ใช้คูปองนี้ซ้อนกับโปรโมชันอัตโนมัติได้</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="cStackable" ${c.is_stackable ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">เปิดใช้งาน</div>
                            <div class="apple-toggle-desc">คูปองจะสามารถนำไปใช้ได้ทันที</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="cActive" ${c.is_active !== false ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

        </div>

        <div class="apple-modal-footer">
            <button class="apple-btn-cancel" onclick="closeCouponModal()">ยกเลิก</button>
            <button class="apple-btn-save" onclick="saveCoupon()">บันทึก</button>
        </div>

      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    if (c.min_tier_id) document.getElementById('cTier').value = c.min_tier_id;
    updateCouponUI();
    _couponAppliesToItems = [];
    _couponSelectedIds = new Set((c.applies_to_ids || []).map(Number));
    updateCouponAppliesTo();
}

let _couponAppliesToItems = [];
let _couponSelectedIds = new Set();

async function updateCouponAppliesTo() {
    const val = document.getElementById('cAppliesTo')?.value;
    const panel = document.getElementById('cAppliesToPanel');
    if (!panel) return;
    if (val === 'all') {
        panel.style.display = 'none';
        _renderCouponAppliesToSelected();
        return;
    }
    panel.style.display = 'block';
    const list = document.getElementById('cAppliesToList');
    list.innerHTML = '<div style="padding:12px;text-align:center;color:rgba(255,255,255,0.4);font-size:12px;">กำลังโหลด...</div>';
    try {
        if (val === 'brand') {
            const r = await fetch('/api/brands', { credentials: 'include' });
            const data = await r.json();
            _couponAppliesToItems = (Array.isArray(data) ? data : (data.brands || [])).map(b => ({ id: b.id, name: b.name }));
        } else {
            const r = await fetch('/api/admin/products?limit=200', { credentials: 'include' });
            const data = await r.json();
            _couponAppliesToItems = (Array.isArray(data) ? data : (data.products || [])).map(p => ({ id: p.id, name: p.name }));
        }
        _renderCouponAppliesToList('');
    } catch(e) {
        list.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
    _renderCouponAppliesToSelected();
}

function filterCouponAppliesTo(q) {
    _renderCouponAppliesToList(q.toLowerCase());
}

function _renderCouponAppliesToList(q) {
    const list = document.getElementById('cAppliesToList');
    if (!list) return;
    const filtered = q ? _couponAppliesToItems.filter(x => x.name.toLowerCase().includes(q)) : _couponAppliesToItems;
    if (!filtered.length) {
        list.innerHTML = '<div style="padding:12px;text-align:center;color:rgba(255,255,255,0.4);font-size:12px;">ไม่พบรายการ</div>';
        return;
    }
    list.innerHTML = filtered.map(item => `
        <div onclick="toggleCouponAppliesItem(${item.id}, ${JSON.stringify(item.name).replace(/"/g,'&quot;')})"
             style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:10px;transition:background 0.1s;border-bottom:1px solid rgba(255,255,255,0.05);"
             onmouseover="this.style.background='rgba(255,255,255,0.07)'" onmouseout="this.style.background='transparent'">
            <div style="width:18px;height:18px;border-radius:4px;border:2px solid ${_couponSelectedIds.has(item.id) ? '#a855f7' : 'rgba(255,255,255,0.3)'};background:${_couponSelectedIds.has(item.id) ? '#a855f7' : 'transparent'};display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.15s;">
                ${_couponSelectedIds.has(item.id) ? '<svg width="10" height="10" viewBox="0 0 12 12"><polyline points="1,6 5,10 11,2" stroke="white" stroke-width="2" fill="none" stroke-linecap="round"/></svg>' : ''}
            </div>
            <span style="font-size:13px;color:rgba(255,255,255,0.9);">${item.name}</span>
        </div>`).join('');
}

function toggleCouponAppliesItem(id, name) {
    if (_couponSelectedIds.has(id)) {
        _couponSelectedIds.delete(id);
    } else {
        _couponSelectedIds.add(id);
    }
    const q = document.getElementById('cAppliesToSearchInput')?.value?.toLowerCase() || '';
    _renderCouponAppliesToList(q);
    _renderCouponAppliesToSelected();
}

function _renderCouponAppliesToSelected() {
    const sel = document.getElementById('cAppliesToSelected');
    if (!sel) return;
    const val = document.getElementById('cAppliesTo')?.value;
    if (val === 'all' || _couponSelectedIds.size === 0) {
        sel.innerHTML = val === 'all' ? '<span style="font-size:12px;color:rgba(255,255,255,0.4);">ใช้ได้กับสินค้าทุกรายการ</span>' : '';
        return;
    }
    const allItems = _couponAppliesToItems;
    const tags = [..._couponSelectedIds].map(id => {
        const item = allItems.find(x => x.id === id);
        const name = item ? item.name : `#${id}`;
        return `<span style="background:rgba(168,85,247,0.25);border:1px solid rgba(168,85,247,0.4);border-radius:20px;padding:3px 10px;font-size:12px;color:#d8b4fe;display:flex;align-items:center;gap:4px;">
            ${name} <span onclick="toggleCouponAppliesItem(${id}, '')" style="cursor:pointer;opacity:0.7;font-size:14px;line-height:1;">&times;</span>
        </span>`;
    }).join('');
    sel.innerHTML = tags || '';
}

function updateCouponUI() {
    const type = document.getElementById('cType').value;
    const valWrap = document.getElementById('cValWrap');
    const maxWrap = document.getElementById('cMaxWrap');
    const label = document.getElementById('cValLabel');
    if (type === 'free_shipping') {
        valWrap.style.display = 'none';
        maxWrap.style.display = 'none';
    } else {
        valWrap.style.display = '';
        label.textContent = type === 'percent' ? 'ส่วนลด (%)' : 'ส่วนลด (฿)';
        maxWrap.style.display = type === 'percent' ? '' : 'none';
    }
}

function closeCouponModal() {
    const m = document.getElementById('couponModal');
    if (m) m.remove();
}

async function saveCoupon() {
    const appliesTo = document.getElementById('cAppliesTo')?.value || 'all';
    const body = {
        code: (document.getElementById('cCode').value || '').trim().toUpperCase(),
        name: (document.getElementById('cName').value || '').trim(),
        discount_type: document.getElementById('cType').value,
        discount_value: parseFloat(document.getElementById('cVal')?.value) || 0,
        max_discount: parseFloat(document.getElementById('cMax')?.value) || 0,
        min_spend: parseFloat(document.getElementById('cMinSpend').value) || 0,
        total_quota: parseInt(document.getElementById('cQuota').value) || 0,
        per_user_limit: parseInt(document.getElementById('cPerUser').value) || 1,
        min_tier_id: document.getElementById('cTier').value || null,
        start_date: document.getElementById('cStart').value || null,
        end_date: document.getElementById('cEnd').value || null,
        is_stackable: document.getElementById('cStackable').checked,
        is_active: document.getElementById('cActive').checked,
        applies_to: appliesTo,
        applies_to_ids: appliesTo !== 'all' ? [..._couponSelectedIds] : []
    };
    if (!body.code) { showGlobalAlert('กรุณาระบุรหัสคูปอง', 'error'); return; }
    const url = _editingCouponId ? `/api/admin/coupons/${_editingCouponId}` : '/api/admin/coupons';
    const method = _editingCouponId ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) {
            showGlobalAlert(_editingCouponId ? 'แก้ไขคูปองเรียบร้อย' : 'สร้างคูปองเรียบร้อย', 'success');
            closeCouponModal();
            loadCoupons();
        } else {
            const d = await res.json();
            showGlobalAlert(d.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch { showGlobalAlert('เกิดข้อผิดพลาด', 'error'); }
}

async function toggleCoupon(id, isActive) {
    const coupon = _couponData.find(c => c.id === id);
    if (!coupon) return;
    await fetch(`/api/admin/coupons/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ...coupon, is_active: isActive })
    });
    loadCoupons();
}

async function deleteCoupon(id) {
    if (!confirm('ลบคูปองนี้? สมาชิกที่เก็บไว้แล้วจะไม่สามารถใช้ได้อีก')) return;
    const res = await fetch(`/api/admin/coupons/${id}`, { method: 'DELETE' });
    if (res.ok) { showGlobalAlert('ลบเรียบร้อย', 'success'); loadCoupons(); }
    else showGlobalAlert('เกิดข้อผิดพลาด', 'error');
}

let _distributeCouponId = null;

async function openDistributeModal(id) {
    _distributeCouponId = id;
    const coupon = _couponData.find(c => c.id === id);
    if (!coupon) return;
    await _mktLoadMeta();
    const modal = document.getElementById('distributeCouponModal');
    if (!modal) return;
    document.getElementById('distributeCouponTitle').textContent = `แจกคูปอง: ${coupon.code}`;
    const tierList = document.getElementById('distributeTierList');
    tierList.innerHTML = _mktTiers.map(t => `
        <label style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">
            <input type="checkbox" value="${t.id}" class="distribute-tier-cb" style="width:16px;height:16px;accent-color:#a855f7;"
                   onchange="document.getElementById('distributeAllTiers').checked=false;_updateDistributePreview();">
            <span style="font-size:13px;color:#fff;">${t.name}</span>
        </label>`).join('');
    document.getElementById('distributePreviewText').textContent = 'เลือกระดับสมาชิกเพื่อดูจำนวน';
    document.getElementById('distributeConfirmBtn').textContent = 'แจก';
    document.getElementById('distributeConfirmBtn').disabled = false;
    modal.style.display = 'flex';
    await _updateDistributePreview();
}

async function _updateDistributePreview() {
    const cbs = document.querySelectorAll('.distribute-tier-cb:checked');
    const tierIds = Array.from(cbs).map(cb => cb.value);
    const params = tierIds.length ? `?tier_ids=${tierIds.join(',')}` : '';
    try {
        const r = await fetch(`/api/admin/coupons/${_distributeCouponId}/assign-preview${params}`);
        const d = await r.json();
        const count = d.count || 0;
        const tierLabel = tierIds.length ? `ระดับที่เลือก` : 'ทุกระดับ';
        document.getElementById('distributePreviewText').innerHTML =
            `<span style="color:rgba(255,255,255,0.6);">${tierLabel} — </span><span style="color:#a78bfa;font-weight:700;">${count} คน</span><span style="color:rgba(255,255,255,0.4);font-size:11px;"> ที่จะได้รับ (ข้ามคนที่มีอยู่แล้ว)</span>`;
        const btn = document.getElementById('distributeConfirmBtn');
        btn.textContent = count > 0 ? `แจก ${count} คน` : 'ไม่มีสมาชิกที่ต้องแจก';
        btn.disabled = count === 0;
    } catch {
        document.getElementById('distributePreviewText').textContent = 'โหลดจำนวนไม่สำเร็จ';
    }
}

function closeDistributeModal() {
    const modal = document.getElementById('distributeCouponModal');
    if (modal) modal.style.display = 'none';
    _distributeCouponId = null;
}

async function confirmDistribute() {
    if (!_distributeCouponId) return;
    const cbs = document.querySelectorAll('.distribute-tier-cb:checked');
    const tierIds = Array.from(cbs).map(cb => parseInt(cb.value));
    const btn = document.getElementById('distributeConfirmBtn');
    btn.disabled = true;
    btn.textContent = 'กำลังแจก...';
    try {
        const res = await fetch(`/api/admin/coupons/${_distributeCouponId}/assign`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tier_ids: tierIds })
        });
        const data = await res.json();
        if (res.ok) {
            closeDistributeModal();
            showGlobalAlert(`แจกคูปองให้ ${data.assigned} คน เรียบร้อย`, 'success');
            loadCoupons();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
            btn.disabled = false;
            btn.textContent = 'แจก';
        }
    } catch {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
        btn.disabled = false;
        btn.textContent = 'แจก';
    }
}

// ==================== END MARKETING MODULE ====================

// ==================== STOCK REPORT ====================

const _SIZE_ORDER = ['XS','S','M','L','XL','2XL','3XL','4XL','5XL','FREESIZE','FREE SIZE','ONE SIZE','ONESIZE'];

function _srParseVariant(variantName, skuCode) {
    const opts = {};
    (variantName || '').split(' / ').forEach(part => {
        const idx = part.indexOf(':');
        if (idx > 0) {
            opts[part.substring(0, idx).trim().toLowerCase()] = part.substring(idx + 1).trim();
        }
    });
    let size = opts['ขนาด'] || opts['ไซส์'] || opts['size'] || opts['ไซ'] || opts['sz'] || null;
    const color = opts['สี'] || opts['color'] || opts['ลาย'] || opts['pattern'] || null;

    if (!size && skuCode) {
        const parts = (skuCode || '').split('-');
        const last = (parts[parts.length - 1] || '').toUpperCase();
        if (_SIZE_ORDER.indexOf(last) >= 0) size = last;
    }

    return { size, color };
}

function _srSortSizes(sizes) {
    return [...sizes].sort((a, b) => {
        if (a === 'No Size') return 1;
        if (b === 'No Size') return -1;
        const ai = _SIZE_ORDER.indexOf(a.toUpperCase());
        const bi = _SIZE_ORDER.indexOf(b.toUpperCase());
        if (ai >= 0 && bi >= 0) return ai - bi;
        if (ai >= 0) return -1;
        if (bi >= 0) return 1;
        return a.localeCompare(b);
    });
}

function openStockReport() {
    const products = filteredProducts || [];
    if (!products.length) { showGlobalAlert('ไม่มีสินค้าที่จะสร้างรายงาน', 'error'); return; }

    const allSizesSet = new Set();
    const rows = [];

    products.forEach(p => {
        const skus = p.skus || [];
        const colorMap = {};

        skus.forEach(sku => {
            const { size, color } = _srParseVariant(sku.variant_name || '', sku.sku_code || '');
            const sizeKey = size ? size.toUpperCase() : 'No Size';
            const colorKey = color || '__none__';
            allSizesSet.add(sizeKey);
            if (!colorMap[colorKey]) colorMap[colorKey] = {};
            colorMap[colorKey][sizeKey] = (colorMap[colorKey][sizeKey] || 0) + (sku.stock || 0);
        });

        const colors = Object.keys(colorMap);
        const multiColor = colors.filter(c => c !== '__none__').length > 1;

        colors.forEach(colorKey => {
            const label = multiColor && colorKey !== '__none__'
                ? `${p.name} <span class="sr-color-label">(${colorKey})</span>`
                : p.name;
            rows.push({ label, sizeStock: colorMap[colorKey] });
        });

        if (skus.length === 0) rows.push({ label: p.name, sizeStock: {} });
    });

    const sortedSizes = _srSortSizes([...allSizesSet]);

    const colTotals = {};
    sortedSizes.forEach(s => { colTotals[s] = 0; });
    let grandTotal = 0;

    const tbody = rows.map(row => {
        let rowTotal = 0;
        const cells = sortedSizes.map(s => {
            const v = row.sizeStock[s] || 0;
            rowTotal += v;
            colTotals[s] += v;
            return v > 0 ? `<td>${v}</td>` : `<td class="dash">-</td>`;
        }).join('');
        grandTotal += rowTotal;
        return `<tr><td>${row.label}</td>${cells}<td class="total-col">${rowTotal || '-'}</td></tr>`;
    }).join('');

    const sumCells = sortedSizes.map(s => `<td>${colTotals[s] || '-'}</td>`).join('');
    const thead = `<thead><tr><th>รายการสินค้า</th>${sortedSizes.map(s => `<th>${s}</th>`).join('')}<th>รวม (ตัว)</th></tr></thead>`;
    const tfoot = `<tfoot><tr class="sum-row"><td>รวมทั้งหมด</td>${sumCells}<td>${grandTotal}</td></tr></tfoot>`;

    const dateStr = new Date().toLocaleDateString('th-TH', { year: 'numeric', month: 'long', day: 'numeric' });
    const brandEl = document.getElementById('filterBrand');
    const brandLabel = brandEl && brandEl.value ? ` · แบรนด์: ${brandEl.options[brandEl.selectedIndex].text}` : '';
    const statusTab = document.querySelector('.status-tab.active');
    const statusLabel = statusTab ? ` · สถานะ: ${statusTab.textContent.replace(/\d+/g, '').trim()}` : '';
    const searchVal = (document.getElementById('searchProduct')?.value || '').trim();
    const searchLabel = searchVal ? ` · ค้นหา: "${searchVal}"` : '';

    document.getElementById('srMeta').textContent =
        `สร้างเมื่อ: ${dateStr} · แสดง ${rows.length} รายการ${brandLabel}${statusLabel}${searchLabel}`;
    document.getElementById('srTable').innerHTML = thead + `<tbody>${tbody}</tbody>` + tfoot;
    document.getElementById('stockReportModal').classList.add('open');
}

function closeStockReport() {
    document.getElementById('stockReportModal').classList.remove('open');
}

function printStockReport() {
    window.print();
}

// ==================== CUSTOMER DATA PAGE ====================

let _allCustomers = [];
let _customerBrands = [];
let _customerProducts = [];
let _phoneCheckTimer = null;

const PLATFORM_LABEL = {
    shopee: '🛍️ Shopee', lazada: '📦 Lazada', tiktok: '🎵 TikTok',
    line: '💬 LINE', facebook: '📘 Facebook', onsale: '🏪 หน้าร้าน', other: '🔹 อื่นๆ'
};
const TAG_LABEL = { frequent: '🌟 ประจำ', new: '🆕 ใหม่', inactive: '💤 ไม่ active', reseller: '👤 ตัวแทน' };
const TAG_COLOR = { frequent: '#f59e0b', new: '#10b981', inactive: '#6b7280', reseller: '#7c3aed' };

async function loadCustomers() {
    try {
        const res = await fetch('/api/admin/customers');
        if (!res.ok) throw new Error(await res.text());
        _allCustomers = await res.json();
        renderCustomersTable(_allCustomers);
    } catch (e) {
        document.getElementById('customersTableContainer').innerHTML =
            `<div style="text-align:center;padding:40px;color:#f87171;">โหลดข้อมูลล้มเหลว: ${e.message}</div>`;
    }
}

function filterCustomers() {
    const q = (document.getElementById('customerSearchInput')?.value || '').toLowerCase();
    const platform = document.getElementById('customerPlatformFilter')?.value || '';
    const tag = document.getElementById('customerTagFilter')?.value || '';

    const filtered = _allCustomers.filter(c => {
        const matchQ = !q || (c.name || '').toLowerCase().includes(q) ||
            (c.phone || '').includes(q) || (c.province || '').toLowerCase().includes(q) ||
            (c.district || '').toLowerCase().includes(q) || (c.note || '').toLowerCase().includes(q);
        const matchPlatform = !platform || (c.platforms || []).includes(platform);
        const matchTag = !tag || c.auto_tag === tag || (c.tags || []).includes(tag);
        return matchQ && matchPlatform && matchTag;
    });
    renderCustomersTable(filtered);
}

function renderCustomersTable(customers) {
    const badge = document.getElementById('customerCountBadge');
    if (badge) badge.textContent = `${customers.length} คน`;

    if (!customers.length) {
        document.getElementById('customersTableContainer').innerHTML =
            `<div style="text-align:center;padding:60px;color:#8e8e93;">ไม่พบลูกค้า</div>`;
        return;
    }

    const TAG_BG   = { frequent: '#fff7ed', new: '#f0fdf4', inactive: '#f9fafb', reseller: '#f5f3ff' };
    const TAG_TEXT = { frequent: '#c2410c', new: '#15803d', inactive: '#6b7280', reseller: '#7c3aed' };

    const rows = customers.map(c => {
        const tagLabel = TAG_LABEL[c.auto_tag] || '';
        const tagBg   = TAG_BG[c.auto_tag]   || '#f3f4f6';
        const tagText = TAG_TEXT[c.auto_tag]  || '#6b7280';
        const isReseller = c.source_type === 'reseller';
        const platforms = (c.platforms || []).map(p =>
            `<span style="font-size:11px;background:#f3f4f6;color:#374151;padding:2px 7px;border-radius:5px;white-space:nowrap;">${PLATFORM_LABEL[p] || p}</span>`
        ).join(' ');
        const lastOrder = c.last_order_at
            ? new Date(c.last_order_at).toLocaleDateString('th-TH', { day:'2-digit', month:'short', year:'2-digit' })
            : '—';
        const spent = c.total_spent > 0 ? `฿${c.total_spent.toLocaleString('th-TH', { maximumFractionDigits: 0 })}` : '—';
        const subNote = isReseller
            ? `<div style="font-size:11px;color:#7c3aed;margin-top:2px;">ตัวแทน: ${c.reseller_name || '—'}</div>`
            : (c.note ? `<div style="font-size:11px;color:#8e8e93;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;">${c.note}</div>` : '');
        const actionBtns = isReseller
            ? `<span style="font-size:11px;color:#c7c7cc;">จัดการโดยตัวแทน</span>`
            : `<div style="display:flex;gap:6px;">
                <button onclick="openEditCustomerModal(${c.id})" style="padding:5px 12px;font-size:12px;font-weight:500;border-radius:8px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#f9fafb'" onmouseout="this.style.background='#fff'">แก้ไข</button>
                <button onclick="deleteCustomer(${c.id},'${(c.name||'ลูกค้า').replace(/'/g,'')}')" style="padding:5px 10px;font-size:12px;font-weight:500;border-radius:8px;border:1px solid #fecaca;background:#fff;color:#ef4444;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#fef2f2'" onmouseout="this.style.background='#fff'" title="ลบลูกค้า">
                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                </button>
               </div>`;
        return `<tr class="cust-row">
            <td style="padding:12px 14px;vertical-align:middle;max-width:200px;">
                <div style="font-weight:600;font-size:14px;color:#1d1d1f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${c.name || '<span style="color:#c7c7cc">ไม่มีชื่อ</span>'}</div>
                ${subNote}
            </td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:13px;color:#3a3a3c;white-space:nowrap;">${c.phone || '—'}</td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:12px;color:#6e6e73;">${[c.province, c.district].filter(Boolean).join(', ') || '—'}</td>
            <td style="padding:12px 14px;vertical-align:middle;text-align:center;font-size:13px;font-weight:600;color:#1d1d1f;">${isReseller ? '<span style="color:#c7c7cc">—</span>' : c.order_count}</td>
            <td style="padding:12px 14px;vertical-align:middle;text-align:right;font-size:13px;font-weight:600;color:#1d1d1f;">${isReseller ? '<span style="color:#c7c7cc">—</span>' : spent}</td>
            <td style="padding:12px 14px;vertical-align:middle;">
                <div style="display:flex;flex-wrap:wrap;gap:3px;">${platforms || '<span style="color:#c7c7cc;font-size:12px;">—</span>'}</div>
            </td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:12px;color:#6e6e73;white-space:nowrap;">${lastOrder}</td>
            <td style="padding:12px 14px;vertical-align:middle;">
                <span style="font-size:11px;background:${tagBg};color:${tagText};padding:3px 9px;border-radius:20px;font-weight:500;white-space:nowrap;">${tagLabel}</span>
            </td>
            <td style="padding:12px 14px;vertical-align:middle;">${actionBtns}</td>
        </tr>`;
    }).join('');

    document.getElementById('customersTableContainer').innerHTML = `
        <div style="background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08),0 0 0 1px rgba(0,0,0,0.05);overflow:hidden;">
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="background:#f9fafb;border-bottom:1px solid #e5e7eb;">
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">ชื่อ</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">เบอร์โทร</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">พื้นที่</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:center;">ออเดอร์</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:right;">ยอดรวม</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">แพลตฟอร์ม</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">สั่งล่าสุด</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">ประเภท</th>
                    <th style="padding:11px 14px;"></th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
        </div>
        </div>`;

    document.querySelectorAll('#customersTableContainer .cust-row').forEach(tr => {
        tr.style.borderBottom = '1px solid #f3f4f6';
        tr.style.transition = 'background 0.12s';
        tr.addEventListener('mouseenter', () => tr.style.background = '#fafafa');
        tr.addEventListener('mouseleave', () => tr.style.background = '');
    });
}

async function deleteCustomer(id, name) {
    if (!confirm(`ลบลูกค้า "${name}" ออกจากระบบ?\nออเดอร์ที่เกี่ยวข้องจะไม่ถูกลบ`)) return;
    try {
        const res = await fetch(`/api/admin/customers/${id}`, { method: 'DELETE', credentials: 'include' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'ลบไม่สำเร็จ');
        showGlobalAlert('ลบลูกค้าสำเร็จ', 'success');
        _allCustomers = _allCustomers.filter(c => !(c.source_type === 'admin' && c.id === id));
        filterCustomers();
    } catch (e) {
        showGlobalAlert(e.message, 'error');
    }
}

function openAddCustomerModal() {
    document.getElementById('editCustomerId').value = '';
    document.getElementById('addCustomerModalTitle').textContent = 'เพิ่มลูกค้าใหม่';
    document.getElementById('custName').value = '';
    document.getElementById('custPhone').value = '';
    document.getElementById('custAddress').value = '';
    document.getElementById('custSubdistrict').value = '';
    document.getElementById('custDistrict').value = '';
    document.getElementById('custProvince').value = '';
    document.getElementById('custPostal').value = '';
    document.getElementById('custSource').value = 'manual';
    document.getElementById('custNote').value = '';
    document.getElementById('custDuplicateWarning').style.display = 'none';
    document.getElementById('customerScanStatus').style.display = 'none';
    const prevImg = document.getElementById('custLabelPreview');
    if (prevImg) { prevImg.src = ''; prevImg.style.display = 'none'; }
    document.getElementById('addCustomerModal').style.display = 'flex';
    _labelPasteContext = 'customer';

    const phoneInput = document.getElementById('custPhone');
    phoneInput.oninput = () => {
        clearTimeout(_phoneCheckTimer);
        _phoneCheckTimer = setTimeout(() => checkCustomerPhoneDuplicate(phoneInput.value), 600);
    };
}

function openEditCustomerModal(id) {
    const c = _allCustomers.find(x => x.id === id);
    if (!c) return;
    document.getElementById('editCustomerId').value = c.id;
    document.getElementById('addCustomerModalTitle').textContent = 'แก้ไขข้อมูลลูกค้า';
    document.getElementById('custName').value = c.name || '';
    document.getElementById('custPhone').value = c.phone || '';
    document.getElementById('custAddress').value = c.address || '';
    document.getElementById('custSubdistrict').value = c.subdistrict || '';
    document.getElementById('custDistrict').value = c.district || '';
    document.getElementById('custProvince').value = c.province || '';
    document.getElementById('custPostal').value = c.postal_code || '';
    document.getElementById('custSource').value = c.source || 'manual';
    document.getElementById('custNote').value = c.note || '';
    document.getElementById('custDuplicateWarning').style.display = 'none';
    document.getElementById('customerScanStatus').style.display = 'none';
    document.getElementById('addCustomerModal').style.display = 'flex';
    _labelPasteContext = 'customer';

    const phoneInput = document.getElementById('custPhone');
    const origPhone = c.phone || '';
    phoneInput.oninput = () => {
        clearTimeout(_phoneCheckTimer);
        if (phoneInput.value !== origPhone) {
            _phoneCheckTimer = setTimeout(() => checkCustomerPhoneDuplicate(phoneInput.value), 600);
        } else {
            document.getElementById('custDuplicateWarning').style.display = 'none';
        }
    };
}

function closeAddCustomerModal() {
    document.getElementById('addCustomerModal').style.display = 'none';
    _labelPasteContext = null;
}

async function checkCustomerPhoneDuplicate(phone) {
    if (!phone || phone.length < 9) {
        document.getElementById('custDuplicateWarning').style.display = 'none';
        return;
    }
    try {
        const res = await fetch(`/api/admin/customers/check-phone?phone=${encodeURIComponent(phone)}`);
        const data = await res.json();
        const warn = document.getElementById('custDuplicateWarning');
        if (data.exists) {
            warn.style.display = 'block';
            warn.innerHTML = `<strong>⚠️ เบอร์นี้มีในระบบแล้ว</strong> (${data.name || 'ไม่มีชื่อ'}) — จะอัปเดตข้อมูลลูกค้าเดิม`;
        } else {
            warn.style.display = 'none';
        }
    } catch {}
}

async function handleCustomerLabelUpload(input) {
    if (input.files && input.files[0]) await _processLabelFile(input.files[0], 'customer');
}

async function saveCustomer() {
    const btn = document.getElementById('btnSaveCustomer');
    btn.disabled = true;
    btn.textContent = 'กำลังบันทึก...';

    const payload = {
        id: document.getElementById('editCustomerId').value || null,
        name: document.getElementById('custName').value.trim(),
        phone: document.getElementById('custPhone').value.trim(),
        address: document.getElementById('custAddress').value.trim(),
        subdistrict: document.getElementById('custSubdistrict').value.trim(),
        district: document.getElementById('custDistrict').value.trim(),
        province: document.getElementById('custProvince').value.trim(),
        postal_code: document.getElementById('custPostal').value.trim(),
        source: document.getElementById('custSource').value,
        note: document.getElementById('custNote').value.trim()
    };

    if (!payload.name && !payload.phone && !payload.address) {
        showAlert('กรุณากรอกชื่อ, เบอร์โทร หรือที่อยู่ อย่างน้อย 1 อย่าง', 'error');
        btn.disabled = false;
        btn.textContent = 'บันทึกลูกค้า';
        return;
    }

    try {
        const res = await fetch('/api/admin/customers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'บันทึกล้มเหลว');
        showAlert('บันทึกข้อมูลลูกค้าสำเร็จ', 'success');
        closeAddCustomerModal();
        loadCustomers();
    } catch (e) {
        showAlert(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'บันทึกลูกค้า';
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('addCustomerModal');
        if (modal && modal.style.display !== 'none') closeAddCustomerModal();
    }
});

document.addEventListener('paste', (e) => {
    if (!_labelPasteContext) return;
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
        if (item.type.startsWith('image/')) {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) _processLabelFile(file, _labelPasteContext);
            break;
        }
    }
});

// ==================== END CUSTOMER DATA PAGE ====================

// ==================== END STOCK REPORT ====================
