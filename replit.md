# Admin User Management & Product Management System

## Overview
This full-stack reseller/distributor application, built with Flask and Neon PostgreSQL, is designed for Super Admins to manage users (Super Admin, Assistant Admin, Reseller) and their tiers, alongside comprehensive product management. Key capabilities include advanced SPU/SKU variant handling, multiple image uploads with drag-and-drop ordering, optional size charts, and dynamic pricing based on a 4-tier reseller system with configurable auto-upgrade logic. It features role-based access control, a robust order management system with configurable numbering, sales analytics, and a complete Made-to-Order (MTO) system with production tracking and payment verification. The system also includes an in-app chat for real-time communication between Admins and Resellers. The overarching goal is to provide a professional, secure business management solution with a modern UI and real-time API integration.

## Authentication System (Google OAuth)
- **All users login via Google OAuth** (`/auth/google` → `/auth/google/callback`)
- **Admin (Super Admin / Assistant Admin)**: Login with Google — email must exist in DB first. Super Admin creates Admin accounts manually.
- **Reseller**: Login with Google — if email not in DB, auto-creates account and logs in immediately (auto-approve, no manual approval needed)
- **Fallback**: Username/Password form available for Admins only (hidden behind toggle on login page)
- **Note**: Manual registration/approval system (`reseller_applications` table, `/api/register`, `/api/reseller-applications/*`) has been removed — all reseller registration is now via Google OAuth auto-approve
- **Routes**: `GET /auth/google`, `GET /auth/google/callback`
- **Dependencies**: `authlib`, `werkzeug.middleware.proxy_fix.ProxyFix` (for HTTPS URL generation behind Gunicorn)

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
The system features a modern, responsive glassmorphism design with frosted glass effects, animated gradient backgrounds, and smooth transitions, adhering to a consistent purple-to-pink gradient color scheme. It uses the Inter font, compact sizing for data, and modern line-style SVG icons. The multi-page dashboard includes a collapsible sidebar. Product management UI is inspired by e-commerce platforms, offering compact font sizes, status tabs, an advanced filter bar, bulk actions, toggle switches, collapsible SKU variants, and inline editing. A global alert system provides consistent user feedback. Both Admin and Reseller interfaces are structured as Single Page Applications (SPAs) using hash-based navigation.

### Technical Implementations
The backend is a Flask 3.1.2 application, utilizing Flask-CORS and a Neon PostgreSQL database. It employs a custom session-based authentication system with bcrypt for password hashing and role-based access control, ensuring all admin routes are protected with input validation. The frontend uses Jinja2 templates, vanilla JavaScript, CSS Grid for responsiveness, and asynchronous Fetch API requests. Product updates use a diff-based approach to maintain SKU ID integrity. The system also includes a comprehensive warehouse management system with stock transfers, adjustments, and an audit log, as well as an order shipment system with automatic splitting and label printing.

### Feature Specifications
- **User & Role Management:** Super Admin, Assistant Admin, Reseller roles; 4-tier reseller system with auto-upgrade logic and manual override; role-based brand access. `total_purchases` is incremented only when order status changes to `delivered` (not at payment approval); uses `AND status != 'delivered'` + `cursor.rowcount > 0` guard across all 3 delivery paths (admin mark-delivered, shipment tracking, iShip webhook) to prevent double-counting. `cancel_order` deducts only if order `was_delivered`.
- **Marketing Module:** Admin CRUD for promotions (auto-applied, tier/brand/category conditions, stackable flag) and coupons (assign to users, min spend, max discount, expiry, usage limits). Coupons now support **applies_to** scope: `all` / `brand` (select specific brands) / `product` (select specific products) — stored as `applies_to` + `applies_to_ids INTEGER[]` on `coupons` table; validated at checkout and preview; displayed on coupon cards with brand/product names. Admin UI redesigned: Apple+Google style stat cards (large numbers), promo card grid (2-col desktop/1-col mobile), coupon ticket cards (colored left panel + code), FAB floating action button, modal bottom sheet on mobile. Reseller UI: coupon input at checkout with preview-discount API, coupon wallet picker modal (bottom sheet), coupon wallet section in Profile page, **dedicated "โปรโมชัน" tab (6th tab in bottom nav)** with `page-promo-wallet` showing active auto-promotions + coupon ticket cards with "ใช้เลย" button. Bottom nav resized to 20px icons / 10px text for 6-tab fit. Layer system: Tier pricing → Best auto-promotion → Coupon (if stackable or no promo). `create_order` applies coupon+promotion and marks coupon as used.
- **Product Management (SPU/SKU):** Full CRUD for products, brands, and categories; dynamic options/attributes; auto-generation of SKU variants; multi-image upload with drag-and-drop; low stock indicators; product status management; shipping fields. Made-to-Order (MTO) system with production days, minimum order quantity, deposit settings, custom product creation, and a 4-page management workflow (Quotation Requests, Quotations, MTO Orders, Payment Verification) with timeline tracking.
- **Order & Sales Management:** Configurable order numbering; sales statistics, 7-day sales charts, recent orders, top-selling products; sales history with filters; brand sales analytics. Shipping update page (`/admin#shipping-update`) lists all in-transit orders with "จัดส่งสำเร็จ" and "สินค้าตีกลับ" (with reason) buttons — both trigger `send_order_status_chat()` automatically. Admin can cancel shipped orders (stock NOT auto-restored); triggers refund flow with bank info, PromptPay QR, and slip upload.
- **Quick Order (ขายด่วน) — Enhanced:** `orders` table has `is_quick_order BOOLEAN` + `platform VARCHAR(30)` columns. Quick orders created via `POST /api/admin/quick-order` with optional `platform` (shopee/lazada/tiktok/line/facebook/onsale/other) and `tracking_number` — if tracking provided, shipment is immediately set to 'shipped'. Orders page has mode toggle: "ออเดอร์ตัวแทน" vs "⚡ ขายด่วน". Quick Orders tab shows platform badge (colored), tracking link (Lazada → external track URL), status tabs (paid/shipped/delivered/returned/stock_restored), action buttons per status. Status update via `POST /api/admin/quick-orders/<id>/status`; stock restoration via `POST /api/admin/quick-orders/<id>/restore-stock` (restores to original warehouses). iShip webhook: `returned` status now updates order+shipment status to 'returned' (previously only sent chat). Regular orders API excludes quick orders (`is_quick_order = FALSE`).
- **Refund System:** `order_refunds` table stores refund records. Endpoints: `GET /api/admin/orders/<id>/refund-info` (calculates refund = final_amount − shipping_fee), `POST /api/admin/orders/<id>/refund` (saves slip + notifies chat), `GET /api/admin/orders/<id>/refund-qr` (PromptPay QR using reseller's promptpay_number). Reseller profile stores: `bank_name`, `bank_account_number`, `bank_account_name`, `promptpay_number`.
- **Warehouse & Stock Management:** Full CRUD for warehouses; multi-warehouse stock tracking per SKU; stock transfer system with audit logging; stock adjustment system for various reasons and channels; comprehensive stock audit log.
- **Reseller Features:** Dedicated dashboard; tier-specific pricing; customer database management for direct shipping; profile management for shipping info and branding.
- **Communication:** In-app chat system between Admin and Resellers with real-time messaging, broadcast capabilities, quick reply templates, file attachments, product attachment with tier pricing, unread badges, and smart email notifications.
- **PWA & Push Notifications:** Progressive Web App with installable app icon, Service Worker for caching, Web Push Notifications (VAPID-based) for real-time alerts on chat messages, new orders, and broadcasts. Push subscription management via `/api/push/*` endpoints.
- **Security:** `bcrypt` for passwords, strong `SESSION_SECRET`, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask (lightweight, flexible).
- **Database:** Neon PostgreSQL (reliability, scalability, Replit integration).
- **Authentication:** Custom session-based for granular control.
- **Frontend:** Vanilla JavaScript (performance, no framework overhead), CSS Grid (responsive layout), Fetch API for RESTful interaction.
- **Deployment:** Gunicorn production server with `gevent` async workers (`--worker-class gevent --workers 2 --worker-connections 1000`). Gevent prevents worker timeouts caused by browser idle keep-alive connections blocking sync workers.

## Active Integrations

### iShip (ตัวกลางการขนส่ง) - ✅ Implemented (Phase 1: Webhook)
- **Purpose:** Receive shipping status updates via webhook from iShip logistics aggregator
- **Webhook Endpoint:** `POST /api/webhook/iship` (no auth decorator — public but key-verified)
- **Auth:** Header `X-API-Key: <ISHIP_API_KEY>` or `Authorization: Bearer <ISHIP_API_KEY>`
- **Secret:** `ISHIP_API_KEY` (stored in Replit Secrets)
- **Payload Fields:** `tracking` (tracking number), `status` (shipped/in_transit/pickup/delivered/returned/exception/failed), `status_desc` (description)
- **Status Mapping:**
  - `delivered` → shipment status=delivered, all-delivered check → order status=delivered, chat notification
  - `shipped/in_transit/pickup` → shipment status=shipped, order status=shipped (if not already), chat notification
  - `returned/exception/failed` → chat notification with shipping_issue (no status change)
- **iShip Dashboard Config:** Set Webhook URL to `https://[production-domain]/api/webhook/iship`
- **Phase 2 (Pending):** Outbound API — create_order, check-price, printLabel via iShip API

## External Dependencies

### Python Packages
- **flask**: Web framework.
- **flask-cors**: CORS support.
- **psycopg2-binary**: PostgreSQL adapter.
- **python-dotenv**: Environment variable management.
- **bcrypt**: Password hashing.
- **gunicorn**: Production WSGI server.
- **pywebpush**: Web Push notification sending.
- **py-vapid**: VAPID key management for Web Push.

### Database Service
- **Replit PostgreSQL (Neon-backed)**: Auto-provisioned, accessed via `DATABASE_URL`.

### Frontend Libraries
- **Vanilla JavaScript**: For client-side logic.
- **CSS Grid**: For responsive layouts.
- **Fetch API**: For HTTP requests.
- **SortableJS (1.15.0)**: Drag-and-drop functionality.
- **Cropper.js**: Image cropping.
- **Chart.js**: For sales charts.