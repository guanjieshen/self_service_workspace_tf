"""The catalog's sections and cards, in the order the catalog shows them.

To add a card, add one Card to CARDS: its section, title and text, and where it goes:

- href "/path": a task in this app (it shows how it is approved, from portal.approval_of);
- link "name": a page in Databricks, from config links.<name> (or "onboarding", the Genie One
  link); the card is left out while that link is not set;
- neither: Coming soon.

A new section goes in SECTIONS; its key is also its FAQ link (self_service_app.faq.<key>, and
settings.FAQS). Keys stay the same when a title changes: Settings stores the FAQ links by key.
"""
from dataclasses import dataclass

SECTIONS = [
    ("access", "Get started"),
    ("data", "Data"),
    ("workspace", "Build"),
    ("compute", "Compute & cost"),
]


@dataclass(frozen=True)
class Card:
    key: str        # the task's key (portal.APPROVAL, links.sop.<key>), or the card's own name
    section: str    # a SECTIONS key
    title: str
    text: str
    href: str = ""  # a page of this app
    link: str = ""  # a page in Databricks: config links.<link>, or "onboarding"
    icon: str = ""  # _icons.html name; the key when empty


CARDS = [
    Card("persona", "access", "Request workspace access", "Choose the access level you need.", href="/persona"),
    Card("onboarding", "access", "Genie One Onboarding",
         "Ask Genie to look at the data you can use and suggest the best questions to start with.", link="onboarding", icon="ask"),

    Card("discover", "data", "Discover data",
         "Browse the data your organization has curated, by business domain, in Databricks.", link="discover", icon="search"),
    Card("review_requests", "data", "Review data access requests",
         "See the data access requests you made in Databricks, and the ones others made for your data.", link="review_requests", icon="requests"),

    Card("schema", "workspace", "Request a personal schema",
         "Create your own schema in the workspace catalog, with full permissions to manage it.", href="/schema"),
    Card("project_schema", "workspace", "Request a project schema",
         "Create a schema with a name you choose, for a project of yours.", href="/schema/project", icon="schema"),
    Card("team_schema", "workspace", "Request a team schema",
         "Create a schema your team manages together, so it stays when people move on.", href="/schema/team", icon="schema"),
    Card("folder", "workspace", "Request a workspace folder",
         "Create a shared workspace folder and control who can access it.", href="/folder"),

    Card("warehouses", "compute", "Manage SQL warehouses", "Create and manage SQL warehouses sized to your workload."),
    Card("budget_policy", "compute", "Request a budget policy",
         "Get a serverless budget policy, so your team's serverless usage is charged to your team.", icon="budget"),
    Card("cost_dashboard", "compute", "View cost dashboard",
         "See what your team spends on compute in this workspace, and where it goes.", icon="chart"),
]


def groups(links, onboarding=None):
    """[(section key, title, [card, ...])] for the catalog, each card with where it goes:
    {"card": Card, "href": ..., "external": bool, "ready": bool}. Link cards whose link is not
    set are left out; sections with no cards are too."""
    out = []
    for key, title in SECTIONS:
        shown = []
        for c in CARDS:
            if c.section != key:
                continue
            if c.link:
                href = onboarding if c.link == "onboarding" else (links or {}).get(c.link)
                if not href:
                    continue
                shown.append({"card": c, "href": href, "external": True, "ready": True})
            else:
                shown.append({"card": c, "href": c.href, "external": False, "ready": bool(c.href)})
        if shown:
            out.append((key, title, shown))
    return out
