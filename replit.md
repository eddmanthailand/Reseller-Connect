# Admin User Management & Product Management System

## Overview
This full-stack reseller/distributor application, built with Flask and Neon PostgreSQL, is designed for Super Admins to manage users (Super Admin, Assistant Admin, Reseller) and their tiers, alongside comprehensive product management. Key capabilities include advanced SPU/SKU variant handling, multiple image uploads, optional size charts, and dynamic pricing based on a 4-tier reseller system with configurable auto-upgrade logic. It features role-based access control, a robust order management system with configurable numbering, sales analytics, and a complete Made-to-Order (MTO) system with production tracking and payment verification. The system also includes an in-app chat for real-time communication between Admins and Resellers. The overarching goal is to provide a professional, secure business management solution with a modern UI and real-time API integration, aiming for market leadership in reseller management platforms.

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
The system features a modern, responsive glassmorphism design with frosted glass effects, animated gradient backgrounds, and smooth transitions, adhering to a consistent purple-to-pink gradient color scheme. It uses the Inter font, compact sizing for data, and modern line-style SVG icons. The multi-page dashboard includes a collapsible sidebar. Product management UI offers compact font sizes, status tabs, an advanced filter bar, bulk actions, toggle switches, collapsible SKU variants, and inline editing. A global alert system provides consistent user feedback. Both Admin and Reseller interfaces are structured as Single Page Applications (SPAs) using hash-based navigation.

### Technical Implementations
The backend is a Flask 3.1.2 application, utilizing Flask-CORS and a Neon PostgreSQL database. It employs a custom session-based authentication system with bcrypt for password hashing and role-based access control, ensuring all admin routes are protected with input validation. The frontend uses Jinja2 templates, vanilla JavaScript, CSS Grid for responsiveness, and asynchronous Fetch API requests. Product updates use a diff-based approach to maintain SKU ID integrity. The system also includes a comprehensive warehouse management system with stock transfers, adjustments, and an audit log, as well as an order shipment system with automatic splitting and label printing. Stock race condition protection is implemented using `SELECT ... FOR UPDATE OF sws` and conditional updates to prevent overselling. An APScheduler task automatically cancels expired `pending_payment` orders, restores stock, and notifies resellers.

### Feature Specifications
- **User & Role Management:** Super Admin, Assistant Admin, Reseller roles; 4-tier reseller system with auto-upgrade logic and manual override; role-based brand access.
- **Product Management (SPU/SKU):** Full CRUD for products, brands, and categories; dynamic options/attributes; auto-generation of SKU variants; multi-image upload; low stock indicators; product status management; shipping fields. Made-to-Order (MTO) system with production days, MOQ, deposit settings, and a 4-page management workflow.
- **Order & Sales Management:** Configurable order numbering; sales statistics, 7-day sales charts, recent orders, top-selling products; sales history with filters; brand sales analytics. Shipping update page for in-transit orders with status changes and chat notifications. Quick order functionality includes "📷 อ่านใบปะหน้าอัตโนมัติ" (label OCR) via Gemini Vision to auto-fill order details and real-time phone lookup.
- **Stripe Online Payment:** Resellers can pay via card (Stripe Checkout) as alternative to PromptPay slip upload. On successful payment, order is auto-approved to `preparing` status via Stripe webhook. Stripe credentials fetched from Replit Connectors API. Routes in `routes/stripe_payment.py`.
- **Refund System:** Dedicated table and APIs for refund information, slip upload, chat notification, and PromptPay QR generation.
- **Warehouse & Stock Management:** Full CRUD for warehouses; multi-warehouse stock tracking; stock transfer and adjustment systems with audit logging.
- **Reseller Features:** Dedicated dashboard; tier-specific pricing; customer database management; profile management.
- **Communication:** In-app chat between Admin and Resellers with real-time messaging, broadcasts, templates, attachments, unread badges, and email notifications. An **Auto-Chat Bot** (`gemini-2.5-flash-lite`) automatically replies to resellers, offering keyword product search, brand/category/SKU context, Gemini Vision-based size chart reading, and alternative product suggestions.
- **PWA & Push Notifications:** Progressive Web App with installable icon, Service Worker for caching, and VAPID-based Web Push Notifications.
- **AI Agent:** In-app AI assistant (FAB) with READ tools (e.g., query_sales_today, query_low_stock, search_web, generate_image) and WRITE tools (e.g., adjust_stock, update_order_status, toggle_product, send_chat_message, toggle_facebook_ad) requiring Admin approval. Smart model routing uses `gemini-2.5-flash` for READ/chat and `gemini-3.1-pro-preview` for WRITE tools (2-phase verification). `search_web` uses Gemini Google Search grounding. `generate_image` uses Imagen 4.
- **Marketing Module:** Admin CRUD for promotions (auto-applied, stackable) and coupons (assign to users, usage limits, `applies_to` scope). Includes dedicated Admin and Reseller UIs for promotions and coupons.
- **Public Catalog Page:** `/catalog` for public product browsing with brand/category/featured filters.
- **Size Chart Groups:** Reusable size chart templates (`size_chart_groups` table) with dynamic columns/rows (JSONB). Admin can create templates, assign multiple products to a template, and the bot automatically includes the text-based size chart in prompts for both guest and member bots when size-related keywords are detected. Located at Admin → "ตารางขนาดสินค้า". API: `/api/admin/size-chart-groups` (CRUD) + `/api/admin/products-for-size-chart`. JS: `static/js/dashboard-size-charts.js`.

### System Design Choices
- **Backend Framework:** Flask (lightweight, flexible).
- **Database:** Neon PostgreSQL (reliability, scalability, Replit integration).
- **Authentication:** Custom session-based for granular control.
- **Frontend:** Vanilla JavaScript (performance, no framework overhead), CSS Grid (responsive layout), Fetch API for RESTful interaction.
- **Deployment:** Gunicorn production server with `gevent` async workers.

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
- **google-genai**: For Gemini Vision integration.
- **APScheduler**: For scheduled tasks (e.g., auto-canceling orders).

### Database Service
- **Replit PostgreSQL (Neon-backed)**: Accessed via `DATABASE_URL`.

### Frontend Libraries
- **Vanilla JavaScript**: For client-side logic.
- **CSS Grid**: For responsive layouts.
- **Fetch API**: For HTTP requests.
- **SortableJS**: Drag-and-drop functionality.
- **Cropper.js**: Image cropping.
- **Chart.js**: For sales charts.

### Payment System Roadmap (รอ API Keys จากผู้ใช้)
ผู้ใช้กำลังสมัครบริการต่อไปนี้ เมื่อได้รับ API Keys จะ implement พร้อมกัน:
- **Omise (Opn Payments)** — บัตรเครดิต/เดบิต (Public Key + Secret Key)
- **EasySlip API** — ตรวจสลิป PromptPay อัตโนมัติ (API Key)
- **iShip COD** — เก็บเงินปลายทาง (ถ้ามี key เพิ่มเติม)

แนวทาง implement:
- PromptPay/โอนเงิน: ใช้ระบบเดิม + เพิ่ม EasySlip verify อัตโนมัติ (fallback ให้ Admin ตรวจถ้า verify ล้มเหลว)
- บัตรเครดิต: เพิ่ม Omise ใน checkout flow (hosted payment form, tokenization)
- COD: เพิ่มผ่าน iShip API เป็นตัวเลือกที่ 3
- แยกเป็น module ภายใน: `routes/payment.py`, `routes/payment_omise.py`, `routes/payment_cod.py`
- ไม่แยกเป็น service แยก (ไม่จำเป็นสำหรับ scale ปัจจุบัน)

### AI Bot Known Fixes (app.py)
- **Guest bot `InFailedSqlTransaction` cascade**: Each `except Exception` in fetch functions (`_fetch_agent_settings`, `_fetch_training`, `_fetch_cats`, `_fetch_promos`, `_fetch_shipping`) now calls `conn.rollback()` to clear aborted transaction before the next fetch, preventing silent cascading failures.
- **Guest bot `_fetch_promos()` wrong SQL**: Fixed columns from non-existent `description`, `type` → correct `promo_type`, `start_date`; `promos_text` builder updated to match.
- **Cache poisoning**: All fetch functions return `None` (not `[]`/`{}`) on DB error; `_bot_cache_get` treats `None` as "retry always" (never stale-caches errors).
- **Member bot `_fetch_promos()` + `_member_fetch_shipping()`**: Added `conn.rollback()` + try/except for the same InFailedSqlTransaction protection.
- **Phone number rule (STRICT)**: `083-668-2211` shown only in 3 cases: (1) customer explicitly asks, (2) payment trust concern, (3) custom order request.
- **Promotions in system prompt**: Added inline instruction at section header `=== โปรโมชั่น... ===` to force Gemini to list all promos when asked (prevents "ไม่มีโปรโมชั่น" when data is present).
- **Opening hours (member bot)**: "ระบบทำงานตลอด 24 ชม. พนักงานจะจัดส่งในวันรุ่งขึ้น"

### Active Integrations
- **iShip (ตัวกลางการขนส่ง)**: Webhook integration (`POST /api/webhook/iship`) for shipping status updates.
- **Meta Marketing API**: Facebook Ads real data integration (`/api/admin/facebook-ads/meta-insights`) for analyzing ad performance and controlling campaigns via the AI Agent.
- **Google AI Models**:
  - `gemini-3.1-pro-preview`: AI Agent WRITE tools (2-phase verify)
  - `gemini-2.5-flash`: AI Agent READ, Bot Vision (size chart), OCR
  - `gemini-2.5-flash-lite`: Auto-Chat Bot (text)
  - `imagen-4.0-generate-preview-05-20` (and fallbacks): AI Agent `generate_image` tool