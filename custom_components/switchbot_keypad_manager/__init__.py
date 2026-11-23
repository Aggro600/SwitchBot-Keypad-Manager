"""SwitchBot Keypad Manager.

Enroll and delete credentials (fingerprint, face, palm, PIN, NFC) on a SwitchBot Keypad Vision / Vision Pro
from Home Assistant, assign them to people, show who unlocked how (events of the ESPHome keypad bridge) and,
optionally, approve or deny each keypad unlock with per-person rules.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BRIDGE_UNLOCK_EVENT, CONF_BRIDGE, CONF_KEYPAD_ENTRY, CONF_PERSONS, DOMAIN, FINGERPRINT, KINDS, NFC, NO_ENTRY, PIN,
    RULE_OPTIONS, UNLOCKED_EVENT, VALIDITY_OPTIONS, WHAT_OPTIONS, WINDOW_DEFAULT, WINDOWS, DAY_NAMES,
)
from .keypad import Keypad, KeypadError
from .texts import detail_text, texts

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TEXT, Platform.TIME]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SIGNAL = f"{DOMAIN}_updated_{{}}"
STORAGE_VERSION = 1


def reported_index(keypad_slot: int) -> int:
    """Slot number the keypad bridge reports on unlock for a keypad slot.

    The keypad reports credentials with a bias of 10 for some kinds (fingerprints are stored from slot 10 on);
    the bridge removes it (index = slot - 10 for slots >= 10), see switchbot-keypad-bridge lock_protocol.cpp.
    """
    return keypad_slot - 10 if keypad_slot >= 10 else keypad_slot


class Manager:
    """State and workflows of one keypad (one config entry)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.keypad = Keypad(hass, entry.data[CONF_KEYPAD_ENTRY])
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.entries: list[dict] = []
        self.extra_persons: list[str] = []
        self.counts: dict[str, int] = {}
        self.last: dict = {}
        self.rules: dict[str, str] = {}          # person -> rule
        self.unknown_rule = "always"              # rule for credentials without a person
        self.approval = False                     # approve/deny unlocks via the bridge
        self.fallback_mode = "all"                # bridge fallback without HA: all | allowed | none
        self._pushed_fallback: tuple | None = None
        self.unassigned: dict | None = None       # last unlock without a matching entry
        self.status_key, self.status_args = "ready", {}
        self.choice = {"person": None, "what": "thumb_right", "validity": "permanent", "entry": NO_ENTRY}
        self.running: asyncio.Task | None = None
        self.cancel_event = asyncio.Event()

    @property
    def t(self) -> dict:
        return texts(self.hass.config.language)

    # ---------- storage ----------
    async def load(self) -> None:
        data = await self.store.async_load() or {}
        self.entries = data.get("entries", [])
        for entry in self.entries:   # 1.0.0 stored the keypad slot of enrolled entries in "slot"
            if entry.get("source") == "home_assistant" and "keypad_slot" not in entry:
                entry["keypad_slot"] = entry["slot"]
                entry["slot"] = reported_index(entry["slot"])
        self.extra_persons = data.get("persons", [])
        self.last = data.get("last", {})
        self.counts = data.get("counts", {})
        self.rules = data.get("rules", {})
        self.unknown_rule = data.get("unknown_rule", "always")
        self.approval = data.get("approval", False)
        self.fallback_mode = data.get("fallback_mode", "all")

    async def save(self) -> None:
        await self.store.async_save({
            "entries": self.entries, "persons": self.extra_persons, "last": self.last, "counts": self.counts,
            "rules": self.rules, "unknown_rule": self.unknown_rule, "approval": self.approval,
            "fallback_mode": self.fallback_mode})
        self.notify_entities()
        self.push_fallback()

    # ---------- fallback policy on the bridge ----------
    def fallback_policy(self) -> tuple[int, str]:
        """(mode, allow list) for the bridge: 0 all, 1 only allowed entries, 2 none."""
        mode = {"all": 0, "allowed": 1, "none": 2}.get(self.fallback_mode, 0)
        allow = ",".join(f"{e['kind']}:{e['slot']}" for e in self.entries if e.get("fallback", True))
        return mode, allow

    @callback
    def push_fallback(self, force: bool = False) -> None:
        """Send the fallback policy to the bridge (stored there in flash) when it changed."""
        policy = self.fallback_policy()
        if not force and policy == self._pushed_fallback:
            return
        service = f"{self.entry.data[CONF_BRIDGE].replace('-', '_')}_set_fallback"
        if not self.hass.services.has_service("esphome", service):
            return
        self._pushed_fallback = policy
        self.hass.async_create_task(self.hass.services.async_call(
            "esphome", service, {"mode": policy[0], "allow": policy[1]}))

    @callback
    def notify_entities(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL.format(self.entry.entry_id))

    @staticmethod
    def new_entry(kind, slot, person, detail, *, source="home_assistant", keypad_slot=None, valid_from=None,
                  valid_until=None) -> dict:
        """slot = number reported by the bridge on unlock; keypad_slot = slot on the keypad (known when enrolled
        here, needed to delete it on the keypad)."""
        return {"id": uuid.uuid4().hex[:8], "kind": kind, "slot": slot, "keypad_slot": keypad_slot,
                "person": person, "detail": detail,
                "source": source, "created": dt_util.now().isoformat(timespec="minutes"),
                "valid_from": valid_from, "valid_until": valid_until}

    # ---------- presentation ----------
    def who(self, entry: dict) -> str:
        detail = detail_text(self.t, entry.get("detail") or "")
        return f"{entry['person']} ({detail})" if detail else entry["person"]

    def label(self, entry: dict) -> str:
        until = ""
        if entry.get("valid_until"):
            until = f", {self.t['until']} {dt_util.parse_datetime(entry['valid_until']).strftime('%d.%m. %H:%M')}"
        return f"{self.who(entry)} – {self.t['kind'][entry['kind']]} {entry['slot']}{until}"

    def persons(self) -> list[str]:
        names = []
        for entity_id in self.entry.options.get(CONF_PERSONS, self.entry.data.get(CONF_PERSONS, [])):
            if (state := self.hass.states.get(entity_id)) is not None:
                names.append(state.attributes.get("friendly_name") or entity_id.split(".", 1)[1])
        for name in self.extra_persons + [e["person"] for e in self.entries]:
            if name and name not in names:
                names.append(name)
        return names or ["Guest"]

    def current_person(self) -> str:
        person = self.choice["person"]
        return person if person in self.persons() else self.persons()[0]

    def unassigned_counts(self) -> dict[str, int]:
        """Credentials on the keypad without an entry in the list (e.g. created in the SwitchBot app)."""
        result = {}
        for kind in KINDS:
            if kind in self.counts:
                diff = self.counts[kind] - sum(1 for e in self.entries if e["kind"] == kind)
                if diff:
                    result[self.t["kind"][kind]] = diff
        return result

    @property
    def status(self) -> str:
        text = self.t.get(self.status_key, self.status_key)
        try:
            return text.format(**self.status_args)
        except (KeyError, IndexError):
            return text

    async def set_status(self, key: str, **args) -> None:
        self.status_key, self.status_args = key, args
        self.notify_entities()

    # ---------- unlock events from the keypad bridge ----------
    @callback
    def handle_bridge_event(self, event: Event) -> None:
        data = event.data
        if data.get("bridge") != self.entry.data[CONF_BRIDGE]:
            return
        kind = str(data.get("method", ""))
        try:
            slot = int(data.get("index"))
        except (TypeError, ValueError):
            return
        match = next((e for e in self.entries if e["kind"] == kind and e["slot"] == slot), None)
        decision, rule = self.decide(match)
        allowed = decision == "open"
        if self.approval:
            self._answer_bridge(allowed)
        kind_text = self.t["kind"].get(kind, kind)
        if match:
            text = self.who(match)
            self.unassigned = None
        else:
            text = f"{self.t['unknown']} ({kind_text} {slot})"
            self.unassigned = {"kind": kind, "slot": slot}
        # decision: open | denied | event_only (only meaningful with approval on; without it the bridge always opens)
        self.last = {"person": match["person"] if match else None, "detail": (match.get("detail") or "") if match else "",
                     "text": text, "kind": kind, "kind_text": kind_text, "slot": slot, "rule": rule,
                     "decision": decision if self.approval else "open",
                     "allowed": allowed if self.approval else None, "time": dt_util.now().isoformat()}
        self.hass.bus.async_fire(UNLOCKED_EVENT, {"keypad": self.entry.title, **self.last})
        self.hass.async_create_task(self.save())
        if "logbook" in self.hass.config.components:
            message = f"{text} {self.t['via']} {kind_text}"
            if self.approval and decision != "open":
                message += f" ({self.t[decision]})"
            self.hass.async_create_task(self.hass.services.async_call(
                "logbook", "log", {"name": self.entry.title, "message": message}))

    # ---------- approval rules ----------
    def decide(self, entry: dict | None) -> tuple[str, str]:
        """Decision for an unlock: ('open' | 'denied' | 'event_only', effective rule)."""
        if entry is None:
            rule = self.unknown_rule
        else:
            rule = entry.get("rule") or "inherit"
            if rule == "inherit":
                rule = self.rules.get(entry["person"], "always")
        if rule == "event_only":
            return "event_only", rule
        return ("open" if self._rule_allows(rule, entry) else "denied"), rule

    def _rule_allows(self, rule: str, entry: dict | None) -> bool:
        now = dt_util.now()
        if rule == "blocked":
            return False
        if rule == "daytime":
            return 6 <= now.hour < 22
        if rule == "weekdays":
            return now.weekday() < 5 and 7 <= now.hour < 19
        if rule == "time_window":
            return any(self._window_active(w, now) for w in self.windows(entry))
        if rule == "someone_home":
            home = self.hass.states.get("zone.home")
            try:
                return home is not None and int(float(home.state)) > 0
            except ValueError:
                return False
        return True

    @staticmethod
    def windows(entry: dict | None) -> list[dict]:
        """Up to WINDOWS time windows of an entry (1.2/1.3 stored a single 'window')."""
        if entry is None:
            return []
        stored = list(entry.get("windows") or ([entry["window"]] if entry.get("window") else []))
        while len(stored) < WINDOWS:
            stored.append(dict(WINDOW_DEFAULT) if not stored else {**WINDOW_DEFAULT, "days": "off"})
        return stored[:WINDOWS]

    @staticmethod
    def _window_active(window: dict, now) -> bool:
        days = window.get("days", "all")
        weekday = now.weekday()
        if days == "off" or (days == "weekdays" and weekday >= 5) or (days == "weekend" and weekday < 5):
            return False
        if days in DAY_NAMES and DAY_NAMES.index(days) != weekday:
            return False
        start, end = window.get("from", "06:00"), window.get("until", "22:00")
        current = now.strftime("%H:%M")
        return start <= current < end if start <= end else (current >= start or current < end)

    def selected_entry(self) -> dict | None:
        return next((e for e in self.entries if self.label(e) == self.choice["entry"]), None)

    async def set_entry_rule(self, **changes) -> None:
        """Change rule / time window of the entry selected in 'Entry'."""
        entry = self.selected_entry()
        if entry is None:
            raise HomeAssistantError(self.t["err_select"])
        if "rule" in changes:
            entry["rule"] = changes.pop("rule")
        if "fallback" in changes:
            entry["fallback"] = changes.pop("fallback")
        number = changes.pop("window", 1)
        if changes:
            windows = self.windows(entry)
            windows[number - 1].update(changes)
            entry["windows"] = windows
            entry.pop("window", None)
        await self.save()

    def _answer_bridge(self, allowed: bool) -> None:
        service = f"{self.entry.data[CONF_BRIDGE].replace('-', '_')}_{'approve' if allowed else 'deny'}_unlock"
        if not self.hass.services.has_service("esphome", service):
            _LOGGER.warning("Approval is on, but esphome.%s does not exist – see the README (bridge approval)", service)
            return
        self.hass.async_create_task(self.hass.services.async_call("esphome", service, {}))

    # ---------- workflows ----------
    def _period(self, validity: str):
        now = dt_util.now()
        end = {"today": now.replace(hour=23, minute=59, second=59), "24h": now + timedelta(hours=24),
               "1w": now + timedelta(days=7), "1m": now + timedelta(days=30)}.get(validity)
        return (now, end) if end else (None, None)

    async def enroll(self, person: str, what: str, validity: str = "permanent") -> dict:
        if self.running and not self.running.done():
            raise HomeAssistantError(self.t["err_running"])
        if not person:
            raise HomeAssistantError(self.t["err_person"])
        if what not in WHAT_OPTIONS:
            raise HomeAssistantError(f"Unknown option {what}")
        kind, detail = WHAT_OPTIONS[what]
        start, end = self._period(validity)
        once = validity == "once"
        if once and kind != PIN:
            raise HomeAssistantError(self.t["err_once"])
        if end and kind not in (PIN, FINGERPRINT, NFC):
            raise HomeAssistantError(self.t["err_limit"])
        self.cancel_event.clear()
        self.running = asyncio.current_task()
        await self.set_status("starting", who=person, what=self.t["kind"][kind])
        try:
            result = await self.keypad.enroll(
                kind, valid_from=start.timestamp() if end else None, valid_until=end.timestamp() if end else None,
                once=once, status=lambda key: self.set_status(key), cancel=self.cancel_event)
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        finally:
            self.running = None
        # an outdated entry for the same slot is replaced
        slot = reported_index(result["slot"])
        self.entries = [e for e in self.entries if not (e["kind"] == kind and e["slot"] == slot)]
        entry = self.new_entry(kind, slot, person, detail, keypad_slot=result["slot"],
                               valid_from=start.isoformat() if end else None, valid_until=end.isoformat() if end else None)
        self.entries.append(entry)
        if person not in self.persons():
            self.extra_persons.append(person)
        await self._refresh_counts()
        await self.set_status("done", entry=self.label(entry))
        message = self.t["enrolled"].format(entry=self.label(entry))
        if "pin" in result:
            message += "\n\n" + self.t["pin_note"].format(pin=result["pin"])
        self._notify(message)
        return {"entry": entry, **({"pin": result["pin"]} if "pin" in result else {})}

    async def delete(self, entry_id: str) -> None:
        entry = next((e for e in self.entries if e["id"] == entry_id), None)
        if entry is None:
            raise HomeAssistantError(self.t["err_entry"])
        if entry.get("keypad_slot") is None:
            # not enrolled here (SwitchBot app / assigned): the keypad slot is unknown, never guess it
            self.entries.remove(entry)
            self.choice["entry"] = NO_ENTRY
            await self.save()
            await self.set_status("deleted_list_only", entry=self.label(entry))
            self._notify(self.t["deleted_list_only_note"].format(entry=self.label(entry)))
            return
        await self.set_status("deleting", entry=self.label(entry))
        try:
            await self.keypad.delete(entry["kind"], entry["keypad_slot"])
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        self.entries.remove(entry)
        self.choice["entry"] = NO_ENTRY
        await self._refresh_counts()
        await self.set_status("deleted", entry=self.label(entry))
        self._notify(self.t["deleted_note"].format(entry=self.label(entry)))

    def what_of(self, entry: dict) -> str:
        """'What' option that describes an entry (for pre-filling the selects when editing)."""
        if entry["kind"] == FINGERPRINT and entry.get("detail") in WHAT_OPTIONS:
            return entry["detail"]
        return next((k for k, (kind, _) in WHAT_OPTIONS.items() if kind == entry["kind"] and kind != FINGERPRINT),
                    self.choice["what"])

    async def update_entry(self, entry_id: str, person: str | None = None, what: str | None = None) -> None:
        """Change person and/or finger of an entry (only in the list – the keypad stores no names)."""
        entry = next((e for e in self.entries if e["id"] == entry_id), None)
        if entry is None:
            raise HomeAssistantError(self.t["err_entry"])
        if what is not None:
            kind, detail = WHAT_OPTIONS[what]
            if kind != entry["kind"]:
                raise HomeAssistantError(self.t["err_kind"])
            entry["detail"] = detail
        if person:
            entry["person"] = person
            if person not in self.persons():
                self.extra_persons.append(person)
        if self.last and self.last.get("kind") == entry["kind"] and self.last.get("slot") == entry["slot"]:
            self.last.update({"person": entry["person"], "detail": entry.get("detail") or "", "text": self.who(entry)})
        self.choice["entry"] = self.label(entry)
        await self.save()
        await self.set_status("updated", entry=self.label(entry))

    async def assign_last(self, person: str, what: str) -> None:
        """Assign the last unknown unlock (e.g. a credential from the SwitchBot app) – no keypad command."""
        if not self.unassigned:
            raise HomeAssistantError(self.t["err_unassigned"])
        if not person:
            raise HomeAssistantError(self.t["err_person"])
        kind, slot = self.unassigned["kind"], self.unassigned["slot"]
        what_kind, detail = WHAT_OPTIONS.get(what, (kind, ""))
        if what_kind != kind:
            detail = ""
        entry = self.new_entry(kind, slot, person, detail, source="assigned")
        self.entries.append(entry)
        self.unassigned = None
        self.last.update({"text": self.who(entry), "person": person, "detail": detail})
        await self.save()
        await self.set_status("assigned", entry=self.label(entry))

    async def sync(self) -> None:
        await self.set_status("querying")
        try:
            self.counts = await self.keypad.counts()
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        await self.save()
        diff = self.unassigned_counts()
        if diff:
            await self.set_status("sync", diff=", ".join(f"{k} {v:+d}" for k, v in diff.items()))
        else:
            await self.set_status("sync_ok")

    async def _refresh_counts(self) -> None:
        try:
            self.counts = await self.keypad.counts()
        except KeypadError:
            pass
        await self.save()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _notify(self, message: str) -> None:
        self.hass.async_create_task(self.hass.services.async_call("persistent_notification", "create", {
            "notification_id": f"{DOMAIN}_{self.entry.entry_id}", "title": self.entry.title, "message": message}))


def _manager(hass: HomeAssistant, call: ServiceCall) -> Manager:
    managers: dict[str, Manager] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("config_entry_id")
    if entry_id:
        if entry_id not in managers:
            raise HomeAssistantError("Keypad not found")
        return managers[entry_id]
    if len(managers) != 1:
        raise HomeAssistantError("Several keypads – please pass config_entry_id")
    return next(iter(managers.values()))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def enroll(call: ServiceCall):
        return await _manager(hass, call).enroll(call.data["person"], call.data["what"], call.data["validity"])

    async def update(call: ServiceCall) -> None:
        await _manager(hass, call).update_entry(call.data["entry_id"], call.data.get("person"), call.data.get("what"))

    async def delete(call: ServiceCall) -> None:
        await _manager(hass, call).delete(call.data["entry_id"])

    async def sync(call: ServiceCall) -> None:
        await _manager(hass, call).sync()

    base = {vol.Optional("config_entry_id"): cv.string}
    hass.services.async_register(DOMAIN, "enroll", enroll, schema=vol.Schema({
        **base, vol.Required("person"): cv.string, vol.Required("what"): vol.In(list(WHAT_OPTIONS)),
        vol.Optional("validity", default="permanent"): vol.In(VALIDITY_OPTIONS)}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "delete", delete, schema=vol.Schema({**base, vol.Required("entry_id"): cv.string}))
    hass.services.async_register(DOMAIN, "sync", sync, schema=vol.Schema(base))
    hass.services.async_register(DOMAIN, "update", update, schema=vol.Schema({
        **base, vol.Required("entry_id"): cv.string, vol.Optional("person"): cv.string,
        vol.Optional("what"): vol.In(list(WHAT_OPTIONS))}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = Manager(hass, entry)
    await manager.load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    entry.async_on_unload(hass.bus.async_listen(BRIDGE_UNLOCK_EVENT, manager.handle_bridge_event))

    @callback
    def _service_registered(event: Event) -> None:
        if event.data.get("domain") == "esphome" and str(event.data.get("service", "")).endswith("_set_fallback"):
            manager.push_fallback(force=True)

    entry.async_on_unload(hass.bus.async_listen("service_registered", _service_registered))
    entry.async_on_unload(async_track_time_interval(
        hass, callback(lambda _now: manager.push_fallback(force=True)), timedelta(minutes=15)))
    manager.push_fallback(force=True)
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id).cancel()
    return unloaded


__all__ = ["Manager", "RULE_OPTIONS", "SIGNAL"]
