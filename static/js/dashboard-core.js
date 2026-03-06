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
