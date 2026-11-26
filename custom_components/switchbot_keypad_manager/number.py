"""Number entities: only lock settings (auto-lock delays)."""
from __future__ import annotations

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("type") == "lock":
        from .lock import lock_entities
        async_add_entities(lock_entities("number", entry.runtime_data))
        return
    from .keypad_settings import setting_entities
    async_add_entities(setting_entities("number", entry.runtime_data))
