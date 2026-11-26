"""Binary sensors from the keypad's advertisements: charging and alarms."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import AdvEntity

SENSORS = {
    "battery_charging": BinarySensorDeviceClass.BATTERY_CHARGING,
    "lockout_alarm": BinarySensorDeviceClass.PROBLEM,
    "tamper_alarm": BinarySensorDeviceClass.TAMPER,
    "duress_alarm": BinarySensorDeviceClass.SAFETY,
    "low_temperature": BinarySensorDeviceClass.COLD,
    "high_temperature": BinarySensorDeviceClass.HEAT,
}


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        return
    async_add_entities(AdvBinary(entry.runtime_data, key, cls) for key, cls in SENSORS.items())


class AdvBinary(AdvEntity, BinarySensorEntity):
    def __init__(self, manager, key, device_class):
        super().__init__(manager, key)
        self.key = key
        self._attr_device_class = device_class

    @property
    def is_on(self):
        return self.manager.adv.get(self.key)
