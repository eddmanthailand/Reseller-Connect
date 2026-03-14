// ==========================================
// Product Analytics Dashboard
// ==========================================

let _paTrendChart = null;

async function loadProductAnalytics() {
    const days     = document.getElementById('paRangeSel')?.value     || 30;
    const campaign = document.getElementById('paCampaignSel')?.value  || '';

    await Promise.all([
        _paLoadSummary(days, campaign),
        _paLoadTrend(days, campaign),
        _paLoadTopProducts(days, campaign),
        _paLoadCampaignBreakdown(days)
    ]);
}

// ── Summary cards ─────────────────────────────────────────────
async function _paLoadSummary(days, campaign) {
    const el = document.getElementById('paSummaryCards');
    if (!el) return;
    try {
        const params = new URLSearchParams({ days });
        if (campaign) params.set('campaign', campaign);
        const r = await fetch(`${API_URL}/product-analytics/summary?${params}`, { credentials: 'include' });
        const d = await r.json();

        const cards = [
            { label: 'ครั้งที่ดูสินค้า',     value: _paFmt(d.total_views),     color: '#007aff', icon: '👁️' },
            { label: 'สินค้าที่ถูกดู',        value: _paFmt(d.unique_products), color: '#34c759', icon: '📦' },
            { label: 'ผู้เข้าชม (session)',   value: _paFmt(d.unique_sessions), color: '#ff9f0a', icon: '👤' },
            { label: 'มาจากโฆษณา',           value: _paFmt(d.paid_sessions),   color: '#ff375f', icon: '📢' }
        ];

        el.innerHTML = cards.map(c => `
            <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);border-radius:14px;padding:14px 16px;">
                <div style="font-size:20px;margin-bottom:4px;">${c.icon}</div>
                <div style="font-size:22px;font-weight:700;color:${c.color};">${c.value}</div>
                <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px;">${c.label}</div>
            </div>
        `).join('');

        // Populate campaign filter dropdown once
        _paPopulateCampaignFilter(d.top_campaigns || []);

    } catch(e) {
        if (el) el.innerHTML = '<div style="color:rgba(255,255,255,0.3);font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
}

function _paPopulateCampaignFilter(topCampaigns) {
    const sel = document.getElementById('paCampaignSel');
    if (!sel || sel.dataset.populated) return;
    sel.dataset.populated = '1';
    topCampaigns.forEach(c => {
        if (!c.utm_campaign) return;
        const opt = document.createElement('option');
        opt.value = c.utm_campaign;
        opt.textContent = `${c.utm_campaign} (${_paFmt(c.views)} ครั้ง)`;
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
        const rows = await r.json();

        const labels  = rows.map(r => r.day ? r.day.slice(5) : '');
        const views   = rows.map(r => r.views || 0);
        const unique  = rows.map(r => r.unique_viewers || 0);

        if (_paTrendChart) { _paTrendChart.destroy(); _paTrendChart = null; }
        _paTrendChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'ครั้งที่ดู',
                        data: views,
                        borderColor: '#007aff',
                        backgroundColor: 'rgba(0,122,255,0.12)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: rows.length > 30 ? 0 : 3
                    },
                    {
                        label: 'ผู้เข้าชม',
                        data: unique,
                        borderColor: '#34c759',
                        backgroundColor: 'rgba(52,199,89,0.08)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: rows.length > 30 ? 0 : 3
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { labels: { color: 'rgba(255,255,255,0.6)', font: { size: 11 } } }
                },
                scales: {
                    x: { ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
                }
            }
        });
    } catch(e) {}
}

// ── Top products table ─────────────────────────────────────────
async function _paLoadTopProducts(days, campaign) {
    const el = document.getElementById('paTopProducts');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:16px;color:rgba(255,255,255,0.3);font-size:12px;">กำลังโหลด...</div>';
    try {
        const params = new URLSearchParams({ days, limit: 50 });
        if (campaign) params.set('campaign', campaign);
        const r = await fetch(`${API_URL}/product-analytics/top-products?${params}`, { credentials: 'include' });
        const rows = await r.json();

        if (!rows.length) {
            el.innerHTML = '<div style="text-align:center;padding:24px;color:rgba(255,255,255,0.3);font-size:13px;">ยังไม่มีข้อมูล — เริ่ม track เมื่อลูกค้ากดดูสินค้าในแคตตาล็อก</div>';
            return;
        }

        const maxViews = Math.max(...rows.map(r => r.views || 1));
        el.innerHTML = `
            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="color:rgba(255,255,255,0.4);border-bottom:1px solid rgba(255,255,255,0.08);">
                            <th style="text-align:left;padding:8px 10px;font-weight:500;">#</th>
                            <th style="text-align:left;padding:8px 10px;font-weight:500;">สินค้า</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">ดู</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">ผู้เข้าชม</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">สั่งซื้อ</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">Conv.</th>
                            <th style="padding:8px 10px;min-width:80px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((row, i) => {
                            const pct = Math.round((row.views / maxViews) * 100);
                            const convColor = row.conversion_pct >= 10 ? '#34c759' : row.conversion_pct >= 3 ? '#ff9f0a' : 'rgba(255,255,255,0.4)';
                            const img = row.image_url
                                ? `<img src="${row.image_url}" style="width:32px;height:32px;border-radius:8px;object-fit:cover;flex-shrink:0;" onerror="this.style.display='none'">`
                                : `<div style="width:32px;height:32px;border-radius:8px;background:rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;">👗</div>`;
                            return `
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                    <td style="padding:8px 10px;color:rgba(255,255,255,0.3);">${i+1}</td>
                                    <td style="padding:8px 10px;">
                                        <div style="display:flex;align-items:center;gap:8px;">
                                            ${img}
                                            <span style="color:rgba(255,255,255,0.85);line-height:1.3;">${_paEsc(row.name)}</span>
                                        </div>
                                    </td>
                                    <td style="padding:8px 10px;text-align:right;font-weight:600;color:#007aff;">${_paFmt(row.views)}</td>
                                    <td style="padding:8px 10px;text-align:right;color:rgba(255,255,255,0.6);">${_paFmt(row.unique_viewers)}</td>
                                    <td style="padding:8px 10px;text-align:right;color:rgba(255,255,255,0.6);">${_paFmt(row.orders)}</td>
                                    <td style="padding:8px 10px;text-align:right;font-weight:600;color:${convColor};">${row.conversion_pct}%</td>
                                    <td style="padding:8px 10px;">
                                        <div style="height:6px;background:rgba(255,255,255,0.07);border-radius:3px;overflow:hidden;">
                                            <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#007aff,#5856d6);border-radius:3px;transition:width 0.5s;"></div>
                                        </div>
                                    </td>
                                </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`;
    } catch(e) {
        el.innerHTML = '<div style="text-align:center;padding:16px;color:rgba(255,59,48,0.7);font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
}

// ── Campaign breakdown ─────────────────────────────────────────
async function _paLoadCampaignBreakdown(days) {
    const el = document.getElementById('paCampaignBreakdown');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:16px;color:rgba(255,255,255,0.3);font-size:12px;">กำลังโหลด...</div>';
    try {
        const r = await fetch(`${API_URL}/product-analytics/campaign-breakdown?days=${days}`, { credentials: 'include' });
        const rows = await r.json();

        if (!rows.length) {
            el.innerHTML = '<div style="text-align:center;padding:24px;color:rgba(255,255,255,0.3);font-size:13px;">ยังไม่มีข้อมูล</div>';
            return;
        }

        const maxViews = Math.max(...rows.map(r => r.views || 1));
        el.innerHTML = `
            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="color:rgba(255,255,255,0.4);border-bottom:1px solid rgba(255,255,255,0.08);">
                            <th style="text-align:left;padding:8px 10px;font-weight:500;">แคมเปญ</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">ครั้งที่ดู</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">สินค้า</th>
                            <th style="text-align:right;padding:8px 10px;font-weight:500;">ผู้เข้าชม</th>
                            <th style="padding:8px 10px;min-width:80px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => {
                            const pct = Math.round((row.views / maxViews) * 100);
                            const isPaid = row.campaign !== '(ไม่มี UTM)';
                            return `
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                    <td style="padding:8px 10px;">
                                        <span style="color:${isPaid ? '#ff9f0a' : 'rgba(255,255,255,0.5)'};">
                                            ${isPaid ? '📢' : '🌐'} ${_paEsc(row.campaign)}
                                        </span>
                                    </td>
                                    <td style="padding:8px 10px;text-align:right;font-weight:600;color:#007aff;">${_paFmt(row.views)}</td>
                                    <td style="padding:8px 10px;text-align:right;color:rgba(255,255,255,0.6);">${_paFmt(row.unique_products)}</td>
                                    <td style="padding:8px 10px;text-align:right;color:rgba(255,255,255,0.6);">${_paFmt(row.unique_viewers)}</td>
                                    <td style="padding:8px 10px;">
                                        <div style="height:6px;background:rgba(255,255,255,0.07);border-radius:3px;overflow:hidden;">
                                            <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#ff9f0a,#ff375f);border-radius:3px;transition:width 0.5s;"></div>
                                        </div>
                                    </td>
                                </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`;
    } catch(e) {
        el.innerHTML = '<div style="text-align:center;padding:16px;color:rgba(255,59,48,0.7);font-size:12px;">โหลดไม่สำเร็จ</div>';
    }
}

// ── Helpers ────────────────────────────────────────────────────
function _paFmt(n) {
    if (n == null || n === '') return '0';
    return Number(n).toLocaleString('th-TH');
}
function _paEsc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
