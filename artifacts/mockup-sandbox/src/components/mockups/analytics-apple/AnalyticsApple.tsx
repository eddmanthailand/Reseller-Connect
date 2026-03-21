import { useState } from "react";

const BLUE = "#007AFF";
const GREEN = "#34C759";
const ORANGE = "#FF9500";
const RED = "#FF3B30";
const PURPLE = "#AF52DE";
const INDIGO = "#5856D6";
const GRAY6 = "#F2F2F7";
const GRAY5 = "#E5E5EA";
const GRAY4 = "#C7C7CC";
const GRAY3 = "#AEAEB2";
const GRAY2 = "#636366";
const GRAY1 = "#1C1C1E";

const summary = {
  total_members: 10,
  active_users: 1,
  sessions: 2,
  total_events: 37,
  cart_users: 1,
  buyers: 1,
  product_view_users: 1,
  checkout_users: 1,
};

const funnelData = [
  { label: "สมาชิกทั้งหมด", val: 10, color: PURPLE },
  { label: "เข้าใช้งาน", val: 1, color: BLUE },
  { label: "ดูสินค้า", val: 1, color: "#0891B2" },
  { label: "ใส่ตะกร้า", val: 1, color: ORANGE },
  { label: "สั่งซื้อแล้ว", val: 1, color: GREEN },
];

const topPages = [
  { page: "/shop", visits: 18 },
  { page: "/", visits: 9 },
  { page: "/profile", visits: 5 },
  { page: "/orders", visits: 3 },
  { page: "/cart", visits: 2 },
];

const topProducts = [
  { name: "เสื้อพยาบาลคอกลม แขนยาว", views: 8 },
  { name: "กางเกงขาว สำหรับพยาบาล", views: 5 },
  { name: "ชุดสครับสีเขียว", views: 3 },
];

const hours = Array.from({ length: 24 }, (_, i) => ({
  hour: i,
  cnt: [0, 0, 0, 1, 0, 0, 2, 5, 8, 12, 9, 7, 4, 6, 8, 10, 12, 14, 11, 8, 5, 3, 2, 1][i] || 0,
}));

const dowData = [
  { day: "จ", cnt: 12 },
  { day: "อ", cnt: 18 },
  { day: "พ", cnt: 15 },
  { day: "พฤ", cnt: 20 },
  { day: "ศ", cnt: 16 },
  { day: "ส", cnt: 8 },
  { day: "อา", cnt: 5 },
];

const tierData = [
  { name: "Bronze", members: 6, avg_orders: 1.2, color: "#CD7F32" },
  { name: "Silver", members: 3, avg_orders: 2.8, color: "#A0A0A0" },
  { name: "Gold", members: 1, avg_orders: 5.0, color: "#FFD700" },
];

const interestGap = [
  { product_name: "เสื้อพยาบาลคอกลม", view_cnt: 8, order_cnt: 2 },
  { product_name: "กางเกงขาว", view_cnt: 5, order_cnt: 1 },
  { product_name: "ชุดสครับสีเขียว", view_cnt: 3, order_cnt: 0 },
];

const engageLeaders = [
  { name: "น.ส. สุดา มาลา", events: 24, score: 92, tier: "Gold" },
  { name: "นาง วารี สุข", events: 18, score: 74, tier: "Silver" },
  { name: "น.ส. พิม ใจดี", events: 12, score: 55, tier: "Silver" },
  { name: "นาย ดวง ดี", events: 7, score: 31, tier: "Bronze" },
  { name: "น.ส. อ้อย หวาน", events: 4, score: 18, tier: "Bronze" },
];

function StatCard({
  label, value, sub, color = GRAY1, icon, accent
}: {
  label: string; value: string | number; sub?: string; color?: string; icon: string; accent?: string;
}) {
  return (
    <div style={{
      background: "#fff",
      borderRadius: 18,
      padding: "20px 20px 18px",
      boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.06)",
      display: "flex",
      flexDirection: "column",
      gap: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: GRAY2, letterSpacing: 0.2 }}>{label}</span>
        <span style={{
          width: 28, height: 28, borderRadius: 8, background: accent || GRAY6,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14
        }}>{icon}</span>
      </div>
      <div style={{ fontSize: 36, fontWeight: 700, color, letterSpacing: -1.5, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: GRAY3, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function SectionLabel({ children }: { children: string }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: GRAY1, marginBottom: 14, letterSpacing: -0.2 }}>
      {children}
    </div>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "#fff",
      borderRadius: 18,
      padding: "20px",
      boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.06)",
      ...style
    }}>
      {children}
    </div>
  );
}

function TabOverview() {
  const maxFunnel = funnelData[0].val;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Stat grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        <StatCard label="สมาชิกทั้งหมด" value={summary.total_members} sub="registered" icon="👥" accent="#EDE9FE" color={PURPLE} />
        <StatCard label="ACTIVE 30 วัน" value={summary.active_users} sub={`${Math.round(summary.active_users / summary.total_members * 100)}% ของทั้งหมด`} icon="⚡" accent="#FFF3E0" color={ORANGE} />
        <StatCard label="SESSIONS" value={summary.sessions} sub="การเข้าชม" icon="🔗" accent="#E3F2FD" color={BLUE} />
        <StatCard label="EVENTS" value={summary.total_events} sub="กิจกรรมทั้งหมด" icon="📊" accent="#F3E5F5" color={INDIGO} />
        <StatCard label="ใส่ตะกร้า" value={summary.cart_users} sub="คน" icon="🛒" accent="#FFF8E1" color={ORANGE} />
        <StatCard label="สั่งซื้อแล้ว" value={summary.buyers} sub="conversion" icon="✅" accent="#E8F5E9" color={GREEN} />
      </div>

      {/* Funnel */}
      <Card>
        <SectionLabel>Conversion Funnel</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {funnelData.map((f, i) => {
            const pct = Math.round(f.val / maxFunnel * 100);
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 110, fontSize: 12, color: GRAY2, flexShrink: 0, fontWeight: 500 }}>{f.label}</div>
                <div style={{ flex: 1, background: GRAY6, borderRadius: 6, height: 24, overflow: "hidden", position: "relative" }}>
                  <div style={{
                    width: `${pct}%`, height: "100%", background: f.color, borderRadius: 6,
                    display: "flex", alignItems: "center", paddingLeft: 10,
                    transition: "width 0.6s ease",
                  }}>
                    <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>{f.val.toLocaleString()}</span>
                  </div>
                </div>
                <div style={{ width: 42, fontSize: 12, color: GRAY3, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {pct}%
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Top pages + top products */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Card>
          <SectionLabel>หน้ายอดนิยม</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {topPages.map((p, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "9px 0", borderBottom: i < topPages.length - 1 ? `0.5px solid ${GRAY5}` : "none"
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: 6, background: i === 0 ? "#EDE9FE" : GRAY6,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 10, fontWeight: 700, color: i === 0 ? PURPLE : GRAY3
                  }}>{i + 1}</div>
                  <span style={{ fontSize: 12, color: GRAY1, fontFamily: "SF Mono, monospace" }}>{p.page}</span>
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: BLUE }}>{p.visits}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionLabel>สินค้าที่ถูกดูมากสุด</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {topProducts.map((p, i) => {
              const maxV = topProducts[0].views;
              return (
                <div key={i} style={{ padding: "10px 0", borderBottom: i < topProducts.length - 1 ? `0.5px solid ${GRAY5}` : "none" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                    <span style={{ fontSize: 12, color: GRAY1, fontWeight: 500, flex: 1, paddingRight: 8 }}>{p.name}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: ORANGE, flexShrink: 0 }}>{p.views}</span>
                  </div>
                  <div style={{ background: GRAY6, borderRadius: 4, height: 4, overflow: "hidden" }}>
                    <div style={{ width: `${p.views / maxV * 100}%`, height: "100%", background: ORANGE, borderRadius: 4 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabBehavior() {
  const maxHour = Math.max(...hours.map(h => h.cnt), 1);
  const maxDow = Math.max(...dowData.map(d => d.cnt), 1);
  const maxTier = Math.max(...tierData.map(t => t.members), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Hour heatmap */}
      <Card>
        <SectionLabel>ช่วงเวลาที่ Active (24 ชม.)</SectionLabel>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 80 }}>
          {hours.map(h => {
            const pct = h.cnt / maxHour;
            const isPeak = h.cnt === maxHour;
            return (
              <div key={h.hour} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                <div style={{
                  width: "100%", borderRadius: "4px 4px 2px 2px",
                  background: isPeak ? BLUE : `rgba(0,122,255,${0.12 + pct * 0.75})`,
                  height: Math.max(pct * 60, 3),
                  transition: "height 0.5s ease",
                }} />
                {h.hour % 6 === 0 && (
                  <span style={{ fontSize: 9, color: GRAY3, fontVariantNumeric: "tabular-nums" }}>{h.hour}</span>
                )}
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
          <span style={{ fontSize: 11, color: GRAY3 }}>00:00</span>
          <span style={{ fontSize: 11, color: BLUE, fontWeight: 600 }}>
            Peak: {hours.find(h => h.cnt === maxHour)?.hour}:00 น.
          </span>
          <span style={{ fontSize: 11, color: GRAY3 }}>23:00</span>
        </div>
      </Card>

      {/* Day of week + Tier breakdown */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Card>
          <SectionLabel>วันที่ Active มากสุด</SectionLabel>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 90 }}>
            {dowData.map((d, i) => {
              const pct = d.cnt / maxDow;
              const isPeak = d.cnt === maxDow;
              return (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  <span style={{ fontSize: 9, fontWeight: 600, color: isPeak ? BLUE : GRAY3 }}>{d.cnt}</span>
                  <div style={{
                    width: "100%", borderRadius: "6px 6px 3px 3px",
                    background: isPeak ? BLUE : `rgba(0,122,255,${0.15 + pct * 0.6})`,
                    height: Math.max(pct * 56, 4),
                  }} />
                  <span style={{ fontSize: 11, fontWeight: 600, color: isPeak ? BLUE : GRAY2 }}>{d.day}</span>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <SectionLabel>Tier Breakdown</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {tierData.map((t, i) => (
              <div key={i}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: t.color }}>{t.name}</span>
                  <span style={{ fontSize: 12, color: GRAY2 }}>{t.members} คน · avg {t.avg_orders} orders</span>
                </div>
                <div style={{ background: GRAY6, borderRadius: 5, height: 7, overflow: "hidden" }}>
                  <div style={{
                    width: `${t.members / maxTier * 100}%`, height: "100%",
                    background: t.color, borderRadius: 5,
                  }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Interest gap + Leaderboard */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Card>
          <SectionLabel>ดูแต่ยังไม่สั่ง</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {interestGap.map((p, i) => {
              const convRate = p.view_cnt > 0 ? Math.round(p.order_cnt / p.view_cnt * 100) : 0;
              const isLow = convRate < 30;
              return (
                <div key={i} style={{
                  padding: "11px 0", borderBottom: i < interestGap.length - 1 ? `0.5px solid ${GRAY5}` : "none"
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: GRAY1, fontWeight: 500, flex: 1, paddingRight: 8 }}>{p.product_name}</span>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 5,
                      background: isLow ? "#FFF3F3" : "#E8F5E9",
                      color: isLow ? RED : GREEN,
                    }}>
                      {convRate}% conv
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 12, fontSize: 11, color: GRAY3 }}>
                    <span>👁 ดู {p.view_cnt} ครั้ง</span>
                    <span>🛒 สั่ง {p.order_cnt} ครั้ง</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <SectionLabel>Engagement Leaderboard</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {engageLeaders.map((u, i) => {
              const tierColors: Record<string, string> = { Gold: "#FFD700", Silver: "#A0A0A0", Bronze: "#CD7F32" };
              return (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "9px 0", borderBottom: i < engageLeaders.length - 1 ? `0.5px solid ${GRAY5}` : "none"
                }}>
                  <div style={{
                    width: 26, height: 26, borderRadius: 8,
                    background: i === 0 ? "#EDE9FE" : GRAY6,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: i === 0 ? 14 : 11, fontWeight: 700,
                    color: i === 0 ? PURPLE : GRAY3, flexShrink: 0,
                  }}>
                    {i === 0 ? "🏆" : i + 1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: GRAY1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{u.name}</div>
                    <div style={{ fontSize: 10, color: GRAY3, marginTop: 1 }}>{u.events} events</div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: BLUE }}>{u.score}</span>
                    <span style={{ fontSize: 9, fontWeight: 700, color: tierColors[u.tier] || GRAY3 }}>{u.tier}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}

export function AnalyticsApple() {
  const [tab, setTab] = useState<"overview" | "behavior">("overview");
  const [days, setDays] = useState("30");

  return (
    <div style={{
      minHeight: "100vh",
      background: GRAY6,
      fontFamily: "-apple-system, 'SF Pro Display', 'SF Pro Text', BlinkMacSystemFont, 'Helvetica Neue', sans-serif",
      color: GRAY1,
      WebkitFontSmoothing: "antialiased",
    }}>
      {/* Sticky header */}
      <div style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "rgba(242,242,247,0.88)",
        backdropFilter: "saturate(200%) blur(24px)",
        WebkitBackdropFilter: "saturate(200%) blur(24px)",
        borderBottom: `0.5px solid rgba(0,0,0,0.08)`,
        padding: "0 24px",
        height: 52,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button style={{
            display: "flex", alignItems: "center", gap: 4,
            background: "none", border: "none", color: BLUE, fontSize: 15, fontWeight: 500,
            cursor: "pointer", padding: "4px 0", fontFamily: "inherit",
          }}>
            <svg width="9" height="14" viewBox="0 0 9 15" fill="none">
              <path d="M7.5 1.5L1.5 7.5L7.5 13.5" stroke={BLUE} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            กลับ
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: "linear-gradient(135deg, #7c3aed, #5b21b6)",
              display: "flex", alignItems: "center", justifyContent: "center",
              boxShadow: "0 2px 8px rgba(124,58,237,0.35)",
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
                <path d="M18 20V10M12 20V4M6 20v-6" stroke="white" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: -0.5 }}>Analytics</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <select
            value={days}
            onChange={e => setDays(e.target.value)}
            style={{
              padding: "6px 10px", border: `0.5px solid ${GRAY4}`, borderRadius: 9,
              fontSize: 13, fontWeight: 500, color: GRAY1,
              background: "#fff", cursor: "pointer", outline: "none", fontFamily: "inherit",
              appearance: "none", paddingRight: 24,
              backgroundImage: `url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%23636366' strokeWidth='1.5' strokeLinecap='round'/%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center",
            }}
          >
            <option value="7">7 วัน</option>
            <option value="30">30 วัน</option>
            <option value="90">90 วัน</option>
          </select>
          <button style={{
            display: "flex", alignItems: "center", gap: 6,
            background: "linear-gradient(135deg, #7c3aed, #5b21b6)",
            color: "#fff", border: "none", borderRadius: 9,
            padding: "7px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
            boxShadow: "0 2px 8px rgba(124,58,237,0.35)", fontFamily: "inherit",
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            รีเฟรช
          </button>
        </div>
      </div>

      {/* Segmented tab bar */}
      <div style={{
        background: "rgba(242,242,247,0.88)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: `0.5px solid rgba(0,0,0,0.07)`,
        padding: "10px 24px",
        display: "flex", alignItems: "center",
      }}>
        <div style={{
          display: "flex", background: GRAY5, borderRadius: 10, padding: 3, gap: 2,
        }}>
          {[
            { id: "overview", label: "📋 ภาพรวม" },
            { id: "behavior", label: "🧠 พฤติกรรมสมาชิก" },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as "overview" | "behavior")}
              style={{
                padding: "6px 18px", borderRadius: 8, border: "none",
                fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
                background: tab === t.id ? "#fff" : "transparent",
                color: tab === t.id ? GRAY1 : GRAY2,
                boxShadow: tab === t.id ? "0 1px 3px rgba(0,0,0,0.12)" : "none",
                transition: "all 0.18s ease",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: "20px 24px", maxWidth: 1400, margin: "0 auto" }}>
        {tab === "overview" ? <TabOverview /> : <TabBehavior />}
      </div>
    </div>
  );
}
