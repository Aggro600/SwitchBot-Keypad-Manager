"""Settings of a Keypad Vision (Pro) – verified on a Keypad Vision Pro (write, read back, restore).

  0101  lock button            read 01 off / 02 on                 write 570F520101 <01|02> 0000
  0102  keypad disabled        read 01 no / 02 yes                 write 570F520102 <01|02>
  0104  backlight + key tone   read <mode 01 off/02 auto/03 on> <level> <tone 01 off/02 on>
                               write 570F520104 <mode|00> <level|00> <tone|00>  (00 = keep)
  0107  fast unlock            00 off / 01 always / 02 auto        write 570F520107 <v>
  0108  detection sensitivity  01 low / 02 medium / 03 high        write 570F520108 <v>
  010A  detection trigger      01 auto / 02 manual / 03 schedule   write 570F52010A <v>
  010B  deactivation interval  seconds                             write 570F52010B <s>
  5702  basic info             byte9 tamper alarm 01 off / 02 on   write 570F520103 <01|02>
  010D  voice language         01 English / 04 German (others unknown) write 570F52010D <v>
  010C  volume                 read <voice> <tones>, 1 mute … 4 high
                               write 570F52010C <v> <01 tones | 02 voice>
"""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .entity import KeypadEntity
from .keypad import KeypadError

_LOGGER = logging.getLogger(__name__)

TRIGGERS = ["auto", "manual", "schedule"]
SENSITIVITY = ["low", "medium", "high"]
FAST_UNLOCK = ["off", "always", "auto"]
VOLUMES = ["mute", "low", "medium", "high"]
BACKLIGHT = ["off", "auto", "on"]
LANGUAGES = {"english": 1, "german": 4}
SIGNAL = "switchbot_keypad_manager_kpset_{}"


class KeypadSettings:
    def __init__(self, manager) -> None:
        self.m = manager
        self.s: dict = {}
        self.available = False
        self._unsubs: list = []

    async def _r(self, cmd: str, length: int) -> bytes:
        """Read one register; a reply that does not fit (busy, stray notification) is read again."""
        reply = b""
        for _ in range(3):
            reply = await self.m.keypad.command(cmd)
            if reply and reply[0] == 1 and len(reply) >= length:
                return reply
        raise KeypadError(f"Unexpected reply to {cmd}: {reply.hex()}")

    async def _read_all(self) -> None:
        s = {}
        r = await self._r("570F530101", 2)
        s["lock_button"] = r[1] != 1
        r = await self._r("570F530102", 2)
        s["keypad_disabled"] = r[1] == 2
        r = await self._r("570F530104", 4)
        s["backlight"] = BACKLIGHT[min(max(r[1], 1), 3) - 1]
        s["backlight_level"] = r[2]
        s["key_tone"] = r[3] == 2
        r = await self._r("570F530107", 2)
        s["fast_unlock"] = FAST_UNLOCK[min(r[1], 2)]
        r = await self._r("570F530108", 2)
        s["sensitivity"] = SENSITIVITY[min(max(r[1], 1), 3) - 1]
        r = await self._r("570F53010A", 2)
        s["trigger"] = TRIGGERS[min(max(r[1], 1), 3) - 1]
        r = await self._r("570F53010B", 2)
        s["deactivation_interval"] = r[1]
        r = await self._r("5702", 10)
        s["tamper_alarm"] = r[9] == 2
        r = await self._r("570F53010D", 2)
        s["language"] = next((k for k, v in LANGUAGES.items() if v == r[1]), None)
        r = await self._r("570F53010C", 3)
        s["voice_volume"] = VOLUMES[min(max(r[1], 1), 4) - 1]
        s["tone_volume"] = VOLUMES[min(max(r[2], 1), 4) - 1]
        self.s = s

    async def refresh(self) -> None:
        async with self.m.keypad.lock:
            try:
                await self._read_all()
                self.available = True
            except (KeypadError, IndexError) as err:
                self.available = False
                _LOGGER.warning("%s: keypad settings not readable: %s", self.m.entry.title, err)
            finally:
                await self.m.keypad.release()
        async_dispatcher_send(self.m.hass, SIGNAL.format(self.m.entry.entry_id))

    async def set(self, key: str, value) -> None:
        if key == "lock_button":
            cmd = f"570F520101{2 if value else 1:02X}0000"
        elif key == "keypad_disabled":
            cmd = f"570F520102{2 if value else 1:02X}"
        elif key == "backlight":
            level = self.s.get("backlight_level") or 5
            cmd = f"570F520104{BACKLIGHT.index(value) + 1:02X}{level:02X}00"
        elif key == "backlight_level":
            mode = BACKLIGHT.index(self.s.get("backlight", "on")) + 1
            cmd = f"570F520104{mode:02X}{int(value):02X}00"
        elif key == "key_tone":
            cmd = f"570F5201040000{2 if value else 1:02X}"
        elif key == "fast_unlock":
            cmd = f"570F520107{FAST_UNLOCK.index(value):02X}"
        elif key == "sensitivity":
            cmd = f"570F520108{SENSITIVITY.index(value) + 1:02X}"
        elif key == "trigger":
            cmd = f"570F52010A{TRIGGERS.index(value) + 1:02X}"
        elif key == "deactivation_interval":
            cmd = f"570F52010B{int(value):02X}"
        elif key == "tamper_alarm":
            cmd = f"570F520103{2 if value else 1:02X}"
        elif key == "language":
            cmd = f"570F52010D{LANGUAGES[value]:02X}"
        elif key == "voice_volume":
            cmd = f"570F52010C{VOLUMES.index(value) + 1:02X}02"
        elif key == "tone_volume":
            cmd = f"570F52010C{VOLUMES.index(value) + 1:02X}01"
        else:
            raise KeypadError(f"Unknown setting {key}")
        async with self.m.keypad.lock:
            try:
                r = await self.m.keypad.command(cmd)
                if r[0] != 1:
                    raise KeypadError(f"Keypad rejected the setting ({r.hex()})")
                await self._read_all()
                self.available = True
            finally:
                await self.m.keypad.release()
        async_dispatcher_send(self.m.hass, SIGNAL.format(self.m.entry.entry_id))

    def start(self) -> None:
        async def _refresh(_now=None) -> None:
            await self.refresh()
        self._unsubs.append(async_call_later(self.m.hass, 40, _refresh))
        self._unsubs.append(async_track_time_interval(self.m.hass, _refresh, timedelta(hours=12)))

    def stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()


class _SettingEntity(KeypadEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager, key: str, icon: str) -> None:
        super().__init__(manager, f"kp_{key}")
        self.key = key
        self._attr_icon = icon

    @property
    def ks(self) -> KeypadSettings:
        return self.manager.settings

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL.format(self.manager.entry.entry_id),
                                                      self._kp_updated))

    @callback
    def _kp_updated(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.ks.available and self.key in self.ks.s


class SettingSwitch(_SettingEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.ks.s.get(self.key)

    async def async_turn_on(self, **kwargs) -> None:
        await self.ks.set(self.key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ks.set(self.key, False)


class SettingSelect(_SettingEntity, SelectEntity):
    def __init__(self, manager, key, icon, options) -> None:
        super().__init__(manager, key, icon)
        self._attr_options = options

    @property
    def current_option(self):
        return self.ks.s.get(self.key)

    async def async_select_option(self, option: str) -> None:
        await self.ks.set(self.key, option)


class SettingNumber(_SettingEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, manager, key, icon, lo, hi, unit=None) -> None:
        super().__init__(manager, key, icon)
        self._attr_native_min_value, self._attr_native_max_value = lo, hi
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return self.ks.s.get(self.key)

    async def async_set_native_value(self, value: float) -> None:
        await self.ks.set(self.key, int(value))


class SettingsRefresh(KeypadEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, manager) -> None:
        super().__init__(manager, "kp_refresh")

    async def async_press(self) -> None:
        await self.manager.settings.refresh()


def setting_entities(platform: str, m) -> list:
    if platform == "switch":
        return [SettingSwitch(m, "lock_button", "mdi:lock-check"), SettingSwitch(m, "keypad_disabled", "mdi:dialpad"),
                SettingSwitch(m, "key_tone", "mdi:volume-high"), SettingSwitch(m, "tamper_alarm", "mdi:alarm-light")]
    if platform == "select":
        return [SettingSelect(m, "trigger", "mdi:radar", TRIGGERS),
                SettingSelect(m, "sensitivity", "mdi:signal-distance-variant", SENSITIVITY),
                SettingSelect(m, "fast_unlock", "mdi:lock-open-variant", FAST_UNLOCK),
                SettingSelect(m, "voice_volume", "mdi:account-voice", VOLUMES),
                SettingSelect(m, "tone_volume", "mdi:bell-ring", VOLUMES),
                SettingSelect(m, "backlight", "mdi:brightness-6", BACKLIGHT),
                SettingSelect(m, "language", "mdi:translate", list(LANGUAGES))]
    if platform == "number":
        return [SettingNumber(m, "deactivation_interval", "mdi:timer-sand", 5, 60, "s"),
                SettingNumber(m, "backlight_level", "mdi:brightness-percent", 1, 5)]
    if platform == "button":
        return [SettingsRefresh(m)]
    return []
