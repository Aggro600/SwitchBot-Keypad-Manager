"""Optional: add a new person by name (the selection stays the normal way)."""
from __future__ import annotations

from homeassistant.components.text import TextEntity

from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("text", entry.runtime_data))
        return
    m = entry.runtime_data
    async_add_entities([NewPerson(m)])


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
