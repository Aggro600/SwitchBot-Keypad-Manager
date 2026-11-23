"""Time windows (from / until) of the entry selected in 'Entry'."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity

from .const import DOMAIN, WINDOWS
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WindowTime(manager, which, number) for number in range(1, WINDOWS + 1)
                        for which in ("from", "until")])


class WindowTime(KeypadEntity, TimeEntity):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, manager, which: str, number: int):
        super().__init__(manager, f"entry_{which}" if number == 1 else f"entry_{which}_{number}")
        self.which = which
        self.number = number

    @property
    def available(self) -> bool:
        """Only meaningful when the selected entry uses the rule 'time window' (otherwise ignored)."""
        entry = self.manager.selected_entry()
        return entry is not None and (entry.get("rule") or "inherit") == "time_window"

    @property
    def native_value(self) -> time:
        entry = self.manager.selected_entry()
        windows = self.manager.windows(entry) if entry else [{"from": "06:00", "until": "22:00"}] * WINDOWS
        hour, minute = (int(x) for x in windows[self.number - 1][self.which].split(":"))
        return time(hour, minute)

    async def async_set_value(self, value: time) -> None:
        await self.manager.set_entry_rule(window=self.number, **{self.which: value.strftime("%H:%M")})
