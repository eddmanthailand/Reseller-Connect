/* =========================================================
   AI Agent — EKG Shops Admin
   ========================================================= */

const AGENT_PAGE_LABELS = {
    dashboard:    { label: 'ภาพรวม',    icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    products:     { label: 'สินค้า',     icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
    orders:       { label: 'ออเดอร์',   icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    warehouse:    { label: 'คลังสินค้า', icon: 'M8 14v3m4-3v3m4-3v3M3 21h18M3 10h18M3 7l9-4 9 4M4 10h16v11H4V10z' },
    customers:    { label: 'ลูกค้า',    icon: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2' },
    promotions:   { label: 'โปรโมชัน',  icon: 'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z' },
    coupons:      { label: 'คูปอง',     icon: 'M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z' },
    'quick-orders': { label: 'ขายด่วน', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
};

const AGENT_QUICK_CMDS = {
    dashboard:    ['ยอดขายวันนี้', 'ออเดอร์ค้างชำระ', 'สต็อกใกล้หมด'],
    products:     ['เช็คสต็อกสินค้า', 'เพิ่มสต็อก', 'สินค้าใกล้หมด'],
    orders:       ['ออเดอร์ค้างชำระ', 'ออเดอร์วันนี้', 'ยอดขายสัปดาห์นี้'],
    warehouse:    ['สต็อกใกล้หมด', 'เพิ่มสต็อก', 'เช็คสต็อกทั้งหมด'],
    customers:    ['ลูกค้าใหม่วันนี้', 'ยอดขายสรุป', 'ออเดอร์ค้างชำระ'],
    promotions:   ['ยอดขายวันนี้', 'สต็อกใกล้หมด', 'ออเดอร์ค้างชำระ'],
    coupons:      ['ยอดขายวันนี้', 'ออเดอร์ค้างชำระ', 'สต็อกใกล้หมด'],
    default:      ['ยอดขายวันนี้', 'สต็อกใกล้หมด', 'ออเดอร์ค้างชำระ'],
};

let _agentOpen      = false;
let _agentMin       = false;
let _agentMessages  = [];
let _agentLoading   = false;
let _agentPending   = null;
let _agentNotify    = false;
let _agentCtxPage   = 'dashboard';

function _agentCurrentPage() {
    const hash = (window.location.hash || '').replace('#', '') || 'dashboard';
    return hash;
}

function agentToggle() {
    if (_agentMin) { agentUnminimize(); return; }
    _agentOpen = !_agentOpen;
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    if (_agentOpen) {
        _agentCtxPage = _agentCurrentPage();
        panel.style.display = 'flex';
        requestAnimationFrame(() => { panel.style.opacity = '1'; panel.style.transform = 'translateY(0) scale(1)'; });
        fab.style.display = 'none';
        _agentNotify = false;
        _agentRenderNotifyDot();
        if (_agentMessages.length === 0) _agentAddWelcome();
        _agentScrollBottom();
        document.getElementById('agentInput').focus();
    } else {
        agentClose();
    }
}

function agentClose() {
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    panel.style.opacity = '0';
    panel.style.transform = 'translateY(16px) scale(0.97)';
    setTimeout(() => { panel.style.display = 'none'; }, 220);
    fab.style.display = 'flex';
    _agentOpen = false;
    _agentMin  = false;
}

function agentMinimize() {
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    panel.style.opacity = '0';
    panel.style.transform = 'translateY(16px) scale(0.97)';
    setTimeout(() => { panel.style.display = 'none'; }, 220);
    fab.style.display = 'flex';
    _agentOpen = false;
    _agentMin  = true;
}

function agentUnminimize() {
    _agentMin = false;
    _agentOpen = true;
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    panel.style.display = 'flex';
    requestAnimationFrame(() => { panel.style.opacity = '1'; panel.style.transform = 'translateY(0) scale(1)'; });
    fab.style.display = 'none';
    _agentNotify = false;
    _agentRenderNotifyDot();
    _agentScrollBottom();
    setTimeout(() => document.getElementById('agentInput').focus(), 250);
}

function _agentRenderNotifyDot() {
    const dot = document.getElementById('agentFabDot');
    if (dot) dot.style.display = _agentNotify ? 'block' : 'none';
}

function _agentRenderContext() {
    const page = _agentCurrentPage();
    const info = AGENT_PAGE_LABELS[page] || { label: page, icon: '' };
    const chipEl = document.getElementById('agentContextChip');
    if (chipEl) {
        chipEl.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${info.icon}"/></svg>
            <span>บริบท: ${info.label}</span>`;
    }
    const cmds = AGENT_QUICK_CMDS[page] || AGENT_QUICK_CMDS.default;
    const chipsEl = document.getElementById('agentQuickChips');
    if (chipsEl) {
        chipsEl.innerHTML = cmds.map(c =>
            `<button class="agent-chip" onclick="agentQuickCmd('${c}')">${c}</button>`
        ).join('');
    }
}

function agentQuickCmd(text) {
    const inp = document.getElementById('agentInput');
    if (inp) { inp.value = text; inp.focus(); }
    agentSend();
}

function _agentAddWelcome() {
    _agentMessages.push({
        role: 'ai',
        text: 'สวัสดีครับ 👋 ผมช่วยงานด้านต่างๆ ได้เลย เช่น เช็คยอดขาย ดูสต็อกสินค้า หรือช่วยเพิ่มสต็อกให้ครับ'
    });
    _agentRenderMessages();
}

function _agentScrollBottom() {
    setTimeout(() => {
        const msgs = document.getElementById('agentMessages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }, 50);
}

function _agentRenderMessages() {
    const el = document.getElementById('agentMessages');
    if (!el) return;
    el.innerHTML = _agentMessages.map((m, i) => {
        if (m.role === 'ai') return _agentBubbleAI(m.text, i);
        if (m.role === 'user') return _agentBubbleUser(m.text, i);
        if (m.role === 'plan') return _agentPlanCard(m, i);
        if (m.role === 'success') return _agentSuccessCard(m, i);
        return '';
    }).join('');

    if (_agentLoading) {
        el.innerHTML += `
        <div class="agent-bubble-ai" style="display:flex;align-items:center;gap:8px;padding:12px 16px;">
            <div class="agent-typing">
                <span></span><span></span><span></span>
            </div>
            <span style="font-size:12px;color:#8e8e93;">กำลังคิด...</span>
        </div>`;
    }
    _agentScrollBottom();
}

function _agentBubbleAI(text, i) {
    return `<div class="agent-bubble-ai">
        <div class="agent-bubble-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </div>
        <div class="agent-bubble-text">${_agentEscape(text).replace(/\n/g, '<br>')}</div>
    </div>`;
}

function _agentBubbleUser(text, i) {
    return `<div class="agent-bubble-user">
        <div class="agent-bubble-text-user">${_agentEscape(text)}</div>
    </div>`;
}

function _agentPlanCard(m, i) {
    const p = m.plan || {};
    const beforeRows = Object.entries(p.before || {}).map(([k, v]) =>
        `<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;">${k}</td><td style="padding:4px 8px;font-size:12px;font-weight:500;color:#dc2626;">${v}</td></tr>`
    ).join('');
    const afterRows = Object.entries(p.after || {}).map(([k, v]) =>
        `<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;">${k}</td><td style="padding:4px 8px;font-size:12px;font-weight:600;color:#16a34a;">${v}</td></tr>`
    ).join('');
    const approved = m.approved;
    return `<div class="agent-plan-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <div style="width:24px;height:24px;background:#1d1d1f;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            </div>
            <span style="font-size:13px;font-weight:700;color:#1d1d1f;">แผนการดำเนินงาน</span>
        </div>
        <div style="font-size:13px;color:#374151;margin-bottom:10px;">${_agentEscape(m.text || '')}</div>
        ${beforeRows || afterRows ? `
        <div style="background:#f9fafb;border-radius:10px;border:1px solid #e5e7eb;overflow:hidden;margin-bottom:10px;">
            ${beforeRows ? `
            <div style="padding:6px 8px;background:#fef2f2;border-bottom:1px solid #fee2e2;">
                <span style="font-size:10px;font-weight:700;color:#dc2626;text-transform:uppercase;letter-spacing:.5px;">ก่อนแก้ไข</span>
            </div>
            <table style="width:100%;border-collapse:collapse;">${beforeRows}</table>` : ''}
            ${afterRows ? `
            <div style="padding:6px 8px;background:#f0fdf4;border-bottom:1px solid #bbf7d0;${beforeRows ? 'border-top:1px solid #e5e7eb;' : ''}">
                <span style="font-size:10px;font-weight:700;color:#16a34a;text-transform:uppercase;letter-spacing:.5px;">หลังแก้ไข</span>
            </div>
            <table style="width:100%;border-collapse:collapse;">${afterRows}</table>` : ''}
        </div>` : ''}
        ${!approved ? `
        <div style="display:flex;gap:8px;">
            <button onclick="agentRejectPlan(${i})" style="flex:1;padding:9px;background:#f3f4f6;border:none;border-radius:10px;font-size:13px;font-weight:600;color:#6b7280;cursor:pointer;font-family:inherit;transition:background 0.15s;" onmouseover="this.style.background='#e5e7eb'" onmouseout="this.style.background='#f3f4f6'">ยกเลิก</button>
            <button onclick="agentApprovePlan(${i})" style="flex:2;padding:9px;background:#1d1d1f;border:none;border-radius:10px;font-size:13px;font-weight:700;color:#fff;cursor:pointer;font-family:inherit;transition:opacity 0.15s;" onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;"><polyline points="20 6 9 17 4 12"/></svg>
                อนุมัติ
            </button>
        </div>` : `<div style="display:flex;align-items:center;gap:6px;color:#6b7280;font-size:12px;"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>ดำเนินการแล้ว</div>`}
    </div>`;
}

function _agentSuccessCard(m, i) {
    const beforeRows = Object.entries(m.before || {}).map(([k, v]) =>
        `<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;">${k}</td><td style="padding:4px 8px;font-size:12px;color:#6b7280;">${v}</td></tr>`
    ).join('');
    const afterRows = Object.entries(m.after || {}).map(([k, v]) =>
        `<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;">${k}</td><td style="padding:4px 8px;font-size:12px;font-weight:700;color:#16a34a;">${v}</td></tr>`
    ).join('');
    return `<div class="agent-success-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <div style="width:24px;height:24px;background:#16a34a;border-radius:6px;display:flex;align-items:center;justify-content:center;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <span style="font-size:13px;font-weight:700;color:#16a34a;">ดำเนินการสำเร็จ</span>
            <span style="font-size:11px;color:#9ca3af;margin-left:auto;">บันทึกโดย AI Agent</span>
        </div>
        <div style="font-size:13px;color:#374151;margin-bottom:8px;">${_agentEscape(m.text || '')}</div>
        ${beforeRows || afterRows ? `
        <div style="background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;overflow:hidden;">
            ${beforeRows ? `<div style="padding:5px 8px;background:#f3f4f6;border-bottom:1px solid #e5e7eb;"><span style="font-size:10px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;">ก่อน</span></div><table style="width:100%;border-collapse:collapse;">${beforeRows}</table>` : ''}
            ${afterRows ? `<div style="padding:5px 8px;background:#f0fdf4;border-bottom:1px solid #bbf7d0;${beforeRows ? 'border-top:1px solid #e5e7eb;' : ''}"><span style="font-size:10px;font-weight:600;color:#16a34a;text-transform:uppercase;letter-spacing:.5px;">หลัง</span></div><table style="width:100%;border-collapse:collapse;">${afterRows}</table>` : ''}
        </div>` : ''}
    </div>`;
}

function _agentEscape(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function agentSend() {
    const inp = document.getElementById('agentInput');
    const text = (inp?.value || '').trim();
    if (!text || _agentLoading) return;
    inp.value = '';
    _agentAutoResize(inp);

    _agentMessages.push({ role: 'user', text });
    _agentLoading = true;
    _agentRenderMessages();

    try {
        const res = await fetch('/api/admin/agent/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ message: text, context_page: _agentCurrentPage() })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'เกิดข้อผิดพลาด');

        if (data.type === 'plan') {
            _agentPending = { log_id: data.log_id, tool: data.tool, params: data.params };
            _agentMessages.push({ role: 'plan', text: data.message, plan: data.plan, log_id: data.log_id, tool: data.tool, params: data.params, approved: false });
        } else {
            _agentMessages.push({ role: 'ai', text: data.message });
        }
    } catch (e) {
        _agentMessages.push({ role: 'ai', text: '❌ ' + e.message });
    }

    _agentLoading = false;
    _agentRenderMessages();

    if (!_agentOpen) {
        _agentNotify = true;
        _agentRenderNotifyDot();
    }
}

async function agentApprovePlan(msgIdx) {
    const m = _agentMessages[msgIdx];
    if (!m || m.role !== 'plan' || m.approved) return;
    m.approved = true;
    _agentLoading = true;
    _agentRenderMessages();

    try {
        const res = await fetch('/api/admin/agent/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ log_id: m.log_id, tool: m.tool, params: m.params })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'ดำเนินการไม่สำเร็จ');

        _agentMessages.push({
            role: 'success',
            text: data.message || 'ดำเนินการสำเร็จ',
            before: data.before || {},
            after: data.after || {}
        });
    } catch (e) {
        m.approved = false;
        _agentMessages.push({ role: 'ai', text: '❌ ' + e.message });
    }
    _agentLoading = false;
    _agentRenderMessages();
}

function agentRejectPlan(msgIdx) {
    const m = _agentMessages[msgIdx];
    if (!m || m.role !== 'plan') return;
    m.approved = true;
    _agentMessages.push({ role: 'ai', text: 'ยกเลิกแล้วครับ ถ้าต้องการทำอะไรเพิ่มเติมบอกได้เลย 😊' });
    _agentRenderMessages();
}

function agentInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); agentSend(); }
}

function _agentAutoResize(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function _agentInitPanel() {
    const panel = document.getElementById('agentPanel');
    if (!panel) return;
    panel.style.opacity = '0';
    panel.style.transform = 'translateY(16px) scale(0.97)';
    panel.style.display = 'none';
    _agentRenderContext();

    window.addEventListener('hashchange', () => {
        if (_agentOpen) {
            _agentCtxPage = _agentCurrentPage();
            _agentRenderContext();
        }
    });
}

document.addEventListener('DOMContentLoaded', _agentInitPanel);
