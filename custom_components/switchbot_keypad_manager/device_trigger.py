"""Device triggers: "unlocked (any credential)" and "unlocked with a specific credential".

Lets automations pick the keypad, the credential (person + finger/face/…) and the outcome from lists instead of
typing event data.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, UNLOCKED_EVENT

TRIGGER_TYPES = ("unlocked", "unlocked_by_entry")
DECISIONS = ("any", "open", "denied", "event_only")
CONF_ENTRY = "entry"
CONF_DECISION = "decision"

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({
    vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    vol.Optional(CONF_ENTRY): str,
    vol.Optional(CONF_DECISION, default="any"): vol.In(DECISIONS),
})


def _config_entry_id(hass: HomeAssistant, device_id: str) -> str | None:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    return next((ident for dom, ident in device.identifiers if dom == DOMAIN), None)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict]:
    if _config_entry_id(hass, device_id) is None:
        return []
    return [{CONF_PLATFORM: "device", CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: t}
            for t in TRIGGER_TYPES]


async def async_get_trigger_capabilities(hass: HomeAssistant, config: ConfigType) -> dict:
    fields: dict = {}
    if config[CONF_TYPE] == "unlocked_by_entry":
        manager = hass.data.get(DOMAIN, {}).get(_config_entry_id(hass, config[CONF_DEVICE_ID]) or "")
        entries = {}
        if manager is not None:
            for e in sorted(manager.entries, key=lambda x: (x["person"], x["kind"], x["slot"])):
                entries[e["id"]] = f"{manager.who(e)} – {manager.t['kind'][e['kind']]} {e['slot']}"
        fields[vol.Required(CONF_ENTRY)] = vol.In(entries)
    de = (hass.config.language or "en").startswith("de")
    labels = ({"any": "Beliebig", "open": "Geöffnet", "denied": "Abgelehnt", "event_only": "Nur Automation"} if de else
              {"any": "Any", "open": "Opened", "denied": "Denied", "event_only": "Automation only"})
    fields[vol.Optional(CONF_DECISION, default="any")] = vol.In(labels)
    return {"extra_fields": vol.Schema(fields)}


async def async_attach_trigger(hass: HomeAssistant, config: ConfigType, action: TriggerActionType,
                               trigger_info: TriggerInfo) -> CALLBACK_TYPE:
    event_data: dict = {"config_entry_id": _config_entry_id(hass, config[CONF_DEVICE_ID])}
    if config[CONF_TYPE] == "unlocked_by_entry" and config.get(CONF_ENTRY):
        event_data["entry_id"] = config[CONF_ENTRY]
    if config.get(CONF_DECISION, "any") != "any":
        event_data["decision"] = config[CONF_DECISION]
    event_config = event_trigger.TRIGGER_SCHEMA({
        event_trigger.CONF_PLATFORM: "event",
        event_trigger.CONF_EVENT_TYPE: UNLOCKED_EVENT,
        event_trigger.CONF_EVENT_DATA: event_data,
    })
    return await event_trigger.async_attach_trigger(hass, event_config, action, trigger_info, platform_type="device")
