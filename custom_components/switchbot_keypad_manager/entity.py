"""Common entity base."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class KeypadEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager, key: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, manager.entry.entry_id)}, name=manager.entry.title,
                                            manufacturer="SwitchBot Keypad Manager", model="Keypad Vision")

    async def async_added_to_hass(self) -> None:
        from . import SIGNAL
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL.format(self.manager.entry.entry_id), self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()


class AdvEntity(KeypadEntity):
    """Entity fed by the keypad's Bluetooth advertisements; unavailable until the first one arrived."""

    @property
    def available(self) -> bool:
        return bool(self.manager.adv)

    async def async_added_to_hass(self) -> None:
        from . import ADV_SIGNAL
        self.async_on_remove(async_dispatcher_connect(
            self.hass, ADV_SIGNAL.format(self.manager.entry.entry_id), self._updated))
