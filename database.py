import psycopg2
import psycopg2.extras
import bcrypt
import os
from datetime import datetime

def get_db_url():
    """Get database URL from environment"""
    return os.environ.get('DATABASE_URL')

def get_db():
    """Get database connection"""
    db_url = get_db_url()
    if not db_url:
        raise Exception("DATABASE_URL environment variable not set")
    conn = psycopg2.connect(db_url)
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
