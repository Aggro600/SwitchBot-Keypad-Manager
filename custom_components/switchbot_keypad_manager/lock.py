"""Settings of a SwitchBot Lock Ultra (motor speed, light, sound, button, auto-lock, half lock, night mode, iBeacon).

The lock is a second kind of config entry of this integration (type "lock") with its own Bluetooth connection, like
the keypad. Settings are read on start, every 12 h, on the refresh button and right after every change; the connection
is dropped right after each read/write so the lock's battery is spared.

Commands (verified on a Lock Ultra, read back after every write):
  read  570F4F0401  basic: byte1 bit7 light, bit6 sound, bit3 button on, bit2 double press, bits1-0 button action;
                    byte3 bits1-0 motor speed (0 fast, 1 normal, 2 quiet); byte5 bit6 half lock enabled
  write 570F4E0401 00 <mask> <value> <speed|FF>   (mask 80 light, 40 sound, 0E/08 button; mask 00 + speed)
  r/w   570F4F0402 / 570F4E0402 00 <on<<7 | seconds> <minutes>   auto-lock after the door closed
  r/w   570F4F0404 / 570F4E0404 00 <on<<7>                       pause auto-lock
  write 570F4E040C00 <0|1>                                        half lock enabled
  r/w   570F4F8203 / 570F4E8203 <0|1>                             iBeacon advertising
  r/w   570F4F0700 / 570F4E0700 <info> <sh> <sm> <eh> <em> <as> <am>   night mode
        info: bit7 lock at night start, bit6 auto-unlock allowed, bit5 auto-lock, bits4-3 speed, bit2 sound,
        bit1 night mode on, bit0 lock position (0 full, 1 half)
"""
from __future__ import annotations

import asyncio
from datetime import time as dtime, timedelta
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import Entity, EntityCategory
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import CONF_ADDRESS, CONF_ENCRYPTION_KEY, CONF_KEY_ID, CONF_MODEL, DOMAIN

_LOGGER = logging.getLogger(__name__)

SPEEDS = ["fast", "normal", "quiet"]
BUTTON_ACTIONS = ["lock_only", "unlock_only", "toggle"]
BUTTON_TRIGGERS = ["single", "double"]
LOCK_POSITIONS = ["full", "half"]
LOCK_SIGNAL = f"{DOMAIN}_lock_{{}}"


class LockError(HomeAssistantError):
    """Bluetooth or protocol error talking to the lock."""


class LockSettings:
    """Reads and writes the settings of one lock."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address = entry.data[CONF_ADDRESS]
        self.lock = asyncio.Lock()
        self.s: dict = {}           # parsed settings
        self.available = False
        self._dev = None
        self._unsubs: list = []

    # ---------- connection ----------
    def _device(self):
        from homeassistant.components import bluetooth
        from switchbot import SwitchbotLock, SwitchbotModel, parse_advertisement_data
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        ble = info.device if info else bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble is None:
            raise LockError("Lock is not in Bluetooth range (no adapter or proxy sees it)")
        if self._dev is None:
            class RawLock(SwitchbotLock):
                async def raw_command(self, hexcmd: str) -> bytes | None:
                    return await self._send_command(hexcmd)

                async def release(self) -> None:
                    await self._execute_disconnect()

            self._dev = RawLock(ble, self.entry.data[CONF_KEY_ID], self.entry.data[CONF_ENCRYPTION_KEY],
                                model=SwitchbotModel(self.entry.data[CONF_MODEL]))
        elif info is not None and (adv := parse_advertisement_data(info.device, info.advertisement)) is not None:
            self._dev.update_from_advertisement(adv)
        return self._dev

    async def _cmd(self, hexcmd: str) -> bytes:
        last = None
        for i in range(4):
            try:
                reply = await self._device().raw_command(hexcmd)
            except LockError:
                raise
            except Exception as err:  # noqa: BLE001 - any Bluetooth error
                _LOGGER.debug("Lock command %s failed: %s", hexcmd[:12], err)
                reply = None
            if reply and reply[0] in (0x01, 0x06, 0x0E):
                return reply
            last = reply
            await asyncio.sleep(1 + i)   # e.g. 04 right after a change: the lock is still busy
        if last:
            raise LockError(f"Lock rejected {hexcmd[:12]} ({last.hex()})")
        raise LockError("Lock does not respond (out of range?)")

    async def _release(self) -> None:
        if self._dev is not None:
            try:
                await self._dev.release()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Disconnect failed: %s", err)

    # ---------- read ----------
    async def refresh(self) -> None:
        async with self.lock:
            try:
                await self._read_all()
                self.available = True
            except LockError as err:
                self.available = False
                _LOGGER.warning("%s: settings not readable: %s", self.entry.title, err)
            finally:
                await self._release()
        async_dispatcher_send(self.hass, LOCK_SIGNAL.format(self.entry.entry_id))

    async def _read_all(self) -> None:
        b = await self._cmd("570F4F0401")
        s = {"light": bool(b[1] & 0x80), "sound": bool(b[1] & 0x40), "button": bool(b[1] & 0x08),
             "button_trigger": BUTTON_TRIGGERS[1 if b[1] & 0x04 else 0],
             "button_action": BUTTON_ACTIONS[min(b[1] & 0x03, 2)],
             "speed": SPEEDS[min(b[3] & 0x03, 2)] if len(b) > 3 else "fast",
             "half_lock": bool(b[5] & 0x40) if len(b) > 5 else False}
        a = await self._cmd("570F4F0402")
        s["auto_lock"] = bool(a[1] & 0x80)
        s["auto_lock_delay"] = (a[2] if len(a) > 2 else 0) * 60 + (a[1] & 0x3F)
        p = await self._cmd("570F4F0404")
        s["pause_auto_lock"] = bool(p[1] & 0x80) if len(p) > 1 else False
        i = await self._cmd("570F4F8203")
        s["ibeacon"] = bool(i[1] & 0x01) if len(i) > 1 else False
        n = await self._cmd("570F4F0700")
        if len(n) >= 8:
            info = n[1]
            s["night"] = {"on": bool(info & 0x02), "lock_position": LOCK_POSITIONS[info & 0x01],
                          "sound": bool(info & 0x04), "speed": SPEEDS[min((info & 0x18) >> 3, 2)],
                          "auto_lock": bool(info & 0x20), "auto_unlock": bool(info & 0x40),
                          "lock_at_start": bool(info & 0x80), "start": (n[2] % 24, n[3] % 60),
                          "end": (n[4] % 24, n[5] % 60), "auto_lock_delay": n[7] * 60 + n[6]}
        self.s = s

    # ---------- write ----------
    async def write(self, hexcmd: str) -> None:
        async with self.lock:
            try:
                await self._cmd(hexcmd)
                await self._read_all()
                self.available = True
            finally:
                await self._release()
        async_dispatcher_send(self.hass, LOCK_SIGNAL.format(self.entry.entry_id))

    async def set_basic(self, key: str, value) -> None:
        s = self.s
        if key == "light":
            cmd = f"570F4E04010080{0x80 if value else 0:02X}FF"
        elif key == "sound":
            cmd = f"570F4E04010040{0x40 if value else 0:02X}FF"
        elif key == "speed":
            cmd = f"570F4E0401000000{SPEEDS.index(value):02X}"
        elif key in ("button", "button_trigger", "button_action"):
            on = value if key == "button" else s.get("button", True)
            trig = value if key == "button_trigger" else s.get("button_trigger", "single")
            act = value if key == "button_action" else s.get("button_action", "toggle")
            if on:
                byte = 0x08 | (BUTTON_TRIGGERS.index(trig) << 2) | BUTTON_ACTIONS.index(act)
                cmd = f"570F4E0401000E{byte:02X}FF"
            else:
                cmd = "570F4E0401000800FF"
        elif key == "half_lock":
            cmd = f"570F4E040C00{1 if value else 0:02X}"
        elif key == "pause_auto_lock":
            cmd = f"570F4E040400{0x80 if value else 0:02X}"
        elif key == "ibeacon":
            cmd = f"570F4E8203{1 if value else 0:02X}"
        elif key in ("auto_lock", "auto_lock_delay"):
            on = value if key == "auto_lock" else s.get("auto_lock", False)
            delay = int(value if key == "auto_lock_delay" else s.get("auto_lock_delay", 30))
            cmd = f"570F4E040200{(0x80 if on else 0) | (delay % 60):02X}{min(delay // 60, 255):02X}"
        else:
            raise HomeAssistantError(f"Unknown setting {key}")
        await self.write(cmd)

    async def set_night(self, key: str, value) -> None:
        n = dict(self.s.get("night") or {})
        if not n:
            raise HomeAssistantError("Night mode settings not read yet")
        n[key] = value
        info = ((0x80 if n["lock_at_start"] else 0) | (0x40 if n["auto_unlock"] else 0) | (0x20 if n["auto_lock"] else 0)
                | (SPEEDS.index(n["speed"]) << 3) | (0x04 if n["sound"] else 0) | (0x02 if n["on"] else 0)
                | LOCK_POSITIONS.index(n["lock_position"]))
        delay = int(n["auto_lock_delay"])
        cmd = (f"570F4E0700{info:02X}{n['start'][0]:02X}{n['start'][1]:02X}{n['end'][0]:02X}{n['end'][1]:02X}"
               f"{delay % 60:02X}{min(delay // 60, 255):02X}")
        await self.write(cmd)

    # ---------- lifecycle ----------
    def start(self) -> None:
        async def _refresh(_now=None) -> None:
            await self.refresh()
        self._unsubs.append(async_call_later(self.hass, 20, _refresh))
        self._unsubs.append(async_track_time_interval(self.hass, _refresh, timedelta(hours=12)))

    def stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()


# ---------------------------------------------------------------- entities
class LockEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ls: LockSettings, key: str, icon: str) -> None:
        self.ls = ls
        self.key = key
        self._attr_unique_id = f"{ls.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ls.entry.entry_id)}, name=ls.entry.title,
                                            manufacturer="SwitchBot Keypad Manager", model=ls.entry.data[CONF_MODEL])

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, LOCK_SIGNAL.format(self.ls.entry.entry_id),
                                                      self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.ls.available and self._value() is not None

    def _value(self):
        if self.key.startswith("night_"):
            return (self.ls.s.get("night") or {}).get(self.key[6:])
        return self.ls.s.get(self.key)

    async def _set(self, value) -> None:
        if self.key.startswith("night_"):
            await self.ls.set_night(self.key[6:], value)
        else:
            await self.ls.set_basic(self.key, value)


class LockSwitch(LockEntity, SwitchEntity):
    @property
    def is_on(self):
        return self._value()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class LockSelect(LockEntity, SelectEntity):
    def __init__(self, ls, key, icon, options) -> None:
        super().__init__(ls, key, icon)
        self._attr_options = options

    @property
    def current_option(self):
        return self._value()

    async def async_select_option(self, option: str) -> None:
        await self._set(option)


class LockDelay(LockEntity, NumberEntity):
    _attr_native_min_value = 1
    _attr_native_max_value = 3600
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self._value()

    async def async_set_native_value(self, value: float) -> None:
        await self._set(int(value))


class LockTime(LockEntity, TimeEntity):
    @property
    def native_value(self):
        v = self._value()
        return dtime(v[0], v[1]) if v else None

    async def async_set_value(self, value: dtime) -> None:
        await self._set((value.hour, value.minute))


class LockRefresh(LockEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.ls.refresh()


def lock_entities(platform: str, ls: LockSettings) -> list:
    if platform == "switch":
        return [LockSwitch(ls, k, i) for k, i in (
            ("light", "mdi:led-on"), ("sound", "mdi:volume-high"), ("button", "mdi:gesture-tap-button"),
            ("half_lock", "mdi:lock-minus"), ("auto_lock", "mdi:lock-clock"), ("pause_auto_lock", "mdi:lock-off"),
            ("ibeacon", "mdi:access-point"), ("night_on", "mdi:weather-night"), ("night_sound", "mdi:volume-off"),
            ("night_auto_lock", "mdi:lock-clock"), ("night_auto_unlock", "mdi:lock-open-variant"),
            ("night_lock_at_start", "mdi:lock-check"))]
    if platform == "select":
        return [LockSelect(ls, "speed", "mdi:speedometer", SPEEDS),
                LockSelect(ls, "button_trigger", "mdi:gesture-double-tap", BUTTON_TRIGGERS),
                LockSelect(ls, "button_action", "mdi:gesture-tap", BUTTON_ACTIONS),
                LockSelect(ls, "night_speed", "mdi:speedometer-slow", SPEEDS),
                LockSelect(ls, "night_lock_position", "mdi:lock-minus", LOCK_POSITIONS)]
    if platform == "number":
        return [LockDelay(ls, "auto_lock_delay", "mdi:timer-lock"), LockDelay(ls, "night_auto_lock_delay", "mdi:timer-lock")]
    if platform == "time":
        return [LockTime(ls, "night_start", "mdi:weather-sunset-down"), LockTime(ls, "night_end", "mdi:weather-sunset-up")]
    if platform == "button":
        return [LockRefresh(ls, "refresh", "mdi:refresh")]
    return []
