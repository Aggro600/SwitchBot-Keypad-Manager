"""Selects: person, what, validity, entry, rule for the person, rule for unknown credentials."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, NO_ENTRY, RULE_OPTIONS, VALIDITY_OPTIONS, WHAT_OPTIONS
from .entity import KeypadEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Person(m), ChoiceSelect(m, "what", list(WHAT_OPTIONS), "mdi:fingerprint"),
                        ChoiceSelect(m, "validity", VALIDITY_OPTIONS, "mdi:calendar-clock"), Entry(m),
                        PersonRule(m), UnknownRule(m)])


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
        self.manager.choice["entry"] = option
        self.manager.notify_entities()

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
