"""Buttons: only "read settings" of keypad and lock. Credential actions are admin-only services (see services.yaml)."""
from __future__ import annotations


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("button", entry.runtime_data))
        return
    from .keypad_settings import setting_entities
    async_add_entities(setting_entities("button", entry.runtime_data))
