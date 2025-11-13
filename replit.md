# Admin User Management & Product Management System

## Overview

This is a full-stack reseller/distributor application built with Flask and Neon PostgreSQL. The system allows Super Admins to manage users with various roles (Super Admin, Assistant Admin, Reseller), assign reseller tiers, and manage products with advanced SPU/SKU variant management. The system features a modern glassmorphism UI design with real-time API integration, aiming for a professional and secure business management solution.

## User Preferences

- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling

## System Architecture

### UI/UX Decisions
The system features a modern, responsive web interface with a focus on a glassmorphism design aesthetic. This includes frosted glass effects, animated gradient backgrounds, smooth transitions, hover effects, and a professional Inter font family. A multi-page dashboard with a professional sidebar navigation enhances user experience, providing clear organization for Home (statistics), Admin User Management, and Settings sections. The design maintains a consistent purple to pink gradient color scheme. Modern line-style SVG icons are used throughout the interface for a clean, professional appearance.

### Technical Implementations
The backend is built with Flask 3.1.2 and Flask-CORS, utilizing a Neon PostgreSQL database accessed via environment variables. It implements a custom session-based authentication system with bcrypt for password hashing and role-based access control using `@login_required` and `@admin_required` decorators. All admin routes are protected, and input validation is applied to API endpoints to prevent SQL injection. The frontend uses Jinja2 templates, vanilla JavaScript, and CSS Grid for a responsive layout, making asynchronous Fetch API requests for dynamic updates.

### Feature Specifications
- **Authentication:** Custom login, session management, bcrypt password hashing, role-based redirects.
- **Admin Dashboard:** Multi-page layout, sidebar navigation, real-time statistics (Total Users, Admin Count, Reseller Count, Silver Tier Count), full CRUD for user management, placeholder settings page.
- **Reseller Dashboard:** Dedicated dashboard for reseller users displaying user info and tier level.
- **User Management:** Create, view, delete users; assign roles (Super Admin, Assistant Admin, Reseller); assign reseller tiers; dynamic form validation.
- **Product Management (SPU/SKU System):** 
  - Create products with parent SKU (SPU)
  - Dynamic options/attributes system (color, size, material, etc.)
  - Drag-and-drop value ordering with SortableJS (not alphabetical)
  - Auto-generate SKU variants via Cartesian product
  - Bulk actions: Master Price and Master Stock to apply to all variants
  - View product list with SKU counts
  - Delete products with cascade deletion
- **Security:** bcrypt for passwords, strong `SESSION_SECRET` from environment variables, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask for its lightweight and flexible nature.
- **Database:** Neon PostgreSQL for reliability, scalability, and Replit integration.
- **Authentication:** Custom session-based system for granular control and security.
- **Frontend:** Vanilla JavaScript for performance and to avoid framework overhead.
- **Deployment:** Gunicorn production server with multiple workers for concurrency and stability.
- **API Design:** RESTful API endpoints for clear separation of concerns.

### Database Schema

**User Management:**
- **roles:** `id`, `name` (Super Admin, Assistant Admin, Reseller)
- **reseller_tiers:** `id`, `name` (Bronze, Silver)
- **users:** `id`, `full_name`, `username`, `password` (bcrypt hashed), `role_id` (FK to roles), `reseller_tier_id` (NULL FK to reseller_tiers), `created_at`

**Product Management (6-Table SPU/SKU Architecture):**
- **products:** `id`, `name`, `parent_sku` (UNIQUE), `description`, `created_at`, `updated_at` (SPU - parent product)
- **product_images:** `id`, `product_id` (FK to products), `image_url`, `sort_order`, `created_at` (product images with drag-and-drop ordering)
- **options:** `id`, `product_id` (FK to products), `name` (e.g., "Color", "Size"), `created_at` (product attributes)
- **option_values:** `id`, `option_id` (FK to options), `value` (e.g., "Red", "S", "M"), `sort_order` (for drag-and-drop ordering), `created_at`
- **skus:** `id`, `product_id` (FK to products), `sku_code` (UNIQUE), `price`, `stock`, `created_at`, `updated_at` (SKU variants)
- **sku_values_map:** `id`, `sku_id` (FK to skus), `option_value_id` (FK to option_values), `created_at` (Many-to-Many relationship)

## External Dependencies

### Python Packages
- **flask**: Web framework.
- **flask-cors**: CORS support for API.
- **psycopg2-binary**: PostgreSQL adapter.
- **python-dotenv**: Environment variable management.
- **bcrypt**: Password hashing.
- **gunicorn**: Production WSGI server.

### Database Service
- **Replit PostgreSQL (Neon-backed)**: Auto-provisioned, accessed via `DATABASE_URL`.

### Frontend
- **Vanilla JavaScript**: For client-side logic.
- **CSS Grid**: For responsive layouts.
- **Fetch API**: For HTTP requests to the backend.
- **SortableJS (1.15.0)**: For drag-and-drop functionality in product variant ordering.

## Recent Changes

### November 12, 2025 - Product Management Module (SPU/SKU System)
- **Database Architecture:** Added 5 new tables for advanced product management
  - `products` (SPU - parent products with `image_url` column for product images)
  - `options` (product attributes like color, size)
  - `option_values` (attribute values with sort_order for custom ordering)
  - `skus` (product variants)
  - `sku_values_map` (relationship mapping between SKUs and option values)
- **Backend API Endpoints:**
  - `GET /api/products` - List all products with SKU counts and images
  - `GET /api/products/<id>` - Get detailed product info with options and SKUs
  - `POST /api/products` - Create new product with options, values, SKUs, and image
  - `DELETE /api/products/<id>` - Delete product with cascade
  - `POST /api/products/upload-image` - Upload product image to Replit Object Storage
  - `GET /api/products/images/<filename>` - Serve product images
- **Frontend Implementation:**
  - Product Management page integrated into Admin Dashboard (SPA navigation)
  - Product List displayed within dashboard with live data loading
  - Product Creation page (`/admin/products/create`) - Full SPU/SKU creation workflow
  - JavaScript functions: `loadProducts()`, `deleteProduct()` in dashboard.js
- **Key Features Implemented:**
  - Dynamic options/attributes system (add unlimited options)
  - Drag-and-drop value reordering with SortableJS (preserves custom order via sort_order field)
  - Variant Matrix Generation via Cartesian Product algorithm
  - Bulk Actions: Master Price and Master Stock to update all variants at once
  - **Image Upload:** Full integration with Replit Object Storage
    - Upload product images (PNG, JPG, GIF, WebP)
    - Real-time image preview (200x200px) before form submission
    - Product list displays 50x50px rounded thumbnails
    - Placeholder icon (📦) when no image is uploaded
    - Secure file storage with unique filenames
  - Glassmorphism design matching existing system aesthetic
  - Modern SVG icons throughout
  - Single Page Application navigation for seamless UX
- **Routes Added:**
  - `/admin/products` - Product list page (standalone route)
  - `/admin/products/create` - Product creation page
  - Product list also accessible within Admin Dashboard via navigation menu
- **Navigation:** 
  - Added "Product Management" menu item to Admin Dashboard sidebar
  - SPA-style navigation using data-page="products" attribute
  - Auto-loads product data when switching to Products page
- **Cache Control:** Added HTTP headers to prevent browser caching issues
  - `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`
  - `Pragma: no-cache`
  - `Expires: 0`
- **JavaScript Architecture:** Fixed duplicate constant declarations
  - Unified API_URL management using `window.API_URL` pattern
  - dashboard.js reads from `window.API_URL || '/api'`
  - All templates properly initialize API_URL without conflicts
- **UI/UX Improvement (November 13, 2025):**
  - Changed Product Creation page to full-page layout (removed sidebar)
  - New sticky header with back button, page title, user info, and logout button
  - Increased max-width to 1400px for better data entry experience
  - Clean, spacious interface optimized for form filling

### November 13, 2025 - Multiple Product Image Upload with Drag-and-Drop Ordering
- **Database Migration:**
  - Migrated from single `image_url` column in products table to dedicated `product_images` table
  - New table supports unlimited images per product with `sort_order` field for custom ordering
  - Each product can now have multiple images with drag-and-drop reordering capability
- **Backend Enhancements:**
  - Updated `POST /api/upload-images` - Accept multiple files, return array of URLs
  - New `PUT /api/products/<id>/images/reorder` - Update image sort order
  - Modified all product CRUD endpoints to handle `image_urls` array instead of single image_url
  - Fixed database migration issues with duplicate sequence errors
- **Frontend Implementation:**
  - Multiple file input with `<input type="file" multiple>` in product creation form
  - Image gallery preview with real-time display (200x200px thumbnails)
  - Drag-and-drop reordering using SortableJS for intuitive image management
  - Visual feedback: hover effects, drag cursors, and sortable handles
  - Product list displays first image as 50x50px thumbnail
  - Automatic image upload on file selection with progress feedback
- **File Storage:**
  - Full integration with Replit Object Storage
  - Supports PNG, JPG, GIF, WebP formats
  - Unique filename generation to prevent conflicts
  - **IMPORTANT:** Requires manual Object Storage bucket creation via Replit UI
- **Key Features:**
  - Upload multiple images simultaneously
  - Drag-and-drop to reorder images in gallery
  - First image displayed as product thumbnail in list view
  - Seamless integration with existing SPU/SKU workflow