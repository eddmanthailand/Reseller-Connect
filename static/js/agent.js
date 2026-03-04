/* =========================================================
   AI Agent — EKG Shops Admin (Superadmin Only)
   ========================================================= */

const AGENT_PAGE_LABELS = {
    dashboard:      { label: 'ภาพรวม',     chips: ['ยอดขายวันนี้', 'ออเดอร์รอดำเนินการ', 'สต็อกใกล้หมด'] },
    products:       { label: 'สินค้า',      chips: ['เช็คสต็อกสินค้า', 'สินค้าขายดีเดือนนี้', 'ปิดสินค้าชั่วคราว'] },
    orders:         { label: 'ออเดอร์',    chips: ['ออเดอร์รอดำเนินการ', 'ออเดอร์วันนี้', 'ยอดขายแยกแบรนด์'] },
    warehouse:      { label: 'คลังสินค้า', chips: ['สต็อกใกล้หมด', 'เพิ่มสต็อก', 'เช็คสต็อกสินค้า'] },
    customers:      { label: 'ลูกค้า',     chips: ['ค้นหาลูกค้า', 'ออเดอร์รอดำเนินการ', 'ยอดขายวันนี้'] },
    promotions:     { label: 'โปรโมชัน',   chips: ['ยอดขายวันนี้', 'สต็อกใกล้หมด', 'ออเดอร์รอดำเนินการ'] },
    coupons:        { label: 'คูปอง',      chips: ['ยอดขายวันนี้', 'แชทรอตอบ', 'ออเดอร์รอดำเนินการ'] },
    'quick-orders': { label: 'ขายด่วน',   chips: ['ออเดอร์รอดำเนินการ', 'ค้นหาลูกค้า', 'ยอดขายวันนี้'] },
    chat:           { label: 'แชท',        chips: ['แชทรอตอบ', 'รายชื่อตัวแทน', 'ยอดขายวันนี้'] },
    mto:            { label: 'สั่งผลิต',   chips: ['สถานะ MTO', 'ออเดอร์รอดำเนินการ', 'ยอดขายวันนี้'] },
    default:        { label: 'ระบบ',       chips: ['ยอดขายวันนี้', 'สต็อกใกล้หมด', 'ออเดอร์รอดำเนินการ'] },
};

let _agentOpen      = false;
let _agentMin       = false;
let _agentMessages  = [];
let _agentLoading   = false;
let _agentNotify    = false;
let _agentBriefed   = false;
let _agentSettings  = null;
let _agentImageB64  = null;
let _agentImageMime = null;
let _agentImageName = null;

function _agentCurrentPage() {
    return (window.location.hash || '').replace('#', '') || 'dashboard';
}

function _agentPageInfo() {
    return AGENT_PAGE_LABELS[_agentCurrentPage()] || AGENT_PAGE_LABELS.default;
}

/* ---- FAB visibility (superadmin only, controlled by dashboard.js) ---- */
function agentInitVisibility(role) {
    const fab = document.getElementById('agentFab');
    if (!fab) return;
    if (role === 'Super Admin') {
        fab.style.display = 'flex';
    } else {
        fab.style.display = 'none';
        const panel = document.getElementById('agentPanel');
        if (panel) panel.style.display = 'none';
    }
}

/* ---- Open / Close / Minimize ---- */
function agentToggle() {
    if (_agentMin) { agentUnminimize(); return; }
    _agentOpen = !_agentOpen;
    if (_agentOpen) _agentDoOpen(); else agentClose();
}

function _agentDoOpen() {
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    panel.style.display = 'flex';
    requestAnimationFrame(() => {
        panel.style.opacity = '1';
        panel.style.transform = 'translateY(0) scale(1)';
    });
    fab.style.display = 'none';
    _agentOpen   = true;
    _agentNotify = false;
    _agentRenderNotifyDot();
    _agentRenderChips();
    if (_agentMessages.length === 0) _agentShowWelcome();
    if (!_agentBriefed) { _agentBriefed = true; _agentLoadBriefing(); }
    _agentScrollBottom();
    setTimeout(() => document.getElementById('agentInput')?.focus(), 200);
}

function agentClose() {
    _agentAnimate('close');
    const fab = document.getElementById('agentFab');
    fab.style.display = 'flex';
    _agentOpen = false;
    _agentMin  = false;
}

function agentMinimize() {
    _agentAnimate('close');
    document.getElementById('agentFab').style.display = 'flex';
    _agentOpen = false;
    _agentMin  = true;
}

function agentUnminimize() {
    _agentMin = false;
    _agentDoOpen();
}

function _agentAnimate(dir) {
    const panel = document.getElementById('agentPanel');
    panel.style.opacity   = '0';
    panel.style.transform = 'translateY(16px) scale(0.97)';
    setTimeout(() => { panel.style.display = 'none'; }, 220);
}

function _agentRenderNotifyDot() {
    const dot = document.getElementById('agentFabDot');
    if (dot) dot.style.display = _agentNotify ? 'block' : 'none';
}

/* ---- Context chips ---- */
function _agentRenderChips() {
    const info = _agentPageInfo();
    const el = document.getElementById('agentContextChip');
    if (el) el.textContent = `📍 ${info.label}`;
    const chipsEl = document.getElementById('agentQuickChips');
    if (chipsEl) {
        chipsEl.innerHTML = info.chips.map(c =>
            `<button class="agent-chip" onclick="agentQuickCmd('${c}')">${c}</button>`
        ).join('');
    }
    window.removeEventListener('hashchange', _agentRenderChips);
    window.addEventListener('hashchange', _agentRenderChips);
}

function agentQuickCmd(text) {
    const inp = document.getElementById('agentInput');
    if (inp) { inp.value = text; _agentAutoResize(inp); inp.focus(); }
    agentSend();
}

/* ---- Welcome & Briefing ---- */
function _agentShowWelcome() {
    const name = (_agentSettings?.agent_name) || 'น้องเอก';
    _agentPush({ role: 'ai', text: `สวัสดีครับ ผม${name} 👋\nพร้อมช่วยงานเต็มที่เลยครับ ลองพิมพ์คำสั่ง หรือกดแนบรูป (📎) เพื่อให้ผมอ่านใบปะหน้า/สลิปให้ได้เลยครับ` });
}

async function _agentLoadBriefing() {
    try {
        const res = await fetch('/api/admin/agent/briefing', { credentials: 'include' });
        if (!res.ok) return;
        const d = await res.json();
        if (d.alerts && d.alerts.length > 0) {
            const salesLine = d.sales_today_count > 0
                ? `💰 ยอดขายวันนี้: ${d.sales_today_count} ออเดอร์ ฿${Number(d.sales_today_total).toLocaleString()}\n\n`
                : '';
            _agentPush({ role: 'ai', text: `${salesLine}🔔 สิ่งที่ต้องดูแลวันนี้:\n${d.alerts.join('\n')}` });
        }
    } catch (_) {}
}

/* ---- Message rendering ---- */
function _agentPush(msg) {
    _agentMessages.push(msg);
    _agentRenderMessages();
}

function _agentRenderMessages() {
    const el = document.getElementById('agentMessages');
    if (!el) return;
    el.innerHTML = _agentMessages.map((m, i) => {
        if (m.role === 'ai')      return _agentBubbleAI(m, i);
        if (m.role === 'user')    return _agentBubbleUser(m, i);
        if (m.role === 'plan')    return _agentPlanCard(m, i);
        if (m.role === 'success') return _agentSuccessCard(m, i);
        return '';
    }).join('');
    if (_agentLoading) {
        el.innerHTML += `<div class="agent-bubble-ai" style="padding:12px 16px;">
            <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
            <div class="agent-typing"><span></span><span></span><span></span></div>
        </div>`;
    }
    _agentScrollBottom();
}

function _agentBubbleAI(m, i) {
    return `<div class="agent-bubble-ai">
        <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
        <div>
            <div class="agent-bubble-text">${_esc(m.text).replace(/\n/g, '<br>')}</div>
            <div class="agent-feedback-row" id="fb-${i}">
                <button class="agent-fb-btn" onclick="agentFeedback(${i},1)" title="ดีมาก">👍</button>
                <button class="agent-fb-btn" onclick="agentFeedback(${i},-1)" title="ไม่ตรง">👎</button>
            </div>
        </div>
    </div>`;
}

function _agentBubbleUser(m, i) {
    return `<div class="agent-bubble-user">
        <div>
            ${m.image ? `<img src="${m.image}" style="max-width:160px;border-radius:10px;margin-bottom:4px;display:block;">` : ''}
            ${m.text ? `<div class="agent-bubble-text-user">${_esc(m.text)}</div>` : ''}
        </div>
    </div>`;
}

function _agentPlanCard(m, i) {
    const p = m.plan || {};
    const beforeRows = _tableRows(p.before || {}, '#dc2626');
    const afterRows  = _tableRows(p.after  || {}, '#16a34a');
    const done = m.approved;
    return `<div class="agent-plan-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <div style="width:24px;height:24px;background:#1d1d1f;border-radius:6px;display:flex;align-items:center;justify-content:center;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            </div>
            <span style="font-size:13px;font-weight:700;color:#1d1d1f;">แผนการดำเนินงาน</span>
        </div>
        <div style="font-size:13px;color:#374151;margin-bottom:10px;">${_esc(m.text || '')}</div>
        ${beforeRows || afterRows ? `<div style="background:#f9fafb;border-radius:10px;border:1px solid #e5e7eb;overflow:hidden;margin-bottom:10px;">
            ${beforeRows ? `<div style="padding:5px 8px;background:#fef2f2;border-bottom:1px solid #fee2e2;"><span style="font-size:10px;font-weight:700;color:#dc2626;text-transform:uppercase;letter-spacing:.5px;">ก่อน</span></div><table style="width:100%;border-collapse:collapse;">${beforeRows}</table>` : ''}
            ${afterRows  ? `<div style="padding:5px 8px;background:#f0fdf4;border-bottom:1px solid #bbf7d0;${beforeRows?'border-top:1px solid #e5e7eb;':''}"><span style="font-size:10px;font-weight:700;color:#16a34a;text-transform:uppercase;letter-spacing:.5px;">หลัง</span></div><table style="width:100%;border-collapse:collapse;">${afterRows}</table>` : ''}
        </div>` : ''}
        ${!done ? `<div style="display:flex;gap:8px;">
            <button onclick="agentRejectPlan(${i})" class="agent-plan-btn-cancel">ยกเลิก</button>
            <button onclick="agentApprovePlan(${i})" class="agent-plan-btn-ok">✓ อนุมัติ</button>
        </div>` : `<div style="font-size:12px;color:#9ca3af;">ดำเนินการแล้ว</div>`}
    </div>`;
}

function _agentSuccessCard(m, i) {
    return `<div class="agent-success-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:24px;height:24px;background:#16a34a;border-radius:6px;display:flex;align-items:center;justify-content:center;">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <span style="font-size:13px;font-weight:700;color:#16a34a;">ดำเนินการสำเร็จ</span>
        </div>
        <div style="font-size:13px;color:#374151;margin-bottom:8px;">${_esc(m.text || '')}</div>
        ${(m.before||m.after) ? `<div style="background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;overflow:hidden;">
            ${m.before ? `<div style="padding:5px 8px;background:#f3f4f6;"><span style="font-size:10px;font-weight:600;color:#9ca3af;text-transform:uppercase;">ก่อน</span></div><table style="width:100%;border-collapse:collapse;">${_tableRows(m.before,'#6b7280')}</table>` : ''}
            ${m.after  ? `<div style="padding:5px 8px;background:#f0fdf4;border-top:1px solid #e5e7eb;"><span style="font-size:10px;font-weight:600;color:#16a34a;text-transform:uppercase;">หลัง</span></div><table style="width:100%;border-collapse:collapse;">${_tableRows(m.after,'#16a34a')}</table>` : ''}
        </div>` : ''}
    </div>`;
}

function _tableRows(obj, color) {
    return Object.entries(obj).map(([k,v]) =>
        `<tr><td style="padding:4px 8px;color:#6b7280;font-size:12px;">${_esc(k)}</td><td style="padding:4px 8px;font-size:12px;font-weight:600;color:${color};">${_esc(String(v))}</td></tr>`
    ).join('');
}

function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _agentScrollBottom() {
    setTimeout(() => {
        const el = document.getElementById('agentMessages');
        if (el) el.scrollTop = el.scrollHeight;
    }, 50);
}

/* ---- Send message ---- */
async function agentSend() {
    const inp  = document.getElementById('agentInput');
    const text = (inp?.value || '').trim();
    if ((!text && !_agentImageB64) || _agentLoading) return;
    inp.value = '';
    _agentAutoResize(inp);

    const userMsg = { role: 'user', text, image: _agentImageB64 ? `data:${_agentImageMime};base64,${_agentImageB64}` : null };
    _agentMessages.push(userMsg);
    const sentImage = _agentImageB64;
    const sentMime  = _agentImageMime;
    _agentClearImage();
    _agentLoading = true;
    _agentRenderMessages();

    try {
        const body = { message: text, context_page: _agentCurrentPage() };
        if (sentImage) { body.image_data = sentImage; body.image_mime = sentMime; }
        const res  = await fetch('/api/admin/agent/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'include', body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'เกิดข้อผิดพลาด');

        if (data.type === 'plan') {
            _agentMessages.push({ role: 'plan', text: data.message, plan: data.plan, log_id: data.log_id, tool: data.tool, params: data.params, approved: false });
        } else {
            _agentMessages.push({ role: 'ai', text: data.message });
        }
    } catch (e) {
        _agentMessages.push({ role: 'ai', text: '❌ ' + e.message });
    }

    _agentLoading = false;
    _agentRenderMessages();
    if (!_agentOpen) { _agentNotify = true; _agentRenderNotifyDot(); }
}

/* ---- Plan approve/reject ---- */
async function agentApprovePlan(idx) {
    const m = _agentMessages[idx];
    if (!m || m.role !== 'plan' || m.approved) return;
    m.approved = true;
    _agentLoading = true;
    _agentRenderMessages();
    try {
        const res  = await fetch('/api/admin/agent/execute', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'include', body: JSON.stringify({ log_id: m.log_id, tool: m.tool, params: m.params })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'ดำเนินการไม่สำเร็จ');
        _agentMessages.push({ role: 'success', text: data.message || 'สำเร็จ', before: data.before, after: data.after });
    } catch (e) {
        m.approved = false;
        _agentMessages.push({ role: 'ai', text: '❌ ' + e.message });
    }
    _agentLoading = false;
    _agentRenderMessages();
}

function agentRejectPlan(idx) {
    const m = _agentMessages[idx];
    if (!m) return;
    m.approved = true;
    _agentMessages.push({ role: 'ai', text: 'ยกเลิกแล้วครับ มีอะไรอื่นให้ช่วยไหมครับ?' });
    _agentRenderMessages();
}

/* ---- Feedback ---- */
async function agentFeedback(idx, rating) {
    const m = _agentMessages[idx];
    if (!m) return;
    const fbRow = document.getElementById('fb-' + idx);
    if (fbRow) fbRow.innerHTML = `<span style="font-size:11px;color:#9ca3af;">${rating > 0 ? '👍 ขอบคุณ' : '👎 รับทราบ จะพยายามปรับปรุง'}</span>`;
    let correction = null;
    if (rating < 0) {
        correction = prompt('ช่วยบอกผมด้วยครับ ควรตอบว่าอะไร? (กด Cancel เพื่อข้าม)');
    }
    try {
        const userMsg = _agentMessages.slice(0, idx).reverse().find(mm => mm.role === 'user');
        await fetch('/api/admin/agent/feedback', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
            body: JSON.stringify({ command_text: userMsg?.text || '', response_text: m.text, rating, correction, context_page: _agentCurrentPage() })
        });
    } catch (_) {}
}

/* ---- Image attach ---- */
function agentAttachImage() {
    document.getElementById('agentImageInput')?.click();
}

function agentImageSelected(input) {
    const file = input.files?.[0];
    if (!file) return;
    _agentImageMime = file.type || 'image/jpeg';
    _agentImageName = file.name;
    const reader = new FileReader();
    reader.onload = (e) => {
        _agentImageB64 = e.target.result.split(',')[1];
        const preview = document.getElementById('agentImagePreview');
        const previewImg = document.getElementById('agentImagePreviewImg');
        if (preview && previewImg) {
            previewImg.src = e.target.result;
            preview.style.display = 'flex';
        }
    };
    reader.readAsDataURL(file);
    input.value = '';
}

function _agentClearImage() {
    _agentImageB64 = null; _agentImageMime = null; _agentImageName = null;
    const preview = document.getElementById('agentImagePreview');
    if (preview) preview.style.display = 'none';
    const img = document.getElementById('agentImagePreviewImg');
    if (img) img.src = '';
}

/* ---- Settings modal ---- */
async function agentOpenSettings() {
    const modal = document.getElementById('agentSettingsModal');
    if (!modal) return;
    try {
        const res = await fetch('/api/admin/agent/settings', { credentials: 'include' });
        if (res.ok) {
            const d = await res.json();
            _agentSettings = d;
            document.getElementById('agentSettingName').value      = d.agent_name      || 'น้องเอก';
            document.getElementById('agentSettingTone').value      = d.tone             || 'friendly';
            document.getElementById('agentSettingParticle').value  = d.ending_particle  || 'ครับ';
            document.getElementById('agentSettingCustom').value    = d.custom_prompt    || '';
        }
    } catch (_) {}
    modal.style.display = 'flex';
    requestAnimationFrame(() => { modal.style.opacity = '1'; });
}

function agentCloseSettings() {
    const modal = document.getElementById('agentSettingsModal');
    if (!modal) return;
    modal.style.opacity = '0';
    setTimeout(() => { modal.style.display = 'none'; }, 180);
}

async function agentSaveSettings() {
    const payload = {
        agent_name:      document.getElementById('agentSettingName').value.trim()    || 'น้องเอก',
        tone:            document.getElementById('agentSettingTone').value            || 'friendly',
        ending_particle: document.getElementById('agentSettingParticle').value.trim() || 'ครับ',
        custom_prompt:   document.getElementById('agentSettingCustom').value.trim(),
    };
    try {
        const res = await fetch('/api/admin/agent/settings', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            credentials: 'include', body: JSON.stringify(payload)
        });
        if (res.ok) {
            _agentSettings = payload;
            agentCloseSettings();
            _agentMessages = [];
            _agentBriefed  = false;
            _agentShowWelcome();
        }
    } catch (e) { alert('บันทึกไม่สำเร็จ: ' + e.message); }
}

/* ---- Helpers ---- */
function agentInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); agentSend(); }
}

function _agentAutoResize(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

/* ---- Init ---- */
document.addEventListener('DOMContentLoaded', () => {
    const panel = document.getElementById('agentPanel');
    if (panel) {
        panel.style.opacity = '0';
        panel.style.transform = 'translateY(16px) scale(0.97)';
        panel.style.display = 'none';
    }
    const fab = document.getElementById('agentFab');
    if (fab) fab.style.display = 'none';

    fetch('/api/admin/agent/settings', { credentials: 'include' })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) _agentSettings = d; })
        .catch(() => {});
});
