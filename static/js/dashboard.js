// API Base URL (use window.API_URL set by template, fallback to '/api')
const API_URL = (typeof window !== 'undefined' && window.API_URL) ? window.API_URL : '/api';

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
        
        await loadCurrentUser();
        await Promise.all([
            loadRoles(),
            loadResellerTiers(),
            loadUsers()
        ]);
        setupEventListeners();
        updateStats();
        
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
    const hash = window.location.hash.substring(1); // Remove the '#'
    if (hash) {
        const validPages = ['home', 'users', 'products', 'brands', 'categories', 'orders', 'tier-settings', 'settings'];
        if (validPages.includes(hash)) {
            switchPage(hash);
        }
    }
}

// Load current user info
async function loadCurrentUser() {
    try {
        const response = await fetch(`${API_URL}/me`);
        if (!response.ok) {
            throw new Error('Not authenticated');
        }
        const user = await response.json();
        const currentUserElement = document.getElementById('currentUser');
        if (currentUserElement) {
            currentUserElement.textContent = `${user.full_name} (${user.role})`;
        }
    } catch (error) {
        console.error('Error loading current user:', error);
        window.location.href = '/login';
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
    if (pageName === 'products') {
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
        
        if (user.role === 'Reseller') {
            editTierGroup.classList.remove('hidden');
            editManualOverrideGroup.classList.remove('hidden');
        } else {
            editTierGroup.classList.add('hidden');
            editManualOverrideGroup.classList.add('hidden');
        }
        
        editRoleSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption.dataset.roleName === 'Reseller') {
                editTierGroup.classList.remove('hidden');
                editManualOverrideGroup.classList.remove('hidden');
            } else {
                editTierGroup.classList.add('hidden');
                editManualOverrideGroup.classList.add('hidden');
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
                <button class="edit-stock-btn" onclick="openEditStockModal(${product.id})">
                    <span style="font-size: 11px;">${totalStock.toLocaleString()}</span>
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                </button>
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
            product.skus.forEach(sku => {
                const skuRow = document.createElement('tr');
                skuRow.className = 'sku-row';
                skuRow.dataset.parentId = product.id;
                
                skuRow.innerHTML = `
                    <td></td>
                    <td></td>
                    <td style="padding-left: 48px;">
                        <span class="sku-indicator">└</span>
                        <span style="font-size: 11px;">${sku.sku_code || '-'}</span>
                        <span style="font-size: 10px; opacity: 0.6; margin-left: 8px;">${sku.variant_name || ''}</span>
                    </td>
                    <td>
                        <div class="inline-edit">
                            <input type="text" class="inline-edit-input" value="${sku.price || 0}" 
                                   onblur="updateSkuPrice(${sku.id}, this.value)"
                                   onkeypress="if(event.key==='Enter') this.blur()">
                        </div>
                    </td>
                    <td>
                        <div class="inline-edit">
                            <input type="text" class="inline-edit-input" value="${sku.stock || 0}" 
                                   onblur="updateSkuStock(${sku.id}, this.value)"
                                   onkeypress="if(event.key==='Enter') this.blur()">
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

// Open Edit Stock Modal
function openEditStockModal(productId) {
    const product = allProducts.find(p => p.id === productId);
    if (!product) return;
    
    currentEditingProduct = product;
    const modal = document.getElementById('editStockModal');
    const skuList = document.getElementById('stockModalSkuList');
    
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
                            <label>สินค้าพร้อมส่ง</label>
                            <input type="number" class="modal-sku-input sku-stock-input" 
                                   data-sku-id="${sku.id}" 
                                   value="${sku.stock || 0}" 
                                   min="0" step="1">
                        </div>
                    </div>
                </div>
            `;
            skuList.innerHTML += itemHtml;
        });
    }
    
    // Setup search filter
    const searchInput = document.getElementById('stockModalSearch');
    searchInput.value = '';
    searchInput.oninput = () => filterModalSkus('stockModalSkuList', searchInput.value);
    
    modal.classList.add('active');
}

// Close Edit Stock Modal
function closeEditStockModal() {
    const modal = document.getElementById('editStockModal');
    modal.classList.remove('active');
    currentEditingProduct = null;
}

// Save all stock
async function saveAllStock() {
    const inputs = document.querySelectorAll('#stockModalSkuList .sku-stock-input');
    const updates = [];
    
    inputs.forEach(input => {
        const skuId = input.dataset.skuId;
        const stockVal = parseInt(input.value);
        const stock = isNaN(stockVal) || stockVal < 0 ? 0 : stockVal;
        updates.push({ skuId, stock });
    });
    
    if (updates.length === 0) {
        closeEditStockModal();
        return;
    }
    
    try {
        const results = await Promise.all(updates.map(async u => {
            const response = await fetch(`${API_URL}/skus/${u.skuId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stock: u.stock })
            });
            return response.ok;
        }));
        
        const failedCount = results.filter(r => !r).length;
        
        if (failedCount === 0) {
            showAlert('บันทึกสต็อกสำเร็จ', 'success');
        } else {
            showAlert(`บันทึกสำเร็จ ${results.length - failedCount}/${results.length} รายการ`, 'error');
        }
        
        closeEditStockModal();
        await loadProducts();
    } catch (error) {
        console.error('Error saving stock:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึกสต็อก', 'error');
    }
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
        let url = `${API_URL}/orders`;
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
        'paid': 'ชำระแล้ว',
        'rejected': 'ปฏิเสธ',
        'cancelled': 'ยกเลิก'
    };
    
    let html = `
        <table class="orders-table">
            <thead>
                <tr>
                    <th>เลขที่คำสั่งซื้อ</th>
                    <th>ลูกค้า</th>
                    <th>ยอดรวม</th>
                    <th>สถานะ</th>
                    <th>วันที่</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    allOrders.forEach(order => {
        const statusLabel = statusLabels[order.status] || order.status;
        const orderDate = new Date(order.created_at).toLocaleDateString('th-TH');
        
        html += `
            <tr>
                <td>#${order.id}</td>
                <td>${order.customer_name || 'N/A'}</td>
                <td>${parseFloat(order.total_amount || 0).toLocaleString('th-TH')} บาท</td>
                <td><span class="order-status ${order.status}">${statusLabel}</span></td>
                <td>${orderDate}</td>
                <td>
                    <button class="action-btn btn-review" onclick="viewOrderDetails(${order.id})">ดูรายละเอียด</button>
                </td>
            </tr>
        `;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

async function updateOrderCounts() {
    try {
        const response = await fetch(`${API_URL}/orders?status=under_review`);
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

async function viewOrderDetails(orderId) {
    try {
        const response = await fetch(`${API_URL}/orders/${orderId}`);
        const order = await response.json();
        
        const statusLabels = {
            'pending_payment': 'รอชำระเงิน',
            'under_review': 'รอตรวจสอบ',
            'paid': 'ชำระแล้ว',
            'rejected': 'ปฏิเสธ',
            'cancelled': 'ยกเลิก'
        };
        
        let itemsHtml = '';
        if (order.items && order.items.length > 0) {
            itemsHtml = order.items.map(item => `
                <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <span>${item.product_name || 'Product'} x${item.quantity}</span>
                    <span>${parseFloat(item.price * item.quantity).toLocaleString('th-TH')} บาท</span>
                </div>
            `).join('');
        }
        
        let slipHtml = '';
        if (order.payment_slip_url) {
            slipHtml = `
                <div style="margin-top: 16px;">
                    <h4 style="margin-bottom: 8px;">หลักฐานการชำระเงิน:</h4>
                    <img src="${order.payment_slip_url}" alt="Payment Slip" style="max-width: 100%; max-height: 300px; border-radius: 8px;">
                </div>
            `;
        }
        
        let actionsHtml = '';
        if (order.status === 'under_review') {
            actionsHtml = `
                <div style="display: flex; gap: 12px; margin-top: 20px;">
                    <button class="btn btn-success" onclick="updateOrderStatus(${orderId}, 'paid')" style="flex: 1;">
                        ยืนยันการชำระเงิน
                    </button>
                    <button class="btn btn-danger" onclick="updateOrderStatus(${orderId}, 'rejected')" style="flex: 1;">
                        ปฏิเสธ
                    </button>
                </div>
            `;
        }
        
        const modalContent = `
            <div style="padding: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2>คำสั่งซื้อ #${order.id}</h2>
                    <span class="order-status ${order.status}">${statusLabels[order.status]}</span>
                </div>
                <div style="margin-bottom: 16px;">
                    <p><strong>ลูกค้า:</strong> ${order.customer_name || 'N/A'}</p>
                    <p><strong>วันที่:</strong> ${new Date(order.created_at).toLocaleString('th-TH')}</p>
                </div>
                <h4 style="margin-bottom: 8px;">รายการสินค้า:</h4>
                <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px;">
                    ${itemsHtml || '<p style="opacity: 0.6;">ไม่มีรายการ</p>'}
                    <div style="display: flex; justify-content: space-between; padding-top: 12px; margin-top: 8px; border-top: 2px solid rgba(255,255,255,0.2); font-weight: bold;">
                        <span>ยอดรวม</span>
                        <span>${parseFloat(order.total_amount || 0).toLocaleString('th-TH')} บาท</span>
                    </div>
                </div>
                ${slipHtml}
                ${actionsHtml}
            </div>
        `;
        
        showModal(modalContent);
    } catch (error) {
        console.error('Error loading order details:', error);
        showAlert('ไม่สามารถโหลดรายละเอียดคำสั่งซื้อได้', 'error');
    }
}

async function updateOrderStatus(orderId, newStatus) {
    const confirmMessages = {
        'paid': 'ยืนยันการชำระเงินและหักสต็อก?',
        'rejected': 'ปฏิเสธคำสั่งซื้อนี้?'
    };
    
    if (!confirm(confirmMessages[newStatus] || `เปลี่ยนสถานะเป็น ${newStatus}?`)) return;
    
    try {
        const response = await fetch(`${API_URL}/orders/${orderId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (response.ok) {
            showAlert('อัปเดตสถานะสำเร็จ', 'success');
            closeModal();
            loadOrders(currentOrdersStatus);
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error updating order status:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
