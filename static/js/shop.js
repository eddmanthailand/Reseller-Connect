/* EKG Shops — Retail (B2C) storefront logic. Guest checkout, localStorage cart. */
const Shop = (() => {
  const CART_KEY = 'ekg_shop_cart';
  const LAST_ORDER_KEY = 'ekg_shop_last_order';
  let products = [];
  let searchTimer = null;
  let currentProduct = null;   // {product, skus}
  let selectedSku = null;
  let selectedQty = 1;

  /* ---------- FB Pixel (retail channel, no-op if pixel absent) ---------- */
  function fbTrack(event, params = {}) {
    try {
      if (window.fbq) window.fbq('track', event, Object.assign({ channel: 'retail' }, params));
    } catch (e) {}
  }

  /* ---------- utils ---------- */
  const money = n => '฿' + Number(n || 0).toLocaleString('th-TH', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

  function toast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2200);
  }

  function getCart() {
    try { return JSON.parse(localStorage.getItem(CART_KEY)) || []; } catch (e) { return []; }
  }
  function saveCart(c) { localStorage.setItem(CART_KEY, JSON.stringify(c)); updateCartBadge(); }
  function cartCount() { return getCart().reduce((s, i) => s + i.quantity, 0); }
  function cartSubtotal() { return getCart().reduce((s, i) => s + i.discounted_price * i.quantity, 0); }

  function updateCartBadge() {
    const n = cartCount();
    const badge = document.getElementById('cartBadge');
    const btn = document.getElementById('cartBtn');
    badge.textContent = n;
    badge.classList.toggle('show', n > 0);
    btn.classList.toggle('has-items', n > 0);
  }

  /* ---------- load filters + products ---------- */
  async function init() {
    updateCartBadge();
    try {
      const [b, c] = await Promise.all([
        fetch('/api/public/brands').then(r => r.json()),
        fetch('/api/public/categories').then(r => r.json()),
      ]);
      const bf = document.getElementById('brandFilter');
      (b.brands || []).forEach(x => bf.insertAdjacentHTML('beforeend', `<option value="${x.id}">${esc(x.name)}</option>`));
      const cf = document.getElementById('categoryFilter');
      (c.categories || []).forEach(x => cf.insertAdjacentHTML('beforeend', `<option value="${x.id}">${esc(x.name)}</option>`));
    } catch (e) {}
    loadProducts();
    fbTrack('PageView');
  }

  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadProducts, 300);
  }

  async function loadProducts() {
    const grid = document.getElementById('productGrid');
    const state = document.getElementById('gridState');
    grid.innerHTML = '';
    state.innerHTML = '<div class="loading">กำลังโหลดสินค้า...</div>';
    const params = new URLSearchParams();
    const brand = document.getElementById('brandFilter').value;
    const cat = document.getElementById('categoryFilter').value;
    const search = document.getElementById('searchInput').value.trim();
    if (brand) params.set('brand', brand);
    if (cat) params.set('category', cat);
    if (search) params.set('search', search);
    try {
      const data = await fetch('/api/shop/products?' + params).then(r => r.json());
      products = data.products || [];
      state.innerHTML = '';
      if (!products.length) { state.innerHTML = '<div class="empty">ไม่พบสินค้า</div>'; return; }
      grid.innerHTML = products.map(renderCard).join('');
    } catch (e) {
      state.innerHTML = '<div class="empty">เกิดข้อผิดพลาดในการโหลดสินค้า</div>';
    }
  }

  function renderCard(p) {
    const hasDisc = p.discount_percent > 0;
    const img = p.image_url || '/static/icons/icon-192x192.png';
    let priceHtml;
    if (hasDisc) {
      priceHtml = `<div class="price-old">${money(p.min_price)}</div>
        <div class="price-now">${money(p.discounted_min_price)}<span class="discount-tag">-${p.discount_percent}%</span></div>`;
    } else {
      priceHtml = `<div class="price-now">${money(p.min_price)}</div>`;
    }
    const stock = p.total_stock > 0 ? priceHtml : '<div class="stock-out">สินค้าหมด</div>';
    return `<div class="card" onclick="Shop.openProduct(${p.id})">
      <img class="card-img" src="${esc(img)}" alt="${esc(p.name)}" loading="lazy" onerror="this.src='/static/icons/icon-192x192.png'">
      <div class="card-body">
        <div class="card-brand">${esc(p.brand_name || '')}</div>
        <div class="card-name">${esc(p.name)}</div>
        <div class="card-price">${stock}</div>
      </div>
    </div>`;
  }

  /* ---------- product modal ---------- */
  async function openProduct(id) {
    const body = document.getElementById('pmBody');
    body.innerHTML = '<div class="loading">กำลังโหลด...</div>';
    document.getElementById('productModal').classList.add('show');
    document.body.style.overflow = 'hidden';
    try {
      const data = await fetch(`/api/shop/product/${id}/skus`).then(r => r.json());
      currentProduct = data;
      selectedSku = null; selectedQty = 1;
      renderProductModal();
      fbTrack('ViewContent', { content_ids: [id], content_type: 'product' });
    } catch (e) {
      body.innerHTML = '<div class="empty">ไม่สามารถโหลดสินค้าได้</div>';
    }
  }

  function renderProductModal() {
    const { product, skus } = currentProduct;
    document.getElementById('pmTitle').textContent = product.name;
    const img = product.image_url || '/static/icons/icon-192x192.png';
    const disc = product.discount_percent || 0;

    let skuHtml = skus.map(s => {
      const opts = Object.entries(s.options || {}).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(' · ') || 'มาตรฐาน';
      const out = s.stock <= 0;
      const priceLine = disc > 0
        ? `<span class="price-old">${money(s.price)}</span> <b style="color:var(--primary)">${money(s.discounted_price)}</b>`
        : `<b style="color:var(--primary)">${money(s.price)}</b>`;
      const sel = selectedSku && selectedSku.id === s.id;
      const qtyCtrl = sel
        ? `<div class="qty-ctrl">
             <button class="qty-btn" onclick="event.stopPropagation();Shop.changeQty(-1)">−</button>
             <span class="qty-val">${selectedQty}</span>
             <button class="qty-btn" onclick="event.stopPropagation();Shop.changeQty(1)" ${selectedQty >= s.stock ? 'disabled' : ''}>+</button>
           </div>`
        : (out ? '<span class="stock-out">หมด</span>' : `<span class="info-line">คงเหลือ ${s.stock}</span>`);
      return `<div class="sku-row ${sel ? 'selected' : ''}" ${out ? '' : `onclick="Shop.selectSku(${s.id})"`} style="${out ? 'opacity:.5' : ''}">
        <div class="sku-info"><div class="sku-opts">${opts}</div><div class="sku-price">${priceLine}</div></div>
        ${qtyCtrl}
      </div>`;
    }).join('');

    let sizeChartHtml = '';
    const scg = product.size_chart_group;
    if (scg && scg.columns && scg.columns.length) {
      const head = scg.columns.map(c => `<th>${esc(c)}</th>`).join('');
      const rows = (scg.rows || []).map(r => '<tr>' + scg.columns.map(c => `<td>${esc(r[c] || '')}</td>`).join('') + '</tr>').join('');
      sizeChartHtml = `<details style="margin:12px 0"><summary style="cursor:pointer;font-weight:600;color:var(--primary)">📏 ตารางขนาด (${esc(scg.name)})</summary>
        <table class="sizechart-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></details>`;
    } else if (product.size_chart_image_url) {
      sizeChartHtml = `<details style="margin:12px 0"><summary style="cursor:pointer;font-weight:600;color:var(--primary)">📏 ตารางขนาด</summary>
        <img src="${esc(product.size_chart_image_url)}" style="width:100%;border-radius:10px;margin-top:8px"></details>`;
    }

    document.getElementById('pmBody').innerHTML = `
      <img class="modal-img" src="${esc(img)}" onerror="this.src='/static/icons/icon-192x192.png'">
      ${sizeChartHtml}
      <div style="font-weight:600;font-size:14px;margin-bottom:8px">เลือกตัวเลือกสินค้า</div>
      ${skuHtml}
      <button class="btn-primary" style="margin-top:8px" onclick="Shop.addSelectedToCart()" ${selectedSku ? '' : 'disabled'}>
        ${selectedSku ? 'เพิ่มลงตะกร้า' : 'เลือกตัวเลือกก่อน'}
      </button>`;
  }

  function selectSku(id) {
    selectedSku = currentProduct.skus.find(s => s.id === id);
    selectedQty = 1;
    renderProductModal();
  }
  function changeQty(d) {
    if (!selectedSku) return;
    const n = selectedQty + d;
    if (n >= 1 && n <= selectedSku.stock) selectedQty = n;
    renderProductModal();
  }

  function addSelectedToCart() {
    if (!selectedSku) return;
    const { product } = currentProduct;
    const cart = getCart();
    const existing = cart.find(i => i.sku_id === selectedSku.id);
    const opts = Object.entries(selectedSku.options || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'มาตรฐาน';
    if (existing) {
      existing.quantity = Math.min(existing.quantity + selectedQty, selectedSku.stock);
    } else {
      cart.push({
        sku_id: selectedSku.id,
        product_id: product.id,
        product_name: product.name,
        sku_code: selectedSku.sku_code,
        options: opts,
        price: selectedSku.price,
        discounted_price: selectedSku.discounted_price,
        image_url: product.image_url,
        stock: selectedSku.stock,
        quantity: selectedQty,
      });
    }
    saveCart(cart);
    fbTrack('AddToCart', { content_ids: [selectedSku.id], value: selectedSku.discounted_price * selectedQty, currency: 'THB' });
    toast('เพิ่มลงตะกร้าแล้ว');
    closeModal('productModal');
  }

  /* ---------- cart drawer ---------- */
  function openCart() {
    renderCart();
    document.getElementById('drawerOverlay').classList.add('show');
    document.getElementById('cartDrawer').classList.add('show');
    document.body.style.overflow = 'hidden';
  }
  function closeCart() {
    document.getElementById('drawerOverlay').classList.remove('show');
    document.getElementById('cartDrawer').classList.remove('show');
    document.body.style.overflow = '';
  }

  function renderCart() {
    const cart = getCart();
    const body = document.getElementById('cartBody');
    const footer = document.getElementById('cartFooter');
    if (!cart.length) {
      body.innerHTML = '<div class="empty">ตะกร้าว่างเปล่า</div>';
      footer.innerHTML = '';
      return;
    }
    body.innerHTML = cart.map((i, idx) => `
      <div class="cart-item">
        <img src="${esc(i.image_url || '/static/icons/icon-192x192.png')}" onerror="this.src='/static/icons/icon-192x192.png'">
        <div class="cart-item-info">
          <div class="cart-item-name">${esc(i.product_name)}</div>
          <div class="cart-item-opts">${esc(i.options)}</div>
          <div class="cart-item-price">${money(i.discounted_price)}</div>
          <div class="qty-ctrl" style="margin-top:6px">
            <button class="qty-btn" onclick="Shop.cartQty(${idx},-1)">−</button>
            <span class="qty-val">${i.quantity}</span>
            <button class="qty-btn" onclick="Shop.cartQty(${idx},1)" ${i.quantity >= i.stock ? 'disabled' : ''}>+</button>
            <button class="cart-item-remove" style="margin-left:auto" onclick="Shop.cartRemove(${idx})">ลบ</button>
          </div>
        </div>
      </div>`).join('');
    footer.innerHTML = `
      <div class="summary-row"><span>ยอดสินค้า</span><span>${money(cartSubtotal())}</span></div>
      <div class="summary-row"><span style="color:var(--text-muted);font-size:12.5px">ค่าจัดส่งคำนวณตามน้ำหนักในขั้นตอนถัดไป</span></div>
      <button class="btn-primary" onclick="Shop.startCheckout()">สั่งซื้อ (${cartCount()} ชิ้น)</button>`;
  }

  function cartQty(idx, d) {
    const cart = getCart();
    const it = cart[idx]; if (!it) return;
    const n = it.quantity + d;
    if (n < 1) { cart.splice(idx, 1); }
    else if (n <= it.stock) { it.quantity = n; }
    saveCart(cart); renderCart();
  }
  function cartRemove(idx) {
    const cart = getCart(); cart.splice(idx, 1); saveCart(cart); renderCart();
  }

  /* ---------- checkout ---------- */
  let provinces = [];
  async function startCheckout() {
    if (!getCart().length) return;
    closeCart();
    document.getElementById('coTitle').textContent = 'ข้อมูลจัดส่ง';
    const body = document.getElementById('coBody');
    body.innerHTML = `
      <div id="coAlert"></div>
      <div class="form-group"><label>ชื่อ-นามสกุล <span class="req">*</span></label><input id="fName" placeholder="ชื่อผู้รับ"></div>
      <div class="form-row">
        <div class="form-group"><label>เบอร์โทร <span class="req">*</span></label><input id="fPhone" inputmode="tel" placeholder="08x-xxx-xxxx"></div>
        <div class="form-group"><label>อีเมล <span class="req">*</span></label><input id="fEmail" inputmode="email" placeholder="อีเมลสำหรับติดตาม"></div>
      </div>
      <div class="form-group"><label>ที่อยู่ (บ้านเลขที่ ถนน) <span class="req">*</span></label><textarea id="fAddr" rows="2" placeholder="บ้านเลขที่ หมู่ ซอย ถนน"></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>จังหวัด <span class="req">*</span></label><select id="fProvince" onchange="Shop.onProvince()"><option value="">เลือกจังหวัด</option></select></div>
        <div class="form-group"><label>อำเภอ/เขต <span class="req">*</span></label><select id="fDistrict" onchange="Shop.onDistrict()"><option value="">เลือกอำเภอ</option></select></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>ตำบล/แขวง <span class="req">*</span></label><select id="fSubdistrict" onchange="Shop.onSubdistrict()"><option value="">เลือกตำบล</option></select></div>
        <div class="form-group"><label>รหัสไปรษณีย์</label><input id="fPostal" inputmode="numeric" readonly></div>
      </div>
      <div class="form-group"><label>หมายเหตุ (ถ้ามี)</label><textarea id="fNotes" rows="2" placeholder="เช่น ขนาดที่ต้องการ / ข้อความถึงร้าน"></textarea></div>
      <div class="summary-row total"><span>ยอดสินค้า</span><span>${money(cartSubtotal())}</span></div>
      <div class="info-line" style="margin-bottom:12px">* ค่าจัดส่งจะถูกคำนวณและแสดงในหน้าชำระเงิน</div>
      <button class="btn-primary" id="coSubmit" onclick="Shop.submitOrder()">ยืนยันคำสั่งซื้อ</button>`;
    document.getElementById('checkoutModal').classList.add('show');
    document.body.style.overflow = 'hidden';
    fbTrack('InitiateCheckout', { value: cartSubtotal(), currency: 'THB', num_items: cartCount() });
    if (!provinces.length) {
      try { provinces = await fetch('/api/thailand/provinces').then(r => r.json()); } catch (e) { provinces = []; }
    }
    const sel = document.getElementById('fProvince');
    provinces.forEach(p => sel.insertAdjacentHTML('beforeend', `<option value="${p.provinceCode}">${esc(p.provinceNameTh)}</option>`));
  }

  async function onProvince() {
    const code = document.getElementById('fProvince').value;
    const dSel = document.getElementById('fDistrict');
    const sSel = document.getElementById('fSubdistrict');
    dSel.innerHTML = '<option value="">เลือกอำเภอ</option>';
    sSel.innerHTML = '<option value="">เลือกตำบล</option>';
    document.getElementById('fPostal').value = '';
    if (!code) return;
    try {
      const d = await fetch('/api/thailand/districts/' + code).then(r => r.json());
      d.forEach(x => dSel.insertAdjacentHTML('beforeend', `<option value="${x.districtCode}">${esc(x.districtNameTh)}</option>`));
    } catch (e) {}
  }
  async function onDistrict() {
    const code = document.getElementById('fDistrict').value;
    const sSel = document.getElementById('fSubdistrict');
    sSel.innerHTML = '<option value="">เลือกตำบล</option>';
    document.getElementById('fPostal').value = '';
    if (!code) return;
    try {
      const s = await fetch('/api/thailand/subdistricts/' + code).then(r => r.json());
      window._subd = s;
      s.forEach(x => sSel.insertAdjacentHTML('beforeend', `<option value="${x.subdistrictCode}" data-postal="${x.postalCode}">${esc(x.subdistrictNameTh)}</option>`));
    } catch (e) {}
  }
  function onSubdistrict() {
    const opt = document.getElementById('fSubdistrict').selectedOptions[0];
    document.getElementById('fPostal').value = opt ? (opt.dataset.postal || '') : '';
  }

  function textOf(id) {
    const el = document.getElementById(id);
    return el.selectedOptions ? el.selectedOptions[0].textContent : el.value;
  }

  async function submitOrder() {
    const alertBox = document.getElementById('coAlert');
    alertBox.innerHTML = '';
    const name = document.getElementById('fName').value.trim();
    const phone = document.getElementById('fPhone').value.trim();
    const email = document.getElementById('fEmail').value.trim();
    const addr = document.getElementById('fAddr').value.trim();
    const provinceSel = document.getElementById('fProvince').value;
    const districtSel = document.getElementById('fDistrict').value;
    const subdistrictSel = document.getElementById('fSubdistrict').value;
    if (!name || !phone || !email || !addr || !provinceSel || !districtSel || !subdistrictSel) {
      alertBox.innerHTML = '<div class="alert alert-error">กรุณากรอกข้อมูลให้ครบทุกช่องที่มี *</div>'; return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      alertBox.innerHTML = '<div class="alert alert-error">อีเมลไม่ถูกต้อง</div>'; return;
    }
    const btn = document.getElementById('coSubmit');
    btn.disabled = true; btn.textContent = 'กำลังสร้างคำสั่งซื้อ...';
    const payload = {
      items: getCart().map(i => ({ sku_id: i.sku_id, quantity: i.quantity })),
      name, phone, email, address: addr,
      province: textOf('fProvince'), district: textOf('fDistrict'),
      subdistrict: textOf('fSubdistrict'), postal: document.getElementById('fPostal').value,
      notes: document.getElementById('fNotes').value.trim(),
    };
    try {
      const res = await fetch('/api/shop/order', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-error">${esc(data.error || 'เกิดข้อผิดพลาด')}</div>`;
        btn.disabled = false; btn.textContent = 'ยืนยันคำสั่งซื้อ'; return;
      }
      const order = data.order;
      localStorage.setItem(LAST_ORDER_KEY, JSON.stringify({ token: order.guest_token, order_number: order.order_number }));
      saveCart([]);  // clear cart
      fbTrack('Purchase', { value: order.final_amount, currency: 'THB', content_type: 'product' });
      showPayment(order.guest_token);
    } catch (e) {
      alertBox.innerHTML = '<div class="alert alert-error">เชื่อมต่อไม่สำเร็จ กรุณาลองใหม่</div>';
      btn.disabled = false; btn.textContent = 'ยืนยันคำสั่งซื้อ';
    }
  }

  /* ---------- payment (PromptPay QR + slip) ---------- */
  async function showPayment(token) {
    document.getElementById('coTitle').textContent = 'ชำระเงิน';
    const body = document.getElementById('coBody');
    body.innerHTML = '<div class="loading">กำลังสร้าง QR Code...</div>';
    try {
      const qr = await fetch(`/api/shop/order/${token}/promptpay-qr`).then(r => r.json());
      if (qr.error) throw new Error(qr.error);
      body.innerHTML = `
        <div class="alert alert-success">✅ สร้างคำสั่งซื้อ <b>${esc(qr.order_number)}</b> สำเร็จ!</div>
        <div class="qr-box">
          <p class="info-line">สแกนเพื่อชำระผ่าน PromptPay (ยอดเงินฝังอัตโนมัติ)</p>
          <img src="${qr.qr_data_url}" alt="PromptPay QR">
          <div class="pay-amount">${money(qr.amount)}</div>
          ${qr.account_name ? `<div class="info-line">ชื่อบัญชี: ${esc(qr.account_name)}</div>` : ''}
          <div class="info-line">พร้อมเพย์: ${esc(qr.promptpay_number)}</div>
        </div>
        <hr style="border:none;border-top:1px solid var(--border);margin:18px 0">
        <div style="font-weight:600;margin-bottom:8px">อัปโหลดสลิปหลังโอนเงิน</div>
        <div id="slipAlert"></div>
        <input type="file" id="slipFile" accept="image/*" style="display:none" onchange="Shop.previewSlip(event)">
        <div class="upload-area" id="slipArea" onclick="document.getElementById('slipFile').click()">
          📎 แตะเพื่อเลือกรูปสลิป
          <img id="slipPreview" class="upload-preview" style="display:none">
        </div>
        <button class="btn-primary" style="margin-top:12px" id="slipSubmit" onclick="Shop.uploadSlip('${token}')" disabled>ยืนยันการชำระเงิน</button>
        <p class="info-line" style="margin-top:12px;text-align:center">เก็บเลขคำสั่งซื้อ <b>${esc(qr.order_number)}</b> ไว้ติดตามสถานะ<br>ระบบส่งอีเมลยืนยันและเลขพัสดุให้อัตโนมัติ</p>`;
    } catch (e) {
      body.innerHTML = `<div class="alert alert-error">${esc(e.message || 'ไม่สามารถสร้าง QR ได้')}</div>
        <p class="info-line">คำสั่งซื้อถูกบันทึกแล้ว ติดต่อแอดมินเพื่อชำระเงินได้ที่ ${esc(window.EKG_CONTACT_PHONE || '')}</p>`;
    }
  }

  let slipFileData = null;
  function previewSlip(ev) {
    const f = ev.target.files[0];
    if (!f) return;
    slipFileData = f;
    const img = document.getElementById('slipPreview');
    img.src = URL.createObjectURL(f); img.style.display = 'block';
    document.getElementById('slipSubmit').disabled = false;
  }

  async function uploadSlip(token) {
    if (!slipFileData) return;
    const btn = document.getElementById('slipSubmit');
    const alertBox = document.getElementById('slipAlert');
    btn.disabled = true; btn.textContent = 'กำลังตรวจสอบสลิป...';
    alertBox.innerHTML = '<div class="alert alert-info">⏳ กำลังตรวจสอบสลิปอัตโนมัติ (ไม่เกิน 20 วินาที)...</div>';
    const fd = new FormData();
    fd.append('slip_image', slipFileData);
    try {
      const res = await fetch(`/api/shop/order/${token}/payment-slip`, { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok && data.auto_verified) {
        showDone(true, 'ชำระเงินสำเร็จ! คำสั่งซื้อได้รับการยืนยันแล้ว ร้านกำลังเตรียมจัดส่ง');
      } else if (res.ok) {
        showDone(false, 'อัปโหลดสลิปสำเร็จ รอแอดมินตรวจสอบและยืนยันการชำระเงิน');
      } else if (data.thunder_rejected) {
        alertBox.innerHTML = `<div class="alert alert-error">${esc(data.error)}</div>`;
        btn.disabled = false; btn.textContent = 'ลองอัปโหลดใหม่';
      } else {
        alertBox.innerHTML = `<div class="alert alert-error">${esc(data.error || 'อัปโหลดไม่สำเร็จ')}</div>`;
        btn.disabled = false; btn.textContent = 'ยืนยันการชำระเงิน';
      }
    } catch (e) {
      alertBox.innerHTML = '<div class="alert alert-error">เชื่อมต่อไม่สำเร็จ กรุณาลองใหม่</div>';
      btn.disabled = false; btn.textContent = 'ยืนยันการชำระเงิน';
    }
  }

  function showDone(verified, msg) {
    const body = document.getElementById('coBody');
    body.innerHTML = `
      <div class="step-done">
        <div class="check">${verified ? '✅' : '📤'}</div>
        <h3 style="margin-bottom:8px">${verified ? 'ชำระเงินสำเร็จ' : 'ได้รับสลิปแล้ว'}</h3>
        <p class="info-line" style="margin-bottom:20px">${esc(msg)}</p>
        <a href="/shop/track" class="btn-primary" style="display:block;text-decoration:none;margin-bottom:10px">ติดตามคำสั่งซื้อ</a>
        <button class="btn-outline" onclick="Shop.closeModal('checkoutModal');Shop.loadProducts()">เลือกซื้อสินค้าต่อ</button>
      </div>`;
  }

  /* ---------- misc modals ---------- */
  function openPolicy() {
    document.getElementById('imTitle').textContent = 'นโยบายการคืนสินค้า';
    document.getElementById('imBody').innerHTML = `
      <div style="font-size:14px;line-height:1.7;color:var(--text)">
        <p>• ตรวจสอบสินค้าทันทีที่ได้รับ หากพบปัญหา (สินค้าชำรุด/ผิดขนาด/ผิดรุ่น) กรุณาแจ้งภายใน 7 วัน</p>
        <p>• สินค้าต้องอยู่ในสภาพสมบูรณ์ ยังไม่ผ่านการใช้งาน พร้อมป้ายและบรรจุภัณฑ์เดิม</p>
        <p>• กรณีสินค้ามีปัญหาจากทางร้าน ร้านรับผิดชอบค่าจัดส่งในการเปลี่ยน/คืน</p>
        <p style="margin-top:14px">สินค้ามีปัญหา? <a href="#" onclick="Shop.contactAdmin();return false;" style="color:var(--primary);font-weight:600">ติดต่อแอดมิน</a></p>
      </div>`;
    document.getElementById('infoModal').classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function contactAdmin() {
    const phone = window.EKG_CONTACT_PHONE || '';
    document.getElementById('imTitle').textContent = 'ติดต่อแอดมิน';
    document.getElementById('imBody').innerHTML = `
      <div style="text-align:center;padding:10px">
        <p style="font-size:14px;margin-bottom:16px">สินค้ามีปัญหาหรือต้องการสอบถาม ติดต่อเราได้ที่</p>
        <a href="tel:${esc(phone.replace(/-/g,''))}" class="btn-primary" style="display:block;text-decoration:none;margin-bottom:10px">📞 โทร ${esc(phone)}</a>
        <p class="info-line">เวลาทำการ: ทุกวัน (ระบบรับออเดอร์ 24 ชม.)</p>
      </div>`;
    document.getElementById('infoModal').classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    document.body.style.overflow = '';
  }

  return {
    init, loadProducts, onSearch, openProduct, selectSku, changeQty, addSelectedToCart,
    openCart, closeCart, cartQty, cartRemove, startCheckout, onProvince, onDistrict, onSubdistrict,
    submitOrder, previewSlip, uploadSlip, openPolicy, contactAdmin, closeModal,
  };
})();

document.addEventListener('DOMContentLoaded', Shop.init);
