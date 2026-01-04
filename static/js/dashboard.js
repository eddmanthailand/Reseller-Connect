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

// Sidebar Toggle Function
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
        
        // Load applications count badge
        loadApplicationsCount();
        
        // Handle hash navigation (e.g., /admin#products)
        handleHashNavigation();
        
        // Listen for hash changes
        window.addEventListener('hashchange', handleHashNavigation);
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
        const [pageName] = fullHash.split('?');
        const validPages = ['home', 'users', 'applications', 'products', 'brands', 'categories', 'warehouses', 'stock-summary', 'stock-transfer', 'stock-adjustment', 'stock-import', 'stock-history', 'orders', 'slip-review', 'quick-order', 'tier-settings', 'settings'];
        if (validPages.includes(pageName)) {
            switchPage(pageName);
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
    } catch (error) {
        console.error('Error loading current user:', error);
        window.location.href = '/login';
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
async function handleLogout() {
    showConfirmAlert('คุณต้องการออกจากระบบหรือไม่?', async () => {
        try {
            const response = await fetch(`${API_URL}/logout`, {
                method: 'POST'
            });
            
            if (response.ok) {
                showAlert('ออกจากระบบสำเร็จ', 'success');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1000);
            } else {
                throw new Error('Logout failed');
            }
        } catch (error) {
            console.error('Logout error:', error);
            showAlert('เกิดข้อผิดพลาดในการออกจากระบบ', 'error');
        }
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
                return; // Let the browser handle the link
            }
            
            e.preventDefault();
            const targetPage = item.dataset.page;
            
            // Handle submenu toggle
            if (item.classList.contains('has-submenu')) {
                item.classList.toggle('expanded');
                const submenu = document.getElementById(`${targetPage}-submenu`);
                if (submenu) {
                    submenu.classList.toggle('open');
                }
            }
            
            if (targetPage) {
                switchPage(targetPage);
            }
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
    } else if (pageName === 'tier-settings') {
        loadTierSettings();
        loadResellers();
    } else if (pageName === 'settings') {
        loadSettings();
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
    } else if (pageName === 'slip-review') {
        loadSlipReviewPage();
    } else if (pageName === 'applications') {
        loadApplicationsPage();
    } else if (pageName === 'activity-logs') {
        loadActivityLogs();
    }
}

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
        'cancelled': 'ยกเลิก'
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
        'cancelled': '#6b7280'
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
                <td>${escapeHtml(order.customer_name || 'N/A')}</td>
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
        const response = await fetch(`${API_URL}/admin/orders?status=under_review`);
        const reviewOrders = await response.json();
        
        const reviewCountEl = document.getElementById('reviewCount');
        const pendingBadge = document.getElementById('pendingOrderCount');
        
        if (reviewCountEl) reviewCountEl.textContent = reviewOrders.length;
        if (pendingBadge) {
            if (reviewOrders.length > 0) {
                pendingBadge.textContent = reviewOrders.length;
                pendingBadge.style.display = 'inline';
            } else {
                pendingBadge.style.display = 'none';
            }
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
            'shipped': 'กำลังจัดส่ง',
            'delivered': 'จัดส่งสำเร็จ',
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
                            <img src="${slip.slip_image_url}" alt="Payment Slip" style="max-width: 100%; max-height: 200px; border-radius: 8px; display: block; margin: 0 auto;">
                            <div style="margin-top: 12px; display: flex; align-items: center; gap: 12px; font-size: 13px; color: #fff;">
                                <span style="background: ${slip.status === 'approved' ? 'linear-gradient(135deg, #22c55e, #16a34a)' : slip.status === 'rejected' ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 'linear-gradient(135deg, #f59e0b, #d97706)'}; color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">${slip.status === 'approved' ? 'อนุมัติแล้ว' : slip.status === 'rejected' ? 'ปฏิเสธ' : 'รอตรวจสอบ'}</span>
                                ${slip.amount ? `<span>ยอด: <strong>฿${parseFloat(slip.amount).toLocaleString('th-TH')}</strong></span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        // Build action buttons based on order status
        let actionsHtml = '';
        if (order.status === 'under_review') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;">
                    <button onclick="approveSlip(${orderId}); closeModal('orderDetailModal');" style="padding: 14px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยืนยันการชำระเงิน
                    </button>
                    <button onclick="requestNewSlip(${orderId}); closeModal('orderDetailModal');" style="padding: 14px; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ขอสลิปใหม่
                    </button>
                </div>
            `;
        } else if (order.status === 'pending_payment') {
            actionsHtml = `
                <div style="margin-top: 24px;">
                    <button onclick="cancelOrderAdmin(${orderId})" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิกคำสั่งซื้อ
                    </button>
                </div>
            `;
        } else if (order.status === 'preparing') {
            actionsHtml = `
                <div style="margin-top: 24px;">
                    <button onclick="cancelOrderAdmin(${orderId})" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิกคำสั่งซื้อ
                    </button>
                </div>
            `;
        } else if (order.status === 'shipped') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;">
                    <button onclick="markDelivered(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ส่งสำเร็จ
                    </button>
                    <button onclick="markFailedDelivery(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        จัดส่งไม่สำเร็จ
                    </button>
                </div>
            `;
        } else if (order.status === 'failed_delivery') {
            actionsHtml = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;">
                    <button onclick="reshipOrder(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        จัดส่งใหม่
                    </button>
                    <button onclick="cancelOrderAdmin(${orderId})" style="padding: 14px; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        ยกเลิก / คืนเงิน
                    </button>
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
                    <div style="display: flex; justify-content: space-between; padding: 16px 0 0; margin-top: 12px; border-top: 2px solid rgba(255,255,255,0.15);">
                        <span style="color: #fff; font-size: 16px; font-weight: 600;">ยอดรวมทั้งหมด</span>
                        <span style="color: #fff; font-size: 20px; font-weight: 700;">฿${parseFloat(order.final_amount || order.total_amount || 0).toLocaleString('th-TH')}</span>
                    </div>
                </div>
                
                ${shipmentsHtml}
                ${slipHtml}
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
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showGlobalAlert('อนุมัติคำสั่งซื้อสำเร็จ', 'success');
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

async function approveSlip(orderId) {
    if (!confirm('ยืนยันการชำระเงินและเริ่มเตรียมสินค้า?')) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showGlobalAlert('อนุมัติสลิปสำเร็จ - เริ่มเตรียมสินค้า', 'success');
            loadOrders(currentOrdersStatus);
            loadSlipReviewOrders();
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error approving slip:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function requestNewSlip(orderId) {
    const reason = prompt('เหตุผลที่ต้องขอสลิปใหม่ (เช่น สลิปไม่ชัด, ยอดเงินไม่ตรง):', 'สลิปไม่ชัด กรุณาส่งใหม่');
    if (!reason) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/request-new-slip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        if (response.ok) {
            showGlobalAlert('แจ้งขอสลิปใหม่สำเร็จ', 'warning');
            loadOrders(currentOrdersStatus);
            loadSlipReviewOrders();
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error requesting new slip:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function rejectOrder(orderId) {
    const reason = prompt('เหตุผลในการปฏิเสธ:');
    if (reason === null) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        if (response.ok) {
            showGlobalAlert('ปฏิเสธคำสั่งซื้อสำเร็จ', 'success');
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

async function cancelOrderAdmin(orderId) {
    const reason = prompt('เหตุผลในการยกเลิก:');
    if (reason === null) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        if (response.ok) {
            showGlobalAlert('ยกเลิกคำสั่งซื้อสำเร็จ สต็อกถูกคืนกลับแล้ว', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showGlobalAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error cancelling order:', error);
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
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
        .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #333; }
        .provider-box { background: #f0f0f0; padding: 8px 15px; border-radius: 5px; font-size: 16px; font-weight: bold; }
        .tracking-box { text-align: right; }
        .tracking-number { font-size: 18px; font-weight: bold; letter-spacing: 1px; }
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
</head>
<body>
    <div class="page">
        <!-- Top Half: Shipping Info -->
        <div class="half shipping-half">
            <div class="header">
                <div class="provider-box">${shippingProvider || '-- ขนส่ง --'}</div>
                <div class="tracking-box">
                    ${trackingNumber ? `<div class="tracking-number">${trackingNumber}</div>` : '<div style="color: #999;">-- ยังไม่มีเลขพัสดุ --</div>'}
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
            setTimeout(function() {
                window.print();
            }, 300);
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
    loadChannels();
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
        'paid': 'ชำระแล้ว',
        'cancelled': 'ยกเลิก'
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
        'paid': 'ชำระแล้ว',
        'cancelled': 'ยกเลิก'
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

// ==================== SLIP REVIEW SECTION ====================

async function loadSlipReviewPage() {
    const container = document.getElementById('slipReviewContent');
    if (!container) return;
    
    container.innerHTML = '<div style="text-align: center; padding: 40px; opacity: 0.6;">กำลังโหลดข้อมูล...</div>';
    
    await loadSlipReviewOrders();
}

async function loadSlipReviewOrders() {
    const container = document.getElementById('slipReviewContent');
    if (!container) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders?status=under_review`);
        if (!response.ok) throw new Error('Failed to load orders');
        const orders = await response.json();
        
        // Update badge count
        const badge = document.getElementById('slipReviewCount');
        if (badge) {
            if (orders.length > 0) {
                badge.textContent = orders.length;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
        
        if (orders.length === 0) {
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 60px;">
                    <svg width="64" height="64" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1.5" viewBox="0 0 24 24" style="margin: 0 auto 16px;">
                        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <h3 style="color: #fff; font-size: 18px; margin-bottom: 8px;">ไม่มีสลิปรอตรวจสอบ</h3>
                    <p style="color: rgba(255,255,255,0.5); font-size: 14px;">สลิปทั้งหมดถูกตรวจสอบแล้ว</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px;">
                ${orders.map(order => renderSlipReviewCard(order)).join('')}
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading slip review orders:', error);
        container.innerHTML = '<div style="text-align: center; padding: 40px; color: #f87171;">เกิดข้อผิดพลาดในการโหลดข้อมูล</div>';
    }
}

function renderSlipReviewCard(order) {
    const orderDate = new Date(order.created_at).toLocaleDateString('th-TH', { 
        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' 
    });
    
    const slipUrl = order.payment_slips && order.payment_slips.length > 0 
        ? order.payment_slips[order.payment_slips.length - 1].slip_image_url 
        : null;
    
    return `
        <div class="card" style="padding: 0; overflow: hidden;">
            <div style="display: grid; grid-template-columns: 140px 1fr; min-height: 240px;">
                <div style="background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; cursor: pointer;" onclick="viewSlipFullscreen('${slipUrl}')">
                    ${slipUrl 
                        ? `<img src="${slipUrl}" alt="Payment Slip" style="width: 100%; height: 100%; object-fit: contain;">`
                        : `<div style="color: rgba(255,255,255,0.3); text-align: center; padding: 20px;">ไม่มีสลิป</div>`
                    }
                </div>
                <div style="padding: 16px; display: flex; flex-direction: column;">
                    <div style="margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #fff; font-size: 15px;">#${escapeHtml(order.order_number || 'ORD-' + order.id)}</span>
                            <span style="background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500;">รอตรวจสอบ</span>
                        </div>
                        <div style="font-size: 12px; color: rgba(255,255,255,0.5);">${orderDate}</div>
                    </div>
                    
                    <div style="font-size: 13px; color: #fff; margin-bottom: 8px;">
                        <strong>${escapeHtml(order.reseller_name || 'ไม่ระบุ')}</strong>
                        ${order.reseller_tier_name ? `<span style="color: rgba(255,255,255,0.5);"> (${escapeHtml(order.reseller_tier_name)})</span>` : ''}
                    </div>
                    
                    <div style="font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 12px;">
                        ${order.item_count || '-'} รายการ
                    </div>
                    
                    <div style="font-size: 18px; font-weight: 700; color: #22c55e; margin-bottom: auto;">
                        ฿${parseFloat(order.total_amount).toLocaleString('th-TH', {minimumFractionDigits: 2})}
                    </div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px;">
                        <button onclick="approveSlip(${order.id})" style="padding: 10px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;">
                            อนุมัติ
                        </button>
                        <button onclick="requestNewSlip(${order.id})" style="padding: 10px; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;">
                            ขอสลิปใหม่
                        </button>
                    </div>
                    
                    <button onclick="viewOrderDetails(${order.id})" style="width: 100%; padding: 8px; background: rgba(255,255,255,0.1); color: #fff; border: none; border-radius: 8px; font-size: 12px; cursor: pointer; margin-top: 8px;">
                        ดูรายละเอียด
                    </button>
                </div>
            </div>
        </div>
    `;
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
                    <button type="button" onclick="updateQuickOrderItemQty(${item.sku_id}, -1)" style="width: 28px; height: 28px; border: none; border-radius: 6px; background: rgba(239,68,68,0.2); color: #ef4444; cursor: pointer; font-size: 16px; font-weight: 700;">-</button>
                    <span style="min-width: 24px; text-align: center; font-weight: 600;">${item.quantity}</span>
                    <button type="button" onclick="updateQuickOrderItemQty(${item.sku_id}, 1)" style="width: 28px; height: 28px; border: none; border-radius: 6px; background: rgba(16,185,129,0.2); color: #10b981; cursor: pointer; font-size: 16px; font-weight: 700;">+</button>
                </div>
                <button type="button" onclick="removeQuickOrderItem(${item.sku_id})" style="background: none; border: none; color: #ef4444; cursor: pointer; font-size: 11px; opacity: 0.8;">ลบ</button>
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
    const customerName = document.getElementById('quickOrderCustomerName').value.trim();
    const customerPhone = document.getElementById('quickOrderCustomerPhone').value.trim();
    const notes = document.getElementById('quickOrderNotes').value.trim();
    
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
                customer_name: customerName || null,
                customer_phone: customerPhone || null,
                notes: notes || null,
                items: quickOrderItems.map(item => ({
                    sku_id: item.sku_id,
                    quantity: item.quantity,
                    price: item.price
                }))
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showGlobalAlert(`สร้างคำสั่งซื้อสำเร็จ! เลขที่: ${result.order_number}`, 'success');
            quickOrderItems = [];
            document.getElementById('quickOrderCustomerName').value = '';
            document.getElementById('quickOrderCustomerPhone').value = '';
            document.getElementById('quickOrderNotes').value = '';
            document.getElementById('quickOrderChannel').value = '';
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

// =====================================================
// SLIP REVIEW PAGE FUNCTIONS
// =====================================================

async function loadSlipReviewPage() {
    const container = document.getElementById('slipReviewContent');
    if (!container) return;
    
    container.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="loading-spinner"></div><p>กำลังโหลด...</p></div>';
    
    try {
        const response = await fetch(`${API_URL}/admin/orders?status=under_review`);
        if (!response.ok) throw new Error('Failed to load orders');
        
        const orders = await response.json();
        
        if (orders.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px;">
                    <svg width="64" height="64" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1.5" viewBox="0 0 24 24" style="margin: 0 auto 16px;">
                        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <h3 style="color: rgba(255,255,255,0.6); font-size: 18px; margin-bottom: 8px;">ไม่มีสลิปรอตรวจสอบ</h3>
                    <p style="color: rgba(255,255,255,0.4); font-size: 14px;">สลิปทั้งหมดได้รับการตรวจสอบแล้ว</p>
                </div>
            `;
            return;
        }
        
        // Fetch full details for each order
        const orderDetails = await Promise.all(orders.map(async (order) => {
            const detailRes = await fetch(`${API_URL}/orders/${order.id}`);
            return await detailRes.json();
        }));
        
        container.innerHTML = `
            <div style="display: grid; gap: 20px;">
                ${orderDetails.map(order => {
                    const slip = order.payment_slips && order.payment_slips.length > 0 ? order.payment_slips[0] : null;
                    const customerName = order.customer ? order.customer.full_name : order.reseller_name;
                    const itemCount = order.items ? order.items.reduce((sum, i) => sum + i.quantity, 0) : 0;
                    
                    return `
                    <div class="slip-review-card" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; overflow: hidden;">
                        <div style="display: grid; grid-template-columns: 280px 1fr; gap: 0;">
                            <!-- Slip Image -->
                            <div style="padding: 20px; background: rgba(0,0,0,0.2); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                                ${slip ? `
                                    <img src="${slip.slip_image_url}" alt="Payment Slip" 
                                         style="max-width: 100%; max-height: 300px; border-radius: 8px; cursor: pointer; transition: transform 0.2s;"
                                         onclick="showSlipFullscreen('${slip.slip_image_url}')"
                                         onmouseover="this.style.transform='scale(1.02)'" 
                                         onmouseout="this.style.transform='scale(1)'">
                                    <p style="font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 8px;">คลิกเพื่อขยาย</p>
                                ` : `
                                    <div style="color: rgba(255,255,255,0.4); text-align: center;">
                                        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                                            <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                                        </svg>
                                        <p style="margin-top: 8px;">ไม่มีสลิป</p>
                                    </div>
                                `}
                            </div>
                            
                            <!-- Order Info -->
                            <div style="padding: 20px;">
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                                    <div>
                                        <h3 style="color: #fff; font-size: 18px; font-weight: 600; margin: 0 0 4px 0;">${order.order_number || '#' + order.id}</h3>
                                        <p style="color: rgba(255,255,255,0.5); font-size: 13px; margin: 0;">${new Date(order.created_at).toLocaleString('th-TH')}</p>
                                    </div>
                                    <span style="background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: #fff; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 500;">รอตรวจสอบ</span>
                                </div>
                                
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
                                    <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
                                        <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">ผู้สั่ง</div>
                                        <div style="font-size: 14px; color: #fff; font-weight: 500;">${escapeHtml(order.reseller_name || '-')}</div>
                                        <div style="font-size: 12px; color: rgba(255,255,255,0.6);">${escapeHtml(order.reseller_tier_name || '')}</div>
                                    </div>
                                    <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
                                        <div style="font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 4px;">ผู้รับ</div>
                                        <div style="font-size: 14px; color: #fff; font-weight: 500;">${escapeHtml(customerName || '-')}</div>
                                    </div>
                                </div>
                                
                                <div style="display: flex; gap: 20px; margin-bottom: 16px; font-size: 14px;">
                                    <div><span style="color: rgba(255,255,255,0.5);">สินค้า:</span> <strong style="color: #fff;">${itemCount} ชิ้น</strong></div>
                                    <div><span style="color: rgba(255,255,255,0.5);">ยอดรวม:</span> <strong style="color: #22c55e;">฿${parseFloat(order.final_amount || 0).toLocaleString('th-TH')}</strong></div>
                                    ${slip && slip.amount ? `<div><span style="color: rgba(255,255,255,0.5);">ยอดในสลิป:</span> <strong style="color: #fbbf24;">฿${parseFloat(slip.amount).toLocaleString('th-TH')}</strong></div>` : ''}
                                </div>
                                
                                <!-- Action Buttons -->
                                <div style="display: flex; gap: 12px;">
                                    <button onclick="approveSlip(${order.id})" style="flex: 1; padding: 12px 20px; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;">
                                        <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                                        ยืนยันการชำระเงิน
                                    </button>
                                    <button onclick="requestNewSlip(${order.id})" style="flex: 1; padding: 12px 20px; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;">
                                        <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                                        ขอสลิปใหม่
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                    `;
                }).join('')}
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading slip review:', error);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #ef4444;">
                <p>เกิดข้อผิดพลาดในการโหลดข้อมูล</p>
                <button onclick="loadSlipReviewPage()" style="margin-top: 12px; padding: 8px 16px; background: rgba(255,255,255,0.1); color: #fff; border: none; border-radius: 8px; cursor: pointer;">ลองใหม่</button>
            </div>
        `;
    }
}

function showSlipFullscreen(imageUrl) {
    const overlay = document.createElement('div');
    overlay.id = 'slipFullscreenOverlay';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.9); z-index: 10000; display: flex; align-items: center; justify-content: center; cursor: pointer;';
    overlay.onclick = () => overlay.remove();
    
    overlay.innerHTML = `
        <img src="${imageUrl}" style="max-width: 90%; max-height: 90%; border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.5);">
        <button style="position: absolute; top: 20px; right: 20px; background: rgba(255,255,255,0.1); border: none; color: #fff; width: 48px; height: 48px; border-radius: 50%; cursor: pointer; font-size: 24px;">×</button>
    `;
    
    document.body.appendChild(overlay);
}

async function approveSlip(orderId) {
    if (!confirm('ยืนยันการชำระเงินและอนุมัติคำสั่งซื้อนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        if (response.ok) {
            showGlobalAlert('อนุมัติคำสั่งซื้อสำเร็จ - สถานะเปลี่ยนเป็น "ที่ต้องจัดส่ง"', 'success');
            loadSlipReviewPage();
        } else {
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error approving order:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการอนุมัติ', 'error');
    }
}

async function requestNewSlip(orderId) {
    const reason = prompt('เหตุผลในการขอสลิปใหม่:', 'สลิปไม่ชัด');
    if (!reason) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/orders/${orderId}/request-new-slip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        
        const result = await response.json();
        if (response.ok) {
            showGlobalAlert('ขอสลิปใหม่สำเร็จ - แจ้งเตือนตัวแทนจำหน่ายแล้ว', 'success');
            loadSlipReviewPage();
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
            '<tr><td colspan="5" style="text-align: center; color: #ef4444;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

function renderShippingPromos() {
    const tbody = document.getElementById('shippingPromosTableBody');
    if (!tbody) return;
    
    if (shippingPromos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: rgba(255,255,255,0.5);">ยังไม่มีโปรโมชั่น</td></tr>';
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
        
        return `
            <tr>
                <td>${escapeHtml(promo.name)}</td>
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

function showAddShippingPromoModal() {
    editingPromoId = null;
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

function editShippingPromo(id) {
    const promo = shippingPromos.find(p => p.id === id);
    if (!promo) return;
    
    editingPromoId = id;
    const showDiscount = promo.promo_type !== 'free_shipping';
    
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
    const discountValue = parseFloat(document.getElementById('promoDiscountValue').value) || 0;
    const isActive = document.getElementById('promoIsActive').checked;
    
    if (!name) {
        showGlobalAlert('กรุณากรอกชื่อโปรโมชั่น', 'error');
        return;
    }
    
    const data = {
        name: name,
        promo_type: promoType,
        min_order_value: minAmount,
        discount_amount: promoType === 'free_shipping' ? 100 : discountValue,
        is_active: isActive
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

// ==================== RESELLER APPLICATIONS ====================
let allApplications = [];
let currentApplicationStatus = 'pending';
let currentApplicationId = null;

async function loadApplicationsPage() {
    await loadApplications(currentApplicationStatus);
    await loadApplicationsCount();
}

async function loadApplicationsCount() {
    try {
        const response = await fetch(`${API_URL}/reseller-applications/count`);
        if (response.ok) {
            const data = await response.json();
            const badge = document.getElementById('applicationsCount');
            if (badge) {
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline-flex';
                } else {
                    badge.style.display = 'none';
                }
            }
        }
    } catch (error) {
        console.error('Error loading applications count:', error);
    }
}

async function loadApplications(status = 'pending') {
    currentApplicationStatus = status;
    const tbody = document.getElementById('applicationsTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center;">กำลังโหลด...</td></tr>';
    
    try {
        const response = await fetch(`${API_URL}/reseller-applications?status=${status}`);
        if (!response.ok) throw new Error('Failed to load applications');
        
        allApplications = await response.json();
        renderApplicationsTable(allApplications);
        updateApplicationCounts();
        
    } catch (error) {
        console.error('Error loading applications:', error);
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: #f87171;">เกิดข้อผิดพลาดในการโหลดข้อมูล</td></tr>';
    }
}

async function updateApplicationCounts() {
    try {
        const [pending, approved, rejected] = await Promise.all([
            fetch(`${API_URL}/reseller-applications?status=pending`).then(r => r.json()),
            fetch(`${API_URL}/reseller-applications?status=approved`).then(r => r.json()),
            fetch(`${API_URL}/reseller-applications?status=rejected`).then(r => r.json())
        ]);
        
        const pendingCount = document.getElementById('app-count-pending');
        const approvedCount = document.getElementById('app-count-approved');
        const rejectedCount = document.getElementById('app-count-rejected');
        
        if (pendingCount) pendingCount.textContent = pending.length;
        if (approvedCount) approvedCount.textContent = approved.length;
        if (rejectedCount) rejectedCount.textContent = rejected.length;
        
    } catch (error) {
        console.error('Error updating application counts:', error);
    }
}

function renderApplicationsTable(applications) {
    const tbody = document.getElementById('applicationsTableBody');
    if (!tbody) return;
    
    if (applications.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: rgba(255,255,255,0.6);">ไม่มีข้อมูล</td></tr>';
        return;
    }
    
    tbody.innerHTML = applications.map(app => {
        const statusBadge = getApplicationStatusBadge(app.status);
        const createdAt = new Date(app.created_at).toLocaleDateString('th-TH', {
            year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        
        return `
            <tr>
                <td>${escapeHtml(app.full_name)}</td>
                <td>${escapeHtml(app.username)}</td>
                <td>${escapeHtml(app.email)}</td>
                <td>${escapeHtml(app.phone)}</td>
                <td>${escapeHtml(app.line_id || '-')}</td>
                <td>${escapeHtml(app.province)}</td>
                <td>${statusBadge}</td>
                <td>${createdAt}</td>
                <td>
                    <button class="btn btn-sm btn-info" onclick="viewApplicationDetail(${app.id})" title="ดูรายละเอียด">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M20.188 10.9C20.707 11.486 21 12 21 12s-4.03 7-9 7c-.658 0-1.292-.1-1.896-.275M3.812 10.9C3.293 11.486 3 12 3 12s4.03 7 9 7c.658 0 1.292-.1 1.896-.275M3 3l18 18"/></svg>
                    </button>
                    ${app.status === 'pending' ? `
                        <button class="btn btn-sm btn-success" onclick="approveApplication(${app.id})" title="อนุมัติ">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="openRejectModal(${app.id})" title="ปฏิเสธ">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;
    }).join('');
}

function getApplicationStatusBadge(status) {
    const statusMap = {
        'pending': { text: 'รออนุมัติ', class: 'badge-warning' },
        'approved': { text: 'อนุมัติแล้ว', class: 'badge-success' },
        'rejected': { text: 'ปฏิเสธ', class: 'badge-danger' }
    };
    const s = statusMap[status] || { text: status, class: 'badge-secondary' };
    return `<span class="status-badge ${s.class}">${s.text}</span>`;
}

function filterApplications(status) {
    currentApplicationStatus = status;
    
    document.querySelectorAll('#page-applications .status-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.status === status);
    });
    
    loadApplications(status);
}

async function viewApplicationDetail(id) {
    currentApplicationId = id;
    
    try {
        const response = await fetch(`${API_URL}/reseller-applications/${id}`);
        if (!response.ok) throw new Error('Failed to load application');
        
        const app = await response.json();
        
        const body = document.getElementById('applicationDetailBody');
        const actions = document.getElementById('applicationActions');
        
        const createdAt = new Date(app.created_at).toLocaleDateString('th-TH', {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        
        body.innerHTML = `
            <div style="display: grid; gap: 12px;">
                <div class="detail-row">
                    <span class="detail-label">ชื่อ-นามสกุล:</span>
                    <span class="detail-value">${escapeHtml(app.full_name)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Username:</span>
                    <span class="detail-value">${escapeHtml(app.username)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Email:</span>
                    <span class="detail-value">${escapeHtml(app.email)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">เบอร์โทร:</span>
                    <span class="detail-value">${escapeHtml(app.phone)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Line ID:</span>
                    <span class="detail-value">${escapeHtml(app.line_id || '-')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">ที่อยู่:</span>
                    <span class="detail-value">${escapeHtml(app.address || '-')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">ตำบล/อำเภอ/จังหวัด:</span>
                    <span class="detail-value">${escapeHtml(app.subdistrict || '')} ${escapeHtml(app.district || '')} ${escapeHtml(app.province || '')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">รหัสไปรษณีย์:</span>
                    <span class="detail-value">${escapeHtml(app.postal_code || '-')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">หมายเหตุ:</span>
                    <span class="detail-value">${escapeHtml(app.notes || '-')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">สถานะ:</span>
                    <span class="detail-value">${getApplicationStatusBadge(app.status)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">วันที่สมัคร:</span>
                    <span class="detail-value">${createdAt}</span>
                </div>
                ${app.status === 'rejected' && app.reject_reason ? `
                <div class="detail-row" style="background: rgba(248,113,113,0.1); padding: 10px; border-radius: 8px;">
                    <span class="detail-label">เหตุผลที่ปฏิเสธ:</span>
                    <span class="detail-value" style="color: #f87171;">${escapeHtml(app.reject_reason)}</span>
                </div>
                ` : ''}
            </div>
        `;
        
        if (app.status === 'pending') {
            actions.innerHTML = `
                <button class="btn btn-secondary" onclick="closeApplicationModal()">ปิด</button>
                <button class="btn btn-danger" onclick="openRejectModal(${app.id})">ปฏิเสธ</button>
                <button class="btn btn-success" onclick="approveApplication(${app.id})">อนุมัติ</button>
            `;
        } else {
            actions.innerHTML = `
                <button class="btn btn-secondary" onclick="closeApplicationModal()">ปิด</button>
            `;
        }
        
        document.getElementById('applicationDetailModal').style.display = 'flex';
        
    } catch (error) {
        console.error('Error loading application detail:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
    }
}

function closeApplicationModal() {
    document.getElementById('applicationDetailModal').style.display = 'none';
    currentApplicationId = null;
}

function openRejectModal(id) {
    currentApplicationId = id;
    document.getElementById('rejectReasonText').value = '';
    document.getElementById('rejectReasonModal').style.display = 'flex';
}

function closeRejectModal() {
    document.getElementById('rejectReasonModal').style.display = 'none';
    currentApplicationId = null;
}

async function approveApplication(id) {
    if (!confirm('ต้องการอนุมัติใบสมัครนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/reseller-applications/${id}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showGlobalAlert('อนุมัติใบสมัครสำเร็จ ระบบได้สร้างผู้ใช้และส่ง Email แจ้งผลแล้ว', 'success');
            closeApplicationModal();
            loadApplicationsPage();
            loadApplicationsCount();
        } else {
            const result = await response.json();
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error approving application:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการอนุมัติ', 'error');
    }
}

async function confirmReject() {
    const reason = document.getElementById('rejectReasonText').value.trim();
    
    try {
        const response = await fetch(`${API_URL}/reseller-applications/${currentApplicationId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
        });
        
        if (response.ok) {
            showGlobalAlert('ปฏิเสธใบสมัครสำเร็จ ระบบได้ส่ง Email แจ้งผลแล้ว', 'success');
            closeRejectModal();
            closeApplicationModal();
            loadApplicationsPage();
            loadApplicationsCount();
        } else {
            const result = await response.json();
            showGlobalAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error rejecting application:', error);
        showGlobalAlert('เกิดข้อผิดพลาดในการปฏิเสธ', 'error');
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
