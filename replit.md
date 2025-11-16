# Admin User Management & Product Management System

## Overview
This is a full-stack reseller/distributor application built with Flask and Neon PostgreSQL. The system enables Super Admins to manage users with various roles (Super Admin, Assistant Admin, Reseller), assign reseller tiers, and manage products with advanced SPU/SKU variant management, including multiple images, drag-and-drop ordering, and optional size charts. It features a modern glassmorphism UI design with real-time API integration, aiming to provide a professional and secure business management solution.

## User Preferences
- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling

## System Architecture

### UI/UX Decisions
The system features a modern, responsive glassmorphism design with frosted glass effects, animated gradient backgrounds, smooth transitions, and a consistent purple to pink gradient color scheme. It uses the Inter font family and modern line-style SVG icons. A multi-page dashboard with a professional sidebar enhances user experience for sections like Home, Admin User Management, and Settings.

### Technical Implementations
The backend is built with Flask 3.1.2 and Flask-CORS, using a Neon PostgreSQL database. It employs a custom session-based authentication system with bcrypt for password hashing and role-based access control. All admin routes are protected, and input validation is applied to API endpoints. The frontend uses Jinja2 templates, vanilla JavaScript, and CSS Grid for a responsive layout, making asynchronous Fetch API requests.

### Feature Specifications
- **Authentication:** Custom login, session management, bcrypt password hashing, role-based redirects.
- **Admin Dashboard:** Multi-page layout, sidebar navigation, real-time statistics, full CRUD for user management, placeholder settings page.
- **Reseller Dashboard:** Dedicated dashboard for reseller users displaying user info and tier level.
- **User Management:** Create, view, delete users; assign roles (Super Admin, Assistant Admin, Reseller); assign reseller tiers; dynamic form validation.
- **Product Management (SPU/SKU System):**
  - Create products with parent SKU (SPU).
  - Dynamic options/attributes system with drag-and-drop value ordering using SortableJS.
  - Auto-generate SKU variants via Cartesian product.
  - Bulk actions for Master Price and Master Stock application to all variants.
  - View product list with SKU counts.
  - Delete products with cascade deletion.
  - Multiple product image uploads with drag-and-drop reordering.
  - Optional size chart image upload with free aspect ratio cropping.
  - Client-side image preview and deferred upload pattern to prevent orphaned files.
- **Security:** bcrypt for passwords, strong `SESSION_SECRET`, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask for its lightweight and flexibility.
- **Database:** Neon PostgreSQL for reliability, scalability, and Replit integration.
- **Authentication:** Custom session-based system for granular control and security.
- **Frontend:** Vanilla JavaScript for performance and to avoid framework overhead.
- **Deployment:** Gunicorn production server with multiple workers.
- **API Design:** RESTful API endpoints for clear separation of concerns.

### Database Schema
**User Management:** `roles`, `reseller_tiers`, `users`
**Product Management (6-Table SPU/SKU Architecture):** `products`, `product_images`, `options`, `option_values`, `skus`, `sku_values_map`. The `products` table includes `size_chart_image_url`.

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