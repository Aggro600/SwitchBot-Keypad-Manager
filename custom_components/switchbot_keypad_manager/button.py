"""Buttons: enroll, delete, update entry, assign last unlock, sync, cancel."""
from __future__ import annotations

import time

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, NO_ENTRY
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Action(m, "enroll", "mdi:account-plus"), Action(m, "delete", "mdi:account-remove"),
                        Action(m, "update", "mdi:account-edit"),
                        Action(m, "assign_last", "mdi:account-arrow-left"), Action(m, "sync", "mdi:sync"),
                        Action(m, "cancel", "mdi:cancel"), Action(m, "delete_all", "mdi:delete-alert")])


class Action(KeypadEntity, ButtonEntity):
    def __init__(self, manager, key, icon):
        super().__init__(manager, key)
        self.key = key
        self._attr_icon = icon
        self._armed = 0.0

    async def async_press(self) -> None:
        m = self.manager
        if self.key == "enroll":
            # enrollment takes up to 90 s – run in the background so the button returns at once
            self.hass.async_create_background_task(
                self._quiet(m.enroll(m.current_person(), m.choice["what"], m.choice["validity"])),
                f"{DOMAIN}_enroll")
        elif self.key == "delete":
            choice = m.choice["entry"]
            unknown = m.unknown_labels().get(choice)
            if unknown:
                # searching the slot can take a while – run in the background, progress in the status sensor
                self.hass.async_create_background_task(self._quiet(m.delete_unknown(unknown)), f"{DOMAIN}_delete")
                return
            entry_id = next((e["id"] for e in m.entries if m.label(e) == choice), None)
            if choice == NO_ENTRY or entry_id is None:
                raise HomeAssistantError(m.t["err_select"])
            await m.delete(entry_id)
        elif self.key == "update":
            choice = m.choice["entry"]
            entry_id = next((e["id"] for e in m.entries if m.label(e) == choice), None)
            if choice == NO_ENTRY or entry_id is None:
                raise HomeAssistantError(m.t["err_select"])
            await m.update_entry(entry_id, m.current_person(), m.choice["what"])
        elif self.key == "assign_last":
            await m.assign_last(m.current_person(), m.choice["what"])
        elif self.key == "sync":
            await m.sync()
        elif self.key == "delete_all":
            # two presses within 15 s
            now = time.monotonic()
            if now - self._armed > 15:
                self._armed = now
                await m.set_status("delete_all_confirm")
                return
            self._armed = 0.0
            self.hass.async_create_background_task(self._quiet(m.delete_all()), f"{DOMAIN}_delete_all")
        elif self.key == "cancel":
            m.cancel()
            await m.set_status("cancel")

    @staticmethod
    async def _quiet(coro):
        try:
            await coro
        except HomeAssistantError:
            pass  # already shown in the status sensor
