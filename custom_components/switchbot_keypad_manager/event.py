"""Doorbell event from the keypad's advertisements (the doorbell counter changes on every ring)."""
from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import callback

from .entity import AdvEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        return
    async_add_entities([Doorbell(entry.runtime_data)])


class Doorbell(AdvEntity, EventEntity):
    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["ring"]

    def __init__(self, manager):
        super().__init__(manager, "doorbell")
        self._seq = manager.adv.get("doorbell_seq")

    @callback
    def _updated(self) -> None:
        seq = self.manager.adv.get("doorbell_seq")
        if self._seq is not None and seq not in (None, 0, self._seq):
            self._trigger_event("ring")
        if seq is not None:
            self._seq = seq
        self.async_write_ha_state()
