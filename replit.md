# Admin User Management System

## Overview

Full-stack admin user management system built with Flask and Neon PostgreSQL. Allows Super Admins to create, view, and delete users with different roles (Super Admin, Assistant Admin, Reseller) and assign reseller tiers when applicable. Features a modern, responsive web interface with real-time API integration.

**Last Updated:** November 12, 2025

## User Preferences

- **Communication Style:** Simple, everyday language (Thai/English)
- **Database:** Neon PostgreSQL (via Replit built-in integration)
- **Development Approach:** Production-ready code with proper error handling

## Recent Changes

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
GET  /                      - Render admin management page
GET  /api/roles             - List all roles
GET  /api/reseller-tiers    - List all reseller tiers
GET  /api/users             - List all users with role info
POST /api/users             - Create new user
DELETE /api/users/<id>      - Delete user
```

**Security:**
- Password hashing with SHA-256 (note: should upgrade to bcrypt for production)
- Session secret from environment variable
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
   - password (VARCHAR) - SHA-256 hashed
   - role_id (INTEGER FK → roles.id)
   - reseller_tier_id (INTEGER NULL FK → reseller_tiers.id)
   - created_at (TIMESTAMP)

**Default Data:**
- Admin user: admin@system.com / admin123 (Super Admin role)
- 3 roles and 2 reseller tiers pre-seeded

### Frontend Architecture

**Template System:** Jinja2 (Flask)
- Main template: `templates/admin_user_management.html`

**Static Assets:**
- CSS: `static/css/admin.css` - Modern gradient design with responsive grid
- JavaScript: `static/js/admin.js` - API integration with fetch(), no frameworks

**UI Features:**
- Form validation (required fields, email format)
- Dynamic show/hide of Reseller Tier field based on role selection
- Real-time user list updates after create/delete operations
- Badge styling for different user roles
- Success/error alert notifications
- Delete confirmation dialogs
- Responsive design (mobile-friendly)

### File Structure

```
├── app.py                           # Flask application & API routes
├── database.py                      # Database connection & initialization
├── templates/
│   └── admin_user_management.html  # Main admin interface
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

### Required (Auto-configured by Replit)
- `DATABASE_URL` - PostgreSQL connection string
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - DB credentials

### Optional
- `SESSION_SECRET` - Flask session encryption key (has default for dev)

## Development Workflow

### Running the Application
1. Workflow "Admin User Management" runs: `python app.py`
2. Server starts on `http://0.0.0.0:5000`
3. Database automatically initializes on first run
4. Access via Replit webview at port 5000

### Making Database Changes
1. Update schema in `database.py` (init_db function)
2. For development: Delete existing data and restart workflow
3. For production: Would need proper migration tool (Alembic recommended)

### Testing
- Manual testing via web interface
- Check workflow logs for database connection status
- Verify API endpoints return correct JSON responses

## Known Limitations & Future Improvements

### Security (Identified by Architect Review)
1. **No Authentication/Authorization** - Anyone can access admin endpoints
   - Recommended: Implement login system with session-based auth
   - Check user role before allowing admin actions

2. **Weak Password Hashing** - SHA-256 without salt
   - Recommended: Upgrade to bcrypt or Argon2

### Code Quality Improvements
1. **Connection Management** - Currently using manual connection handling
   - Consider: Context managers or connection pooling helpers
   
2. **Server-side Validation** - Limited validation on reseller tier requirement
   - Add: Check that Reseller role requires reseller_tier_id

3. **Testing** - No automated tests
   - Add: Integration tests for all API endpoints

### Features for Production
1. User editing functionality (currently only create/delete)
2. Pagination for large user lists
3. Search and filtering
4. Audit logging for user management actions
5. Email verification for new users
6. Password reset functionality

## Deployment Notes

- **Current State:** Development server (Flask debug mode)
- **For Production:** 
  - Use production WSGI server (Gunicorn recommended)
  - Disable Flask debug mode
  - Implement authentication before deploying
  - Use environment-specific SESSION_SECRET
  - Consider rate limiting on API endpoints

## Additional Notes

- System uses Replit's built-in PostgreSQL (Neon), not external Supabase
- Original prototype (admin_user_management.html with mock data) has been removed
- Database supports automatic rollback via Replit's checkpoint feature
- All API responses use JSON format
- Frontend makes asynchronous requests for better UX
