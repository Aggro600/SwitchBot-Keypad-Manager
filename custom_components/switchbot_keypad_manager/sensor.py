"""Sensors: last unlock, credentials, status."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.util import dt as dt_util

from .entity import AdvEntity, KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("sensor", entry.runtime_data))
        return
    manager = entry.runtime_data
    async_add_entities([LastUnlock(manager), Credentials(manager), Status(manager), *adv_sensors(manager)])


class LastUnlock(KeypadEntity, SensorEntity):
    _attr_icon = "mdi:lock-open-account"

    def __init__(self, manager):
        super().__init__(manager, "last_unlock")

    @property
    def native_value(self):
        last = self.manager.last
        if not last:
            return None
        when = dt_util.parse_datetime(last["time"]).strftime("%d.%m. %H:%M")
        text = f"{last['text']} {self.manager.t['via']} {last['kind_text']} · {when}"
        if last.get("decision") == "event_only":
            text += f" ({self.manager.t['event_only']})"
        elif last.get("allowed") is False:
            text += f" ({self.manager.t['denied']})"
        return text[:255]

    @property
    def extra_state_attributes(self):
        return dict(self.manager.last)


class Credentials(KeypadEntity, SensorEntity):
    _attr_icon = "mdi:account-key"

    def __init__(self, manager):
        super().__init__(manager, "credentials")

    @property
    def native_value(self):
        return len(self.manager.entries)

    @property
    def extra_state_attributes(self):
        m = self.manager
        ordered = sorted(m.entries, key=lambda e: (e["person"], e["kind"], e["slot"]))
        return {
            "entries": [{"id": e["id"], "label": m.label(e), "effective_rule": m.decide(e)[1], "decision_now": m.decide(e)[0],
                         "person": e["person"], "detail": e.get("detail", ""), "kind": e["kind"],
                         "slot": e["slot"], "keypad_slot": e.get("keypad_slot"), "rule": e.get("rule") or "inherit",
                         "windows": [dict(w) for w in m.windows(e)], "fallback": e.get("fallback", True), "valid_until": e.get("valid_until"), "source": e.get("source")}
                        for e in ordered],
            "list": "\n".join(m.label(e) for e in ordered),
            "on_keypad": {m.t["kind"].get(k, k): n for k, n in m.counts.items()},
            "unassigned": m.unassigned_counts(),
            "pending": {m.t["kind"][k]: v["person"] for k, v in m.pending.items()},
            "fallback_mode": m.fallback_mode,
            "person_rules": dict(m.rules),
            "unknown_rule": m.unknown_rule,
            "approval": m.approval,
        }


class Status(KeypadEntity, SensorEntity):
    _attr_icon = "mdi:information-outline"

    def __init__(self, manager):
        super().__init__(manager, "status")

    @property
    def native_value(self):
        return self.manager.status[:255]


def adv_sensors(manager) -> list:
    """From the keypad's advertisements: battery, signal and (Vision Pro: radar, Vision: PIR) trigger values."""
    pro = "Pro" in manager.entry.data.get("model", "Keypad Vision Pro")
    keys = ["radar_triggered_level", "radar_triggered_distance"] if pro else ["pir_triggered_level"]
    return [Battery(manager), Rssi(manager), *[AdvValue(manager, k) for k in keys]]


class Battery(AdvEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, manager):
        super().__init__(manager, "battery")

    @property
    def native_value(self):
        return self.manager.adv.get("battery")


class Rssi(AdvEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, manager):
        super().__init__(manager, "rssi")

    @property
    def native_value(self):
        return self.manager.rssi


class AdvValue(AdvEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager, key):
        super().__init__(manager, key)
        self.key = key

    @property
    def native_value(self):
        return self.manager.adv.get(self.key)
