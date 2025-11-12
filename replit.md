# Admin User Management System

## Overview

This is a full-stack admin user management system built with Flask and Neon PostgreSQL. Its primary purpose is to allow Super Admins to create, view, and delete users with various roles (Super Admin, Assistant Admin, Reseller) and assign reseller tiers. The system features a modern, responsive web interface with real-time API integration, aiming for a professional and secure user management solution.

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
- **Security:** bcrypt for passwords, strong `SESSION_SECRET` from environment variables, route protection, input validation.

### System Design Choices
- **Backend Framework:** Flask for its lightweight and flexible nature.
- **Database:** Neon PostgreSQL for reliability, scalability, and Replit integration.
- **Authentication:** Custom session-based system for granular control and security.
- **Frontend:** Vanilla JavaScript for performance and to avoid framework overhead.
- **Deployment:** Gunicorn production server with multiple workers for concurrency and stability.
- **API Design:** RESTful API endpoints for clear separation of concerns.

### Database Schema
- **roles:** `id`, `name` (Super Admin, Assistant Admin, Reseller)
- **reseller_tiers:** `id`, `name` (Bronze, Silver)
- **users:** `id`, `full_name`, `username`, `password` (bcrypt hashed), `role_id` (FK to roles), `reseller_tier_id` (NULL FK to reseller_tiers), `created_at`

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