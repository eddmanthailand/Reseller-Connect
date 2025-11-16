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
        
        # Insert default roles
        roles = ['Super Admin', 'Assistant Admin', 'Reseller']
        for role in roles:
            cursor.execute(
                'INSERT INTO roles (name) VALUES (%s) ON CONFLICT (name) DO NOTHING',
                (role,)
            )
        
        # Insert default reseller tiers
        tiers = ['Bronze', 'Silver']
        for tier in tiers:
            cursor.execute(
                'INSERT INTO reseller_tiers (name) VALUES (%s) ON CONFLICT (name) DO NOTHING',
                (tier,)
            )
        
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
        
        conn.commit()
        print("✅ Database initialized successfully with Neon PostgreSQL!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing database: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    init_db()
