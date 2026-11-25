# SwitchBot Keypad Manager

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://img.shields.io/github/actions/workflow/status/Aggro600/SwitchBot-Keypad-Manager/validate.yml?style=for-the-badge&label=validate)](https://github.com/Aggro600/SwitchBot-Keypad-Manager/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)](LICENSE)

**Manage the users of a SwitchBot Keypad Vision / Vision Pro directly from Home Assistant** – enroll and delete
fingerprints, faces, palms, PIN codes and NFC cards, see *who* unlocked *how*, and optionally let Home Assistant
**approve or deny every keypad unlock** with per-person rules – with an automatic fallback when Home Assistant is down.

[Deutsche Anleitung](README.de.md)

## Features

- **Enroll on the keypad from Home Assistant** – pick a person and what to enroll (10 fingers, face, left/right palm,
  random PIN, NFC card), press *Start enrollment*, go to the keypad. Slot and name are stored automatically.
- **Delete – always on the keypad *and* in the list**, also credentials that were not enrolled here. Unknown ones
  appear in the selection as *Unknown – Face 1*, *Unknown – PIN code 1* …; the integration finds the keypad slot itself
  (the keypad reports the remaining count on delete). **Delete everything** (press twice) clears keypad and list.
- **Edit** an entry – wrong person or wrong finger? Select the entry (person and finger are pre-filled), change them, press *Update entry*.
- **Time limits** for fingerprints, PIN codes and NFC cards (today, 24 h, 1 week, 1 month) and one-time PINs.
- **Who unlocked how** – "Anna (right thumb) via Fingerprint · 08:15" as a sensor, a logbook entry and an event
  for your automations.
- **Approval with fallback (optional)** – per person: *always*, *blocked*, *automation only*, *only 6:00–22:00*,
  *only weekdays 7:00–19:00*, *only when someone is home* – and **per credential** (overrides the person):
  *always open*, *blocked*, *automation only* (never opens, only triggers your automations), *time window*
  (up to 3 windows per entry, each from/until + every day / weekdays / weekend / a single day; opens if one matches),
  *only when someone is home*. If Home Assistant is not connected or does not answer
  within 2 s, the bridge falls back – by default it opens for every recognised credential, or (your choice) only
  for entries allowed for the fallback, or for nobody. The fallback policy is stored on the bridge.
- **Sync** – compares the counts stored on the keypad with the list and shows credentials without a name
  (e.g. created in the SwitchBot app). Assign them by unlocking once and pressing *Assign last unlock*. Unknown
  credentials have their own rule (also *automation only*) – e.g. "every unlock only runs my door script".
- **Keypad settings** – detection trigger and sensitivity, deactivation interval, fast unlock, voice and signal tone
  volume, voice language, key tone, backlight and brightness, lock button, tamper alarm, disable the keypad – the same
  as in the SwitchBot app.
- **Lock Ultra settings** (add the lock as a second entry) – motor speed (fast / normal / quiet), LED light, sound,
  auto-lock and its delay, pause auto-lock, half lock, the button on the lock (press, action), iBeacon and the whole
  **night mode** (from/until, speed, sound, lock at start, full/half lock, auto-lock, auto-unlock).
- **Selection only** – everything works with dropdowns and buttons; free text is optional (new person name).
- Several keypads: add the integration once per keypad.

## How it works

```
             enroll / delete / count (BLE, encrypted)
 Home Assistant ───────────────────────────────────────────► Keypad Vision (Pro)
   │  own connection: PySwitchbot + HA Bluetooth / proxies         │ unlock
   │                                                               ▼
   │  ◄── event: who/how ───  ESP32 "keypad bridge" (ESPHome) ◄────┘
   │  ─── approve / deny ──►        │ relays the unlock (BLE)
   │                                ▼
   │                         SwitchBot Lock (Ultra, Pro, …)
```

- **Credential management** uses the BLE commands of the keypad (documented in [docs/PROTOCOL.md](docs/PROTOCOL.md)).
  The integration has its **own connection**: a PySwitchbot `SwitchbotKeypadVision` device (the library that ships
  with Home Assistant) with the keypad's encryption key, talking through Home Assistant's Bluetooth – adapters and
  ESPHome Bluetooth proxies. The key is retrieved once with your SwitchBot account in the setup dialog (not stored)
  or entered manually. The SwitchBot integration is **not** needed.
- **Who unlocked** comes from the community ESPHome component
  [switchbot-keypad-bridge](https://github.com/pierluigizagaria/switchbot-keypad-bridge) by *pierluigizagaria*
  (not part of this repository). The keypad is linked to an ESP32 that impersonates a lock, reports every unlock
  with method and slot to Home Assistant and relays it to your real lock.

## Requirements

| | |
|---|---|
| Home Assistant | 2026.9 or newer (ships PySwitchbot with Keypad Vision support) |
| Keypad | SwitchBot Keypad Vision or Keypad Vision Pro, set up in the SwitchBot app (your SwitchBot account is used once to get the encryption key) |
| Bluetooth | a Bluetooth adapter or ESPHome Bluetooth proxy in range of the keypad |
| For "who unlocked" and approval | an ESP32 with the [switchbot-keypad-bridge](https://github.com/pierluigizagaria/switchbot-keypad-bridge) |

Enrolling and deleting works without the bridge; the last-unlock sensor, rules and approval need it.

## Installation

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/Aggro600/SwitchBot-Keypad-Manager` (type *Integration*).
2. Install **SwitchBot Keypad Manager**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → SwitchBot Keypad Manager*:
   - **Keypad** – picked from the keypads Home Assistant's Bluetooth currently sees (touch the keypad to wake it),
   - **Keypad bridge** – the ESPHome device name of your bridge (can be changed later in the options),
   - **People in the selection** – `person` entities offered in the *Person* dropdown.

### Keypad bridge configuration

The integration listens to the bridge event `esphome.switchbot_keypad_unlock`. Add `bridge` with the device name so
several bridges can be told apart:

```yaml
switchbot_keypad_bridge:
  id: keypad_bridge
  on_unlock:
    - homeassistant.event:
        event: esphome.switchbot_keypad_unlock
        data:
          bridge: keypad-bridge          # = ESPHome device name
          method: !lambda 'return method;'
          index: !lambda 'return to_string(index);'
```

Enable *Allow the device to perform Home Assistant actions* in the ESPHome device options, otherwise the event is blocked.

### Approval (optional)

Approval needs a bridge with the `approval:` option – proposed upstream in
[switchbot-keypad-bridge pull request #56](https://github.com/pierluigizagaria/switchbot-keypad-bridge/pull/56) (until it is
merged, use the branch `feat/home-assistant-approval` of [this fork](https://github.com/Aggro600/switchbot-keypad-bridge/tree/feat/home-assistant-approval)):

```yaml
api:
  actions:
    - action: approve_unlock          # method/index: a late answer never applies to another unlock
      variables:
        method: string
        index: int
      then:
        - lambda: 'id(keypad_bridge).approve(method, index);'
    - action: deny_unlock
      variables:
        method: string
        index: int
      then:
        - lambda: 'id(keypad_bridge).deny(method, index);'

switchbot_keypad_bridge:
  id: keypad_bridge
  approval:
    timeout: 2s        # no answer → fallback
    on_timeout: relay  # relay = open anyway (fallback), drop = stay locked
```

For the fallback policy add this action as well (needs the same bridge version):

```yaml
api:
  actions:
    - action: set_fallback
      variables:
        mode: int
        allow: string
      then:
        - lambda: 'id(keypad_bridge).set_fallback(mode, allow);'
```

Then switch on **Approve unlocks** and set the rules. With the switch off the integration approves every unlock
immediately, so a bridge with `approval:` never waits for its timeout.

**Keep a key or another way in** – it is an access system. Tips for the bridge:

- Set `reboot_timeout: 0s` for `api:` and `wifi:` in the bridge YAML. ESPHome's default reboots the ESP32 after
  15 minutes without Home Assistant or Wi-Fi – the fallback should keep running instead.
- The keypad only connects while it is used and disconnects a few seconds later; "not connected" is normal.
- After re-linking a keypad, power-cycle it once. While Home Assistant is connected, the bridge waits for its
answer (typically a few milliseconds); without a connection it relays immediately, exactly as without approval.
The keypad always shows success – it does not wait for the lock.

## Entities

| Entity | Purpose |
|---|---|
| `sensor.…_last_unlock` | "Anna (right thumb) via Fingerprint · 08:15" – attributes `person`, `detail`, `kind`, `slot`, `allowed` |
| `sensor.…_credentials` | number of entries – attributes `entries` (each with `label`, `rule`, `effective_rule`, `decision_now`, …), `list`, `on_keypad`, `unassigned`, `person_rules`, `unknown_rule`, `approval` |
| `sensor.…_status` | what to do / result of the last action |
| `select.…_person`, `…_what`, `…_validity` | choices for enrolling |
| `select.…_entry` | entry to delete |
| `select.…_rule_for_the_person`, `…_rule_for_unknown_credentials` | approval rules |
| `select.…_rule_for_the_entry`, `time.…_time_window_from` / `…_until`, `select.…_time_window_days` (+ `…_2_…`, `…_3_…`) | rule and time window of the entry selected in *Entry* |
| `switch.…_approve_unlocks` | approval on/off |
| `select.…_fallback_without_home_assistant`, `select.…_fallback_for_the_entry` | fallback policy: all / only allowed entries / nobody, and per entry |
| `text.…_new_person_optional` | optional: add a person by name |
| `button.…_start_enrollment`, `…_update_entry`, `…_delete_entry`, `…_assign_last_unlock`, `…_sync_with_keypad`, `…_cancel` | actions |
| `button.…_delete_everything_keypad_list` | deletes every credential on the keypad and the list – press twice within 15 s |

Entity IDs follow your Home Assistant language.

### Dashboard (copy & paste)

The complete user management as **one card** – including a live box *“What happens with this credential?”* that explains the effective rule of the selected entry in plain words, and a rule table: *Dashboard → Edit → Add card → Manual*, paste
[docs/dashboard-card.en.yaml](docs/dashboard-card.en.yaml) (English UI) or
[docs/dashboard-card.de.yaml](docs/dashboard-card.de.yaml) (German UI) and replace the entity prefix
(`front_door` / `keypad_haustur`) with yours. A larger sections view is in [docs/dashboard.yaml](docs/dashboard.yaml).

## Keypad and lock settings

The keypad entry also gets **configuration entities** for the keypad itself:

| Entity | Values |
|---|---|
| Detection trigger | auto / manual / schedule |
| Schedules 1–3 | on/off, days (every day, Mon–Fri, weekend, a single day; other combinations from the app are shown as *custom*), from/until – local time (the keypad stores UTC) |
| Detection sensitivity | low / medium / high |
| Deactivation interval | 5–60 s |
| Fast unlock | off / always on / auto |
| Voice prompt volume, signal tone volume | mute / low / medium / high |
| Key tone, lock button, keypad disabled, tamper alarm | on / off – *keypad disabled* means nobody can unlock at the keypad |
| Voice language | English / German (other languages: set them in the app) |
| Backlight, brightness | off / auto / on, 1–5 |

**Lock Ultra:** *Add integration → SwitchBot Keypad Manager → Lock Ultra – settings*, pick the lock and get its key
(SwitchBot account or manual). Entities: motor speed, LED light, sound, auto-lock + delay, pause auto-lock, half lock,
button on the lock (on, single/double press, lock only / unlock only / lock-unlock), iBeacon, night mode with all its
options. The lock force (soft/standard/strong) is intentionally not offered – the lock must be re-calibrated after it.

Settings are read on start, every 12 h, after every change and with the *Read settings* button; the Bluetooth
connection is closed right after each read/write. Every setting was verified on hardware (Keypad Vision Pro, Lock Ultra:
change, read back, restore). A sections example with both is in [docs/dashboard.yaml](docs/dashboard.yaml)
(English UI); a German settings view is in [docs/settings-view.de.yaml](docs/settings-view.de.yaml).

## Actions and event

- `switchbot_keypad_manager.enroll` – `person`, `what` (`thumb_right` … `little_left`, `face`, `palm_right`, `palm_left`,
  `pin_random`, `nfc_card`), `validity` (`permanent`, `today`, `24h`, `1w`, `1m`, `once`); returns the entry
  and, for PINs, the generated code.
- `switchbot_keypad_manager.update` – `entry_id`, optional `person` and `what` (the kind stays the same).
- `switchbot_keypad_manager.delete` – `entry_id` (from the `entries` attribute); deletes on the keypad and in the list.
- `switchbot_keypad_manager.sync`
- Event `switchbot_keypad_manager_unlocked` – `keypad`, `person`, `detail`, `kind`, `kind_text`, `slot`, `text`,
  `rule`, `decision` (`open`, `denied`, `event_only`), `allowed`, `time`.

```yaml
triggers:
  - trigger: event
    event_type: switchbot_keypad_manager_unlocked
    event_data:
      person: Anna
      kind: fingerprint
      detail: thumb_right
```

**Device triggers** – easiest way in the automation editor: *Add trigger → Device → (your keypad)*:
*Unlocked (any credential)* or *Unlocked with a specific credential* (pick person + finger/face/… from a list),
each with an optional *Outcome* (any / opened / denied / automation only).

A credential with the rule *automation only* never opens the door (approval must be on) – use it as a "button":

```yaml
triggers:
  - trigger: event
    event_type: switchbot_keypad_manager_unlocked
    event_data:
      decision: event_only
      detail: index_left
```

More examples (one combined automation vs. one automation per case): [docs/examples.yaml](docs/examples.yaml).

## Good to know

- **PIN codes** are random 6-digit codes, shown once as a notification and **not stored** anywhere.
- Credentials enrolled here are **not known to the SwitchBot app** (it keeps names in your SwitchBot account);
  names live in Home Assistant.
- **The keypad cannot list its credentials** (the list in the SwitchBot app lives in the SwitchBot cloud). Unknown
  credentials are therefore only known as a count; deleting one tries the keypad slots one by one until the count drops
  (PIN/card up to about a minute). Slots of known entries are never touched. The SwitchBot app may still show deleted ones.
- **Verified on hardware** (Keypad Vision Pro): enroll, unlock report and delete for PIN, NFC card, fingerprint, face
  and left/right palm – each checked against the keypad's own count.
- **NFC card:** hold the card to the keypad **within about 5 s** after *Enroll* – the keypad only listens that long.
- **Never delete an empty NFC slot by hand** (e.g. with your own raw commands): the keypad still counts its card
  counter down; below zero it reports 255 cards and refuses every new card until it is removed from and re-added to
  the SwitchBot app. The integration checks that a slot holds a card before it deletes it.
- **Upgrading from 1.x:** the integration asks once to re-authenticate (pick the keypad, get the key) – approval and
  unlock events keep working meanwhile. After the keypad is removed and re-added in the SwitchBot app it gets a new
  key; the integration then asks again.
- After the bridge restarts, some keypads stop talking to it until they are power-cycled once.
- SwitchBot may change the protocol with a firmware update.
- Face and palm recognition re-arm about 20 s after an unlock.
- Fingerprints need all captures until the keypad itself reports done; the integration waits for that and
  checks the keypad count afterwards.
- Too many failed attempts lock the keypad for a while (lockout alarm in the SwitchBot integration).
- Keypad slots and reported indexes differ (fingerprints are stored from slot 10, the bridge reports slot − 10);
  the integration stores both.

## Disclaimer

Not affiliated with SwitchBot / Wonderlabs. The protocol was observed from the official app's behaviour for
interoperability. Use at your own risk – this controls access to your home; keep a physical key or another way in.

## License

MIT – see [LICENSE](LICENSE).
