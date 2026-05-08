import os, hashlib
from flask import Flask, request, jsonify, session, Response
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "billpro_secret_key_2024")
CORS(app, supports_credentials=True)

# ══════════════════════════════════════════════════════════
#  DATABASE SETUP
# ══════════════════════════════════════════════════════════

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Render gives 'postgres://' but psycopg2 needs 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DB_READY = False
DB_ERROR = ""

try:
    import psycopg2
    import psycopg2.extras
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable is not set on Render.")
    # Test the connection immediately
    test_conn = psycopg2.connect(DATABASE_URL)
    test_conn.close()
    DB_READY = True
except ImportError:
    DB_ERROR = "psycopg2 not installed. Check requirements.txt has psycopg2-binary."
except Exception as e:
    DB_ERROR = str(e)


def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def qone(sql, params=()):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, params)
    row  = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def qall(sql, params=()):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run(sql, params=()):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()


def hpw(pw):
    return hashlib.sha256(pw.strip().encode()).hexdigest()


# ══════════════════════════════════════════════════════════
#  INIT TABLES
# ══════════════════════════════════════════════════════════

def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            code  TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            price NUMERIC NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            number  TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id             SERIAL PRIMARY KEY,
            bill_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            customer_name  TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            customer_email TEXT DEFAULT '',
            customer_addr  TEXT DEFAULT '',
            worker_number  TEXT DEFAULT '',
            worker_name    TEXT DEFAULT '',
            total_amount   NUMERIC DEFAULT 0,
            total_pieces   INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            id           SERIAL PRIMARY KEY,
            bill_id      INTEGER NOT NULL REFERENCES bills(id),
            product_code TEXT,
            product_name TEXT,
            price        NUMERIC,
            quantity     INTEGER,
            subtotal     NUMERIC
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS adjustments (
            id            SERIAL PRIMARY KEY,
            worker_number TEXT NOT NULL,
            pieces        INTEGER NOT NULL,
            note          TEXT DEFAULT '',
            created       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supervisor (
            id       SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cur.execute("SELECT COUNT(*) AS n FROM supervisor")
    if cur.fetchone()['n'] == 0:
        cur.execute(
            "INSERT INTO supervisor(username,password) VALUES(%s,%s)",
            ('admin', hpw('admin123'))
        )
    conn.commit()
    conn.close()


if DB_READY:
    try:
        init_db()
        print("✅ Database tables ready.")
    except Exception as e:
        DB_READY = False
        DB_ERROR = "Tables init failed: " + str(e)
        print("❌ " + DB_ERROR)
else:
    print("❌ DB not ready: " + DB_ERROR)


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def need_sup(fn):
    from functools import wraps
    @wraps(fn)
    def wrap(*a, **kw):
        if not session.get("is_sup"):
            return jsonify({"error": "Supervisor login required"}), 401
        return fn(*a, **kw)
    return wrap


def jok(**kwargs):
    kwargs['ok'] = True
    return jsonify(kwargs)


def jerr(msg, code=400):
    return jsonify({'error': msg}), code


def jdata():
    d = request.get_json(force=True, silent=True)
    return d if isinstance(d, dict) else {}


def db_check():
    """Return error response if DB is not ready."""
    if not DB_READY:
        return jerr("Database not connected. Error: " + DB_ERROR, 503)
    return None


# ══════════════════════════════════════════════════════════
#  FRONTEND HTML
# ══════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Billing System Pro Database</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f0f2f5;--card:#fff;--sb:#3949ab;--top:#3949ab;
  --pri:#3949ab;--pri2:#303f9f;
  --gn:#2e7d32;--gn2:#e8f5e9;
  --rd:#c62828;--rd2:#ffebee;
  --am:#e65100;--bl:#1565c0;--bl2:#e3f2fd;
  --tx:#212121;--t2:#555;--t3:#888;
  --br:#dde1e7;--ibg:#f8f9fb;--hov:#f1f3f8;--sel:#e8eaf6;
  --sw:210px;--sh:0 1px 4px rgba(0,0,0,.10),0 2px 12px rgba(0,0,0,.06);
}
html,body{height:100%;font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--tx);overflow:hidden;font-size:14px}
body{display:flex}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-thumb{background:#bbb;border-radius:99px}
.sb{width:var(--sw);min-width:var(--sw);background:var(--sb);display:flex;flex-direction:column;height:100vh;flex-shrink:0}
.sb-logo{padding:18px 16px 14px;border-bottom:1px solid rgba(255,255,255,.15);display:flex;align-items:center;gap:11px}
.sb-ic{width:38px;height:38px;border-radius:9px;background:rgba(255,255,255,.25);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;color:#fff;flex-shrink:0}
.sb-title{font-size:16px;font-weight:700;color:#fff}
.sb-sub{font-size:10px;color:rgba(255,255,255,.6);margin-top:1px}
.sb-nav{flex:1;padding:10px 8px;overflow-y:auto}
.ni{display:flex;align-items:center;gap:9px;padding:10px 12px;border-radius:7px;cursor:pointer;font-size:13.5px;font-weight:500;color:rgba(255,255,255,.75);transition:all .15s;margin-bottom:2px;user-select:none}
.ni:hover{background:rgba(255,255,255,.12);color:#fff}
.ni.on{background:rgba(255,255,255,.2);color:#fff;font-weight:600}
.ni-ic{font-size:16px;flex-shrink:0}
.sb-clk{padding:12px 16px;border-top:1px solid rgba(255,255,255,.15);text-align:center}
.cl-t{font-size:19px;font-weight:700;color:#fff;letter-spacing:1px}
.cl-d{font-size:10.5px;color:rgba(255,255,255,.6);margin-bottom:3px}
.main{flex:1;display:flex;flex-direction:column;height:100vh;overflow:hidden}
.topbar{background:var(--top);color:#fff;padding:0 24px;height:52px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;box-shadow:0 2px 8px rgba(0,0,0,.15)}
.tb-t{font-size:16px;font-weight:600}
.tb-r{font-size:12px;color:rgba(255,255,255,.8)}
.content{flex:1;overflow-y:auto;padding:22px 24px}
.pg{display:none}
.pg.on{display:block;animation:fi .2s ease}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.stitle{font-size:20px;font-weight:700;color:var(--tx);margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--br);border-radius:12px;padding:20px 22px;margin-bottom:16px;box-shadow:var(--sh)}
.ctitle{font-size:14px;font-weight:600;color:var(--t2);margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid var(--br)}
.fr{display:flex;gap:12px;flex-wrap:wrap}
.fg{display:flex;flex-direction:column;gap:5px;flex:1;min-width:130px}
.fg label{font-size:11.5px;font-weight:600;color:var(--t2)}
input,select{width:100%;background:var(--ibg);border:1.5px solid var(--br);border-radius:6px;padding:9px 12px;font-size:13.5px;font-family:inherit;color:var(--tx);outline:none;transition:border-color .15s,box-shadow .15s}
input:focus,select:focus{border-color:var(--pri);box-shadow:0 0 0 3px rgba(57,73,171,.12);background:#fff}
input::placeholder{color:#aaa;font-size:13px}
input[readonly]{background:#f3f4f6;color:var(--t3);cursor:not-allowed}
.iwrap{position:relative}
.iwrap input{padding-right:112px}
.ibadge{position:absolute;right:9px;top:50%;transform:translateY(-50%);font-size:11px;font-weight:600;color:var(--gn);background:var(--gn2);border-radius:20px;padding:2px 9px;max-width:102px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:none}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border:none;border-radius:6px;font-family:inherit;font-size:13.5px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}
.btn:hover{transform:translateY(-1px);box-shadow:0 2px 8px rgba(0,0,0,.12)}
.btn:active{transform:none}
.bp{background:var(--pri);color:#fff}.bp:hover{background:var(--pri2)}
.bg{background:#2e7d32;color:#fff}.bg:hover{background:#1b5e20}
.br_{background:#c62828;color:#fff}.br_:hover{background:#b71c1c}
.ba{background:#e65100;color:#fff}
.bo{background:#fff;color:var(--pri);border:1.5px solid var(--pri)}.bo:hover{background:var(--sel)}
.bsm{padding:6px 13px;font-size:12px}
.delbtn{background:var(--rd2);color:var(--rd);border:1px solid #ffcdd2;border-radius:5px;padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .13s}
.delbtn:hover{background:var(--rd);color:#fff}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{padding:9px 13px;background:#f5f6fa;color:var(--t2);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;text-align:left;border-bottom:1.5px solid var(--br)}
tbody td{padding:10px 13px;border-bottom:1px solid #f0f0f0;color:var(--tx);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--hov)}
.etd{text-align:center;color:var(--t3);padding:28px!important;font-size:13px;font-style:italic}
.cpill{background:#e8eaf6;color:var(--pri);border-radius:5px;padding:2px 8px;font-size:12px;font-weight:700;font-family:'Courier New',monospace}
.bgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.btbox{background:#e8eaf6;border:1px solid #c5cae9;border-radius:12px;padding:18px 22px}
.btr{display:flex;justify-content:space-between;align-items:center;font-size:14px;color:var(--t2);margin-bottom:6px}
.btgrand{font-size:20px;font-weight:700;color:var(--pri);margin-top:10px}
.bact{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}
.bid{background:var(--sel);color:var(--pri);border:1px solid #c5cae9;border-radius:20px;padding:4px 14px;font-size:13px;font-weight:600}
.sgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.sc{background:var(--card);border:1px solid var(--br);border-radius:12px;padding:18px 20px;display:flex;gap:14px;align-items:center;box-shadow:var(--sh);transition:transform .15s;border-left:4px solid transparent}
.sc:hover{transform:translateY(-2px)}
.s-bl{border-left-color:var(--pri)}.s-gn{border-left-color:#2e7d32}.s-am{border-left-color:#e65100}.s-cy{border-left-color:#0277bd}
.s-ic{font-size:28px}.s-lb{font-size:11px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.4px}
.s-vl{font-size:22px;font-weight:800;margin-top:3px}
.s-bl .s-vl{color:var(--pri)}.s-gn .s-vl{color:#2e7d32}.s-am .s-vl{color:#e65100}.s-cy .s-vl{color:#0277bd}
.crbox{margin-top:14px;background:var(--bl2);border:1px solid #bbdefb;border-radius:8px;padding:18px}
.crtitle{font-size:15px;font-weight:700;color:var(--bl);margin-bottom:12px}
.crgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px}
.crl{font-size:10px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px}
.crv{font-size:13.5px;font-weight:600;color:var(--tx)}
.cribox{background:#fff;border-radius:6px;padding:10px 14px;font-size:13px;color:var(--t2);line-height:1.8;font-family:'Courier New',monospace}
.supcard{border-top:3px solid var(--am)}
.supbadge{background:var(--gn2);color:var(--gn);border:1px solid #a5d6a7;border-radius:20px;padding:4px 13px;font-size:12.5px;font-weight:700;display:inline-block}
.supctrl{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.msg{font-size:12.5px;font-weight:600;margin-top:9px;min-height:16px}
.mok{color:var(--gn)}.mer{color:var(--rd)}
.lst{font-size:12.5px;font-weight:600;margin-top:7px;min-height:16px}
.lok{color:var(--gn)}.ler{color:var(--rd)}
.ov{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:999}
.ov.off{display:none}
.rmodal{background:#fff;border-radius:14px;padding:28px;width:90%;max-width:400px;box-shadow:0 20px 60px rgba(0,0,0,.25);font-family:'Courier New',monospace}
.rh{text-align:center;border-bottom:2px dashed #ddd;padding-bottom:14px;margin-bottom:13px}
.rh h2{font-size:20px;font-weight:800;color:var(--pri)}
.rh p{font-size:11px;color:var(--t3);margin-top:3px}
.rc p{font-size:12.5px;color:var(--t2);margin:3px 0}.rc strong{color:var(--tx)}.rc{margin-bottom:12px}
.riw{border-top:1px dashed #ddd;padding-top:10px}
.rir{display:flex;justify-content:space-between;font-size:12px;margin:4px 0;color:var(--t2)}
.rir span:last-child{color:var(--tx);font-weight:600}
.rtot{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:11px;border-top:2px dashed #ddd;font-size:16px;font-weight:800;color:var(--pri)}
.rftr{text-align:center;margin-top:12px;font-size:11px;color:var(--t2)}
.ract{display:flex;gap:9px;justify-content:center;margin-top:18px}
#tc{position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;gap:7px;z-index:9999}
.toast{background:#fff;border:1px solid var(--br);border-radius:8px;padding:11px 16px;font-size:13.5px;font-weight:500;color:var(--tx);box-shadow:0 4px 20px rgba(0,0,0,.12);display:flex;align-items:center;gap:8px;min-width:220px;animation:sir .2s ease}
@keyframes sir{from{transform:translateX(36px);opacity:0}to{transform:translateX(0);opacity:1}}
.tok{border-left:4px solid #2e7d32}.ter{border-left:4px solid #c62828}.tif{border-left:4px solid var(--pri)}
/* DB ERROR BANNER */
.db-err-banner{background:#fff3e0;border:2px solid #ff9800;border-radius:10px;padding:20px 24px;margin-bottom:20px;display:none}
.db-err-banner.show{display:block}
.db-err-title{font-size:16px;font-weight:700;color:#e65100;margin-bottom:8px}
.db-err-msg{font-size:13px;color:#555;font-family:'Courier New',monospace;background:#fff;padding:10px;border-radius:6px;margin-top:8px;word-break:break-all}
.hidden{display:none!important}
.mt12{margin-top:12px}.mt16{margin-top:16px}
.sep{border:none;border-top:1px solid var(--br);margin:14px 0}
.rgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.bpill{background:var(--sel);color:var(--pri);border-radius:4px;padding:1px 7px;font-size:11px;font-weight:700}
@media print{body *{visibility:hidden}.rmodal,.rmodal *{visibility:visible}.rmodal{position:fixed;inset:0;background:#fff;max-width:none;border-radius:0;padding:30px}.ract{display:none!important}}
@media(max-width:900px){.bgrid,.rgrid{grid-template-columns:1fr}.sgrid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<aside class="sb">
  <div class="sb-logo"><div class="sb-ic">BS</div><div><div class="sb-title">Billing System</div><div class="sb-sub">Pro Edition</div></div></div>
  <nav class="sb-nav">
    <div class="ni on" data-p="bill"        onclick="nav('bill')">      <span class="ni-ic">🧾</span> New Bill</div>
    <div class="ni"    data-p="stock"       onclick="nav('stock')">     <span class="ni-ic">📦</span> Stock Manager</div>
    <div class="ni"    data-p="customer"    onclick="nav('customer')">  <span class="ni-ic">👤</span> Customer Lookup</div>
    <div class="ni"    data-p="incentives"  onclick="nav('incentives')"><span class="ni-ic">🏆</span> Incentives</div>
    <div class="ni"    data-p="reports"     onclick="nav('reports')">   <span class="ni-ic">📊</span> Reports</div>
  </nav>
  <div class="sb-clk"><div class="cl-d" id="cld"></div><div class="cl-t" id="clt"></div></div>
</aside>
<div class="main">
  <div class="topbar"><span class="tb-t" id="tbt">Create New Bill</span><span class="tb-r">Billing System Pro</span></div>
  <div class="content">

    <!-- DB ERROR BANNER — shows if database not connected -->
    <div class="db-err-banner" id="dbBanner">
      <div class="db-err-title">⚠️ Database Not Connected</div>
      <div>The app cannot connect to the database. Please check:</div>
      <ul style="margin:8px 0 0 18px;font-size:13px;color:#555">
        <li>You created a <strong>PostgreSQL</strong> database on Render</li>
        <li>You added <strong>DATABASE_URL</strong> in Environment Variables</li>
        <li>The DATABASE_URL value is the <strong>Internal Database URL</strong></li>
        <li>You redeployed after adding the variable</li>
      </ul>
      <div class="db-err-msg" id="dbErrMsg"></div>
    </div>

    <!-- NEW BILL -->
    <div class="pg on" id="pg-bill">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
        <div class="stitle" style="margin-bottom:0">Create New Bill</div>
        <div class="bid">Bill # <span id="billNo">—</span></div>
      </div>
      <div class="card">
        <div class="ctitle">Customer Information</div>
        <div class="fr">
          <div class="fg" style="flex:2;min-width:150px"><label>Customer Name *</label><input id="bCN" type="text" placeholder="Enter name" onkeydown="ek(event,'bCP')"/></div>
          <div class="fg" style="flex:2;min-width:130px"><label>Phone Number *</label><input id="bCP" type="tel" placeholder="10-digit phone" maxlength="10" onkeydown="ek(event,'bEM')"/></div>
          <div class="fg" style="flex:2;min-width:150px"><label>Email</label><input id="bEM" type="email" placeholder="Enter email" onkeydown="ek(event,'bAD')"/></div>
          <div class="fg" style="flex:2;min-width:150px"><label>Address</label><input id="bAD" type="text" placeholder="Enter address" onkeydown="ek(event,'bCode')"/></div>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Add Items</div>
        <div class="fr">
          <div class="fg" style="max-width:155px"><label>Stock Code (3 digits)</label><input id="bCode" type="text" maxlength="3" placeholder="101" oninput="lookProd()" onkeydown="ek(event,'bQty')"/></div>
          <div class="fg" style="flex:2"><label>Product Name</label><input id="bPN" type="text" readonly placeholder="Auto-filled"/></div>
          <div class="fg"><label>Price (₹)</label><input id="bPr" type="text" readonly placeholder="Auto"/></div>
          <div class="fg" style="max-width:85px"><label>Qty</label><input id="bQty" type="number" value="1" min="1" onkeydown="if(event.key==='Enter')addItem()"/></div>
          <div class="fg" style="align-self:flex-end;max-width:120px"><button class="btn bp" onclick="addItem()">➕ Add Item</button></div>
        </div>
        <div class="lst" id="lst"></div>
      </div>
      <div class="card">
        <div class="ctitle">Bill Items</div>
        <div class="tw"><table><thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Price</th><th>Discount</th><th>Total</th><th>Action</th></tr></thead>
        <tbody id="bitb"><tr><td colspan="7" class="etd">No items added</td></tr></tbody></table></div>
        <div class="btbox mt16">
          <div class="btr"><span>Subtotal:</span><span id="bsub">₹0.00</span></div>
          <div class="btr btgrand"><span>Total Amount:</span><span id="btot">₹0.00</span></div>
          <hr class="sep"/>
          <div class="fr mt12">
            <div class="fg"><label>Worker Number</label>
              <div class="iwrap"><input id="bW" type="text" placeholder="Enter worker number (e.g., 01)" oninput="prevW()" onkeydown="if(event.key==='Enter')submitBill()"/><span class="ibadge" id="wbadge"></span></div>
            </div>
            <div class="fg" style="max-width:180px;align-self:flex-end"><input id="bWN" type="text" readonly placeholder="Worker name auto-filled"/></div>
          </div>
          <div class="bact">
            <button class="btn br_ bsm" onclick="clrBill()">🗑 Clear Bill</button>
            <button class="btn bg" style="flex:1;max-width:220px;justify-content:center" onclick="submitBill()">✅ Generate Bill</button>
          </div>
        </div>
      </div>
    </div>

    <!-- STOCK -->
    <div class="pg" id="pg-stock">
      <div class="stitle">Stock Manager</div>
      <div class="card">
        <div class="ctitle">Add New Product</div>
        <div class="fr">
          <div class="fg" style="max-width:165px"><label>Product Code (3 digits)</label><input id="pCode" type="text" maxlength="3" placeholder="e.g. 100" onkeydown="ek(event,'pName')"/></div>
          <div class="fg" style="flex:2"><label>Product Name</label><input id="pName" type="text" placeholder="Shirt, Pant..." onkeydown="ek(event,'pPrice')"/></div>
          <div class="fg"><label>Price (₹)</label><input id="pPrice" type="number" placeholder="100" min="0" step="0.01" onkeydown="ek(event,'pStock')"/></div>
          <div class="fg"><label>Stock Quantity</label><input id="pStock" type="number" placeholder="100" min="0" onkeydown="if(event.key==='Enter')addProd()"/></div>
          <div class="fg" style="align-self:flex-end;max-width:155px"><button class="btn bp" onclick="addProd()">📦 Add Product</button></div>
        </div>
        <div class="msg" id="pmsg"></div>
      </div>
      <div class="card">
        <div class="ctitle">Current Stock</div>
        <div class="tw"><table><thead><tr><th>Code</th><th>Product Name</th><th>Price (₹)</th><th>Stock</th><th>Total Value</th><th>Action</th></tr></thead>
        <tbody id="stb"><tr><td colspan="6" class="etd">Loading...</td></tr></tbody></table></div>
      </div>
    </div>

    <!-- CUSTOMER -->
    <div class="pg" id="pg-customer">
      <div class="stitle">Customer Lookup</div>
      <div class="card">
        <div class="ctitle">Search by Phone Number</div>
        <div class="fr">
          <div class="fg"><label>Phone Number</label><input id="cPh" type="tel" placeholder="Enter 10-digit phone number" maxlength="10" onkeydown="if(event.key==='Enter')lookCust()"/></div>
          <div class="fg" style="align-self:flex-end;max-width:130px"><button class="btn bp" onclick="lookCust()">🔍 Search</button></div>
        </div>
        <div id="cres" class="hidden"></div>
      </div>
    </div>

    <!-- INCENTIVES -->
    <div class="pg" id="pg-incentives">
      <div class="stitle">Worker Incentives <small style="font-size:13px;color:#888;font-weight:400">(₹1 per piece)</small></div>
      <div class="card supcard">
        <div class="ctitle">🔐 Supervisor Access</div>
        <div id="supfrm">
          <div class="fr">
            <div class="fg"><label>Username</label><input id="sU" type="text" placeholder="admin" onkeydown="ek(event,'sP')"/></div>
            <div class="fg"><label>Password</label><input id="sP" type="password" placeholder="Password" onkeydown="if(event.key==='Enter')supLogin()"/></div>
            <div class="fg" style="align-self:flex-end;max-width:190px"><button class="btn ba" onclick="supLogin()">🔐 Supervisor Login</button></div>
          </div>
          <div class="msg" id="smsg"></div>
        </div>
        <div id="suppnl" class="hidden">
          <div class="supctrl">
            <span class="supbadge">✅ Supervisor: <span id="supwho"></span></span>
            <button class="btn br_ bsm" onclick="clrInc()">🗑 Clear All Incentives (Month End)</button>
            <button class="btn bo bsm" onclick="supOut()">Logout</button>
          </div>
          <hr class="sep"/>
          <div style="font-size:12.5px;font-weight:600;color:#555;margin-bottom:12px">✏️ Edit Worker Incentive Manually</div>
          <div class="fr">
            <div class="fg"><label>Worker Number</label><input id="sEW" type="text" placeholder="e.g. 01" onkeydown="ek(event,'sEA')"/></div>
            <div class="fg"><label>Adjust Pieces (+ add, − subtract)</label><input id="sEA" type="number" placeholder="e.g. 5 or -3" onkeydown="ek(event,'sEN')"/></div>
            <div class="fg"><label>Note (optional)</label><input id="sEN" type="text" placeholder="Reason..." onkeydown="if(event.key==='Enter')supEdit()"/></div>
            <div class="fg" style="align-self:flex-end;max-width:150px"><button class="btn bp" onclick="supEdit()">✏️ Apply</button></div>
          </div>
          <div class="msg" id="semsg"></div>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Add New Worker</div>
        <div class="fr">
          <div class="fg" style="max-width:200px"><label>Worker Number</label><input id="wNum" type="text" placeholder="e.g. 01" onkeydown="ek(event,'wNam')"/></div>
          <div class="fg"><label>Worker Name</label><input id="wNam" type="text" placeholder="e.g. RAJ" onkeydown="if(event.key==='Enter')addWorker()"/></div>
          <div class="fg" style="align-self:flex-end;max-width:155px"><button class="btn bp" onclick="addWorker()">➕ Add Worker</button></div>
        </div>
        <div class="msg" id="wmsg"></div>
      </div>
      <div class="card">
        <div class="ctitle">Worker Performance</div>
        <div class="tw"><table><thead><tr><th>Number</th><th>Name</th><th>Pieces Sold</th><th>Bills</th><th>Incentive (₹)</th><th>Action</th></tr></thead>
        <tbody id="inctb"><tr><td colspan="6" class="etd">Loading...</td></tr></tbody></table></div>
      </div>
    </div>

    <!-- REPORTS -->
    <div class="pg" id="pg-reports">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
        <div class="stitle" style="margin-bottom:0">Reports &amp; Analytics</div>
        <button class="btn bo bsm" onclick="loadRep()">🔄 Refresh</button>
      </div>
      <div class="sgrid">
        <div class="sc s-bl"><div class="s-ic">💰</div><div><div class="s-lb">Total Sales</div><div class="s-vl" id="rS">—</div></div></div>
        <div class="sc s-gn"><div class="s-ic">🧾</div><div><div class="s-lb">Total Bills</div><div class="s-vl" id="rB">—</div></div></div>
        <div class="sc s-am"><div class="s-ic">👥</div><div><div class="s-lb">Customers</div><div class="s-vl" id="rC">—</div></div></div>
        <div class="sc s-cy"><div class="s-ic">🏆</div><div><div class="s-lb">Incentives</div><div class="s-vl" id="rI">—</div></div></div>
      </div>
      <div class="rgrid">
        <div class="card"><div class="ctitle">Recent Bills</div>
          <div class="tw"><table><thead><tr><th>Bill#</th><th>Date</th><th>Customer</th><th>Phone</th><th>Amount</th><th>Worker</th></tr></thead><tbody id="rbt"></tbody></table></div>
        </div>
        <div class="card"><div class="ctitle">Top Products</div>
          <div class="tw"><table><thead><tr><th>Product</th><th>Units</th><th>Revenue</th></tr></thead><tbody id="rpt"></tbody></table></div>
        </div>
      </div>
    </div>

  </div>
</div>

<div class="ov off" id="ov" onclick="if(event.target.id==='ov')closeR()">
  <div class="rmodal">
    <div class="rh"><h2>Billing System Pro</h2><p id="rDt"></p><p>Bill No: <strong id="rNo"></strong></p></div>
    <div class="rc"><p>Customer: <strong id="rCu"></strong></p><p>Phone: <strong id="rPh"></strong></p><p>Worker: <strong id="rWk"></strong></p></div>
    <div class="riw" id="rIt"></div>
    <div class="rtot"><span>TOTAL</span><strong id="rTo"></strong></div>
    <div class="rftr">Thank you for your purchase!</div>
    <div class="ract"><button class="btn bp" onclick="window.print()">🖨 Print</button><button class="btn bo" onclick="closeR()">✕ Close</button></div>
  </div>
</div>
<div id="tc"></div>

<script>
var PT={'bill':'Create New Bill','stock':'Stock Manager','customer':'Customer Lookup','incentives':'Worker Incentives','reports':'Reports & Analytics'};
var BI=[],PC={};

function tick(){var n=new Date(),d=document.getElementById('cld'),t=document.getElementById('clt');if(d)d.textContent=n.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});if(t)t.textContent=n.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true});}
setInterval(tick,1000);tick();

function nav(p){
  document.querySelectorAll('.pg').forEach(function(x){x.classList.remove('on')});
  document.querySelectorAll('.ni').forEach(function(x){x.classList.remove('on')});
  var pg=document.getElementById('pg-'+p);if(pg)pg.classList.add('on');
  var ni=document.querySelector('[data-p="'+p+'"]');if(ni)ni.classList.add('on');
  var tt=document.getElementById('tbt');if(tt)tt.textContent=PT[p]||'';
  if(p==='stock')loadStock();
  if(p==='incentives'){chkSup();loadInc();}
  if(p==='reports')loadRep();
  if(p==='bill')loadNextId();
}

function api(method,path,body){
  var opts={method:method,headers:{'Content-Type':'application/json'},credentials:'include'};
  if(body!=null)opts.body=JSON.stringify(body);
  return fetch(path,opts).then(function(r){
    var ct=r.headers.get('content-type')||'';
    if(ct.indexOf('application/json')<0){
      return r.text().then(function(txt){
        throw new Error('Server returned HTML instead of JSON. Database may not be connected. Check Render environment variables.');
      });
    }
    return r.json().then(function(d){if(!r.ok)throw new Error(d.error||'Error '+r.status);return d;});
  });
}

function toast(msg,t){
  var ic={ok:'✅',er:'❌',info:'ℹ️'};
  var el=document.createElement('div');
  el.className='toast t'+(t==='ok'?'ok':t==='er'?'er':'if');
  el.innerHTML='<span>'+(ic[t]||'ℹ️')+'</span><span>'+esc(msg)+'</span>';
  var tc=document.getElementById('tc');if(tc)tc.appendChild(el);
  setTimeout(function(){try{el.remove()}catch(e){}},4000);
}

function ek(e,n){if(e.key==='Enter'){var el=document.getElementById(n);if(el)el.focus();}}
function gv(id){var el=document.getElementById(id);return el?el.value.trim():'';}
function sv(id,v){var el=document.getElementById(id);if(el)el.value=v;}
function cv(ids){ids.forEach(function(id){sv(id,'');});}
function sm(id,msg,t){var el=document.getElementById(id);if(!el)return;el.textContent=msg;el.className='msg'+(msg?' m'+t:'');}
function sl(msg,t){var el=document.getElementById('lst');if(!el)return;el.textContent=msg;el.className='lst'+(msg?' l'+t:'');}
function fm(n){return '₹'+parseFloat(n||0).toFixed(2);}
function esc(s){var d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
function fd(s){if(!s)return '—';try{return new Date(s).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return s;}}

// Check DB status on load and show banner if not connected
function checkDB(){
  api('GET','/api/db-status').then(function(r){
    var banner=document.getElementById('dbBanner');
    if(!r.ok){
      if(banner){banner.classList.add('show');var em=document.getElementById('dbErrMsg');if(em)em.textContent=r.error||'Unknown error';}
    } else {
      if(banner)banner.classList.remove('show');
    }
  }).catch(function(){});
}

function loadNextId(){
  api('GET','/api/bills/next-id').then(function(r){sv('billNo',String(r.next_id).padStart(3,'0'));}).catch(function(){sv('billNo','???');});
  api('GET','/api/products').then(function(ps){PC={};ps.forEach(function(p){PC[p.code]=p;});}).catch(function(){});
}

function lookProd(){
  var code=gv('bCode');sv('bPN','');sv('bPr','');sl('','');
  if(code.length<3)return;
  var p=PC[code];
  if(p){sv('bPN',p.name);sv('bPr',p.price);sl('✔ '+p.name+' — Stock: '+p.stock,'ok');var q=document.getElementById('bQty');if(q)q.focus();}
  else{sl('✘ Product "'+code+'" not found. Add it in Stock Manager first.','er');}
}

function prevW(){
  var num=gv('bW'),badge=document.getElementById('wbadge'),wn=document.getElementById('bWN');
  if(badge)badge.style.display='none';if(wn)wn.value='';
  if(!num)return;
  api('GET','/api/workers/'+encodeURIComponent(num)).then(function(w){if(badge){badge.textContent=w.name;badge.style.display='block';}if(wn)wn.value=w.name;}).catch(function(){});
}

function addItem(){
  var code=gv('bCode'),name=gv('bPN'),price=parseFloat(gv('bPr')),qty=parseInt(document.getElementById('bQty').value)||1;
  if(!code||!name||isNaN(price)){toast('Enter a valid 3-digit product code first','er');document.getElementById('bCode').focus();return;}
  if(qty<1){toast('Quantity must be at least 1','er');return;}
  var p=PC[code];
  if(p){var inb=BI.filter(function(i){return i.code===code;}).reduce(function(s,i){return s+i.quantity;},0);if(p.stock<qty+inb){toast('Not enough stock! Available: '+(p.stock-inb),'er');return;}}
  var idx=BI.findIndex(function(i){return i.code===code;});
  if(idx>=0){BI[idx].quantity+=qty;BI[idx].subtotal=BI[idx].price*BI[idx].quantity;}
  else BI.push({code:code,name:name,price:price,quantity:qty,subtotal:price*qty});
  renderBI();cv(['bCode','bPN','bPr']);sv('bQty',1);sl('','');
  document.getElementById('bCode').focus();toast(name+' × '+qty+' added','ok');
}

function remItem(i){BI.splice(i,1);renderBI();}
function renderBI(){
  var tb=document.getElementById('bitb');if(!tb)return;
  if(!BI.length){tb.innerHTML='<tr><td colspan="7" class="etd">No items added</td></tr>';document.getElementById('bsub').textContent='₹0.00';document.getElementById('btot').textContent='₹0.00';return;}
  var tot=0,html='';
  BI.forEach(function(it,i){tot+=it.subtotal;html+='<tr><td>'+(i+1)+'</td><td><strong>'+esc(it.name)+'</strong> <span class="bpill">'+esc(it.code)+'</span></td><td>'+it.quantity+'</td><td>'+fm(it.price)+'</td><td>—</td><td><strong>'+fm(it.subtotal)+'</strong></td><td><button class="delbtn" onclick="remItem('+i+')">Remove</button></td></tr>';});
  tb.innerHTML=html;document.getElementById('bsub').textContent=fm(tot);document.getElementById('btot').textContent=fm(tot);
}

function submitBill(){
  var cn=gv('bCN'),cp=gv('bCP'),em=gv('bEM'),ad=gv('bAD'),wn=gv('bW'),wnm=gv('bWN');
  if(!cn){toast('Customer name is required','er');document.getElementById('bCN').focus();return;}
  if(!cp||cp.length!==10||!/^\d+$/.test(cp)){toast('Phone must be exactly 10 digits','er');document.getElementById('bCP').focus();return;}
  if(!BI.length){toast('Add at least one product','er');return;}
  api('POST','/api/bills',{customer_name:cn,customer_phone:cp,customer_email:em,customer_addr:ad,worker_number:wn,worker_name:wnm,items:BI.map(function(i){return{code:i.code,quantity:i.quantity};})})
  .then(function(r){showR(r.bill_id,cn,cp,wn,wnm,BI,r.total);BI=[];renderBI();cv(['bCN','bCP','bEM','bAD','bW','bWN']);var b=document.getElementById('wbadge');if(b)b.style.display='none';loadNextId();toast('Bill #'+r.bill_id+' created! Total: '+fm(r.total),'ok');})
  .catch(function(e){toast(e.message,'er');});
}

function clrBill(){if(!BI.length)return;if(!confirm('Clear all items?'))return;BI=[];renderBI();cv(['bCN','bCP','bEM','bAD','bW','bWN']);var b=document.getElementById('wbadge');if(b)b.style.display='none';toast('Bill cleared','info');}

function showR(id,cu,ph,wn,wnm,items,tot){
  function s(i,v){var el=document.getElementById(i);if(el)el.textContent=v;}
  s('rDt',new Date().toLocaleString('en-IN'));s('rNo',String(id).padStart(3,'0'));s('rCu',cu);s('rPh',ph);s('rWk',wn?wn+' — '+wnm:'N/A');
  var ri=document.getElementById('rIt');if(ri)ri.innerHTML=items.map(function(it){return '<div class="rir"><span>'+esc(it.name)+' × '+it.quantity+'</span><span>'+fm(it.subtotal)+'</span></div>';}).join('');
  s('rTo',fm(tot));var ov=document.getElementById('ov');if(ov)ov.classList.remove('off');
}
function closeR(){var ov=document.getElementById('ov');if(ov)ov.classList.add('off');}

function addProd(){
  var code=gv('pCode'),name=gv('pName'),price=gv('pPrice'),stock=gv('pStock');
  if(!code||code.length!==3||!/^\d{3}$/.test(code)){sm('pmsg','✘ Code must be exactly 3 digits','er');return;}
  if(!name){sm('pmsg','✘ Product name is required','er');return;}
  if(price===''||isNaN(parseFloat(price))||parseFloat(price)<0){sm('pmsg','✘ Enter a valid price','er');return;}
  if(stock===''||isNaN(parseInt(stock))||parseInt(stock)<0){sm('pmsg','✘ Enter a valid stock quantity','er');return;}
  api('POST','/api/products',{code:code,name:name,price:parseFloat(price),stock:parseInt(stock)})
  .then(function(r){sm('pmsg','✔ Product "'+name+'" added!','ok');cv(['pCode','pName','pPrice','pStock']);document.getElementById('pCode').focus();loadStock();toast('"'+name+'" added','ok');})
  .catch(function(e){sm('pmsg','✘ '+e.message,'er');});
}

function delProd(code){if(!confirm('Delete product "'+code+'"?'))return;api('DELETE','/api/products/'+encodeURIComponent(code)).then(function(){loadStock();toast('Deleted','info');}).catch(function(e){toast(e.message,'er');});}

function loadStock(){
  var tb=document.getElementById('stb');if(!tb)return;
  tb.innerHTML='<tr><td colspan="6" class="etd">Loading...</td></tr>';
  api('GET','/api/products').then(function(ps){
    PC={};ps.forEach(function(p){PC[p.code]=p;});
    if(!ps.length){tb.innerHTML='<tr><td colspan="6" class="etd">No products yet — add above</td></tr>';return;}
    tb.innerHTML=ps.map(function(p){return '<tr><td><span class="cpill">'+esc(p.code)+'</span></td><td><strong>'+esc(p.name)+'</strong></td><td>'+fm(p.price)+'</td><td><strong>'+p.stock+'</strong></td><td>'+fm(p.price*p.stock)+'</td><td><button class="delbtn" onclick="delProd(\''+esc(p.code)+'\')">Delete</button></td></tr>';}).join('');
  }).catch(function(e){tb.innerHTML='<tr><td colspan="6" class="etd" style="color:#c62828">✘ '+esc(e.message)+'</td></tr>';});
}

function lookCust(){
  var ph=gv('cPh'),box=document.getElementById('cres');
  if(box){box.innerHTML='';box.classList.add('hidden');}
  if(!ph||ph.length!==10){toast('Enter valid 10-digit phone','er');return;}
  api('GET','/api/customers/lookup?phone='+encodeURIComponent(ph)).then(function(b){
    var ih=(b.items||[]).map(function(it){return esc(it.product_code)+' | '+esc(it.product_name)+' × '+it.quantity+' = '+fm(it.subtotal);}).join('<br/>');
    var note=b.total_count>1?'<div style="font-size:11.5px;color:#888;margin-top:8px">📌 '+b.total_count+' total bills for this customer.</div>':'';
    if(box){box.innerHTML='<div class="crbox"><div class="crtitle">📋 Last Bill — #'+String(b.id).padStart(3,'0')+'</div><div class="crgrid"><div><div class="crl">Customer</div><div class="crv">'+esc(b.customer_name)+'</div></div><div><div class="crl">Phone</div><div class="crv">'+esc(b.customer_phone)+'</div></div><div><div class="crl">Date</div><div class="crv">'+fd(b.bill_date)+'</div></div><div><div class="crl">Amount</div><div class="crv" style="color:#1565c0">'+fm(b.total_amount)+'</div></div><div><div class="crl">Pieces</div><div class="crv">'+b.total_pieces+'</div></div><div><div class="crl">Worker</div><div class="crv">'+(b.worker_number?esc(b.worker_number)+' — '+esc(b.worker_name):'N/A')+'</div></div></div><div class="cribox"><strong>Items:</strong><br/>'+ih+'</div>'+note+'</div>';box.classList.remove('hidden');}
  }).catch(function(e){if(box){box.innerHTML='<div class="crbox"><div style="color:#c62828;font-weight:600">✘ '+esc(e.message)+'</div></div>';box.classList.remove('hidden');}});
}

function addWorker(){
  var num=gv('wNum'),name=gv('wNam');
  if(!num){sm('wmsg','✘ Worker number is required','er');return;}
  if(!name){sm('wmsg','✘ Worker name is required','er');return;}
  api('POST','/api/workers',{number:num,name:name}).then(function(r){sm('wmsg','✔ Worker "'+name+'" added!','ok');cv(['wNum','wNam']);document.getElementById('wNum').focus();loadInc();toast('Worker added','ok');}).catch(function(e){sm('wmsg','✘ '+e.message,'er');});
}
function delWorker(num){if(!confirm('Delete worker #'+num+'?'))return;api('DELETE','/api/workers/'+encodeURIComponent(num)).then(function(){loadInc();toast('Deleted','info');}).catch(function(e){toast(e.message,'er');});}
function loadInc(){
  var tb=document.getElementById('inctb');if(!tb)return;
  tb.innerHTML='<tr><td colspan="6" class="etd">Loading...</td></tr>';
  api('GET','/api/incentives').then(function(data){
    if(!data.length){tb.innerHTML='<tr><td colspan="6" class="etd">No workers added yet</td></tr>';return;}
    tb.innerHTML=data.map(function(w){return '<tr><td><span class="cpill">'+esc(w.number)+'</span></td><td><strong>'+esc(w.name)+'</strong></td><td>'+w.pieces+'</td><td>'+w.bills+'</td><td><strong style="color:#2e7d32">₹'+w.incentive+'</strong></td><td><button class="delbtn" onclick="delWorker(\''+esc(w.number)+'\')">Delete</button></td></tr>';}).join('');
  }).catch(function(e){tb.innerHTML='<tr><td colspan="6" class="etd" style="color:#c62828">✘ '+esc(e.message)+'</td></tr>';});
}

function chkSup(){api('GET','/api/sup/status').then(function(r){if(r.logged_in)showPnl(r.username);else showFrm();}).catch(function(){showFrm();});}
function showPnl(who){var f=document.getElementById('supfrm'),p=document.getElementById('suppnl'),w=document.getElementById('supwho');if(f)f.classList.add('hidden');if(p)p.classList.remove('hidden');if(w)w.textContent=who;}
function showFrm(){var f=document.getElementById('supfrm'),p=document.getElementById('suppnl');if(f)f.classList.remove('hidden');if(p)p.classList.add('hidden');}
function supLogin(){
  var u=gv('sU'),p=gv('sP');
  if(!u||!p){sm('smsg','✘ Enter both username and password','er');return;}
  api('POST','/api/sup/login',{username:u,password:p}).then(function(r){showPnl(r.username);sm('smsg','','');cv(['sU','sP']);toast('Supervisor logged in','ok');}).catch(function(e){sm('smsg','✘ '+e.message,'er');toast(e.message,'er');});
}
function supOut(){api('POST','/api/sup/logout').then(function(){showFrm();cv(['sU','sP']);toast('Logged out','info');}).catch(function(){showFrm();});}
function clrInc(){
  if(!confirm('⚠ MONTH-END CLEAR\n\nRemove all worker incentives?\n\nCannot be undone!'))return;
  api('POST','/api/incentives/clear').then(function(r){toast(r.message,'ok');loadInc();}).catch(function(e){toast(e.message,'er');});
}
function supEdit(){
  var wn=gv('sEW'),adj=parseInt(gv('sEA')),note=gv('sEN');
  if(!wn){sm('semsg','✘ Enter worker number','er');return;}
  if(isNaN(adj)||adj===0){sm('semsg','✘ Enter a non-zero number','er');return;}
  api('POST','/api/incentives/adjust',{worker_number:wn,adjustment:adj,note:note}).then(function(r){sm('semsg','✔ '+r.message,'ok');cv(['sEW','sEA','sEN']);loadInc();toast(r.message,'ok');}).catch(function(e){sm('semsg','✘ '+e.message,'er');});
}
function loadRep(){
  ['rS','rB','rC','rI'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent='...';});
  api('GET','/api/reports').then(function(d){
    function s(i,v){var el=document.getElementById(i);if(el)el.textContent=v;}
    s('rS',fm(d.total_sales));s('rB',d.total_bills);s('rC',d.total_customers);s('rI',fm(d.total_incentives));
    var rbt=document.getElementById('rbt');
    if(rbt){if(!d.recent_bills||!d.recent_bills.length){rbt.innerHTML='<tr><td colspan="6" class="etd">No bills yet</td></tr>';}else rbt.innerHTML=d.recent_bills.map(function(b){return '<tr><td><strong>#'+String(b.id).padStart(3,'0')+'</strong></td><td>'+fd(b.bill_date)+'</td><td>'+esc(b.customer_name)+'</td><td>'+esc(b.customer_phone)+'</td><td><strong style="color:#2e7d32">'+fm(b.total_amount)+'</strong></td><td>'+esc(b.worker_number||'—')+'</td></tr>';}).join('');}
    var rpt=document.getElementById('rpt');
    if(rpt){if(!d.top_products||!d.top_products.length){rpt.innerHTML='<tr><td colspan="3" class="etd">No sales yet</td></tr>';}else rpt.innerHTML=d.top_products.map(function(p){return '<tr><td><strong>'+esc(p.product_name)+'</strong></td><td>'+p.units+'</td><td><strong style="color:#2e7d32">'+fm(p.revenue)+'</strong></td></tr>';}).join('');}
  }).catch(function(e){['rS','rB','rC','rI'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent='ERR';});toast('Reports error: '+e.message,'er');});
}

checkDB();
loadNextId();
</script>
</body>
</html>"""


@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


# ── DB STATUS CHECK (called on page load to show banner if broken) ──
@app.route('/api/db-status', methods=['GET'])
def db_status():
    if not DB_READY:
        return jsonify({'ok': False, 'error': DB_ERROR})
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════
#  ALL API ROUTES
# ══════════════════════════════════════════════════════════

@app.route('/api/sup/login', methods=['POST'])
def sup_login():
    err = db_check()
    if err: return err
    d = jdata()
    u = str(d.get('username','') or '').strip()
    p = str(d.get('password','') or '').strip()
    if not u or not p:
        return jerr('Username and password required')
    row = qone("SELECT * FROM supervisor WHERE username=%s AND password=%s", (u, hpw(p)))
    if not row:
        return jerr('Wrong username or password', 401)
    session['is_sup'] = True
    session['sup_u']  = u
    return jok(username=u)

@app.route('/api/sup/logout', methods=['POST'])
def sup_logout():
    session.clear()
    return jok()

@app.route('/api/sup/status', methods=['GET'])
def sup_status():
    return jsonify({'logged_in': bool(session.get('is_sup')), 'username': session.get('sup_u','')})


@app.route('/api/products', methods=['GET'])
def get_products():
    err = db_check()
    if err: return err
    return jsonify(qall("SELECT * FROM products ORDER BY code"))

@app.route('/api/products/<code>', methods=['GET'])
def get_product(code):
    err = db_check()
    if err: return err
    p = qone("SELECT * FROM products WHERE code=%s", (code.strip(),))
    if p: return jsonify(p)
    return jerr('Product not found', 404)

@app.route('/api/products', methods=['POST'])
def add_product():
    err = db_check()
    if err: return err
    d     = jdata()
    code  = str(d.get('code','')  or '').strip()
    name  = str(d.get('name','')  or '').strip()
    price = d.get('price')
    stock = d.get('stock')
    if not code or len(code) != 3 or not code.isdigit():
        return jerr('Product code must be exactly 3 digits')
    if not name:
        return jerr('Product name is required')
    try:    price = float(price)
    except: return jerr('Enter a valid price number')
    try:    stock = int(stock)
    except: return jerr('Enter a valid stock quantity')
    if stock < 0: return jerr('Stock cannot be negative')
    if qone("SELECT code FROM products WHERE code=%s", (code,)):
        return jerr(f'Product code {code} already exists')
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO products(code,name,price,stock) VALUES(%s,%s,%s,%s)", (code,name,price,stock))
    conn.commit(); conn.close()
    return jok(message=f'Product "{name}" added')

@app.route('/api/products/<code>', methods=['DELETE'])
def del_product(code):
    err = db_check()
    if err: return err
    run("DELETE FROM products WHERE code=%s", (code,))
    return jok()


@app.route('/api/workers', methods=['GET'])
def get_workers():
    err = db_check()
    if err: return err
    return jsonify(qall("SELECT * FROM workers ORDER BY number"))

@app.route('/api/workers/<number>', methods=['GET'])
def get_worker(number):
    err = db_check()
    if err: return err
    w = qone("SELECT * FROM workers WHERE number=%s", (number.strip(),))
    if w: return jsonify(w)
    return jerr('Worker not found', 404)

@app.route('/api/workers', methods=['POST'])
def add_worker():
    err = db_check()
    if err: return err
    d    = jdata()
    num  = str(d.get('number','') or '').strip()
    name = str(d.get('name','')   or '').strip()
    if not num:  return jerr('Worker number is required')
    if not name: return jerr('Worker name is required')
    if qone("SELECT number FROM workers WHERE number=%s", (num,)):
        return jerr(f'Worker {num} already exists')
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO workers(number,name) VALUES(%s,%s)", (num,name))
    conn.commit(); conn.close()
    return jok(message=f'Worker "{name}" added')

@app.route('/api/workers/<number>', methods=['DELETE'])
def del_worker(number):
    err = db_check()
    if err: return err
    run("DELETE FROM workers WHERE number=%s", (number,))
    return jok()


@app.route('/api/bills/next-id', methods=['GET'])
def next_id():
    err = db_check()
    if err: return err
    r = qone("SELECT COALESCE(MAX(id),0) AS m FROM bills")
    return jsonify({'next_id': r['m'] + 1})

@app.route('/api/bills', methods=['POST'])
def create_bill():
    err = db_check()
    if err: return err
    d      = jdata()
    cname  = str(d.get('customer_name','')  or '').strip()
    cphone = str(d.get('customer_phone','') or '').strip()
    cemail = str(d.get('customer_email','') or '').strip()
    caddr  = str(d.get('customer_addr','')  or '').strip()
    wnum   = str(d.get('worker_number','')  or '').strip()
    wname  = str(d.get('worker_name','')    or '').strip()
    items  = d.get('items') or []
    if not cname:  return jerr('Customer name is required')
    if not cphone or len(cphone)!=10 or not cphone.isdigit():
        return jerr('Phone must be exactly 10 digits')
    if not items:  return jerr('Add at least one item')
    if wnum and not qone("SELECT number FROM workers WHERE number=%s", (wnum,)):
        return jerr(f'Worker {wnum} not found. Add worker first.')
    conn = get_db(); cur = conn.cursor()
    total_a = 0; total_p = 0; validated = []
    for item in items:
        code = str(item.get('code','') or '').strip()
        qty  = int(item.get('quantity',1) or 1)
        cur.execute("SELECT * FROM products WHERE code=%s", (code,))
        p = cur.fetchone()
        if not p: conn.close(); return jerr(f'Product code {code} not found')
        if p['stock'] < qty: conn.close(); return jerr(f'Not enough stock for {p["name"]} (available: {p["stock"]})')
        sub = float(p['price']) * qty
        total_a += sub; total_p += qty
        validated.append({'code':code,'name':p['name'],'price':float(p['price']),'qty':qty,'sub':sub})
    cur.execute("INSERT INTO bills(customer_name,customer_phone,customer_email,customer_addr,worker_number,worker_name,total_amount,total_pieces) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (cname,cphone,cemail,caddr,wnum,wname,total_a,total_p))
    bid = cur.fetchone()['id']
    for it in validated:
        cur.execute("INSERT INTO bill_items(bill_id,product_code,product_name,price,quantity,subtotal) VALUES(%s,%s,%s,%s,%s,%s)",
                    (bid,it['code'],it['name'],it['price'],it['qty'],it['sub']))
        cur.execute("UPDATE products SET stock=stock-%s WHERE code=%s", (it['qty'],it['code']))
    conn.commit(); conn.close()
    return jok(bill_id=bid, total=total_a, pieces=total_p)


    
@app.route('/api/customers/lookup', methods=['GET'])
def lookup_cust():
    err = db_check()
    if err: return err
    ph = (request.args.get('phone') or '').strip()
    if not ph: return jerr('Phone required')
    b = qone("SELECT * FROM bills WHERE customer_phone=%s ORDER BY id DESC LIMIT 1", (ph,))
    if not b: return jerr(f'No bills found for {ph}', 404)
    b['items']       = qall("SELECT * FROM bill_items WHERE bill_id=%s", (b['id'],))
    b['total_count'] = qone("SELECT COUNT(*) AS c FROM bills WHERE customer_phone=%s", (ph,))['c']
    return jsonify(b)


@app.route('/api/incentives', methods=['GET'])
def get_incentives():
    err = db_check()
    if err: return err
    workers = qall("SELECT * FROM workers ORDER BY number")
    out = []
    for w in workers:
        bd  = qone("SELECT COUNT(*) AS cnt,COALESCE(SUM(total_pieces),0) AS pcs FROM bills WHERE worker_number=%s", (w['number'],))
        adj = qone("SELECT COALESCE(SUM(pieces),0) AS tot FROM adjustments WHERE worker_number=%s", (w['number'],))
        p   = int(bd['pcs'] or 0) + int(adj['tot'] or 0)
        out.append({'number':w['number'],'name':w['name'],'pieces':p,'bills':bd['cnt'],'incentive':p})
    return jsonify(out)

@app.route('/api/incentives/adjust', methods=['POST'])
@need_sup
def adj_inc():
    err = db_check()
    if err: return err
    d    = jdata()
    wnum = str(d.get('worker_number','') or '').strip()
    note = str(d.get('note','') or '').strip()
    try: adj = int(d.get('adjustment',0))
    except: return jerr('Invalid adjustment')
    if not wnum: return jerr('Worker number required')
    if not qone("SELECT number FROM workers WHERE number=%s", (wnum,)):
        return jerr(f'Worker {wnum} not found')
    if adj == 0: return jerr('Adjustment cannot be zero')
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO adjustments(worker_number,pieces,note) VALUES(%s,%s,%s)", (wnum,adj,note))
    conn.commit(); conn.close()
    return jok(message=f'Adjusted {adj:+d} pieces for worker {wnum}')


@app.route('/api/incentives/clear', methods=['POST'])
@need_sup
def clr_inc():
    err = db_check()
    if err: return err
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE bills SET worker_number='',worker_name=''")
    cur.execute("DELETE FROM adjustments")
    conn.commit(); conn.close()
    return jok(message='All incentives cleared for new month')


@app.route('/api/reports', methods=['GET'])
def get_reports():
    err = db_check()
    if err: return err
    sales  = qone("SELECT COALESCE(SUM(total_amount),0) AS v FROM bills")['v']
    nbills = qone("SELECT COUNT(*) AS v FROM bills")['v']
    ncusts = qone("SELECT COUNT(DISTINCT customer_phone) AS v FROM bills")['v']
    rows = qall("SELECT COALESCE(SUM(b.total_pieces),0) AS inc FROM workers w LEFT JOIN bills b ON b.worker_number=w.number GROUP BY w.number")
    tinc   = sum(int(r['inc'] or 0) for r in rows)
    recent = qall("SELECT b.id,b.bill_date,b.customer_name,b.customer_phone,b.total_amount,b.worker_number FROM bills b ORDER BY b.id DESC LIMIT 15")
    top    = qall("SELECT product_name,SUM(quantity) AS units,SUM(subtotal) AS revenue FROM bill_items GROUP BY product_name ORDER BY units DESC LIMIT 10")
    return jsonify({'total_sales':float(sales),'total_bills':nbills,'total_customers':ncusts,'total_incentives':tinc,'recent_bills':recent,'top_products':top})


if __name__ == '__main__':
    print("\n" + "="*52)
    print("  Billing System Pro")
    print("  Open: http://localhost:5000")
    print("  Supervisor: admin / admin123")
    print("="*52 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
