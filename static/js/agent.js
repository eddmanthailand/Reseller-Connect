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

const _AGENT_STORAGE_KEY  = 'ekg_agent_history';
const _AGENT_MAX_SAVED    = 60;

function _agentSaveHistory() {
    try {
        const toSave = _agentMessages.slice(-_AGENT_MAX_SAVED).map(m => {
            if (m.role === 'genimage') {
                const { image_b64, ...rest } = m;
                return { ...rest, _image_removed: true };
            }
            return m;
        });
        sessionStorage.setItem(_AGENT_STORAGE_KEY, JSON.stringify(toSave));
    } catch (_) {}
}

function _agentRestoreHistory() {
    try {
        const raw = sessionStorage.getItem(_AGENT_STORAGE_KEY);
        if (!raw) return false;
        const saved = JSON.parse(raw);
        if (!Array.isArray(saved) || saved.length === 0) return false;
        _agentMessages = saved;
        return true;
    } catch (_) {
        return false;
    }
}

function agentClearHistory() {
    sessionStorage.removeItem(_AGENT_STORAGE_KEY);
    _agentMessages = [];
    _agentBriefed = false;
    _agentShowWelcome();
}

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
        const hadHistory = _agentRestoreHistory();
        if (hadHistory) {
            _agentBriefed = true;
            _agentRenderMessages();
            if (_agentMessages.length > 0) {
                _agentNotify = false;
            }
        }
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

function _agentFitPanel() {
    const panel = document.getElementById('agentPanel');
    if (!panel) return;
    const vw = window.innerWidth;
    if (vw <= 480) {
        panel.style.width    = '';
        panel.style.maxWidth = '';
        panel.style.right    = '';
        panel.style.left     = '';
        panel.style.bottom   = '';
        return;
    }
    const sidebar = document.getElementById('sidebar');
    const sidebarRight = sidebar ? sidebar.getBoundingClientRect().right : 0;
    const available = vw - sidebarRight - 48;
    if (available < 160) return;
    const w = Math.min(400, available);
    panel.style.width    = w + 'px';
    panel.style.maxWidth = w + 'px';
    panel.style.right    = '24px';
    panel.style.left     = 'auto';
    panel.style.bottom   = '28px';
}

function _agentDoOpen() {
    const panel = document.getElementById('agentPanel');
    const fab   = document.getElementById('agentFab');
    _agentFitPanel();
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
    if (_agentMessages.length === 0) {
        _agentShowWelcome();
    } else {
        _agentRenderMessages();
    }
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
    const name     = (_agentSettings?.agent_name)      || 'น้องเอก';
    const prompt   = (_agentSettings?.custom_prompt)   || '';
    const particle = (_agentSettings?.ending_particle) || '';
    const isFemale = /ค่ะ|ขา/.test(particle) || /ผู้หญิง|หญิง|เลขา|เลขานุการ|สาว|นางสาว/.test(prompt);
    const pronoun  = isFemale ? 'หนู' : 'ผม';
    const polite   = particle || (isFemale ? 'ค่ะ' : 'ครับ');
    _agentPush({ role: 'ai', text: `สวัสดี${polite} ${pronoun}${name} 👋\nพร้อมช่วยงานเต็มที่เลย${polite} ลองพิมพ์คำสั่ง หรือกดแนบรูป (📎) เพื่อให้${pronoun}อ่านใบปะหน้า/สลิปให้ได้เลย${polite}` });
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
    _agentSaveHistory();
    _agentRenderMessages();
}

const _agentChartConfigs = {};

function _agentRenderMessages() {
    const el = document.getElementById('agentMessages');
    if (!el) return;
    el.innerHTML = _agentMessages.map((m, i) => {
        if (m.role === 'ai')       return _agentBubbleAI(m, i);
        if (m.role === 'user')     return _agentBubbleUser(m, i);
        if (m.role === 'plan')     return _agentPlanCard(m, i);
        if (m.role === 'success')  return _agentSuccessCard(m, i);
        if (m.role === 'chart')    return _agentChartCard(m, i);
        if (m.role === 'genimage') return _agentGenImageCard(m, i);
        return '';
    }).join('');
    if (_agentLoading) {
        el.innerHTML += `<div class="agent-bubble-ai" style="padding:12px 16px;">
            <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
            <div class="agent-typing"><span></span><span></span><span></span></div>
        </div>`;
    }
    _agentScrollBottom();
    requestAnimationFrame(_agentInitCharts);
}

function _agentInitCharts() {
    const bahtFmt = v => '฿' + Number(v).toLocaleString('th-TH', {maximumFractionDigits: 0});
    Object.entries(_agentChartConfigs).forEach(([id, cfg]) => {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const existing = typeof Chart !== 'undefined' && Chart.getChart(canvas);
        if (existing) existing.destroy();
        const config = JSON.parse(JSON.stringify(cfg));
        (function fixCallbacks(obj) {
            if (!obj || typeof obj !== 'object') return;
            Object.keys(obj).forEach(k => {
                if (k === 'callback' && obj[k] === '__BAHT__') { obj[k] = bahtFmt; }
                else fixCallbacks(obj[k]);
            });
        })(config);
        if (typeof Chart !== 'undefined') new Chart(canvas, config);
    });
}

function _agentChartCard(m, i) {
    const id = `agent-chart-${i}`;
    _agentChartConfigs[id] = m.chartConfig;
    return `<div class="agent-bubble-ai">
        <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
        <div style="flex:1;min-width:0;">
            <div class="agent-bubble-text" style="margin-bottom:10px;">${_esc(m.text)}</div>
            <div style="background:#fff;border-radius:14px;padding:14px 12px;box-shadow:0 1px 6px rgba(0,0,0,0.08);border:1px solid rgba(0,0,0,0.06);">
                <canvas id="${id}" style="max-height:220px;width:100%;display:block;"></canvas>
            </div>
            <div class="agent-feedback-row" style="margin-top:6px;">
                <button class="agent-fb-btn" onclick="agentFeedback(${i},1)" title="ดีมาก">👍</button>
                <button class="agent-fb-btn" onclick="agentFeedback(${i},-1)" title="ไม่ตรง">👎</button>
                ${m.model ? _agentModelBadge(m.model) : ''}
            </div>
        </div>
    </div>`;
}

function _agentGenImageCard(m, i) {
    const src = `data:${m.mime_type || 'image/png'};base64,${m.image_b64}`;
    const shortModel = (m.image_model || 'Imagen').split('/').pop().replace('imagen-','Imagen ');
    return `<div class="agent-bubble-ai">
        <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21,15 16,10 5,21"/></svg></div>
        <div style="flex:1;min-width:0;">
            <div class="agent-bubble-text" style="margin-bottom:8px;">${_esc(m.text).replace(/\n/g,'<br>')}</div>
            <div style="position:relative;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.15);border:1px solid rgba(255,255,255,0.1);">
                <img src="${src}" style="width:100%;display:block;border-radius:14px;" alt="AI Generated Image">
                <div style="position:absolute;bottom:8px;right:8px;display:flex;gap:6px;">
                    <a href="${src}" download="imagen-${i}.png" style="background:rgba(0,0,0,0.65);backdrop-filter:blur(8px);color:#fff;text-decoration:none;padding:5px 10px;border-radius:8px;font-size:11px;font-weight:600;display:flex;align-items:center;gap:4px;">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        ดาวน์โหลด
                    </a>
                    <span style="background:rgba(0,0,0,0.55);backdrop-filter:blur(8px);color:rgba(255,255,255,0.8);padding:5px 10px;border-radius:8px;font-size:10px;font-weight:600;">🎨 ${_esc(shortModel)}</span>
                </div>
            </div>
            <div class="agent-feedback-row" style="margin-top:6px;">
                <button class="agent-fb-btn" onclick="agentFeedback(${i},1)" title="ดีมาก">👍</button>
                <button class="agent-fb-btn" onclick="agentFeedback(${i},-1)" title="ไม่ตรง">👎</button>
                ${m.model ? _agentModelBadge(m.model) : ''}
            </div>
        </div>
    </div>`;
}

function _agentModelBadge(model) {
    if (!model) return '';
    const styles = {
        '3.1 Pro':   { label: '✨ 3.1 Pro',   style: 'background:linear-gradient(135deg,#7c3aed,#db2777);color:#fff;' },
        'Pro':       { label: '✨ Pro',        style: 'background:linear-gradient(135deg,#7c3aed,#db2777);color:#fff;' },
        'Flash':     { label: '⚡ Flash',      style: 'background:#e0f2fe;color:#0369a1;border:1px solid #bae6fd;' },
        'Flash Lite':{ label: '⚡ Flash Lite', style: 'background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;' },
    };
    const s = styles[model] || { label: `⚡ ${model}`, style: 'background:#f3f4f6;color:#6b7280;border:1px solid #e5e7eb;' };
    return `<span style="display:inline-flex;align-items:center;gap:3px;font-size:9px;font-weight:700;padding:1px 6px;border-radius:20px;margin-left:6px;vertical-align:middle;${s.style}">${s.label}</span>`;
}

function _agentBubbleAI(m, i) {
    return `<div class="agent-bubble-ai">
        <div class="agent-bubble-icon"><svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
        <div>
            <div class="agent-bubble-text">${_esc(m.text).replace(/\n/g, '<br>')}</div>
            <div class="agent-feedback-row" id="fb-${i}">
                <button class="agent-fb-btn" onclick="agentFeedback(${i},1)" title="ดีมาก">👍</button>
                <button class="agent-fb-btn" onclick="agentFeedback(${i},-1)" title="ไม่ตรง">👎</button>
                ${m.model ? _agentModelBadge(m.model) : ''}
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
            ${m.model ? _agentModelBadge(m.model) : ''}
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
        ${m.model ? `<div style="margin-top:6px;">${_agentModelBadge(m.model)}</div>` : ''}
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
    _agentSaveHistory();
    const sentImage = _agentImageB64;
    const sentMime  = _agentImageMime;
    _agentClearImage();
    _agentLoading = true;
    _agentRenderMessages();

    try {
        const history = _agentMessages.slice(0, -1)
            .filter(m => ['user', 'ai', 'plan', 'success'].includes(m.role))
            .slice(-20)
            .map(m => {
                if (m.role === 'user') return { role: 'user', text: m.text || '' };
                if (m.role === 'plan') {
                    const status = m.approved ? '[อนุมัติแล้ว ดำเนินการสำเร็จ]' : '[รออนุมัติ]';
                    return { role: 'model', text: `[แผนงาน ${m.tool}: ${m.text || ''} — ${status}]` };
                }
                if (m.role === 'success') {
                    return { role: 'model', text: `[ผลลัพธ์: ${m.text || 'สำเร็จ'}]` };
                }
                let text = m.text || '';
                if (text.includes('📊')) {
                    text = '[ผลลัพธ์ query จาก DB ก่อนหน้า — ถ้าต้องการข้อมูลต้อง query_db ใหม่]';
                }
                return { role: 'model', text };
            })
            .filter(m => m.text);
        const body = { message: text, context_page: _agentCurrentPage(), history };
        if (sentImage) { body.image_data = sentImage; body.image_mime = sentMime; }
        const res  = await fetch('/api/admin/agent/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'include', body: JSON.stringify(body)
        });
        const rawText = await res.text();
        let data;
        try { data = JSON.parse(rawText); }
        catch (_) { throw new Error(`Server error (${res.status}): ระบบส่งข้อมูลผิดรูปแบบ กรุณาลองใหม่`); }
        if (!res.ok) throw new Error(data.error || data.message || `เกิดข้อผิดพลาด (${res.status})`);

        if (data.type === 'chart') {
            _agentMessages.push({ role: 'chart', text: data.message, chartConfig: data.chart, model: data.model_used });
        } else if (data.type === 'image') {
            _agentMessages.push({ role: 'genimage', text: data.message, image_b64: data.image_b64, mime_type: data.mime_type, prompt: data.prompt, image_model: data.image_model, model: data.model_used });
        } else if (data.type === 'plan') {
            _agentMessages.push({ role: 'plan', text: data.message, plan: data.plan, log_id: data.log_id, tool: data.tool, params: data.params, approved: false, model: data.model_used });
        } else {
            let msgText = data.message || '';
            // Safety: ถ้า message เป็น raw JSON string ที่หลุดมา ให้ดึงเฉพาะ message field
            if (msgText.trim().startsWith('{') && msgText.includes('"message"')) {
                try {
                    const inner = JSON.parse(msgText);
                    if (inner && inner.message) msgText = inner.message;
                } catch (_) {
                    const m = msgText.match(/"message"\s*:\s*"([\s\S]*?)"(?:\s*[,}])/);
                    if (m && m[1]) msgText = m[1];
                }
            }
            _agentMessages.push({ role: 'ai', text: msgText, model: data.model_used });
        }
    } catch (e) {
        _agentMessages.push({ role: 'ai', text: '❌ ' + e.message });
    }

    _agentSaveHistory();
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
        const rawText2 = await res.text();
        let data;
        try { data = JSON.parse(rawText2); }
        catch (_) { throw new Error(`Server error (${res.status}): ระบบส่งข้อมูลผิดรูปแบบ กรุณาลองใหม่`); }
        if (!res.ok) throw new Error(data.error || data.message || 'ดำเนินการไม่สำเร็จ');
        _agentMessages.push({ role: 'success', text: data.message || 'สำเร็จ', before: data.before, after: data.after, model: m.model });
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

/* ---- Notes helpers ---- */
function _agentRenderNotes(notes) {
    const el = document.getElementById('agentNotesList');
    if (!el) return;
    if (!notes || !notes.length) {
        el.innerHTML = '<div style="font-size:11px;color:#9ca3af;padding:4px 0;">ยังไม่มีบันทึก — AI จะเริ่มจำเมื่อคุณสั่งให้บันทึก</div>';
        return;
    }
    el.innerHTML = notes.map(n => `
        <div style="display:flex;align-items:flex-start;gap:6px;padding:5px 0;border-bottom:1px solid #f3f4f6;">
            <div style="flex:1;min-width:0;">
                <span style="font-size:11px;font-weight:600;color:#1d1d1f;">${n.note_key}</span>
                <span style="font-size:11px;color:#6b7280;"> — ${n.note_value}</span>
            </div>
            <button onclick="agentDeleteNote('${n.note_key.replace(/'/g,"\\'")}',this)" style="flex-shrink:0;background:none;border:none;color:#ef4444;font-size:13px;cursor:pointer;padding:0 2px;" title="ลบ">✕</button>
        </div>`).join('');
}

async function agentAddNote() {
    const key = (document.getElementById('agentNoteKey')?.value || '').trim();
    const val = (document.getElementById('agentNoteVal')?.value || '').trim();
    if (!key || !val) { alert('กรุณาระบุหัวข้อและข้อมูล'); return; }
    const res = await fetch('/api/admin/agent/notes', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        credentials: 'include', body: JSON.stringify({key, value: val})
    });
    if (res.ok) {
        document.getElementById('agentNoteKey').value = '';
        document.getElementById('agentNoteVal').value = '';
        const notes = await (await fetch('/api/admin/agent/notes', {credentials:'include'})).json();
        _agentRenderNotes(notes);
    }
}

async function agentDeleteNote(key, btn) {
    if (!confirm(`ลบบันทึก "${key}" ออกจากสมุดโน้ต?`)) return;
    const res = await fetch('/api/admin/agent/notes', {
        method: 'DELETE', headers: {'Content-Type':'application/json'},
        credentials: 'include', body: JSON.stringify({key})
    });
    if (res.ok) {
        const notes = await (await fetch('/api/admin/agent/notes', {credentials:'include'})).json();
        _agentRenderNotes(notes);
    }
}

/* ---- Settings modal ---- */
async function agentOpenSettings() {
    const modal = document.getElementById('agentSettingsModal');
    if (!modal) return;
    try {
        const [res1, res2, res3] = await Promise.all([
            fetch('/api/admin/agent/settings', { credentials: 'include' }),
            fetch('/api/admin/bot-settings', { credentials: 'include' }),
            fetch('/api/admin/agent/notes', { credentials: 'include' })
        ]);
        if (res1.ok) {
            const d = await res1.json();
            _agentSettings = d;
            document.getElementById('agentSettingName').value      = d.agent_name      || 'น้องเอก';
            document.getElementById('agentSettingTone').value      = d.tone             || 'friendly';
            document.getElementById('agentSettingParticle').value  = d.ending_particle  || 'ครับ';
            document.getElementById('agentSettingCustom').value    = d.custom_prompt    || '';
        }
        if (res3.ok) { _agentRenderNotes(await res3.json()); }
        _loadBotTraining();
        if (res2.ok) {
            const b = await res2.json();
            const cb = document.getElementById('botChatEnabled');
            const sl = document.getElementById('botChatToggleSlider');
            if (cb) cb.checked = !!b.bot_chat_enabled;
            if (sl) sl.style.background = b.bot_chat_enabled ? '#a855f7' : '#ccc';
            if (document.getElementById('botChatName')) document.getElementById('botChatName').value = b.bot_chat_name || 'น้องนุ่น';
            if (document.getElementById('botChatPersona')) document.getElementById('botChatPersona').value = b.bot_chat_persona || '';
            const cb2 = document.getElementById('botChatEnabled');
            if (cb2) cb2.addEventListener('change', () => { if (sl) sl.style.background = cb2.checked ? '#a855f7' : '#ccc'; });
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
    const botPayload = {
        bot_chat_enabled: document.getElementById('botChatEnabled')?.checked ?? true,
        bot_chat_name:    (document.getElementById('botChatName')?.value.trim()) || 'น้องนุ่น',
        bot_chat_persona: document.getElementById('botChatPersona')?.value.trim() || '',
    };
    try {
        const [res1, res2] = await Promise.all([
            fetch('/api/admin/agent/settings', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                credentials: 'include', body: JSON.stringify(payload)
            }),
            fetch('/api/admin/bot-settings', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                credentials: 'include', body: JSON.stringify(botPayload)
            })
        ]);
        if (res1.ok) {
            _agentSettings = payload;
            agentCloseSettings();
            _agentMessages = [];
            _agentBriefed  = false;
            _agentShowWelcome();
        }
    } catch (e) { alert('บันทึกไม่สำเร็จ: ' + e.message); }
}

/* ---- Bot Training ---- */
let _botTrainingData = [];

async function _loadBotTraining() {
    try {
        const res = await fetch('/api/admin/bot-training', { credentials: 'include' });
        if (!res.ok) return;
        _botTrainingData = await res.json();
        _renderBotTraining();
    } catch (_) {}
}

function _renderBotTraining() {
    const list = document.getElementById('botTrainingList');
    const counter = document.getElementById('botTrainingCount');
    if (!list) return;
    const active = _botTrainingData.filter(e => e.is_active).length;
    if (counter) counter.textContent = `(${active} เปิดใช้ / ${_botTrainingData.length} ทั้งหมด)`;
    if (!_botTrainingData.length) {
        list.innerHTML = '<div style="text-align:center;padding:16px 0;color:#9ca3af;font-size:12px;">ยังไม่มีตัวอย่าง — กด "+ เพิ่มตัวอย่าง" เพื่อเริ่มเทรนบอท</div>';
        return;
    }
    list.innerHTML = _botTrainingData.map(ex => `
        <div style="border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;margin-bottom:8px;background:${ex.is_active ? '#fff' : '#f9fafb'};opacity:${ex.is_active ? '1' : '0.6'};">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
                <div style="flex:1;min-width:0;">
                    <div style="font-size:11px;font-weight:700;color:#a855f7;margin-bottom:3px;">❓ ${_escHtml(ex.question_pattern)}</div>
                    <div style="font-size:11px;color:#374151;line-height:1.5;">${_escHtml(ex.answer_template)}</div>
                </div>
                <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
                    <button onclick="botTrainingEdit(${ex.id})" style="padding:3px 8px;background:#f3f4f6;border:none;border-radius:6px;font-size:11px;cursor:pointer;color:#374151;">แก้ไข</button>
                    <button onclick="botTrainingToggle(${ex.id}, ${!ex.is_active})" style="padding:3px 8px;background:${ex.is_active ? '#fef3c7' : '#d1fae5'};border:none;border-radius:6px;font-size:11px;cursor:pointer;color:${ex.is_active ? '#92400e' : '#065f46'};">${ex.is_active ? 'ปิด' : 'เปิด'}</button>
                    <button onclick="botTrainingDelete(${ex.id})" style="padding:3px 8px;background:#fee2e2;border:none;border-radius:6px;font-size:11px;cursor:pointer;color:#991b1b;">ลบ</button>
                </div>
            </div>
        </div>`).join('');
}

function _escHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function botTrainingShowForm(id) {
    const form = document.getElementById('botTrainingForm');
    if (!form) return;
    document.getElementById('btfId').value = '';
    document.getElementById('btfQuestion').value = '';
    document.getElementById('btfAnswer').value = '';
    form.style.display = 'block';
    document.getElementById('btfQuestion').focus();
}

function botTrainingEdit(id) {
    const ex = _botTrainingData.find(e => e.id === id);
    if (!ex) return;
    const form = document.getElementById('botTrainingForm');
    if (!form) return;
    document.getElementById('btfId').value = id;
    document.getElementById('btfQuestion').value = ex.question_pattern;
    document.getElementById('btfAnswer').value = ex.answer_template;
    form.style.display = 'block';
    form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    document.getElementById('btfQuestion').focus();
}

function botTrainingCancelForm() {
    const form = document.getElementById('botTrainingForm');
    if (form) form.style.display = 'none';
}

async function botTrainingSave() {
    const id = document.getElementById('btfId').value;
    const q = (document.getElementById('btfQuestion').value || '').trim();
    const a = (document.getElementById('btfAnswer').value || '').trim();
    if (!q || !a) { alert('กรุณาระบุทั้งคำถามและคำตอบ'); return; }
    const body = { question_pattern: q, answer_template: a, is_active: true };
    const url = id ? `/api/admin/bot-training/${id}` : '/api/admin/bot-training';
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, {
            method, credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) { alert('บันทึกไม่สำเร็จ'); return; }
        botTrainingCancelForm();
        await _loadBotTraining();
    } catch (e) { alert('เกิดข้อผิดพลาด'); }
}

async function botTrainingToggle(id, isActive) {
    const ex = _botTrainingData.find(e => e.id === id);
    if (!ex) return;
    try {
        await fetch(`/api/admin/bot-training/${id}`, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_pattern: ex.question_pattern, answer_template: ex.answer_template, is_active: isActive })
        });
        await _loadBotTraining();
    } catch (_) {}
}

async function botTrainingDelete(id) {
    if (!confirm('ลบตัวอย่างนี้?')) return;
    try {
        await fetch(`/api/admin/bot-training/${id}`, { method: 'DELETE', credentials: 'include' });
        await _loadBotTraining();
    } catch (_) {}
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

    window.addEventListener('resize', () => { if (_agentOpen) _agentFitPanel(); });
    window.addEventListener('orientationchange', () => { setTimeout(() => { if (_agentOpen) _agentFitPanel(); }, 150); });

    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        new MutationObserver(() => { if (_agentOpen) _agentFitPanel(); })
            .observe(sidebar, { attributes: true, attributeFilter: ['class'] });
    }

    document.addEventListener('paste', (e) => {
        if (!_agentOpen) return;
        const items = e.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                e.preventDefault();
                const file = item.getAsFile();
                if (!file) return;
                _agentImageMime = item.type;
                _agentImageName = 'clipboard.png';
                const reader = new FileReader();
                reader.onload = (ev) => {
                    _agentImageB64 = ev.target.result.split(',')[1];
                    const preview    = document.getElementById('agentImagePreview');
                    const previewImg = document.getElementById('agentImagePreviewImg');
                    if (preview && previewImg) {
                        previewImg.src = ev.target.result;
                        preview.style.display = 'flex';
                    }
                };
                reader.readAsDataURL(file);
                return;
            }
        }
    });
});
