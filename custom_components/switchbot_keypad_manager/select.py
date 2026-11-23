"""Selects: person, what, validity, entry, rule for the person, rule for unknown credentials."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DAYS_OPTIONS, DOMAIN, ENTRY_FALLBACK_OPTIONS, FALLBACK_OPTIONS, ENTRY_RULE_OPTIONS, NO_ENTRY, RULE_OPTIONS, VALIDITY_OPTIONS, WHAT_OPTIONS
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Person(m), ChoiceSelect(m, "what", list(WHAT_OPTIONS), "mdi:fingerprint"),
                        ChoiceSelect(m, "validity", VALIDITY_OPTIONS, "mdi:calendar-clock"), Entry(m),
                        PersonRule(m), UnknownRule(m), EntryRule(m), EntryDays(m),
                        FallbackMode(m), EntryFallback(m)])


class Person(KeypadEntity, SelectEntity):
    _attr_icon = "mdi:account"

    def __init__(self, manager):
        super().__init__(manager, "person")

    @property
    def options(self):
        return self.manager.persons()

    @property
    def current_option(self):
        return self.manager.current_person()

    async def async_select_option(self, option: str) -> None:
        self.manager.choice["person"] = option
        self.manager.notify_entities()


class ChoiceSelect(KeypadEntity, SelectEntity):
    def __init__(self, manager, key, options, icon):
        super().__init__(manager, key)
        self.key = key
        self._attr_options = options
        self._attr_icon = icon

    @property
    def current_option(self):
        return self.manager.choice[self.key]

    async def async_select_option(self, option: str) -> None:
        self.manager.choice[self.key] = option
        self.manager.notify_entities()


class Entry(KeypadEntity, SelectEntity):
    _attr_icon = "mdi:account-key-outline"

    def __init__(self, manager):
        super().__init__(manager, "entry")

    def _labels(self):
        m = self.manager
        return {m.label(e): e["id"] for e in sorted(m.entries, key=lambda e: (e["person"], e["kind"], e["slot"]))}

    @property
    def options(self):
        return [NO_ENTRY, *self._labels()]

    @property
    def current_option(self):
        choice = self.manager.choice["entry"]
        return choice if choice in self.options else NO_ENTRY

    async def async_select_option(self, option: str) -> None:
        m = self.manager
        m.choice["entry"] = option
        entry = next((e for e in m.entries if m.label(e) == option), None)
        if entry is not None:   # pre-fill person and "what" so the entry can be edited right away
            m.choice["person"] = entry["person"]
            m.choice["what"] = m.what_of(entry)
        m.notify_entities()

    def selected_id(self):
        return self._labels().get(self.current_option)


class PersonRule(KeypadEntity, SelectEntity):
    """Approval rule of the person currently selected in 'Person'."""
    _attr_icon = "mdi:shield-account"
    _attr_options = RULE_OPTIONS

    def __init__(self, manager):
        super().__init__(manager, "person_rule")

    @property
    def current_option(self):
        return self.manager.rules.get(self.manager.current_person(), "always")

    async def async_select_option(self, option: str) -> None:
        self.manager.rules[self.manager.current_person()] = option
        await self.manager.save()


class UnknownRule(KeypadEntity, SelectEntity):
    _attr_icon = "mdi:shield-alert"
    _attr_options = ["always", "blocked"]

    def __init__(self, manager):
        super().__init__(manager, "unknown_rule")

    @property
    def current_option(self):
        return self.manager.unknown_rule

    async def async_select_option(self, option: str) -> None:
        self.manager.unknown_rule = option
        await self.manager.save()


class EntryRule(KeypadEntity, SelectEntity):
    """Approval rule of the entry currently selected in 'Entry' (overrides the person rule)."""
    _attr_icon = "mdi:shield-key"
    _attr_options = ENTRY_RULE_OPTIONS

    def __init__(self, manager):
        super().__init__(manager, "entry_rule")

    @property
    def current_option(self):
        entry = self.manager.selected_entry()
        return (entry.get("rule") or "inherit") if entry else "inherit"

    async def async_select_option(self, option: str) -> None:
        await self.manager.set_entry_rule(rule=option)


class EntryDays(KeypadEntity, SelectEntity):
    """Days of the time window of the selected entry."""
    _attr_icon = "mdi:calendar-week"
    _attr_options = DAYS_OPTIONS

    def __init__(self, manager):
        super().__init__(manager, "entry_days")

    @property
    def current_option(self):
        entry = self.manager.selected_entry()
        return ((entry or {}).get("window") or {}).get("days", "all")

    async def async_select_option(self, option: str) -> None:
        await self.manager.set_entry_rule(days=option)


class FallbackMode(KeypadEntity, SelectEntity):
    """What the bridge does without Home Assistant: open for all, only allowed entries, or nobody."""
    _attr_icon = "mdi:door-closed-lock"
    _attr_options = FALLBACK_OPTIONS

    def __init__(self, manager):
        super().__init__(manager, "fallback_mode")

    @property
    def current_option(self):
        return self.manager.fallback_mode

    async def async_select_option(self, option: str) -> None:
        self.manager.fallback_mode = option
        await self.manager.save()


class EntryFallback(KeypadEntity, SelectEntity):
    """Whether the selected entry may open via the fallback (mode 'only allowed entries')."""
    _attr_icon = "mdi:door-open"
    _attr_options = ENTRY_FALLBACK_OPTIONS

    def __init__(self, manager):
        super().__init__(manager, "entry_fallback")

    @property
    def current_option(self):
        entry = self.manager.selected_entry()
        return "allowed" if (entry or {}).get("fallback", True) else "blocked"

    async def async_select_option(self, option: str) -> None:
        await self.manager.set_entry_rule(fallback=option == "allowed")
