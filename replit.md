# Admin User Management & Product Management System

## Overview
This full-stack reseller/distributor application, built with Flask and Neon PostgreSQL, is designed for Super Admins to manage users (Super Admin, Assistant Admin, Reseller) and their tiers, alongside comprehensive product management. Key capabilities include advanced SPU/SKU variant handling, multiple image uploads with drag-and-drop ordering, optional size charts, and dynamic pricing based on a 4-tier reseller system with configurable auto-upgrade logic. It features role-based access control, a robust order management system with configurable numbering, sales analytics, and a complete Made-to-Order (MTO) system with production tracking and payment verification. The system also includes an in-app chat for real-time communication between Admins and Resellers. The overarching goal is to provide a professional, secure business management solution with a modern UI and real-time API integration.

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
- **User & Role Management:** Super Admin, Assistant Admin, Reseller roles; 4-tier reseller system with auto-upgrade logic and manual override; role-based brand access.
- **Product Management (SPU/SKU):** Full CRUD for products, brands, and categories; dynamic options/attributes; auto-generation of SKU variants; multi-image upload with drag-and-drop; low stock indicators; product status management; shipping fields. Made-to-Order (MTO) system with production days, minimum order quantity, deposit settings, custom product creation, and a 4-page management workflow (Quotation Requests, Quotations, MTO Orders, Payment Verification) with timeline tracking.
- **Order & Sales Management:** Configurable order numbering; sales statistics, 7-day sales charts, recent orders, top-selling products; sales history with filters; brand sales analytics.
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
- **Deployment:** Gunicorn production server.

## Planned Integrations

### iShip (ตัวกลางการขนส่ง) - Pending
- **Purpose:** Receive shipping status updates via webhook from iShip logistics aggregator
- **Webhook Endpoint:** `POST /api/webhook/iship`
- **Payload Fields:** `tracking` (tracking number), `status` (shipped/in_transit/pickup/delivered), `status_desc` (description)
- **Expected Behavior:**
  - Match `tracking` to `orders.tracking_number` (or `order_shipments.tracking_number`)
  - On `delivered` → update order status to 'delivered', send chat notification
  - On `shipped/in_transit/pickup` → update to 'shipped', send chat notification
  - Auto-unarchive chat thread and notify reseller via existing `send_order_status_chat()` helper
- **Integration Notes:**
  - Use existing `get_db()` (not `get_db_connection()`)
  - Use existing `send_order_status_chat(reseller_id, order_number, status, extra_info)` for chat notifications
  - Use existing `send_push_notification()` for push alerts
  - Tracking number is stored in `order_shipments` table (not directly in `orders`)
  - May need iShip API key stored as secret `ISHIP_API_KEY`
  - Webhook should validate request authenticity (e.g., signature or API key header)

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