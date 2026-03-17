/* =========================================================
   BillPro - Frontend JavaScript
   All API calls go to Flask backend on same origin.
   ========================================================= */

'use strict';

/* ─────────────────────────────────────────────────────────
   CLOCK
───────────────────────────────────────────────────────── */
function updateClock() {
  var now  = new Date();
  var dateEl = document.getElementById('clDate');
  var timeEl = document.getElementById('clTime');
  if (dateEl) dateEl.textContent = now.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' });
  if (timeEl) timeEl.textContent = now.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:true });
}
setInterval(updateClock, 1000);
updateClock();

/* ─────────────────────────────────────────────────────────
   PAGE TITLES
───────────────────────────────────────────────────────── */
var PAGE_TITLES = {
  'bill':       'Create New Bill',
  'stock':      'Stock Manager',
  'customer':   'Customer Lookup',
  'incentives': 'Worker Incentives',
  'reports':    'Reports & Analytics'
};

/* ─────────────────────────────────────────────────────────
   NAVIGATION
───────────────────────────────────────────────────────── */
function navTo(page) {
  document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.ni').forEach(function(n)   { n.classList.remove('active'); });

  var pg = document.getElementById('page-' + page);
  if (pg) pg.classList.add('active');

  var ni = document.querySelector('[data-page="' + page + '"]');
  if (ni) ni.classList.add('active');

  var tt = document.getElementById('topTitle');
  if (tt) tt.textContent = PAGE_TITLES[page] || '';

  if (page === 'stock')      loadStock();
  if (page === 'incentives') { checkSupStatus(); loadIncentives(); }
  if (page === 'reports')    loadReports();
  if (page === 'bill')       loadNextBillId();
}

/* ─────────────────────────────────────────────────────────
   API HELPER  — all requests go to Flask
───────────────────────────────────────────────────────── */
function api(method, path, body) {
  var opts = {
    method:      method,
    headers:     { 'Content-Type': 'application/json' },
    credentials: 'include'
  };
  if (body !== undefined && body !== null) {
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(function(res) {
    return res.json().then(function(data) {
      if (!res.ok) {
        throw new Error(data.error || 'Server error (' + res.status + ')');
      }
      return data;
    });
  });
}

/* ─────────────────────────────────────────────────────────
   TOAST
───────────────────────────────────────────────────────── */
function toast(msg, type) {
  type = type || 'info';
  var icons = { ok: '✅', err: '❌', info: 'ℹ️' };
  var el = document.createElement('div');
  el.className = 'toast t-' + type;
  el.innerHTML = '<span>' + (icons[type] || 'ℹ️') + '</span><span>' + escHtml(msg) + '</span>';
  var container = document.getElementById('toast-container');
  if (container) container.appendChild(el);
  setTimeout(function() { try { el.remove(); } catch(e) {} }, 3500);
}

/* ─────────────────────────────────────────────────────────
   HELPERS
───────────────────────────────────────────────────────── */
function ek(e, nextId) {
  if (e.key === 'Enter') {
    var el = document.getElementById(nextId);
    if (el) el.focus();
  }
}

function setMsg(id, msg, type) {
  var el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.className   = 'msg-box' + (msg ? ' msg-' + type : '');
}

function setLookup(msg, type) {
  var el = document.getElementById('lstatus');
  if (!el) return;
  el.textContent = msg;
  el.className   = 'lookup-status' + (msg ? ' ls-' + type : '');
}

function money(n) { return '₹' + parseFloat(n || 0).toFixed(2); }

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function fmtDate(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-IN', {
      day:'2-digit', month:'short', year:'numeric',
      hour:'2-digit', minute:'2-digit'
    });
  } catch(e) { return s; }
}

function getVal(id) {
  var el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function setVal(id, v) {
  var el = document.getElementById(id);
  if (el) el.value = v;
}

function clearVals(ids) {
  ids.forEach(function(id) { setVal(id, ''); });
}

/* ─────────────────────────────────────────────────────────
   BILL STATE
───────────────────────────────────────────────────────── */
var billItems   = [];
var productCache = {};

function loadNextBillId() {
  api('GET', '/api/bills/next-id').then(function(r) {
    setVal('billNo', String(r.next_id).padStart(3, '0'));
  }).catch(function() {
    setVal('billNo', '???');
  });
  // Also refresh product cache
  api('GET', '/api/products').then(function(prods) {
    productCache = {};
    prods.forEach(function(p) { productCache[p.code] = p; });
  }).catch(function() {});
}

/* ─ Product auto-lookup ── */
function lookupProduct() {
  var code = getVal('bCode');
  setVal('bPN', '');
  setVal('bPr', '');
  setLookup('', '');

  if (code.length < 3) return;

  var p = productCache[code];
  if (p) {
    setVal('bPN', p.name);
    setVal('bPr', p.price);
    setLookup('✔ ' + p.name + '  —  Stock: ' + p.stock, 'ok');
    var q = document.getElementById('bQty');
    if (q) q.focus();
  } else {
    setLookup('✘ Product "' + code + '" not found in stock. Add it first.', 'err');
  }
}

/* ─ Worker preview ─────── */
function previewWorker() {
  var num    = getVal('bWorker');
  var badge  = document.getElementById('workerBadge');
  var nameEl = document.getElementById('bWorkerName');
  if (badge)  badge.style.display = 'none';
  if (nameEl) nameEl.value = '';
  if (!num)   return;

  api('GET', '/api/workers/' + encodeURIComponent(num)).then(function(w) {
    if (badge)  { badge.textContent = w.name; badge.style.display = 'block'; }
    if (nameEl) nameEl.value = w.name;
  }).catch(function() {
    if (badge)  badge.style.display = 'none';
    if (nameEl) nameEl.value = '';
  });
}

/* ─ Add item to bill ───── */
function addItem() {
  var code  = getVal('bCode');
  var name  = getVal('bPN');
  var price = parseFloat(getVal('bPr'));
  var qty   = parseInt(document.getElementById('bQty').value) || 1;

  if (!code || !name || isNaN(price)) {
    toast('Please enter a valid 3-digit product code first', 'err');
    document.getElementById('bCode').focus();
    return;
  }
  if (qty < 1) { toast('Quantity must be at least 1', 'err'); return; }

  var p = productCache[code];
  if (p) {
    var alreadyInBill = billItems
      .filter(function(i) { return i.code === code; })
      .reduce(function(s, i) { return s + i.quantity; }, 0);
    if (p.stock < qty + alreadyInBill) {
      toast('Not enough stock! Available: ' + (p.stock - alreadyInBill), 'err');
      return;
    }
  }

  var idx = billItems.findIndex(function(i) { return i.code === code; });
  if (idx >= 0) {
    billItems[idx].quantity += qty;
    billItems[idx].subtotal  = billItems[idx].price * billItems[idx].quantity;
  } else {
    billItems.push({ code: code, name: name, price: price,
                     quantity: qty, subtotal: price * qty });
  }

  renderBillItems();
  clearVals(['bCode', 'bPN', 'bPr']);
  setVal('bQty', 1);
  setLookup('', '');
  document.getElementById('bCode').focus();
  toast(name + ' × ' + qty + ' added', 'ok');
}

function removeItem(idx) {
  billItems.splice(idx, 1);
  renderBillItems();
}

function renderBillItems() {
  var tb = document.getElementById('billTbody');
  if (!tb) return;

  if (!billItems.length) {
    tb.innerHTML = '<tr><td colspan="7" class="empty-td">No items added</td></tr>';
    setVal('bSubtotal', '₹0.00');
    setVal('bTotal',    '₹0.00');
    document.getElementById('bSubtotal').textContent = '₹0.00';
    document.getElementById('bTotal').textContent    = '₹0.00';
    return;
  }

  var total = 0;
  var html  = '';
  billItems.forEach(function(it, i) {
    total += it.subtotal;
    html += '<tr>'
      + '<td>' + (i + 1) + '</td>'
      + '<td><strong>' + escHtml(it.name) + '</strong>'
      + ' <span class="badge-primary" style="font-size:11px">' + escHtml(it.code) + '</span></td>'
      + '<td>' + it.quantity + '</td>'
      + '<td>' + money(it.price) + '</td>'
      + '<td>—</td>'
      + '<td><strong>' + money(it.subtotal) + '</strong></td>'
      + '<td><button class="del-btn" onclick="removeItem(' + i + ')">Remove</button></td>'
      + '</tr>';
  });
  tb.innerHTML = html;

  var st = document.getElementById('bSubtotal');
  var tt = document.getElementById('bTotal');
  if (st) st.textContent = money(total);
  if (tt) tt.textContent = money(total);
}

/* ─ Submit bill ─────────── */
function submitBill() {
  var cname  = getVal('bCN');
  var cphone = getVal('bCP');
  var cemail = getVal('bEmail');
  var caddr  = getVal('bAddr');
  var wnum   = getVal('bWorker');
  var wname  = getVal('bWorkerName');

  if (!cname)  { toast('Customer name is required', 'err'); document.getElementById('bCN').focus(); return; }
  if (!cphone || cphone.length !== 10 || !/^\d+$/.test(cphone)) {
    toast('Phone must be exactly 10 digits', 'err');
    document.getElementById('bCP').focus(); return;
  }
  if (!billItems.length) { toast('Add at least one item to the bill', 'err'); return; }

  var items = billItems.map(function(i) {
    return { code: i.code, quantity: i.quantity };
  });

  api('POST', '/api/bills', {
    customer_name:  cname,
    customer_phone: cphone,
    customer_email: cemail,
    customer_addr:  caddr,
    worker_number:  wnum,
    worker_name:    wname,
    items:          items
  }).then(function(r) {
    showReceipt(r.bill_id, cname, cphone, wnum, wname, billItems, r.total);
    billItems = [];
    renderBillItems();
    clearVals(['bCN','bCP','bEmail','bAddr','bWorker','bWorkerName']);
    var badge = document.getElementById('workerBadge');
    if (badge) badge.style.display = 'none';
    loadNextBillId();
    toast('Bill #' + r.bill_id + ' created! Total: ' + money(r.total), 'ok');
  }).catch(function(e) {
    toast(e.message, 'err');
  });
}

function clearBill() {
  if (!billItems.length) return;
  if (!confirm('Clear all items from this bill?')) return;
  billItems = [];
  renderBillItems();
  clearVals(['bCN','bCP','bEmail','bAddr','bWorker','bWorkerName']);
  var badge = document.getElementById('workerBadge');
  if (badge) badge.style.display = 'none';
  toast('Bill cleared', 'info');
}

/* ─────────────────────────────────────────────────────────
   RECEIPT MODAL
───────────────────────────────────────────────────────── */
function showReceipt(id, cust, phone, wnum, wname, items, total) {
  function s(elId, v) {
    var el = document.getElementById(elId);
    if (el) el.textContent = v;
  }
  s('rDate',   new Date().toLocaleString('en-IN'));
  s('rNo',     String(id).padStart(3, '0'));
  s('rCust',   cust);
  s('rPhone',  phone);
  s('rWorker', wnum ? wnum + ' — ' + wname : 'N/A');

  var container = document.getElementById('rItemsContainer');
  if (container) {
    container.innerHTML = items.map(function(it) {
      return '<div class="r-item-row">'
        + '<span>' + escHtml(it.name) + ' × ' + it.quantity + '</span>'
        + '<span>' + money(it.subtotal) + '</span>'
        + '</div>';
    }).join('');
  }

  s('rTotal', money(total));
  var ov = document.getElementById('receiptOverlay');
  if (ov) ov.classList.remove('hidden');
}

function closeReceipt() {
  var ov = document.getElementById('receiptOverlay');
  if (ov) ov.classList.add('hidden');
}

function handleOverlayClick(e) {
  if (e.target.id === 'receiptOverlay') closeReceipt();
}

/* ─────────────────────────────────────────────────────────
   STOCK MANAGER
───────────────────────────────────────────────────────── */
function addProduct() {
  var code  = getVal('pCode');
  var name  = getVal('pName');
  var price = getVal('pPrice');
  var stock = getVal('pStock');

  // Validate
  if (!code || code.length !== 3 || !/^\d{3}$/.test(code)) {
    setMsg('pMsg', '✘ Product code must be exactly 3 digits (e.g. 114)', 'err'); return;
  }
  if (!name) {
    setMsg('pMsg', '✘ Product name is required', 'err'); return;
  }
  if (price === '' || isNaN(parseFloat(price)) || parseFloat(price) < 0) {
    setMsg('pMsg', '✘ Enter a valid price (numbers only)', 'err'); return;
  }
  if (stock === '' || isNaN(parseInt(stock)) || parseInt(stock) < 0) {
    setMsg('pMsg', '✘ Enter a valid stock quantity (0 or more)', 'err'); return;
  }

  api('POST', '/api/products', {
    code:  code,
    name:  name,
    price: parseFloat(price),
    stock: parseInt(stock)
  }).then(function(r) {
    setMsg('pMsg', '✔ Product "' + name + '" added successfully!', 'ok');
    clearVals(['pCode','pName','pPrice','pStock']);
    document.getElementById('pCode').focus();
    loadStock();
    toast('"' + name + '" added to stock', 'ok');
  }).catch(function(e) {
    setMsg('pMsg', '✘ ' + e.message, 'err');
  });
}

function deleteProduct(code) {
  if (!confirm('Delete product "' + code + '"? This cannot be undone.')) return;
  api('DELETE', '/api/products/' + encodeURIComponent(code))
    .then(function() {
      loadStock();
      toast('Product deleted', 'info');
    })
    .catch(function(e) { toast(e.message, 'err'); });
}

function loadStock() {
  var tb = document.getElementById('stockTbody');
  if (!tb) return;
  tb.innerHTML = '<tr><td colspan="6" class="empty-td">Loading...</td></tr>';

  api('GET', '/api/products').then(function(prods) {
    productCache = {};
    prods.forEach(function(p) { productCache[p.code] = p; });

    if (!prods.length) {
      tb.innerHTML = '<tr><td colspan="6" class="empty-td">No products yet — add your first product above</td></tr>';
      return;
    }
    tb.innerHTML = prods.map(function(p) {
      return '<tr>'
        + '<td><span class="code-pill">' + escHtml(p.code) + '</span></td>'
        + '<td><strong>' + escHtml(p.name) + '</strong></td>'
        + '<td>' + money(p.price) + '</td>'
        + '<td><strong>' + p.stock + '</strong></td>'
        + '<td>' + money(p.price * p.stock) + '</td>'
        + '<td><button class="del-btn" onclick="deleteProduct(\'' + escHtml(p.code) + '\')">Delete</button></td>'
        + '</tr>';
    }).join('');
  }).catch(function(e) {
    tb.innerHTML = '<tr><td colspan="6" class="empty-td" style="color:#c62828">✘ ' + escHtml(e.message) + '</td></tr>';
  });
}

/* ─────────────────────────────────────────────────────────
   CUSTOMER LOOKUP
───────────────────────────────────────────────────────── */
function lookupCustomer() {
  var phone  = getVal('cPhone');
  var resBox = document.getElementById('custResultBox');

  if (!resBox) return;
  resBox.innerHTML = '';
  resBox.classList.add('hidden');

  if (!phone || phone.length !== 10) {
    toast('Enter a valid 10-digit phone number', 'err');
    return;
  }

  api('GET', '/api/customers/lookup?phone=' + encodeURIComponent(phone))
    .then(function(bill) {
      var itemsHtml = (bill.items || []).map(function(it) {
        return escHtml(it.product_code) + ' | ' + escHtml(it.product_name)
             + ' × ' + it.quantity + ' = ' + money(it.subtotal);
      }).join('<br/>');

      var note = bill.total_count > 1
        ? '<div style="font-size:11.5px;color:#888;margin-top:8px">📌 This customer has ' + bill.total_count + ' bill(s) on record.</div>'
        : '';

      resBox.innerHTML =
        '<div class="cust-result">'
        + '<div class="cust-result-title">📋 Last Bill — #' + String(bill.id).padStart(3,'0') + '</div>'
        + '<div class="cr-grid">'
        + '<div><div class="cr-label">Customer</div><div class="cr-value">' + escHtml(bill.customer_name) + '</div></div>'
        + '<div><div class="cr-label">Phone</div><div class="cr-value">' + escHtml(bill.customer_phone) + '</div></div>'
        + '<div><div class="cr-label">Date</div><div class="cr-value">' + fmtDate(bill.bill_date) + '</div></div>'
        + '<div><div class="cr-label">Amount</div><div class="cr-value" style="color:#1565c0">' + money(bill.total_amount) + '</div></div>'
        + '<div><div class="cr-label">Pieces</div><div class="cr-value">' + bill.total_pieces + '</div></div>'
        + '<div><div class="cr-label">Worker</div><div class="cr-value">' + (bill.worker_number ? escHtml(bill.worker_number) + ' — ' + escHtml(bill.worker_name) : 'N/A') + '</div></div>'
        + '</div>'
        + '<div class="cr-items-box"><strong>Items:</strong><br/>' + itemsHtml + '</div>'
        + note
        + '</div>';

      resBox.classList.remove('hidden');
    })
    .catch(function(e) {
      resBox.innerHTML = '<div class="cust-result"><div style="color:#c62828;font-weight:600">✘ ' + escHtml(e.message) + '</div></div>';
      resBox.classList.remove('hidden');
    });
}

/* ─────────────────────────────────────────────────────────
   WORKERS & INCENTIVES
───────────────────────────────────────────────────────── */
function addWorker() {
  var num  = getVal('wNum');
  var name = getVal('wName');

  if (!num)  { setMsg('wMsg', '✘ Worker number is required', 'err'); return; }
  if (!name) { setMsg('wMsg', '✘ Worker name is required',   'err'); return; }

  api('POST', '/api/workers', { number: num, name: name })
    .then(function(r) {
      setMsg('wMsg', '✔ Worker "' + name + '" (' + num + ') added!', 'ok');
      clearVals(['wNum','wName']);
      document.getElementById('wNum').focus();
      loadIncentives();
      toast('Worker "' + name + '" added', 'ok');
    })
    .catch(function(e) {
      setMsg('wMsg', '✘ ' + e.message, 'err');
    });
}

function deleteWorker(num) {
  if (!confirm('Delete worker #' + num + '?')) return;
  api('DELETE', '/api/workers/' + encodeURIComponent(num))
    .then(function() {
      loadIncentives();
      toast('Worker deleted', 'info');
    })
    .catch(function(e) { toast(e.message, 'err'); });
}

function loadIncentives() {
  var tb = document.getElementById('incTbody');
  if (!tb) return;
  tb.innerHTML = '<tr><td colspan="6" class="empty-td">Loading...</td></tr>';

  api('GET', '/api/incentives').then(function(data) {
    if (!data.length) {
      tb.innerHTML = '<tr><td colspan="6" class="empty-td">No workers added yet</td></tr>';
      return;
    }
    tb.innerHTML = data.map(function(w) {
      return '<tr>'
        + '<td><span class="code-pill">' + escHtml(w.number) + '</span></td>'
        + '<td><strong>' + escHtml(w.name) + '</strong></td>'
        + '<td>' + w.pieces + '</td>'
        + '<td>' + w.bills + '</td>'
        + '<td><strong style="color:#2e7d32">₹' + w.incentive + '</strong></td>'
        + '<td><button class="del-btn" onclick="deleteWorker(\'' + escHtml(w.number) + '\')">Delete</button></td>'
        + '</tr>';
    }).join('');
  }).catch(function(e) {
    tb.innerHTML = '<tr><td colspan="6" class="empty-td" style="color:#c62828">✘ ' + escHtml(e.message) + '</td></tr>';
  });
}

/* ─────────────────────────────────────────────────────────
   SUPERVISOR
───────────────────────────────────────────────────────── */
function checkSupStatus() {
  api('GET', '/api/supervisor/status').then(function(r) {
    if (r.logged_in) {
      showSupPanel(r.username);
    } else {
      showSupForm();
    }
  }).catch(function() { showSupForm(); });
}

function showSupPanel(who) {
  var loginBlock  = document.getElementById('supLoginBlock');
  var activeBlock = document.getElementById('supActiveBlock');
  var whoEl       = document.getElementById('supWho');
  if (loginBlock)  loginBlock.classList.add('hidden');
  if (activeBlock) activeBlock.classList.remove('hidden');
  if (whoEl)       whoEl.textContent = who;
}

function showSupForm() {
  var loginBlock  = document.getElementById('supLoginBlock');
  var activeBlock = document.getElementById('supActiveBlock');
  if (loginBlock)  loginBlock.classList.remove('hidden');
  if (activeBlock) activeBlock.classList.add('hidden');
}

function supervisorLogin() {
  var u = getVal('supU');
  var p = getVal('supP');

  if (!u || !p) {
    setMsg('supMsg', '✘ Enter both username and password', 'err');
    return;
  }

  api('POST', '/api/supervisor/login', { username: u, password: p })
    .then(function(r) {
      showSupPanel(r.username);
      setMsg('supMsg', '', '');
      clearVals(['supU','supP']);
      toast('Supervisor logged in as ' + r.username, 'ok');
    })
    .catch(function(e) {
      setMsg('supMsg', '✘ ' + e.message, 'err');
      toast(e.message, 'err');
    });
}

function supervisorLogout() {
  api('POST', '/api/supervisor/logout')
    .then(function() {
      showSupForm();
      clearVals(['supU','supP']);
      toast('Supervisor logged out', 'info');
    })
    .catch(function() {
      showSupForm();
    });
}

function clearIncentives() {
  if (!confirm('⚠  MONTH-END CLEAR\n\nThis will remove all worker-bill links and incentive adjustments.\n\nThis CANNOT be undone. Proceed?')) return;

  api('POST', '/api/incentives/clear')
    .then(function(r) {
      toast(r.message, 'ok');
      loadIncentives();
    })
    .catch(function(e) { toast(e.message, 'err'); });
}

function supervisorEditIncentive() {
  var wnum = getVal('supEW');
  var adj  = parseInt(getVal('supEA'));
  var note = getVal('supEN');

  if (!wnum) { setMsg('supEditMsg', '✘ Enter worker number', 'err'); return; }
  if (isNaN(adj) || adj === 0) { setMsg('supEditMsg', '✘ Enter a non-zero number (e.g. 5 or -3)', 'err'); return; }

  api('POST', '/api/incentives/adjust', {
    worker_number: wnum,
    adjustment:    adj,
    note:          note
  }).then(function(r) {
    setMsg('supEditMsg', '✔ ' + r.message, 'ok');
    clearVals(['supEW','supEA','supEN']);
    loadIncentives();
    toast(r.message, 'ok');
  }).catch(function(e) {
    setMsg('supEditMsg', '✘ ' + e.message, 'err');
  });
}

/* ─────────────────────────────────────────────────────────
   REPORTS
───────────────────────────────────────────────────────── */
function loadReports() {
  // Show loading
  ['rSales','rBills','rCusts','rInc'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.textContent = '...';
  });

  api('GET', '/api/reports').then(function(d) {
    function s(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

    s('rSales', money(d.total_sales));
    s('rBills', d.total_bills);
    s('rCusts', d.total_customers);
    s('rInc',   money(d.total_incentives));

    // Recent bills
    var rBT = document.getElementById('repBillsTb');
    if (rBT) {
      if (!d.recent_bills || !d.recent_bills.length) {
        rBT.innerHTML = '<tr><td colspan="6" class="empty-td">No bills yet</td></tr>';
      } else {
        rBT.innerHTML = d.recent_bills.map(function(b) {
          return '<tr>'
            + '<td><strong>#' + String(b.id).padStart(3,'0') + '</strong></td>'
            + '<td>' + fmtDate(b.bill_date) + '</td>'
            + '<td>' + escHtml(b.customer_name) + '</td>'
            + '<td>' + escHtml(b.customer_phone) + '</td>'
            + '<td><strong style="color:#2e7d32">' + money(b.total_amount) + '</strong></td>'
            + '<td>' + escHtml(b.worker_number || '—') + '</td>'
            + '</tr>';
        }).join('');
      }
    }

    // Top products
    var rPT = document.getElementById('repProdTb');
    if (rPT) {
      if (!d.top_products || !d.top_products.length) {
        rPT.innerHTML = '<tr><td colspan="3" class="empty-td">No sales data yet</td></tr>';
      } else {
        rPT.innerHTML = d.top_products.map(function(p) {
          return '<tr>'
            + '<td><strong>' + escHtml(p.product_name) + '</strong></td>'
            + '<td>' + p.units + '</td>'
            + '<td><strong style="color:#2e7d32">' + money(p.revenue) + '</strong></td>'
            + '</tr>';
        }).join('');
      }
    }
  }).catch(function(e) {
    ['rSales','rBills','rCusts','rInc'].forEach(function(id) {
      var el = document.getElementById(id); if (el) el.textContent = 'ERR';
    });
    toast('Reports error: ' + e.message, 'err');
  });
}
/* ─────────────────────────────────────────────────────────
   INIT
───────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function() {
  loadNextBillId();
});
