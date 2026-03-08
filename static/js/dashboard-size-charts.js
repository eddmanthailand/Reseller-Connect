const SizeCharts = (() => {
  let _columns = ['ขนาด', 'รอบอก', 'รอบเอว', 'ความยาว'];
  let _rows = [];
  let _allProducts = [];
  let _selectedProductIds = new Set();
  let _filterText = '';

  function _toast(msg, type = 'success') {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:10px;color:#fff;font-size:14px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.2);background:${type === 'success' ? '#10b981' : '#ef4444'};`;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  function _renderTable() {
    const thead = document.getElementById('sc-thead');
    const tbody = document.getElementById('sc-tbody');
    if (!thead || !tbody) return;

    const colCount = _columns.length;

    thead.innerHTML = `<tr>${_columns.map((c, i) => `
      <th style="padding:8px 10px;text-align:left;font-size:13px;font-weight:600;color:#374151;white-space:nowrap;border-bottom:1px solid #e5e7eb;">
        ${i === 0
          ? `<span style="color:#6b7280;">ขนาด</span>`
          : `<input value="${c}" onchange="SizeCharts.updateColName(${i},this.value)"
              style="border:none;background:transparent;font-weight:600;font-size:13px;width:90px;outline:none;color:#374151;">`
        }
        ${i > 1 ? `<button onclick="SizeCharts.removeCol(${i})" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:12px;padding:0 2px;" title="ลบคอลัมน์">✕</button>` : ''}
      </th>`).join('')}
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

  function _renderProductPicker() {
    const el = document.getElementById('sc-products-list');
    if (!el || !_allProducts.length) return;
    const q = _filterText.trim().toLowerCase();
    const filtered = q ? _allProducts.filter(p => p.name.toLowerCase().includes(q)) : _allProducts;
    if (!filtered.length) {
      el.innerHTML = `<span style="color:#9ca3af;font-size:13px;">ไม่พบสินค้าที่ค้นหา "${_filterText}"</span>`;
      return;
    }
    el.innerHTML = filtered.map(p => {
      const checked = _selectedProductIds.has(p.id);
      const otherChart = (!checked && p.chart_group_name) ? ` <span style="font-size:11px;color:#f59e0b;">(${p.chart_group_name})</span>` : '';
      return `<label style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;background:${checked ? '#ede9fe' : '#fff'};border:1px solid ${checked ? '#a78bfa' : '#e5e7eb'};border-radius:20px;cursor:pointer;font-size:13px;user-select:none;" onclick="SizeCharts.toggleProduct(${p.id},this)">
        <input type="checkbox" ${checked ? 'checked' : ''} style="display:none;">
        ${p.name}${otherChart}
      </label>`;
    }).join('');
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
        const sizes = rows.map(r => r.size).join(', ') || '-';
        return `<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
            <div>
              <h3 style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1f2937;">${g.name}</h3>
              ${g.description ? `<p style="margin:0;font-size:13px;color:#6b7280;">${g.description}</p>` : ''}
            </div>
            <div style="display:flex;gap:8px;">
              <button onclick="SizeCharts.openEditModal(${g.id})" style="background:#f3f4f6;border:1px solid #d1d5db;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px;">แก้ไข</button>
              <button onclick="SizeCharts.deleteGroup(${g.id},'${g.name}')" style="background:#fef2f2;border:1px solid #fca5a5;color:#ef4444;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px;">ลบ</button>
            </div>
          </div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">
            คอลัมน์: ${cols.join(' | ')} &nbsp;•&nbsp; ไซส์: ${sizes}
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
    _columns = ['ขนาด', 'รอบอก', 'รอบเอว', 'ความยาว'];
    _rows = [
      { size: 'SS', values: ['', '', ''] },
      { size: 'S', values: ['', '', ''] },
      { size: 'M', values: ['', '', ''] },
      { size: 'L', values: ['', '', ''] },
      { size: 'XL', values: ['', '', ''] },
      { size: '2XL', values: ['', '', ''] },
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
      _columns = Array.isArray(g.columns) ? [...g.columns] : JSON.parse(g.columns || '[]');
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
    _columns.push(colName.trim());
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
    _columns[ci] = val;
  }

  function updateCell(ri, key, val) {
    if (key === 'size') {
      _rows[ri].size = val;
    } else {
      if (!_rows[ri].values) _rows[ri].values = [];
      _rows[ri].values[key] = val;
    }
  }

  function toggleProduct(pid, label) {
    if (_selectedProductIds.has(pid)) {
      _selectedProductIds.delete(pid);
      label.style.background = '#fff';
      label.style.borderColor = '#e5e7eb';
    } else {
      _selectedProductIds.add(pid);
      label.style.background = '#ede9fe';
      label.style.borderColor = '#a78bfa';
    }
  }

  async function save() {
    const name = document.getElementById('sc-name').value.trim();
    if (!name) { _toast('กรุณาใส่ชื่อ template', 'error'); return; }
    const id = document.getElementById('sc-edit-id').value;
    const payload = {
      name,
      description: document.getElementById('sc-description').value.trim(),
      columns: _columns,
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

  return { load, openCreateModal, openEditModal, closeModal, addRow, removeRow, addColumn, removeCol, updateColName, updateCell, toggleProduct, filterProducts, save, deleteGroup };
})();
