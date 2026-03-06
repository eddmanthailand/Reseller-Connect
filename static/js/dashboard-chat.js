// ==================== CHAT SYSTEM ====================

let currentChatThreadId = null;
let showingArchivedThreads = false;
let oldestMessageId = 0;
let chatHasMore = false;
let loadingOlderMessages = false;
let chatPollingInterval = null;
let lastMessageId = 0;
let chatQuickReplies = [];
let pendingChatAttachments = [];
let selectedChatProduct = null;
let chatProductSearchTimeout = null;
let currentChatResellerTierId = null;

async function loadChatThreadsAndAutoSelect() {
    const threads = await loadChatThreads();
    if (threads && threads.length > 0 && !currentChatThreadId) {
        const firstThread = threads.find(t => t.unread_count > 0) || threads[0];
        selectChatThread(firstThread.id, firstThread.reseller_name, firstThread.tier_name || '', firstThread.reseller_tier_id || null, firstThread.bot_paused || false);
    }
}

async function loadChatThreads() {
    try {
        let url = '/api/chat/threads';
        if (showingArchivedThreads) url += '?archived=true';
        const response = await fetch(url, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            console.error('Chat threads API error:', response.status);
            const container = document.getElementById('chatThreadsList');
            if (container) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.5);">
                        <p>ไม่สามารถโหลดข้อมูลได้</p>
                    </div>
                `;
            }
            return [];
        }
        
        const threads = await response.json();
        
        const container = document.getElementById('chatThreadsList');
        if (!container) return [];
        
        if (!Array.isArray(threads) || threads.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.5);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 12px; opacity: 0.3;">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <p>${showingArchivedThreads ? 'ไม่มีการสนทนาที่ซ่อน' : 'ยังไม่มีการสนทนา'}</p>
                </div>
            `;
            return [];
        }
        
        const isAdmin = document.getElementById('btnToggleArchived') !== null;
        container.innerHTML = threads.map(thread => `
            <div class="chat-thread-item ${currentChatThreadId === thread.id ? 'active' : ''}" 
                 onclick="selectChatThread(${thread.id}, '${escapeHtml(thread.reseller_name)}', '${escapeHtml(thread.tier_name || '')}', ${thread.reseller_tier_id || 'null'}, ${thread.bot_paused ? 'true' : 'false'})"
                 style="display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 8px; cursor: pointer; background: ${thread.needs_admin ? 'rgba(251,191,36,0.08)' : currentChatThreadId === thread.id ? 'rgba(102,126,234,0.2)' : 'transparent'}; transition: background 0.2s; border-left: ${thread.needs_admin ? '3px solid #fbbf24' : '3px solid transparent'};">
                <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; flex-shrink: 0; position:relative;">
                    ${thread.reseller_name.charAt(0).toUpperCase()}
                    ${thread.needs_admin ? '<span style="position:absolute;top:-4px;right:-4px;background:#fbbf24;border-radius:50%;width:16px;height:16px;font-size:10px;display:flex;align-items:center;justify-content:center;">🙋</span>' : ''}
                    <span data-bot-indicator title="${thread.bot_paused ? 'บอทหยุดอยู่' : 'บอทกำลังทำงาน'}" style="position:absolute;bottom:-3px;left:-3px;background:${thread.bot_paused ? '#6b7280' : '#10b981'};border-radius:50%;width:14px;height:14px;border:2px solid #1a1a2e;font-size:8px;display:flex;align-items:center;justify-content:center;line-height:1;">${thread.bot_paused ? '⏸' : '🤖'}</span>
                </div>
                <div style="flex: 1; min-width: 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600; font-size: 14px;">${escapeHtml(thread.reseller_name)}${thread.needs_admin ? ' <span style="background:#fbbf24;color:#000;font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700;margin-left:4px;">รอ Admin</span>' : ''}</span>
                        ${thread.unread_count > 0 ? `<span style="background: #ef4444; color: white; font-size: 11px; padding: 2px 6px; border-radius: 10px; min-width: 18px; text-align: center;">${thread.unread_count}</span>` : ''}
                    </div>
                    <div style="font-size: 12px; opacity: 0.6; margin-top: 2px;">${thread.tier_name || 'ไม่ระบุ Tier'}</div>
                    <div style="font-size: 12px; opacity: 0.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 4px;">${escapeHtml(thread.last_message_preview || 'ยังไม่มีข้อความ')}</div>
                </div>
                ${isAdmin ? `<button onclick="${showingArchivedThreads ? `unarchiveChatThread(${thread.id}, event)` : `archiveChatThread(${thread.id}, event)`}" style="flex-shrink: 0; width: 28px; height: 28px; border: none; background: rgba(255,255,255,0.08); border-radius: 6px; color: rgba(255,255,255,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.15)';this.style.color='rgba(255,255,255,0.8)'" onmouseout="this.style.background='rgba(255,255,255,0.08)';this.style.color='rgba(255,255,255,0.4)'" title="${showingArchivedThreads ? 'แสดง' : 'ซ่อน'}">
                    ${showingArchivedThreads
                        ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
                        : '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'}
                </button>` : ''}
            </div>
        `).join('');
        
        return threads;
        
    } catch (error) {
        console.error('Error loading chat threads:', error);
        return [];
    }
}

async function toggleArchivedThreads() {
    showingArchivedThreads = !showingArchivedThreads;
    const btn = document.getElementById('btnToggleArchived');
    if (btn) btn.textContent = showingArchivedThreads ? '💬 แชททั้งหมด' : '📁 ซ่อนแล้ว';
    loadChatThreads();
}

async function archiveChatThread(threadId, event) {
    event.stopPropagation();
    if (!confirm('ซ่อนการสนทนานี้? (จะกลับมาเมื่อมีข้อความใหม่)')) return;
    try {
        const resp = await fetch(`/api/chat/threads/${threadId}/archive`, {
            method: 'POST', credentials: 'include'
        });
        if (resp.ok) {
            showAlert('ซ่อนการสนทนาแล้ว', 'success');
            loadChatThreads();
        }
    } catch(e) { console.error(e); }
}

async function unarchiveChatThread(threadId, event) {
    event.stopPropagation();
    try {
        const resp = await fetch(`/api/chat/threads/${threadId}/unarchive`, {
            method: 'POST', credentials: 'include'
        });
        if (resp.ok) {
            showAlert('แสดงการสนทนาอีกครั้ง', 'success');
            loadChatThreads();
        }
    } catch(e) { console.error(e); }
}


async function selectChatThread(threadId, resellerName, tierName, resellerTierId, botPaused) {
    currentChatThreadId = threadId;
    lastMessageId = 0;
    oldestMessageId = 0;
    chatHasMore = false;
    currentChatResellerTierId = resellerTierId || null;
    selectedChatProduct = null;
    const productPreview = document.getElementById('chatProductPreview');
    if (productPreview) productPreview.style.display = 'none';
    
    document.getElementById('chatHeader').style.display = 'block';
    document.getElementById('chatInputArea').style.display = 'block';
    document.getElementById('chatAvatarInitial').textContent = resellerName.charAt(0).toUpperCase();
    document.getElementById('chatResellerName').textContent = resellerName;
    document.getElementById('chatResellerTier').textContent = tierName || 'ไม่ระบุ Tier';
    
    updateChatBotToggleBtn(!botPaused);
    
    const chatGrid = document.querySelector('.admin-chat-grid');
    if (chatGrid) chatGrid.classList.add('chat-thread-open');
    
    await loadChatMessages(threadId);
    loadChatThreads();
    loadQuickReplyButtons();
    startChatPolling();
}

function updateChatBotToggleBtn(isActive) {
    const btn = document.getElementById('btnChatBotToggle');
    if (!btn) return;
    if (isActive) {
        btn.style.background = 'rgba(72,199,142,0.2)';
        btn.style.color = '#48c78e';
        btn.style.borderColor = '#48c78e';
        btn.innerHTML = '🤖 <span id="chatBotToggleLabel">บอทเปิดอยู่</span>';
    } else {
        btn.style.background = 'rgba(239,68,68,0.15)';
        btn.style.color = '#f87171';
        btn.style.borderColor = '#f87171';
        btn.innerHTML = '⏸️ <span id="chatBotToggleLabel">บอทปิดอยู่</span>';
    }
    // Update bot indicator on the thread row in the list
    if (currentChatThreadId) {
        const threadItems = document.querySelectorAll('#chatThreadsList .chat-thread-item');
        threadItems.forEach(item => {
            const onclick = item.getAttribute('onclick') || '';
            if (onclick.includes(`selectChatThread(${currentChatThreadId},`)) {
                const indicator = item.querySelector('[data-bot-indicator]');
                if (indicator) {
                    indicator.textContent = isActive ? '🤖' : '⏸';
                    indicator.style.background = isActive ? '#10b981' : '#6b7280';
                    indicator.title = isActive ? 'บอทกำลังทำงาน' : 'บอทหยุดอยู่';
                }
            }
        });
    }
}

async function toggleChatBot() {
    if (!currentChatThreadId) return;
    const btn = document.getElementById('btnChatBotToggle');
    if (btn) btn.disabled = true;
    try {
        const res = await fetch(`/api/chat/threads/${currentChatThreadId}/toggle-bot`, {
            method: 'POST', credentials: 'include'
        });
        if (res.ok) {
            const data = await res.json();
            updateChatBotToggleBtn(data.bot_active);
            showGlobalAlert('success', data.bot_active ? '🤖 บอทเปิดทำงานแล้ว' : '⏸️ บอทหยุดทำงานแล้ว');
        }
    } catch (e) {
        showGlobalAlert('error', 'เกิดข้อผิดพลาด');
    } finally {
        if (btn) btn.disabled = false;
    }
}

function _updateGlobalBotBtn(enabled) {
    const btn = document.getElementById('btnGlobalBotToggle');
    const dot = document.getElementById('globalBotStatusDot');
    const lbl = document.getElementById('globalBotStatusLabel');
    if (!btn) return;
    if (enabled) {
        btn.style.background = 'rgba(72,199,142,0.15)';
        btn.style.color = '#48c78e';
        btn.style.borderColor = 'rgba(72,199,142,0.5)';
        if (dot) { dot.style.background = '#48c78e'; }
        if (lbl) lbl.textContent = 'เปิดอยู่';
    } else {
        btn.style.background = 'rgba(255,255,255,0.07)';
        btn.style.color = 'rgba(255,255,255,0.5)';
        btn.style.borderColor = 'rgba(255,255,255,0.2)';
        if (dot) { dot.style.background = '#6b7280'; }
        if (lbl) lbl.textContent = 'ปิดอยู่';
    }
}

async function loadGlobalBotStatus() {
    try {
        const res = await fetch('/api/admin/bot-settings', { credentials: 'include' });
        if (res.ok) {
            const data = await res.json();
            _updateGlobalBotBtn(data.bot_chat_enabled !== false);
        }
    } catch (e) {}
}

async function toggleGlobalBot() {
    const btn = document.getElementById('btnGlobalBotToggle');
    if (btn) btn.disabled = true;
    try {
        const statusRes = await fetch('/api/admin/bot-settings', { credentials: 'include' });
        if (!statusRes.ok) return;
        const current = await statusRes.json();
        const newEnabled = !(current.bot_chat_enabled !== false);
        const res = await fetch('/api/admin/bot-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ bot_chat_enabled: newEnabled })
        });
        if (res.ok) {
            _updateGlobalBotBtn(newEnabled);
            showGlobalAlert('success', newEnabled ? '🤖 เปิดบอทแชทแล้ว' : '⏸️ ปิดบอทแชทแล้ว');
        }
    } catch (e) {
        showGlobalAlert('error', 'เกิดข้อผิดพลาด');
    } finally {
        if (btn) btn.disabled = false;
    }
}

function adminChatGoBack() {
    const chatGrid = document.querySelector('.admin-chat-grid');
    if (chatGrid) chatGrid.classList.remove('chat-thread-open');
}

function formatChatDateSeparator(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (date.toDateString() === today.toDateString()) return 'วันนี้';
    if (date.toDateString() === yesterday.toDateString()) return 'เมื่อวาน';
    
    const months = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear() + 543}`;
}

function renderChatContent(text) {
    if (!text) return '';
    let html = escapeHtml(text).replace(/\n/g, '<br>');
    const imgTag = (url) =>
        `<a href="${url}" target="_blank" style="display:block;margin:4px 0;">` +
        `<img src="${url}" style="max-width:100%;max-height:220px;border-radius:10px;object-fit:contain;cursor:zoom-in;border:1px solid rgba(255,255,255,0.15);" ` +
        `onerror="this.style.display='none'"></a>`;
    html = html.replace(/(\/storage\/[^<>\s"']+\.(?:jpg|jpeg|png|gif|webp))/gi, (m) => imgTag(m));
    html = html.replace(/(https?:\/\/[^<>\s"']+\.(?:jpg|jpeg|png|gif|webp))/gi, (m) => imgTag(m));
    return html;
}

function renderChatMessageHtml(msg, otherLastRead) {
    const isMine = Number(msg.sender_id) === Number(currentUserId);
    const isRead = isMine && msg.id <= otherLastRead;
    
    let productCardHtml = '';
    if (msg.product) {
        const p = msg.product;
        const hasDiscount = p.discount_percent && p.discount_percent > 0;
        const tierPrice = hasDiscount ? (p.tier_min_price === p.tier_max_price ? `฿${formatNumber(p.tier_min_price)}` : `฿${formatNumber(p.tier_min_price)} - ฿${formatNumber(p.tier_max_price)}`) : '';
        const originalPrice = p.min_price === p.max_price ? `฿${formatNumber(p.min_price)}` : `฿${formatNumber(p.min_price)} - ฿${formatNumber(p.max_price)}`;
        productCardHtml = `
            <div style="background: rgba(255,255,255,0.08); border-radius: 10px; overflow: hidden; margin-bottom: ${msg.content ? '8px' : '0'}; border: 1px solid rgba(255,255,255,0.1); cursor: pointer;" onclick="navigateToProduct(${p.id})"
                ${p.image_url ? `<img src="${p.image_url}" style="width: 100%; height: 140px; object-fit: cover;">` : '<div style="width: 100%; height: 80px; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.3);">ไม่มีรูป</div>'}
                <div style="padding: 10px;">
                    <div style="font-size: 13px; font-weight: 600; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.name)}</div>
                    ${hasDiscount ? `
                        <div style="font-size: 14px; font-weight: 700; color: #ffffff;">${tierPrice}</div>
                        <div style="font-size: 11px; text-decoration: line-through; opacity: 0.5;">${originalPrice}</div>
                        <div style="font-size: 10px; color: #34d399; margin-top: 2px;">ส่วนลด ${p.discount_percent}%</div>
                    ` : `
                        <div style="font-size: 14px; font-weight: 700; color: #ffffff;">${originalPrice}</div>
                    `}
                </div>
            </div>
        `;
    }
    
    const isBot = !!msg.is_bot;
    const botBadge = isBot ? '<span style="display:inline-block;background:rgba(139,92,246,0.4);border-radius:4px;padding:1px 5px;font-size:9px;margin-bottom:4px;letter-spacing:0.5px;">🤖 Bot</span><br>' : '';

    return `
        <div style="display: flex; ${isMine ? 'justify-content: flex-end' : 'justify-content: flex-start'}; flex-direction:column; align-items:${isMine ? 'flex-end' : 'flex-start'};">
            ${isBot && !isMine ? `<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-bottom:2px;padding-left:2px;"><span style="background:rgba(139,92,246,0.35);border-radius:4px;padding:1px 6px;font-size:9px;">🤖 Bot</span></div>` : ''}
            <div style="max-width: 70%; padding: 12px 16px; border-radius: 16px; ${isBot && !isMine ? 'background:#2d2235; border:1px solid rgba(139,92,246,0.3);' : isMine ? 'background: linear-gradient(135deg, #667eea, #764ba2);' : 'background: #3a3a3c;'} color: #fff; ${isMine ? 'border-bottom-right-radius: 4px;' : 'border-bottom-left-radius: 4px;'}">
                ${msg.is_broadcast ? '<div style="font-size: 10px; opacity: 0.6; margin-bottom: 4px;">📢 Broadcast</div>' : ''}
                ${productCardHtml}
                ${msg.content ? `<div style="font-size: 14px; line-height: 1.6;">${renderChatContent(msg.content)}</div>` : ''}
                ${msg.attachments && msg.attachments.length > 0 ? msg.attachments.map(att => 
                    att.file_type && att.file_type.startsWith('image/') 
                        ? `<img src="${att.file_url}" style="max-width: 200px; border-radius: 8px; margin-top: 8px; cursor: pointer;" onclick="window.open('${att.file_url}', '_blank')">`
                        : `<a href="${att.file_url}" target="_blank" style="display: block; margin-top: 8px; color: #60a5fa;">📎 ${escapeHtml(att.file_name)}</a>`
                ).join('') : ''}
                <div style="font-size: 10px; opacity: 0.5; margin-top: 6px; text-align: right;">${formatChatTime(msg.created_at)}${isRead ? ' <span style="color: #60a5fa; opacity: 1;">อ่านแล้ว</span>' : ''}</div>
            </div>
        </div>
    `;
}

function renderDateSeparator(dateLabel) {
    return `<div style="display: flex; align-items: center; gap: 12px; margin: 16px 0;">
        <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
        <div style="font-size: 12px; color: rgba(255,255,255,0.4); white-space: nowrap;">${dateLabel}</div>
        <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.15);"></div>
    </div>`;
}

function renderMessagesWithDateSeparators(messages, otherLastRead, existingLastDate) {
    let html = '';
    let lastDate = existingLastDate || '';
    messages.forEach(msg => {
        const msgDate = new Date(msg.created_at).toDateString();
        if (msgDate !== lastDate) {
            lastDate = msgDate;
            html += renderDateSeparator(formatChatDateSeparator(msg.created_at));
        }
        html += renderChatMessageHtml(msg, otherLastRead);
    });
    return html;
}

async function loadChatMessages(threadId) {
    try {
        let url;
        if (lastMessageId > 0) {
            url = `/api/chat/threads/${threadId}/messages?since_id=${lastMessageId}`;
        } else {
            url = `/api/chat/threads/${threadId}/messages`;
        }
        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();
        const messages = data.messages || data;
        const otherLastRead = data.other_last_read || 0;
        chatHasMore = data.has_more || false;
        
        const container = document.getElementById('chatMessagesContainer');
        if (!container) return;
        
        if (lastMessageId === 0) {
            container.innerHTML = '';
            const html = renderMessagesWithDateSeparators(messages, otherLastRead, '');
            container.insertAdjacentHTML('beforeend', html);
            if (messages.length > 0) {
                oldestMessageId = messages[0].id;
            }
            setupChatScrollListener(container, threadId);
        } else {
            messages.forEach(msg => {
                const msgDate = new Date(msg.created_at).toDateString();
                const lastChild = container.lastElementChild;
                const lastMsgDateAttr = lastChild ? lastChild.dataset?.msgDate : '';
                if (msgDate !== lastMsgDateAttr) {
                    container.insertAdjacentHTML('beforeend', renderDateSeparator(formatChatDateSeparator(msg.created_at)));
                }
                const msgEl = document.createElement('div');
                msgEl.dataset.msgDate = msgDate;
                msgEl.innerHTML = renderChatMessageHtml(msg, otherLastRead);
                container.appendChild(msgEl);
            });
        }
        
        messages.forEach(msg => {
            lastMessageId = Math.max(lastMessageId, msg.id);
        });
        
        container.scrollTop = container.scrollHeight;
        
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

async function loadOlderChatMessages(threadId) {
    if (loadingOlderMessages || !chatHasMore || oldestMessageId <= 0) return;
    loadingOlderMessages = true;
    
    const container = document.getElementById('chatMessagesContainer');
    if (!container) { loadingOlderMessages = false; return; }
    
    const loader = document.createElement('div');
    loader.id = 'chatLoadingOlder';
    loader.style.cssText = 'text-align: center; padding: 12px; color: rgba(255,255,255,0.4); font-size: 12px;';
    loader.textContent = 'กำลังโหลด...';
    container.prepend(loader);
    
    const prevScrollHeight = container.scrollHeight;
    
    try {
        const response = await fetch(`/api/chat/threads/${threadId}/messages?before_id=${oldestMessageId}`, { credentials: 'include' });
        const data = await response.json();
        const messages = data.messages || data;
        chatHasMore = data.has_more || false;
        
        const loaderEl = document.getElementById('chatLoadingOlder');
        if (loaderEl) loaderEl.remove();
        
        if (messages.length > 0) {
            const html = renderMessagesWithDateSeparators(messages, data.other_last_read || 0, '');
            container.insertAdjacentHTML('afterbegin', html);
            oldestMessageId = messages[0].id;
            container.scrollTop = container.scrollHeight - prevScrollHeight;
        }
    } catch (error) {
        console.error('Error loading older messages:', error);
        const loaderEl = document.getElementById('chatLoadingOlder');
        if (loaderEl) loaderEl.remove();
    }
    
    loadingOlderMessages = false;
}

function setupChatScrollListener(container, threadId) {
    container.onscroll = function() {
        if (container.scrollTop < 50 && chatHasMore && !loadingOlderMessages) {
            loadOlderChatMessages(threadId);
        }
    };
}

function formatChatTime(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
        return date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
        return 'เมื่อวาน ' + date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    } else {
        return date.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) + ' ' + date.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    }
}

async function sendChatMessage() {
    if (!currentChatThreadId) return;
    
    const input = document.getElementById('chatMessageInput');
    const content = input.value.trim();
    
    if (!content && pendingChatAttachments.length === 0 && !selectedChatProduct) return;
    
    try {
        const body = {
            content: content,
            attachments: pendingChatAttachments
        };
        if (selectedChatProduct) {
            body.product_id = selectedChatProduct.id;
        }
        
        const response = await fetch(`/api/chat/threads/${currentChatThreadId}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify(body)
        });
        
        if (response.ok) {
            input.value = '';
            input.style.height = 'auto';
            pendingChatAttachments = [];
            selectedChatProduct = null;
            document.getElementById('chatAttachmentPreview').style.display = 'none';
            document.getElementById('chatAttachmentPreview').innerHTML = '';
            document.getElementById('chatProductPreview').style.display = 'none';
            await loadChatMessages(currentChatThreadId);
            loadChatThreads();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถส่งข้อความได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function handleChatFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/chat/upload', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken },
            credentials: 'include',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            pendingChatAttachments.push(result);
            updateChatAttachmentPreview();
        } else {
            showAlert('error', result.error || 'อัปโหลดไม่สำเร็จ');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
    
    event.target.value = '';
}

function updateChatAttachmentPreview() {
    const container = document.getElementById('chatAttachmentPreview');
    if (pendingChatAttachments.length === 0) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    
    container.style.display = 'flex';
    container.style.gap = '8px';
    container.style.flexWrap = 'wrap';
    
    container.innerHTML = pendingChatAttachments.map((att, i) => `
        <div style="position: relative; padding: 8px 12px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 12px;">
            ${att.file_type && att.file_type.startsWith('image/') ? '🖼️' : '📎'} ${escapeHtml(att.file_name)}
            <button onclick="removeChatAttachment(${i})" style="position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; background: #ef4444; border: none; color: white; cursor: pointer; font-size: 12px; line-height: 1;">×</button>
        </div>
    `).join('');
}

function removeChatAttachment(index) {
    pendingChatAttachments.splice(index, 1);
    updateChatAttachmentPreview();
}

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('th-TH', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

let chatProductSelections = [];

function openChatProductSearch() {
    document.getElementById('chatProductModal').style.display = 'flex';
    document.getElementById('chatProductSearchInput').value = '';
    document.getElementById('chatProductSearchStatus').style.display = 'none';
    document.getElementById('chatProductSearchResults').innerHTML = `
        <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
            <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
        </div>`;
    chatProductSelections = [];
    updateChatProductSelectedBar();
    setTimeout(() => document.getElementById('chatProductSearchInput').focus(), 100);
}

function closeChatProductModal() {
    document.getElementById('chatProductModal').style.display = 'none';
}

function searchChatProducts() {
    clearTimeout(chatProductSearchTimeout);
    const q = document.getElementById('chatProductSearchInput').value.trim();
    const statusEl = document.getElementById('chatProductSearchStatus');
    if (q.length < 1) {
        statusEl.style.display = 'none';
        document.getElementById('chatProductSearchResults').innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
                <p style="margin: 0; font-size: 14px;">พิมพ์เพื่อค้นหาสินค้า</p>
            </div>`;
        return;
    }
    statusEl.style.display = 'block';
    statusEl.innerHTML = '<span style="display: inline-flex; align-items: center; gap: 6px;"><span class="chat-product-spinner"></span> กำลังค้นหา...</span>';
    chatProductSearchTimeout = setTimeout(async () => {
        try {
            let url = `/api/chat/products/search?q=${encodeURIComponent(q)}`;
            if (currentChatResellerTierId) {
                url += `&tier_id=${currentChatResellerTierId}`;
            }
            const response = await fetch(url, { credentials: 'include' });
            const products = await response.json();
            const container = document.getElementById('chatProductSearchResults');
            
            if (!Array.isArray(products) || products.length === 0) {
                statusEl.textContent = 'ไม่พบสินค้า';
                container.innerHTML = `
                    <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.3);">
                        <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 10px; opacity: 0.4;"><path d="M9.172 16.172a4 4 0 015.656 0"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><circle cx="12" cy="12" r="10"/></svg>
                        <p style="margin: 0; font-size: 14px;">ไม่พบสินค้าที่ตรงกัน</p>
                    </div>`;
                return;
            }
            
            statusEl.textContent = `พบ ${products.length} รายการ`;
            container.innerHTML = products.map(p => {
                const isSelected = chatProductSelections.some(s => s.id === p.id);
                const hasDiscount = p.discount_percent && p.discount_percent > 0;
                const priceDisplay = hasDiscount
                    ? `<span style="color: #ffffff; font-weight: 600;">฿${formatNumber(p.tier_min_price)}</span> <span style="text-decoration: line-through; opacity: 0.4; font-size: 11px;">฿${formatNumber(p.min_price)}</span>`
                    : `<span style="color: #ffffff; font-weight: 600;">฿${formatNumber(p.min_price)}</span>`;
                const stockColor = (p.total_stock || 0) > 0 ? '#34d399' : '#f87171';
                const stockText = (p.total_stock || 0) > 0 ? `${p.total_stock} ชิ้น` : 'หมด';
                return `
                    <div onclick="toggleChatProductSelect(${p.id}, '${escapeHtml(p.name).replace(/'/g, "\\'")}', '${p.image_url || ''}', ${p.min_price || 0}, ${hasDiscount ? p.tier_min_price : p.min_price || 0}, ${p.discount_percent || 0})"
                         id="chatProdItem_${p.id}"
                         style="display: flex; gap: 12px; align-items: center; padding: 10px 12px; border-radius: 10px; cursor: pointer; transition: all 0.2s; margin-bottom: 4px; border: 1.5px solid ${isSelected ? 'rgba(102,126,234,0.5)' : 'transparent'}; background: ${isSelected ? 'rgba(102,126,234,0.1)' : 'transparent'};"
                         onmouseover="if(!this.classList.contains('selected'))this.style.background='rgba(255,255,255,0.05)'" onmouseout="if(!this.classList.contains('selected'))this.style.background='transparent'">
                        <div style="position: relative; flex-shrink: 0;">
                            ${p.image_url ? `<img src="${p.image_url}" style="width: 52px; height: 52px; object-fit: cover; border-radius: 8px;">` : '<div style="width: 52px; height: 52px; background: rgba(255,255,255,0.05); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.15); font-size: 22px;">📦</div>'}
                            <div data-check="1" style="position: absolute; top: -4px; right: -4px; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; transition: all 0.2s; ${isSelected ? 'background: linear-gradient(135deg, #667eea, #764ba2); color: white; box-shadow: 0 0 0 2px rgba(102,126,234,0.3);' : 'background: rgba(255,255,255,0.1); color: transparent;'}">${isSelected ? '✓' : ''}</div>
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: white;">${escapeHtml(p.name)}</div>
                            <div style="display: flex; align-items: center; gap: 8px; margin-top: 3px;">
                                <span style="font-size: 11px; opacity: 0.45;">${p.brand_name || ''}</span>
                                ${p.sku_count ? `<span style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.5);">${p.sku_count} SKU</span>` : ''}
                                <span style="font-size: 10px; color: ${stockColor};">● ${stockText}</span>
                            </div>
                            <div style="font-size: 13px; margin-top: 4px;">${priceDisplay}${hasDiscount ? ` <span style="color: #34d399; font-size: 11px; font-weight: 500;">-${p.discount_percent}%</span>` : ''}</div>
                        </div>
                    </div>`;
            }).join('');
        } catch (error) {
            console.error('Error searching products:', error);
            statusEl.textContent = 'เกิดข้อผิดพลาด';
        }
    }, 300);
}

function toggleChatProductSelect(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    const idx = chatProductSelections.findIndex(s => s.id === id);
    if (idx >= 0) {
        chatProductSelections.splice(idx, 1);
    } else {
        chatProductSelections.push({ id, name, imageUrl, originalPrice, tierPrice, discountPercent });
    }
    const item = document.getElementById(`chatProdItem_${id}`);
    if (item) {
        const isNowSelected = chatProductSelections.some(s => s.id === id);
        item.style.border = isNowSelected ? '1.5px solid rgba(102,126,234,0.5)' : '1.5px solid transparent';
        item.style.background = isNowSelected ? 'rgba(102,126,234,0.1)' : 'transparent';
        const checkEl = item.querySelector('[data-check]');
        if (checkEl) {
            if (isNowSelected) {
                checkEl.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
                checkEl.style.color = 'white';
                checkEl.textContent = '✓';
            } else {
                checkEl.style.background = 'rgba(255,255,255,0.1)';
                checkEl.style.color = 'transparent';
                checkEl.textContent = '';
            }
        }
    }
    updateChatProductSelectedBar();
}

function updateChatProductSelectedBar() {
    const bar = document.getElementById('chatProductSelectedBar');
    const countEl = document.getElementById('chatProductSelectedCount');
    const thumbsEl = document.getElementById('chatProductSelectedThumbs');
    if (chatProductSelections.length === 0) {
        bar.style.display = 'none';
        return;
    }
    bar.style.display = 'block';
    countEl.textContent = chatProductSelections.length;
    thumbsEl.innerHTML = chatProductSelections.map(s => `
        <div style="position: relative; flex-shrink: 0;" title="${escapeHtml(s.name)}">
            ${s.imageUrl ? `<img src="${s.imageUrl}" style="width: 28px; height: 28px; object-fit: cover; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);">` : '<div style="width: 28px; height: 28px; background: rgba(255,255,255,0.1); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px;">📦</div>'}
            <div onclick="event.stopPropagation(); removeChatProductFromSelection(${s.id})" style="position: absolute; top: -5px; right: -5px; width: 14px; height: 14px; background: #ef4444; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 8px; color: white; cursor: pointer; line-height: 1;">×</div>
        </div>
    `).join('');
}

function removeChatProductFromSelection(id) {
    chatProductSelections = chatProductSelections.filter(s => s.id !== id);
    const item = document.getElementById(`chatProdItem_${id}`);
    if (item) {
        item.style.border = '1.5px solid transparent';
        item.style.background = 'transparent';
        const checkEl = item.querySelector('[data-check]');
        if (checkEl) {
            checkEl.style.background = 'rgba(255,255,255,0.1)';
            checkEl.style.color = 'transparent';
            checkEl.textContent = '';
        }
    }
    updateChatProductSelectedBar();
}

function clearChatProductSelection() {
    chatProductSelections.forEach(s => {
        const item = document.getElementById(`chatProdItem_${s.id}`);
        if (item) {
            item.style.border = '1.5px solid transparent';
            item.style.background = 'transparent';
            const checkEl = item.querySelector('[data-check]');
            if (checkEl) {
                checkEl.style.background = 'rgba(255,255,255,0.1)';
                checkEl.style.color = 'transparent';
                checkEl.textContent = '';
            }
        }
    });
    chatProductSelections = [];
    updateChatProductSelectedBar();
}

async function sendSelectedChatProducts() {
    if (!currentChatThreadId || chatProductSelections.length === 0) return;
    closeChatProductModal();
    for (const product of chatProductSelections) {
        try {
            await fetch(`/api/chat/threads/${currentChatThreadId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
                credentials: 'include',
                body: JSON.stringify({ content: '', product_id: product.id })
            });
        } catch (e) { console.error('Error sending product:', e); }
    }
    chatProductSelections = [];
    updateChatProductSelectedBar();
    loadChatMessages(currentChatThreadId);
}

function navigateToProduct(productId) {
    window.location.hash = 'products';
    switchPage('products');
    let attempts = 0;
    const maxAttempts = 30;
    const tryHighlight = () => {
        attempts++;
        const row = document.querySelector(`tr[data-product-id="${productId}"]`);
        if (row) {
            row.classList.remove('highlight-flash');
            void row.offsetWidth;
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('highlight-flash');
            setTimeout(() => row.classList.remove('highlight-flash'), 15000);
        } else if (attempts < maxAttempts) {
            setTimeout(tryHighlight, 500);
        }
    };
    setTimeout(tryHighlight, 500);
}

function selectChatProduct(id, name, imageUrl, originalPrice, tierPrice, discountPercent) {
    selectedChatProduct = { id, name, imageUrl, originalPrice, tierPrice, discountPercent };
    const preview = document.getElementById('chatProductPreview');
    const img = document.getElementById('chatProductPreviewImg');
    const nameEl = document.getElementById('chatProductPreviewName');
    const priceEl = document.getElementById('chatProductPreviewPrice');
    if (imageUrl) { img.src = imageUrl; img.style.display = 'block'; } else { img.style.display = 'none'; }
    nameEl.textContent = name;
    if (discountPercent > 0) {
        priceEl.innerHTML = `฿${formatNumber(tierPrice)} <span style="text-decoration: line-through; opacity: 0.5; font-size: 11px;">฿${formatNumber(originalPrice)}</span>`;
    } else {
        priceEl.textContent = `฿${formatNumber(originalPrice)}`;
    }
    preview.style.display = 'block';
    closeChatProductModal();
}

function removeChatProduct() {
    selectedChatProduct = null;
    document.getElementById('chatProductPreview').style.display = 'none';
}

function startChatPolling() {
    if (chatPollingInterval) clearInterval(chatPollingInterval);
    chatPollingInterval = setInterval(() => {
        if (currentChatThreadId) {
            loadChatMessages(currentChatThreadId);
        }
        loadChatUnreadCount();
    }, 5000);
}

function stopChatPolling() {
    if (chatPollingInterval) {
        clearInterval(chatPollingInterval);
        chatPollingInterval = null;
    }
}

async function loadChatUnreadCount() {
    try {
        const response = await fetch('/api/chat/unread-count', { credentials: 'include' });
        const data = await response.json();
        
        const badge = document.getElementById('chatUnreadCount');
        const chatNavItem = document.querySelector('a.nav-item[href="/chat"]');

        if (badge) {
            if (data.unread_count > 0) {
                badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                badge.style.display = 'inline';
                badge.classList.add('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.add('chat-nav-active');
            } else {
                badge.style.display = 'none';
                badge.classList.remove('chat-badge-animated');
                if (chatNavItem) chatNavItem.classList.remove('chat-nav-active');
            }
        }
    } catch (error) {
        console.error('Error loading unread count:', error);
    }
}

// Quick Replies
async function loadQuickReplyButtons() {
    try {
        const response = await fetch('/api/chat/quick-replies', { credentials: 'include' });
        chatQuickReplies = await response.json();
        
        const container = document.getElementById('quickReplyButtons');
        if (!container) return;
        
        container.innerHTML = chatQuickReplies.slice(0, 5).map(qr => `
            <button onclick="insertQuickReply('${escapeHtml(qr.content)}')" class="btn btn-sm" style="font-size: 11px; padding: 4px 8px;">
                ${escapeHtml(qr.title)}
            </button>
        `).join('');
    } catch (error) {
        console.error('Error loading quick replies:', error);
    }
}

function insertQuickReply(content) {
    const input = document.getElementById('chatMessageInput');
    input.value = content;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
    input.focus();
}

// Broadcast Modal
function openBroadcastModal() {
    document.getElementById('broadcastModal').style.display = 'flex';
    loadTiersForBroadcast();
}

function closeBroadcastModal() {
    document.getElementById('broadcastModal').style.display = 'none';
    document.getElementById('broadcastTitle').value = '';
    document.getElementById('broadcastContent').value = '';
}

function toggleBroadcastTier() {
    const target = document.getElementById('broadcastTarget').value;
    document.getElementById('broadcastTierSelect').style.display = target === 'tier' ? 'block' : 'none';
}

async function loadTiersForBroadcast() {
    try {
        const response = await fetch('/api/tiers', { credentials: 'include' });
        const tiers = await response.json();
        
        const select = document.getElementById('broadcastTierId');
        select.innerHTML = '<option value="">เลือก Tier</option>' + 
            tiers.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
    } catch (error) {
        console.error('Error loading tiers:', error);
    }
}

async function sendBroadcast() {
    const title = document.getElementById('broadcastTitle').value.trim();
    const content = document.getElementById('broadcastContent').value.trim();
    const targetType = document.getElementById('broadcastTarget').value;
    const targetTierId = document.getElementById('broadcastTierId').value || null;
    
    if (!content) {
        showAlert('error', 'กรุณากรอกข้อความ');
        return;
    }
    
    try {
        const response = await fetch('/api/chat/broadcast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                title,
                content,
                target_type: targetType,
                target_tier_id: targetTierId
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', result.message || 'ส่ง Broadcast สำเร็จ');
            closeBroadcastModal();
            loadChatThreads();
        } else {
            showAlert('error', result.error || 'ไม่สามารถส่ง Broadcast ได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Quick Replies Management Modal
function openQuickRepliesModal() {
    document.getElementById('quickRepliesModal').style.display = 'flex';
    loadQuickRepliesList();
}

function closeQuickRepliesModal() {
    document.getElementById('quickRepliesModal').style.display = 'none';
}

async function loadQuickRepliesList() {
    try {
        const response = await fetch('/api/chat/quick-replies', { credentials: 'include' });
        const replies = await response.json();
        
        const container = document.getElementById('quickRepliesList');
        
        if (replies.length === 0) {
            container.innerHTML = '<div style="text-align: center; padding: 20px; color: rgba(255,255,255,0.5);">ยังไม่มี Quick Reply</div>';
            return;
        }
        
        container.innerHTML = replies.map(qr => `
            <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(255,255,255,0.05); border-radius: 8px; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="font-weight: 600;">${escapeHtml(qr.title)}</div>
                    <div style="font-size: 12px; opacity: 0.6;">${qr.shortcut ? 'Shortcut: ' + escapeHtml(qr.shortcut) : ''}</div>
                    <div style="font-size: 13px; margin-top: 4px; opacity: 0.8;">${escapeHtml(qr.content.substring(0, 100))}${qr.content.length > 100 ? '...' : ''}</div>
                </div>
                <button onclick="deleteQuickReply(${qr.id})" class="btn btn-sm" style="color: #ef4444;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading quick replies:', error);
    }
}

function showAddQuickReplyForm() {
    document.getElementById('addQuickReplyForm').style.display = 'block';
}

function hideAddQuickReplyForm() {
    document.getElementById('addQuickReplyForm').style.display = 'none';
    document.getElementById('newQuickReplyTitle').value = '';
    document.getElementById('newQuickReplyShortcut').value = '';
    document.getElementById('newQuickReplyContent').value = '';
}

async function saveQuickReply() {
    const title = document.getElementById('newQuickReplyTitle').value.trim();
    const shortcut = document.getElementById('newQuickReplyShortcut').value.trim();
    const content = document.getElementById('newQuickReplyContent').value.trim();
    
    if (!title || !content) {
        showAlert('error', 'กรุณากรอกชื่อและข้อความ');
        return;
    }
    
    try {
        const response = await fetch('/api/chat/quick-replies', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({ title, shortcut, content })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', 'เพิ่ม Quick Reply สำเร็จ');
            hideAddQuickReplyForm();
            loadQuickRepliesList();
            loadQuickReplyButtons();
        } else {
            showAlert('error', result.error || 'ไม่สามารถบันทึกได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function deleteQuickReply(replyId) {
    if (!confirm('ต้องการลบ Quick Reply นี้หรือไม่?')) return;
    
    try {
        const response = await fetch(`/api/chat/quick-replies/${replyId}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': csrfToken },
            credentials: 'include'
        });
        
        if (response.ok) {
            showAlert('success', 'ลบสำเร็จ');
            loadQuickRepliesList();
            loadQuickReplyButtons();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถลบได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

async function searchChatMessages() {
    const query = document.getElementById('chatSearchInput').value.trim();
    if (!query || query.length < 2) {
        showAlert('error', 'กรุณากรอกคำค้นอย่างน้อย 2 ตัวอักษร');
        return;
    }
    
    try {
        const response = await fetch(`/api/chat/search?q=${encodeURIComponent(query)}`, {
            credentials: 'include'
        });
        const results = await response.json();
        
        if (results.length === 0) {
            showAlert('info', 'ไม่พบข้อความที่ค้นหา');
            return;
        }
        
        const firstResult = results[0];
        selectChatThread(firstResult.thread_id, firstResult.reseller_name || firstResult.sender_name, '', null, false);
        
        showAlert('success', `พบ ${results.length} ข้อความ`);
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Reseller Search/Picker for Chat
let allResellersForChat = [];

async function loadAllResellersForChat() {
    try {
        const response = await fetch('/api/resellers?limit=1000', { credentials: 'include' });
        const data = await response.json();
        allResellersForChat = data.resellers || data;
        return allResellersForChat;
    } catch (error) {
        console.error('Error loading resellers:', error);
        return [];
    }
}

function toggleResellerPickerDropdown() {
    const dropdown = document.getElementById('resellerPickerDropdown');
    if (dropdown.style.display === 'none') {
        showResellerPickerDropdown();
    } else {
        dropdown.style.display = 'none';
    }
}

async function showResellerPickerDropdown(searchTerm = '') {
    const dropdown = document.getElementById('resellerPickerDropdown');
    dropdown.style.display = 'block';
    dropdown.innerHTML = '<div style="padding: 12px; text-align: center; color: rgba(255,255,255,0.5); font-size: 12px;">กำลังโหลด...</div>';
    
    if (allResellersForChat.length === 0) {
        await loadAllResellersForChat();
    }
    
    let filtered = allResellersForChat;
    if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filtered = allResellersForChat.filter(r => 
            (r.full_name && r.full_name.toLowerCase().includes(term)) ||
            (r.email && r.email.toLowerCase().includes(term)) ||
            (r.phone && r.phone.includes(term))
        );
    }
    
    if (filtered.length === 0) {
        dropdown.innerHTML = '<div style="padding: 12px; text-align: center; color: rgba(255,255,255,0.5); font-size: 12px;">ไม่พบตัวแทน</div>';
        return;
    }
    
    const tierIcons = { 'Bronze': '🥉', 'Silver': '🥈', 'Gold': '🥇', 'Platinum': '💎' };
    
    dropdown.innerHTML = filtered.slice(0, 50).map(r => `
        <div onclick="startChatWithReseller(${r.id}, '${escapeHtml(r.full_name || '')}', '${escapeHtml(r.tier_name || 'Bronze')}')" 
             style="padding: 10px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 10px; transition: background 0.2s;"
             onmouseover="this.style.background='rgba(168,85,247,0.2)'" onmouseout="this.style.background='transparent'">
            <div style="width: 36px; height: 36px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; color: white;">
                ${escapeHtml((r.full_name || '?').charAt(0).toUpperCase())}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 500; font-size: 13px; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.full_name || 'ไม่ระบุชื่อ')}</div>
                <div style="font-size: 11px; color: rgba(255,255,255,0.5);">${tierIcons[r.tier_name] || '🏷️'} ${escapeHtml(r.tier_name || 'Bronze')}</div>
            </div>
        </div>
    `).join('');
}

function searchResellersForChat(searchTerm) {
    if (searchTerm.length >= 1) {
        showResellerPickerDropdown(searchTerm);
    } else {
        document.getElementById('resellerPickerDropdown').style.display = 'none';
    }
}

async function startChatWithReseller(resellerId, resellerName, tierName) {
    document.getElementById('resellerPickerDropdown').style.display = 'none';
    document.getElementById('chatResellerSearchInput').value = '';
    
    try {
        const response = await fetch(`/api/chat/start/${resellerId}`, {
            method: 'POST',
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            selectChatThread(data.thread_id, resellerName, tierName, null, false);
            loadChatThreads();
        } else {
            const error = await response.json();
            showAlert('error', error.error || 'ไม่สามารถเริ่มแชทได้');
        }
    } catch (error) {
        showAlert('error', 'เกิดข้อผิดพลาด: ' + error.message);
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const dropdown = document.getElementById('resellerPickerDropdown');
    const searchInput = document.getElementById('chatResellerSearchInput');
    const pickerBtn = e.target.closest('button[onclick*="toggleResellerPickerDropdown"]');
    
    if (dropdown && dropdown.style.display !== 'none') {
        if (!dropdown.contains(e.target) && e.target !== searchInput && !pickerBtn) {
            dropdown.style.display = 'none';
        }
    }
});

// ─── Shipping Update Page ─────────────────────────────────────────────────────

function copyTrackingNumber(el, tn) {
    navigator.clipboard.writeText(tn).then(() => {
        el.textContent = 'คัดลอกแล้ว';
        el.style.color = '#34d399';
        setTimeout(() => {
            el.textContent = 'คัดลอก';
            el.style.color = 'rgba(255,255,255,0.5)';
        }, 1800);
    }).catch(() => {
        el.textContent = 'ไม่สำเร็จ';
    });
}

async function loadShippingUpdatePage() {
    const container = document.getElementById('shippingUpdateContent');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:48px;color:rgba(255,255,255,0.5);font-size:13px;">กำลังโหลด...</div>';

    try {
        const resp = await fetch(`${API_URL}/admin/orders/shipped`, { credentials: 'include' });
        const orders = await resp.json();

        const badge = document.getElementById('shippingUpdateCount');
        if (badge) {
            badge.textContent = orders.length;
            badge.style.display = orders.length > 0 ? 'inline' : 'none';
        }

        if (!orders.length) {
            container.innerHTML = `
                <div style="text-align:center;padding:72px 20px;color:rgba(255,255,255,0.35);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="display:block;margin:0 auto 14px;opacity:0.3;">
                        <rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/>
                        <circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>
                    </svg>
                    <div style="font-size:14px;font-weight:500;color:rgba(255,255,255,0.45);">ไม่มีคำสั่งซื้อที่กำลังจัดส่งในขณะนี้</div>
                </div>`;
            return;
        }

        const rows = orders.map(order => {
            const shipments = order.shipments || [];
            const sh = shipments[0] || {};
            const orderNum = escapeHtml(order.order_number || '#' + order.id);
            const resellerName = escapeHtml(order.reseller_name || '-');

            let daysLabel = '';
            if (sh.shipped_at) {
                const diff = Math.floor((Date.now() - new Date(sh.shipped_at)) / 86400000);
                daysLabel = diff === 0 ? 'ส่งวันนี้' : `${diff} วันที่แล้ว`;
            }
            const shippedDate = sh.shipped_at
                ? new Date(sh.shipped_at).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' })
                : '-';

            const shipmentsHtml = shipments.length > 0 ? shipments.map(s => {
                const tn = escapeHtml(s.tracking_number || '');
                const provider = escapeHtml(s.shipping_provider || 'ไม่ระบุ');
                const tUrl = escapeHtml(s.tracking_url || '');
                return `
                <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:rgba(0,0,0,0.2);border-radius:10px;flex-wrap:wrap;row-gap:6px;">
                    <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                        <span style="font-size:12px;font-weight:600;color:#ffffff;">${provider}</span>
                    </div>
                    <div style="flex:1;display:flex;align-items:center;gap:6px;min-width:0;flex-wrap:wrap;row-gap:4px;">
                        <span style="font-family:monospace;font-size:12px;color:#ffffff;background:rgba(255,255,255,0.08);padding:3px 10px;border-radius:6px;letter-spacing:0.5px;word-break:break-all;">${tn || '-'}</span>
                        ${tn ? `<button onclick="copyTrackingNumber(this,'${tn}')" style="background:none;border:none;color:rgba(255,255,255,0.5);font-size:11px;cursor:pointer;padding:0;white-space:nowrap;flex-shrink:0;">คัดลอก</button>` : ''}
                    </div>
                    ${tUrl ? `<a href="${tUrl}" target="_blank" style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:#ffffff;font-weight:500;text-decoration:none;background:rgba(129,140,248,0.2);border:1px solid rgba(129,140,248,0.4);padding:4px 10px;border-radius:7px;white-space:nowrap;flex-shrink:0;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        ติดตามพัสดุ
                    </a>` : ''}
                </div>`;
            }).join('') : `<div style="font-size:12px;color:rgba(255,255,255,0.35);padding:8px 0;">ยังไม่มีข้อมูลพัสดุ</div>`;

            return `
            <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:16px 18px;margin-bottom:10px;">

                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px;flex-wrap:wrap;row-gap:8px;">
                    <div style="display:flex;align-items:center;gap:10px;min-width:0;">
                        <div style="width:38px;height:38px;flex-shrink:0;border-radius:10px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.3);display:flex;align-items:center;justify-content:center;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                        </div>
                        <div style="min-width:0;">
                            <div style="font-size:14px;font-weight:700;color:#ffffff;">${orderNum}</div>
                            <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-top:2px;display:flex;align-items:center;gap:4px;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                ${resellerName}
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end;row-gap:4px;">
                        <span style="display:inline-flex;align-items:center;gap:5px;background:rgba(14,165,233,0.15);border:1px solid rgba(14,165,233,0.35);color:#ffffff;font-size:10px;font-weight:600;padding:3px 9px;border-radius:20px;">
                            <span style="width:5px;height:5px;border-radius:50%;background:#38bdf8;flex-shrink:0;"></span>
                            กำลังจัดส่ง
                        </span>
                        ${shippedDate !== '-' ? `<div style="text-align:right;"><div style="font-size:11px;color:rgba(255,255,255,0.7);">${shippedDate}</div>${daysLabel ? `<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-top:1px;">${daysLabel}</div>` : ''}</div>` : ''}
                    </div>
                </div>

                <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px;">
                    ${shipmentsHtml}
                </div>

                <div id="shipping-actions-${order.id}" style="display:flex;gap:8px;flex-wrap:wrap;">
                    <button onclick="showShippingConfirm(${order.id},'${orderNum}','delivered')"
                        style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        จัดส่งสำเร็จ
                    </button>
                    <button onclick="showShippingConfirm(${order.id},'${orderNum}','return')"
                        style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.45);color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
                        สินค้าตีกลับ
                    </button>
                </div>
            </div>`;
        }).join('');

        container.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
                <span style="font-size:13px;color:rgba(255,255,255,0.6);">กำลังจัดส่งอยู่</span>
                <span style="background:rgba(14,165,233,0.2);border:1px solid rgba(14,165,233,0.4);color:#ffffff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;">${orders.length} รายการ</span>
            </div>
            ${rows}`;

    } catch (err) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:#f87171;">เกิดข้อผิดพลาดในการโหลดข้อมูล</div>';
        console.error('loadShippingUpdatePage error:', err);
    }
}

function showShippingConfirm(orderId, orderNum, action) {
    const actionsDiv = document.getElementById(`shipping-actions-${orderId}`);
    if (!actionsDiv) return;

    const isDelivered = action === 'delivered';
    const label    = isDelivered ? 'ยืนยันจัดส่งสำเร็จ?' : 'ยืนยันสินค้าตีกลับ?';
    const color    = isDelivered ? '#10b981' : '#ef4444';
    const colorBg  = isDelivered ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
    const colorBdr = isDelivered ? 'rgba(16,185,129,0.45)' : 'rgba(239,68,68,0.45)';
    const iconSvg  = isDelivered
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>`;

    const onConfirm = isDelivered
        ? `markShippingDelivered(${orderId},'${orderNum}')`
        : `openFailedDeliveryModal(${orderId},'${orderNum}');restoreShippingActions(${orderId},'${orderNum}')`;

    actionsDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;width:100%;background:${colorBg};border:1px solid ${colorBdr};border-radius:10px;padding:10px 14px;flex-wrap:wrap;row-gap:8px;">
            <span style="flex:1;font-size:12px;font-weight:600;color:#ffffff;display:flex;align-items:center;gap:6px;">
                ${iconSvg} ${label}
            </span>
            <div style="display:flex;gap:6px;flex-shrink:0;">
                <button onclick="${onConfirm}"
                    style="padding:6px 16px;background:${color};border:none;color:#ffffff;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;">
                    ยืนยัน
                </button>
                <button onclick="restoreShippingActions(${orderId},'${orderNum}')"
                    style="padding:6px 14px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);color:#ffffff;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;">
                    ยกเลิก
                </button>
            </div>
        </div>`;
}

function restoreShippingActions(orderId, orderNum) {
    const actionsDiv = document.getElementById(`shipping-actions-${orderId}`);
    if (!actionsDiv) return;
    actionsDiv.innerHTML = `
        <button onclick="showShippingConfirm(${orderId},'${orderNum}','delivered')"
            style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            จัดส่งสำเร็จ
        </button>
        <button onclick="showShippingConfirm(${orderId},'${orderNum}','return')"
            style="flex:1;min-width:120px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 14px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.45);color:#ffffff;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
            สินค้าตีกลับ
        </button>`;
    actionsDiv.style.display = 'flex';
    actionsDiv.style.gap = '8px';
    actionsDiv.style.flexWrap = 'wrap';
}

async function markShippingDelivered(orderId, orderNumber) {
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/mark-delivered`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await resp.json();
        if (resp.ok) {
            showGlobalAlert(`✅ อัปเดต ${orderNumber} เป็นจัดส่งสำเร็จแล้ว`, 'success');
            loadShippingUpdatePage();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (err) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

function openFailedDeliveryModal(orderId, orderNumber) {
    document.getElementById('failedDeliveryOrderId').value = orderId;
    document.getElementById('failedDeliveryReason').value = '';
    const modal = document.getElementById('failedDeliveryModal');
    if (modal) { modal.style.display = 'flex'; }
}

function closeFailedDeliveryModal() {
    const modal = document.getElementById('failedDeliveryModal');
    if (modal) { modal.style.display = 'none'; }
}

async function confirmFailedDelivery() {
    const orderId = document.getElementById('failedDeliveryOrderId').value;
    const reason = document.getElementById('failedDeliveryReason').value.trim();
    if (!reason) {
        showGlobalAlert('กรุณากรอกเหตุผล', 'error');
        return;
    }
    try {
        const resp = await fetch(`${API_URL}/admin/orders/${orderId}/mark-failed-delivery`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        const data = await resp.json();
        if (resp.ok) {
            closeFailedDeliveryModal();
            showGlobalAlert('📦 บันทึกสินค้าตีกลับเรียบร้อย', 'success');
            loadShippingUpdatePage();
        } else {
            showGlobalAlert(data.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (err) {
        showGlobalAlert('เกิดข้อผิดพลาด', 'error');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);

