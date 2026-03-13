// ==================== FACEBOOK PIXEL SETTINGS ====================

async function loadFacebookPixelSettings() {
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('Loaded Facebook Pixel settings:', data);
            
            if (data.pixel_id) {
                document.getElementById('fbPixelId').value = data.pixel_id;
            }
            if (data.is_active !== undefined) {
                document.getElementById('fbPixelActive').checked = data.is_active;
            }
        }
    } catch (error) {
        console.error('Error loading Facebook Pixel settings:', error);
    }
}

async function saveFacebookPixelSettings() {
    const pixelId = document.getElementById('fbPixelId').value.trim();
    const accessToken = document.getElementById('fbAccessToken').value.trim();
    const isActive = document.getElementById('fbPixelActive').checked;
    
    if (isActive && !pixelId) {
        showAlert('กรุณากรอก Pixel ID ก่อนเปิดใช้งาน', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                pixel_id: pixelId,
                access_token: accessToken,
                is_active: isActive,
                track_page_view: true,
                track_lead: true,
                track_complete_registration: true
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('บันทึกการตั้งค่า Facebook Pixel สำเร็จ', 'success');
            // Clear access token field after save for security
            document.getElementById('fbAccessToken').value = '';
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving Facebook Pixel settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

// ==================== FACEBOOK ADS PAGE ====================

let fbAdsChart = null;

async function loadFacebookAdsPage() {
    const urlInput = document.getElementById('fbLandingUrl');
    if (urlInput) urlInput.value = 'https://ekgshops.com/catalog';
    loadFbAdsPixelSettings();
    loadFacebookAdsStats();
    loadMetaApiStatus();
    loadAdLandingUrls();
    loadTrafficSources('total');
    loadFunnelStats('total');
}

async function loadAdLandingUrls() {
    const container = document.getElementById('adLandingUrls');
    if (!container) return;
    const base = window.location.origin;

    try {
        const [brandsRes, catsRes] = await Promise.all([
            fetch('/api/public/brands').then(r => r.json()).catch(() => ({ brands: [] })),
            fetch('/api/public/categories').then(r => r.json()).catch(() => ({ categories: [] }))
        ]);

        const urlRow = (label, url, desc) => `
            <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 12px 14px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.8); margin-bottom: 3px;">${label}</div>
                    <div style="font-size: 11px; color: rgba(255,255,255,0.4); margin-bottom: 4px;">${desc}</div>
                    <code style="font-size: 12px; color: #a5f3fc; word-break: break-all;">${url}</code>
                </div>
                <div style="display: flex; gap: 6px; flex-shrink: 0;">
                    <button onclick="copyAdUrl('${url.replace(/'/g, "\\'")}', this)" style="background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.4); color: #a5b4fc; font-size: 11px; padding: 5px 10px; border-radius: 6px; cursor: pointer; white-space: nowrap;">Copy</button>
                    <a href="${url}" target="_blank" style="background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #6ee7b7; font-size: 11px; padding: 5px 10px; border-radius: 6px; text-decoration: none; white-space: nowrap;">ดู ↗</a>
                </div>
            </div>`;

        let html = urlRow('🎯 หน้าสมัครสมาชิก (Landing Page)', `${base}/join`, 'หน้าหลักสำหรับโฆษณา — สมัครด้วย Google, ข้อมูลสิทธิประโยชน์ครบ เหมาะกับ Campaign สมัครสมาชิก');
        html += urlRow('ทุกสินค้า (หน้าหลัก)', `${base}/catalog`, 'แสดงสินค้าทั้งหมด เหมาะกับโฆษณา Awareness');
        html += urlRow('เฉพาะสินค้าโปรโมท', `${base}/catalog?featured=1`, 'แสดงเฉพาะสินค้าที่ติด ★ ไว้ เหมาะกับ Campaign เฉพาะกิจ');

        (brandsRes.brands || []).forEach(b => {
            html += urlRow(`แบรนด์: ${b.name}`, `${base}/catalog?brand=${b.id}`, `แสดงเฉพาะสินค้าแบรนด์ ${b.name}`);
        });
        (catsRes.categories || []).forEach(c => {
            html += urlRow(`หมวด: ${c.name}`, `${base}/catalog?category=${c.id}`, `แสดงเฉพาะหมวด ${c.name}`);
        });
        (brandsRes.brands || []).forEach(b => {
            html += urlRow(`แบรนด์ ${b.name} + โปรโมท`, `${base}/catalog?brand=${b.id}&featured=1`, `สินค้าโปรโมทของแบรนด์ ${b.name} เท่านั้น`);
        });

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div style="opacity:0.5;font-size:13px;">โหลด URL ไม่สำเร็จ</div>`;
    }
}

function copyAdUrl(url, btn) {
    navigator.clipboard.writeText(url).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied ✓';
        btn.style.background = 'rgba(16,185,129,0.25)';
        btn.style.color = '#6ee7b7';
        setTimeout(() => { btn.textContent = orig; btn.style.background = ''; btn.style.color = ''; }, 2000);
    });
}

/* ─── Meta Marketing API ─── */
async function loadMetaApiStatus() {
    try {
        const r = await fetch('/api/admin/facebook-ads/meta-settings', { credentials: 'include' });
        if (!r.ok) return;
        const d = await r.json();
        const el = document.getElementById('metaApiStatus');
        const accountEl = document.getElementById('metaAdAccountId');
        if (el) {
            if (d.has_token && d.has_account) {
                el.style.background = 'rgba(74,222,128,0.1)';
                el.style.border = '1px solid rgba(74,222,128,0.3)';
                el.innerHTML = `✅ เชื่อมต่อแล้ว | Account: <strong>${d.meta_ad_account_id}</strong> | Token: <code style="font-size:10px;">${d.meta_access_token_masked}</code>${d.token_from_env ? ' <span style="opacity:0.6;">(env)</span>' : ''}`;
                document.getElementById('metaInsightsCard').style.display = '';
                loadMetaInsights('30d');
            } else {
                el.style.background = 'rgba(251,191,36,0.1)';
                el.style.border = '1px solid rgba(251,191,36,0.3)';
                el.innerHTML = '⚠️ ยังไม่ได้ตั้งค่า — กรอก Access Token และ Ad Account ID แล้วกดบันทึก';
            }
        }
        if (accountEl && d.meta_ad_account_id) accountEl.value = d.meta_ad_account_id;
    } catch (e) { console.error('loadMetaApiStatus', e); }
}

async function saveMetaApiSettings() {
    const token = document.getElementById('metaAccessToken')?.value || '';
    const account = document.getElementById('metaAdAccountId')?.value.trim() || '';
    if (!account) { showAlert('กรุณาระบุ Ad Account ID', 'error'); return; }
    try {
        const r = await fetch('/api/admin/facebook-ads/meta-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ meta_access_token: token, meta_ad_account_id: account })
        });
        const d = await r.json();
        if (r.ok) {
            showAlert('บันทึก Meta API credentials เรียบร้อย', 'success');
            document.getElementById('metaAccessToken').value = '';
            loadMetaApiStatus();
        } else {
            showAlert(d.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (e) { showAlert('ไม่สามารถบันทึกได้', 'error'); }
}

async function loadMetaInsights(period = '30d') {
    const card = document.getElementById('metaInsightsCard');
    const content = document.getElementById('metaInsightsContent');
    if (!card || !content) return;
    card.style.display = '';
    content.innerHTML = '<div style="text-align:center;padding:20px;opacity:0.5;font-size:13px;">กำลังดึงข้อมูลจาก Meta...</div>';
    ['7d','30d','90d'].forEach(p => {
        const btn = document.getElementById(`metaBtn${p}`);
        if (btn) { btn.className = p === period ? 'btn-primary' : 'btn-secondary'; btn.style.padding='4px 10px'; btn.style.fontSize='11px'; }
    });
    try {
        const r = await fetch(`/api/admin/facebook-ads/meta-insights?period=${period}`, { credentials: 'include' });
        const d = await r.json();
        if (!r.ok || d.error) {
            content.innerHTML = `<div style="color:#f87171;font-size:13px;padding:12px;">${d.error || 'ไม่สามารถดึงข้อมูลได้'}</div>`;
            return;
        }
        if (!d.data) {
            content.innerHTML = `<div style="opacity:0.5;font-size:13px;padding:12px;text-align:center;">${d.message || 'ไม่มีข้อมูล'}</div>`;
            return;
        }
        const x = d.data;
        const roas_color = x.roas >= 3 ? '#4ade80' : x.roas >= 1.5 ? '#fbbf24' : '#f87171';
        content.innerHTML = `
            <div style="font-size:11px;opacity:0.5;margin-bottom:12px;">${d.since} — ${d.until}</div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px;">
                ${_metaStat('💰 ใช้จ่าย', '฿' + x.spend.toLocaleString('th-TH',{minimumFractionDigits:0}), '#60a5fa')}
                ${_metaStat('📊 ROAS', x.roas + 'x', roas_color)}
                ${_metaStat('🛒 ยอดซื้อ', '฿' + x.purchase_value.toLocaleString('th-TH',{minimumFractionDigits:0}), '#4ade80')}
                ${_metaStat('👁 Impressions', x.impressions.toLocaleString(), '#e2e8f0')}
                ${_metaStat('🖱 Clicks', x.clicks.toLocaleString(), '#e2e8f0')}
                ${_metaStat('📈 CTR', x.ctr.toFixed(2) + '%', '#e2e8f0')}
                ${_metaStat('💵 CPC', '฿' + x.cpc.toFixed(2), '#e2e8f0')}
                ${_metaStat('📢 CPM', '฿' + x.cpm.toFixed(2), '#e2e8f0')}
                ${_metaStat('🛒 Conversions', x.purchases, '#e2e8f0')}
            </div>
        `;
    } catch (e) {
        content.innerHTML = `<div style="color:#f87171;font-size:13px;padding:12px;">ไม่สามารถเชื่อมต่อได้: ${e.message}</div>`;
    }
}

function _metaStat(label, value, color = '#1d1d1f') {
    return `<div style="background:#f9f9f9;border-radius:9px;padding:10px 12px;border:0.5px solid #e5e5ea;">
        <div style="font-size:11px;color:#6e6e73;margin-bottom:3px;font-weight:500;">${label}</div>
        <div style="font-size:16px;font-weight:700;color:${color};">${value}</div>
    </div>`;
}

async function loadFbAdsPixelSettings() {
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, { credentials: 'include' });
        if (response.ok) {
            const data = await response.json();
            if (data.pixel_id) {
                const pixelInput = document.getElementById('fbAdsPixelId');
                if (pixelInput) pixelInput.value = data.pixel_id;
            }
            if (data.is_active !== undefined) {
                const activeCheck = document.getElementById('fbAdsPixelActive');
                if (activeCheck) activeCheck.checked = data.is_active;
            }
        }
    } catch (error) {
        console.error('Error loading Facebook Pixel settings:', error);
    }
}

async function saveAllMetaSettings() {
    const pixelId   = (document.getElementById('fbAdsPixelId')?.value || '').trim();
    const token     = (document.getElementById('fbAdsAccessToken')?.value || '').trim();
    const accountId = (document.getElementById('metaAdAccountId')?.value || '').trim();
    const isActive  = document.getElementById('fbAdsPixelActive')?.checked || false;

    if (isActive && !pixelId) { showAlert('กรุณากรอก Pixel ID ก่อนเปิดใช้งาน', 'error'); return; }

    const statusEl = document.getElementById('metaApiStatus');
    if (statusEl) { statusEl.innerHTML = '<span style="color:#6e6e73;">กำลังบันทึก...</span>'; }

    try {
        // บันทึก Pixel settings (CAPI token + pixel_id + is_active)
        const r1 = await fetch(`${API_URL}/facebook-pixel-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ pixel_id: pixelId, access_token: token, is_active: isActive,
                                   track_page_view: true, track_lead: true, track_complete_registration: true })
        });

        // บันทึก Meta Ads API token + account_id
        const r2 = await fetch(`${API_URL}/admin/facebook-ads/meta-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ meta_access_token: token, meta_ad_account_id: accountId })
        });

        if (r1.ok && r2.ok) {
            showAlert('บันทึกการตั้งค่าเรียบร้อย', 'success');
            const tokenInput = document.getElementById('fbAdsAccessToken');
            if (tokenInput && token) tokenInput.value = '';
            await loadMetaApiStatus();
        } else {
            const e1 = r1.ok ? null : (await r1.json()).error;
            const e2 = r2.ok ? null : (await r2.json()).error;
            showAlert(e1 || e2 || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch(e) {
        showAlert('ไม่สามารถบันทึกได้: ' + e.message, 'error');
    }
}

async function saveFbAdsPixelSettings() {
    const pixelId = document.getElementById('fbAdsPixelId').value.trim();
    const accessToken = document.getElementById('fbAdsAccessToken').value.trim();
    const isActive = document.getElementById('fbAdsPixelActive').checked;
    
    if (isActive && !pixelId) {
        showAlert('กรุณากรอก Pixel ID ก่อนเปิดใช้งาน', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                pixel_id: pixelId,
                access_token: accessToken,
                is_active: isActive,
                track_page_view: true,
                track_lead: true,
                track_complete_registration: true
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('บันทึกการตั้งค่า Facebook Pixel สำเร็จ', 'success');
            document.getElementById('fbAdsAccessToken').value = '';
        } else {
            showAlert(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving Facebook Pixel settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

let _fbStatsData = null;
let _fbActivePeriod = 'today';

function fbSetPeriod(period, btn) {
    _fbActivePeriod = period;
    document.querySelectorAll('.fb-seg-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    if (_fbStatsData) _fbApplyPeriod(_fbStatsData, period);
}

function _fbApplyPeriod(data, period) {
    const p = data[period];
    if (!p) return;
    const visits = document.getElementById('fbStatsTodayVisits');
    const regs = document.getElementById('fbStatsTodayRegs');
    const conv = document.getElementById('fbStatsTodayConv');
    if (visits) visits.textContent = p.visits.toLocaleString();
    if (regs) regs.textContent = p.registrations.toLocaleString();
    if (conv) conv.textContent = p.conversion + '%';
}

async function loadFacebookAdsStats() {
    try {
        const response = await fetch(`${API_URL}/facebook-ads/stats`, { credentials: 'include' });
        if (!response.ok) { console.error('Failed to load Facebook Ads stats'); return; }

        const data = await response.json();
        _fbStatsData = data;

        // Fill hidden legacy IDs for any other code that uses them
        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setEl('fbStatsWeekVisits', data.week.visits);
        setEl('fbStatsWeekRegs', data.week.registrations);
        setEl('fbStatsWeekConv', data.week.conversion + '%');
        setEl('fbStatsMonthVisits', data.month.visits);
        setEl('fbStatsMonthRegs', data.month.registrations);
        setEl('fbStatsMonthConv', data.month.conversion + '%');
        setEl('fbStatsTotalVisits', data.total.visits);
        setEl('fbStatsTotalRegs', data.total.registrations);
        setEl('fbStatsTotalConv', data.total.conversion + '%');

        // Apply current period to visible cards
        _fbApplyPeriod(data, _fbActivePeriod);

        // Chart, campaign breakdown, recent regs
        renderFbAdsChart(data.chart);
        renderCampaignBreakdown(data.campaign_breakdown || []);
        renderFbRecentRegistrations(data.recent_registrations);

        // Pixel badge
        const badge = document.getElementById('fbPixelStatusBadge');
        if (badge) badge.style.display = 'inline-flex';

    } catch (error) {
        console.error('Error loading Facebook Ads stats:', error);
    }
}

let _fbCampaignCharts = {};
let _fbOpenCampaign = null;

function _statusBadge(s) {
    if (s === 'active') return '<span style="display:inline-block;padding:1px 7px;border-radius:20px;font-size:10px;font-weight:600;background:#dcfce7;color:#15803d;">● Active</span>';
    if (s === 'pausing') return '<span style="display:inline-block;padding:1px 7px;border-radius:20px;font-size:10px;font-weight:600;background:#fef9c3;color:#854d0e;">⏸ หยุดพัก</span>';
    return '<span style="display:inline-block;padding:1px 7px;border-radius:20px;font-size:10px;font-weight:600;background:#f1f5f9;color:#64748b;">— Inactive</span>';
}

function renderCampaignBreakdown(campaigns) {
    const el = document.getElementById('fbCampaignBreakdown');
    if (!el) return;
    if (!campaigns || campaigns.length === 0) {
        el.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:13px;padding:20px 0;">ยังไม่มีข้อมูลแคมเปญ<br><span style="font-size:11px;">เพิ่ม utm_campaign= ใน URL โฆษณา</span></div>';
        return;
    }
    const max = campaigns[0].visits || 1;
    el.innerHTML = campaigns.map((c, i) => {
        const pct = Math.round((c.visits / max) * 100);
        const safeName = (c.campaign || '').replace(/"/g, '&quot;');
        const displayName = c.campaign === '(ไม่ระบุแคมเปญ)'
            ? '<span style="color:#6e6e73;font-style:italic;">ไม่ระบุ</span>'
            : `<span style="color:#1d1d1f;font-weight:500;">${c.campaign}</span>`;
        const budgetChip = c.budget > 0
            ? `<span style="font-size:10px;color:#6e6e73;margin-left:4px;">฿${(c.budget||0).toLocaleString()}</span>`
            : '';
        const cpvChip = c.cpv != null
            ? `<span style="font-size:10px;color:#ff9500;margin-left:4px;">CPV ฿${c.cpv}</span>`
            : '';
        const hideBtn = c.campaign !== '(ไม่ระบุแคมเปญ)'
            ? `<button onclick="event.stopPropagation();hideCampaign('${safeName}',this)" title="ซ่อนแคมเปญนี้"
                style="border:none;background:none;cursor:pointer;font-size:10px;color:#c7c7cc;padding:2px 4px;border-radius:4px;line-height:1;flex-shrink:0;"
                onmouseover="this.style.color='#ff3b30'" onmouseout="this.style.color='#c7c7cc'">ซ่อน</button>`
            : '';
        return `
        <div id="fbRow_${safeName.replace(/[^a-zA-Z0-9]/g,'_')}" style="margin-bottom:4px;">
            <div onclick="toggleCampaignDetail('${safeName}', this)" style="cursor:pointer;padding:8px 6px;border-radius:8px;transition:background 0.15s;" onmouseover="this.style.background='#f9f9f9'" onmouseout="this.style.background='transparent'">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="display:flex;align-items:center;gap:6px;font-size:13px;flex:1;min-width:0;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#c7c7cc" stroke-width="2.5" style="transition:transform 0.2s;flex-shrink:0;" class="fbChevronIcon"><polyline points="9 18 15 12 9 6"/></svg>
                        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${displayName}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                        ${hideBtn}
                        ${_statusBadge(c.active_status)}
                        <span style="font-size:13px;font-weight:600;color:#007aff;">${(c.visits||0).toLocaleString()}</span>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:6px;margin-left:18px;margin-bottom:5px;">
                    ${budgetChip}${cpvChip}
                </div>
                <div style="height:4px;background:#f2f2f7;border-radius:2px;overflow:hidden;margin-left:18px;">
                    <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#007aff,#34c759);border-radius:2px;transition:width 0.5s ease;"></div>
                </div>
            </div>
            <div id="fbDetail_${safeName.replace(/[^a-zA-Z0-9]/g,'_')}" data-campaign="${safeName}" data-budget="${c.budget||0}" style="display:none;margin:0 0 8px 18px;"></div>
        </div>`;
    }).join('');
}

async function hideCampaign(campaignName, btnEl) {
    if (!confirm(`ซ่อนแคมเปญ "${campaignName}" ออกจาก Dashboard?\n(สามารถยกเลิกได้ในอนาคต)`)) return;
    try {
        const r = await fetch(`${API_URL}/facebook-ads/campaign-hide`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ campaign_name: campaignName, is_hidden: true })
        });
        if (r.ok) {
            const safeId = campaignName.replace(/[^a-zA-Z0-9]/g, '_');
            const row = document.getElementById(`fbRow_${safeId}`);
            if (row) { row.style.opacity = '0'; setTimeout(() => row.remove(), 300); }
        } else {
            showAlert('ไม่สามารถซ่อนแคมเปญได้', 'error');
        }
    } catch(e) { showAlert('เกิดข้อผิดพลาด', 'error'); }
}

async function toggleCampaignDetail(campaign, rowEl) {
    const safeId = campaign.replace(/[^a-zA-Z0-9]/g, '_');
    const detailEl = document.getElementById(`fbDetail_${safeId}`);
    if (!detailEl) return;

    const chevrons = rowEl.querySelectorAll('svg');
    const chevron = chevrons[0];

    if (detailEl.style.display !== 'none') {
        detailEl.style.display = 'none';
        if (chevron) chevron.style.transform = '';
        _fbOpenCampaign = null;
        return;
    }

    // Close previously open panel
    if (_fbOpenCampaign && _fbOpenCampaign !== safeId) {
        const prev = document.getElementById(`fbDetail_${_fbOpenCampaign}`);
        if (prev) prev.style.display = 'none';
        const prevChevrons = prev && prev.parentElement.querySelectorAll('svg');
        if (prevChevrons && prevChevrons[0]) prevChevrons[0].style.transform = '';
    }
    _fbOpenCampaign = safeId;

    if (chevron) chevron.style.transform = 'rotate(90deg)';
    detailEl.style.display = 'block';
    detailEl.innerHTML = `<div style="padding:12px;text-align:center;color:#6e6e73;font-size:12px;">กำลังโหลด...</div>`;

    try {
        const r = await fetch(`${API_URL}/facebook-ads/campaign-detail?campaign=${encodeURIComponent(campaign)}`, { credentials: 'include' });
        const d = await r.json();
        renderCampaignDetailPanel(detailEl, d, safeId);
    } catch(e) {
        detailEl.innerHTML = `<div style="padding:12px;color:#ff3b30;font-size:12px;">โหลดข้อมูลไม่สำเร็จ</div>`;
    }
}

function renderCampaignDetailPanel(el, d, safeId) {
    const fmt = dt => dt ? new Date(dt).toLocaleDateString('th-TH', {day:'2-digit',month:'short',year:'2-digit'}) : '-';
    const peakText = d.peak_hours && d.peak_hours.length
        ? d.peak_hours.map(p => `${p.hour}:00`).join(', ')
        : 'ไม่พอข้อมูล';
    const campaign = el.getAttribute('data-campaign') || '';
    const existingBudget = parseFloat(el.getAttribute('data-budget') || '0');

    el.innerHTML = `
    <div style="background:#f9f9f9;border-radius:10px;padding:14px;border:0.5px solid #e5e5ea;">

        <!-- Meta row -->
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
            <div style="background:#fff;border-radius:7px;padding:6px 10px;border:0.5px solid #e5e5ea;font-size:11px;">
                <span style="color:#6e6e73;">👁 Visits</span>
                <span style="font-weight:700;color:#1d1d1f;margin-left:4px;">${(d.total_visits||0).toLocaleString()}</span>
            </div>
            <div style="background:#fff;border-radius:7px;padding:6px 10px;border:0.5px solid #e5e5ea;font-size:11px;">
                <span style="color:#6e6e73;">📅 ระยะเวลา</span>
                <span style="font-weight:700;color:#1d1d1f;margin-left:4px;">${d.duration_days} วัน</span>
            </div>
            <div style="background:#fff;border-radius:7px;padding:6px 10px;border:0.5px solid #e5e5ea;font-size:11px;">
                <span style="color:#6e6e73;">🗓 เริ่ม</span>
                <span style="font-weight:700;color:#1d1d1f;margin-left:4px;">${fmt(d.date_first)}</span>
            </div>
            <div style="background:#fff;border-radius:7px;padding:6px 10px;border:0.5px solid #e5e5ea;font-size:11px;">
                <span style="color:#6e6e73;">🕗 Peak</span>
                <span style="font-weight:700;color:#ff9500;margin-left:4px;">${peakText}</span>
            </div>
        </div>

        <!-- Budget row -->
        <div style="background:#fff;border-radius:8px;padding:10px 12px;border:0.5px solid #e5e5ea;margin-bottom:12px;">
            <div style="font-size:11px;font-weight:600;color:#6e6e73;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">💰 งบประมาณแคมเปญ</div>
            <div style="display:flex;gap:8px;align-items:center;">
                <input id="budgetInput_${safeId}" type="number" min="0" step="100"
                    value="${existingBudget > 0 ? existingBudget : ''}"
                    placeholder="กรอกงบรวม (บาท)"
                    style="flex:1;border:1px solid #e5e5ea;border-radius:7px;padding:6px 10px;font-size:12px;outline:none;color:#1d1d1f;"
                    onfocus="this.style.borderColor='#007aff'" onblur="this.style.borderColor='#e5e5ea'"/>
                <button onclick="saveCampaignBudget('${campaign}','${safeId}')"
                    style="padding:6px 14px;background:#007aff;color:#fff;border:none;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;">
                    บันทึก
                </button>
            </div>
            <div id="budgetSaveMsg_${safeId}" style="font-size:11px;color:#34c759;margin-top:5px;display:none;">✓ บันทึกแล้ว</div>
            ${existingBudget > 0 && d.total_visits > 0 ? `<div style="margin-top:6px;font-size:11px;color:#ff9500;">CPV = ฿${(existingBudget/d.total_visits).toFixed(2)} / visit</div>` : ''}
        </div>

        <!-- Device breakdown -->
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
            <div style="flex:1;">
                <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px;">
                    <span style="color:#6e6e73;">📱 มือถือ</span>
                    <span style="font-weight:600;color:#1d1d1f;">${d.device.mobile_pct}%</span>
                </div>
                <div style="height:6px;background:#e5e5ea;border-radius:3px;overflow:hidden;">
                    <div style="height:100%;width:${d.device.mobile_pct}%;background:#007aff;border-radius:3px;transition:width 0.5s;"></div>
                </div>
            </div>
            <div style="flex:1;">
                <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px;">
                    <span style="color:#6e6e73;">💻 คอมพิวเตอร์</span>
                    <span style="font-weight:600;color:#1d1d1f;">${100-d.device.mobile_pct}%</span>
                </div>
                <div style="height:6px;background:#e5e5ea;border-radius:3px;overflow:hidden;">
                    <div style="height:100%;width:${100-d.device.mobile_pct}%;background:#34c759;border-radius:3px;transition:width 0.5s;"></div>
                </div>
            </div>
        </div>

        <!-- Trend mini chart -->
        <div style="font-size:11px;color:#6e6e73;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">📈 แนวโน้ม 14 วัน</div>
        <div style="height:70px;"><canvas id="fbMiniChart_${safeId}"></canvas></div>

        <!-- Hour distribution -->
        <div style="font-size:11px;color:#6e6e73;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin:10px 0 6px;">⏰ การกระจายตามชั่วโมง (เที่ยงคืน→23:00)</div>
        <div style="height:44px;"><canvas id="fbHourChart_${safeId}"></canvas></div>

        <!-- AI Analysis button -->
        <button onclick="loadCampaignAiAnalysis('${campaign}','${safeId}')"
            id="campaignAiBtn_${safeId}"
            style="margin-top:12px;width:100%;padding:8px;background:linear-gradient(135deg,#af52de,#5856d6);color:#fff;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;letter-spacing:0.2px;">
            ✨ วิเคราะห์แคมเปญนี้ด้วย AI
        </button>
        <div id="campaignAiResult_${safeId}" style="margin-top:10px;"></div>
    </div>`;

    // Render trend chart
    setTimeout(() => {
        const tCtx = document.getElementById(`fbMiniChart_${safeId}`);
        if (tCtx) {
            if (_fbCampaignCharts[`trend_${safeId}`]) _fbCampaignCharts[`trend_${safeId}`].destroy();
            _fbCampaignCharts[`trend_${safeId}`] = new Chart(tCtx, {
                type: 'line',
                data: {
                    labels: d.trend.labels,
                    datasets: [{
                        data: d.trend.visits,
                        borderColor: '#007aff',
                        backgroundColor: 'rgba(0,122,255,0.07)',
                        fill: true, tension: 0.4, pointRadius: 2,
                        borderWidth: 1.5, pointBackgroundColor: '#007aff'
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { color: '#6e6e73', font: { size: 9 }, maxTicksLimit: 3 }, grid: { color: 'rgba(0,0,0,0.04)' }, border: { display: false } },
                        x: { ticks: { color: '#6e6e73', font: { size: 9 }, maxTicksLimit: 7 }, grid: { display: false }, border: { display: false } }
                    }
                }
            });
        }

        // Hour distribution bar chart
        const hCtx = document.getElementById(`fbHourChart_${safeId}`);
        if (hCtx) {
            if (_fbCampaignCharts[`hour_${safeId}`]) _fbCampaignCharts[`hour_${safeId}`].destroy();
            _fbCampaignCharts[`hour_${safeId}`] = new Chart(hCtx, {
                type: 'bar',
                data: {
                    labels: Array.from({length: 24}, (_, i) => i % 6 === 0 ? `${i}:00` : ''),
                    datasets: [{
                        data: d.hour_dist,
                        backgroundColor: d.hour_dist.map((v, i) => {
                            const max = Math.max(...d.hour_dist);
                            return v === max ? '#ff9500' : 'rgba(0,122,255,0.25)';
                        }),
                        borderRadius: 2, borderSkipped: false
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: {
                        callbacks: { title: (items) => `${items[0].dataIndex}:00 น.`, label: (item) => `${item.raw} visits` }
                    }},
                    scales: {
                        y: { display: false, beginAtZero: true },
                        x: { ticks: { color: '#6e6e73', font: { size: 9 } }, grid: { display: false }, border: { display: false } }
                    }
                }
            });
        }
    }, 50);
}

function renderFbAdsChart(chartData) {
    const ctx = document.getElementById('fbAdsChart');
    if (!ctx) return;
    if (fbAdsChart) { fbAdsChart.destroy(); }

    fbAdsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: 'ผู้เข้าชม',
                    data: chartData.visits,
                    borderColor: '#007aff',
                    backgroundColor: 'rgba(0,122,255,0.08)',
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#007aff',
                    pointRadius: 3,
                    borderWidth: 2
                },
                {
                    label: 'สมัคร',
                    data: chartData.registrations,
                    borderColor: '#34c759',
                    backgroundColor: 'rgba(52,199,89,0.08)',
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#34c759',
                    pointRadius: 3,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#6e6e73', font: { size: 12 }, boxWidth: 12 }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#6e6e73', font: { size: 11 } },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    border: { display: false }
                },
                x: {
                    ticks: { color: '#6e6e73', font: { size: 11 } },
                    grid: { display: false },
                    border: { display: false }
                }
            }
        }
    });
}

function renderFbRecentRegistrations(registrations) {
    const tbody = document.getElementById('fbRecentRegistrations');
    if (!tbody) return;
    if (!registrations || registrations.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#6e6e73;padding:20px 0;font-size:13px;">ยังไม่มีผู้สมัครจาก Facebook Ads</td></tr>';
        return;
    }
    tbody.innerHTML = registrations.map(reg => {
        const date = new Date(reg.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short' });
        const badge = reg.is_approved
            ? '<span style="background:#e8fbe8;color:#1a7f37;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:600;">อนุมัติแล้ว</span>'
            : '<span style="background:#fff8e1;color:#b45309;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:600;">รออนุมัติ</span>';
        return `<tr style="border-bottom:0.5px solid #f2f2f7;">
            <td style="padding:10px 0;color:#1d1d1f;">${reg.full_name || '-'}</td>
            <td style="padding:10px 0;color:#6e6e73;">${reg.username}</td>
            <td style="padding:10px 0;color:#6e6e73;">${date}</td>
            <td style="padding:10px 0;">${badge}</td>
        </tr>`;
    }).join('');
}

function copyLandingUrl() {
    const url = 'https://ekgshops.com/catalog';
    navigator.clipboard.writeText(url).then(() => {
        showAlert('คัดลอก URL สำเร็จ', 'success');
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = url; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
        showAlert('คัดลอก URL สำเร็จ', 'success');
    });
}

async function loadPromptPaySettings() {
    try {
        const response = await fetch(`${API_URL}/promptpay-settings`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('Loaded PromptPay settings:', data);
            
            if (data.account_name) {
                document.getElementById('accountName').value = data.account_name;
            }
            if (data.account_number) {
                document.getElementById('accountNumber').value = data.account_number;
            }
            if (data.qr_image_url) {
                const preview = document.getElementById('qrPreview');
                const placeholder = document.getElementById('qrPlaceholder');
                preview.src = data.qr_image_url;
                preview.style.display = 'block';
                if (placeholder) placeholder.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading PromptPay settings:', error);
    }
}

async function loadChannels() {
    const container = document.getElementById('channelList');
    
    try {
        const response = await fetch(`${API_URL}/sales-channels`);
        salesChannels = await response.json();
        
        if (salesChannels.length === 0) {
            container.innerHTML = '<p style="text-align: center; opacity: 0.6;">ยังไม่มีช่องทางการขาย</p>';
            return;
        }
        
        let html = '';
        salesChannels.forEach(channel => {
            html += `
                <div class="channel-item">
                    <div class="channel-info">
                        <span class="channel-name">${channel.name}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <label class="toggle-switch">
                            <input type="checkbox" ${channel.is_active ? 'checked' : ''} onchange="toggleChannel(${channel.id}, this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                        <button class="btn-icon delete" onclick="deleteChannel(${channel.id})">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/></svg>
                        </button>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading channels:', error);
        container.innerHTML = '<p style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</p>';
    }
}

async function addChannel() {
    const nameInput = document.getElementById('newChannelName');
    const name = nameInput.value.trim();
    
    if (!name) {
        showAlert('กรุณากรอกชื่อช่องทาง', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/sales-channels`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        
        if (response.ok) {
            nameInput.value = '';
            loadChannels();
            showAlert('เพิ่มช่องทางสำเร็จ', 'success');
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error adding channel:', error);
        showAlert('เกิดข้อผิดพลาด', 'error');
    }
}

async function toggleChannel(channelId, isActive) {
    try {
        await fetch(`${API_URL}/sales-channels/${channelId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });
    } catch (error) {
        console.error('Error toggling channel:', error);
    }
}

async function deleteChannel(channelId) {
    if (!confirm('ลบช่องทางนี้?')) return;
    
    try {
        const response = await fetch(`${API_URL}/sales-channels/${channelId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadChannels();
            showAlert('ลบช่องทางสำเร็จ', 'success');
        }
    } catch (error) {
        console.error('Error deleting channel:', error);
    }
}

// PromptPay form submit handler
async function savePromptPaySettings() {
    console.log('savePromptPaySettings called');
    
    const accountName = document.getElementById('accountName').value;
    const accountNumber = document.getElementById('accountNumber').value;
    
    console.log('Saving PromptPay:', { accountName, accountNumber });
    
    try {
        let qrUrl = null;
        
        if (promptPayQrFile) {
            const formData = new FormData();
            formData.append('file', promptPayQrFile);
            formData.append('type', 'promptpay_qr');
            
            const uploadResponse = await fetch(`${API_URL}/upload`, {
                method: 'POST',
                credentials: 'include',
                body: formData
            });
            
            if (uploadResponse.ok) {
                const uploadResult = await uploadResponse.json();
                qrUrl = uploadResult.url;
            }
        }
        
        const settingsData = {
            account_name: accountName,
            account_number: accountNumber
        };
        if (qrUrl) settingsData.qr_image_url = qrUrl;
        
        console.log('Sending data:', settingsData);
        
        const response = await fetch(`${API_URL}/promptpay-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(settingsData)
        });
        
        console.log('Response status:', response.status);
        
        if (response.ok) {
            const result = await response.json();
            console.log('Save success:', result);
            showAlert('บันทึกการตั้งค่า PromptPay สำเร็จ', 'success');
            promptPayQrFile = null;
        } else {
            const errorText = await response.text();
            console.error('Save failed:', response.status, errorText);
            try {
                const error = JSON.parse(errorText);
                showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
            } catch {
                showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
            }
        }
    } catch (error) {
        console.error('Error saving PromptPay settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

// ==================== ORDER NUMBER SETTINGS ====================

async function loadOrderNumberSettings() {
    const prefixInput = document.getElementById('orderPrefix');
    const digitSelect = document.getElementById('orderDigitCount');
    const previewDiv = document.getElementById('orderNumberPreview');
    
    if (!prefixInput || !digitSelect || !previewDiv) return;
    
    try {
        const response = await fetch(`${API_URL}/order-number-settings`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            prefixInput.value = data.prefix || 'ORD';
            digitSelect.value = data.digit_count || 4;
            previewDiv.textContent = data.preview || 'ORD-2512-0001';
        } else {
            console.error('Failed to load order number settings:', response.status);
            updateOrderPreview();
        }
    } catch (error) {
        console.error('Error loading order number settings:', error);
        updateOrderPreview();
    }
}

function updateOrderPreview() {
    const prefix = document.getElementById('orderPrefix').value.toUpperCase().trim() || 'ORD';
    const digitCount = parseInt(document.getElementById('orderDigitCount').value) || 4;
    
    const now = new Date();
    const yymm = String(now.getFullYear()).slice(-2) + String(now.getMonth() + 1).padStart(2, '0');
    const sequence = '1'.padStart(digitCount, '0');
    
    const preview = `${prefix}-${yymm}-${sequence}`;
    document.getElementById('orderNumberPreview').textContent = preview;
}

async function saveOrderNumberSettings() {
    const prefixInput = document.getElementById('orderPrefix');
    const digitSelect = document.getElementById('orderDigitCount');
    const previewDiv = document.getElementById('orderNumberPreview');
    
    if (!prefixInput || !digitSelect) {
        showAlert('ไม่พบฟอร์มตั้งค่า', 'error');
        return;
    }
    
    const prefix = prefixInput.value.toUpperCase().trim();
    const digitCount = parseInt(digitSelect.value);
    
    if (!prefix || prefix.length > 10) {
        showAlert('คำนำหน้าต้องมี 1-10 ตัวอักษร', 'error');
        return;
    }
    
    if (!/^[A-Z0-9]+$/.test(prefix)) {
        showAlert('คำนำหน้าต้องเป็นตัวอักษรภาษาอังกฤษหรือตัวเลขเท่านั้น', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/order-number-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prefix: prefix,
                digit_count: digitCount
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.settings) {
                prefixInput.value = result.settings.prefix || prefix;
                digitSelect.value = result.settings.digit_count || digitCount;
                if (result.settings.preview && previewDiv) {
                    previewDiv.textContent = result.settings.preview;
                }
            }
            showAlert('บันทึกการตั้งค่าเลขที่คำสั่งซื้อสำเร็จ', 'success');
        } else {
            const error = await response.json();
            showAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving order number settings:', error);
        showAlert('เกิดข้อผิดพลาดในการบันทึก กรุณาลองใหม่', 'error');
    }
}

// QR Code upload handler
function handleQrUpload(event) {
    const file = event.target.files[0];
    if (file) {
        promptPayQrFile = file;
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('qrPreview');
            const placeholder = document.getElementById('qrPlaceholder');
            preview.src = e.target.result;
            preview.style.display = 'block';
            placeholder.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
}

// ==================== PHASE 2A: TRAFFIC SOURCES ====================

let _trafficChartInst = null;

async function loadTrafficSources(period, btn) {
    const container = document.getElementById('fbTrafficSources');
    if (!container) return;
    if (btn) {
        btn.closest('div').querySelectorAll('.fb-seg-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }
    container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:13px;padding:12px 0;">กำลังโหลด...</div>';
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/traffic-sources?period=${period}`, { credentials: 'include' });
        if (!res.ok) throw new Error('Load failed');
        const data = await res.json();
        renderTrafficSources(data);
    } catch(e) {
        container.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:12px 0;">โหลดข้อมูลไม่สำเร็จ</div>`;
    }
}

function renderTrafficSources(data) {
    const container = document.getElementById('fbTrafficSources');
    if (!container) return;
    const breakdown = data.breakdown || [];
    const total = data.total || 0;

    if (!breakdown.length) {
        container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:16px 0;border:1px dashed #e5e5ea;border-radius:10px;">ยังไม่มีข้อมูล traffic</div>';
        return;
    }

    let html = '';
    breakdown.forEach(item => {
        html += `
        <div style="margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                <span style="font-size:13px;font-weight:600;color:#1d1d1f;">
                    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${item.color};margin-right:6px;"></span>
                    ${item.label}
                </span>
                <span style="font-size:12px;color:#6e6e73;">${item.visits.toLocaleString()} visits · ${item.pct}%</span>
            </div>
            <div style="height:6px;background:#f2f2f7;border-radius:3px;overflow:hidden;">
                <div style="height:100%;width:${item.pct}%;background:${item.color};border-radius:3px;transition:width 0.6s ease;"></div>
            </div>
        </div>`;
    });
    container.innerHTML = html;

    // Traffic chart (stacked line, 30 days)
    const chartEl = document.getElementById('fbTrafficChart');
    if (!chartEl || !data.chart) return;
    if (_trafficChartInst) { _trafficChartInst.destroy(); _trafficChartInst = null; }
    const rawDaily = data.chart.raw || {};
    const labels = data.chart.labels || [];
    const dates = data.chart.dates || [];
    const topTypes = breakdown.slice(0, 4);
    const datasets = topTypes.map(item => ({
        label: item.label,
        data: dates.map(d => (rawDaily[d] && rawDaily[d][item.type]) || 0),
        borderColor: item.color,
        backgroundColor: item.color + '22',
        borderWidth: 2,
        fill: false,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 4
    }));
    _trafficChartInst = new Chart(chartEl.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 10 } } },
            scales: {
                x: { ticks: { font: { size: 10 }, maxTicksLimit: 8 }, grid: { display: false } },
                y: { ticks: { font: { size: 10 } }, beginAtZero: true, grid: { color: '#f2f2f7' } }
            }
        }
    });
}

// ==================== PHASE 2C: CONVERSION FUNNEL ====================

async function loadFunnelStats(period, btn) {
    const container = document.getElementById('fbFunnelStats');
    if (!container) return;
    if (btn) {
        btn.closest('div').querySelectorAll('.fb-seg-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }
    container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:13px;padding:12px 0;">กำลังโหลด...</div>';
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/funnel?period=${period}`, { credentials: 'include' });
        if (!res.ok) throw new Error('Load failed');
        const data = await res.json();
        renderFunnelStats(data);
    } catch(e) {
        container.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:12px 0;">โหลดข้อมูลไม่สำเร็จ</div>`;
    }
}

function renderFunnelStats(data) {
    const container = document.getElementById('fbFunnelStats');
    if (!container) return;
    const funnel = data.funnel || [];
    if (!funnel.length) {
        container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:16px 0;border:1px dashed #e5e5ea;border-radius:10px;">ยังไม่มีข้อมูล funnel</div>';
        return;
    }
    const colors = ['#5856d6', '#007aff', '#ff9500', '#34c759'];
    let html = '<div style="display:flex;flex-direction:column;gap:6px;">';
    funnel.forEach((step, i) => {
        const w = step.pct || 0;
        html += `
        <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
                <span style="font-size:12px;font-weight:600;color:#1d1d1f;">${step.label}</span>
                <span style="font-size:12px;color:#6e6e73;">${(step.count||0).toLocaleString()} · ${w}%</span>
            </div>
            <div style="height:20px;background:#f2f2f7;border-radius:6px;overflow:hidden;">
                <div style="height:100%;width:${Math.max(w,2)}%;background:${colors[i % colors.length]};border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding-right:6px;transition:width 0.7s ease;">
                    ${w >= 15 ? `<span style="font-size:10px;color:#fff;font-weight:600;">${w}%</span>` : ''}
                </div>
            </div>
        </div>`;
    });
    html += '</div>';

    // By source table
    const bySource = data.by_source || [];
    if (bySource.length) {
        html += `<div style="margin-top:12px;"><div style="font-size:11px;font-weight:600;color:#6e6e73;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Conversion รายแหล่งที่มา</div>`;
        bySource.slice(0, 5).forEach(s => {
            html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:0.5px solid #f2f2f7;">
                <span style="font-size:12px;color:#1d1d1f;">${s.source}</span>
                <span style="font-size:12px;color:#6e6e73;">${s.views} views · ${s.registrations} regs · <strong style="color:#34c759;">${s.conversion}%</strong></span>
            </div>`;
        });
        html += '</div>';
    }
    container.innerHTML = html;
}

// ==================== PHASE 2B: AI FEATURES ====================

async function loadAiAnalysis() {
    const container = document.getElementById('fbAiAnalysis');
    const btn = document.getElementById('aiAnalysisBtn');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:20px 0;"><div class="fb-spinner" style="display:inline-block;width:20px;height:20px;border:2px solid #e5e5ea;border-top-color:#af52de;border-radius:50%;animation:spin 0.8s linear infinite;"></div><br>AI กำลังวิเคราะห์...</div>';
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/ai-analysis`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const score = data.score || 0;
        const scoreColor = score >= 70 ? '#34c759' : score >= 40 ? '#ff9500' : '#ff3b30';
        container.innerHTML = `
            <div style="background:#f9f9f9;border-radius:10px;padding:12px;margin-bottom:10px;border-left:3px solid #af52de;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;font-weight:700;color:#6e6e73;text-transform:uppercase;letter-spacing:0.5px;">ภาพรวม</span>
                    <span style="font-size:20px;font-weight:700;color:${scoreColor};">${score}<span style="font-size:12px;">/100</span></span>
                </div>
                <p style="font-size:12px;color:#1d1d1f;line-height:1.6;">${data.summary || ''}</p>
                ${data.top_insight ? `<div style="margin-top:8px;padding:8px;background:#fff;border-radius:8px;border:1px solid #e5e5ea;font-size:12px;color:#007aff;">💡 ${data.top_insight}</div>` : ''}
            </div>
            <div style="margin-bottom:8px;">
                <div style="font-size:11px;font-weight:700;color:#6e6e73;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">คำแนะนำ</div>
                ${(data.recommendations || []).map((r,i) => `<div style="display:flex;gap:8px;padding:5px 0;border-bottom:0.5px solid #f2f2f7;font-size:12px;color:#1d1d1f;"><span style="color:#af52de;font-weight:600;">${i+1}.</span>${r}</div>`).join('')}
            </div>
            ${data.roi_summary ? `<div style="padding:8px 10px;background:#fff7ed;border-radius:8px;font-size:12px;color:#92400e;margin-top:8px;border:1px solid #fed7aa;">💰 ROI: ${data.roi_summary}</div>` : ''}
            ${data.best_time ? `<div style="padding:8px 10px;background:#f0fdf4;border-radius:8px;font-size:12px;color:#15803d;margin-top:6px;">⏰ ${data.best_time}</div>` : ''}
        `;
    } catch(e) {
        container.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:12px;border:1px dashed #fca5a5;border-radius:10px;">เกิดข้อผิดพลาด: ${e.message}</div>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg> วิเคราะห์'; }
    }
}

async function loadAiTiming() {
    const container = document.getElementById('fbAiTiming');
    const btn = document.getElementById('aiTimingBtn');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:20px 0;"><div class="fb-spinner" style="display:inline-block;width:20px;height:20px;border:2px solid #e5e5ea;border-top-color:#ff9500;border-radius:50%;animation:spin 0.8s linear infinite;"></div><br>AI กำลังวิเคราะห์...</div>';
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/ai-timing`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const fmtHours = arr => (arr || []).map(h => `${h}:00`).join(', ');
        container.innerHTML = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">
                <div style="background:#f0fdf4;border-radius:10px;padding:10px;">
                    <div style="font-size:10px;font-weight:700;color:#15803d;text-transform:uppercase;margin-bottom:4px;">⏰ ชั่วโมงที่ดีที่สุด</div>
                    <div style="font-size:13px;font-weight:600;color:#1d1d1f;">${fmtHours(data.best_hours)}</div>
                </div>
                <div style="background:#fff9f0;border-radius:10px;padding:10px;">
                    <div style="font-size:10px;font-weight:700;color:#b45309;text-transform:uppercase;margin-bottom:4px;">📅 วันที่ดีที่สุด</div>
                    <div style="font-size:13px;font-weight:600;color:#1d1d1f;">${(data.best_days || []).join(', ')}</div>
                </div>
            </div>
            ${data.schedule_suggestion ? `<div style="background:#f9f9f9;border-radius:10px;padding:10px;margin-bottom:8px;font-size:12px;color:#1d1d1f;line-height:1.6;border-left:3px solid #ff9500;">${data.schedule_suggestion}</div>` : ''}
            ${data.budget_tip ? `<div style="background:#f0f4ff;border-radius:10px;padding:10px;font-size:12px;color:#4338ca;line-height:1.6;">💰 ${data.budget_tip}</div>` : ''}
            ${(data.avoid_hours || []).length ? `<div style="margin-top:8px;font-size:11px;color:#ff3b30;">⚠️ หลีกเลี่ยง: ${fmtHours(data.avoid_hours)}</div>` : ''}
        `;
    } catch(e) {
        container.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:12px;border:1px dashed #fca5a5;border-radius:10px;">เกิดข้อผิดพลาด: ${e.message}</div>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg> วิเคราะห์'; }
    }
}

async function generateAiCopy() {
    const container = document.getElementById('fbAiCopy');
    const btn = document.getElementById('aiCopyBtn');
    if (!container) return;
    const product = document.getElementById('aiCopyProduct')?.value?.trim() || 'ชุดพยาบาล EKG';
    const tone = document.getElementById('aiCopyTone')?.value || 'friendly';
    const goal = document.getElementById('aiCopyGoal')?.value || 'สมัครสมาชิก';
    container.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:16px 0;"><div class="fb-spinner" style="display:inline-block;width:16px;height:16px;border:2px solid #e5e5ea;border-top-color:#34c759;border-radius:50%;animation:spin 0.8s linear infinite;"></div> กำลังสร้าง...</div>';
    if (btn) { btn.disabled = true; btn.innerHTML = '⌛ กำลังสร้าง...'; }
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/ai-copy`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product, tone, goal })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        container.innerHTML = `
            <div style="background:#f9f9f9;border-radius:10px;padding:12px;border:1px solid #e5e5ea;">
                <div style="font-size:14px;font-weight:700;color:#1d1d1f;margin-bottom:8px;border-bottom:1px solid #e5e5ea;padding-bottom:8px;">📢 ${data.headline || ''}</div>
                <div style="font-size:12px;color:#1d1d1f;line-height:1.7;margin-bottom:8px;white-space:pre-line;">${data.primary_text || ''}</div>
                <div style="font-size:12px;font-weight:700;color:#007aff;margin-bottom:8px;">👉 ${data.cta || ''}</div>
                <div style="font-size:11px;color:#5856d6;margin-bottom:8px;">${(data.hashtags || []).join(' ')}</div>
                ${data.tip ? `<div style="background:#fffbeb;border-radius:8px;padding:8px;font-size:11px;color:#92400e;border:1px solid #fde68a;">💡 เคล็ดลับ: ${data.tip}</div>` : ''}
                <button onclick="navigator.clipboard.writeText(\`${(data.headline||'')+'\\n'+(data.primary_text||'')+'\\n'+(data.cta||'')}\`.replace(/\`/g,''))" style="margin-top:10px;width:100%;padding:7px;border:1px solid #e5e5ea;border-radius:8px;background:#fff;font-size:12px;cursor:pointer;color:#6e6e73;">📋 คัดลอก Copy</button>
            </div>
        `;
    } catch(e) {
        container.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:10px;border:1px dashed #fca5a5;border-radius:10px;">เกิดข้อผิดพลาด: ${e.message}</div>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg> สร้าง Ad Copy'; }
    }
}


// ==================== CAMPAIGN BUDGET + PER-CAMPAIGN AI ====================

async function saveCampaignBudget(campaignName, safeId) {
    const input = document.getElementById(`budgetInput_${safeId}`);
    const msgEl = document.getElementById(`budgetSaveMsg_${safeId}`);
    if (!input) return;
    const budget = parseFloat(input.value) || 0;
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/campaign-budgets`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ campaign_name: campaignName, total_budget: budget })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (msgEl) {
            msgEl.style.display = 'block';
            setTimeout(() => { msgEl.style.display = 'none'; }, 2500);
        }
        // Update the data-budget attribute so CPV shows correctly on reload
        const detailEl = document.getElementById(`fbDetail_${safeId}`);
        if (detailEl) detailEl.setAttribute('data-budget', budget);
    } catch(e) {
        if (msgEl) { msgEl.style.color = '#ff3b30'; msgEl.textContent = '✗ บันทึกไม่สำเร็จ'; msgEl.style.display = 'block'; }
    }
}

async function loadCampaignAiAnalysis(campaignName, safeId) {
    const resultEl = document.getElementById(`campaignAiResult_${safeId}`);
    const btn = document.getElementById(`campaignAiBtn_${safeId}`);
    if (!resultEl) return;
    resultEl.innerHTML = '<div style="text-align:center;color:#6e6e73;font-size:12px;padding:14px 0;"><div class="fb-spinner" style="display:inline-block;width:18px;height:18px;border:2px solid #e5e5ea;border-top-color:#af52de;border-radius:50%;animation:spin 0.8s linear infinite;"></div><br>AI กำลังวิเคราะห์แคมเปญ...</div>';
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    try {
        const res = await fetch(`${window.API_URL || '/api'}/facebook-ads/ai-campaign-analysis?campaign=${encodeURIComponent(campaignName)}`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d = await res.json();
        if (d.error) throw new Error(d.error);
        const score = d.performance_score || 0;
        const scoreColor = score >= 70 ? '#34c759' : score >= 40 ? '#ff9500' : '#ff3b30';
        resultEl.innerHTML = `
        <div style="background:#fff;border-radius:10px;padding:12px;border:1px solid #e5e5ea;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-size:12px;font-weight:700;color:#5856d6;">✨ AI Analysis</span>
                <span style="font-size:18px;font-weight:700;color:${scoreColor};">${score}<span style="font-size:10px;">/100</span></span>
            </div>
            <div style="font-size:12px;color:#1d1d1f;line-height:1.6;margin-bottom:8px;padding:8px;background:#f9f9f9;border-radius:8px;">${d.verdict || ''}</div>
            ${d.roi_assessment ? `<div style="font-size:11px;color:#92400e;background:#fff7ed;padding:7px 10px;border-radius:8px;margin-bottom:8px;border:1px solid #fed7aa;">💰 ${d.roi_assessment}</div>` : ''}
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                <div>
                    <div style="font-size:10px;font-weight:700;color:#15803d;text-transform:uppercase;margin-bottom:4px;">จุดแข็ง</div>
                    ${(d.strengths||[]).map(s=>`<div style="font-size:11px;color:#1d1d1f;padding:2px 0;border-bottom:0.5px solid #f2f2f7;">✓ ${s}</div>`).join('')}
                </div>
                <div>
                    <div style="font-size:10px;font-weight:700;color:#ff3b30;text-transform:uppercase;margin-bottom:4px;">จุดอ่อน</div>
                    ${(d.weaknesses||[]).map(w=>`<div style="font-size:11px;color:#1d1d1f;padding:2px 0;border-bottom:0.5px solid #f2f2f7;">⚠ ${w}</div>`).join('')}
                </div>
            </div>
            <div style="font-size:10px;font-weight:700;color:#6e6e73;text-transform:uppercase;margin-bottom:4px;">สิ่งที่ควรทำ</div>
            ${(d.actions||[]).map((a,i)=>`<div style="font-size:11px;color:#1d1d1f;padding:3px 0;border-bottom:0.5px solid #f2f2f7;"><span style="color:#007aff;font-weight:600;">${i+1}.</span> ${a}</div>`).join('')}
            ${d.budget_advice ? `<div style="font-size:11px;color:#4338ca;background:#f0f4ff;padding:7px 10px;border-radius:8px;margin-top:8px;">📊 ${d.budget_advice}</div>` : ''}
        </div>`;
    } catch(e) {
        resultEl.innerHTML = `<div style="text-align:center;color:#ff3b30;font-size:12px;padding:10px;border:1px dashed #fca5a5;border-radius:8px;">เกิดข้อผิดพลาด: ${e.message}</div>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '✨ วิเคราะห์แคมเปญนี้ด้วย AI'; }
    }
}
