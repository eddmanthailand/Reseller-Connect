"""
[Database Migration] Unified Marketing Module v2
- promotions (auto-promotions: %, fixed, GWP)
- coupons + user_coupons (wallet)
- Alters: products, cart_items, orders, mto_orders
"""
import logging
import psycopg2
from database import get_db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_marketing_migration():
    conn = get_db()
    cursor = conn.cursor()
    try:
        logging.info("Starting Marketing Module Migration...")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promotions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                promo_type VARCHAR(50) NOT NULL,
                condition_min_spend DECIMAL(10,2) DEFAULT 0,
                condition_min_qty INT DEFAULT 0,
                reward_type VARCHAR(50) NOT NULL,
                reward_value DECIMAL(10,2) DEFAULT 0,
                reward_sku_id INT REFERENCES skus(id) ON DELETE SET NULL,
                reward_qty INT DEFAULT 1,
                target_brand_id INT REFERENCES brands(id) ON DELETE SET NULL,
                target_category_id INT REFERENCES categories(id) ON DELETE SET NULL,
                min_tier_id INT REFERENCES reseller_tiers(id) ON DELETE SET NULL,
                is_stackable BOOLEAN DEFAULT FALSE,
                priority INT DEFAULT 0,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logging.info("Table 'promotions' verified.")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS coupons (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                discount_type VARCHAR(50) NOT NULL,
                discount_value DECIMAL(10,2) NOT NULL,
                max_discount DECIMAL(10,2) DEFAULT 0,
                min_spend DECIMAL(10,2) DEFAULT 0,
                total_quota INT DEFAULT 0,
                usage_count INT DEFAULT 0,
                per_user_limit INT DEFAULT 1,
                target_type VARCHAR(50) DEFAULT 'all',
                min_tier_id INT REFERENCES reseller_tiers(id) ON DELETE SET NULL,
                is_stackable BOOLEAN DEFAULT FALSE,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logging.info("Table 'coupons' verified.")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_coupons (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                coupon_id INT REFERENCES coupons(id) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'ready',
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP,
                used_in_order_id INT REFERENCES orders(id) ON DELETE SET NULL,
                UNIQUE(user_id, coupon_id)
            )
        ''')
        logging.info("Table 'user_coupons' verified.")

        cursor.execute('''
            ALTER TABLE products
            ADD COLUMN IF NOT EXISTS is_free_gift BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS gift_condition_desc VARCHAR(255)
        ''')
        logging.info("Table 'products' altered.")

        cursor.execute('''
            ALTER TABLE cart_items
            ADD COLUMN IF NOT EXISTS is_free_gift BOOLEAN DEFAULT FALSE
        ''')
        logging.info("Table 'cart_items' altered.")

        cursor.execute('''
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS coupon_id INT REFERENCES coupons(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS coupon_discount DECIMAL(10,2) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS promotion_id INT REFERENCES promotions(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS promotion_discount DECIMAL(10,2) DEFAULT 0
        ''')
        logging.info("Table 'orders' altered.")

        cursor.execute('''
            ALTER TABLE mto_orders
            ADD COLUMN IF NOT EXISTS coupon_id INT REFERENCES coupons(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS coupon_discount DECIMAL(10,2) DEFAULT 0
        ''')
        logging.info("Table 'mto_orders' altered.")

        conn.commit()
        logging.info("Marketing Module Migration completed successfully!")
        return True

    except Exception as e:
        conn.rollback()
        logging.error(f"Migration Error: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = run_marketing_migration()
    exit(0 if success else 1)
