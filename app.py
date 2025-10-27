from flask import Flask, render_template, request, jsonify, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
import uuid

app = Flask(__name__)
app.secret_key = 'your_super_secure_secret_key_change_this_in_production'

# MySQL configurations
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Rudransh@2005'  # ← ADD YOUR PASSWORD!
app.config['MYSQL_DB'] = 'ecommerce'

mysql = MySQL(app)

# Home route
@app.route('/')
def index():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM Product')
    products = cursor.fetchall()
    cursor.execute('SELECT * FROM Category')
    categories = cursor.fetchall()
    cursor.close()
    return render_template('index.html', section='home', products=products, categories=categories)

# Product details route
@app.route('/product/<int:product_id>')
def product(product_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM Product WHERE product_id = %s', (product_id,))
    product = cursor.fetchone()
    
    if product:
        cursor.execute('''
            SELECT r.*, c.name 
            FROM Review r 
            JOIN Customer c ON r.customer_id = c.customer_id 
            WHERE r.product_id = %s 
            ORDER BY r.created_at DESC
        ''', (product_id,))
        reviews = cursor.fetchall()
    else:
        reviews = []
    
    cursor.close()
    return render_template('index.html', section='product', product=product, reviews=reviews)

# GUEST CART - NO LOGIN REQUIRED
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    # Create guest session ID
    if 'guest_session' not in session:
        session['guest_session'] = str(uuid.uuid4())[:16]
    
    cursor = mysql.connection.cursor()
    try:
        # Check if item exists in guest cart
        cursor.execute('''
            SELECT * FROM GuestCart WHERE session_id = %s AND product_id = %s
        ''', (session['guest_session'], product_id))
        cart_item = cursor.fetchone()
        
        if cart_item:
            # Update quantity
            cursor.execute('''
                UPDATE GuestCart SET quantity = quantity + 1 
                WHERE session_id = %s AND product_id = %s
            ''', (session['guest_session'], product_id))
        else:
            # Insert new item
            cursor.execute('''
                INSERT INTO GuestCart (session_id, product_id, quantity) 
                VALUES (%s, %s, 1)
            ''', (session['guest_session'], product_id))
        
        mysql.connection.commit()
        cursor.close()
        return jsonify({'message': 'Added to cart!', 'status': 'success'})
    except Exception as e:
        cursor.close()
        return jsonify({'message': 'Error adding to cart.', 'status': 'danger'})

# REMOVE FROM CART - NEW ROUTE
@app.route('/remove_from_cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'guest_session' not in session:
        return jsonify({'message': 'Cart is empty.', 'status': 'danger'})
    
    cursor = mysql.connection.cursor()
    try:
        # Delete item from guest cart
        cursor.execute('''
            DELETE FROM GuestCart WHERE session_id = %s AND product_id = %s
        ''', (session['guest_session'], product_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({'message': 'Item not found in cart.', 'status': 'danger'})
        
        mysql.connection.commit()
        cursor.close()
        return jsonify({'message': 'Item removed from cart!', 'status': 'success'})
    except Exception as e:
        cursor.close()
        return jsonify({'message': 'Error removing from cart.', 'status': 'danger'})

# GUEST CART VIEW - NO LOGIN REQUIRED
@app.route('/cart')
def cart():
    if 'guest_session' not in session:
        return render_template('index.html', section='cart', cart_items=[], total=0)
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT gc.quantity, p.product_name AS name, p.price, (gc.quantity * p.price) AS item_total, p.product_id
        FROM GuestCart gc
        JOIN Product p ON gc.product_id = p.product_id
        WHERE gc.session_id = %s
    ''', (session['guest_session'],))
    cart_items = cursor.fetchall()
    
    total = sum(item['item_total'] for item in cart_items) if cart_items else 0
    cursor.close()
    return render_template('index.html', section='cart', cart_items=cart_items, total=total)

# GUEST ORDER - NO LOGIN REQUIRED
@app.route('/place_order', methods=['POST'])
def place_order():
    if 'guest_session' not in session:
        return jsonify({'message': 'Cart is empty.', 'status': 'danger'})
    
    data = request.get_json()
    shipping_address = data.get('shipping_address')
    
    cursor = mysql.connection.cursor()
    try:
        # Get cart items
        cursor.execute('''
            SELECT gc.quantity, p.product_id, p.product_name, p.price
            FROM GuestCart gc 
            JOIN Product p ON gc.product_id = p.product_id
            WHERE gc.session_id = %s
        ''', (session['guest_session'],))
        cart_items = cursor.fetchall()
        
        if not cart_items:
            return jsonify({'message': 'Cart is empty.', 'status': 'danger'})
        
        total = sum(item[0] * item[3] for item in cart_items)
        
        # Create guest order (no customer_id required)
        cursor.execute('''
            INSERT INTO GuestOrders (session_id, total_amount, shipping_address, status)
            VALUES (%s, %s, %s, 'Pending')
        ''', (session['guest_session'], total, shipping_address))
        order_id = cursor.lastrowid
        
        # Create order items
        for item in cart_items:
            cursor.execute('''
                INSERT INTO GuestOrderItem (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
            ''', (order_id, item[1], item[0], item[3]))
        
        # Clear guest cart
        cursor.execute('DELETE FROM GuestCart WHERE session_id = %s', (session['guest_session'],))
        
        mysql.connection.commit()
        cursor.close()
        return jsonify({'message': 'Order placed successfully!', 'status': 'success', 'order_id': order_id})
    except Exception as e:
        mysql.connection.rollback()
        cursor.close()
        return jsonify({'message': 'Error placing order.', 'status': 'danger'})

# Order details (for guest orders)
@app.route('/order/<int:order_id>')
def order(order_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get guest order
    cursor.execute('''
        SELECT * FROM GuestOrders WHERE order_id = %s
    ''', (order_id,))
    order = cursor.fetchone()
    
    if order:
        # Get order items
        cursor.execute('''
            SELECT oi.*, p.product_name
            FROM GuestOrderItem oi
            JOIN Product p ON oi.product_id = p.product_id
            WHERE oi.order_id = %s
        ''', (order_id,))
        order_items = cursor.fetchall()
    else:
        order = None
        order_items = []
    
    cursor.close()
    return render_template('index.html', section='order', order=order, order_items=order_items)

if __name__ == '__main__':
    app.run(debug=True)