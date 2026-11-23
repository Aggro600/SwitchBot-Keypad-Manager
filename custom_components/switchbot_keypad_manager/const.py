"""Constants for SwitchBot Keypad Manager."""
DOMAIN = "switchbot_keypad_manager"

CONF_KEYPAD_ENTRY = "keypad_entry"   # config entry of the SwitchBot integration (Keypad Vision / Pro)
CONF_BRIDGE = "bridge"               # "bridge" value in the keypad bridge event (ESPHome device name)
CONF_PERSONS = "persons"             # person.* entities offered in the person selection

BRIDGE_UNLOCK_EVENT = "esphome.switchbot_keypad_unlock"
UNLOCKED_EVENT = f"{DOMAIN}_unlocked"

# Credential kinds, same names as the bridge "method"
PIN, NFC, FINGERPRINT, FACE, PALM = "pin", "nfc", "fingerprint", "face", "palm"
KINDS = (PIN, NFC, FINGERPRINT, FACE, PALM)

FINGERS = [f"{finger}_{side}" for side in ("right", "left")
           for finger in ("thumb", "index", "middle", "ring", "little")]
# Option of the "what" select -> (kind, detail)
WHAT_OPTIONS = {**{f: (FINGERPRINT, f) for f in FINGERS},
                "face": (FACE, ""), "palm": (PALM, ""), "pin_random": (PIN, ""), "nfc_card": (NFC, "")}

VALIDITY_OPTIONS = ["permanent", "today", "24h", "1w", "1m", "once"]
RULE_OPTIONS = ["always", "blocked", "daytime", "weekdays", "someone_home"]
ENTRY_RULE_OPTIONS = ["inherit", "always", "blocked", "event_only", "time_window", "someone_home"]
DAYS_OPTIONS = ["all", "weekdays", "weekend"]
NO_ENTRY = "none"
