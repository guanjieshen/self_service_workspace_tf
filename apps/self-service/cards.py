"""The catalog's sections and cards, in the order the catalog shows them.

To add a card, add one Card to CARDS: its section, title and text, and where it goes:

- href "/path": a task in this app (it shows how it is approved, from portal.approval_of);
- link "name": a page in Databricks, from links.<name> (config links, and the ones main.catalog
  adds: "workspace", "tour"); the card is left out while that link is not set;
- neither: Coming soon.

A link card with soon=True shows as Coming soon until its link is set, instead of being left out.
A link card's more=(text, link name) is a second, smaller link in its foot, shown when that link is set.

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
    link: str = ""  # a page in Databricks: links.<link>
    icon: str = ""  # _icons.html name; the key when empty
    soon: bool = False  # a link card: Coming soon (not left out) while its link is not set
    opens: str = "Opens in Databricks"   # a link card's foot: where it goes, and what it needs
    more: tuple = ()  # a link card's second link: (its text, links.<name>)


CARDS = [
    Card("persona", "access", "Request workspace access", "Choose the access level you need.", href="/persona"),
    # /open: Genie One in the person's workspace, with the guided tour (the onboarding prompt) the
    # first time (portal.open_workspace).
    Card("open_workspace", "access", "Open Genie One",
         "Explore the data you have access to and try suggested questions to get started.",
         link="workspace", icon="launch", opens="Opens in Databricks · Workspace access required",
         more=("Restart guided tour", "tour")),

    Card("discover", "data", "Discover data",
         "Explore curated datasets organized by business area.", link="discover", icon="search",
         opens="Opens in Databricks · Workspace access required"),
    Card("review_requests", "data", "View data access requests",
         "See the requests you made and the ones made for data you manage.", link="review_requests", icon="requests",
         opens="Opens in Databricks · Workspace access required"),

    Card("schema", "workspace", "Create a personal schema",
         "Create a schema for your own work, with full control over its contents.", href="/schema"),
    Card("project_schema", "workspace", "Request a project schema",
         "Create a dedicated schema for your project.", href="/schema/project", icon="schema"),
    Card("team_schema", "workspace", "Request a team schema",
         "Create a shared schema your team can manage together.", href="/schema/team", icon="schema"),
    # Coming soon for now: a folder is workspace specific, and the hub does not call other
    # workspaces (its job is not deployed). Set href="/folder" again to bring it back.
    Card("folder", "workspace", "Request a workspace folder",
         "Create a shared workspace folder and control who can access it."),
    Card("group_request", "workspace", "Add a group to your workspace",
         "Add an Entra ID group and assign its workspace access level.",
         link="group_request", icon="group", soon=True, opens="Opens your organization's request form"),

    Card("warehouses", "compute", "Manage SQL warehouses", "Create and manage SQL warehouses for your workloads."),
    Card("budget_policy", "compute", "Request a budget policy",
         "Track your team's serverless usage and costs.", icon="budget"),
    Card("cost_dashboard", "compute", "View compute costs",
         "See how much your team spends on compute in this workspace.", icon="chart"),
]


def groups(links):
    """[(section key, title, [card, ...])] for the catalog, each card with where it goes:
    {"card": Card, "href": ..., "external": bool, "ready": bool, "more": (text, href) or None}.
    Link cards whose link is not set are left out; sections with no cards are too."""
    links = links or {}
    out = []
    for key, title in SECTIONS:
        shown = []
        for c in CARDS:
            if c.section != key:
                continue
            if c.link:
                href = links.get(c.link)
                if not href:
                    if c.soon:
                        shown.append({"card": c, "href": "", "external": False, "ready": False, "more": None})
                    continue
                more = c.more and links.get(c.more[1]) and (c.more[0], links[c.more[1]])
                shown.append({"card": c, "href": href, "external": True, "ready": True, "more": more or None})
            else:
                shown.append({"card": c, "href": c.href, "external": False, "ready": bool(c.href), "more": None})
        if shown:
            out.append((key, title, shown))
    return out
