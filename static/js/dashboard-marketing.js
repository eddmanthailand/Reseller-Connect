// ==================== MARKETING MODULE ====================

let _promoData = [], _couponData = [];
let _mktTiers = [], _mktBrands = [], _mktCategories = [];
let _editingPromoId = null, _editingCouponId = null;

async function _mktLoadMeta() {
    if (_mktTiers.length) return;
    const [t, b, c] = await Promise.all([
        fetch('/api/reseller-tiers').then(r => r.json()).catch(() => []),
        fetch('/api/brands').then(r => r.json()).catch(() => []),
        fetch('/api/categories').then(r => r.json()).catch(() => [])
    ]);
    _mktTiers = Array.isArray(t) ? t : [];
    _mktBrands = Array.isArray(b) ? b : [];
    _mktCategories = Array.isArray(c) ? c : [];
}

function _fmtDiscount(promo) {
    if (promo.reward_type === 'discount_percent') return `ลด ${promo.reward_value}%`;
    if (promo.reward_type === 'discount_fixed') return `ลด ฿${Number(promo.reward_value).toLocaleString()}`;
    if (promo.reward_type === 'free_item') return `ของแถม ${promo.reward_qty || 1} ชิ้น`;
    return promo.reward_type;
}
function _fmtCondition(promo) {
    const parts = [];
    if (promo.condition_min_spend > 0) parts.push(`ซื้อครบ ฿${Number(promo.condition_min_spend).toLocaleString()}`);
    if (promo.condition_min_qty > 0) parts.push(`จำนวน ${promo.condition_min_qty} ชิ้นขึ้นไป`);
    return parts.join(' & ') || 'ทุกออเดอร์';
}
function _fmtCouponDiscount(c) {
    if (c.discount_type === 'percent') {
        let s = `ลด ${c.discount_value}%`;
        if (c.max_discount > 0) s += ` (สูงสุด ฿${Number(c.max_discount).toLocaleString()})`;
        return s;
    }
    if (c.discount_type === 'fixed') return `ลด ฿${Number(c.discount_value).toLocaleString()}`;
    if (c.discount_type === 'free_shipping') return 'ส่งฟรี';
    return c.discount_type;
}

// ── Promotions ──────────────────────────────────────────────────

async function loadPromotions() {
    try {
        const data = await fetch('/api/admin/promotions').then(r => r.json());
        _promoData = Array.isArray(data) ? data : [];
        const active = _promoData.filter(p => p.is_active).length;
        const inactive = _promoData.length - active;
        document.getElementById('promoStats').innerHTML = `
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#fff;">${_promoData.length}</div>
                <div class="mkt-stat-lbl">ทั้งหมด</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#4ade80;">${active}</div>
                <div class="mkt-stat-lbl">กำลังใช้งาน</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#9ca3af;">${inactive}</div>
                <div class="mkt-stat-lbl">ปิดอยู่</div>
            </div>
        `;
        if (!_promoData.length) {
            document.getElementById('promoTableWrap').innerHTML = `<div class="empty-state"><p>ยังไม่มีโปรโมชัน — กดปุ่ม "สร้างโปรโมชัน" เพื่อเริ่มต้น</p></div>`;
            return;
        }
        const cards = _promoData.map(p => {
            const chips = [];
            if (p.condition_min_spend > 0) chips.push(`<span class="promo-chip chip-condition">ซื้อครบ ฿${Number(p.condition_min_spend).toLocaleString()}</span>`);
            if (p.condition_min_qty > 0) chips.push(`<span class="promo-chip chip-condition">${p.condition_min_qty} ชิ้นขึ้นไป</span>`);
            chips.push(`<span class="promo-chip chip-reward">${_fmtDiscount(p)}</span>`);
            if (p.is_stackable) chips.push(`<span class="promo-chip chip-stackable">+คูปองได้</span>`);
            if (p.once_per_user) chips.push(`<span class="promo-chip" style="background:rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.25);">1 ครั้ง/คน</span>`);
            if (p.target_brand_name) chips.push(`<span class="promo-chip chip-brand">${p.target_brand_name}</span>`);
            if (p.min_tier_name) chips.push(`<span class="promo-chip chip-tier">${p.min_tier_name}+</span>`);
            const dateStr = p.end_date ? `หมดอายุ ${new Date(p.end_date).toLocaleDateString('th-TH')}` : 'ไม่มีกำหนดหมดอายุ';
            return `
            <div class="promo-card">
                <div class="promo-card-top">
                    <div class="promo-card-name">${p.name}</div>
                    <label class="toggle-switch" style="flex-shrink:0;">
                        <input type="checkbox" ${p.is_active ? 'checked' : ''} onchange="togglePromotion(${p.id}, this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="promo-chip-row">${chips.join('')}</div>
                <div class="promo-card-footer">
                    <div class="promo-card-date">${dateStr}</div>
                    <div class="promo-card-actions">
                        <button class="action-btn btn-review" onclick="openPromoModal(${p.id})">แก้ไข</button>
                        <button class="action-btn" style="background:rgba(239,68,68,0.2);color:#ef4444;" onclick="deletePromotion(${p.id})">ลบ</button>
                    </div>
                </div>
            </div>`;
        }).join('');
        document.getElementById('promoTableWrap').innerHTML = `<div class="promo-grid">${cards}</div>`;
    } catch (e) {
        document.getElementById('promoTableWrap').innerHTML = `<div class="empty-state"><p>เกิดข้อผิดพลาด</p></div>`;
    }
}

async function openPromoModal(id = null) {
    _editingPromoId = id;
    await _mktLoadMeta();

    const tierOptions = `<option value="">ทุกระดับ</option>` + _mktTiers.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    const brandOptions = `<option value="">ทุกแบรนด์</option>` + _mktBrands.map(b => `<option value="${b.id}">${b.name}</option>`).join('');

    let promo = {};
    if (id) {
        promo = _promoData.find(p => p.id === id) || {};
    }

    const html = `
    <div id="promoModal" class="modal" style="display:flex; z-index:10005;">
      <div class="apple-modal-content">

        <div class="apple-modal-header">
            <h3 class="apple-modal-title">${id ? 'แก้ไขโปรโมชัน' : 'สร้างโปรโมชันใหม่'}</h3>
            <button class="apple-modal-close" onclick="closePromoModal()">&times;</button>
        </div>

        <div class="apple-modal-body">

            <div class="apple-section" style="margin-top:16px;">
                <div class="apple-field">
                    <label class="apple-field-label">ชื่อโปรโมชัน <span style="color:#ec4899;">*</span></label>
                    <input id="pName" class="apple-input" value="${promo.name || ''}" placeholder="เช่น ซื้อครบ 1,000 ลด 10%">
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เงื่อนไข</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ซื้อครบ (฿)</label>
                        <input id="pMinSpend" class="apple-input" type="number" min="0" value="${promo.condition_min_spend || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">จำนวนขั้นต่ำ (ชิ้น)</label>
                        <input id="pMinQty" class="apple-input" type="number" min="0" value="${promo.condition_min_qty || 0}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">รางวัล</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ประเภทรางวัล</label>
                        <select id="pRewardType" class="apple-select" onchange="updatePromoRewardUI()">
                            <option value="discount_percent" ${promo.reward_type === 'discount_percent' ? 'selected' : ''}>ลดเป็น %</option>
                            <option value="discount_fixed" ${promo.reward_type === 'discount_fixed' ? 'selected' : ''}>ลดคงที่ (฿)</option>
                            <option value="free_item" ${promo.reward_type === 'free_item' ? 'selected' : ''}>ของแถม (GWP)</option>
                        </select>
                    </div>
                    <div id="pRewardValWrap" class="apple-field">
                        <label class="apple-field-label" id="pRewardValLabel">ส่วนลด (%)</label>
                        <input id="pRewardVal" class="apple-input" type="number" min="0" value="${promo.reward_value || 0}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เป้าหมาย</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">เฉพาะแบรนด์</label>
                        <select id="pBrand" class="apple-select">${brandOptions}</select>
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ระดับสมาชิกขั้นต่ำ</label>
                        <select id="pTier" class="apple-select">${tierOptions}</select>
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ช่วงเวลา</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">วันเริ่ม</label>
                        <input id="pStart" class="apple-input" type="datetime-local" value="${promo.start_date ? promo.start_date.substring(0,16) : ''}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">วันสิ้นสุด</label>
                        <input id="pEnd" class="apple-input" type="datetime-local" value="${promo.end_date ? promo.end_date.substring(0,16) : ''}">
                    </div>
                </div>
                <div class="apple-field" style="margin-top:10px;">
                    <label class="apple-field-label">ลำดับความสำคัญ <span class="apple-field-hint">(ตัวเลขสูง = ใช้ก่อน)</span></label>
                    <input id="pPriority" class="apple-input" type="number" value="${promo.priority || 0}" min="0">
                </div>
            </div>

            <div class="apple-section" style="margin-bottom:20px;">
                <span class="apple-section-label">การตั้งค่า</span>
                <div class="apple-toggle-card">
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">ใช้ร่วมกับคูปองได้</div>
                            <div class="apple-toggle-desc">ลูกค้าสามารถใช้คูปองซ้อนกับโปรโมชันนี้</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="pStackable" ${promo.is_stackable ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label" style="color:#fbbf24;">1 ครั้ง/คน (Once per user)</div>
                            <div class="apple-toggle-desc">แต่ละ reseller ใช้โปรโมชันนี้ได้เพียง 1 ครั้ง เช่น "ซื้อครั้งแรก"</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="pOncePerUser" ${promo.once_per_user ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">เปิดใช้งาน</div>
                            <div class="apple-toggle-desc">โปรโมชันจะแสดงและใช้งานได้ทันที</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="pActive" ${promo.is_active !== false ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

        </div>

        <div class="apple-modal-footer">
            <button class="apple-btn-cancel" onclick="closePromoModal()">ยกเลิก</button>
            <button class="apple-btn-save" onclick="savePromotion()">บันทึก</button>
        </div>

      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);

    // Restore select values
    if (promo.target_brand_id) document.getElementById('pBrand').value = promo.target_brand_id;
    if (promo.min_tier_id) document.getElementById('pTier').value = promo.min_tier_id;
    updatePromoRewardUI();
}

function updatePromoRewardUI() {
    const type = document.getElementById('pRewardType').value;
    const label = document.getElementById('pRewardValLabel');
    const wrap = document.getElementById('pRewardValWrap');
    if (type === 'discount_percent') { label.textContent = 'ส่วนลด (%)'; wrap.style.display = ''; }
    else if (type === 'discount_fixed') { label.textContent = 'ส่วนลด (฿)'; wrap.style.display = ''; }
    else { wrap.style.display = 'none'; }
}

function closePromoModal() {
    const m = document.getElementById('promoModal');
    if (m) m.remove();
}

async function savePromotion() {
    const body = {
        name: document.getElementById('pName').value.trim(),
        promo_type: document.getElementById('pRewardType').value,
        condition_min_spend: parseFloat(document.getElementById('pMinSpend').value) || 0,
        condition_min_qty: parseInt(document.getElementById('pMinQty').value) || 0,
        reward_type: document.getElementById('pRewardType').value,
        reward_value: parseFloat(document.getElementById('pRewardVal').value) || 0,
        target_brand_id: document.getElementById('pBrand').value || null,
        min_tier_id: document.getElementById('pTier').value || null,
        start_date: document.getElementById('pStart').value || null,
        end_date: document.getElementById('pEnd').value || null,
        priority: parseInt(document.getElementById('pPriority').value) || 0,
        is_stackable: document.getElementById('pStackable').checked,
        once_per_user: document.getElementById('pOncePerUser').checked,
        is_active: document.getElementById('pActive').checked
    };
    if (!body.name) { showGlobalAlert('กรุณาระบุชื่อโปรโมชัน', 'error'); return; }
    const url = _editingPromoId ? `/api/admin/promotions/${_editingPromoId}` : '/api/admin/promotions';
    const method = _editingPromoId ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) {
            showGlobalAlert(_editingPromoId ? 'แก้ไขโปรโมชันเรียบร้อย' : 'สร้างโปรโมชันเรียบร้อย', 'success');
            closePromoModal();
            loadPromotions();
        } else {
            const d = await res.json();
            showGlobalAlert(d.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch { showGlobalAlert('เกิดข้อผิดพลาด', 'error'); }
}

async function togglePromotion(id, isActive) {
    const promo = _promoData.find(p => p.id === id);
    if (!promo) return;
    await fetch(`/api/admin/promotions/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ...promo, is_active: isActive })
    });
    loadPromotions();
}

async function deletePromotion(id) {
    if (!confirm('ลบโปรโมชันนี้?')) return;
    const res = await fetch(`/api/admin/promotions/${id}`, { method: 'DELETE' });
    if (res.ok) { showGlobalAlert('ลบเรียบร้อย', 'success'); loadPromotions(); }
    else showGlobalAlert('เกิดข้อผิดพลาด', 'error');
}

// ── Coupons ─────────────────────────────────────────────────────

async function loadCoupons() {
    try {
        const data = await fetch('/api/admin/coupons').then(r => r.json());
        _couponData = Array.isArray(data) ? data : [];
        const active = _couponData.filter(c => c.is_active).length;
        const totalUsed = _couponData.reduce((s, c) => s + (c.usage_count || 0), 0);
        document.getElementById('couponStats').innerHTML = `
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#fff;">${_couponData.length}</div>
                <div class="mkt-stat-lbl">ทั้งหมด</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#4ade80;">${active}</div>
                <div class="mkt-stat-lbl">กำลังใช้งาน</div>
            </div>
            <div class="mkt-stat-card">
                <div class="mkt-stat-val" style="color:#ffffff;">${totalUsed}</div>
                <div class="mkt-stat-lbl">ใช้ไปแล้ว</div>
            </div>
        `;
        if (!_couponData.length) {
            document.getElementById('couponTableWrap').innerHTML = `<div class="empty-state"><p>ยังไม่มีคูปอง — กดปุ่ม "สร้างคูปอง" เพื่อเริ่มต้น</p></div>`;
            return;
        }
        const typeColors = { percent: ['#7c3aed','#a78bfa'], fixed: ['#0e7490','#67e8f9'], free_shipping: ['#065f46','#6ee7b7'] };
        const typeLabels = { percent: 'ลด %', fixed: 'ลดคงที่', free_shipping: 'ส่งฟรี' };
        const cards = _couponData.map(c => {
            const [bg1, bg2] = typeColors[c.discount_type] || ['#4c1d95','#a78bfa'];
            const typeLabel = typeLabels[c.discount_type] || c.discount_type;
            const quota = c.total_quota > 0 ? `${c.usage_count || 0}/${c.total_quota}` : `${c.usage_count || 0}/∞`;
            const claimed = c.claimed_count || 0;
            const dateStr = c.end_date ? `หมดอายุ ${new Date(c.end_date).toLocaleDateString('th-TH')}` : 'ไม่มีกำหนด';
            const codeLen = (c.code || '').length;
            const codeFontSize = codeLen <= 7 ? '13px' : codeLen <= 10 ? '11px' : codeLen <= 14 ? '9px' : '8px';
            return `
            <div class="coupon-ticket" style="${!c.is_active ? 'opacity:0.5;' : ''}">
                <div class="coupon-ticket-left" style="background:linear-gradient(135deg,${bg1},${bg2});">
                    <div class="coupon-ticket-code" style="font-size:${codeFontSize};line-height:1.3;">${c.code}</div>
                    <div class="coupon-ticket-type">${typeLabel}</div>
                </div>
                <div class="coupon-ticket-right">
                    <div>
                        <div class="coupon-ticket-name">${c.name || _fmtCouponDiscount(c)}</div>
                        <div class="coupon-ticket-desc">${_fmtCouponDiscount(c)}${c.min_spend > 0 ? ' · ขั้นต่ำ ฿'+Number(c.min_spend).toLocaleString() : ''}</div>
                        ${c.applies_to && c.applies_to !== 'all' ? `<div style="margin-top:3px;font-size:10px;color:rgba(255,255,255,0.5);">${c.applies_to === 'brand' ? '🏷️ แบรนด์' : '📦 สินค้า'}: ${(c.applies_to_names && c.applies_to_names.length) ? c.applies_to_names.slice(0,2).join(', ') + (c.applies_to_names.length > 2 ? ` +${c.applies_to_names.length-2}` : '') : (c.applies_to_ids?.length || 0) + ' รายการ'}</div>` : ''}
                    </div>
                    <div class="coupon-ticket-footer">
                        <div>
                            <div class="coupon-ticket-meta">${dateStr}</div>
                            <div class="coupon-ticket-meta">เก็บแล้ว ${claimed} · ใช้แล้ว ${quota}</div>
                        </div>
                        <div class="coupon-ticket-actions">
                            <label class="toggle-switch">
                                <input type="checkbox" ${c.is_active ? 'checked' : ''} onchange="toggleCoupon(${c.id}, this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                            <button class="action-btn btn-review" onclick="openCouponModal(${c.id})">แก้ไข</button>
                            <button class="action-btn" style="background:rgba(34,197,94,0.25);color:#fff;" onclick="openDistributeModal(${c.id})" title="แจกให้สมาชิก">แจก</button>
                            <button class="action-btn" style="background:rgba(239,68,68,0.25);color:#fff;" onclick="deleteCoupon(${c.id})">ลบ</button>
                        </div>
                    </div>
                </div>
            </div>`;
        }).join('');
        document.getElementById('couponTableWrap').innerHTML = `<div class="coupon-grid">${cards}</div>`;
    } catch (e) {
        document.getElementById('couponTableWrap').innerHTML = `<div class="empty-state"><p>เกิดข้อผิดพลาด</p></div>`;
    }
}

async function openCouponModal(id = null) {
    _editingCouponId = id;
    await _mktLoadMeta();
    const tierOptions = `<option value="">ทุกระดับ</option>` + _mktTiers.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    let c = {};
    if (id) c = _couponData.find(x => x.id === id) || {};

    const html = `
    <div id="couponModal" class="modal" style="display:flex; z-index:10005;">
      <div class="apple-modal-content">

        <div class="apple-modal-header">
            <h3 class="apple-modal-title">${id ? 'แก้ไขคูปอง' : 'สร้างคูปองใหม่'}</h3>
            <button class="apple-modal-close" onclick="closeCouponModal()">&times;</button>
        </div>

        <div class="apple-modal-body">

            <div class="apple-section" style="margin-top:16px;">
                <span class="apple-section-label">รหัส & ชื่อ</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">รหัสคูปอง <span style="color:#ec4899;">*</span></label>
                        <input id="cCode" class="apple-input apple-input-code" value="${c.code || ''}" placeholder="SALE20" ${id ? 'readonly' : ''}>
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ชื่อคูปอง</label>
                        <input id="cName" class="apple-input" value="${c.name || ''}" placeholder="ลด 20% สำหรับสมาชิก">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ส่วนลด</span>
                <div class="apple-row-2" style="margin-bottom:10px;">
                    <div class="apple-field">
                        <label class="apple-field-label">ประเภท</label>
                        <select id="cType" class="apple-select" onchange="updateCouponUI()">
                            <option value="percent" ${c.discount_type === 'percent' ? 'selected' : ''}>ลดเป็น %</option>
                            <option value="fixed" ${c.discount_type === 'fixed' ? 'selected' : ''}>ลดคงที่ (฿)</option>
                            <option value="free_shipping" ${c.discount_type === 'free_shipping' ? 'selected' : ''}>ส่งฟรี</option>
                        </select>
                    </div>
                    <div id="cValWrap" class="apple-field">
                        <label class="apple-field-label" id="cValLabel">มูลค่าส่วนลด</label>
                        <input id="cVal" class="apple-input" type="number" min="0" value="${c.discount_value || 0}">
                    </div>
                </div>
                <div id="cMaxWrap" class="apple-field">
                    <label class="apple-field-label">ลดสูงสุด (฿) <span class="apple-field-hint">0 = ไม่จำกัด</span></label>
                    <input id="cMax" class="apple-input" type="number" min="0" value="${c.max_discount || 0}">
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">เงื่อนไข</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">ซื้อขั้นต่ำ (฿)</label>
                        <input id="cMinSpend" class="apple-input" type="number" min="0" value="${c.min_spend || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">ระดับสมาชิกขั้นต่ำ</label>
                        <select id="cTier" class="apple-select">${tierOptions}</select>
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ใช้ได้กับ</span>
                <div class="apple-field" style="margin-bottom:10px;">
                    <label class="apple-field-label">ขอบเขตสินค้า</label>
                    <select id="cAppliesTo" class="apple-select" onchange="updateCouponAppliesTo()">
                        <option value="all" ${(!c.applies_to || c.applies_to === 'all') ? 'selected' : ''}>ทั้งหมด</option>
                        <option value="brand" ${c.applies_to === 'brand' ? 'selected' : ''}>เฉพาะแบรนด์</option>
                        <option value="product" ${c.applies_to === 'product' ? 'selected' : ''}>เฉพาะสินค้า</option>
                    </select>
                </div>
                <div id="cAppliesToPanel" style="display:none;">
                    <div id="cAppliesToSearch" style="margin-bottom:8px;">
                        <input id="cAppliesToSearchInput" class="apple-input" placeholder="ค้นหา..." oninput="filterCouponAppliesTo(this.value)" style="margin-bottom:6px;">
                    </div>
                    <div id="cAppliesToList" style="max-height:180px;overflow-y:auto;border:1px solid rgba(255,255,255,0.1);border-radius:10px;background:rgba(255,255,255,0.04);"></div>
                </div>
                <div id="cAppliesToSelected" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ขีดจำกัดการใช้งาน</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">จำนวนสิทธิ์ทั้งหมด <span class="apple-field-hint">0 = ไม่จำกัด</span></label>
                        <input id="cQuota" class="apple-input" type="number" min="0" value="${c.total_quota || 0}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">จำกัดต่อสมาชิก (ครั้ง)</label>
                        <input id="cPerUser" class="apple-input" type="number" min="1" value="${c.per_user_limit || 1}">
                    </div>
                </div>
            </div>

            <div class="apple-section">
                <span class="apple-section-label">ช่วงเวลา</span>
                <div class="apple-row-2">
                    <div class="apple-field">
                        <label class="apple-field-label">วันเริ่ม</label>
                        <input id="cStart" class="apple-input" type="datetime-local" value="${c.start_date ? c.start_date.substring(0,16) : ''}">
                    </div>
                    <div class="apple-field">
                        <label class="apple-field-label">วันสิ้นสุด</label>
                        <input id="cEnd" class="apple-input" type="datetime-local" value="${c.end_date ? c.end_date.substring(0,16) : ''}">
                    </div>
                </div>
            </div>

            <div class="apple-section" style="margin-bottom:20px;">
                <span class="apple-section-label">การตั้งค่า</span>
                <div class="apple-toggle-card">
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">ใช้ร่วมกับโปรโมชันได้</div>
                            <div class="apple-toggle-desc">ใช้คูปองนี้ซ้อนกับโปรโมชันอัตโนมัติได้</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="cStackable" ${c.is_stackable ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                    <div class="apple-toggle-row">
                        <div>
                            <div class="apple-toggle-label">เปิดใช้งาน</div>
                            <div class="apple-toggle-desc">คูปองจะสามารถนำไปใช้ได้ทันที</div>
                        </div>
                        <label class="toggle-switch"><input type="checkbox" id="cActive" ${c.is_active !== false ? 'checked' : ''}><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

        </div>

        <div class="apple-modal-footer">
            <button class="apple-btn-cancel" onclick="closeCouponModal()">ยกเลิก</button>
            <button class="apple-btn-save" onclick="saveCoupon()">บันทึก</button>
        </div>

      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    if (c.min_tier_id) document.getElementById('cTier').value = c.min_tier_id;
    updateCouponUI();
    _couponAppliesToItems = [];
    _couponSelectedIds = new Set((c.applies_to_ids || []).map(Number));
    updateCouponAppliesTo();
}

let _couponAppliesToItems = [];
let _couponSelectedIds = new Set();

async function updateCouponAppliesTo() {
    const val = document.getElementById('cAppliesTo')?.value;
    const panel = document.getElementById('cAppliesToPanel');
    if (!panel) return;
    if (val === 'all') {
        panel.style.display = 'none';
        _renderCouponAppliesToSelected();
        return;
    }
    panel.style.display = 'block';
    const list = document.getElementById('cAppliesToList');
    list.innerHTML = '<div style="padding:12px;text-align:center;color:rgba(255,255,255,0.4);font-size:12px;">กำลังโหลด...</div>';
    try {
        if (val === 'brand') {
            const r = await fetch('/api/brands', { credentials: 'include' });
            const data = await r.json();
            _couponAppliesToItems = (Array.isArray(data) ? data : (data.brands || [])).map(b => ({ id: b.id, name: b.name }));
        } else {
            const r = await fetch('/api/admin/products?limit=200', { credentials: 'include' });
            const data = await r.json();
            _couponAppliesToItems = (Array.isArray(data) ? data : (data.products || [])).map(p => ({ id: p.id, name: p.name }));
        }
        _renderCouponAppliesToList('');
    } catch(e) {
        list.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
    _renderCouponAppliesToSelected();
}

function filterCouponAppliesTo(q) {
    _renderCouponAppliesToList(q.toLowerCase());
}

function _renderCouponAppliesToList(q) {
    const list = document.getElementById('cAppliesToList');
    if (!list) return;
    const filtered = q ? _couponAppliesToItems.filter(x => x.name.toLowerCase().includes(q)) : _couponAppliesToItems;
    if (!filtered.length) {
        list.innerHTML = '<div style="padding:12px;text-align:center;color:rgba(255,255,255,0.4);font-size:12px;">ไม่พบรายการ</div>';
        return;
    }
    list.innerHTML = filtered.map(item => `
        <div onclick="toggleCouponAppliesItem(${item.id}, ${JSON.stringify(item.name).replace(/"/g,'&quot;')})"
             style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:10px;transition:background 0.1s;border-bottom:1px solid rgba(255,255,255,0.05);"
             onmouseover="this.style.background='rgba(255,255,255,0.07)'" onmouseout="this.style.background='transparent'">
            <div style="width:18px;height:18px;border-radius:4px;border:2px solid ${_couponSelectedIds.has(item.id) ? '#a855f7' : 'rgba(255,255,255,0.3)'};background:${_couponSelectedIds.has(item.id) ? '#a855f7' : 'transparent'};display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.15s;">
                ${_couponSelectedIds.has(item.id) ? '<svg width="10" height="10" viewBox="0 0 12 12"><polyline points="1,6 5,10 11,2" stroke="white" stroke-width="2" fill="none" stroke-linecap="round"/></svg>' : ''}
            </div>
            <span style="font-size:13px;color:rgba(255,255,255,0.9);">${item.name}</span>
        </div>`).join('');
}

function toggleCouponAppliesItem(id, name) {
    if (_couponSelectedIds.has(id)) {
        _couponSelectedIds.delete(id);
    } else {
        _couponSelectedIds.add(id);
    }
    const q = document.getElementById('cAppliesToSearchInput')?.value?.toLowerCase() || '';
    _renderCouponAppliesToList(q);
    _renderCouponAppliesToSelected();
}

function _renderCouponAppliesToSelected() {
    const sel = document.getElementById('cAppliesToSelected');
    if (!sel) return;
    const val = document.getElementById('cAppliesTo')?.value;
    if (val === 'all' || _couponSelectedIds.size === 0) {
        sel.innerHTML = val === 'all' ? '<span style="font-size:12px;color:rgba(255,255,255,0.4);">ใช้ได้กับสินค้าทุกรายการ</span>' : '';
        return;
    }
    const allItems = _couponAppliesToItems;
    const tags = [..._couponSelectedIds].map(id => {
        const item = allItems.find(x => x.id === id);
        const name = item ? item.name : `#${id}`;
        return `<span style="background:rgba(168,85,247,0.25);border:1px solid rgba(168,85,247,0.4);border-radius:20px;padding:3px 10px;font-size:12px;color:#d8b4fe;display:flex;align-items:center;gap:4px;">
            ${name} <span onclick="toggleCouponAppliesItem(${id}, '')" style="cursor:pointer;opacity:0.7;font-size:14px;line-height:1;">&times;</span>
        </span>`;
    }).join('');
    sel.innerHTML = tags || '';
}

function updateCouponUI() {
    const type = document.getElementById('cType').value;
    const valWrap = document.getElementById('cValWrap');
    const maxWrap = document.getElementById('cMaxWrap');
    const label = document.getElementById('cValLabel');
    if (type === 'free_shipping') {
        valWrap.style.display = 'none';
        maxWrap.style.display = 'none';
    } else {
        valWrap.style.display = '';
        label.textContent = type === 'percent' ? 'ส่วนลด (%)' : 'ส่วนลด (฿)';
        maxWrap.style.display = type === 'percent' ? '' : 'none';
    }
}

function closeCouponModal() {
    const m = document.getElementById('couponModal');
    if (m) m.remove();
}

async function saveCoupon() {
    const appliesTo = document.getElementById('cAppliesTo')?.value || 'all';
    const body = {
        code: (document.getElementById('cCode').value || '').trim().toUpperCase(),
        name: (document.getElementById('cName').value || '').trim(),
        discount_type: document.getElementById('cType').value,
        discount_value: parseFloat(document.getElementById('cVal')?.value) || 0,
        max_discount: parseFloat(document.getElementById('cMax')?.value) || 0,
        min_spend: parseFloat(document.getElementById('cMinSpend').value) || 0,
        total_quota: parseInt(document.getElementById('cQuota').value) || 0,
        per_user_limit: parseInt(document.getElementById('cPerUser').value) || 1,
        min_tier_id: document.getElementById('cTier').value || null,
        start_date: document.getElementById('cStart').value || null,
        end_date: document.getElementById('cEnd').value || null,
        is_stackable: document.getElementById('cStackable').checked,
        is_active: document.getElementById('cActive').checked,
        applies_to: appliesTo,
        applies_to_ids: appliesTo !== 'all' ? [..._couponSelectedIds] : []
    };
    if (!body.code) { showGlobalAlert('กรุณาระบุรหัสคูปอง', 'error'); return; }
    const url = _editingCouponId ? `/api/admin/coupons/${_editingCouponId}` : '/api/admin/coupons';
    const method = _editingCouponId ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
        if (res.ok) {
            showGlobalAlert(_editingCouponId ? 'แก้ไขคูปองเรียบร้อย' : 'สร้างคูปองเรียบร้อย', 'success');
            closeCouponModal();
            loadCoupons();
        } else {
            const d = await res.json();
            showGlobalAlert(d.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch { showGlobalAlert('เกิดข้อผิดพลาด', 'error'); }
}

async function toggleCoupon(id, isActive) {
    const coupon = _couponData.find(c => c.id === id);
    if (!coupon) return;
    await fetch(`/api/admin/coupons/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ...coupon, is_active: isActive })
    });
    loadCoupons();
}

async function deleteCoupon(id) {
    if (!confirm('ลบคูปองนี้? สมาชิกที่เก็บไว้แล้วจะไม่สามารถใช้ได้อีก')) return;
    const res = await fetch(`/api/admin/coupons/${id}`, { method: 'DELETE' });
    if (res.ok) { showGlobalAlert('ลบเรียบร้อย', 'success'); loadCoupons(); }
    else showGlobalAlert('เกิดข้อผิดพลาด', 'error');
}

let _distributeCouponId = null;

async function openDistributeModal(id) {
    _distributeCouponId = id;
    const coupon = _couponData.find(c => c.id === id);
    if (!coupon) return;
    await _mktLoadMeta();
    const modal = document.getElementById('distributeCouponModal');
    if (!modal) return;
    document.getElementById('distributeCouponTitle').textContent = `แจกคูปอง: ${coupon.code}`;
    const tierList = document.getElementById('distributeTierList');
    tierList.innerHTML = _mktTiers.map(t => `
        <label style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">
            <input type="checkbox" value="${t.id}" class="distribute-tier-cb" style="width:16px;height:16px;accent-color:#a855f7;"
                   onchange="document.getElementById('distributeAllTiers').checked=false;_updateDistributePreview();">
            <span style="font-size:13px;color:#fff;">${t.name}</span>
        </label>`).join('');
    document.getElementById('distributePreviewText').textContent = 'เลือกระดับสมาชิกเพื่อดูจำนวน';
    document.getElementById('distributeConfirmBtn').textContent = 'แจก';
    document.getElementById('distributeConfirmBtn').disabled = false;
    modal.style.display = 'flex';
    await _updateDistributePreview();
}

async function _updateDistributePreview() {
    const cbs = document.querySelectorAll('.distribute-tier-cb:checked');
    const tierIds = Array.from(cbs).map(cb => cb.value);
    const params = tierIds.length ? `?tier_ids=${tierIds.join(',')}` : '';
    try {
        const r = await fetch(`/api/admin/coupons/${_distributeCouponId}/assign-preview${params}`);
        const d = await r.json();
        const count = d.count || 0;
        const tierLabel = tierIds.length ? `ระดับที่เลือก` : 'ทุกระดับ';
        document.getElementById('distributePreviewText').innerHTML =
            `<span style="color:rgba(255,255,255,0.6);">${tierLabel} — </span><span style="color:#a78bfa;font-weight:700;">${count} คน</span><span style="color:rgba(255,255,255,0.4);font-size:11px;"> ที่จะได้รับ (ข้ามคนที่มีอยู่แล้ว)</span>`;
        const btn = document.getElementById('distributeConfirmBtn');
        btn.textContent = count > 0 ? `แจก ${count} คน` : 'ไม่มีสมาชิกที่ต้องแจก';
        btn.disabled = count === 0;
    } catch {
        document.getElementById('distributePreviewText').textContent = 'โหลดจำนวนไม่สำเร็จ';
    }
}

function closeDistributeModal() {
    const modal = document.getElementById('distributeCouponModal');
    if (modal) modal.style.display = 'none';
    _distributeCouponId = null;
}

async function confirmDistribute() {
    if (!_distributeCouponId) return;
    const cbs = document.querySelectorAll('.distribute-tier-cb:checked');
    const tierIds = Array.from(cbs).map(cb => parseInt(cb.value));
    const btn = document.getElementById('distributeConfirmBtn');
    btn.disabled = true;
    btn.textContent = 'กำลังแจก...';
    try {
        const res = await fetch(`/api/admin/coupons/${_distributeCouponId}/assign`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tier_ids: tierIds })
        });
        const data = await res.json();
        if (res.ok) {
            closeDistributeModal();
            showGlobalAlert(`แจกคูปองให้ ${data.assigned} คน เรียบร้อย`, 'success');
            loadCoupons();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
            btn.disabled = false;
            btn.textContent = 'แจก';
        }
    } catch {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
        btn.disabled = false;
        btn.textContent = 'แจก';
    }
}

// ==================== END MARKETING MODULE ====================

// ==================== STOCK REPORT ====================

const _SIZE_ORDER = ['XS','S','M','L','XL','2XL','3XL','4XL','5XL','FREESIZE','FREE SIZE','ONE SIZE','ONESIZE'];

function _srParseVariant(variantName, skuCode) {
    const opts = {};
    (variantName || '').split(' / ').forEach(part => {
        const idx = part.indexOf(':');
        if (idx > 0) {
            opts[part.substring(0, idx).trim().toLowerCase()] = part.substring(idx + 1).trim();
        }
    });
    let size = opts['ขนาด'] || opts['ไซส์'] || opts['size'] || opts['ไซ'] || opts['sz'] || null;
    const color = opts['สี'] || opts['color'] || opts['ลาย'] || opts['pattern'] || null;

    if (!size && skuCode) {
        const parts = (skuCode || '').split('-');
        const last = (parts[parts.length - 1] || '').toUpperCase();
        if (_SIZE_ORDER.indexOf(last) >= 0) size = last;
    }

    return { size, color };
}

function _srSortSizes(sizes) {
    return [...sizes].sort((a, b) => {
        if (a === 'No Size') return 1;
        if (b === 'No Size') return -1;
        const ai = _SIZE_ORDER.indexOf(a.toUpperCase());
        const bi = _SIZE_ORDER.indexOf(b.toUpperCase());
        if (ai >= 0 && bi >= 0) return ai - bi;
        if (ai >= 0) return -1;
        if (bi >= 0) return 1;
        return a.localeCompare(b);
    });
}

function openStockReport() {
    const products = filteredProducts || [];
    if (!products.length) { showGlobalAlert('ไม่มีสินค้าที่จะสร้างรายงาน', 'error'); return; }

    const allSizesSet = new Set();
    const rows = [];

    products.forEach(p => {
        const skus = p.skus || [];
        const colorMap = {};

        skus.forEach(sku => {
            const { size, color } = _srParseVariant(sku.variant_name || '', sku.sku_code || '');
            const sizeKey = size ? size.toUpperCase() : 'No Size';
            const colorKey = color || '__none__';
            allSizesSet.add(sizeKey);
            if (!colorMap[colorKey]) colorMap[colorKey] = {};
            colorMap[colorKey][sizeKey] = (colorMap[colorKey][sizeKey] || 0) + (sku.stock || 0);
        });

        const colors = Object.keys(colorMap);
        const multiColor = colors.filter(c => c !== '__none__').length > 1;

        colors.forEach(colorKey => {
            const label = multiColor && colorKey !== '__none__'
                ? `${p.name} <span class="sr-color-label">(${colorKey})</span>`
                : p.name;
            rows.push({ label, sizeStock: colorMap[colorKey] });
        });

        if (skus.length === 0) rows.push({ label: p.name, sizeStock: {} });
    });

    const sortedSizes = _srSortSizes([...allSizesSet]);

    const colTotals = {};
    sortedSizes.forEach(s => { colTotals[s] = 0; });
    let grandTotal = 0;

    const tbody = rows.map(row => {
        let rowTotal = 0;
        const cells = sortedSizes.map(s => {
            const v = row.sizeStock[s] || 0;
            rowTotal += v;
            colTotals[s] += v;
            return v > 0 ? `<td>${v}</td>` : `<td class="dash">-</td>`;
        }).join('');
        grandTotal += rowTotal;
        return `<tr><td>${row.label}</td>${cells}<td class="total-col">${rowTotal || '-'}</td></tr>`;
    }).join('');

    const sumCells = sortedSizes.map(s => `<td>${colTotals[s] || '-'}</td>`).join('');
    const thead = `<thead><tr><th>รายการสินค้า</th>${sortedSizes.map(s => `<th>${s}</th>`).join('')}<th>รวม (ตัว)</th></tr></thead>`;
    const tfoot = `<tfoot><tr class="sum-row"><td>รวมทั้งหมด</td>${sumCells}<td>${grandTotal}</td></tr></tfoot>`;

    const dateStr = new Date().toLocaleDateString('th-TH', { year: 'numeric', month: 'long', day: 'numeric' });
    const brandEl = document.getElementById('filterBrand');
    const brandLabel = brandEl && brandEl.value ? ` · แบรนด์: ${brandEl.options[brandEl.selectedIndex].text}` : '';
    const statusTab = document.querySelector('.status-tab.active');
    const statusLabel = statusTab ? ` · สถานะ: ${statusTab.textContent.replace(/\d+/g, '').trim()}` : '';
    const searchVal = (document.getElementById('searchProduct')?.value || '').trim();
    const searchLabel = searchVal ? ` · ค้นหา: "${searchVal}"` : '';

    document.getElementById('srMeta').textContent =
        `สร้างเมื่อ: ${dateStr} · แสดง ${rows.length} รายการ${brandLabel}${statusLabel}${searchLabel}`;
    document.getElementById('srTable').innerHTML = thead + `<tbody>${tbody}</tbody>` + tfoot;
    document.getElementById('stockReportModal').classList.add('open');
}

function closeStockReport() {
    document.getElementById('stockReportModal').classList.remove('open');
}

function printStockReport() {
    window.print();
}

// ==================== CUSTOMER DATA PAGE ====================

let _allCustomers = [];
let _customerBrands = [];
let _customerProducts = [];
let _phoneCheckTimer = null;

const PLATFORM_LABEL = {
    shopee: '🛍️ Shopee', lazada: '📦 Lazada', tiktok: '🎵 TikTok',
    line: '💬 LINE', facebook: '📘 Facebook', onsale: '🏪 หน้าร้าน', other: '🔹 อื่นๆ'
};
const TAG_LABEL = { frequent: '🌟 ประจำ', new: '🆕 ใหม่', inactive: '💤 ไม่ active', reseller: '👤 ตัวแทน' };
const TAG_COLOR = { frequent: '#f59e0b', new: '#10b981', inactive: '#6b7280', reseller: '#7c3aed' };

async function loadCustomers() {
    try {
        const res = await fetch('/api/admin/customers');
        if (!res.ok) throw new Error(await res.text());
        _allCustomers = await res.json();
        renderCustomersTable(_allCustomers);
    } catch (e) {
        document.getElementById('customersTableContainer').innerHTML =
            `<div style="text-align:center;padding:40px;color:#f87171;">โหลดข้อมูลล้มเหลว: ${e.message}</div>`;
    }
}

function filterCustomers() {
    const q = (document.getElementById('customerSearchInput')?.value || '').toLowerCase();
    const platform = document.getElementById('customerPlatformFilter')?.value || '';
    const tag = document.getElementById('customerTagFilter')?.value || '';

    const filtered = _allCustomers.filter(c => {
        const matchQ = !q || (c.name || '').toLowerCase().includes(q) ||
            (c.phone || '').includes(q) || (c.province || '').toLowerCase().includes(q) ||
            (c.district || '').toLowerCase().includes(q) || (c.note || '').toLowerCase().includes(q);
        const matchPlatform = !platform || (c.platforms || []).includes(platform);
        const matchTag = !tag || c.auto_tag === tag || (c.tags || []).includes(tag);
        return matchQ && matchPlatform && matchTag;
    });
    renderCustomersTable(filtered);
}

function renderCustomersTable(customers) {
    const badge = document.getElementById('customerCountBadge');
    if (badge) badge.textContent = `${customers.length} คน`;

    if (!customers.length) {
        document.getElementById('customersTableContainer').innerHTML =
            `<div style="text-align:center;padding:60px;color:#8e8e93;">ไม่พบลูกค้า</div>`;
        return;
    }

    const TAG_BG   = { frequent: '#fff7ed', new: '#f0fdf4', inactive: '#f9fafb', reseller: '#f5f3ff' };
    const TAG_TEXT = { frequent: '#c2410c', new: '#15803d', inactive: '#6b7280', reseller: '#7c3aed' };

    const rows = customers.map(c => {
        const tagLabel = TAG_LABEL[c.auto_tag] || '';
        const tagBg   = TAG_BG[c.auto_tag]   || '#f3f4f6';
        const tagText = TAG_TEXT[c.auto_tag]  || '#6b7280';
        const isReseller = c.source_type === 'reseller';
        const platforms = (c.platforms || []).map(p =>
            `<span style="font-size:11px;background:#f3f4f6;color:#374151;padding:2px 7px;border-radius:5px;white-space:nowrap;">${PLATFORM_LABEL[p] || p}</span>`
        ).join(' ');
        const lastOrder = c.last_order_at
            ? new Date(c.last_order_at).toLocaleDateString('th-TH', { day:'2-digit', month:'short', year:'2-digit' })
            : '—';
        const spent = c.total_spent > 0 ? `฿${c.total_spent.toLocaleString('th-TH', { maximumFractionDigits: 0 })}` : '—';
        const subNote = isReseller
            ? `<div style="font-size:11px;color:#7c3aed;margin-top:2px;">ตัวแทน: ${c.reseller_name || '—'}</div>`
            : (c.note ? `<div style="font-size:11px;color:#8e8e93;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;">${c.note}</div>` : '');
        const actionBtns = isReseller
            ? `<span style="font-size:11px;color:#c7c7cc;">จัดการโดยตัวแทน</span>`
            : `<div style="display:flex;gap:6px;">
                <button onclick="openEditCustomerModal(${c.id})" style="padding:5px 12px;font-size:12px;font-weight:500;border-radius:8px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#f9fafb'" onmouseout="this.style.background='#fff'">แก้ไข</button>
                <button onclick="deleteCustomer(${c.id},'${(c.name||'ลูกค้า').replace(/'/g,'')}')" style="padding:5px 10px;font-size:12px;font-weight:500;border-radius:8px;border:1px solid #fecaca;background:#fff;color:#ef4444;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#fef2f2'" onmouseout="this.style.background='#fff'" title="ลบลูกค้า">
                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                </button>
               </div>`;
        return `<tr class="cust-row">
            <td style="padding:12px 14px;vertical-align:middle;max-width:200px;">
                <div style="font-weight:600;font-size:14px;color:#1d1d1f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${c.name || '<span style="color:#c7c7cc">ไม่มีชื่อ</span>'}</div>
                ${subNote}
            </td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:13px;color:#3a3a3c;white-space:nowrap;">${c.phone || '—'}</td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:12px;color:#6e6e73;">${[c.province, c.district].filter(Boolean).join(', ') || '—'}</td>
            <td style="padding:12px 14px;vertical-align:middle;text-align:center;font-size:13px;font-weight:600;color:#1d1d1f;">${isReseller ? '<span style="color:#c7c7cc">—</span>' : c.order_count}</td>
            <td style="padding:12px 14px;vertical-align:middle;text-align:right;font-size:13px;font-weight:600;color:#1d1d1f;">${isReseller ? '<span style="color:#c7c7cc">—</span>' : spent}</td>
            <td style="padding:12px 14px;vertical-align:middle;">
                <div style="display:flex;flex-wrap:wrap;gap:3px;">${platforms || '<span style="color:#c7c7cc;font-size:12px;">—</span>'}</div>
            </td>
            <td style="padding:12px 14px;vertical-align:middle;font-size:12px;color:#6e6e73;white-space:nowrap;">${lastOrder}</td>
            <td style="padding:12px 14px;vertical-align:middle;">
                <span style="font-size:11px;background:${tagBg};color:${tagText};padding:3px 9px;border-radius:20px;font-weight:500;white-space:nowrap;">${tagLabel}</span>
            </td>
            <td style="padding:12px 14px;vertical-align:middle;">${actionBtns}</td>
        </tr>`;
    }).join('');

    document.getElementById('customersTableContainer').innerHTML = `
        <div style="background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08),0 0 0 1px rgba(0,0,0,0.05);overflow:hidden;">
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="background:#f9fafb;border-bottom:1px solid #e5e7eb;">
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">ชื่อ</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">เบอร์โทร</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">พื้นที่</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:center;">ออเดอร์</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:right;">ยอดรวม</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">แพลตฟอร์ม</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">สั่งล่าสุด</th>
                    <th style="padding:11px 14px;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;text-align:left;">ประเภท</th>
                    <th style="padding:11px 14px;"></th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
        </div>
        </div>`;

    document.querySelectorAll('#customersTableContainer .cust-row').forEach(tr => {
        tr.style.borderBottom = '1px solid #f3f4f6';
        tr.style.transition = 'background 0.12s';
        tr.addEventListener('mouseenter', () => tr.style.background = '#fafafa');
        tr.addEventListener('mouseleave', () => tr.style.background = '');
    });
}

async function deleteCustomer(id, name) {
    if (!confirm(`ลบลูกค้า "${name}" ออกจากระบบ?\nออเดอร์ที่เกี่ยวข้องจะไม่ถูกลบ`)) return;
    try {
        const res = await fetch(`/api/admin/customers/${id}`, { method: 'DELETE', credentials: 'include' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'ลบไม่สำเร็จ');
        showGlobalAlert('ลบลูกค้าสำเร็จ', 'success');
        _allCustomers = _allCustomers.filter(c => !(c.source_type === 'admin' && c.id === id));
        filterCustomers();
    } catch (e) {
        showGlobalAlert(e.message, 'error');
    }
}

function openAddCustomerModal() {
    document.getElementById('editCustomerId').value = '';
    document.getElementById('addCustomerModalTitle').textContent = 'เพิ่มลูกค้าใหม่';
    document.getElementById('custName').value = '';
    document.getElementById('custPhone').value = '';
    document.getElementById('custAddress').value = '';
    document.getElementById('custSubdistrict').value = '';
    document.getElementById('custDistrict').value = '';
    document.getElementById('custProvince').value = '';
    document.getElementById('custPostal').value = '';
    document.getElementById('custSource').value = 'manual';
    document.getElementById('custNote').value = '';
    document.getElementById('custDuplicateWarning').style.display = 'none';
    document.getElementById('customerScanStatus').style.display = 'none';
    const prevImg = document.getElementById('custLabelPreview');
    if (prevImg) { prevImg.src = ''; prevImg.style.display = 'none'; }
    document.getElementById('addCustomerModal').style.display = 'flex';
    _labelPasteContext = 'customer';

    const phoneInput = document.getElementById('custPhone');
    phoneInput.oninput = () => {
        clearTimeout(_phoneCheckTimer);
        _phoneCheckTimer = setTimeout(() => checkCustomerPhoneDuplicate(phoneInput.value), 600);
    };
}

function openEditCustomerModal(id) {
    const c = _allCustomers.find(x => x.id === id);
    if (!c) return;
    document.getElementById('editCustomerId').value = c.id;
    document.getElementById('addCustomerModalTitle').textContent = 'แก้ไขข้อมูลลูกค้า';
    document.getElementById('custName').value = c.name || '';
    document.getElementById('custPhone').value = c.phone || '';
    document.getElementById('custAddress').value = c.address || '';
    document.getElementById('custSubdistrict').value = c.subdistrict || '';
    document.getElementById('custDistrict').value = c.district || '';
    document.getElementById('custProvince').value = c.province || '';
    document.getElementById('custPostal').value = c.postal_code || '';
    document.getElementById('custSource').value = c.source || 'manual';
    document.getElementById('custNote').value = c.note || '';
    document.getElementById('custDuplicateWarning').style.display = 'none';
    document.getElementById('customerScanStatus').style.display = 'none';
    document.getElementById('addCustomerModal').style.display = 'flex';
    _labelPasteContext = 'customer';

    const phoneInput = document.getElementById('custPhone');
    const origPhone = c.phone || '';
    phoneInput.oninput = () => {
        clearTimeout(_phoneCheckTimer);
        if (phoneInput.value !== origPhone) {
            _phoneCheckTimer = setTimeout(() => checkCustomerPhoneDuplicate(phoneInput.value), 600);
        } else {
            document.getElementById('custDuplicateWarning').style.display = 'none';
        }
    };
}

function closeAddCustomerModal() {
    document.getElementById('addCustomerModal').style.display = 'none';
    _labelPasteContext = null;
}

async function checkCustomerPhoneDuplicate(phone) {
    if (!phone || phone.length < 9) {
        document.getElementById('custDuplicateWarning').style.display = 'none';
        return;
    }
    try {
        const res = await fetch(`/api/admin/customers/check-phone?phone=${encodeURIComponent(phone)}`);
        const data = await res.json();
        const warn = document.getElementById('custDuplicateWarning');
        if (data.exists) {
            warn.style.display = 'block';
            warn.innerHTML = `<strong>⚠️ เบอร์นี้มีในระบบแล้ว</strong> (${data.name || 'ไม่มีชื่อ'}) — จะอัปเดตข้อมูลลูกค้าเดิม`;
        } else {
            warn.style.display = 'none';
        }
    } catch {}
}

async function handleCustomerLabelUpload(input) {
    if (input.files && input.files[0]) await _processLabelFile(input.files[0], 'customer');
}

async function saveCustomer() {
    const btn = document.getElementById('btnSaveCustomer');
    btn.disabled = true;
    btn.textContent = 'กำลังบันทึก...';

    const payload = {
        id: document.getElementById('editCustomerId').value || null,
        name: document.getElementById('custName').value.trim(),
        phone: document.getElementById('custPhone').value.trim(),
        address: document.getElementById('custAddress').value.trim(),
        subdistrict: document.getElementById('custSubdistrict').value.trim(),
        district: document.getElementById('custDistrict').value.trim(),
        province: document.getElementById('custProvince').value.trim(),
        postal_code: document.getElementById('custPostal').value.trim(),
        source: document.getElementById('custSource').value,
        note: document.getElementById('custNote').value.trim()
    };

    if (!payload.name && !payload.phone && !payload.address) {
        showAlert('กรุณากรอกชื่อ, เบอร์โทร หรือที่อยู่ อย่างน้อย 1 อย่าง', 'error');
        btn.disabled = false;
        btn.textContent = 'บันทึกลูกค้า';
        return;
    }

    try {
        const res = await fetch('/api/admin/customers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'บันทึกล้มเหลว');
        showAlert('บันทึกข้อมูลลูกค้าสำเร็จ', 'success');
        closeAddCustomerModal();
        loadCustomers();
    } catch (e) {
        showAlert(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'บันทึกลูกค้า';
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('addCustomerModal');
        if (modal && modal.style.display !== 'none') closeAddCustomerModal();
    }
});

document.addEventListener('paste', (e) => {
    if (!_labelPasteContext) return;
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
        if (item.type.startsWith('image/')) {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) _processLabelFile(file, _labelPasteContext);
            break;
        }
    }
});

// ==================== END CUSTOMER DATA PAGE ====================

// ==================== END STOCK REPORT ====================
