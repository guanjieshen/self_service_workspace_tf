# Design, typography and copy

Read the repository's [AGENTS.md](../AGENTS.md) first. These rules are for both apps (the
self-service app and the approvals app, `apps/self-service/`): `templates/`,
`static/app.css`, and every word people read, including error messages from `portal.py`.
`apps/self-service/tests/test_ui.py` enforces the parts a test can check (`Components`,
`Typography`).

## Look

Linear/Vercel-like: neutral surfaces, 1px borders instead of shadows, radii 8px (cards)
and 6px (controls), a 4px spacing scale, all as CSS tokens at the top of `app.css`. The
title is configurable (`self_service_app.title`) and shown in the accent yellow `#FFB81C`;
yellow is otherwise used sparingly (the amber accent). No logo. Status pages lead with
what was asked for. A page that takes more than 150 ms shows a loading bar. Reuse the
existing classes and tokens before adding new ones.

## The design language (2026-10-22)

New pages and changes use this; the request pages (`request.html`, `request_held.html`) are the
reference. The yellow stays the accent (badges, the step in progress, approver questions);
the header's first title word and current tab are `--brand` (Databricks red).

- **Surfaces:** every card, panel and list is one surface: white, 1px `--border`, `--r-lg` (12px)
  corners, `--shadow-card`. Pad a card with `.card-body`, or use `.panel` / `.panel-body`.
- **Card labels:** each card opens with a small ALL CAPS label (`.card-label` or `.panel-title`,
  the same style). A label with an action (a copy button) sits in `.card-head`, with a divider under it.
- **Page header** for one thing (a request): its icon in a small yellow square, the name large in
  monospace with a copy button, its status as a pill at the right, facts as chips under it.
- **Two columns** (`.page-grid`): the work on the left (about two thirds); details on the right as
  label and value rows (`kv`), values right-aligned, IDs in an `.id-chip`.
- **Label and value rows** (`kv`) for facts in a card, never loose lines of text.
- **Steps** with a tick in each finished step and the time it began (to the second) under it.
- **The outcome box** (`.live-message`): what happened on the left, its actions at the right.
- **Copy buttons** (`copy_button`) next to anything someone would paste: names, paths, IDs.
- **Wide pages:** `--page-w` (1280px); forms keep their narrower panel (720px).

## Typography

Use the tokens in `static/app.css` `:root`; never a pixel font size or a numeric weight in a
rule (`tests/test_ui.py` `Typography` fails on them; the brand name's 700 is the one exception,
and `em` only to size monospace against its text). Three weights: regular, medium, semibold.

| Element | Token | Weight |
| --- | --- | --- |
| Page title (h1) | `--text-2xl` (28) | semibold |
| Section heading (h2, `.section-title`) | `--text-lg` (16) | semibold |
| Card heading (h3), AI summary headline | `--text-md` (15) | medium |
| Body text, form labels, buttons, navigation | `--text-base` (14) | regular; medium for labels, buttons and navigation |
| Helper text (`.hint`), meta (`.meta`), descriptions under a title | `--text-sm` (13) | regular |
| Table headers, status badges, small labels, timestamps | `--text-xs` (12) | medium for headers and badges |
| Dashboard figures (`.stat-value`) | `--text-xl` (24) | semibold |
| Glyphs, initials, key hints only | `--text-2xs` (11) | medium |

Text colour has three steps, then meaning:

- `--text`: titles, headings, labels, values people act on.
- `--text-2`: descriptions, helper text, inactive navigation. Readable on white; never lighter.
- `--text-3`: timestamps, counts, optional hints, placeholders.
- `--ok`, `--bad`, `--run` (and `--accent-ink`) only for success, errors, in-progress and
  warnings; links are `--text` underlined (`.text-link`). No colour for decoration.

Spacing comes from the `--s1` to `--s10` scale (4px steps). A heading sits close to its
description (`--s1`); a label, its input and its helper text are one `.field` (6px gaps).
No bold inside paragraphs.

## Copy

- **Card labels are ALL CAPS, always the same way:** the label at the top of a card ("REQUEST
  INFORMATION", "REQUEST DETAILS") is `.card-label` (`--text-xs`, semibold, `--text-2`, uppercase,
  0.06em tracking). Never uppercase anything else, and never style a card label by hand.
- **Sentence case for everything else:** navigation, titles, headings, labels, buttons, badges, table
  headers, tooltips. Capitals only for the first word, proper nouns and acronyms: Databricks,
  SQL, Genie, ServiceNow, Catalog Explorer, Entra ID, FAQ, SOP, AI.
- **Punctuation:** no period on titles, headings, navigation, labels, buttons, badges or table
  headers, and no colon after a heading or label. Full sentences in descriptions, helper text,
  errors and notices end with a period. A placeholder ends with one only if it is a full sentence.
- **Dates and times:** `{{ t | local }}` everywhere (`main.local_time`): a `<time>` element that
  `app.js` shows in the browser's own time zone and locale ("Oct 22, 2026, 2:05 PM MDT"), with
  UTC as the text without JavaScript. Styles: `local` (full), `local("short")` (feeds),
  `local("time")` and `local("date")` (inbox cells). Never `strftime` or `| when` in a template
  (`tests/test_ui.py`). Ages and waits: "6h ago", "3d" (`approvals/_macros.html` `age`).
- **One word per state, the same in both apps:** "Pending approval" (not waiting, awaiting
  or in review), "Reply needed", "In progress", "Completed", "Failed", "Rejected". Request
  names match their form's title: "Request a project schema".
- **Plain words.** Short, direct, the words people use; say what happens. Buttons say the
  action ("Submit request", "Create folder", "Approve"). No marketing or filler: not
  "seamlessly", "empower", "unlock", "streamline", "leverage". Keep technical terms where
  accuracy needs them (schema, catalog, workspace).
- **Say only what is true.** Check the code or the job before describing a rule (a name
  prefix, who can manage something, how long it takes).
- **Leave clear text alone.** A pass is for consistency, not rewriting.
- **Catalog cards** (`cards.py`): the title starts with the verb that says what happens, in 2 to
  5 words; the description is one sentence of about 8 to 15 words on the outcome, without
  repeating the title. Never write a card's approval into its text: the foot shows it from
  `human_approval` (a customer can change it).

  | Verb | When |
  | --- | --- |
  | Request | Starts a request that may wait for an approver |
  | Create | Makes something straight away (no approver) |
  | Open | Goes to a tool, such as Genie One |
  | View | Shows information: a page or a dashboard |
  | Manage | Changes or administers something |
  | Discover | Explores what is available |
  | Add | Adds something that exists, such as an Entra ID group |

  A card that opens Databricks says "Opens in Databricks · Workspace access required" in its
  foot. A quota says what it counts ("0 of 1 used"), never a bare "1/1".

## Components

The app has no front-end framework (no Tailwind, no component library): components are Jinja
macros in `apps/self-service/templates/_components.html`, styled once in `static/app.css`
under "Shared components", on the tokens in `:root`. Use them; `tests/test_ui.py` fails when a
template writes a component's markup itself. Fix a look in the component, never with a
page-specific override.

| Component | For | Variants |
| --- | --- | --- |
| `back(href, label)` | The link back, above a page title | |
| `status_badge(label, quiet=False, pill=False)` | Any status: a dot and a word | The label picks one of five tones in `app.css` (success, danger, attention, reply, neutral); `quiet` for labels beside a title; `pill` for the one status at the top right of a page (a dot and a word in lists and tables) |
| `approval_label(kind, labels)` | Auto-approved / Approval required | A quiet `status_badge` |
| `callout(kind)` (call) | Notes, errors, confirmations, warnings in a box | `info`, `error`, `success`, `warning`; `role`, `action` (a link at the right) |
| `field(id, label, required, hint)` (call) | A label, its control and helper text | A hint that changes with the control goes in the caller |
| `filter_select(name, options, selected, label)` | A filter that applies on change | |
| `details_list(items)` | Facts at the foot of a panel (request ID, dates) | |
| `facts(items)` | Facts about a request, as chips | |
| `check_rows(rows)` | Checks with a tick or a mark | |
| `chip(text, kind)` | A short tag | |
| `empty_state(icon, title, text, href, label)` | A list with nothing in it | |
| `conversation(events, you)` | A request's history | |

Add a component when two pages need the same markup, not before. Keep page layout (grids,
columns, a page's own sections) in the page's template and its section of `app.css`.

## Tokens

Everything visual comes from `:root` in `app.css`: colours (`--text*`, `--ok*`, `--bad*`,
`--accent*`, `--border*`), spacing `--s1` to `--s10`, radii `--r-xs` to `--r-full`, type
(`--text-*`, weights), control heights (`--control-h`, `-sm`, `-lg`: inputs, selects and
buttons share one), icon sizes (`--icon`, `--icon-sm`, `--icon-xs`), `--dot`, `--page-w`.
A new value becomes a token first; no hex colours or pixel sizes in rules where a token exists.

## CSS

- Shared rules live once: a rule two selectors share is one rule (`.list, .inbox { … }`),
  not two copies. Shared components go under "Shared components" in `app.css`, one app's
  pages under its own section.
- Reuse a class or token before adding one; delete a class when its last use goes.
- Markup that is a component (`back`, `status_badge`, `facts`, `check_rows`, `empty_state`,
  `chip`, `conversation`) comes from `templates/_components.html`; `test_ui.py` fails on copies.
