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

## Confirmed Available Google AI Models (GEMINI_API_KEY)
รายชื่อโมเดลที่ใช้งานได้จริงกับ API key ของระบบนี้ (ยืนยันโดย Owner มี.ค. 2026):

### Gemini Text/Multimodal Models
| Display Name | API Model Name (ใช้ใน code) | ใช้ใน |
|---|---|---|
| Gemini 3.1 Pro | `gemini-3.1-pro-preview` | AI Agent WRITE tools (2-phase verify) |
| Gemini 3 Pro | `gemini-3.0-pro` | - |
| Gemini 3 Flash | `gemini-3.0-flash` | - |
| Gemini 3.1 Flash Lite | `gemini-3.1-flash-lite` | - |
| Gemini 2.5 Pro | `gemini-2.5-pro` | - |
| Gemini 2.5 Flash | `gemini-2.5-flash` | AI Agent READ, Bot Vision, OCR |
| **Gemini 2.5 Flash Lite** | **`gemini-2.5-flash-lite`** | **Auto-Chat Bot (text)** |
| Gemini 2.5 Flash TTS | `gemini-2.5-flash-tts` | - |
| Gemini 2.5 Pro TTS | `gemini-2.5-pro-tts` | - |
| Gemini 2.5 Flash Native Audio Dialog | `gemini-2.5-flash-native-audio-dialog` | - |
| Gemini 2 Flash | `gemini-2.0-flash` | - |
| Gemini 2 Flash Lite | `gemini-2.0-flash-lite` | - |
| Gemini 2 Flash Exp | `gemini-2.0-flash-exp` | - |
| Gemini Embedding 1 | `gemini-embedding-exp` | - |

### Image Generation Models
| Display Name | API Model Name | ใช้ใน |
|---|---|---|
| **Imagen 4 Generate** | `imagen-4.0-generate-preview-05-20` | AI Agent generate_image tool |
| **Imagen 4 Ultra Generate** | `imagen-4.0-ultra-generate-preview-05-20` | fallback |
| **Imagen 4 Fast Generate** | `imagen-4.0-fast-generate-preview-06-05` | fallback |
| Nano Banana (Gemini 2.5 Flash Preview Image) | `gemini-2.5-flash-preview-image` | - |
| Nano Banana Pro (Gemini 3 Pro Image) | `gemini-3.0-pro-image` | - |
| Nano Banana 2 (Gemini 3.1 Flash Image) | `gemini-3.1-flash-image` | - |

### Video Generation Models
| Display Name | API Model Name |
|---|---|
| Veo 3 Generate | `veo-3.0-generate-preview` |
| Veo 3 Fast Generate | `veo-3.0-fast-generate-preview` |

### Gemma Open Models
| Display Name | API Model Name |
|---|---|
| Gemma 3 1B | `gemma-3-1b-it` |
| Gemma 3 2B | `gemma-3-2b-it` |
| Gemma 3 4B | `gemma-3-4b-it` |
| Gemma 3 12B | `gemma-3-12b-it` |
| Gemma 3 27B | `gemma-3-27b-it` |

### Specialist Models
| Display Name | Notes |
|---|---|
| Gemini Robotics ER 1.5 Preview | Robotics control |
| Computer Use Preview | Computer vision/control |
| Deep Research Pro Preview | Long-form research |

### Current Model Usage in Codebase
- **Auto-Chat Bot (text):** `gemini-2.5-flash-lite` ← confirmed available ✅
- **Auto-Chat Bot (size chart vision):** `gemini-2.5-flash`
- **AI Agent (READ tools / chat):** `gemini-2.5-flash` via `_agent_call_gemini()`
- **AI Agent (WRITE tools 2-phase):** `gemini-3.1-pro-preview`
- **OCR (Quick Order label):** `gemini-2.5-flash`
- **Image Generation (generate_image tool):** Imagen 4 fallback chain

## System Architecture

### UI/UX Decisions
The system features a modern, responsive glassmorphism design with frosted glass effects, animated gradient backgrounds, and smooth transitions, adhering to a consistent purple-to-pink gradient color scheme. It uses the Inter font, compact sizing for data, and modern line-style SVG icons. The multi-page dashboard includes a collapsible sidebar. Product management UI is inspired by e-commerce platforms, offering compact font sizes, status tabs, an advanced filter bar, bulk actions, toggle switches, collapsible SKU variants, and inline editing. A global alert system provides consistent user feedback. Both Admin and Reseller interfaces are structured as Single Page Applications (SPAs) using hash-based navigation.

### Technical Implementations
The backend is a Flask 3.1.2 application, utilizing Flask-CORS and a Neon PostgreSQL database. It employs a custom session-based authentication system with bcrypt for password hashing and role-based access control, ensuring all admin routes are protected with input validation. The frontend uses Jinja2 templates, vanilla JavaScript, CSS Grid for responsiveness, and asynchronous Fetch API requests. Product updates use a diff-based approach to maintain SKU ID integrity. The system also includes a comprehensive warehouse management system with stock transfers, adjustments, and an audit log, as well as an order shipment system with automatic splitting and label printing.

**File Structure:**
- `app.py` — main application (~17,921 lines): all routes except AI Agent
- `routes/agent.py` — AI Agent Blueprint (~1,731 lines): all `/api/admin/agent/*` routes, registered via `app.register_blueprint(agent_bp)`
- `routes/__init__.py` — empty package file
- `database.py` — DB connection pool (shared by app.py and routes/agent.py)

### Feature Specifications
- **User & Role Management:** Super Admin, Assistant Admin, Reseller roles; 4-tier reseller system with auto-upgrade logic and manual override; role-based brand access. `total_purchases` increments on `delivered` status; `cancel_order` deducts stock if `was_delivered`.
- **Public Catalog Page:** `/catalog` — public product catalog (no login required) with brand/category/featured filters via URL params (`?brand=`, `?category=`, `?featured=1`). Admin can mark products as "โปรโมท" (is_featured) via ★ star button in product list. Sidebar link "ดูแคตตาล็อกสินค้า" in admin dashboard opens catalog in new tab.
- **Marketing Module:** Admin CRUD for promotions (auto-applied, tier/brand/category conditions, stackable) and coupons (assign to users, min spend, max discount, expiry, usage limits, `applies_to` scope: `all`/`brand`/`product`). Redesigned Admin and Reseller UIs for promotions and coupons, including a dedicated "โปรโมชัน" tab for resellers.
- **Product Management (SPU/SKU):** Full CRUD for products, brands, and categories; dynamic options/attributes; auto-generation of SKU variants; multi-image upload with drag-and-drop; low stock indicators; product status management; shipping fields. Made-to-Order (MTO) system with production days, MOQ, deposit settings, and a 4-page management workflow.
- **Order & Sales Management:** Configurable order numbering; sales statistics, 7-day sales charts, recent orders, top-selling products; sales history with filters; brand sales analytics. Shipping update page for in-transit orders with status changes and chat notifications. Admin can cancel shipped orders (no stock auto-restore); triggers refund flow.
- **Quick Order (ขายด่วน) — Enhanced + Label OCR + Shipping Address:** Quick order functionality (`is_quick_order`, `platform`, `shipping_*` fields). Includes "📷 อ่านใบปะหน้าอัตโนมัติ" button for label OCR via Gemini Vision to auto-fill order details. Real-time phone lookup to identify existing/new customers. Shipping address saved per order, not on customer profile. Auto-saves customer information during quick order creation.
- **Refund System:** `order_refunds` table for records. APIs for refund info, slip upload, chat notification, and PromptPay QR generation.
- **Warehouse & Stock Management:** Full CRUD for warehouses; multi-warehouse stock tracking; stock transfer and adjustment systems with audit logging.
- **Reseller Features:** Dedicated dashboard; tier-specific pricing; customer database management; profile management.
- **Communication:** In-app chat between Admin and Resellers with real-time messaging, broadcasts, templates, attachments, unread badges, and email notifications. **Auto-Chat Bot**: `gemini-2.5-flash-lite` bot replies automatically to resellers. Features: keyword product search when IDLE, brand/category/SKU option context, **Gemini Vision reads size chart images** when customer asks about sizing, alternative product suggestions when size is OOS. Resellers can press "🙋 ขอคุยกับ Admin" to escalate. Admin sees 🙋 badge + [Bot] badge on messages. Bot pauses 2 hours when admin replies manually. Bot settings (name, persona, on/off) in AI Agent settings panel. `bot_description` field in product create/edit forms for admin to give bot extra product hints.
- **PWA & Push Notifications:** Progressive Web App with installable icon, Service Worker for caching, and VAPID-based Web Push Notifications for real-time alerts.
- **AI Agent:** In-app AI assistant (FAB) with a glassmorphism panel. READ tools (query_sales_today, query_low_stock, query_stock_product, query_order_counts, search_web, generate_image, etc.) for immediate answers. WRITE tools (adjust_stock, update_order_status, toggle_product, send_chat_message, toggle_facebook_ad) require Admin approval. All actions logged. Smart model routing: `gemini-2.5-flash` for READ/chat, `gemini-3.1-pro-preview` for WRITE tools (2-phase verification). `search_web` uses Gemini Google Search grounding for real-time internet data. Model badge (⚡Flash / ✨Pro) shown on each response. Ctrl+V paste image support. Gender-aware welcome message based on `custom_prompt` and `ending_particle` settings. `generate_image` tool uses Imagen 4 to create images inline in the chat panel.
- **Stock Race Condition Protection:** `SELECT ... FOR UPDATE OF sws` locks warehouse stock rows during `create_order` to prevent concurrent purchases from overselling the last unit. The UPDATE also uses `WHERE stock >= qty` as a second safety layer with automatic rollback.
- **Auto-Cancel Expired Orders:** APScheduler (`BackgroundScheduler`) runs every 30 minutes to find `pending_payment` orders older than 24 hours. Auto-cancels them, restores stock to warehouses (with `stock_audit_log`), and sends bot chat notification to the reseller. Uses `FOR UPDATE SKIP LOCKED` for safe multi-worker execution.
- **Order Chat Notifications:** Bot automatically notifies reseller in chat when: (1) order created — 24-hour payment deadline reminder, (2) auto-cancelled — explains reason and instructs to re-order.
- **Security:** `bcrypt` for passwords, strong `SESSION_SECRET`, route protection, input validation.

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

### Database Service
- **Replit PostgreSQL (Neon-backed)**: Accessed via `DATABASE_URL`.

### Frontend Libraries
- **Vanilla JavaScript**: For client-side logic.
- **CSS Grid**: For responsive layouts.
- **Fetch API**: For HTTP requests.
- **SortableJS**: Drag-and-drop functionality.
- **Cropper.js**: Image cropping.
- **Chart.js**: For sales charts.

### Active Integrations
- **iShip (ตัวกลางการขนส่ง)**: Webhook integration (`POST /api/webhook/iship`) for shipping status updates (delivered, shipped, returned, etc.). Authenticated via `X-API-Key` or `Authorization: Bearer`.
- **Meta Marketing API**: Facebook Ads real data integration (`/api/admin/facebook-ads/meta-insights`). Credentials (Access Token + Ad Account ID) stored in `facebook_pixel_settings` table, with fallback to `META_ACCESS_TOKEN` / `META_AD_ACCOUNT_ID` environment variables. AI Agent can call `query_facebook_ads` tool to analyze ad performance (spend, ROAS, CTR, impressions, conversions). AI Agent can call `toggle_facebook_ad` (WRITE tool) to pause/activate campaigns with plan/approve flow.
