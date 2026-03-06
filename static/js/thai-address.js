// thai-address.js — lazy loader
// ข้อมูลจริงอยู่ใน thai-address.json (268 KB)
// โหลดเฉพาะเมื่อต้องการใช้งาน ไม่บล็อก page load

let THAI_ADDRESSES = null;
let _thaiAddressPromise = null;

function loadThaiAddresses() {
    if (THAI_ADDRESSES) return Promise.resolve(THAI_ADDRESSES);
    if (_thaiAddressPromise) return _thaiAddressPromise;
    _thaiAddressPromise = fetch('/static/js/thai-address.json?v=20250306')
        .then(r => r.json())
        .then(data => {
            THAI_ADDRESSES = data;
            return data;
        });
    return _thaiAddressPromise;
}
