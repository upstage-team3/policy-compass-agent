import assert from "node:assert/strict"
import test from "node:test"

import {
  CHAT_STORAGE_KEY,
  PROFILE_DEFAULTS_STORAGE_KEY,
  clearProfileDefaults,
  detectSensitiveData,
  loadChatState,
  loadProfileDefaults,
  privacyGuardMessage,
  sanitizeStoredText,
  saveChatState,
  saveProfileDefaults,
} from "./chatStorage.ts"

class MemoryStorage {
  constructor() {
    this.items = new Map()
  }

  getItem(key) {
    return this.items.get(key) ?? null
  }

  setItem(key, value) {
    this.items.set(key, String(value))
  }

  removeItem(key) {
    this.items.delete(key)
  }
}

function useEmptyStorage() {
  const localStorage = new MemoryStorage()
  globalThis.window = { localStorage }
  return localStorage
}

function message(id, content) {
  return {
    id,
    role: "user",
    content,
    timestamp: new Date("2026-07-13T10:00:00Z"),
  }
}

function chat(id, messages = [message(`${id}-message`, "서울 청년정책")]) {
  return {
    id,
    title: `채팅 ${id}`,
    messages,
    createdAt: new Date("2026-07-13T10:00:00Z"),
  }
}

test("save/load restores dates and the active backend session id", () => {
  useEmptyStorage()
  saveChatState({ chats: [chat("session-1")], activeChatId: "session-1" })

  const restored = loadChatState()
  assert.equal(restored.activeChatId, "session-1")
  assert.equal(restored.chats[0].messages[0].content, "서울 청년정책")
  assert.ok(restored.chats[0].createdAt instanceof Date)
  assert.ok(restored.chats[0].messages[0].timestamp instanceof Date)
})

test("sensitive identifiers are masked before browser persistence", () => {
  const localStorage = useEmptyStorage()
  const sensitive =
    "주민번호는 900101-1234567이고 카드는 1234 5678 9012 3456이야"
  saveChatState({
    chats: [chat("session-2", [message("message-2", sensitive)])],
    activeChatId: "session-2",
  })

  const raw = localStorage.getItem(CHAT_STORAGE_KEY)
  assert.equal(raw.includes("900101-1234567"), false)
  assert.equal(raw.includes("1234 5678 9012 3456"), false)
  assert.match(raw, /민감정보 삭제/)
  assert.equal(sanitizeStoredText(sensitive).includes("900101-1234567"), false)
})

test("sensitive identifiers are detected before network submission", () => {
  const residentId = "991332-1234567"
  const phone = "010-1234-5678"
  const email = "person@example.com"

  assert.deepEqual(detectSensitiveData(residentId), ["주민등록번호·외국인등록번호 형태"])
  assert.deepEqual(detectSensitiveData(phone), ["전화번호 형태"])
  assert.deepEqual(detectSensitiveData(email), ["이메일 주소"])

  const reply = privacyGuardMessage(detectSensitiveData(residentId))
  assert.match(reply, /전송과 정책 검색을 중단/)
  assert.equal(reply.includes(residentId), false)
})

test("retention limits keep the newest 20 chats and 50 messages per chat", () => {
  useEmptyStorage()
  const messages = Array.from({ length: 55 }, (_, index) =>
    message(`message-${index}`, String(index)),
  )
  const chats = Array.from({ length: 22 }, (_, index) =>
    chat(`session-${index}`, messages),
  )

  saveChatState({ chats, activeChatId: "session-0" })
  const restored = loadChatState()

  assert.equal(restored.chats.length, 20)
  assert.equal(restored.chats[0].messages.length, 50)
  assert.equal(restored.chats[0].messages[0].content, "5")
})

test("invalid storage falls back without crashing", () => {
  const localStorage = useEmptyStorage()
  localStorage.setItem(CHAT_STORAGE_KEY, "{broken-json")
  assert.equal(loadChatState(), null)
})

test("policy score and evidence coverage survive browser persistence", () => {
  useEmptyStorage()
  const policyCard = {
    id: "policy-1",
    name: "성남 창업지원",
    target: "예비창업자",
    amount: "사업화 지원",
    period: "상시 ~ 상시",
    reason: "요청 지역과 일치해요.",
    ministry: "테스트 기관",
    category: "창업",
    region: "경기",
    scope: "exact",
    matchScore: 0.45,
    evidenceCoverage: 0.45,
  }
  const assistantMessage = {
    id: "message-policy",
    role: "assistant",
    content: "추천 결과",
    timestamp: new Date("2026-07-14T10:00:00Z"),
    policyCards: [policyCard],
  }

  saveChatState({
    chats: [chat("session-policy", [assistantMessage])],
    activeChatId: "session-policy",
  })
  const restored = loadChatState()
  const restoredCard = restored.chats[0].messages[0].policyCards[0]

  assert.equal(restoredCard.matchScore, 0.45)
  assert.equal(restoredCard.evidenceCoverage, 0.45)
  assert.equal(restoredCard.scope, "exact")
})

test("age and region defaults survive across separate chat sessions", () => {
  const localStorage = useEmptyStorage()

  saveProfileDefaults({ age: 24, region: "경기" })
  const restored = loadProfileDefaults()

  assert.deepEqual(restored, { age: 24, region: "경기" })
  assert.match(localStorage.getItem(PROFILE_DEFAULTS_STORAGE_KEY), /"age":24/)
})

test("clearing all local data also removes profile defaults", () => {
  const localStorage = useEmptyStorage()
  saveProfileDefaults({ age: 25, region: "서울" })

  clearProfileDefaults()

  assert.equal(localStorage.getItem(PROFILE_DEFAULTS_STORAGE_KEY), null)
  assert.deepEqual(loadProfileDefaults(), {})
})
