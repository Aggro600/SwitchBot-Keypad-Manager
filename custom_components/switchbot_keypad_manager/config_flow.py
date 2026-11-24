"""Config flow: pick the keypad (SwitchBot integration) and the keypad bridge."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_BRIDGE, CONF_KEYPAD_ENTRY, CONF_PERSONS, DOMAIN


def _person_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="person", multiple=True))


class KeypadManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        keypads = {e.entry_id: e.title for e in self.hass.config_entries.async_entries("switchbot")
                   if "keypad" in str(e.data.get("sensor_type", ""))}
        if not keypads:
            return self.async_abort(reason="no_keypad")
        bridges = sorted({str(e.data["device_name"]) for e in self.hass.config_entries.async_entries("esphome")
                          if e.data.get("device_name")})
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_KEYPAD_ENTRY])
            self._abort_if_unique_id_configured()
            data = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            return self.async_create_entry(title=user_input.get("name") or keypads[user_input[CONF_KEYPAD_ENTRY]],
                                           data=data)
        default_persons = [s.entity_id for s in self.hass.states.async_all("person")
                           if s.attributes.get("device_trackers")]
        schema = vol.Schema({
            vol.Required(CONF_KEYPAD_ENTRY): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=t) for k, t in keypads.items()],
                mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_BRIDGE, default="keypad-bridge" if "keypad-bridge" in bridges else vol.UNDEFINED):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=bridges, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional("name"): selector.TextSelector(),
            vol.Optional(CONF_PERSONS, default=default_persons): _person_selector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

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
