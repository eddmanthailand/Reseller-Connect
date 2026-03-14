// ==========================================
// Product Analytics — Apple-style Dashboard
// ==========================================

let _paTrendChart = null;
let _paCampaignsPopulated = false;

async function loadProductAnalytics() {
    const days     = document.getElementById('paRangeSel')?.value    || 30;
    const campaign = document.getElementById('paCampaignSel')?.value || '';

    await Promise.all([
        _paLoadSummary(days, campaign),
        _paLoadTrend(days, campaign),
        _paLoadTopProducts(days, campaign),
        _paLoadCampaignBreakdown(days)
    ]);
}

// ── Summary cards ──────────────────────────────────────────────
async function _paLoadSummary(days, campaign) {
    const el = document.getElementById('paSummaryCards');
    if (!el) return;
    try {
        const params = new URLSearchParams({ days });
        if (campaign) params.set('campaign', campaign);
        const r = await fetch(`${API_URL}/product-analytics/summary?${params}`, { credentials: 'include' });
        if (!r.ok) throw new Error(r.status);
        const d = await r.json();

        const cards = [
            { icon: '👁️', val: d.total_views     || 0, lbl: 'ครั้งที่ดูสินค้า',   color: 'var(--pa-blue)',   sub: `${days} วันล่าสุด` },
            { icon: '📦', val: d.unique_products  || 0, lbl: 'สินค้าที่ถูกดู',     color: 'var(--pa-green)',  sub: 'รายการ' },
            { icon: '👤', val: d.unique_sessions  || 0, lbl: 'ผู้เข้าชม',          color: 'var(--pa-orange)', sub: 'unique sessions' },
            { icon: '📢', val: d.paid_sessions    || 0, lbl: 'มาจากโฆษณา',        color: 'var(--pa-purple)', sub: 'มี UTM Campaign' }
        ];

        el.innerHTML = cards.map(c => `
            <div class="pa-card">
                <div class="pa-card-icon">${c.icon}</div>
                <div class="pa-card-val" style="color:${c.color};">${_paFmt(c.val)}</div>
                <div class="pa-card-lbl">${c.lbl}</div>
                <div class="pa-card-sub">${c.sub}</div>
            </div>`).join('');

        if (!_paCampaignsPopulated) _paPopulateCampaignFilter(d.top_campaigns || []);

    } catch(e) {
        if (el) el.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:rgba(255,59,48,0.7);font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
}

function _paPopulateCampaignFilter(topCampaigns) {
    const sel = document.getElementById('paCampaignSel');
    if (!sel) return;
    _paCampaignsPopulated = true;
    // Remove old options except first
    while (sel.options.length > 1) sel.remove(1);
    topCampaigns.forEach(c => {
        if (!c.utm_campaign) return;
        const opt = document.createElement('option');
        opt.value = c.utm_campaign;
        opt.textContent = `${c.utm_campaign}`;
        sel.appendChild(opt);
    });
}

// ── Daily trend chart ──────────────────────────────────────────
async function _paLoadTrend(days, campaign) {
    const canvas = document.getElementById('paTrendChart');
    if (!canvas) return;
    try {
        const params = new URLSearchParams({ days });
        if (campaign) params.set('campaign', campaign);
        const r = await fetch(`${API_URL}/product-analytics/daily-trend?${params}`, { credentials: 'include' });
        if (!r.ok) throw new Error(r.status);
        const rows = await r.json();

        const labels = rows.map(r => {
            if (!r.day) return '';
            const d = new Date(r.day);
            return `${d.getDate()}/${d.getMonth()+1}`;
        });
        const views  = rows.map(r => r.views         || 0);
        const unique = rows.map(r => r.unique_viewers || 0);

        if (_paTrendChart) { _paTrendChart.destroy(); _paTrendChart = null; }

        const noData = rows.length === 0;
        if (noData) {
            canvas.parentElement.innerHTML += '<div class="pa-empty"><div class="pa-empty-icon">📈</div>ยังไม่มีข้อมูล เริ่มสะสมเมื่อลูกค้ากดดูสินค้า</div>';
            return;
        }

        _paTrendChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'ครั้งที่ดู',
                        data: views,
                        borderColor: '#007aff',
                        backgroundColor: 'rgba(0,122,255,0.08)',
                        tension: 0.42,
                        fill: true,
                        pointRadius: rows.length > 45 ? 0 : 3,
                        pointBackgroundColor: '#007aff',
                        pointHoverRadius: 5,
                        borderWidth: 2
                    },
                    {
                        label: 'ผู้เข้าชม',
                        data: unique,
                        borderColor: '#34c759',
                        backgroundColor: 'rgba(52,199,89,0.06)',
                        tension: 0.42,
                        fill: true,
                        pointRadius: rows.length > 45 ? 0 : 3,
                        pointBackgroundColor: '#34c759',
                        pointHoverRadius: 5,
                        borderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: {
                            color: '#6e6e73',
                            font: { size: 11, family: '-apple-system, BlinkMacSystemFont, sans-serif' },
                            boxWidth: 12, boxHeight: 2
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(255,255,255,0.96)',
                        borderColor: '#e5e5ea',
                        borderWidth: 1,
                        titleColor: '#3a3a3c',
                        bodyColor: '#1d1d1f',
                        padding: 12,
                        cornerRadius: 12,
                        boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
                        callbacks: {
                            labelColor: (ctx) => ({
                                borderColor: ctx.dataset.borderColor,
                                backgroundColor: ctx.dataset.borderColor
                            })
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#aeaeb2', font: { size: 10 }, maxTicksLimit: 10 },
                        grid: { color: '#f2f2f7', drawBorder: false }
                    },
                    y: {
                        ticks: { color: '#aeaeb2', font: { size: 10 } },
                        grid: { color: '#f2f2f7', drawBorder: false },
                        beginAtZero: true
                    }
                }
            }
        });
    } catch(e) {}
}

// ── Top products image grid ────────────────────────────────────
async function _paLoadTopProducts(days, campaign) {
    const el = document.getElementById('paTopProducts');
    if (!el) return;
    try {
        const params = new URLSearchParams({ days, limit: 24 });
        if (campaign) params.set('campaign', campaign);
        const r = await fetch(`${API_URL}/product-analytics/top-products?${params}`, { credentials: 'include' });
        if (!r.ok) throw new Error(r.status);
        const rows = await r.json();

        if (!rows.length) {
            el.innerHTML = '<div class="pa-empty"><div class="pa-empty-icon">📦</div>ยังไม่มีข้อมูล<br><small>ข้อมูลจะสะสมเมื่อลูกค้ากดดูสินค้าในแคตตาล็อก</small></div>';
            return;
        }

        const maxViews = Math.max(...rows.map(r => r.views || 1));
        const medals   = ['🥇','🥈','🥉'];

        const cards = rows.map((row, i) => {
            const pct  = Math.round((row.views / maxViews) * 100);
            const conv = parseFloat(row.conversion_pct || 0);
            const convClass = conv >= 10 ? 'good' : conv >= 3 ? 'mid' : '';
            const convLabel = conv > 0 ? `${conv}% conv.` : '';
            const rankHtml  = i < 3
                ? `<div class="pa-prod-card-rank">${medals[i]}</div>`
                : `<div class="pa-prod-card-rank" style="font-size:11px;font-weight:700;background:rgba(0,0,0,0.45);color:#fff;border-radius:6px;padding:2px 6px;top:8px;left:8px;">${i+1}</div>`;

            const imgContent = row.image_url
                ? `<img class="pa-prod-card-img" src="${_paEsc(row.image_url)}" alt="${_paEsc(row.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                   <div class="pa-prod-card-ph" style="display:none;">👗</div>`
                : `<div class="pa-prod-card-ph">👗</div>`;

            return `
                <div class="pa-prod-card">
                    ${imgContent}
                    ${rankHtml}
                    <div class="pa-prod-card-overlay">
                        <div class="pa-prod-card-name">${_paEsc(row.name)}</div>
                        <div class="pa-prod-card-meta">
                            <div class="pa-prod-card-views">
                                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                ${_paFmt(row.views)}
                            </div>
                            ${convLabel ? `<div class="pa-prod-card-conv ${convClass}">${convLabel}</div>` : ''}
                        </div>
                    </div>
                    <div class="pa-prod-card-bar">
                        <div class="pa-prod-card-bar-fill" style="width:${pct}%"></div>
                    </div>
                </div>`;
        }).join('');

        el.innerHTML = `<div class="pa-prod-grid">${cards}</div>`;

    } catch(e) {
        if (el) el.innerHTML = '<div class="pa-empty" style="color:#ff3b30;">โหลดไม่สำเร็จ</div>';
    }
}

// ── Campaign breakdown ─────────────────────────────────────────
async function _paLoadCampaignBreakdown(days) {
    const el = document.getElementById('paCampaignBreakdown');
    if (!el) return;
    try {
        const r = await fetch(`${API_URL}/product-analytics/campaign-breakdown?days=${days}`, { credentials: 'include' });
        if (!r.ok) throw new Error(r.status);
        const rows = await r.json();

        if (!rows.length) {
            el.innerHTML = '<div class="pa-empty"><div class="pa-empty-icon">📢</div>ยังไม่มีข้อมูล</div>';
            return;
        }

        const maxViews = Math.max(...rows.map(r => r.views || 1));
        el.innerHTML = rows.map(row => {
            const pct     = Math.round((row.views / maxViews) * 100);
            const isPaid  = row.campaign !== '(ไม่มี UTM)';
            const label   = row.campaign.length > 24 ? row.campaign.slice(0, 22) + '…' : row.campaign;
            return `
                <div class="pa-camp-row">
                    <div class="pa-camp-badge ${isPaid ? '' : 'organic'}">${label}</div>
                    <div class="pa-camp-bar-wrap">
                        <div class="pa-camp-bar" style="width:${pct}%;${isPaid ? '' : 'background:linear-gradient(90deg,rgba(255,255,255,0.3),rgba(255,255,255,0.2));'}"></div>
                    </div>
                    <div class="pa-camp-views">${_paFmt(row.views)}</div>
                </div>`;
        }).join('');

    } catch(e) {
        if (el) el.innerHTML = '<div class="pa-empty" style="color:rgba(255,59,48,0.6);">โหลดไม่สำเร็จ</div>';
    }
}

// ── Helpers ────────────────────────────────────────────────────
function _paFmt(n) {
    if (n == null || n === '') return '0';
    return Number(n).toLocaleString('th-TH');
}
function _paEsc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
