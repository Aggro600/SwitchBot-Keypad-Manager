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
| Fingerprint status | poll `570F530106` | done when `byte3 >> 4 == 3`, duplicate when `byte3 & 0x0F == 3` |
| Fingerprint validity | `570F520402 <slot> <from> <until>` | `01` |
| Fingerprint confirm | `570F520405 <slot>` | `01 <slot> …` |
| Fingerprint delete | `570F520403 <slot>` | `01 …` |
| **Face** end previous enrollment | `570F520506` | `01` |
| Face start | `570F5205010002` | `01 <slot>` |
| Face status | poll `570F530106` | done when `byte5 == 1` |
| Face confirm | `570F520505 <slot>` | `01 <slot> 01` |
| Face test (app only) | `570F52050701` / `570F52050702` | |
| Face delete | `570F520503 <slot>` | `01 …` |
| **Palm** | as face with group `06` (start and status verified, confirm `570F520605`, delete `570F520603` derived) | |
| **NFC** start | `570F520301 <type> 02` | `01 <slot>` |
| NFC status | poll `570F530106` | `byte2`: 1 ok, 2 failed, 3 duplicate, 4 timeout |
| NFC validity / confirm / delete | `570F520303 <slot> <from> <until>` / `570F520307 <slot>` / `570F520304 <slot>` | |

The `slot` equals the credential `index` reported by the keypad bridge on unlock.
