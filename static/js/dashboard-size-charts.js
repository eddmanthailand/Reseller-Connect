const SizeCharts = (() => {
  let _columns = [
    { name: 'ขนาด', unit: '' },
    { name: 'รอบอก', unit: 'นิ้ว' },
    { name: 'รอบเอว', unit: 'นิ้ว' },
    { name: 'รอบสะโพก', unit: 'นิ้ว' }
  ];
  let _rows = [];
  let _allProducts = [];
  let _selectedProductIds = new Set();
  let _filterText = '';
  let _fabricType = 'non-stretch';
  let _allowances = { chest: 1, waist: 1, hip: 1.5 };

  const UNITS = ['', 'ซม.', 'นิ้ว', 'กก.', 'ม.', 'มม.'];

  function _colName(c) { return typeof c === 'object' ? (c.name || '') : (c || ''); }
  function _colUnit(c) { return typeof c === 'object' ? (c.unit || '') : ''; }
  function _toColObj(c) { return typeof c === 'object' ? c : { name: c || '', unit: '' }; }

  function _toast(msg, type = 'success') {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:10px;color:#fff;font-size:14px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.2);background:${type === 'success' ? '#10b981' : '#ef4444'};`;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  function _unitSelect(colIdx, currentUnit) {
    const opts = UNITS.map(u =>
      `<option value="${u}" ${u === currentUnit ? 'selected' : ''}>${u || '— ไม่ระบุหน่วย'}</option>`
    ).join('');
    return `<select onchange="SizeCharts.updateColUnit(${colIdx},this.value)"
      style="margin-top:4px;border:1px solid #d1d5db;border-radius:5px;font-size:11px;padding:2px 4px;color:#6b7280;background:#f9fafb;cursor:pointer;width:100%;max-width:90px;"
      title="หน่วยกำกับ">
      ${opts}
    </select>`;
  }

  function _renderTable() {
    const thead = document.getElementById('sc-thead');
    const tbody = document.getElementById('sc-tbody');
    if (!thead || !tbody) return;

    thead.innerHTML = `<tr>${_columns.map((c, i) => {
      const name = _colName(c);
      const unit = _colUnit(c);
      return `<th style="padding:8px 10px;text-align:left;font-size:13px;font-weight:600;color:#374151;white-space:nowrap;border-bottom:1px solid #e5e7eb;vertical-align:top;">
        ${i === 0
          ? `<span style="color:#6b7280;">ขนาด</span><div style="font-size:11px;color:#9ca3af;margin-top:4px;">เช่น SS, S, M</div>`
          : `<div style="display:flex;align-items:center;gap:4px;">
               <input value="${name}" onchange="SizeCharts.updateColName(${i},this.value)"
                 style="border:none;background:transparent;font-weight:600;font-size:13px;width:80px;outline:none;color:#374151;">
               ${i > 0 ? `<button onclick="SizeCharts.removeCol(${i})" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:12px;padding:0;" title="ลบคอลัมน์">✕</button>` : ''}
             </div>
             ${_unitSelect(i, unit)}`
        }
      </th>`;
    }).join('')}
      <th style="padding:8px;width:40px;"></th>
    </tr>`;

    tbody.innerHTML = _rows.map((row, ri) => `
      <tr style="border-bottom:1px solid #f3f4f6;">
        <td style="padding:6px 8px;">
          <input value="${row.size}" onchange="SizeCharts.updateCell(${ri},'size',this.value)"
            style="border:1px solid #e5e7eb;border-radius:6px;padding:5px 8px;font-size:13px;width:70px;text-align:center;font-weight:600;">
        </td>
        ${(row.values || []).map((v, vi) => `
          <td style="padding:6px 8px;">
            <input value="${v}" onchange="SizeCharts.updateCell(${ri},${vi},this.value)"
              style="border:1px solid #e5e7eb;border-radius:6px;padding:5px 8px;font-size:13px;width:80px;">
          </td>`).join('')}
        <td style="padding:6px 8px;text-align:center;">
          <button onclick="SizeCharts.removeRow(${ri})" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:14px;" title="ลบแถว">🗑</button>
        </td>
      </tr>`).join('');
  }

  function _syncAllowanceInputs() {
    const ft = document.getElementById('sc-fabric-type');
    const ac = document.getElementById('sc-allowance-chest');
    const aw = document.getElementById('sc-allowance-waist');
    const ah = document.getElementById('sc-allowance-hip');
    if (ft) ft.value = _fabricType;
    if (ac) ac.value = _allowances.chest;
    if (aw) aw.value = _allowances.waist;
    if (ah) ah.value = _allowances.hip;
  }

  function updateFabricType(val) {
    _fabricType = val;
    if (val === 'stretch') {
      _allowances = { chest: 1, waist: 0.5, hip: 1 };
    } else {
      _allowances = { chest: 1, waist: 1, hip: 1.5 };
    }
    _syncAllowanceInputs();
  }

  function updateAllowance(key, val) {
    _allowances[key] = parseFloat(val) || 0;
  }

  function _renderProductPicker() {
    const el = document.getElementById('sc-products-list');
    if (!el || !_allProducts.length) return;
    const q = _filterText.trim().toLowerCase();
    const filtered = q ? _allProducts.filter(p => p.name.toLowerCase().includes(q)) : _allProducts;
    if (!filtered.length) {
      el.innerHTML = `<div style="padding:12px;color:#9ca3af;font-size:13px;">ไม่พบสินค้าที่ค้นหา "${_filterText}"</div>`;
      return;
    }
    el.innerHTML = filtered.map(p => {
      const checked = _selectedProductIds.has(p.id);
      const otherChart = (!checked && p.chart_group_name) ? `<span style="font-size:11px;color:#f59e0b;margin-left:4px;">(${p.chart_group_name})</span>` : '';
      return `<label style="display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid #f3f4f6;cursor:pointer;user-select:none;background:${checked ? '#f5f3ff' : '#fff'};" onmouseenter="if(!${checked})this.style.background='#fafafa'" onmouseleave="this.style.background='${checked ? '#f5f3ff' : '#fff'}'">
        <input type="checkbox" ${checked ? 'checked' : ''} style="width:16px;height:16px;accent-color:#7c3aed;cursor:pointer;flex-shrink:0;" onchange="SizeCharts.toggleProduct(${p.id},this)">
        <span style="font-size:13px;color:#374151;flex:1;">${p.name}</span>${otherChart}
      </label>`;
    }).join('');
    _renderSelectedDisplay();
  }

  function _renderSelectedDisplay() {
    const countEl = document.getElementById('sc-selected-count');
    const dispEl  = document.getElementById('sc-selected-display');
    if (!dispEl) return;
    const selectedProds = _allProducts.filter(p => _selectedProductIds.has(p.id));
    if (countEl) countEl.textContent = `เลือกแล้ว ${selectedProds.length} รายการ:`;
    if (!selectedProds.length) {
      dispEl.innerHTML = `<span style="font-size:12px;color:#9ca3af;">— ยังไม่ได้เลือกสินค้า</span>`;
      return;
    }
    dispEl.innerHTML = selectedProds.map(p =>
      `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px 3px 10px;background:#ede9fe;border:1px solid #a78bfa;border-radius:20px;font-size:12px;color:#5b21b6;">
        ${p.name}
        <span onclick="SizeCharts.toggleProduct(${p.id},null)" style="cursor:pointer;font-size:14px;line-height:1;color:#7c3aed;margin-left:2px;">&times;</span>
      </span>`
    ).join('');
  }

  function filterProducts(val) {
    _filterText = val || '';
    _renderProductPicker();
  }

  async function _loadProducts() {
    try {
      const res = await fetch('/api/admin/products-for-size-chart');
      _allProducts = await res.json();
    } catch (e) {
      _allProducts = [];
    }
  }

  function _fabricLabel(ft) {
    return ft === 'stretch' ? '🟢 ผ้ายืด' : '🔵 ผ้าไม่ยืด';
  }

  async function load() {
    const el = document.getElementById('size-charts-list');
    if (!el) return;
    try {
      const res = await fetch('/api/admin/size-chart-groups');
      const groups = await res.json();
      if (!groups.length) {
        el.innerHTML = `<div style="text-align:center;padding:60px 20px;color:#9ca3af;grid-column:1/-1;">
          <div style="font-size:48px;margin-bottom:16px;">📐</div>
          <p style="font-size:16px;font-weight:600;color:#6b7280;">ยังไม่มีตารางขนาด</p>
          <p style="font-size:14px;">กดปุ่ม "สร้างตารางขนาดใหม่" เพื่อเริ่มต้น</p>
        </div>`;
        return;
      }
      el.innerHTML = groups.map(g => {
        const cols = Array.isArray(g.columns) ? g.columns : JSON.parse(g.columns || '[]');
        const rows = Array.isArray(g.rows) ? g.rows : JSON.parse(g.rows || '[]');
        const allowances = g.allowances || { chest: 1, waist: 1, hip: 1.5 };
        const sizes = rows.map(r => r.size).join(', ') || '-';
        const colLabels = cols.filter(c => _colName(c) !== 'ขนาด').map(c => {
          const n = _colName(c); const u = _colUnit(c);
          return u ? `${n} (${u})` : n;
        }).join(' | ');
        const fabricTag = g.fabric_type === 'stretch'
          ? `<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">ผ้ายืด</span>`
          : `<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">ผ้าไม่ยืด</span>`;
        const allowText = `อก +${allowances.chest}" | เอว +${allowances.waist}" | สะโพก +${allowances.hip}"`;
        return `<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
            <div>
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <h3 style="margin:0;font-size:16px;font-weight:700;color:#1f2937;">${g.name}</h3>
                ${fabricTag}
              </div>
              ${g.description ? `<p style="margin:0 0 4px;font-size:13px;color:#6b7280;">${g.description}</p>` : ''}
              <p style="margin:0;font-size:12px;color:#9ca3af;">เผื่อ: ${allowText}</p>
            </div>
            <div style="display:flex;gap:8px;flex-shrink:0;margin-left:8px;">
              <button onclick="SizeCharts.openEditModal(${g.id})" style="background:#f3f4f6;border:1px solid #d1d5db;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px;">แก้ไข</button>
              <button onclick="SizeCharts.deleteGroup(${g.id},'${g.name}')" style="background:#fef2f2;border:1px solid #fca5a5;color:#ef4444;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px;">ลบ</button>
            </div>
          </div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">
            คอลัมน์: ${colLabels} &nbsp;•&nbsp; ไซส์: ${sizes}
          </div>
          <div style="font-size:13px;">
            <span style="background:#ede9fe;color:#7c3aed;padding:3px 10px;border-radius:20px;font-weight:600;">${g.product_count} สินค้า</span>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      el.innerHTML = `<div style="color:#ef4444;padding:20px;">เกิดข้อผิดพลาด: ${e.message}</div>`;
    }
  }

  function openCreateModal() {
    document.getElementById('size-chart-modal-title').textContent = 'สร้างตารางขนาดใหม่';
    document.getElementById('sc-edit-id').value = '';
    document.getElementById('sc-name').value = '';
    document.getElementById('sc-description').value = '';
    _fabricType = 'non-stretch';
    _allowances = { chest: 1, waist: 1, hip: 1.5 };
    _syncAllowanceInputs();
    _columns = [
      { name: 'ขนาด', unit: '' },
      { name: 'รอบอก', unit: 'นิ้ว' },
      { name: 'รอบเอว', unit: 'นิ้ว' },
      { name: 'รอบสะโพก', unit: 'นิ้ว' }
    ];
    _rows = [
      { size: 'SS', values: ['', '', ''] },
      { size: 'S',  values: ['', '', ''] },
      { size: 'M',  values: ['', '', ''] },
      { size: 'L',  values: ['', '', ''] },
      { size: 'XL', values: ['', '', ''] },
      { size: '2XL',values: ['', '', ''] },
    ];
    _selectedProductIds = new Set();
    _filterText = '';
    const searchEl = document.getElementById('sc-product-search');
    if (searchEl) searchEl.value = '';
    _renderTable();
    _loadProducts().then(() => _renderProductPicker());
    document.getElementById('size-chart-modal').style.display = 'block';
  }

  async function openEditModal(id) {
    try {
      const res = await fetch(`/api/admin/size-chart-groups/${id}`);
      const g = await res.json();
      document.getElementById('size-chart-modal-title').textContent = 'แก้ไขตารางขนาด';
      document.getElementById('sc-edit-id').value = g.id;
      document.getElementById('sc-name').value = g.name;
      document.getElementById('sc-description').value = g.description || '';
      _fabricType = g.fabric_type || 'non-stretch';
      _allowances = g.allowances || { chest: 1, waist: 1, hip: 1.5 };
      _syncAllowanceInputs();
      const rawCols = Array.isArray(g.columns) ? g.columns : JSON.parse(g.columns || '[]');
      _columns = rawCols.map(_toColObj);
      _rows = (Array.isArray(g.rows) ? g.rows : JSON.parse(g.rows || '[]')).map(r => ({
        size: r.size,
        values: [...(r.values || [])]
      }));
      _selectedProductIds = new Set((g.products || []).map(p => p.id));
      _filterText = '';
      const searchEl = document.getElementById('sc-product-search');
      if (searchEl) searchEl.value = '';
      _renderTable();
      await _loadProducts();
      _renderProductPicker();
      document.getElementById('size-chart-modal').style.display = 'block';
    } catch (e) {
      _toast('โหลดข้อมูลไม่สำเร็จ', 'error');
    }
  }

  function closeModal() {
    document.getElementById('size-chart-modal').style.display = 'none';
    _filterText = '';
    const searchEl = document.getElementById('sc-product-search');
    if (searchEl) searchEl.value = '';
  }

  function addRow() {
    const numCols = _columns.length - 1;
    _rows.push({ size: '', values: Array(numCols).fill('') });
    _renderTable();
  }

  function removeRow(ri) {
    _rows.splice(ri, 1);
    _renderTable();
  }

  function addColumn() {
    const colName = prompt('ชื่อคอลัมน์ใหม่ (เช่น สะโพก, รอบคอ, น้ำหนักผ้า):');
    if (!colName || !colName.trim()) return;
    _columns.push({ name: colName.trim(), unit: 'นิ้ว' });
    _rows = _rows.map(r => ({ ...r, values: [...(r.values || []), ''] }));
    _renderTable();
  }

  function removeCol(ci) {
    if (_columns.length <= 2) { _toast('ต้องมีอย่างน้อย 1 คอลัมน์ข้อมูล', 'error'); return; }
    _columns.splice(ci, 1);
    _rows = _rows.map(r => {
      const v = [...(r.values || [])];
      v.splice(ci - 1, 1);
      return { ...r, values: v };
    });
    _renderTable();
  }

  function updateColName(ci, val) {
    _columns[ci] = { ..._toColObj(_columns[ci]), name: val };
  }

  function updateColUnit(ci, val) {
    _columns[ci] = { ..._toColObj(_columns[ci]), unit: val };
  }

  function updateCell(ri, key, val) {
    if (key === 'size') {
      _rows[ri].size = val;
    } else {
      if (!_rows[ri].values) _rows[ri].values = [];
      _rows[ri].values[key] = val;
    }
  }

  function toggleProduct(pid, cb) {
    if (_selectedProductIds.has(pid)) {
      _selectedProductIds.delete(pid);
    } else {
      _selectedProductIds.add(pid);
    }
    _renderProductPicker();
  }

  async function save() {
    const name = document.getElementById('sc-name').value.trim();
    if (!name) { _toast('กรุณาใส่ชื่อ template', 'error'); return; }
    const id = document.getElementById('sc-edit-id').value;
    const ftEl = document.getElementById('sc-fabric-type');
    const acEl = document.getElementById('sc-allowance-chest');
    const awEl = document.getElementById('sc-allowance-waist');
    const ahEl = document.getElementById('sc-allowance-hip');
    if (ftEl) _fabricType = ftEl.value;
    if (acEl) _allowances.chest = parseFloat(acEl.value) || 1;
    if (awEl) _allowances.waist = parseFloat(awEl.value) || 1;
    if (ahEl) _allowances.hip = parseFloat(ahEl.value) || 1.5;
    const payload = {
      name,
      description: document.getElementById('sc-description').value.trim(),
      fabric_type: _fabricType,
      allowances: _allowances,
      columns: _columns.map(_toColObj),
      rows: _rows,
      product_ids: [..._selectedProductIds]
    };
    try {
      const url = id ? `/api/admin/size-chart-groups/${id}` : '/api/admin/size-chart-groups';
      const method = id ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) { const e = await res.json(); _toast(e.error || 'บันทึกไม่สำเร็จ', 'error'); return; }
      _toast(id ? 'แก้ไขตารางขนาดสำเร็จ' : 'สร้างตารางขนาดใหม่สำเร็จ');
      closeModal();
      load();
    } catch (e) {
      _toast('เกิดข้อผิดพลาด: ' + e.message, 'error');
    }
  }

  async function deleteGroup(id, name) {
    if (!confirm(`ลบตารางขนาด "${name}" ใช่ไหม?\nสินค้าที่ผูกอยู่จะถูกยกเลิกการผูกทั้งหมด`)) return;
    try {
      const res = await fetch(`/api/admin/size-chart-groups/${id}`, { method: 'DELETE' });
      if (!res.ok) { _toast('ลบไม่สำเร็จ', 'error'); return; }
      _toast(`ลบตารางขนาด "${name}" แล้ว`);
      load();
    } catch (e) {
      _toast('เกิดข้อผิดพลาด', 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('size-chart-modal')?.addEventListener('click', e => {
      if (e.target === document.getElementById('size-chart-modal')) closeModal();
    });
  });

  return { load, openCreateModal, openEditModal, closeModal, addRow, removeRow, addColumn, removeCol, updateColName, updateColUnit, updateCell, toggleProduct, filterProducts, save, deleteGroup, updateFabricType, updateAllowance };
})();
