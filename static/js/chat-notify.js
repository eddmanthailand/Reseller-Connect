(function() {
  let lastSeenMessageId = 0;
  let pollInterval = null;
  let shownMessageIds = new Set();
  const POLL_DELAY = 5000;
  let chatPageActive = false;

  function createNotifyStyles() {
    if (document.getElementById('chatNotifyStyles')) return;
    const style = document.createElement('style');
    style.id = 'chatNotifyStyles';
    style.textContent = `
      .chat-notify-container {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 100000;
        display: flex;
        flex-direction: column;
        align-items: center;
        pointer-events: none;
        padding-top: 12px;
        gap: 8px;
      }
      .chat-notify-banner {
        pointer-events: auto;
        width: calc(100% - 24px);
        max-width: 420px;
        background: rgba(15, 10, 30, 0.95);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,0.15);
        box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(124,58,237,0.2);
        padding: 14px 16px;
        cursor: pointer;
        animation: chatNotifySlideDown 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        touch-action: pan-y;
        transition: transform 0.2s ease, opacity 0.2s ease;
        will-change: transform;
      }
      .chat-notify-banner.swiping {
        transition: none;
      }
      .chat-notify-banner.dismissing {
        transform: translateX(120%) !important;
        opacity: 0;
      }
      .chat-notify-header {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .chat-notify-avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, #7c3aed, #ec4899);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        color: white;
        font-weight: 700;
        flex-shrink: 0;
      }
      .chat-notify-content {
        flex: 1;
        min-width: 0;
      }
      .chat-notify-sender {
        font-size: 14px;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .chat-notify-app {
        font-size: 10px;
        color: rgba(255,255,255,0.4);
        font-weight: 400;
      }
      .chat-notify-text {
        font-size: 13px;
        color: rgba(255,255,255,0.75);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .chat-notify-time {
        font-size: 11px;
        color: rgba(255,255,255,0.35);
        flex-shrink: 0;
        align-self: flex-start;
        margin-top: 2px;
      }
      @keyframes chatNotifySlideDown {
        from { transform: translateY(-100%); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    `;
    document.head.appendChild(style);
  }

  function getContainer() {
    let container = document.getElementById('chatNotifyContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'chatNotifyContainer';
      container.className = 'chat-notify-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function getInitial(name) {
    if (!name) return '?';
    return name.charAt(0).toUpperCase();
  }

  function timeAgo(dateStr) {
    const now = new Date();
    const date = new Date(dateStr);
    const diff = Math.floor((now - date) / 1000);
    if (diff < 60) return 'เมื่อสักครู่';
    if (diff < 3600) return Math.floor(diff / 60) + ' นาทีที่แล้ว';
    return Math.floor(diff / 3600) + ' ชม.ที่แล้ว';
  }

  function setupSwipeToDismiss(banner) {
    let startX = 0;
    let currentX = 0;
    let isDragging = false;

    banner.addEventListener('touchstart', (e) => {
      startX = e.touches[0].clientX;
      currentX = 0;
      isDragging = true;
      banner.classList.add('swiping');
    }, { passive: true });

    banner.addEventListener('touchmove', (e) => {
      if (!isDragging) return;
      currentX = e.touches[0].clientX - startX;
      if (currentX > 0) {
        banner.style.transform = `translateX(${currentX}px)`;
        banner.style.opacity = Math.max(0, 1 - (currentX / 200));
      }
    }, { passive: true });

    banner.addEventListener('touchend', () => {
      if (!isDragging) return;
      isDragging = false;
      banner.classList.remove('swiping');

      if (currentX > 80) {
        banner.classList.add('dismissing');
        setTimeout(() => banner.remove(), 250);
      } else {
        banner.style.transform = '';
        banner.style.opacity = '';
      }
    });
  }

  function showChatBanner(msg) {
    if (shownMessageIds.has(msg.id)) return;
    shownMessageIds.add(msg.id);

    if (shownMessageIds.size > 50) {
      const arr = Array.from(shownMessageIds);
      shownMessageIds = new Set(arr.slice(-30));
    }

    createNotifyStyles();
    const container = getContainer();

    const isReseller = window.location.pathname.includes('/reseller');
    const chatUrl = isReseller ? '/reseller#chat' : '/admin#chat';

    const banner = document.createElement('div');
    banner.className = 'chat-notify-banner';
    banner.innerHTML = `
      <div class="chat-notify-header">
        <div class="chat-notify-avatar">${getInitial(msg.sender_name)}</div>
        <div class="chat-notify-content">
          <div class="chat-notify-sender">
            ${msg.sender_name}
            <span class="chat-notify-app">EKG Shops</span>
          </div>
          <div class="chat-notify-text">${msg.preview}</div>
        </div>
        <div class="chat-notify-time">${timeAgo(msg.created_at)}</div>
      </div>
    `;

    banner.addEventListener('click', () => {
      if (window.location.hash === '#chat') {
        if (typeof window.openChatThread === 'function') {
          window.openChatThread(msg.thread_id);
        }
      } else {
        window.location.hash = '#chat';
      }
    });

    setupSwipeToDismiss(banner);
    container.appendChild(banner);

    const maxBanners = 3;
    while (container.children.length > maxBanners) {
      container.removeChild(container.firstChild);
    }
  }

  function isChatPageOpen() {
    return window.location.hash === '#chat';
  }

  async function pollNewMessages() {
    if (isChatPageOpen()) return;

    try {
      const resp = await fetch(`/api/chat/new-messages?since_id=${lastSeenMessageId}`, {
        credentials: 'include'
      });
      
      if (!resp.ok) return;
      
      const data = await resp.json();
      if (data.messages && data.messages.length > 0) {
        const sorted = data.messages.sort((a, b) => a.id - b.id);
        for (const msg of sorted) {
          if (msg.id > lastSeenMessageId) {
            lastSeenMessageId = msg.id;
          }
          showChatBanner(msg);
        }
      }
    } catch (e) {
      // silent
    }
  }

  async function initLastSeenId() {
    try {
      const resp = await fetch('/api/chat/new-messages?since_id=0', {
        credentials: 'include'
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.messages && data.messages.length > 0) {
        for (const msg of data.messages) {
          if (msg.id > lastSeenMessageId) {
            lastSeenMessageId = msg.id;
          }
        }
      }
    } catch(e) {
      // silent
    }
  }

  function startPolling() {
    if (pollInterval) return;
    initLastSeenId().then(() => {
      pollInterval = setInterval(pollNewMessages, POLL_DELAY);
    });
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(startPolling, 3000);
  });

  window.addEventListener('hashchange', () => {
    if (isChatPageOpen()) {
      const container = document.getElementById('chatNotifyContainer');
      if (container) container.innerHTML = '';
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopPolling();
    } else {
      startPolling();
    }
  });
})();
