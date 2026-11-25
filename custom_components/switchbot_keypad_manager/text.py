"""Optional: add a new person by name (the selection stays the normal way)."""
from __future__ import annotations

import re

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("text", hass.data[DOMAIN][entry.entry_id]))
        return
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NewPerson(m), PinCode(m)])


class NewPerson(KeypadEntity, TextEntity):
    _attr_icon = "mdi:account-plus-outline"
    _attr_native_max = 40
    _attr_native_value = ""

    def __init__(self, manager):
        super().__init__(manager, "new_person")

    async def async_set_value(self, value: str) -> None:
        name = value.strip()
        if name:
            if name not in self.manager.persons():
                self.manager.extra_persons.append(name)
            self.manager.choice["person"] = name
            await self.manager.save()
        self._attr_native_value = ""
        self.async_write_ha_state()


class PinCode(KeypadEntity, TextEntity):
    """Own PIN for the next "PIN code (own)" enrollment. Kept in memory only and cleared after the enrollment;
    the state only shows asterisks, so the PIN never ends up in the recorder."""
    _attr_icon = "mdi:dialpad"
    _attr_mode = TextMode.PASSWORD
    _attr_native_min = 0
    _attr_native_max = 12

    def __init__(self, manager):
        super().__init__(manager, "pin_code")

    @property
    def native_value(self) -> str:
        return "*" * len(self.manager.pin)

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        if value and set(value) != {"*"}:
            if not re.fullmatch(r"\d{6,12}", value):
                raise HomeAssistantError(self.manager.t["err_pin"])
            self.manager.pin = value
            if self.manager.choice["what"] != "pin_custom":
                self.manager.choice["what"] = "pin_custom"
                self.manager.notify_entities()
        elif not value:
            self.manager.pin = ""
        self.async_write_ha_state()
