let deferredInstallPrompt = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
      .then(reg => {
        console.log('SW registered:', reg.scope);
        reg.update();

        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'activated') {
                console.log('New SW activated');
              }
            });
          }
        });

        if (reg.waiting) {
          reg.waiting.postMessage({ type: 'SKIP_WAITING' });
        }
      })
      .catch(err => {
        console.log('SW registration failed:', err);
      });

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      console.log('SW controller changed, new SW active');
    });
  });
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  showInstallBanner();
});

function showInstallBanner() {
  const existing = document.getElementById('pwaInstallBanner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'pwaInstallBanner';
  banner.innerHTML = `
    <div style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 99999;
         background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 14px 20px;
         border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); display: flex; align-items: center; gap: 14px;
         max-width: 420px; width: calc(100% - 32px); font-family: 'Inter', sans-serif; animation: slideUp 0.4s ease;">
      <div style="font-size: 32px; flex-shrink: 0;">📱</div>
      <div style="flex: 1;">
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 2px;">ติดตั้ง EKG Shops</div>
        <div style="font-size: 12px; opacity: 0.85;">เพิ่มลงหน้าจอเพื่อเข้าถึงได้เร็วขึ้น</div>
      </div>
      <button onclick="installPWA()" style="background: white; color: #7c3aed; border: none; padding: 8px 16px;
              border-radius: 10px; font-weight: 600; font-size: 13px; cursor: pointer; white-space: nowrap;">ติดตั้ง</button>
      <button onclick="dismissInstallBanner()" style="background: none; border: none; color: white; opacity: 0.6;
              cursor: pointer; font-size: 18px; padding: 0 4px;">&times;</button>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = '@keyframes slideUp { from { transform: translateX(-50%) translateY(100px); opacity: 0; } to { transform: translateX(-50%) translateY(0); opacity: 1; } }';
  banner.appendChild(style);

  document.body.appendChild(banner);
}

function installPWA() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    deferredInstallPrompt.userChoice.then(choice => {
      if (choice.outcome === 'accepted') {
        console.log('PWA installed');
      }
      deferredInstallPrompt = null;
      dismissInstallBanner();
    });
  }
}

function dismissInstallBanner() {
  const banner = document.getElementById('pwaInstallBanner');
  if (banner) banner.remove();
  localStorage.setItem('pwa_banner_dismissed', Date.now().toString());
}

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  dismissInstallBanner();
  console.log('PWA installed successfully');
});

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function subscribeToPush() {
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('Notification permission denied');
      return false;
    }

    const registration = await navigator.serviceWorker.ready;

    const response = await fetch('/api/push/vapid-public-key', { credentials: 'include' });
    if (!response.ok) {
      console.log('Failed to get VAPID key, status:', response.status);
      return false;
    }
    const { publicKey } = await response.json();

    if (!publicKey) {
      console.log('No VAPID public key available');
      return false;
    }

    let subscription = await registration.pushManager.getSubscription();
    
    if (subscription) {
      try {
        await subscription.unsubscribe();
        console.log('Unsubscribed old push subscription');
      } catch(e) {
        console.log('Error unsubscribing old:', e);
      }
    }

    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    console.log('New push subscription created:', subscription.endpoint.substring(0, 60));

    const subResponse = await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ subscription: subscription.toJSON() })
    });

    if (subResponse.ok) {
      console.log('Push subscription saved to server');
      localStorage.setItem('push_subscribed', Date.now().toString());
      return true;
    }
    console.log('Failed to save subscription, status:', subResponse.status);
    return false;
  } catch (error) {
    console.error('Push subscription error:', error);
    return false;
  }
}

async function refreshPushSubscription() {
  try {
    if (!('Notification' in window) || !('PushManager' in window)) return;
    if (Notification.permission !== 'granted') return;

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();

    const keyResponse = await fetch('/api/push/vapid-public-key', { credentials: 'include' });
    if (!keyResponse.ok) return false;
    const { publicKey } = await keyResponse.json();
    if (!publicKey) return false;

    const serverKeyBytes = urlBase64ToUint8Array(publicKey);
    let needResubscribe = false;

    if (subscription) {
      const subKey = subscription.options && subscription.options.applicationServerKey;
      if (subKey) {
        const subKeyArray = new Uint8Array(subKey);
        if (subKeyArray.length !== serverKeyBytes.length || 
            !subKeyArray.every((v, i) => v === serverKeyBytes[i])) {
          console.log('VAPID key mismatch, re-subscribing');
          needResubscribe = true;
        }
      } else {
        needResubscribe = true;
      }

      if (!needResubscribe) {
        const subResponse = await fetch('/api/push/subscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ subscription: subscription.toJSON() })
        });
        
        if (subResponse.ok) {
          console.log('Push subscription refreshed');
          return true;
        } else if (subResponse.status === 401) {
          return false;
        }
      }
    }

    if (!subscription || needResubscribe) {
      if (subscription) {
        try { await subscription.unsubscribe(); } catch(e) {}
      }
      const newSub = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: serverKeyBytes
      });
      const subResponse = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ subscription: newSub.toJSON() })
      });
      if (subResponse.ok) {
        console.log('Push subscription re-created with current VAPID key');
        return true;
      }
    }
    return false;
  } catch (error) {
    console.log('Push refresh error:', error);
    return false;
  }
}

async function unsubscribeFromPush() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();

    if (subscription) {
      await fetch('/api/push/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ endpoint: subscription.endpoint })
      });

      await subscription.unsubscribe();
      return true;
    }
    return false;
  } catch (error) {
    console.error('Push unsubscribe error:', error);
    return false;
  }
}

async function checkPushStatus() {
  try {
    if (!('Notification' in window)) return { supported: false };
    if (!('serviceWorker' in navigator)) return { supported: false };
    if (!('PushManager' in window)) return { supported: false };

    const permission = Notification.permission;
    if (permission === 'denied') return { supported: true, permission: 'denied', subscribed: false };

    const swReadyPromise = navigator.serviceWorker.ready;
    const timeoutPromise = new Promise(resolve => setTimeout(() => resolve(null), 5000));
    const registration = await Promise.race([swReadyPromise, timeoutPromise]);

    if (!registration) {
      return { supported: true, permission: permission, subscribed: false };
    }

    const subscription = await registration.pushManager.getSubscription();
    return {
      supported: true,
      permission: permission,
      subscribed: !!subscription
    };
  } catch (error) {
    console.log('Push status check error:', error);
    if ('Notification' in window) {
      return { supported: true, permission: Notification.permission, subscribed: false };
    }
    return { supported: false };
  }
}

async function initPushNotifications() {
  try {
    const status = await checkPushStatus();
    console.log('Push status:', JSON.stringify(status));

    if (!status.supported) return;

    if (status.permission === 'granted') {
      await refreshPushSubscription();
      return;
    }

    if (status.permission === 'denied') return;

    if (status.permission === 'default') {
      const dismissed = localStorage.getItem('push_prompt_dismissed');
      if (dismissed && (Date.now() - parseInt(dismissed)) < 300000) return;

      showPushPrompt();
    }
  } catch (error) {
    console.log('Push init error:', error);
  }
}

function showPushPrompt() {
  const existing = document.getElementById('pushPromptBanner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'pushPromptBanner';
  banner.innerHTML = `
    <div style="position: fixed; top: 20px; right: 20px; z-index: 99999;
         background: rgba(15, 10, 26, 0.95); backdrop-filter: blur(20px); color: white; padding: 18px 20px;
         border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.1);
         max-width: 360px; width: calc(100% - 32px); font-family: 'Inter', sans-serif; animation: slideIn 0.4s ease;">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
        <div style="font-size: 28px;">🔔</div>
        <div>
          <div style="font-weight: 600; font-size: 14px;">เปิดการแจ้งเตือน</div>
          <div style="font-size: 12px; opacity: 0.7; margin-top: 2px;">รับแจ้งเตือนแชท, ออเดอร์ แบบเรียลไทม์</div>
        </div>
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end;">
        <button onclick="dismissPushPrompt()" style="background: rgba(255,255,255,0.1); color: white; border: none;
                padding: 8px 16px; border-radius: 10px; font-size: 13px; cursor: pointer;">ไว้ทีหลัง</button>
        <button onclick="acceptPushPrompt()" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white;
                border: none; padding: 8px 20px; border-radius: 10px; font-weight: 600; font-size: 13px; cursor: pointer;">เปิดเลย</button>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = '@keyframes slideIn { from { transform: translateX(100px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }';
  banner.appendChild(style);

  document.body.appendChild(banner);
}

function dismissPushPrompt() {
  const banner = document.getElementById('pushPromptBanner');
  if (banner) banner.remove();
  localStorage.setItem('push_prompt_dismissed', Date.now().toString());
}

async function acceptPushPrompt() {
  const banner = document.getElementById('pushPromptBanner');
  if (banner) banner.remove();

  const result = await subscribeToPush();
  if (result) {
    showPushSuccess();
  }
}

function showPushSuccess() {
  const toast = document.createElement('div');
  toast.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 99999; background: rgba(34, 197, 94, 0.9); color: white; padding: 14px 20px; border-radius: 12px; font-family: Inter, sans-serif; font-size: 14px; animation: slideIn 0.3s ease; box-shadow: 0 4px 20px rgba(0,0,0,0.3);';
  toast.textContent = '✅ เปิดการแจ้งเตือนสำเร็จ!';
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

document.addEventListener('DOMContentLoaded', () => {
  if ('serviceWorker' in navigator && 'PushManager' in window) {
    setTimeout(() => initPushNotifications(), 2000);
  }
});
