// API Base URL
const API_URL = '/api';

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
