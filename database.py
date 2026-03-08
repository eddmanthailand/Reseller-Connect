import psycopg2
import psycopg2.extras
import psycopg2.pool
import bcrypt
import os
from datetime import datetime

def get_db_url():
    """Get database URL from environment"""
    return os.environ.get('DATABASE_URL')

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        db_url = get_db_url()
        if not db_url:
            raise Exception("DATABASE_URL environment variable not set")
        _pool = psycopg2.pool.SimpleConnectionPool(
            1, 5, db_url,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            connect_timeout=10
        )
    return _pool

class _PooledConnection:
    """Wraps a psycopg2 connection so that .close() returns it to the pool."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def close(self):
        try:
            if self._conn.closed:
                try:
                    self._pool.putconn(self._conn, close=True)
                except Exception:
                    pass
            else:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                try:
                    self._pool.putconn(self._conn)
                except Exception:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def _is_connection_alive(conn):
    """Check if a connection is truly usable by running a lightweight query."""
    try:
        if conn.closed:
            return False
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.rollback()
        return True
    except Exception:
        return False

def _discard_conn(pool, conn):
    """Safely discard a dead connection from the pool."""
    try:
        pool.putconn(conn, close=True)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass

def get_db():
    """Get a pooled database connection with stale-connection recovery."""
    pool = _get_pool()
    db_url = get_db_url()

    for _attempt in range(pool.maxconn + 1):
        conn = pool.getconn()
        if _is_connection_alive(conn):
            return _PooledConnection(conn, pool)
        _discard_conn(pool, conn)

    conn = psycopg2.connect(
        db_url,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=10
    )
    return conn

def init_db():
    """Initialize database with tables and default data"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Use advisory lock to prevent race conditions with multiple workers
        cursor.execute("SELECT pg_advisory_lock(12345)")
        
        # Create roles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            )
        ''')
        
        # Create reseller_tiers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_tiers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            )
        ''')
        
        # Migration: Add new columns to reseller_tiers table
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'reseller_tiers' AND column_name = 'level_rank'
                ) THEN
                    ALTER TABLE reseller_tiers ADD COLUMN level_rank INTEGER DEFAULT 1;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'reseller_tiers' AND column_name = 'upgrade_threshold'
                ) THEN
                    ALTER TABLE reseller_tiers ADD COLUMN upgrade_threshold DECIMAL(12, 2) DEFAULT 0;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'reseller_tiers' AND column_name = 'description'
                ) THEN
                    ALTER TABLE reseller_tiers ADD COLUMN description TEXT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'reseller_tiers' AND column_name = 'is_manual_only'
                ) THEN
                    ALTER TABLE reseller_tiers ADD COLUMN is_manual_only BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        ''')
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role_id INTEGER NOT NULL,
                reseller_tier_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (role_id) REFERENCES roles(id),
                FOREIGN KEY (reseller_tier_id) REFERENCES reseller_tiers(id)
            )
        ''')
        
        # Migration: Add tier_manual_override column to users table
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'tier_manual_override'
                ) THEN
                    ALTER TABLE users ADD COLUMN tier_manual_override BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        ''')
        
        # Create brands table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS brands (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create admin_brand_access table (which admin can manage which brands)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_brand_access (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE CASCADE,
                UNIQUE(user_id, brand_id)
            )
        ''')
        
        # Create products table (SPU - parent product)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                parent_sku VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add brand_id column to products table if not exists
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = 'brand_id'
                ) THEN
                    ALTER TABLE products ADD COLUMN brand_id INTEGER REFERENCES brands(id);
                END IF;
            END $$;
        ''')
        
        # Create options table (product attributes like color, size)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS options (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        
        # Create option_values table (attribute values with sort_order)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS option_values (
                id SERIAL PRIMARY KEY,
                option_id INTEGER NOT NULL,
                value VARCHAR(100) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (option_id) REFERENCES options(id) ON DELETE CASCADE
            )
        ''')
        
        # Create skus table (product variants)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                sku_code VARCHAR(100) UNIQUE NOT NULL,
                price DECIMAL(10, 2) DEFAULT 0,
                stock INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        
        # Create sku_values_map table (many-to-many relationship)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sku_values_map (
                id SERIAL PRIMARY KEY,
                sku_id INTEGER NOT NULL,
                option_value_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus(id) ON DELETE CASCADE,
                FOREIGN KEY (option_value_id) REFERENCES option_values(id) ON DELETE CASCADE
            )
        ''')
        
        # Create product_images table (multiple images per product with ordering)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_images (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        
        # Migration: Drop image_url column from products table if it exists
        cursor.execute('''
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = 'image_url'
                ) THEN
                    ALTER TABLE products DROP COLUMN image_url;
                END IF;
            END $$;
        ''')
        
        # Migration: Add size_chart_image_url column to products table if not exists
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = 'size_chart_image_url'
                ) THEN
                    ALTER TABLE products ADD COLUMN size_chart_image_url TEXT;
                END IF;
            END $$;
        ''')
        
        # Migration: Add status column to products table if not exists
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = 'status'
                ) THEN
                    ALTER TABLE products ADD COLUMN status VARCHAR(20) DEFAULT 'active';
                END IF;
            END $$;
        ''')
        
        # Create categories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create unique constraint for category name (considering hierarchy)
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'categories_name_parent_unique'
                ) THEN
                    ALTER TABLE categories ADD CONSTRAINT categories_name_parent_unique 
                    UNIQUE (name, parent_id);
                END IF;
            END $$;
        ''')
        
        # Create product_categories table (many-to-many relationship)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_categories (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, category_id)
            )
        ''')
        
        # Create product_customizations table (customization groups that don't affect SKU)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_customizations (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                is_required BOOLEAN DEFAULT FALSE,
                allow_multiple BOOLEAN DEFAULT FALSE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create customization_choices table (individual choices within a customization group)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customization_choices (
                id SERIAL PRIMARY KEY,
                customization_id INTEGER NOT NULL REFERENCES product_customizations(id) ON DELETE CASCADE,
                label VARCHAR(255) NOT NULL,
                extra_price DECIMAL(10, 2) DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create product_tier_pricing table (discount percentage per product per tier)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_tier_pricing (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                tier_id INTEGER NOT NULL REFERENCES reseller_tiers(id) ON DELETE CASCADE,
                discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, tier_id)
            )
        ''')
        
        # Migration: Add total_purchases column to users table if not exists
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'total_purchases'
                ) THEN
                    ALTER TABLE users ADD COLUMN total_purchases DECIMAL(12, 2) DEFAULT 0;
                END IF;
            END $$;
        ''')
        
        # Create sales_channels table (configurable sales channels)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_channels (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create promptpay_settings table (store PromptPay QR code)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promptpay_settings (
                id SERIAL PRIMARY KEY,
                qr_image_url TEXT,
                account_name VARCHAR(255),
                account_number VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES users(id)
            )
        ''')
        
        # Create carts table (shopping cart per reseller)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, status)
            )
        ''')
        
        # Create cart_items table (items in cart)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart_items (
                id SERIAL PRIMARY KEY,
                cart_id INTEGER NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
                sku_id INTEGER NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price DECIMAL(10, 2) NOT NULL,
                tier_discount_percent DECIMAL(5, 2) DEFAULT 0,
                customization_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cart_id, sku_id)
            )
        ''')
        
        # Create orders table (order records)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                status VARCHAR(30) DEFAULT 'pending_payment',
                channel_id INTEGER REFERENCES sales_channels(id),
                total_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
                discount_amount DECIMAL(12, 2) DEFAULT 0,
                final_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
                tier_id INTEGER REFERENCES reseller_tiers(id),
                notes TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                cancelled_at TIMESTAMP
            )
        ''')
        
        # Create order_items table (items in order)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                sku_id INTEGER NOT NULL REFERENCES skus(id),
                product_name VARCHAR(255) NOT NULL,
                sku_code VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price DECIMAL(10, 2) NOT NULL,
                tier_discount_percent DECIMAL(5, 2) DEFAULT 0,
                discount_amount DECIMAL(10, 2) DEFAULT 0,
                subtotal DECIMAL(10, 2) NOT NULL,
                customization_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create payment_slips table (payment slip uploads)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_slips (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                slip_image_url TEXT NOT NULL,
                amount DECIMAL(12, 2),
                transfer_date TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                verified_by INTEGER REFERENCES users(id),
                verified_at TIMESTAMP,
                reject_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create stock_transactions table (stock movement log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_transactions (
                id SERIAL PRIMARY KEY,
                sku_id INTEGER NOT NULL REFERENCES skus(id),
                quantity_change INTEGER NOT NULL,
                quantity_before INTEGER NOT NULL,
                quantity_after INTEGER NOT NULL,
                transaction_type VARCHAR(30) NOT NULL,
                reference_type VARCHAR(30),
                reference_id INTEGER,
                channel_id INTEGER REFERENCES sales_channels(id),
                reason TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create notifications table (in-app notifications)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                type VARCHAR(50) DEFAULT 'info',
                reference_type VARCHAR(30),
                reference_id INTEGER,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create Facebook Pixel settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS facebook_pixel_settings (
                id SERIAL PRIMARY KEY,
                pixel_id VARCHAR(50),
                access_token TEXT,
                is_active BOOLEAN DEFAULT FALSE,
                track_page_view BOOLEAN DEFAULT TRUE,
                track_lead BOOLEAN DEFAULT TRUE,
                track_complete_registration BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create page visits tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS page_visits (
                id SERIAL PRIMARY KEY,
                page_name VARCHAR(100) NOT NULL,
                source VARCHAR(50),
                visitor_ip VARCHAR(45),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_page_visits_page_name ON page_visits(page_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_page_visits_source ON page_visits(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_page_visits_created_at ON page_visits(created_at)')
        
        # ==================== IN-APP CHAT SYSTEM ====================
        
        # Chat threads table (1-to-1 conversation between admin and reseller)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_threads (
                id SERIAL PRIMARY KEY,
                reseller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                last_message_at TIMESTAMP,
                last_message_preview TEXT,
                is_archived BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(reseller_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_threads_reseller ON chat_threads(reseller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_threads_last_message ON chat_threads(last_message_at DESC)')
        
        # Chat messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                sender_type VARCHAR(20) NOT NULL,
                content TEXT,
                is_broadcast BOOLEAN DEFAULT FALSE,
                broadcast_id INTEGER,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_messages_sender ON chat_messages(sender_id)')
        
        # Chat message attachments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_attachments (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                file_url TEXT NOT NULL,
                file_name VARCHAR(255),
                file_type VARCHAR(50),
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_attachments(message_id)')
        
        # Chat read status table (tracks last read message per user per thread)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_read_status (
                id SERIAL PRIMARY KEY,
                thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                last_read_message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
                last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(thread_id, user_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_read_status_thread_user ON chat_read_status(thread_id, user_id)')
        
        # Quick reply templates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_quick_replies (
                id SERIAL PRIMARY KEY,
                title VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                shortcut VARCHAR(50),
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # User notification settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_notification_settings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                email_enabled BOOLEAN DEFAULT TRUE,
                email_frequency VARCHAR(20) DEFAULT 'smart',
                email_delay_minutes INTEGER DEFAULT 10,
                in_app_enabled BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        ''')
        
        # Broadcast messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_broadcasts (
                id SERIAL PRIMARY KEY,
                sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255),
                content TEXT NOT NULL,
                target_type VARCHAR(20) DEFAULT 'all',
                target_tier_id INTEGER REFERENCES reseller_tiers(id),
                sent_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_broadcasts_sender ON chat_broadcasts(sender_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_broadcasts_created ON chat_broadcasts(created_at DESC)')
        
        # Pending email notifications table (for smart email scheduling)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_pending_emails (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                scheduled_at TIMESTAMP NOT NULL,
                sent_at TIMESTAMP,
                is_sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_pending_emails_scheduled ON chat_pending_emails(scheduled_at) WHERE is_sent = FALSE')
        
        # Push notification subscriptions table (PWA Web Push)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, endpoint)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id)')

        # Bot training examples table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_training_examples (
                id SERIAL PRIMARY KEY,
                question_pattern TEXT NOT NULL,
                answer_template TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bot_training_active ON bot_training_examples(is_active, sort_order)')

        # ==================== END CHAT SYSTEM ====================
        
        # Insert default sales channels
        default_channels = [
            ('ระบบออนไลน์', 'การสั่งซื้อผ่านระบบตะกร้าสินค้า', 1),
            ('LINE', 'ขายผ่าน LINE Official Account', 2),
            ('หน้าร้าน', 'ขายหน้าร้าน Walk-in', 3),
            ('Facebook', 'ขายผ่าน Facebook Page/Marketplace', 4),
            ('Lazada', 'ขายผ่าน Lazada', 5),
            ('Shopee', 'ขายผ่าน Shopee', 6),
            ('TikTok', 'ขายผ่าน TikTok Shop', 7)
        ]
        for channel in default_channels:
            cursor.execute('''
                INSERT INTO sales_channels (name, description, sort_order)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            ''', channel)
        
        # Insert default roles
        roles = ['Super Admin', 'Assistant Admin', 'Reseller']
        for role in roles:
            cursor.execute(
                'INSERT INTO roles (name) VALUES (%s) ON CONFLICT (name) DO NOTHING',
                (role,)
            )
        
        # Insert default reseller tiers with level_rank and is_manual_only
        tiers_data = [
            {'name': 'Bronze', 'level_rank': 1, 'is_manual_only': False, 'description': 'ระดับเริ่มต้น'},
            {'name': 'Silver', 'level_rank': 2, 'is_manual_only': False, 'description': 'ระดับกลาง'},
            {'name': 'Gold', 'level_rank': 3, 'is_manual_only': False, 'description': 'ระดับสูง'},
            {'name': 'Platinum', 'level_rank': 4, 'is_manual_only': True, 'description': 'ระดับสูงสุด (Manual เท่านั้น)'}
        ]
        for tier in tiers_data:
            cursor.execute('''
                INSERT INTO reseller_tiers (name, level_rank, is_manual_only, description) 
                VALUES (%s, %s, %s, %s) 
                ON CONFLICT (name) DO UPDATE SET 
                    level_rank = EXCLUDED.level_rank,
                    is_manual_only = EXCLUDED.is_manual_only,
                    description = EXCLUDED.description
            ''', (tier['name'], tier['level_rank'], tier['is_manual_only'], tier['description']))
        
        # Insert or update Super Admin user
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = %s', ('superadmin',))
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Hash password with bcrypt
            password_hash = bcrypt.hashpw('A0971exp11'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (full_name, username, password, role_id)
                VALUES (%s, %s, %s, (SELECT id FROM roles WHERE name = 'Super Admin'))
            ''', ('Super Admin', 'superadmin', password_hash))
        else:
            # Update existing Super Admin password with bcrypt
            password_hash = bcrypt.hashpw('A0971exp11'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                UPDATE users 
                SET password = %s, full_name = %s
                WHERE username = %s
            ''', (password_hash, 'Super Admin', 'superadmin'))
        
        # Migration: Add shipping/contact fields to users table for resellers
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'phone') THEN
                    ALTER TABLE users ADD COLUMN phone VARCHAR(50);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'email') THEN
                    ALTER TABLE users ADD COLUMN email VARCHAR(255);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'address') THEN
                    ALTER TABLE users ADD COLUMN address TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'province') THEN
                    ALTER TABLE users ADD COLUMN province VARCHAR(100);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'district') THEN
                    ALTER TABLE users ADD COLUMN district VARCHAR(100);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'subdistrict') THEN
                    ALTER TABLE users ADD COLUMN subdistrict VARCHAR(100);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'postal_code') THEN
                    ALTER TABLE users ADD COLUMN postal_code VARCHAR(10);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'brand_name') THEN
                    ALTER TABLE users ADD COLUMN brand_name VARCHAR(255);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'logo_url') THEN
                    ALTER TABLE users ADD COLUMN logo_url TEXT;
                END IF;
            END $$;
        ''')
        
        # Create warehouses table (warehouse/storage locations)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warehouses (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                address TEXT,
                province VARCHAR(50),
                district VARCHAR(50),
                subdistrict VARCHAR(50),
                postal_code VARCHAR(10),
                phone VARCHAR(20),
                contact_name VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create sku_warehouse_stock table (stock per SKU per warehouse)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sku_warehouse_stock (
                id SERIAL PRIMARY KEY,
                sku_id INTEGER NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
                stock INTEGER DEFAULT 0,
                UNIQUE(sku_id, warehouse_id)
            )
        ''')
        
        # Create order_shipments table (shipments grouped by warehouse per order)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_shipments (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                tracking_number VARCHAR(50),
                shipping_provider VARCHAR(50),
                status VARCHAR(20) DEFAULT 'pending',
                shipped_at TIMESTAMP,
                delivered_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create order_shipment_items table (items in each shipment)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_shipment_items (
                id SERIAL PRIMARY KEY,
                shipment_id INTEGER NOT NULL REFERENCES order_shipments(id) ON DELETE CASCADE,
                order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1
            )
        ''')
        
        # Insert default warehouse if none exists
        cursor.execute('SELECT COUNT(*) FROM warehouses')
        warehouse_count = cursor.fetchone()[0]
        if warehouse_count == 0:
            cursor.execute('''
                INSERT INTO warehouses (name, address, is_active)
                VALUES ('โกดังหลัก', 'โกดังเริ่มต้น', TRUE)
            ''')
        
        # Create reseller_customers table (customers of resellers for direct shipping)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_customers (
                id SERIAL PRIMARY KEY,
                reseller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                full_name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                email VARCHAR(255),
                address TEXT,
                province VARCHAR(100),
                district VARCHAR(100),
                subdistrict VARCHAR(100),
                postal_code VARCHAR(10),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create shipping_providers table (courier companies)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipping_providers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                logo_url VARCHAR(500),
                tracking_url VARCHAR(500),
                is_active BOOLEAN DEFAULT TRUE,
                display_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default shipping providers if none exist
        cursor.execute('SELECT COUNT(*) FROM shipping_providers')
        if cursor.fetchone()[0] == 0:
            default_providers = [
                ('Kerry Express', None, 'https://th.kerryexpress.com/th/track/', 1),
                ('Flash Express', None, 'https://flashexpress.com/fle/tracking?se=', 2),
                ('J&T Express', None, 'https://www.jtexpress.co.th/service/track', 3),
                ('Thailand Post', None, 'https://track.thailandpost.co.th/', 4),
                ('Shopee Express', None, None, 5),
                ('Lazada Express', None, None, 6),
                ('NinjaVan', None, 'https://www.ninjavan.co/th-th/tracking', 7),
                ('Best Express', None, 'https://www.best-inc.co.th/track', 8),
            ]
            for name, logo, tracking, order in default_providers:
                cursor.execute('''
                    INSERT INTO shipping_providers (name, logo_url, tracking_url, display_order)
                    VALUES (%s, %s, %s, %s)
                ''', (name, logo, tracking, order))
        
        # Create shipping_weight_rates table (shipping rates by weight range)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipping_weight_rates (
                id SERIAL PRIMARY KEY,
                min_weight INTEGER NOT NULL DEFAULT 0,
                max_weight INTEGER,
                rate DECIMAL(10,2) NOT NULL DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create shipping_promotions table (free shipping / discount promotions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipping_promotions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                promo_type VARCHAR(20) NOT NULL DEFAULT 'free_shipping',
                min_order_value DECIMAL(10,2) NOT NULL DEFAULT 0,
                discount_amount DECIMAL(10,2) DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default shipping weight rates if none exist
        cursor.execute('SELECT COUNT(*) FROM shipping_weight_rates')
        if cursor.fetchone()[0] == 0:
            default_rates = [
                (0, 500, 35, 1),
                (501, 1000, 50, 2),
                (1001, 2000, 70, 3),
                (2001, None, 90, 4)
            ]
            for min_w, max_w, rate, sort in default_rates:
                cursor.execute('''
                    INSERT INTO shipping_weight_rates (min_weight, max_weight, rate, sort_order)
                    VALUES (%s, %s, %s, %s)
                ''', (min_w, max_w, rate, sort))
        
        # Insert default shipping promotion if none exist
        cursor.execute('SELECT COUNT(*) FROM shipping_promotions')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO shipping_promotions (name, promo_type, min_order_value, is_active)
                VALUES ('ส่งฟรีเมื่อซื้อครบ 800 บาท', 'free_shipping', 800, TRUE)
            ''')
        
        # Create shipping_promotion_brands table (brand-specific promotions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipping_promotion_brands (
                id SERIAL PRIMARY KEY,
                promo_id INTEGER NOT NULL REFERENCES shipping_promotions(id) ON DELETE CASCADE,
                brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
                UNIQUE(promo_id, brand_id)
            )
        ''')
        
        # Create reseller_applications table (registration applications from public)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_applications (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                phone VARCHAR(50) NOT NULL,
                line_id VARCHAR(100),
                address TEXT,
                province VARCHAR(100),
                district VARCHAR(100),
                subdistrict VARCHAR(100),
                postal_code VARCHAR(10),
                notes TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP,
                reject_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add line_id column to users table if not exists
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'line_id') THEN
                    ALTER TABLE users ADD COLUMN line_id VARCHAR(100);
                END IF;
            END $$;
        ''')
        
        # Create activity_logs table for system-wide activity tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                user_name VARCHAR(255),
                action_type VARCHAR(50) NOT NULL,
                action_category VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                target_type VARCHAR(50),
                target_id INTEGER,
                target_name VARCHAR(255),
                ip_address VARCHAR(50),
                user_agent TEXT,
                extra_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster log queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON activity_logs(created_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_logs_action_category ON activity_logs(action_category)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id)
        ''')
        
        # ==========================================
        # Made-to-Order (สินค้าสั่งผลิต) System
        # ==========================================
        
        # Migration: Add product_type and production_days to products table
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'product_type') THEN
                    ALTER TABLE products ADD COLUMN product_type VARCHAR(20) DEFAULT 'ready_stock';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'production_days') THEN
                    ALTER TABLE products ADD COLUMN production_days INTEGER DEFAULT 0;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'deposit_percent') THEN
                    ALTER TABLE products ADD COLUMN deposit_percent INTEGER DEFAULT 50;
                END IF;
            END $$;
        ''')
        
        # Migration: Add min_order_qty to skus table (MOQ per color/variant)
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'skus' AND column_name = 'min_order_qty') THEN
                    ALTER TABLE skus ADD COLUMN min_order_qty INTEGER DEFAULT 1;
                END IF;
            END $$;
        ''')
        
        # Migration: Add min_order_qty to option_values table (MOQ per primary option value like color)
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'option_values' AND column_name = 'min_order_qty') THEN
                    ALTER TABLE option_values ADD COLUMN min_order_qty INTEGER DEFAULT 0;
                END IF;
            END $$;
        ''')
        
        # Create quotation_requests table (คำขอใบเสนอราคาจาก Reseller)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotation_requests (
                id SERIAL PRIMARY KEY,
                request_number VARCHAR(50) UNIQUE,
                reseller_id INTEGER NOT NULL REFERENCES users(id),
                status VARCHAR(30) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create quotation_request_items table (รายการสินค้าในคำขอ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotation_request_items (
                id SERIAL PRIMARY KEY,
                request_id INTEGER NOT NULL REFERENCES quotation_requests(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                sku_id INTEGER REFERENCES skus(id),
                sku_code VARCHAR(100),
                option_snapshot JSONB,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price DECIMAL(12,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create quotations table (ใบเสนอราคา)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotations (
                id SERIAL PRIMARY KEY,
                quote_number VARCHAR(50) UNIQUE,
                request_id INTEGER REFERENCES quotation_requests(id),
                reseller_id INTEGER NOT NULL REFERENCES users(id),
                admin_id INTEGER REFERENCES users(id),
                status VARCHAR(30) DEFAULT 'draft',
                subtotal DECIMAL(12,2) DEFAULT 0,
                discount_amount DECIMAL(12,2) DEFAULT 0,
                total_amount DECIMAL(12,2) DEFAULT 0,
                deposit_percent INTEGER DEFAULT 50,
                deposit_amount DECIMAL(12,2) DEFAULT 0,
                balance_amount DECIMAL(12,2) DEFAULT 0,
                production_days INTEGER DEFAULT 0,
                expected_completion_date DATE,
                valid_until DATE,
                payment_instructions TEXT,
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                accepted_at TIMESTAMP,
                rejected_at TIMESTAMP
            )
        ''')
        
        # Create quotation_items table (รายการในใบเสนอราคา)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotation_items (
                id SERIAL PRIMARY KEY,
                quotation_id INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                sku_id INTEGER REFERENCES skus(id),
                sku_code VARCHAR(100),
                product_name VARCHAR(255),
                option_text VARCHAR(255),
                quantity INTEGER NOT NULL DEFAULT 1,
                original_price DECIMAL(12,2),
                final_price DECIMAL(12,2),
                line_total DECIMAL(12,2),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create mto_orders table (คำสั่งซื้อสินค้าสั่งผลิต - หลังชำระมัดจำ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mto_orders (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) UNIQUE,
                quotation_id INTEGER REFERENCES quotations(id),
                reseller_id INTEGER NOT NULL REFERENCES users(id),
                status VARCHAR(30) DEFAULT 'awaiting_deposit',
                total_amount DECIMAL(12,2) DEFAULT 0,
                deposit_amount DECIMAL(12,2) DEFAULT 0,
                deposit_paid DECIMAL(12,2) DEFAULT 0,
                balance_amount DECIMAL(12,2) DEFAULT 0,
                balance_paid DECIMAL(12,2) DEFAULT 0,
                production_days INTEGER DEFAULT 0,
                payment_confirmed_at TIMESTAMP,
                expected_completion_date DATE,
                production_started_at TIMESTAMP,
                production_completed_at TIMESTAMP,
                balance_requested_at TIMESTAMP,
                balance_paid_at TIMESTAMP,
                shipped_at TIMESTAMP,
                tracking_number VARCHAR(100),
                shipping_provider VARCHAR(100),
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create mto_order_items table (รายการในคำสั่งซื้อสินค้าสั่งผลิต)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mto_order_items (
                id SERIAL PRIMARY KEY,
                mto_order_id INTEGER NOT NULL REFERENCES mto_orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                sku_id INTEGER REFERENCES skus(id),
                sku_code VARCHAR(100),
                product_name VARCHAR(255),
                option_text VARCHAR(255),
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price DECIMAL(12,2),
                line_total DECIMAL(12,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create mto_payments table (บันทึกการชำระเงินสินค้าสั่งผลิต)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mto_payments (
                id SERIAL PRIMARY KEY,
                mto_order_id INTEGER NOT NULL REFERENCES mto_orders(id) ON DELETE CASCADE,
                payment_type VARCHAR(20) NOT NULL,
                amount DECIMAL(12,2) NOT NULL,
                payment_method VARCHAR(50),
                transaction_ref VARCHAR(100),
                slip_image_url TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                confirmed_by INTEGER REFERENCES users(id),
                confirmed_at TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for MTO tables
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotation_requests_reseller ON quotation_requests(reseller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotation_requests_status ON quotation_requests(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotations_reseller ON quotations(reseller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotations_status ON quotations(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mto_orders_reseller ON mto_orders(reseller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mto_orders_status ON mto_orders(status)')

        # Agent Action Logs — บันทึกการกระทำของ AI Agent
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_action_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER REFERENCES users(id),
                admin_name VARCHAR(255),
                command_text TEXT NOT NULL,
                tool_name VARCHAR(80),
                context_page VARCHAR(80),
                plan_data JSONB,
                before_data JSONB,
                after_data JSONB,
                status VARCHAR(20) DEFAULT 'pending',
                executed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Agent Settings — บุคลิกและการตั้งค่า AI Agent
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_settings (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(100) DEFAULT 'น้องเอก',
                tone VARCHAR(20) DEFAULT 'friendly',
                ending_particle VARCHAR(10) DEFAULT 'ครับ',
                custom_prompt TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT INTO agent_settings (id, agent_name, tone, ending_particle, custom_prompt)
            VALUES (1, 'น้องเอก', 'friendly', 'ครับ', '')
            ON CONFLICT (id) DO NOTHING
        ''')

        # Agent Feedback — บันทึก feedback จาก Admin
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_feedback (
                id SERIAL PRIMARY KEY,
                command_text TEXT,
                response_text TEXT,
                rating INTEGER,
                correction TEXT,
                context_page VARCHAR(80),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Enable pg_trgm for similarity search
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

        # Guest chat log for tracking public catalog bot questions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guest_chat_log (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL,
                normalized_q TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_chat_log_norm ON guest_chat_log USING gin(normalized_q gin_trgm_ops)"
        )

        # Guest leads from catalog chat bot
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guest_leads (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(30),
                name VARCHAR(100),
                interest_text TEXT,
                conversation_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_guest_leads_created ON guest_leads(created_at DESC)")

        # Restock alerts — capture customer interest when desired size is out of stock
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restock_alerts (
                id SERIAL PRIMARY KEY,
                product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
                sku_id INTEGER,
                size VARCHAR(50),
                product_name TEXT,
                user_id INTEGER,
                session_id VARCHAR(200),
                phone VARCHAR(30),
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified_at TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_restock_alerts_status ON restock_alerts(status, product_id)")

        # Guest catalog bot full conversation log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guest_chat_sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(200) UNIQUE NOT NULL,
                ip VARCHAR(60),
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                msg_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gcs_last_seen ON guest_chat_sessions(last_seen DESC)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guest_chat_messages (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(200) NOT NULL,
                user_msg TEXT,
                bot_reply TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gcm_session ON guest_chat_messages(session_id, created_at)")

        # Migration: Add Meta Marketing API credentials to facebook_pixel_settings
        cursor.execute("""
            ALTER TABLE facebook_pixel_settings
            ADD COLUMN IF NOT EXISTS meta_access_token TEXT,
            ADD COLUMN IF NOT EXISTS meta_ad_account_id VARCHAR(100)
        """)

        # Create size_chart_groups table (reusable size chart templates)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS size_chart_groups (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                columns JSONB NOT NULL DEFAULT '["ขนาด","รอบอก","รอบเอว","ความยาว"]',
                rows JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: Add size_chart_group_id to products table
        cursor.execute("""
            ALTER TABLE products
            ADD COLUMN IF NOT EXISTS size_chart_group_id INTEGER REFERENCES size_chart_groups(id) ON DELETE SET NULL
        """)

        conn.commit()
        print("✅ Database initialized successfully with Neon PostgreSQL!")
        
        # Release advisory lock
        cursor.execute("SELECT pg_advisory_unlock(12345)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing database: {e}")
        # Make sure to release lock on error too
        try:
            cursor.execute("SELECT pg_advisory_unlock(12345)")
        except:
            pass
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    init_db()
