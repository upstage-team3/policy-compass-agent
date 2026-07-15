import assert from "node:assert/strict"
import test from "node:test"

import { generateUuidV4, isUuidV4 } from "./uuid.ts"

test("uses native randomUUID when the browser exposes it", () => {
  const expected = "5aab327b-6412-4c74-a118-c69f45bbf879"
  const cryptoSource = {
    randomUUID: () => expected,
    getRandomValues: () => {
      throw new Error("getRandomValues should not be called")
    },
  }

  assert.equal(generateUuidV4(cryptoSource), expected)
})

test("creates an RFC 4122 UUIDv4 when randomUUID is unavailable on HTTP", () => {
  const cryptoSource = {
    getRandomValues: (bytes) => {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = index
      }
      return bytes
    },
  }

  const generated = generateUuidV4(cryptoSource)

  assert.equal(generated, "00010203-0405-4607-8809-0a0b0c0d0e0f")
  assert.equal(isUuidV4(generated), true)
})

test("rejects legacy non-UUID chat identifiers", () => {
  assert.equal(isUuidV4("md5x7abc-qwerty12"), false)
  assert.equal(isUuidV4("00000000-0000-0000-0000-000000000000"), false)
})
