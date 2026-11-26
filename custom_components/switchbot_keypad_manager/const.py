"""Constants for SwitchBot Keypad Manager."""
DOMAIN = "switchbot_keypad_manager"

CONF_KEYPAD_ENTRY = "keypad_entry"   # 1.x only: config entry of the SwitchBot integration (replaced by own connection)
CONF_ADDRESS = "address"             # Bluetooth address of the keypad
CONF_MODEL = "model"                 # "Keypad Vision" / "Keypad Vision Pro" (PySwitchbot model name)
CONF_KEY_ID = "key_id"
CONF_ENCRYPTION_KEY = "encryption_key"
KEYPAD_MODELS = ("Keypad Vision", "Keypad Vision Pro")
LOCK_MODELS = ("Lock Ultra",)          # lock settings (verified on a Lock Ultra)
CONF_TYPE = "type"                   # "lock" for a lock-settings entry, missing = keypad
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
                "face": (FACE, ""), "palm_right": (PALM, "palm_right"), "palm_left": (PALM, "palm_left"), "pin_custom": (PIN, ""), "nfc_card": (NFC, "")}

VALIDITY_OPTIONS = ["permanent", "today", "24h", "1w", "1m", "once"]
RULE_OPTIONS = ["always", "blocked", "event_only", "daytime", "weekdays", "someone_home"]
ENTRY_RULE_OPTIONS = ["inherit", "always", "blocked", "event_only", "time_window", "someone_home"]
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYS_OPTIONS = ["all", "weekdays", "weekend", *DAY_NAMES, "off"]
WINDOWS = 3                                   # time windows per entry
WINDOW_DEFAULT = {"from": "06:00", "until": "22:00", "days": "all"}
NO_ENTRY = "none"
FALLBACK_OPTIONS = ["all", "allowed", "none"]
ENTRY_FALLBACK_OPTIONS = ["allowed", "blocked"]
