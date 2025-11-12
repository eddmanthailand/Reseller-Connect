// API Base URL
const API_URL = '/api';

// Global data
let roles = [];
let resellerTiers = [];
let users = [];

// DOM Elements
const roleSelect = document.getElementById('role');
const resellerTierSelect = document.getElementById('resellerTier');
const resellerTierGroup = document.getElementById('resellerTierGroup');
const createUserForm = document.getElementById('createUserForm');
const userTableBody = document.getElementById('userTableBody');
const alertBox = document.getElementById('alertBox');
const userCount = document.getElementById('userCount');

// Initialize the application
async function init() {
    try {
        await Promise.all([
            loadRoles(),
            loadResellerTiers(),
            loadUsers()
        ]);
        setupEventListeners();
    } catch (error) {
        console.error('Initialization error:', error);
        showAlert('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
    }
}

// Load roles from API
async function loadRoles() {
    try {
        const response = await fetch(`${API_URL}/roles`);
        roles = await response.json();
        
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
        
        // Clear existing options
        resellerTierSelect.innerHTML = '<option value="">-- เลือก Tier --</option>';
        
        // Populate reseller tier dropdown
        resellerTiers.forEach(tier => {
            const option = document.createElement('option');
            option.value = tier.id;
            option.textContent = tier.name;
            resellerTierSelect.appendChild(option);
        });
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
        renderUserTable();
    } catch (error) {
        console.error('Error loading users:', error);
        userTableBody.innerHTML = '<tr><td colspan="4" class="loading">ไม่สามารถโหลดข้อมูลได้</td></tr>';
        throw error;
    }
}

// Render user table
function renderUserTable() {
    userTableBody.innerHTML = '';
    
    if (users.length === 0) {
        userTableBody.innerHTML = '<tr><td colspan="4" class="loading">ยังไม่มีผู้ใช้งานในระบบ</td></tr>';
        userCount.textContent = '0';
        return;
    }
    
    userCount.textContent = users.length;
    
    users.forEach(user => {
        const tr = document.createElement('tr');
        const roleBadgeClass = user.role.toLowerCase().replace(/\s+/g, '-');
        
        const roleDisplay = user.reseller_tier 
            ? `${user.role} (${user.reseller_tier})`
            : user.role;
        
        tr.innerHTML = `
            <td>${user.full_name}</td>
            <td>${user.username}</td>
            <td><span class="badge ${roleBadgeClass}">${roleDisplay}</span></td>
            <td>
                <button class="btn-delete" onclick="deleteUser(${user.id}, '${user.full_name}')">
                    Delete
                </button>
            </td>
        `;
        
        userTableBody.appendChild(tr);
    });
}

// Setup event listeners
function setupEventListeners() {
    // Show/Hide Reseller Tier based on selected role
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
    
    // Handle form submit
    createUserForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        await createUser();
    });
}

// Create new user
async function createUser() {
    const submitButton = createUserForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = 'กำลังสร้าง...';
    
    try {
        const formData = {
            full_name: document.getElementById('fullName').value,
            username: document.getElementById('username').value,
            password: document.getElementById('password').value,
            role_id: parseInt(document.getElementById('role').value)
        };
        
        // Add reseller tier if selected
        const resellerTierId = document.getElementById('resellerTier').value;
        if (resellerTierId) {
            formData.reseller_tier_id = parseInt(resellerTierId);
        }
        
        const response = await fetch(`${API_URL}/users`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'เกิดข้อผิดพลาดในการสร้างผู้ใช้');
        }
        
        // Show success message
        let message = `สร้างผู้ใช้ "${result.user.full_name}" สำเร็จ!`;
        if (result.user.reseller_tier) {
            message += ` (Tier: ${result.user.reseller_tier})`;
        }
        showAlert(message, 'success');
        
        // Reload users
        await loadUsers();
        
        // Reset form
        createUserForm.reset();
        resellerTierGroup.classList.add('hidden');
        resellerTierSelect.required = false;
        
    } catch (error) {
        console.error('Error creating user:', error);
        showAlert(error.message, 'error');
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = 'Create User';
    }
}

// Delete user
async function deleteUser(userId, userName) {
    if (!confirm(`คุณต้องการลบผู้ใช้ "${userName}" หรือไม่?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/users/${userId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'เกิดข้อผิดพลาดในการลบผู้ใช้');
        }
        
        showAlert(`ลบผู้ใช้ "${userName}" สำเร็จ!`, 'success');
        
        // Reload users
        await loadUsers();
        
    } catch (error) {
        console.error('Error deleting user:', error);
        showAlert(error.message, 'error');
    }
}

// Show alert message
function showAlert(message, type = 'success') {
    alertBox.textContent = message;
    alertBox.className = `alert ${type}`;
    alertBox.style.display = 'block';
    
    setTimeout(() => {
        alertBox.style.display = 'none';
    }, 5000);
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
