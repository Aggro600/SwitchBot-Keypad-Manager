"""Sensors: last unlock, credentials, status."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LastUnlock(manager), Credentials(manager), Status(manager)])


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
        if last.get("allowed") is False:
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
            "entries": [{"id": e["id"], "person": e["person"], "detail": e.get("detail", ""), "kind": e["kind"],
                         "slot": e["slot"], "keypad_slot": e.get("keypad_slot"), "valid_until": e.get("valid_until"), "source": e.get("source")}
                        for e in ordered],
            "list": "\n".join(m.label(e) for e in ordered),
            "on_keypad": {m.t["kind"].get(k, k): n for k, n in m.counts.items()},
            "unassigned": m.unassigned_counts(),
        }


class Status(KeypadEntity, SensorEntity):
    _attr_icon = "mdi:information-outline"

    def __init__(self, manager):
        super().__init__(manager, "status")

    @property
    def native_value(self):
        return self.manager.status[:255]
