import psycopg2
import psycopg2.extras
import hashlib
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
            password_hash = hashlib.sha256('A0971exp11'.encode()).hexdigest()
            cursor.execute('''
                INSERT INTO users (full_name, username, password, role_id)
                VALUES (%s, %s, %s, (SELECT id FROM roles WHERE name = 'Super Admin'))
            ''', ('Super Admin', 'superadmin', password_hash))
        else:
            # Update existing Super Admin password
            password_hash = hashlib.sha256('A0971exp11'.encode()).hexdigest()
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
