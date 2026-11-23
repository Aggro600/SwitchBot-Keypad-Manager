"""Time window (from / until) of the entry selected in 'Entry'."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity

from .const import DOMAIN
from .entity import KeypadEntity

DEFAULTS = {"from": "06:00", "until": "22:00"}


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WindowTime(manager, "from"), WindowTime(manager, "until")])


class WindowTime(KeypadEntity, TimeEntity):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, manager, which: str):
        super().__init__(manager, f"entry_{which}")
        self.which = which

    @property
    def native_value(self) -> time:
        entry = self.manager.selected_entry()
        value = ((entry or {}).get("window") or {}).get(self.which, DEFAULTS[self.which])
        hour, minute = (int(x) for x in value.split(":"))
        return time(hour, minute)

    async def async_set_value(self, value: time) -> None:
        await self.manager.set_entry_rule(**{self.which: value.strftime("%H:%M")})
