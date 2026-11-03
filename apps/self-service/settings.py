"""Settings platform admins change from the approvals app (Settings), without a pull request:
the links the self-service app shows and a banner across its pages.

Only what the app says or links to (and the Genie One Onboarding prompt). Who can do what (human_approval, approver groups, naming,
the model, grants) stays in app.yaml, where a change is reviewed. Each setting's default is
app.yaml's value; a change made here overrides it until someone resets it. Changes are
appended to the database (setting_events: who and when), never rewritten.
"""
import datetime as dt
import logging
import re
import threading
import time

import cards

log = logging.getLogger(__name__)

PERSONAS = ("explorer", "builder", "publisher")
SOPS = {"schema": "Personal schema", "project_schema": "Project schema", "team_schema": "Team schema",
        "persona": "Workspace access", "folder": "Workspace folder", "warehouses": "SQL warehouses"}
# How it works (the "New here?" line), then one FAQ per catalog section, named as it is.
FAQS = {"getting_started": "How it works", **dict(cards.SECTIONS)}

# Every setting, by section: (key, label, kind). kind: url, text, prompt or date.
SECTIONS = [
    ("Announcement banner", "Show a message at the top of every page, such as planned maintenance.", [
        ("banner.text", "Message", "text"),
        ("banner.until", "Show until", "date")]),
    ("Genie One Onboarding", "The question the Genie One Onboarding card asks Genie in the person's workspace. Empty hides the card.", [
        ("onboarding.prompt", "Prompt", "prompt")]),
    ("Persona request links", "Links to request each access level, such as a ServiceNow catalog item.", [
        (f"persona_request.{p}", p.title(), "url") for p in PERSONAS]),
    ("Group request link", "Where people ask for an Entra group to be added to their workspace with a persona, such as a ServiceNow form. Empty shows the card as Coming soon.", [
        ("group_request", "Add a group to your workspace", "url")]),
    ("FAQ pages", "FAQ links shown in each catalog section.", [
        (f"faq.{k}", label, "url") for k, label in FAQS.items()]),
    ("Standard operating procedures", "SOP links shown on each catalog item.", [
        (f"sop.{k}", label, "url") for k, label in SOPS.items()]),
]
# The Settings page's tabs: (key, label, the SECTIONS shown). Onboarding holds what the catalog's
# Onboarding section shows; the change history is a tab of its own (approvals.py).
TABS = [
    ("announcement", "Announcement", ["Announcement banner"]),
    ("onboarding", "Onboarding", ["Genie One Onboarding", "Persona request links", "Group request link"]),
    ("help", "Help links", ["FAQ pages", "Standard operating procedures"]),
]
KINDS = {key: kind for _, _, fields in SECTIONS for key, _, kind in fields}
LABELS = {key: label for _, _, fields in SECTIONS for key, label, _ in fields}
NAMES = {key: f"{title} · {label}" for title, _, fields in SECTIONS for key, label, _ in fields}   # in the history


def defaults(config):
    """Each setting's value from app.yaml ("" when it has none)."""
    links = config.get("links") or {}
    persona = links.get("persona_request")
    out = {"banner.text": "", "banner.until": "", "onboarding.prompt": (config.get("onboarding") or {}).get("prompt") or "",
           "group_request": links.get("group_request") or ""}
    for p in PERSONAS:
        out[f"persona_request.{p}"] = (persona.get(p) if isinstance(persona, dict) else persona) or ""
    for k in FAQS:
        out[f"faq.{k}"] = (config.get("faq") or {}).get(k) or ""
    for k in SOPS:
        out[f"sop.{k}"] = (links.get("sop") or {}).get(k) or ""
    return out


def values(config, overrides):
    """Each setting's value: its override (a value; None means back to the default) or app.yaml's."""
    out = defaults(config)
    for key, row in overrides.items():
        if key in out and row.get("value") is not None:
            out[key] = row["value"]
    return out


def apply(config, overrides, today=None):
    """config with the settings in it, as the pages read it: links.persona_request (one per
    persona), links.sop, faq and banner (None when there is none, or it has ended)."""
    if not overrides:
        return {**config, "banner": None, "onboarding": {"prompt": defaults(config)["onboarding.prompt"]}}
    v = values(config, overrides)
    links = {**(config.get("links") or {}),
             "persona_request": {p: v[f"persona_request.{p}"] or None for p in PERSONAS},
             "sop": {k: v[f"sop.{k}"] or None for k in SOPS}, "group_request": v["group_request"] or None}
    today = today or dt.datetime.now(dt.timezone.utc).date()
    until = v["banner.until"]
    shown = v["banner.text"] and not (until and until < today.isoformat())
    return {**config, "links": links, "faq": {k: v[f"faq.{k}"] or None for k in FAQS},
            "onboarding": {"prompt": v["onboarding.prompt"]},
            "banner": {"text": v["banner.text"], "until": until} if shown else None}


def check(key, value):
    """The value, tidied, as it can be saved; ValueError saying what is wrong."""
    if key not in KINDS:
        raise ValueError(f"No setting called {key}.")
    value = " ".join((value or "").split())
    kind = KINDS[key]
    if kind == "url" and value and (not re.fullmatch(r"https://[^\s<>\"']+", value) or len(value) > 500):
        raise ValueError(f"{LABELS[key]}: a link starts with https:// and has no spaces.")
    if kind == "text" and len(value) > 200:
        raise ValueError(f"{LABELS[key]}: keep it under 200 characters.")
    if kind == "prompt" and len(value) > 1000:
        raise ValueError(f"{LABELS[key]}: keep it under 1,000 characters.")
    if kind == "date" and value:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{LABELS[key]}: a date, for example 2026-11-30.")
    return value


def changes(config, overrides, form):
    """What a Save writes: (key, value) for each setting the form changed. A value equal to
    app.yaml's is written as None (back to the default), so a later app.yaml change applies."""
    current, default = values(config, overrides), defaults(config)
    out = []
    for key in KINDS:
        if key not in form:
            continue
        value = check(key, form[key])
        if value != current[key]:
            out.append((key, None if value == default[key] else value))
    return out


class Cached:
    """The overrides, read at most every 15 seconds (the self-service app reads them on every
    page). If the database cannot answer, the last ones read (or none: app.yaml's values)."""

    def __init__(self, read, ttl=15):
        self.read, self.ttl = read, ttl
        self._value, self._at = {}, 0.0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            if time.time() - self._at < self.ttl:
                return self._value
            try:
                self._value = self.read()
            except Exception as e:   # the database is down or not migrated yet: app.yaml's values
                log.warning("settings unavailable, using app.yaml's: %s: %s", type(e).__name__, e)
            self._at = time.time()
            return self._value
