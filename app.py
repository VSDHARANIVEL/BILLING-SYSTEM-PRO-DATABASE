"""
BillPro - Billing System Backend
==================================
Run:   python app.py
Open:  http://localhost:5000

Supervisor: username=admin  password=admin123
"""

from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import sqlite3, os, hashlib, secrets
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
app  = Flask(__name__, static_folder=os.path.join(BASE, 'static'))
app.secret_key = "billpro_secret_2024_xk9m"
CORS(app, supports_credentials=True)
DB   = os.path.join(BASE, 'billpro.db')


# ─── DB HELPERS ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def qone(sql, params=()):
    conn = get_db()
    row  = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None

def qall(sql, params=()):
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def run_sql(sql, params=()):
    conn = get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()

def hash_pw(pw):
    return hashlib.sha256(pw.strip().encode()).hexdigest()


# ─── INIT DATABASE ────────────────────────────────────────────────────────────

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            code    TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            price   REAL NOT NULL DEFAULT 0,
            stock   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS workers (
            number  TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            created TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bills (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_date      TEXT DEFAULT CURRENT_TIMESTAMP,
            customer_name  TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            customer_email TEXT DEFAULT '',
            customer_addr  TEXT DEFAULT '',
            worker_number  TEXT DEFAULT '',
            worker_name    TEXT DEFAULT '',
            total_amount   REAL DEFAULT 0,
            total_pieces   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bill_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id       INTEGER NOT NULL,
            product_code  TEXT,
            product_name  TEXT,
            price         REAL,
            quantity      INTEGER,
            subtotal      REAL,
            FOREIGN KEY(bill_id) REFERENCES bills(id)
        );

        CREATE TABLE IF NOT EXISTS adjustments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_number TEXT NOT NULL,
            pieces        INTEGER NOT NULL,
            note          TEXT DEFAULT '',
            created       TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS supervisor (
            id       INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)
    # Default supervisor
    if not qone("SELECT id FROM supervisor LIMIT 1"):
        conn.execute("INSERT INTO supervisor (username,password) VALUES (?,?)",
                     ('admin', hash_pw('admin123')))
    conn.commit()
    conn.close()

init_db()


# ─── AUTH DECORATOR ───────────────────────────────────────────────────────────

def need_supervisor(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('is_supervisor'):
            return jsonify({'error': 'Supervisor login required'}), 401
        return fn(*a, **kw)
    return wrapper


# ─── SERVE FRONTEND ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(BASE, 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(BASE, 'static'), filename)


# ─── SUPERVISOR ───────────────────────────────────────────────────────────────

@app.route('/api/supervisor/login', methods=['POST'])
def sup_login():
    d = request.get_json(force=True) or {}
    u = (d.get('username') or '').strip()
    p = (d.get('password') or '').strip()
    if not u or not p:
        return jsonify({'error': 'Username and password required'}), 400
    row = qone("SELECT * FROM supervisor WHERE username=? AND password=?", (u, hash_pw(p)))
    if row:
        session['is_supervisor'] = True
        session['sup_user']      = u
        return jsonify({'ok': True, 'username': u})
    return jsonify({'error': 'Wrong username or password'}), 401

@app.route('/api/supervisor/logout', methods=['POST'])
def sup_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/supervisor/status', methods=['GET'])
def sup_status():
    return jsonify({
        'logged_in': bool(session.get('is_supervisor')),
        'username':  session.get('sup_user', '')
    })


# ─── PRODUCTS ─────────────────────────────────────────────────────────────────

@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify(qall("SELECT * FROM products ORDER BY code"))

@app.route('/api/products/<code>', methods=['GET'])
def get_product(code):
    p = qone("SELECT * FROM products WHERE code=?", (code.strip(),))
    if p:
        return jsonify(p)
    return jsonify({'error': 'Product not found'}), 404

@app.route('/api/products', methods=['POST'])
def add_product():
    d     = request.get_json(force=True) or {}
    code  = str(d.get('code',  '')).strip()
    name  = str(d.get('name',  '')).strip()
    price = d.get('price',  None)
    stock = d.get('stock',  None)

    if len(code) != 3 or not code.isdigit():
        return jsonify({'error': 'Product code must be exactly 3 digits'}), 400
    if not name:
        return jsonify({'error': 'Product name is required'}), 400
    try:
        price = float(price)
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid price number'}), 400
    try:
        stock = int(stock)
        if stock < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid stock quantity (0 or more)'}), 400

    if qone("SELECT code FROM products WHERE code=?", (code,)):
        return jsonify({'error': f'Product code {code} already exists'}), 400

    conn = get_db()
    conn.execute("INSERT INTO products (code,name,price,stock) VALUES (?,?,?,?)",
                 (code, name, price, stock))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'message': f'Product "{name}" added'})

@app.route('/api/products/<code>', methods=['DELETE'])
def del_product(code):
    run_sql("DELETE FROM products WHERE code=?", (code,))
    return jsonify({'ok': True})


# ─── WORKERS ──────────────────────────────────────────────────────────────────

@app.route('/api/workers', methods=['GET'])
def get_workers():
    return jsonify(qall("SELECT * FROM workers ORDER BY number"))

@app.route('/api/workers/<number>', methods=['GET'])
def get_worker(number):
    w = qone("SELECT * FROM workers WHERE number=?", (number.strip(),))
    if w:
        return jsonify(w)
    return jsonify({'error': f'Worker {number} not found'}), 404

@app.route('/api/workers', methods=['POST'])
def add_worker():
    d    = request.get_json(force=True) or {}
    num  = str(d.get('number', '')).strip()
    name = str(d.get('name',   '')).strip()
    if not num:
        return jsonify({'error': 'Worker number is required'}), 400
    if not name:
        return jsonify({'error': 'Worker name is required'}), 400
    if qone("SELECT number FROM workers WHERE number=?", (num,)):
        return jsonify({'error': f'Worker number {num} already exists'}), 400
    conn = get_db()
    conn.execute("INSERT INTO workers (number,name) VALUES (?,?)", (num, name))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'message': f'Worker "{name}" added'})

@app.route('/api/workers/<number>', methods=['DELETE'])
def del_worker(number):
    run_sql("DELETE FROM workers WHERE number=?", (number,))
    return jsonify({'ok': True})


# ─── BILLS ────────────────────────────────────────────────────────────────────

@app.route('/api/bills/next-id', methods=['GET'])
def next_bill_id():
    row = qone("SELECT COALESCE(MAX(id),0) AS m FROM bills")
    return jsonify({'next_id': row['m'] + 1})

@app.route('/api/bills', methods=['POST'])
def create_bill():
    d      = request.get_json(force=True) or {}
    cname  = str(d.get('customer_name',  '')).strip()
    cphone = str(d.get('customer_phone', '')).strip()
    cemail = str(d.get('customer_email', '')).strip()
    caddr  = str(d.get('customer_addr',  '')).strip()
    wnum   = str(d.get('worker_number',  '')).strip()
    wname  = str(d.get('worker_name',    '')).strip()
    items  = d.get('items', [])

    if not cname:
        return jsonify({'error': 'Customer name is required'}), 400
    if not cphone or len(cphone) != 10 or not cphone.isdigit():
        return jsonify({'error': 'Phone must be exactly 10 digits'}), 400
    if not items:
        return jsonify({'error': 'Add at least one product to the bill'}), 400

    if wnum:
        if not qone("SELECT number FROM workers WHERE number=?", (wnum,)):
            return jsonify({'error': f'Worker {wnum} not found. Add the worker first.'}), 400

    conn          = get_db()
    total_amount  = 0
    total_pieces  = 0
    validated     = []

    for item in items:
        code = str(item.get('code', '')).strip()
        qty  = int(item.get('quantity', 1))
        p    = conn.execute("SELECT * FROM products WHERE code=?", (code,)).fetchone()
        if not p:
            conn.close()
            return jsonify({'error': f'Product code {code} not found'}), 400
        if p['stock'] < qty:
            conn.close()
            return jsonify({'error': f'Not enough stock for {p["name"]} (available: {p["stock"]})'}), 400
        sub = p['price'] * qty
        total_amount += sub
        total_pieces += qty
        validated.append({'code': code, 'name': p['name'],
                          'price': p['price'], 'qty': qty, 'sub': sub})

    cur = conn.execute(
        """INSERT INTO bills
           (customer_name,customer_phone,customer_email,customer_addr,
            worker_number,worker_name,total_amount,total_pieces)
           VALUES (?,?,?,?,?,?,?,?)""",
        (cname, cphone, cemail, caddr, wnum, wname, total_amount, total_pieces)
    )
    bill_id = cur.lastrowid

    for it in validated:
        conn.execute(
            "INSERT INTO bill_items (bill_id,product_code,product_name,price,quantity,subtotal) VALUES (?,?,?,?,?,?)",
            (bill_id, it['code'], it['name'], it['price'], it['qty'], it['sub'])
        )
        conn.execute("UPDATE products SET stock=stock-? WHERE code=?", (it['qty'], it['code']))

    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'bill_id': bill_id,
                    'total': total_amount, 'pieces': total_pieces})

@app.route('/api/bills/<int:bill_id>', methods=['GET'])
def get_bill(bill_id):
    b = qone("SELECT * FROM bills WHERE id=?", (bill_id,))
    if not b:
        return jsonify({'error': 'Bill not found'}), 404
    b['items'] = qall("SELECT * FROM bill_items WHERE bill_id=?", (bill_id,))
    return jsonify(b)


# ─── CUSTOMER LOOKUP ──────────────────────────────────────────────────────────

@app.route('/api/customers/lookup', methods=['GET'])
def lookup_customer():
    phone = (request.args.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    bill = qone("""
        SELECT * FROM bills WHERE customer_phone=?
        ORDER BY id DESC LIMIT 1
    """, (phone,))
    if not bill:
        return jsonify({'error': f'No bills found for {phone}'}), 404
    bill['items']       = qall("SELECT * FROM bill_items WHERE bill_id=?", (bill['id'],))
    bill['total_count'] = qone("SELECT COUNT(*) AS c FROM bills WHERE customer_phone=?", (phone,))['c']
    return jsonify(bill)


# ─── INCENTIVES ───────────────────────────────────────────────────────────────

@app.route('/api/incentives', methods=['GET'])
def get_incentives():
    workers = qall("SELECT * FROM workers ORDER BY number")
    out = []
    for w in workers:
        bdata = qone("""SELECT COUNT(*) AS cnt, COALESCE(SUM(total_pieces),0) AS pcs
                        FROM bills WHERE worker_number=?""", (w['number'],))
        adjs  = qone("""SELECT COALESCE(SUM(pieces),0) AS tot
                        FROM adjustments WHERE worker_number=?""", (w['number'],))
        pieces = (bdata['pcs'] or 0) + (adjs['tot'] or 0)
        out.append({
            'number':    w['number'],
            'name':      w['name'],
            'pieces':    pieces,
            'bills':     bdata['cnt'],
            'incentive': pieces   # ₹1 per piece
        })
    return jsonify(out)

@app.route('/api/incentives/adjust', methods=['POST'])
@need_supervisor
def adjust_incentive():
    d    = request.get_json(force=True) or {}
    wnum = str(d.get('worker_number', '')).strip()
    note = str(d.get('note', '')).strip()
    try:
        adj = int(d.get('adjustment', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid adjustment value'}), 400
    if not wnum:
        return jsonify({'error': 'Worker number required'}), 400
    if not qone("SELECT number FROM workers WHERE number=?", (wnum,)):
        return jsonify({'error': f'Worker {wnum} not found'}), 400
    if adj == 0:
        return jsonify({'error': 'Adjustment cannot be zero'}), 400
    conn = get_db()
    conn.execute("INSERT INTO adjustments (worker_number,pieces,note) VALUES (?,?,?)",
                 (wnum, adj, note))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'message': f'Adjusted {adj:+d} pieces for worker {wnum}'})

@app.route('/api/incentives/clear', methods=['POST'])
@need_supervisor
def clear_incentives():
    conn = get_db()
    conn.execute("UPDATE bills SET worker_number='', worker_name=''")
    conn.execute("DELETE FROM adjustments")
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'message': 'All incentives cleared for new month'})


# ─── REPORTS ──────────────────────────────────────────────────────────────────

@app.route('/api/reports', methods=['GET'])
def get_reports():
    sales   = qone("SELECT COALESCE(SUM(total_amount),0) AS v FROM bills")['v']
    nbills  = qone("SELECT COUNT(*) AS v FROM bills")['v']
    ncusts  = qone("SELECT COUNT(DISTINCT customer_phone) AS v FROM bills")['v']

    # Total incentives
    inc_rows = qall("""
        SELECT w.number,
               COALESCE(SUM(b.total_pieces),0) AS bp,
               COALESCE(a.adj,0) AS ap
        FROM workers w
        LEFT JOIN bills b ON b.worker_number=w.number
        LEFT JOIN (SELECT worker_number, SUM(pieces) AS adj
                   FROM adjustments GROUP BY worker_number) a
               ON a.worker_number=w.number
        GROUP BY w.number
    """)
    total_inc = sum((r['bp'] or 0) + (r['ap'] or 0) for r in inc_rows)

    recent = qall("""
        SELECT b.id, b.bill_date, b.customer_name, b.customer_phone,
               b.total_amount, b.worker_number,
               (SELECT COUNT(*) FROM bill_items WHERE bill_id=b.id) AS items
        FROM bills b ORDER BY b.id DESC LIMIT 15
    """)
    top = qall("""
        SELECT product_name,
               SUM(quantity)  AS units,
               SUM(subtotal)  AS revenue
        FROM bill_items
        GROUP BY product_name
        ORDER BY units DESC LIMIT 10
    """)
    return jsonify({
        'total_sales':     sales,
        'total_bills':     nbills,
        'total_customers': ncusts,
        'total_incentives':total_inc,
        'recent_bills':    recent,
        'top_products':    top
    })


# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print()
    print("=" * 52)
    print("  BillPro - Billing System")
    print("  Local : http://localhost:5000")
    print("  Network: http://0.0.0.0:5000")
    print()
    print("  Supervisor  →  admin / admin123")
    print("=" * 52)
    print()
    app.run(host='0.0.0.0', port=5000, debug=False)
