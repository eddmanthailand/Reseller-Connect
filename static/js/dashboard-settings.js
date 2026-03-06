// ==========================================
// Tier Settings Page Functions
// ==========================================

let tierData = [];

async function loadTierSettings() {
    const container = document.getElementById('tiersContainer');
    
    try {
        const response = await fetch(`${API_URL}/reseller-tiers`);
        tierData = await response.json();
        
        renderTierCards();
    } catch (error) {
        console.error('Error loading tiers:', error);
        container.innerHTML = '<div style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</div>';
    }
}

function renderTierCards() {
    const container = document.getElementById('tiersContainer');
    
    const tierColors = {
        'Bronze': 'bronze',
        'Silver': 'silver',
        'Gold': 'gold',
        'Platinum': 'platinum'
    };
    
    let html = '';
    
    tierData.forEach(tier => {
        const colorClass = tierColors[tier.name] || 'bronze';
        html += `
            <div class="tier-card">
                <div class="tier-header">
                    <span class="tier-badge ${colorClass}">${tier.name}</span>
                    <span class="tier-level">ระดับ ${tier.level_rank || 1}</span>
                </div>
                <div class="tier-form-row">
                    <label>ยอดซื้อขั้นต่ำ</label>
                    <div class="threshold-input-wrapper">
                        <input type="number" class="tier-input threshold-input" 
                               data-tier-id="${tier.id}" 
                               value="${tier.upgrade_threshold || 0}" 
                               min="0">
                        <span class="threshold-suffix">บาท</span>
                    </div>
                </div>
                <div class="tier-form-row">
                    <label>รายละเอียด</label>
                    <input type="text" class="tier-input description-input" 
                           data-tier-id="${tier.id}" 
                           value="${tier.description || ''}" 
                           placeholder="คำอธิบายระดับ (ไม่จำเป็น)">
                </div>
                <p class="info-text">ตัวแทนที่มียอดซื้อสะสมตั้งแต่ ${(tier.upgrade_threshold || 0).toLocaleString()} บาท จะได้รับระดับนี้</p>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

async function saveAllTiers() {
    const thresholdInputs = document.querySelectorAll('.threshold-input');
    const descriptionInputs = document.querySelectorAll('.description-input');
    
    const updates = [];
    thresholdInputs.forEach(input => {
        const tierId = input.dataset.tierId;
        const threshold = parseInt(input.value) || 0;
        const descInput = document.querySelector(`.description-input[data-tier-id="${tierId}"]`);
        const description = descInput ? descInput.value : '';
        
        updates.push({
            id: parseInt(tierId),
            upgrade_threshold: threshold,
            description: description
        });
    });
    
    try {
        const response = await fetch(`${API_URL}/reseller-tiers/bulk`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tiers: updates })
        });
        
        if (response.ok) {
            showTierAlert('บันทึกการตั้งค่าสำเร็จ', 'success');
            loadTierSettings();
        } else {
            const error = await response.json();
            showTierAlert(error.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error saving tiers:', error);
        showTierAlert('เกิดข้อผิดพลาดในการบันทึก', 'error');
    }
}

async function loadResellers() {
    const tableBody = document.getElementById('resellersTableBody');
    
    try {
        const response = await fetch(`${API_URL}/resellers`);
        const resellers = await response.json();
        
        if (resellers.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; opacity: 0.6;">ไม่มีข้อมูลตัวแทน</td></tr>';
            return;
        }
        
        const tierColors = {
            'Bronze': 'bronze',
            'Silver': 'silver',
            'Gold': 'gold',
            'Platinum': 'platinum'
        };
        
        let html = '';
        resellers.forEach(r => {
            const colorClass = tierColors[r.tier_name] || 'bronze';
            const manualBadge = r.tier_manual_override ? '<span class="manual-badge">Manual</span>' : '';
            
            html += `
                <tr>
                    <td>${r.username}</td>
                    <td>${r.full_name}</td>
                    <td><span class="tier-badge ${colorClass}">${r.tier_name}</span></td>
                    <td>${(r.total_purchases || 0).toLocaleString()} บาท</td>
                    <td>${manualBadge || '<span style="opacity: 0.5;">Auto</span>'}</td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    } catch (error) {
        console.error('Error loading resellers:', error);
        tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; opacity: 0.6;">ไม่สามารถโหลดข้อมูลได้</td></tr>';
    }
}

async function checkAllUpgrades() {
    const resultDiv = document.getElementById('upgradeResult');
    resultDiv.innerHTML = '<p style="opacity: 0.6;">กำลังตรวจสอบ...</p>';
    
    try {
        const response = await fetch(`${API_URL}/users/check-tier-upgrades`, { method: 'POST' });
        const result = await response.json();
        
        if (result.upgraded && result.upgraded.length > 0) {
            let html = '<div class="upgrade-result"><h4>อัปเกรดสำเร็จ:</h4><ul>';
            result.upgraded.forEach(u => {
                html += `<li>${u.full_name}: ${u.old_tier} → ${u.new_tier}</li>`;
            });
            html += '</ul></div>';
            resultDiv.innerHTML = html;
            loadResellers();
        } else {
            resultDiv.innerHTML = '<p style="color: rgba(255,255,255,0.6); padding: 16px;">ไม่มีตัวแทนที่ต้องอัปเกรด</p>';
        }
        
        setTimeout(() => { resultDiv.innerHTML = ''; }, 5000);
    } catch (error) {
        console.error('Error checking upgrades:', error);
        resultDiv.innerHTML = '<p style="color: #ef4444;">เกิดข้อผิดพลาด</p>';
    }
}

function showTierAlert(message, type) {
    const alertBox = document.getElementById('tierAlertBox');
    if (!alertBox) return;
    
    alertBox.textContent = message;
    alertBox.className = `alert alert-${type}`;
    alertBox.style.display = 'block';
    
    setTimeout(() => { alertBox.style.display = 'none'; }, 3000);
}

// ==========================================
// Settings Page Functions
// ==========================================

let promptPayQrFile = null;
let salesChannels = [];

async function loadSettings() {
    loadPromptPaySettings();
    loadOrderNumberSettings();
    loadFacebookPixelSettings();
    loadChannels();
}

