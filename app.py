from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import psycopg2.extras
import hashlib
from database import get_db, init_db
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')
CORS(app)

# Initialize database on startup
init_db()

@app.route('/')
def index():
    """Render the admin user management page"""
    return render_template('admin_user_management.html')

@app.route('/api/roles', methods=['GET'])
def get_roles():
    """Get all available roles"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('SELECT id, name FROM roles')
    roles = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(roles)

@app.route('/api/reseller-tiers', methods=['GET'])
def get_reseller_tiers():
    """Get all reseller tiers"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('SELECT id, name FROM reseller_tiers')
    tiers = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(tiers)

@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users with their role information"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('''
        SELECT 
            u.id,
            u.full_name,
            u.username,
            r.name as role,
            rt.name as reseller_tier
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
        ORDER BY u.created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user"""
    data = request.json
    
    # Validate required fields
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['full_name', 'username', 'password', 'role_id']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Hash password
    password_hash = hashlib.sha256(data['password'].encode()).hexdigest()
    
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if username already exists
        cursor.execute('SELECT id FROM users WHERE username = %s', (data['username'],))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Username already exists'}), 400
        
        # Insert new user
        reseller_tier_id = data.get('reseller_tier_id') if data.get('reseller_tier_id') else None
        
        cursor.execute('''
            INSERT INTO users (full_name, username, password, role_id, reseller_tier_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['full_name'], data['username'], password_hash, data['role_id'], reseller_tier_id))
        
        result = cursor.fetchone()
        user_id = result['id']
        
        # Get the created user with role information
        cursor.execute('''
            SELECT 
                u.id,
                u.full_name,
                u.username,
                r.name as role,
                rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.id = %s
        ''', (user_id,))
        
        user = dict(cursor.fetchone())
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'User created successfully',
            'user': user
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user"""
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
