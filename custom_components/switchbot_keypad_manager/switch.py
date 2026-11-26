"""Switch: approve/deny keypad unlocks through the bridge."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("switch", entry.runtime_data))
        return
    from .keypad_settings import setting_entities
    async_add_entities(setting_entities("switch", entry.runtime_data))
    async_add_entities([Approval(entry.runtime_data)])


class Approval(KeypadEntity, SwitchEntity):
    _attr_icon = "mdi:shield-lock"

    def __init__(self, manager):
        super().__init__(manager, "approval")

    @property
    def is_on(self):
        return self.manager.approval

    async def async_turn_on(self, **kwargs) -> None:
        self.manager.approval = True
        await self.manager.save()

    async def async_turn_off(self, **kwargs) -> None:
        self.manager.approval = False
        await self.manager.save()
