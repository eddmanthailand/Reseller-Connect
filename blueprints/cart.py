from flask import Blueprint, request, jsonify, session
from database import get_db
from utils import login_required, admin_required, handle_error
from blueprints.mail_utils import send_order_status_chat
import psycopg2.extras
import psycopg2
import json, os

cart_bp = Blueprint('cart', __name__)

# ==================== SHOPPING CART API ====================

def get_or_create_cart(user_id, cursor):
    """Get active cart for user or create one"""
    cursor.execute('''
        SELECT id FROM carts WHERE user_id = %s AND status = 'active'
    ''', (user_id,))
    cart = cursor.fetchone()
    
    if cart:
        return cart['id'] if isinstance(cart, dict) else cart[0]
    
    # Create new cart
    cursor.execute('''
        INSERT INTO carts (user_id, status) VALUES (%s, 'active')
        RETURNING id
    ''', (user_id,))
    return cursor.fetchone()[0]

@cart_bp.route('/api/cart', methods=['GET'])
@login_required
def get_cart():
    """Get current user's cart with items"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get or create cart
        cart_id = get_or_create_cart(user_id, cursor)
        conn.commit()
        
        # Get cart items with product info
        cursor.execute('''
            SELECT ci.id, ci.sku_id, ci.quantity, ci.unit_price, ci.tier_discount_percent,
                   ci.customization_data, ci.created_at,
                   s.sku_code, s.price as current_price, s.stock,
                   p.id as product_id, p.name as product_name, p.parent_sku, p.brand_id, p.weight,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM cart_items ci
            JOIN skus s ON s.id = ci.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE ci.cart_id = %s
            ORDER BY ci.created_at DESC
        ''', (cart_id,))
        
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            # Calculate discounted price
            unit_price = float(item['unit_price'] or 0)
            discount_pct = float(item['tier_discount_percent'] or 0)
            discounted_price = unit_price * (1 - discount_pct / 100)
            quantity = item['quantity']
            
            item['discounted_price'] = round(discounted_price, 2)
            item['subtotal'] = round(discounted_price * quantity, 2)
            item['unit_price'] = float(item['unit_price']) if item['unit_price'] else 0
            item['current_price'] = float(item['current_price']) if item['current_price'] else 0
            items.append(item)
        
        # Calculate totals
        total_amount = sum(float(item['unit_price']) * item['quantity'] for item in items)
        total_discount = sum((float(item['unit_price']) - item['discounted_price']) * item['quantity'] for item in items)
        final_amount = total_amount - total_discount
        
        return jsonify({
            'cart_id': cart_id,
            'items': items,
            'item_count': len(items),
            'total_quantity': sum(item['quantity'] for item in items),
            'total_amount': round(total_amount, 2),
            'total_discount': round(total_discount, 2),
            'final_amount': round(final_amount, 2)
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@cart_bp.route('/api/cart/items', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        sku_id = data.get('sku_id')
        quantity = data.get('quantity', 1)
        customization_data = data.get('customization_data')
        
        if not sku_id:
            return jsonify({'error': 'SKU ID is required'}), 400
        
        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get SKU info
        cursor.execute('''
            SELECT s.id, s.price, s.stock, p.id as product_id
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = %s AND p.status = 'active'
        ''', (sku_id,))
        sku = cursor.fetchone()
        
        if not sku:
            return jsonify({'error': 'Product not found or not available'}), 404
        
        if sku['stock'] < quantity:
            return jsonify({'error': f'Not enough stock. Available: {sku["stock"]}'}), 400
        
        # Get user's tier discount for this product
        cursor.execute('''
            SELECT ptp.discount_percent
            FROM users u
            JOIN product_tier_pricing ptp ON ptp.tier_id = u.reseller_tier_id
            WHERE u.id = %s AND ptp.product_id = %s
        ''', (user_id, sku['product_id']))
        tier_pricing = cursor.fetchone()
        discount_percent = float(tier_pricing['discount_percent']) if tier_pricing else 0
        
        # Get or create cart
        cart_id = get_or_create_cart(user_id, cursor)
        
        # Check if item already in cart
        cursor.execute('''
            SELECT id, quantity FROM cart_items
            WHERE cart_id = %s AND sku_id = %s
        ''', (cart_id, sku_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update quantity
            new_quantity = existing['quantity'] + quantity
            if new_quantity > sku['stock']:
                return jsonify({'error': f'Total quantity exceeds stock. Available: {sku["stock"]}'}), 400
            
            cursor.execute('''
                UPDATE cart_items
                SET quantity = %s, unit_price = %s, tier_discount_percent = %s,
                    customization_data = COALESCE(%s, customization_data), updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id
            ''', (new_quantity, sku['price'], discount_percent, 
                  json.dumps(customization_data) if customization_data else None,
                  existing['id']))
        else:
            # Insert new item
            cursor.execute('''
                INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent, customization_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (cart_id, sku_id, quantity, sku['price'], discount_percent,
                  json.dumps(customization_data) if customization_data else None))
        
        conn.commit()
        
        return jsonify({'message': 'Added to cart successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@cart_bp.route('/api/cart/migrate-guest', methods=['POST'])
@login_required
def migrate_guest_cart():
    """Migrate guest localStorage cart items into the logged-in member's server-side cart."""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json() or {}
        items = data.get('items') or []
        if not items:
            return jsonify({'migrated': 0}), 200

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cart_id = get_or_create_cart(user_id, cursor)

        migrated = 0
        for item in items:
            try:
                sku_id = int(item.get('skuId') or item.get('sku_id') or 0)
                quantity = max(1, int(item.get('qty') or item.get('quantity') or 1))
                if not sku_id:
                    continue

                cursor.execute('''
                    SELECT s.id, s.price, s.stock, p.id as product_id
                    FROM skus s JOIN products p ON p.id = s.product_id
                    WHERE s.id = %s AND p.status = 'active'
                ''', (sku_id,))
                sku = cursor.fetchone()
                if not sku:
                    continue

                cursor.execute('''
                    SELECT ptp.discount_percent
                    FROM users u
                    JOIN product_tier_pricing ptp ON ptp.tier_id = u.reseller_tier_id
                    WHERE u.id = %s AND ptp.product_id = %s
                ''', (user_id, sku['product_id']))
                tier_pricing = cursor.fetchone()
                discount_percent = float(tier_pricing['discount_percent']) if tier_pricing else 0

                cursor.execute('''
                    SELECT id, quantity FROM cart_items
                    WHERE cart_id = %s AND sku_id = %s
                ''', (cart_id, sku_id))
                existing = cursor.fetchone()

                if existing:
                    new_qty = min(existing['quantity'] + quantity, int(sku['stock']))
                    cursor.execute('''
                        UPDATE cart_items SET quantity = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (new_qty, existing['id']))
                else:
                    qty_to_add = min(quantity, int(sku['stock']))
                    if qty_to_add < 1:
                        continue
                    cursor.execute('''
                        INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (cart_id, sku_id, qty_to_add, sku['price'], discount_percent))
                migrated += 1
            except Exception:
                continue

        conn.commit()
        return jsonify({'migrated': migrated}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@cart_bp.route('/api/cart/items/<int:item_id>', methods=['PATCH'])
@login_required
def update_cart_item(item_id):
    """Update cart item quantity"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        quantity = data.get('quantity', 1)
        
        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify item belongs to user's cart
        cursor.execute('''
            SELECT ci.id, ci.sku_id, s.stock
            FROM cart_items ci
            JOIN carts c ON c.id = ci.cart_id
            JOIN skus s ON s.id = ci.sku_id
            WHERE ci.id = %s AND c.user_id = %s AND c.status = 'active'
        ''', (item_id, user_id))
        item = cursor.fetchone()
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        if quantity > item['stock']:
            return jsonify({'error': f'Not enough stock. Available: {item["stock"]}'}), 400
        
        cursor.execute('''
            UPDATE cart_items
            SET quantity = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (quantity, item_id))
        
        conn.commit()
        return jsonify({'message': 'Cart updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@cart_bp.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
@login_required
def remove_cart_item(item_id):
    """Remove item from cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verify and delete
        cursor.execute('''
            DELETE FROM cart_items
            WHERE id = %s AND cart_id IN (
                SELECT id FROM carts WHERE user_id = %s AND status = 'active'
            )
            RETURNING id
        ''', (item_id, user_id))
        
        if cursor.fetchone() is None:
            return jsonify({'error': 'Item not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Item removed from cart'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@cart_bp.route('/api/cart/clear', methods=['DELETE'])
@login_required
def clear_cart():
    """Clear all items from cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM cart_items
            WHERE cart_id IN (
                SELECT id FROM carts WHERE user_id = %s AND status = 'active'
            )
        ''', (user_id,))
        
        conn.commit()
        return jsonify({'message': 'Cart cleared'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

