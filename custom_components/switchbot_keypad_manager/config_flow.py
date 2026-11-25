"""Config flow: pick a Keypad Vision (Pro) seen by Home Assistant's Bluetooth, get its encryption key, pick the bridge.

The integration talks to the keypad itself (PySwitchbot + Home Assistant's Bluetooth / proxies). The encryption key
is retrieved once with the SwitchBot account (like the SwitchBot integration does) or entered manually.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ADDRESS, CONF_BRIDGE, CONF_ENCRYPTION_KEY, CONF_KEY_ID, CONF_MODEL, CONF_PERSONS, CONF_TYPE, DOMAIN, KEYPAD_MODELS,
    LOCK_MODELS,
)

_LOGGER = logging.getLogger(__name__)


def _person_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="person", multiple=True))


def discovered_keypads(hass, models=KEYPAD_MODELS) -> dict[str, str]:
    """address -> model name of devices of `models` currently seen by Home Assistant's Bluetooth."""
    from switchbot import parse_advertisement_data
    found: dict[str, str] = {}
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        try:
            adv = parse_advertisement_data(info.device, info.advertisement)
        except Exception:  # noqa: BLE001 - foreign advertisements
            continue
        model = str((adv.data or {}).get("modelName") or "") if adv else ""
        if model in models:
            found[info.address] = model
    return found


async def _verify(hass, address: str, model: str, key_id: str, key: str) -> bool:
    from switchbot import SwitchbotKeypadVision, SwitchbotLock, SwitchbotModel
    ble = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble is None:
        return False
    cls = SwitchbotLock if model in LOCK_MODELS else SwitchbotKeypadVision
    return await cls.verify_encryption_key(ble, key_id, key, SwitchbotModel(model))


class KeypadManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._address = ""
        self._model = ""
        self._settings: dict[str, Any] = {}
        self._reauth_entry: ConfigEntry | None = None

    # ---------- 0. what to add ----------
    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["keypad", "lock"])

    # ---------- lock settings ----------
    async def async_step_lock(self, user_input=None) -> ConfigFlowResult:
        locks = discovered_keypads(self.hass, LOCK_MODELS)
        configured = {e.data.get(CONF_ADDRESS) for e in self._async_current_entries()}
        choices = {a: m for a, m in locks.items() if a not in configured}
        if not choices:
            return self.async_abort(reason="no_lock")
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._model = choices[self._address]
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            self._settings = {CONF_TYPE: "lock", **({"name": user_input["name"]} if user_input.get("name") else {})}
            return await self.async_step_key()
        return self.async_show_form(step_id="lock", data_schema=vol.Schema({
            vol.Required(CONF_ADDRESS): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=a, label=f"{m} ({a})") for a, m in choices.items()],
                mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional("name"): selector.TextSelector()}))

    # ---------- 1. keypad + bridge + persons ----------
    async def async_step_keypad(self, user_input=None) -> ConfigFlowResult:
        keypads = discovered_keypads(self.hass)
        configured = {e.data.get(CONF_ADDRESS) for e in self._async_current_entries()}
        choices = {a: m for a, m in keypads.items() if a not in configured}
        if not choices:
            return self.async_abort(reason="no_keypad")
        bridges = sorted({str(e.data["device_name"]) for e in self.hass.config_entries.async_entries("esphome")
                          if e.data.get("device_name")})
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._model = choices[self._address]
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            self._settings = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            return await self.async_step_key()
        default_persons = [s.entity_id for s in self.hass.states.async_all("person")
                           if s.attributes.get("device_trackers")]
        schema = vol.Schema({
            vol.Required(CONF_ADDRESS): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=a, label=f"{m} ({a})") for a, m in choices.items()],
                mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_BRIDGE, default=bridges[0] if len(bridges) == 1 else vol.UNDEFINED):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=bridges, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional("name"): selector.TextSelector(),
            vol.Optional(CONF_PERSONS, default=default_persons): _person_selector(),
        })
        return self.async_show_form(step_id="keypad", data_schema=schema)

    # ---------- 2. encryption key ----------
    async def async_step_key(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="key", menu_options=["key_login", "key_manual"])

    async def async_step_key_login(self, user_input=None) -> ConfigFlowResult:
        from switchbot import SwitchbotAccountConnectionError, SwitchbotAuthenticationError, SwitchbotKeypadVision
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                key = await SwitchbotKeypadVision.async_retrieve_encryption_key(
                    async_get_clientsession(self.hass), self._address, user_input["username"], user_input["password"])
            except SwitchbotAccountConnectionError:
                errors["base"] = "cannot_connect"
            except SwitchbotAuthenticationError:
                errors["base"] = "auth_failed"
            else:
                return await self._finish(key["key_id"], key["encryption_key"], errors)
        return self.async_show_form(step_id="key_login", errors=errors, data_schema=vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))

    async def async_step_key_manual(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._finish(user_input[CONF_KEY_ID].strip(), user_input[CONF_ENCRYPTION_KEY].strip(), errors)
            if not errors:
                return result
        return self.async_show_form(step_id="key_manual", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_KEY_ID): str,
            vol.Required(CONF_ENCRYPTION_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))

    async def _finish(self, key_id: str, key: str, errors: dict) -> ConfigFlowResult:
        try:
            ok = await _verify(self.hass, self._address, self._model, key_id, key)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Key verification failed: %s", err)
            ok = False
        if not ok:
            errors["base"] = "encryption_key_invalid"
            return self.async_show_form(step_id="key_manual", errors=errors, data_schema=vol.Schema({
                vol.Required(CONF_KEY_ID, default=key_id): str,
                vol.Required(CONF_ENCRYPTION_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            }))
        keydata = {CONF_ADDRESS: self._address, CONF_MODEL: self._model, CONF_KEY_ID: key_id, CONF_ENCRYPTION_KEY: key}
        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(self._reauth_entry, data={**self._reauth_entry.data, **keydata})
        title = self._settings.pop("name", None) or self._model
        return self.async_create_entry(title=title, data={**self._settings, **keydata})

    # ---------- reauth: entries from 1.x (via the SwitchBot integration) or a new key ----------
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        self._address = entry_data.get(CONF_ADDRESS, "")
        self._model = entry_data.get(CONF_MODEL, "")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        if self._address and self._model:
            return await self.async_step_key()
        keypads = discovered_keypads(self.hass)
        others = {e.data.get(CONF_ADDRESS) for e in self._async_current_entries() if e is not self._reauth_entry}
        choices = {a: m for a, m in keypads.items() if a not in others}
        if not choices:
            return self.async_abort(reason="no_keypad")
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._model = choices[self._address]
            return await self.async_step_key()
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({
            vol.Required(CONF_ADDRESS): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=a, label=f"{m} ({a})") for a, m in choices.items()],
                mode=selector.SelectSelectorMode.DROPDOWN))}),
            description_placeholders={"title": self._reauth_entry.title if self._reauth_entry else ""})

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        return config_entry.data.get(CONF_TYPE) != "lock"

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry):
        return KeypadManagerOptionsFlow()


class KeypadManagerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_PERSONS, self.config_entry.data.get(CONF_PERSONS, []))
        bridge = self.config_entry.options.get(CONF_BRIDGE) or self.config_entry.data.get(CONF_BRIDGE, "")
        bridges = sorted({str(e.data["device_name"]) for e in self.hass.config_entries.async_entries("esphome")
                          if e.data.get("device_name")} | {bridge})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_BRIDGE, default=bridge): selector.SelectSelector(selector.SelectSelectorConfig(
                options=bridges, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_PERSONS, default=current): _person_selector()}))
