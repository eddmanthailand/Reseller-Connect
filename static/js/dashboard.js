// API Base URL (use window.API_URL set by template, fallback to '/api')
const API_URL = window.API_URL || '/api';

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
        await loadCurrentUser();
        await Promise.all([
            loadRoles(),
            loadResellerTiers(),
            loadUsers()
        ]);
        setupEventListeners();
        updateStats();
    } catch (error) {
        console.error('Initialization error:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
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
    if (!confirm('คุณต้องการออกจากระบบหรือไม่?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/logout`, {
            method: 'POST'
        });
        
        if (response.ok) {
            window.location.href = '/login';
        } else {
            throw new Error('Logout failed');
        }
    } catch (error) {
        console.error('Logout error:', error);
        alert('เกิดข้อผิดพลาดในการออกจากระบบ');
    }
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

// Render users in table
function renderUsers() {
    if (!userTableBody) return;

    userTableBody.innerHTML = '';
    
    if (users.length === 0) {
        userTableBody.innerHTML = '<tr><td colspan="4" style="text-align: center;">ไม่มีข้อมูลผู้ใช้</td></tr>';
        if (userCount) userCount.textContent = '0';
        return;
    }

    users.forEach(user => {
        const row = document.createElement('tr');
        
        // Get role badge class
        let badgeClass = 'badge';
        if (user.role === 'Super Admin') badgeClass += ' badge-super-admin';
        else if (user.role === 'Assistant Admin') badgeClass += ' badge-assistant-admin';
        else if (user.role === 'Reseller') badgeClass += ' badge-reseller';
        
        row.innerHTML = `
            <td>${user.full_name}</td>
            <td>${user.username}</td>
            <td>
                <span class="${badgeClass}">${user.role}</span>
                ${user.reseller_tier ? `<br><small style="color: #666;">Tier: ${user.reseller_tier}</small>` : ''}
            </td>
            <td>
                <button class="btn-edit" onclick="openEditUserModal(${user.id})" style="margin-right: 8px;">Edit</button>
                <button class="btn-delete" onclick="deleteUser(${user.id}, '${user.full_name}')">Delete</button>
            </td>
        `;
        
        userTableBody.appendChild(row);
    });

    // Update user count
    if (userCount) userCount.textContent = users.length;
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
            
            switchPage(targetPage);
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

    // Load products data when switching to products page
    if (pageName === 'products') {
        loadProducts();
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
        editTierSelect.innerHTML = '<option value="">-- เลือก Tier --</option>';
        resellerTiers.forEach(tier => {
            const option = document.createElement('option');
            option.value = tier.id;
            option.textContent = tier.name;
            if (tier.id === user.reseller_tier_id) option.selected = true;
            editTierSelect.appendChild(option);
        });
        
        if (user.role === 'Reseller') {
            editTierGroup.classList.remove('hidden');
        } else {
            editTierGroup.classList.add('hidden');
        }
        
        editRoleSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption.dataset.roleName === 'Reseller') {
                editTierGroup.classList.remove('hidden');
            } else {
                editTierGroup.classList.add('hidden');
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
    } else {
        userData.reseller_tier_id = null;
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

// Load products
async function loadProducts() {
    const productTableBody = document.getElementById('productTableBody');
    const productCountElement = document.getElementById('productCount');
    
    if (!productTableBody) return;

    try {
        const response = await fetch(`${API_URL}/products`);
        
        if (!response.ok) {
            throw new Error('Failed to load products');
        }

        const products = await response.json();
        
        // Update product count
        if (productCountElement) {
            productCountElement.textContent = products.length;
        }

        // Clear and populate table
        productTableBody.innerHTML = '';
        
        if (products.length === 0) {
            productTableBody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px;">
                        <div style="opacity: 0.6;">ยังไม่มีสินค้าในระบบ</div>
                        <div style="margin-top: 10px;">
                            <a href="/admin/products/create" style="color: rgba(255, 255, 255, 0.9);">สร้างสินค้าแรกของคุณ</a>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        products.forEach(product => {
            const row = document.createElement('tr');
            
            const createdDate = new Date(product.created_at);
            const formattedDate = createdDate.toLocaleDateString('th-TH', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });

            const imageHtml = product.first_image_url 
                ? `<img src="${product.first_image_url}" alt="${product.name}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 8px; border: 2px solid rgba(255, 255, 255, 0.2);">`
                : `<div style="width: 50px; height: 50px; background: rgba(255, 255, 255, 0.1); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px;">📦</div>`;
            
            const brandHtml = product.brand_name 
                ? `<span style="background: rgba(168, 85, 247, 0.2); padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 500;">${product.brand_name}</span>`
                : `<span style="opacity: 0.5; font-size: 12px;">ไม่ระบุ</span>`;
            
            const status = product.status || 'active';
            const statusConfig = {
                'active': { label: 'Active', color: '#4ade80', bg: 'rgba(40, 167, 69, 0.2)' },
                'inactive': { label: 'Inactive', color: '#9ca3af', bg: 'rgba(107, 114, 128, 0.2)' },
                'draft': { label: 'Draft', color: '#fcd34d', bg: 'rgba(253, 186, 20, 0.2)' }
            };
            const statusStyle = statusConfig[status] || statusConfig['active'];
            const statusBadge = `<span class="status-badge" style="background: ${statusStyle.bg}; color: ${statusStyle.color}; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; cursor: pointer;" onclick="cycleProductStatus(${product.id}, '${status}')">${statusStyle.label}</span>`;
            
            row.innerHTML = `
                <td>${imageHtml}</td>
                <td>${brandHtml}</td>
                <td><strong>${product.parent_sku || '-'}</strong></td>
                <td>${product.name || '-'}</td>
                <td>${statusBadge}</td>
                <td>
                    <span style="background: rgba(139, 92, 246, 0.2); padding: 4px 12px; border-radius: 12px; font-size: 13px;">
                        ${product.sku_count || 0} SKUs
                    </span>
                </td>
                <td>${formattedDate}</td>
                <td style="display: flex; gap: 8px;">
                    <a href="/admin/products/edit/${product.id}" 
                       class="btn-edit" 
                       style="background: rgba(59, 130, 246, 0.2); color: rgb(59, 130, 246); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                            <path d="m15 5 4 4"/>
                        </svg>
                        แก้ไข
                    </a>
                    <button onclick="deleteProduct(${product.id}, '${product.name}')" 
                            class="btn-delete" 
                            style="background: rgba(239, 68, 68, 0.2); color: rgb(239, 68, 68); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; gap: 4px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 6h18"/>
                            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
                            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                        </svg>
                        ลบ
                    </button>
                </td>
            `;
            
            productTableBody.appendChild(row);
        });
    } catch (error) {
        console.error('Error loading products:', error);
        productTableBody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; padding: 40px;">
                    <div style="color: rgb(239, 68, 68); opacity: 0.8;">เกิดข้อผิดพลาดในการโหลดข้อมูลสินค้า</div>
                </td>
            </tr>
        `;
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

// Show alert message
function showAlert(message, type) {
    if (!alertBox) return;

    alertBox.textContent = message;
    alertBox.className = `alert ${type} show`;

    setTimeout(() => {
        alertBox.classList.remove('show');
    }, 5000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
