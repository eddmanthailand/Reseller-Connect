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
    if (urlInput) urlInput.value = 'https://ekgshops.com/join';
    loadFbAdsPixelSettings();
    loadFacebookAdsStats();
    loadMetaApiStatus();
    loadAdLandingUrls();
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

function _metaStat(label, value, color) {
    return `<div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 12px;border:1px solid rgba(255,255,255,0.08);">
        <div style="font-size:10px;opacity:0.55;margin-bottom:3px;">${label}</div>
        <div style="font-size:16px;font-weight:700;color:${color};">${value}</div>
    </div>`;
}

async function loadFbAdsPixelSettings() {
    try {
        const response = await fetch(`${API_URL}/facebook-pixel-settings`, {
            credentials: 'include'
        });
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

async function loadFacebookAdsStats() {
    try {
        const response = await fetch(`${API_URL}/facebook-ads/stats`, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            console.error('Failed to load Facebook Ads stats');
            return;
        }
        
        const data = await response.json();
        
        // Update stats cards
        document.getElementById('fbStatsTodayVisits').textContent = data.today.visits;
        document.getElementById('fbStatsTodayRegs').textContent = data.today.registrations;
        document.getElementById('fbStatsTodayConv').textContent = data.today.conversion + '%';
        
        document.getElementById('fbStatsWeekVisits').textContent = data.week.visits;
        document.getElementById('fbStatsWeekRegs').textContent = data.week.registrations;
        document.getElementById('fbStatsWeekConv').textContent = data.week.conversion + '%';
        
        document.getElementById('fbStatsMonthVisits').textContent = data.month.visits;
        document.getElementById('fbStatsMonthRegs').textContent = data.month.registrations;
        document.getElementById('fbStatsMonthConv').textContent = data.month.conversion + '%';
        
        document.getElementById('fbStatsTotalVisits').textContent = data.total.visits;
        document.getElementById('fbStatsTotalRegs').textContent = data.total.registrations;
        document.getElementById('fbStatsTotalConv').textContent = data.total.conversion + '%';
        
        // Update chart
        renderFbAdsChart(data.chart);
        
        // Update recent registrations table
        renderFbRecentRegistrations(data.recent_registrations);
        
    } catch (error) {
        console.error('Error loading Facebook Ads stats:', error);
    }
}

function renderFbAdsChart(chartData) {
    const ctx = document.getElementById('fbAdsChart');
    if (!ctx) return;
    
    if (fbAdsChart) {
        fbAdsChart.destroy();
    }
    
    fbAdsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: 'ผู้เข้าชม',
                    data: chartData.visits,
                    borderColor: '#1877f2',
                    backgroundColor: 'rgba(24, 119, 242, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'สมัคร',
                    data: chartData.registrations,
                    borderColor: '#42b72a',
                    backgroundColor: 'rgba(66, 183, 42, 0.1)',
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: 'rgba(255,255,255,0.7)' }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: 'rgba(255,255,255,0.5)' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                x: {
                    ticks: { color: 'rgba(255,255,255,0.5)' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                }
            }
        }
    });
}

function renderFbRecentRegistrations(registrations) {
    const tbody = document.getElementById('fbRecentRegistrations');
    if (!tbody) return;
    
    if (!registrations || registrations.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; opacity: 0.5;">ยังไม่มีผู้สมัครจาก Facebook Ads</td></tr>';
        return;
    }
    
    tbody.innerHTML = registrations.map(reg => {
        const date = new Date(reg.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
        const statusBadge = reg.is_approved 
            ? '<span style="background: rgba(34,197,94,0.2); color: #22c55e; padding: 2px 8px; border-radius: 4px; font-size: 11px;">อนุมัติแล้ว</span>'
            : '<span style="background: rgba(251,191,36,0.2); color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-size: 11px;">รออนุมัติ</span>';
        
        return `<tr>
            <td>${reg.full_name || '-'}</td>
            <td>${reg.username}</td>
            <td>${date}</td>
            <td>${statusBadge}</td>
        </tr>`;
    }).join('');
}

function copyLandingUrl() {
    const urlInput = document.getElementById('fbLandingUrl');
    if (urlInput) {
        urlInput.select();
        navigator.clipboard.writeText(urlInput.value).then(() => {
            showAlert('คัดลอก URL สำเร็จ', 'success');
        }).catch(() => {
            document.execCommand('copy');
            showAlert('คัดลอก URL สำเร็จ', 'success');
        });
    }
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

