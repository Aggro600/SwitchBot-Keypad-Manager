# Keypad Vision BLE protocol (credential management)

Observed from the official SwitchBot app for interoperability; verified on a Keypad Vision Pro (firmware as of
November 2026). All commands are sent encrypted like other SwitchBot devices: Home Assistant's SwitchBot integration
(pySwitchbot) handles the framing – `57 | key_id | iv[0:2] | AES-128-CTR(key, iv)(command without 57)` after an IV
request `57 000000 0F2103 <key_id>`.

## Commands

Byte 4 (`570F52xx`) selects the credential group: `02` PIN, `03` NFC card, `04` fingerprint, `05` face, `06` palm.
`<slot>` is one byte, timestamps are 4-byte big-endian Unix seconds.

| Purpose | Command | Reply |
|---|---|---|
| Counts | `570F530100` | `01 pin nfc finger duress_pin duress_finger face palm` |
| Enrollment status (poll ~1/s) | `570F530106` | see below; `09` = busy |
| **PIN** add | `570F520202 <packet> FF <type> <len> <digits…>` (type 00 permanent, 01 time-limited, 02 one-time; payload split into 11-byte packets, `<packet>` = total<<4 \| index) | `01 10 <slot>` |
| PIN validity | `570F520203 <slot> <from> <until>` | `01` |
| PIN delete | `570F520205 <slot>` | `01 …` |
| **Fingerprint** start | `570F520401 <type> 02 <duress>` (type 00 permanent, 01 time-limited) | `01 <slot>` |
| Fingerprint status | poll `570F530106` | `byte3`: high nibble = captures so far, low nibble = result (0 running, 1 complete, 3 already enrolled). Observed `10 → 20 → 30 → 31`; only `31` is complete. `09` while scanning. The register keeps the last result, so ignore a stale value read before the first capture. |
| Fingerprint validity | `570F520402 <slot> <from> <until>` | `01` |
| Fingerprint confirm | `570F520405 <slot>` | `01 <slot> …` |
| Fingerprint delete | `570F520403 <slot>` | `01 …` |
| **Face** end previous enrollment | `570F520506` | `01` |
| Face start | `570F5205010002` | `01 <slot>` |
| Face status | poll `570F530106` | done when `byte5 == 1` |
| Face confirm | `570F520505 <slot>` | `01 <slot> 01` |
| Face test (app only) | `570F52050701` / `570F52050702` | |
| Face delete | `570F520503 <slot>` | `01 …` |
| **Palm** | as face with group `06`: end `570F520606`, start `570F5206010002`, status byte5 == 1, confirm `570F520605 <slot>`, delete `570F520603 <slot>` (verified) | |
| **NFC** start | `570F520301 <type> 02` | `01 <slot>` |
| NFC status | poll `570F530106` | `byte2`: 1 ok, 2 failed, 3 duplicate, 4 timeout |
| NFC validity / confirm / delete | `570F520303 <slot> <from> <until>` / `570F520307 <slot>` / `570F520304 <slot>` | |

Delete replies carry the remaining count: fingerprint/face/palm `01 <count>`, PIN `01 <count> …`, NFC `01`
(use the count command). Deleting an empty slot succeeds without changing the count.

NFC: the keypad listens for a card only ~5 s after the start command (status byte2 `04` = no card yet; keep polling,
like the SwitchBot app, until `01` read or `03` already enrolled). `570F530301 <slot>` tells whether a slot holds a card
(`01 …` yes, `02` no). **Deleting an unconfirmed/empty NFC slot that was allocated by a start command still decrements
the card counter** – it underflows to `FF`, and every start is answered with `10` until the keypad is removed and
re-added in the SwitchBot app. Never delete an NFC slot without checking it first.

Basic queries answered with `04`/`05` mean the encryption key is not valid (e.g. after the keypad was re-added).

No list: on a Keypad Vision Pro the index-table and cursor queries of older keypads (`570F530200`, `…0300`, `…0400`,
`570F520206/0305/0404` + `570F5302 05/06`, `…0303–0306`, `…0402/0403`) all answer `05`. The credential list shown in
the SwitchBot app lives in the SwitchBot cloud (the official cloud API only exposes PIN codes). To delete a credential
of unknown slot, try the slots one by one and watch the count.

Slots: fingerprints are stored from keypad slot 10 on (first fingerprint = 10). On unlock the keypad sends the slot and
the keypad bridge reports `slot - 10` for slots ≥ 10 (faces use slots below 10 and are reported unchanged).
After too many failed attempts the keypad locks itself for a while (lockout alarm in the SwitchBot integration).
