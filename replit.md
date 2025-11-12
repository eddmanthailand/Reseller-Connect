# Admin User Management System

## Overview

Full-stack admin user management system built with Flask and Neon PostgreSQL. Allows Super Admins to create, view, and delete users with different roles (Super Admin, Assistant Admin, Reseller) and assign reseller tiers when applicable. Features a modern, responsive web interface with real-time API integration.

**Last Updated:** November 12, 2025

## User Preferences

- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling

## Recent Changes

### November 12, 2025 - Production Security & Server Upgrades
- **Upgraded Password Security to bcrypt**
  - Migrated from SHA-256 to bcrypt for all password hashing
  - Super Admin password now uses bcrypt with salt
  - Login endpoint verifies passwords with bcrypt.checkpw()
  - New user creation uses bcrypt hashing
  - Production-grade password security in place

- **Configured Production SESSION_SECRET**
  - Strong 64-character SESSION_SECRET generated
  - Environment variable configuration (no hardcoded fallback)
  - Application fails fast if SESSION_SECRET is missing
  - Clear error message for missing configuration

- **Deployed Gunicorn Production Server**
  - Replaced Flask development server with Gunicorn
  - 4 workers for concurrent request handling
  - --reuse-port flag for better performance
  - Deployment config set to autoscale
  - Production-ready server configuration

### November 12, 2025 - Custom Login Authentication System
- **Implemented Complete Session-Based Authentication**
  - Created professional login page with gradient design
  - Session management using Flask sessions
  - Login/logout API endpoints with credential validation
  - Custom authentication decorators (`login_required`, `admin_required`)
  - Role-based redirects: Super Admin/Assistant Admin → `/admin`, Reseller → `/dashboard`
  - All admin routes now protected with authentication middleware
  - Current user info display with logout functionality

- **Updated Super Admin Credentials**
  - Username: `superadmin`
  - Password: `A0971exp11` (bcrypt hashed)
  - Removed old admin@system.com account

- **Created Reseller Dashboard**
  - Dashboard page for reseller users
  - Displays user info and tier level
  - Coming soon placeholders for sales and order features
  - Logout functionality

### November 12, 2025 - Neon PostgreSQL Migration
- **Migrated from SQLite to Neon PostgreSQL database**
  - Converted all SQL queries from SQLite syntax (?) to PostgreSQL (%s)
  - Updated schema to use PostgreSQL data types (SERIAL, VARCHAR, TIMESTAMP)
  - Implemented RealDictCursor for JSON-friendly responses
  - Added proper connection cleanup with finally blocks to prevent connection leaks
  - Removed obsolete SQLite database file

- **Created Complete Admin User Management System**
  - Flask backend with RESTful API endpoints
  - PostgreSQL database with roles, reseller_tiers, and users tables
  - Modern frontend with vanilla JavaScript (no frameworks)
  - Responsive CSS Grid layout
  - Real-time form validation and dynamic UI updates

## Project Architecture

### Backend (Flask)

**Framework:** Flask 3.1.2 with Flask-CORS 6.0.1

**Database Connection:**
- Uses Replit's built-in Neon PostgreSQL database
- Connection via `DATABASE_URL` environment variable
- Connection pooling handled by psycopg2
- Proper error handling with rollback and cleanup

**API Endpoints:**
```
# Authentication Routes
GET  /login                 - Login page
POST /api/login             - Authenticate user & create session
POST /api/logout            - Clear session & logout
GET  /api/me                - Get current user info

# Protected Routes (require login)
GET  /                      - Redirect to login or appropriate dashboard
GET  /admin                 - Admin panel (Super Admin & Assistant Admin only)
GET  /dashboard             - Reseller dashboard (Reseller role only)

# Admin API (require admin role)
GET  /api/roles             - List all roles
GET  /api/reseller-tiers    - List all reseller tiers
GET  /api/users             - List all users with role info
POST /api/users             - Create new user
DELETE /api/users/<id>      - Delete user
```

**Security:**
- Session-based authentication with Flask sessions
- Password hashing with bcrypt (production-grade with salt)
- SESSION_SECRET required from environment variable (no fallback)
- Route protection with `login_required` and `admin_required` decorators
- Role-based access control
- Input validation on all endpoints
- SQL injection prevention via parameterized queries

### Database Schema (PostgreSQL)

**Tables:**

1. **roles**
   - id (SERIAL PRIMARY KEY)
   - name (VARCHAR UNIQUE) - 'Super Admin', 'Assistant Admin', 'Reseller'

2. **reseller_tiers**
   - id (SERIAL PRIMARY KEY)
   - name (VARCHAR UNIQUE) - 'Bronze', 'Silver'

3. **users**
   - id (SERIAL PRIMARY KEY)
   - full_name (VARCHAR)
   - username (VARCHAR UNIQUE) - Email address
   - password (VARCHAR) - bcrypt hashed
   - role_id (INTEGER FK → roles.id)
   - reseller_tier_id (INTEGER NULL FK → reseller_tiers.id)
   - created_at (TIMESTAMP)

**Default Data:**
- Super Admin user: `superadmin` / `A0971exp11` (Super Admin role)
- 3 roles and 2 reseller tiers pre-seeded

### Frontend Architecture

**Template System:** Jinja2 (Flask)
- Login page: `templates/login.html`
- Admin panel: `templates/admin_user_management.html`
- Reseller dashboard: `templates/reseller_dashboard.html`

**Static Assets:**
- CSS: `static/css/admin.css` - Modern gradient design with responsive grid
- JavaScript: `static/js/admin.js` - API integration with fetch(), no frameworks

**UI Features:**
- Login page with username/password authentication
- Session-based authentication with automatic redirects
- Current user info display with logout button
- Form validation (required fields, email format)
- Dynamic show/hide of Reseller Tier field based on role selection
- Real-time user list updates after create/delete operations
- Badge styling for different user roles
- Success/error alert notifications
- Delete confirmation dialogs
- Responsive design (mobile-friendly)

### File Structure

```
├── app.py                           # Flask application, API routes & auth
├── database.py                      # Database connection & initialization
├── templates/
│   ├── login.html                  # Login page
│   ├── admin_user_management.html  # Admin panel (Super Admin/Assistant Admin)
│   └── reseller_dashboard.html     # Reseller dashboard
├── static/
│   ├── css/
│   │   └── admin.css               # Styling
│   └── js/
│       └── admin.js                # Frontend logic & API calls
├── pyproject.toml                   # Python dependencies (uv)
├── uv.lock                          # Dependency lock file
└── replit.md                        # This file
```

## External Dependencies

### Python Packages (via uv)
- **flask** (3.1.2) - Web framework
- **flask-cors** (6.0.1) - CORS support for API
- **psycopg2-binary** (2.9.11) - PostgreSQL adapter
- **python-dotenv** (1.2.1) - Environment variable management
- **bcrypt** (5.0.0) - Password hashing
- **gunicorn** (23.0.0) - Production WSGI server

### Database Service
- **Replit PostgreSQL** (Neon-backed)
  - Automatically provisioned via Replit integration
  - Accessed via DATABASE_URL environment variable
  - Supports rollback feature for data recovery

### Frontend
- **Vanilla JavaScript** - No external frameworks
- **CSS Grid** - Modern responsive layout
- **Fetch API** - HTTP requests

## Environment Variables

### Required
- `DATABASE_URL` - PostgreSQL connection string (auto-configured by Replit)
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - DB credentials (auto-configured by Replit)
- `SESSION_SECRET` - Flask session encryption key (64-character hex string, REQUIRED for security)

## Development Workflow

### Running the Application
1. Workflow "Admin User Management" runs: `gunicorn --bind 0.0.0.0:5000 --workers 4 --reuse-port app:app`
2. Gunicorn production server starts with 4 workers on `http://0.0.0.0:5000`
3. Database automatically initializes on first run (across all workers)
4. Access via Replit webview at port 5000
5. Login with `superadmin` / `A0971exp11`
6. Super Admin redirects to `/admin`, Reseller redirects to `/dashboard`

### Making Database Changes
1. Update schema in `database.py` (init_db function)
2. For development: Delete existing data and restart workflow
3. For production: Would need proper migration tool (Alembic recommended)

### Testing
- Manual testing via web interface
- Login at `/login` with Super Admin credentials
- Test role-based redirects (Admin → `/admin`, Reseller → `/dashboard`)
- Verify authentication protects all admin routes
- Check workflow logs for database connection status
- Verify API endpoints return correct JSON responses

## Known Limitations & Future Improvements

### Security (Identified by Architect Review)
1. **API Error Messages** - Some endpoints may leak internal exception details
   - Recommended: Tighten error responses to avoid information disclosure in production

### Code Quality Improvements
1. **Connection Management** - Currently using manual connection handling
   - Consider: Context managers or connection pooling helpers
   
2. **Server-side Validation** - Limited validation on reseller tier requirement
   - Add: Check that Reseller role requires reseller_tier_id

3. **Testing** - No automated tests
   - Add: Integration tests for all API endpoints
   - Add: Tests for login/logout flow and role-based access control

### Features for Production
1. User editing functionality (currently only create/delete)
2. Pagination for large user lists
3. Search and filtering
4. Audit logging for user management actions
5. Email verification for new users
6. Password reset functionality

## Deployment Notes

- **Current State:** Production-ready with Gunicorn server
- **Authentication:** ✅ Custom login system with session-based auth and bcrypt
- **Security:** ✅ bcrypt password hashing, required SESSION_SECRET
- **Server:** ✅ Gunicorn with 4 workers, autoscale deployment config
- **For Production Deployment:** 
  - ✅ SESSION_SECRET configured (strong 64-character secret)
  - ✅ bcrypt password hashing implemented
  - ✅ Gunicorn production server running
  - Consider rate limiting on API endpoints
  - Tighten error message responses
  - Set up monitoring and logging

## Additional Notes

- System uses Replit's built-in PostgreSQL (Neon), not external Supabase
- Original prototype (admin_user_management.html with mock data) has been removed
- Database supports automatic rollback via Replit's checkpoint feature
- All API responses use JSON format
- Frontend makes asynchronous requests for better UX
