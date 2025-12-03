# Admin User Management & Product Management System

## Recent Changes (December 2025)
- **Low Stock Indicators & Filters (Dec 2025):**
  - Visual badges on SKU rows: "หมด" (red) for out-of-stock, "ใกล้หมด" (yellow) for low stock
  - Product row shows aggregate stock warning badge with count of problematic SKUs
  - Stock filter dropdown in Products page: สต็อกทั้งหมด / สต็อกใกล้หมด / หมดสต็อก
  - API returns low_stock_count, out_of_stock_count, low_stock_threshold per product
  - CSS classes: .stock-badge-out, .stock-badge-low for color-coded indicators
- **Dashboard Home Page Improvements (Dec 2025):**
  - Added sales statistics widgets: ยอดขายวันนี้, ยอดขายเดือนนี้, รอดำเนินการ, สินค้าใกล้หมด
  - Sales chart showing 7-day trend using Chart.js
  - Recent orders list with status badges and time ago formatting
  - Top selling products of the month with ranking
  - New API endpoint: GET `/api/admin/dashboard-stats`
  - Hash-based navigation support for SPA (#products, #orders, etc.)
  - Removed old "ภาพรวมระบบ" and "ฟีเจอร์หลัก" sections
- **Product Shipping & Cost Fields (Dec 2025):**
  - Added weight (grams), length, width, height (cm) columns to products table for shipping calculation
  - Added cost_price column to skus table for profit margin calculation
  - Added low_stock_threshold column to products table for stock alerts
  - UI forms updated with "Shipping Info" section in product create/edit
  - API endpoints accept and return new fields
- **Product Update Logic - Diff-based Approach (Dec 2025):**
  - Changed from "delete all and recreate" to "diff-based update" strategy
  - SKU IDs are now preserved when editing products (maintains referential integrity with order_items)
  - Options and option values are updated in-place by name matching
  - SKUs with order references are protected: set stock=0 instead of deleting
  - Removed images are automatically deleted from Object Storage after successful DB commit
  - Product deletion now cleans up images from Object Storage
- **Global Alert System (Dec 2025):**
  - Consistent notification system across all pages using showGlobalAlert() and showConfirmAlert()
  - Logout confirmation dialog with success message
  - Script loading order fixed: global-alert.js loads before dashboard.js
- **Order Number Settings (Dec 2025):**
  - Configurable order number format: PREFIX-YYMM-XXXX (e.g., ORD-2512-0001)
  - Settings page UI for configuring prefix (1-10 chars) and digit count (3-6 digits)
  - Automatic sequence reset on new month
  - Real-time preview of next order number
  - Database table: `order_number_settings` with prefix, format_type, digit_count, current_sequence, current_period
  - API endpoints: GET/POST `/api/order-number-settings`
- **SPA Conversion**: Converted admin interface to Single Page Application (SPA) within admin_dashboard.html
  - Orders page integrated with status tabs and order detail modal
  - Tier Settings page with reseller list and upgrade checking
  - Settings page with PromptPay QR upload, Order Number settings, and sales channel management
  - Navigation uses data-page attributes for seamless page switching

## Overview
This is a full-stack reseller/distributor application built with Flask and Neon PostgreSQL. The system enables Super Admins to manage users with various roles (Super Admin, Assistant Admin, Reseller), assign reseller tiers, and manage products with advanced SPU/SKU variant management, including multiple images, drag-and-drop ordering, and optional size charts. It features a modern glassmorphism UI design with real-time API integration, aiming to provide a professional and secure business management solution.

## User Preferences
- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling

## System Architecture

### UI/UX Decisions
The system features a modern, responsive glassmorphism design with frosted glass effects, animated gradient backgrounds, smooth transitions, and a consistent purple to pink gradient color scheme. It uses the Inter font family with compact font sizing for dense data views, and modern line-style SVG icons. A multi-page dashboard with a collapsible sidebar (toggle via hamburger button, state persisted in localStorage) enhances user experience for sections like Home, Admin User Management, Product Management, and Settings.

**Lazada-Style Product Management UI (Dec 2025):**
- Compact font sizes for dense data display (CSS variables --font-xs to --font-3xl)
- Status tabs with live counts (All/Active/Inactive/Draft)
- Advanced filter bar (search by name/SKU, brand filter, category filter, sort options)
- Bulk actions toolbar (select multiple products → activate/deactivate/delete)
- Toggle switches for quick status changes
- Collapsible SKU variants (click SKU count badge to expand/collapse inline)
- Inline editing for SKU price and stock (direct in-table editing with validation)

### Technical Implementations
The backend is built with Flask 3.1.2 and Flask-CORS, using a Neon PostgreSQL database. It employs a custom session-based authentication system with bcrypt for password hashing and role-based access control. All admin routes are protected, and input validation is applied to API endpoints. The frontend uses Jinja2 templates, vanilla JavaScript, and CSS Grid for a responsive layout, making asynchronous Fetch API requests.

### Feature Specifications
- **Authentication:** Custom login, session management, bcrypt password hashing, role-based redirects.
- **Admin Dashboard:** Multi-page layout, sidebar navigation, real-time statistics, full CRUD for user management, placeholder settings page.
- **Reseller Dashboard:** Dedicated dashboard for reseller users displaying user info, tier level, and active products with prices. Role-gated API endpoints ensure security.
- **User Management:** Create, view, edit, delete users; assign roles (Super Admin, Assistant Admin, Reseller); assign reseller tiers; dynamic form validation; edit user modal with real-time validation.
- **Brand Management System:**
  - Full CRUD for brand management (Create, Read, Update, Delete).
  - Brands table with name and description fields.
  - Brand is a required field when creating/editing products (positioned at top of product form).
  - Role-based brand access control for Assistant Admins via `admin_brand_access` table.
  - Super Admin can see and manage all brands; Assistant Admin sees only assigned brands.
  - Brand assignment endpoint: `/api/users/{user_id}/brands`.
  - Submenu navigation under Product Management for brand management page.
- **Product Management (SPU/SKU System):**
  - Create products with parent SKU (SPU) and required brand selection.
  - Dynamic options/attributes system with drag-and-drop value ordering using SortableJS.
  - Auto-generate SKU variants via Cartesian product.
  - Bulk actions for Master Price and Master Stock application to all variants.
  - View product list with SKU counts and brand column.
  - Delete products with cascade deletion.
  - Multiple product image uploads with drag-and-drop reordering.
  - Optional size chart image upload with free aspect ratio cropping.
  - Client-side image preview and deferred upload pattern to prevent orphaned files.
  - **Edit Product (Full CRUD):** Load existing product data, populate form with brand/images/options/SKUs, update via PUT endpoint with proper data integrity (deletes old SKUs/options/images before reinsertion, uses options_map to prevent value collision).
  - Products filtered by brand access for Assistant Admin users.
- **Product Status System:**
  - Status column with values: active (default), inactive, draft.
  - PATCH endpoint for updating product status.
  - Clickable status badges in admin UI that cycle through states.
- **Category System:**
  - Normalized database tables: `categories`, `product_categories`.
  - Full CRUD API endpoints for category management.
  - Foreign-key constraints for data integrity.
- **Product Customization Options (Dec 2025):**
  - Non-SKU variations like button types, embroidery options that don't affect inventory.
  - Stored in `product_customizations` and `customization_choices` tables.
  - Each customization group has: name, is_required flag, allow_multiple flag.
  - Each choice has: name, optional extra_price for price adjustments.
  - Full CRUD API endpoints at `/api/products/:id/customizations`.
  - UI sections in product create/edit forms with dynamic JavaScript management.
  - Customizations saved after product creation/update.
- **4-Tier Reseller Pricing System (Dec 2025):**
  - Four reseller tiers: Bronze (level 1), Silver (level 2), Gold (level 3), Platinum (level 4).
  - Enhanced `reseller_tiers` table with `level_rank`, `upgrade_threshold`, `description`, `is_manual_only` columns.
  - `product_tier_pricing` table stores discount percentages per product/tier combination.
  - Products require discount percentages for all tiers before saving.
  - Tier pricing UI integrated into product create/edit forms with visual tier badges.
  - User management supports manual tier override for VIP customers via `tier_manual_override` column.
  - Reseller dashboard displays prices after tier discount with original price strikethrough and discount badge.
  - API endpoints: GET/POST `/api/products/:id/tier-pricing` for tier pricing CRUD.
- **Tier Settings & Auto-Upgrade System (Dec 2025):**
  - Dedicated tier settings page at `/admin/tier-settings` for configuring upgrade thresholds.
  - `total_purchases` column in users table tracks accumulated purchase amounts.
  - Configurable upgrade thresholds per tier (e.g., Bronze=0, Silver=10000, Gold=50000, Platinum=200000).
  - Automatic tier upgrade when reseller's total purchases reach threshold (unless manual override is set).
  - API endpoints: PUT `/api/reseller-tiers/:id` and `/api/reseller-tiers/bulk` for threshold management.
  - API endpoint: POST `/api/users/:id/add-purchase` to add purchase amount and trigger auto-upgrade check.
  - API endpoint: POST `/api/users/check-tier-upgrades` to batch check and upgrade all resellers.
  - API endpoint: GET `/api/resellers` to list all resellers with tier and purchase info.
  - Resellers table shows current tier, total purchases, and manual override status.
- **Security:** bcrypt for passwords, strong `SESSION_SECRET`, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask for its lightweight and flexibility.
- **Database:** Neon PostgreSQL for reliability, scalability, and Replit integration.
- **Authentication:** Custom session-based system for granular control and security.
- **Frontend:** Vanilla JavaScript for performance and to avoid framework overhead.
- **Deployment:** Gunicorn production server with multiple workers.
- **API Design:** RESTful API endpoints for clear separation of concerns.

### Database Schema
**User Management:** `roles`, `reseller_tiers` (with `level_rank`, `upgrade_threshold`, `description`, `is_manual_only`), `users` (with `tier_manual_override` column)
**Brand Management:** `brands`, `admin_brand_access` (for role-based brand access control)
**Product Management (6-Table SPU/SKU Architecture):** `products`, `product_images`, `options`, `option_values`, `skus`, `sku_values_map`. The `products` table includes `brand_id` (FK to brands), `size_chart_image_url`, `status` (active/inactive/draft), `weight`, `length`, `width`, `height`, `low_stock_threshold`. The `skus` table includes `cost_price` for profit calculation.
**Category Management:** `categories`, `product_categories` (junction table for product-category associations)
**Product Customizations:** `product_customizations`, `customization_choices` (for non-SKU product variations with optional pricing)
**Tier Pricing:** `product_tier_pricing` (stores discount_percent per product/tier combination)

## External Dependencies

### Python Packages
- **flask**: Web framework.
- **flask-cors**: CORS support.
- **psycopg2-binary**: PostgreSQL adapter.
- **python-dotenv**: Environment variable management.
- **bcrypt**: Password hashing.
- **gunicorn**: Production WSGI server.

### Database Service
- **Replit PostgreSQL (Neon-backed)**: Auto-provisioned, accessed via `DATABASE_URL`.

### Frontend
- **Vanilla JavaScript**: For client-side logic.
- **CSS Grid**: For responsive layouts.
- **Fetch API**: For HTTP requests.
- **SortableJS (1.15.0)**: For drag-and-drop functionality in product variant ordering and image reordering.
- **Cropper.js**: For image cropping functionality (lazy loaded).