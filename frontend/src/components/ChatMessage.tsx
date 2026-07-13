import Markdown from "react-markdown";
import type { Message } from "../types";
import PolicyCardComponent from "./PolicyCard";

interface Props {
  message: Message;
}

function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className="msg-appear"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        gap: "4px",
        padding: "4px 0",
      }}
    >
      {/* Role label */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          paddingLeft: isUser ? 0 : "4px",
          paddingRight: isUser ? "4px" : 0,
        }}
      >
        {!isUser && (
          <div
            style={{
              width: "22px",
              height: "22px",
              borderRadius: "6px",
              background: "linear-gradient(135deg, #4f7ef8, #38c96e)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "11px",
              flexShrink: 0,
            }}
          >
            🧭
          </div>
        )}
        <span style={{ fontSize: "11.5px", color: "#6b7280", fontWeight: 600 }}>
          {isUser ? "나" : "정책나침반"}
        </span>
        <span style={{ fontSize: "11px", color: "#8a90a3" }}>{formatTimestamp(message.timestamp)}</span>
      </div>

      {/* Message bubble */}
      <div
        style={{
          maxWidth: "min(680px, 85%)",
          padding: isUser ? "10px 16px" : "14px 18px",
          background: isUser ? "#4f7ef8" : "#ffffff",
          borderRadius: isUser ? "16px 16px 4px 16px" : "4px 16px 16px 16px",
          border: isUser ? "none" : "1px solid #e2e5ec",
          color: isUser ? "#fff" : "#1f2430",
          fontSize: "14px",
          lineHeight: 1.7,
          wordBreak: "break-word",
        }}
      >
        {isUser ? (
          <span style={{ whiteSpace: "pre-wrap" }}>{message.content}</span>
        ) : (
          <div className="prose-chat">
            <Markdown>{message.content}</Markdown>
          </div>
        )}
      </div>

      {/* Policy cards carousel */}
      {!isUser && message.policyCards && message.policyCards.length > 0 && (
        <div style={{ width: "100%", maxWidth: "min(720px, 92%)", marginTop: "8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
            <span style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600 }}>
              추천 정책 {message.policyCards.length}건
            </span>
            <span style={{ fontSize: "11px", color: "#8a90a3" }}>→ 스크롤하여 더 보기</span>
          </div>
          <div
            className="policy-carousel"
            style={{
              display: "flex",
              gap: "12px",
              overflowX: "auto",
              paddingBottom: "8px",
              scrollSnapType: "x mandatory",
              WebkitOverflowScrolling: "touch",
            }}
          >
            {message.policyCards.map((card) => (
              <div
                key={card.id}
                style={{
                  flexShrink: 0,
                  width: "300px",
                  scrollSnapAlign: "start",
                }}
              >
                <PolicyCardComponent card={card} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
