import type { PolicyCard } from "../types";

interface Props {
  card: PolicyCard;
}

// 백엔드 PolicyItem.category 값(구직창업/창업/경영·기술)에 맞춘 배지 색상.
const CATEGORY_COLORS: Record<string, string> = {
  구직창업: "#4f7ef8",
  창업: "#1f9d54",
  "경영/기술": "#f8934f",
};

export default function PolicyCardComponent({ card }: Props) {
  const badgeColor = CATEGORY_COLORS[card.category] || "#6b7280";

  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #e2e5ec",
        borderRadius: "12px",
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        minWidth: 0,
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "#4f7ef8";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 0 0 1px #4f7ef820";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "#e2e5ec";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <span
            style={{
              background: badgeColor + "22",
              color: badgeColor,
              fontSize: "11px",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "999px",
              border: `1px solid ${badgeColor}44`,
              whiteSpace: "nowrap",
            }}
          >
            {card.category}
          </span>
          <span style={{ color: "#6b7280", fontSize: "12px" }}>{card.ministry}</span>
        </div>
      </div>

      {/* Policy name */}
      <div style={{ fontSize: "15px", fontWeight: 700, color: "#1f2430", lineHeight: 1.4 }}>
        {card.name}
      </div>

      {/* Info grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px" }}>
        <InfoRow label="지원대상" value={card.target} />
        <InfoRow label="지원금액" value={card.amount} highlight />
        <InfoRow label="신청기간" value={card.period} />
      </div>

      {/* Reason */}
      <div
        style={{
          background: "#f5f7fb",
          borderRadius: "8px",
          padding: "10px 12px",
          fontSize: "12.5px",
          color: "#4b5164",
          lineHeight: 1.6,
          borderLeft: "3px solid #4f7ef8",
        }}
      >
        <span style={{ color: "#4f7ef8", fontWeight: 600, marginRight: "4px" }}>추천 이유</span>
        {card.reason}
      </div>

      {/* Action */}
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <a
          href={card.url || undefined}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            background: card.url ? "#4f7ef8" : "#eef1f7",
            color: card.url ? "#fff" : "#9aa0b4",
            border: "none",
            borderRadius: "8px",
            padding: "7px 16px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: card.url ? "pointer" : "default",
            textDecoration: "none",
            pointerEvents: card.url ? "auto" : "none",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => {
            if (card.url) (e.currentTarget as HTMLAnchorElement).style.background = "#6b93fa";
          }}
          onMouseLeave={(e) => {
            if (card.url) (e.currentTarget as HTMLAnchorElement).style.background = "#4f7ef8";
          }}
        >
          자세히 보기 →
        </a>
      </div>
    </div>
  );
}

function InfoRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
      <span style={{ fontSize: "11px", color: "#6b7280", fontWeight: 500 }}>{label}</span>
      <span
        style={{
          fontSize: "12.5px",
          color: highlight ? "#1f9d54" : "#1f2430",
          fontWeight: highlight ? 700 : 400,
          lineHeight: 1.4,
        }}
      >
        {value}
      </span>
    </div>
  );
}
