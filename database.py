import sqlite3
import hashlib
from datetime import datetime

DATABASE = 'users.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with tables and default data"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create roles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create reseller_tiers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reseller_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
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
        cursor.execute('INSERT OR IGNORE INTO roles (name) VALUES (?)', (role,))
    
    # Insert default reseller tiers
    tiers = ['Bronze', 'Silver']
    for tier in tiers:
        cursor.execute('INSERT OR IGNORE INTO reseller_tiers (name) VALUES (?)', (tier,))
    
    # Insert default admin user if not exists
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE username = ?', ('admin@system.com',))
    if cursor.fetchone()['count'] == 0:
        password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        cursor.execute('''
            INSERT INTO users (full_name, username, password, role_id)
            VALUES (?, ?, ?, (SELECT id FROM roles WHERE name = 'Super Admin'))
        ''', ('Admin หลัก', 'admin@system.com', password_hash))
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()
