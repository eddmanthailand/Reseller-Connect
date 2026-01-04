# Admin User Management & Product Management System

## Overview
This full-stack reseller/distributor application, built with Flask and Neon PostgreSQL, empowers Super Admins to manage users (Super Admin, Assistant Admin, Reseller) and their respective tiers, alongside comprehensive product management. Key capabilities include advanced SPU/SKU variant handling, multiple image uploads with drag-and-drop ordering, and optional size charts. It features a modern glassmorphism UI, real-time API integration, and aims to provide a professional, secure business management solution. The system supports dynamic pricing based on a 4-tier reseller system with configurable auto-upgrade logic, role-based access control for Assistant Admins, and a robust order management system with configurable order numbering and sales analytics.

## User Preferences
- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling
- **Font Color Rules:** 
  - ห้ามใช้ตัวอักษรสีม่วง (#a855f7, #8b5cf6) หรือสีฟ้า (#3b82f6) บนพื้นหลังสีเดียวกัน
  - ห้ามใช้ตัวอักษรสีที่กลืนกับพื้นหลัง gradient ม่วง-ชมพู
  - ให้ใช้สีขาว (#ffffff) หรือสีอ่อน (rgba(255,255,255,0.9)) สำหรับข้อความหลักเพื่อให้อ่านชัดเจน
  - ถ้าพบข้อความที่อ่านยากให้เปลี่ยนเป็นสีขาวทันที

## System Architecture

### UI/UX Decisions
The system employs a modern, responsive glassmorphism design featuring frosted glass effects, animated gradient backgrounds, smooth transitions, and a consistent purple-to-pink gradient color scheme. It utilizes the Inter font family with compact sizing for dense data displays and modern line-style SVG icons. The multi-page dashboard includes a collapsible sidebar (state persisted in localStorage). The product management UI is inspired by Lazada, offering compact font sizes, status tabs with live counts, an advanced filter bar, bulk action toolbar, toggle switches for status changes, collapsible SKU variants, and inline editing for SKU price and stock. A global alert system ensures consistent user feedback.

### Technical Implementations
The backend is a Flask 3.1.2 application with Flask-CORS, utilizing a Neon PostgreSQL database. It features a custom session-based authentication system with bcrypt for password hashing and role-based access control. All admin routes are protected with input validation on API endpoints. The frontend uses Jinja2 templates, vanilla JavaScript, and CSS Grid for responsiveness, making asynchronous Fetch API requests. The product update logic uses a diff-based approach to preserve SKU IDs and maintain referential integrity.

### Feature Specifications
- **Authentication:** Custom session management, bcrypt hashing, role-based access control.
- **Admin Dashboard:** Multi-page layout, real-time statistics, user management (CRUD, role assignment, tier assignment), product management, settings.
- **Reseller Dashboard:** Dedicated view showing user info, tier level, and products with tier-specific pricing.
- **User Management:** Create/edit/delete users, assign roles (Super Admin, Assistant Admin, Reseller), assign reseller tiers with manual override. Role-based brand access control for Assistant Admins.
- **Brand Management:** Full CRUD for brands, required for products. Assistant Admins see only assigned brands.
- **Product Management (SPU/SKU System):**
    - Create products with SPU and brand.
    - Dynamic options/attributes with drag-and-drop ordering (SortableJS).
    - Auto-generation of SKU variants.
    - Bulk actions for master price/stock.
    - Multi-image upload with drag-and-drop reordering, optional size chart.
    - Diff-based product update logic protecting SKU IDs.
    - Low stock indicators and filters (out-of-stock, low stock).
    - Product status system (active, inactive, draft) with PATCH endpoint.
    - Product shipping fields (weight, dimensions) and `cost_price` for SKUs.
- **Category System:** Full CRUD for categories, normalized database structure.
- **Product Customization Options:** Non-SKU variations with optional pricing, managed via dedicated tables and APIs.
- **4-Tier Reseller Pricing System:** Bronze, Silver, Gold, Platinum tiers with `product_tier_pricing` for product-specific discounts.
- **Tier Settings & Auto-Upgrade System:** Configurable upgrade thresholds, `total_purchases` tracking, automatic tier upgrades (unless manually overridden). Batch check for upgrades.
- **Order Number Settings:** Configurable order number format (prefix, digit count, monthly reset).
- **Dashboard Home Page:** Sales statistics widgets (today, month, pending, low stock), 7-day sales chart (Chart.js), recent orders, top-selling products.
- **Sales History & Brand Sales Analytics:** Sales history table with advanced filters (date range, channel, status, keyword), summary stats. Brand sales grid with revenue, items, orders per brand.
- **Customer Database (Reseller):** Resellers can manage their own customer database for direct shipping with reseller branding. Full CRUD for customers with shipping info (name, phone, email, address, province, district, subdistrict, postal_code).
- **Reseller Profile Management:** Resellers can edit their shipping information and brand name for label printing.
- **Warehouse Management:** Full CRUD for warehouses (name, address, contact info). Multi-warehouse stock tracking per SKU via `sku_warehouse_stock` table.
- **Stock Transfer System:** Move stock between warehouses with automatic audit logging. API validates source stock availability before transfer.
- **Stock Adjustment System:** Adjust stock for external sales channels (Shopee, Lazada, TikTok, Facebook, LINE, offline stores) and other reasons (damaged, lost, expired, miscount, stock-in, returns). All adjustments automatically update total SKU stock and create audit log entries.
- **Stock Audit Log:** Complete history of all stock changes with before/after quantities, change type, reference to source transaction, user who made the change, and timestamps. Supports filtering by date, warehouse, change type.
- **Order Shipment System:** Automatic shipment splitting by warehouse during order creation. Each shipment tracks warehouse source, tracking number, shipping provider, and status (pending/shipped/delivered).
- **Security:** `bcrypt` for passwords, strong `SESSION_SECRET`, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask (lightweight, flexible).
- **Database:** Neon PostgreSQL (reliability, scalability, Replit integration).
- **Authentication:** Custom session-based for granular control.
- **Frontend:** Vanilla JavaScript (performance, no framework overhead), CSS Grid (responsive layout), Fetch API.
- **Deployment:** Gunicorn production server.
- **API Design:** RESTful.
- **SPA Conversion:** Both Admin and Reseller interfaces converted to Single Page Applications using hash-based navigation (`admin_dashboard.html` and `reseller_spa.html`).

### Database Schema
- **User Management:** `roles`, `reseller_tiers` (with `level_rank`, `upgrade_threshold`, `description`, `is_manual_only`), `users` (with `tier_manual_override`, `total_purchases`, `phone`, `email`, `address`, `province`, `district`, `subdistrict`, `postal_code`, `brand_name`, `logo_url`).
- **Brand Management:** `brands`, `admin_brand_access`.
- **Product Management:** `products` (with `brand_id`, `size_chart_image_url`, `status`, `weight`, `length`, `width`, `height`, `low_stock_threshold`), `product_images`, `options`, `option_values`, `skus` (with `cost_price`), `sku_values_map`.
- **Category Management:** `categories`, `product_categories`.
- **Product Customizations:** `product_customizations`, `customization_choices`.
- **Tier Pricing:** `product_tier_pricing`.
- **Order Settings:** `order_number_settings`.
- **Reseller Customer Database:** `reseller_customers` (with `reseller_id`, `full_name`, `phone`, `email`, `address`, `province`, `district`, `subdistrict`, `postal_code`, `notes`).
- **Warehouse System:** `warehouses` (id, name, address, province, district, subdistrict, postal_code, phone, contact_name, is_active), `sku_warehouse_stock` (sku_id, warehouse_id, stock), `order_shipments` (order_id, warehouse_id, tracking_number, shipping_provider, status, shipped_at, delivered_at), `order_shipment_items` (shipment_id, order_item_id, quantity).
- **Stock Management:** `stock_transfers` (id, sku_id, from_warehouse_id, to_warehouse_id, quantity, notes, created_at, created_by), `stock_adjustments` (id, sku_id, warehouse_id, quantity_change, adjustment_type, sales_channel, notes, created_at, created_by), `stock_audit_log` (id, sku_id, warehouse_id, quantity_before, quantity_after, change_type, reference_id, reference_type, notes, created_at, created_by).

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
- **SortableJS (1.15.0)**: Drag-and-drop functionality.
- **Cropper.js**: Image cropping.
- **Chart.js**: For sales charts.