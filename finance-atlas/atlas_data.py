"""Data model for the Finance Operations Atlas.

Everything the generated atlas displays lives in this module: the drive map,
the workstream pipelines, the "Find It" lookup table, the recurring calendar,
the color palette, and the page metadata. ``generate.py`` renders this data
into a single self-contained HTML artifact.

All content is fictional. Entities, people, drive letters, paths, platforms,
banks, and figures describe a made-up real-estate investment group ("Demo
Holdings Inc.") and exist only to demonstrate the documentation pattern.
The tax content references public law only (CRA Form T1134 and the Reg. 5907
series), consistent with this portfolio's tax-surplus-engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Palette — Sophon Finance Systems demonstration theme.
# Deep navy chrome, steel-blue interaction accents, muted teal for "live"
# signals, a warm amber for controlled-access markers, warm grey neutrals.
# Text colors are chosen to meet WCAG AA contrast on their backgrounds.
# ---------------------------------------------------------------------------

PALETTE: Dict[str, str] = {
    "ink": "#152b40",         # deep navy — header, primary chrome
    "ink_deep": "#0e1e2e",    # hero gradient start
    "ink_bright": "#1f4a6b",  # hero gradient end
    "steel": "#2f6f92",       # steel blue — interactive accents (AA on white)
    "teal": "#4aa8a0",        # muted teal — live/active accents (non-text)
    "teal_ink": "#256d66",    # teal darkened for AA text on light fills
    "amber": "#c97b2d",       # warm amber — controlled-access accent (non-text)
    "amber_ink": "#8a4f14",   # amber darkened for AA text on light fills
    "slate": "#5c6b7a",       # slate — secondary chrome
    "paper": "#f7f6f3",       # warm grey page background
    "card": "#ffffff",        # card surface
    "line": "#e5e2dc",        # warm grey hairline
    "silver": "#d8d5cf",      # neutral folder spine
    "text": "#2b3540",        # body text
    "muted": "#68727b",       # secondary text (AA on white)
    "grey": "#666f77",        # small labels (AA on white)
    "pale": "#cfe3ee",        # pale steel — light-on-dark accents
}


# ---------------------------------------------------------------------------
# Typed rows
# ---------------------------------------------------------------------------

KV = Tuple[str, str]          # (key, value) briefing row
FindRow = Tuple[str, str, str, str]   # (need, location, notes, category)
CalRow = Tuple[str, str, str]         # (when, what, detail)


@dataclass(frozen=True)
class Folder:
    """One mapped area on a drive, with its briefing."""

    name: str
    tag: str                  # "live" | "ref" | "archive" | "secure"
    desc: str                 # one-line list description
    purpose: str              # briefing paragraph
    keys: Tuple[str, ...] = ()          # key locations (paths)
    rows: Tuple[KV, ...] = ()           # "what to know" rows
    tips: Tuple[str, ...] = ()          # working notes


@dataclass(frozen=True)
class Drive:
    """A drive (or the systems group) in the rail."""

    key: str                  # drive letter, or "SYS"
    label: str
    sub: str
    color: str                # PALETTE key used for the letter chip
    folders: Tuple[Folder, ...] = ()


@dataclass(frozen=True)
class Step:
    """One step in a workstream pipeline."""

    name: str
    detail: str
    io: Tuple[KV, ...] = ()   # input/output/watch-for rows


@dataclass(frozen=True)
class Workstream:
    """A recurring finance process rendered as a clickable pipeline."""

    key: str
    title: str
    kicker: str               # overview-card cadence label
    kicker_color: str         # PALETTE key for the kicker
    blurb: str                # overview-card one-liner
    meta: Tuple[KV, ...] = () # header facts (window, owner, reviewer, ...)
    steps: Tuple[Step, ...] = ()


# ---------------------------------------------------------------------------
# Page metadata
# ---------------------------------------------------------------------------

META: Dict[str, object] = {
    "title": "Finance Operations Atlas — Sophon Finance Systems (demonstration)",
    "description": (
        "Interactive system map of a fictional real-estate finance group: "
        "drives, workstreams, a find-it directory, and the recurring calendar."
    ),
    "wordmark_main": "SOPHON FINANCE SYSTEMS",
    "wordmark_sub": "Finance Operations Atlas (demonstration)",
    "h1": "SOPHON FINANCE SYSTEMS — Finance Operations Atlas (demonstration)",
    "hero_heading": "A finance department, mapped on a single page.",
    "hero_text": (
        "Where records live, how each recurring process runs, and when it "
        "happens — for the finance and accounting group of Demo Holdings Inc., "
        "a fictional real-estate investment company. Every card, drive, and "
        "process step opens a briefing."
    ),
    "chips": [
        ("FYE", "DEC 31"),
        ("3", "REGIONS"),
        ("~120", "LEGAL ENTITIES"),
        ("4", "CORE WORKSTREAMS"),
        ("4", "DRIVES + SYSTEMS"),
    ],
    "hint": (
        "Every card, drive, and process step opens a briefing — and when the "
        "only question is where something lives, Find It answers it fastest."
    ),
    "tags": {
        "live": "Live",
        "ref": "Reference",
        "archive": "Archive",
        "secure": "Controlled",
    },
    "legend": [
        ("teal", "Live / active"),
        ("steel", "Reference"),
        ("amber", "Controlled access"),
        ("grey", "Archive / legacy"),
    ],
    "find_placeholder": (
        "Try: bank statements, trial balance, procedures, draws, T1134, "
        "templates …"
    ),
    "find_nores": (
        "No matches — a broader term (for example “bank”, "
        "“tax”, or “audit”) usually finds it."
    ),
    # "Good to know" cards on the overview. Each action tells the JS layer
    # which view (and optionally which drive/folder) to open.
    "notes": [
        {
            "kicker": "Convention",
            "kicker_color": "steel",
            "title": "File names carry meaning",
            "text": (
                "Entity, period, and bank are encoded in file names — for "
                "example “<Entity> YYYY-MM <Bank>.pdf” for statements "
                "and “YYYY-MM <Entity> <description>.pdf” for entry "
                "support. File new documents to the same pattern."
            ),
            "action": {"view": "find"},
        },
        {
            "kicker": "Registry",
            "kicker_color": "amber_ink",
            "title": "One folder per legal entity",
            "text": (
                "The Entity Registry holds formation documents, agreements, "
                "and bank records for roughly 120 fictional entities — the "
                "map of the corporate structure."
            ),
            "action": {"view": "drives", "drive": "G", "folder": "Entity Registry"},
        },
        {
            "kicker": "Rhythm",
            "kicker_color": "teal_ink",
            "title": "December 31 is year-end",
            "text": (
                "The fiscal year ends December 31 — the external review, tax "
                "filings, schedule rollforwards, and archive conventions all "
                "key off that date."
            ),
            "action": {"view": "calendar"},
        },
    ],
    "footer_left": (
        "Demonstration artifact — all entities, people, paths and figures "
        "are fictional."
    ),
    "footer_right": "Sophon Finance Systems — generated from atlas_data.py",
}


# ---------------------------------------------------------------------------
# Drives — 4 drives + the systems group, 14 folder briefings.
# ---------------------------------------------------------------------------

DRIVES: Tuple[Drive, ...] = (
    Drive(
        key="G",
        label="Group Drive",
        sub="Primary shared drive",
        color="ink",
        folders=(
            Folder(
                name="Treasury",
                tag="live",
                desc="Bank registers, cash JE support, payment queues",
                purpose=(
                    "Daily cash operations for the group: per-entity bank "
                    "register extracts from the GL system, cash journal-entry "
                    "support organized by region, the posting queue for "
                    "platform-generated entries, and the two-stage wire "
                    "approval workflow."
                ),
                keys=(
                    r"G:\Finance\Treasury\Bank Registers",
                    r"G:\Finance\Treasury\Cash JE Support\<Region>",
                    r"G:\Finance\Treasury\Entries to Post",
                    r"G:\Finance\Treasury\Wires - Released & Scheduled",
                ),
                rows=(
                    (
                        "Bank registers",
                        "One register workbook per entity, refreshed from the "
                        "GL system through the close window — the starting "
                        "point for reconciliation.",
                    ),
                    (
                        "Cash JE support",
                        "Region → entity → year → month folders "
                        "holding wire and transfer support.",
                    ),
                    (
                        "Payment queues",
                        "Batches from the AP payment platform and the "
                        "construction-draw platform land in Entries to Post "
                        "before they are recorded.",
                    ),
                    (
                        "Wire workflow",
                        "Every wire clears two approvals: Pending Release → "
                        "Released & Scheduled.",
                    ),
                ),
                tips=(
                    "Statement PDFs follow “<Entity> YYYY-MM <Bank>.pdf” "
                    "— file new statements to the same pattern.",
                    "Month folders for the coming year are pre-created each "
                    "December.",
                    "The authoritative statement archive is the Entity "
                    "Registry; anything here is a working copy.",
                ),
            ),
            Folder(
                name="Accounting",
                tag="live",
                desc="Entity folders, schedules, procedures, audit support",
                purpose=(
                    "The accounting group's working area: one folder per legal "
                    "entity or project (journal entries, draws, lender "
                    "reporting) plus the functional libraries — written "
                    "procedures, standing schedules, recurring-entry masters, "
                    "and audit support."
                ),
                keys=(
                    r"G:\Finance\Accounting\Procedures",
                    r"G:\Finance\Accounting\Schedules\<Entity>",
                    r"G:\Finance\Accounting\Recurring Entries",
                    r"G:\Finance\Accounting\<Entity>\JE Support",
                ),
                rows=(
                    (
                        "Procedures",
                        "The written methodology library — AP, close, "
                        "recurring entries, draws, and banking. Actively "
                        "maintained; check revision dates.",
                    ),
                    (
                        "Schedules",
                        "Prepaids, fixed assets, and accruals — one workbook "
                        "per entity, rolled forward each month.",
                    ),
                    (
                        "Entity folders",
                        "A standard shape per project: journal entries, "
                        "draws, budget updates, and the project binder.",
                    ),
                    (
                        "Audit",
                        "External-review workpapers by fiscal year, split by "
                        "reporting group.",
                    ),
                ),
                tips=(
                    "Entry support PDFs follow “YYYY-MM <Entity> "
                    "<description>.pdf” so completeness checks work.",
                    "Completed projects are archived under _Completed "
                    "Projects — treat those as read-only.",
                ),
            ),
            Folder(
                name="Trial Balances",
                tag="live",
                desc="Regional TB workbooks + fiscal-year snapshots",
                purpose=(
                    "The regional trial-balance workbooks exported from the GL "
                    "system. Three live files — Northwest, Southwest, and "
                    "Central — sit at the root and are refreshed in place each "
                    "close; month-end snapshots are archived by fiscal year "
                    "beneath them."
                ),
                keys=(
                    r"G:\Finance\Trial Balances\Northwest TB.xlsx",
                    r"G:\Finance\Trial Balances\Southwest TB.xlsx",
                    r"G:\Finance\Trial Balances\Central TB.xlsx",
                    r"G:\Finance\Trial Balances\Archive\<FY>",
                ),
                rows=(
                    (
                        "Live files",
                        "One workbook per region with one tab per entity; "
                        "updated in place through each close.",
                    ),
                    (
                        "Archives",
                        "Dated month-end snapshots by fiscal year — the "
                        "history once the live file has moved on.",
                    ),
                    (
                        "Used by",
                        "Cash reconciliation, close reporting, audit "
                        "support, tax workpapers.",
                    ),
                ),
                tips=(
                    "These are shared files — if one is locked, work in a "
                    "local copy and post the result back; the G: version "
                    "is canonical.",
                    "Balance columns are refreshable GL-system queries — open "
                    "in a licensed session to update.",
                ),
            ),
            Folder(
                name="Tax",
                tag="live",
                desc="Compliance tracker, filings, cross-border workstream",
                purpose=(
                    "The tax filing system, organized by jurisdiction and "
                    "entity family: the compliance tracker, state and local "
                    "filings, information returns, and the cross-border "
                    "workstream supporting the Canadian parent, Demo Holdings "
                    "Inc."
                ),
                keys=(
                    r"G:\Finance\Tax\Compliance Tracker",
                    r"G:\Finance\Tax\State & Local",
                    r"G:\Finance\Tax\T1134\Surplus & ACB",
                    r"G:\Finance\Tax\Structure Charts",
                ),
                rows=(
                    (
                        "Tracker",
                        "The department-wide filing calendar — one row per "
                        "entity per filing, from extension to confirmation.",
                    ),
                    (
                        "Entity families",
                        "One folder per family — for example Maple Fund LP, "
                        "Cedar Mezz Holdings LLC, and Harborview Partners LP — "
                        "with project entities inside each.",
                    ),
                    (
                        "Cross-border",
                        "The T1134 folder holds the annual information-return "
                        "packages; Surplus & ACB is the working area for the "
                        "pool calculations.",
                    ),
                    (
                        "External preparers",
                        "Income tax returns are prepared externally under "
                        "annual engagement letters.",
                    ),
                ),
                tips=(
                    "Historical filings are foldered by fiscal year — the "
                    "December 31 convention.",
                    "Structure-chart decks visualize the Entity Registry; "
                    "the registry itself is authoritative.",
                ),
            ),
            Folder(
                name="Entity Registry",
                tag="secure",
                desc="Legal-entity records + secure bank archive",
                purpose=(
                    "The master legal-entity registry — one standardized "
                    "folder per entity holding formation documents, "
                    "agreements, consents, and licensing — plus the "
                    "controlled-access bank-statement archive."
                ),
                keys=(
                    r"G:\Finance\Entity Registry\Corporate Records",
                    r"G:\Finance\Entity Registry\Bank Records",
                    r"G:\Finance\Entity Registry\Corporate Records\_New Entity",
                ),
                rows=(
                    (
                        "Corporate records",
                        "Folder names encode jurisdiction and status (for "
                        "example “— DE” or “dissolved”), so "
                        "the list itself reads as a status report.",
                    ),
                    (
                        "Bank records",
                        "The authoritative per-entity statement archive, by "
                        "fiscal year, plus cash procedure sets and "
                        "reconciliation templates.",
                    ),
                    (
                        "New entities",
                        "An intake template standardizes new-entity setup — "
                        "banking, GL codes, and registry folder in one pass.",
                    ),
                ),
                tips=(
                    "Access is controlled — request it through the "
                    "Controller's office if a folder will not open.",
                    "When the corporate structure is in question, this "
                    "registry is the authoritative answer.",
                ),
            ),
            Folder(
                name="Reporting & Archive",
                tag="ref",
                desc="Quarterly reporting, project tracker, frozen history",
                purpose=(
                    "Group reporting and frozen history: the quarterly "
                    "project-reporting packages, the master project tracker, "
                    "monthly combined financials, and legacy areas kept "
                    "read-only."
                ),
                keys=(
                    r"G:\Finance\Reporting\Quarterly Reports\<Year>",
                    r"G:\Finance\Reporting\Project Tracker",
                    r"G:\Finance\Reporting\Monthly Financials",
                    r"G:\Finance\_Archive",
                ),
                rows=(
                    (
                        "Quarterly cadence",
                        "Each region reports quarterly on a rotating schedule; "
                        "meeting folders hold the per-project packages.",
                    ),
                    (
                        "Tracker",
                        "One clearly labeled live workbook; dated archive "
                        "copies are point-in-time snapshots.",
                    ),
                    (
                        "Legacy areas",
                        "Read-only corporate history — nothing in _Archive is "
                        "part of a live process.",
                    ),
                ),
                tips=(
                    "When something looks stale, check _Archive before "
                    "assuming it is lost.",
                ),
            ),
        ),
    ),
    Drive(
        key="W",
        label="Workstation",
        sub="Local working copies",
        color="steel",
        folders=(
            Folder(
                name="Desktop staging",
                tag="live",
                desc="Monthly staging & local working copies",
                purpose=(
                    "The local scratch area for the current cycle: monthly "
                    "close support, local trial-balance copies for the "
                    "moments the shared workbook is locked, and the "
                    "workpaper batch in progress. The canonical version of "
                    "anything here lives on G:."
                ),
                keys=(
                    r"W:\Staging\<current month>",
                    r"W:\Staging\Trial Balance (local copies)",
                ),
                rows=(
                    (
                        "Rule of thumb",
                        "Anything worth keeping is filed back to its G: home "
                        "— treat local copies as scratch space, not records.",
                    ),
                ),
                tips=(
                    "Local copies drift — verify dates against the G: master "
                    "before reusing a prior month's file.",
                ),
            ),
            Folder(
                name="Engagement workspaces",
                tag="live",
                desc="Per-engagement builds & status handoffs",
                purpose=(
                    "One working folder per engagement — workbook builds and "
                    "the monthly reconciliation cycle — each carrying its "
                    "process notes and a status handoff for continuity "
                    "between cycles."
                ),
                keys=(r"W:\Documents\Engagements\<engagement>",),
                rows=(
                    (
                        "Contents",
                        "Build folders per entity, review notes, and a status "
                        "document that says exactly where the work stands.",
                    ),
                ),
                tips=(
                    "Each cycle ends by refreshing the handoff notes — read "
                    "them first when resuming the work.",
                ),
            ),
        ),
    ),
    Drive(
        key="L",
        label="Learning Library",
        sub="Training & methodology",
        color="teal_ink",
        folders=(
            Folder(
                name="Training recordings",
                tag="ref",
                desc="Process walkthroughs on video",
                purpose=(
                    "The recorded training library — screen walkthroughs of "
                    "GL-system navigation, month-end close, journal-entry "
                    "schedules, and audit preparation, each with a "
                    "transcript, indexed in one master workbook."
                ),
                keys=(r"L:\Training\Recordings",),
                rows=(
                    (
                        "Coverage",
                        "GL detail pulls, closing training, schedule "
                        "maintenance, audit preparation, and entity tax "
                        "reviews.",
                    ),
                ),
                tips=(
                    "The master index workbook lists sessions by topic — the "
                    "fastest way to find the right recording.",
                    "New joiners: watch the closing series before your first "
                    "month-end.",
                ),
            ),
            Folder(
                name="Methodology notes",
                tag="ref",
                desc="Written notes & structure diagrams",
                purpose=(
                    "Written methodology notes and corporate-structure "
                    "diagrams that supplement the procedures library, "
                    "maintained as processes evolve."
                ),
                keys=(r"L:\Training\Methodology Notes",),
                rows=(),
                tips=(
                    "One notebook is the designated current copy; the others "
                    "are dated snapshots.",
                ),
            ),
        ),
    ),
    Drive(
        key="R",
        label="Regional Share",
        sub="Alternate mount + templates",
        color="slate",
        folders=(
            Folder(
                name="Groups (mirror of G:)",
                tag="ref",
                desc="Same content as G: via another path",
                purpose=(
                    "R: is a second mount of the storage behind G:, so the "
                    "Treasury, Accounting, Tax, and Entity Registry trees are "
                    "reachable under both letters. Older documents may link "
                    "through either path; both resolve to the same folders."
                ),
                keys=(r"R:\Shared\Groups\...",),
                rows=(
                    (
                        "Why it matters",
                        "Count or sweep files under a single drive letter, "
                        "or everything shows up twice.",
                    ),
                ),
                tips=(
                    "If a legacy link fails on R:, try the same path on G: "
                    "before escalating.",
                ),
            ),
            Folder(
                name="Templates & branding",
                tag="ref",
                desc="Letterhead, memo & report templates",
                purpose=(
                    "Corporate identity assets: letterhead, memo, agenda, and "
                    "report-cover templates, plus the shared reporting "
                    "templates used for outward-facing documents."
                ),
                keys=(r"R:\Shared\Templates",),
                rows=(),
                tips=(
                    "Use these templates for anything leaving the department "
                    "— they carry the current identity standards.",
                ),
            ),
        ),
    ),
    Drive(
        key="SYS",
        label="Systems",
        sub="GL · payments · portals",
        color="amber_ink",
        folders=(
            Folder(
                name="The GL system",
                tag="live",
                desc="General ledger & job cost — system of record",
                purpose=(
                    "The system of record for the general ledger and job "
                    "costing. Every trial balance, GL detail pull, and "
                    "journal posting runs through it, and its spreadsheet "
                    "extracts feed the workpapers on G:."
                ),
                keys=(r"GL desktop client + refreshable spreadsheet queries",),
                rows=(
                    (
                        "Company codes",
                        "Each entity has a GL company code — folder names on "
                        "G: often carry it in parentheses.",
                    ),
                    (
                        "Extracts",
                        "Trial-balance and capital-account workbooks use "
                        "refreshable GL queries rather than pasted values.",
                    ),
                ),
                tips=(
                    "Open query-backed workbooks in a licensed session so the "
                    "figures refresh.",
                ),
            ),
            Folder(
                name="Payment & banking platforms",
                tag="live",
                desc="AP payments · construction draws · bank portals",
                purpose=(
                    "The transaction platforms that feed the drive: the AP "
                    "payment platform, the construction-draw platform, and "
                    "the bank portals (for example First Meridian Bank) whose "
                    "statements land in the secure archive."
                ),
                keys=(r"Platform batches land in G:\Finance\Treasury\Entries to Post",),
                rows=(
                    (
                        "Flow",
                        "Platform batches queue for posting, the entries are "
                        "recorded in the GL, and the support is filed under "
                        "the entity and month.",
                    ),
                ),
                tips=(
                    "Platform user guides live beside the procedures library "
                    "in G:\\Finance\\Accounting\\Procedures.",
                ),
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Workstreams — 4 pipelines.
# ---------------------------------------------------------------------------

WORKSTREAMS: Tuple[Workstream, ...] = (
    Workstream(
        key="recon",
        title="Month-End Cash Reconciliation",
        kicker="Monthly · business days 1–4",
        kicker_color="steel",
        blurb=(
            "Bank registers → regional trial balances → tied-out "
            "balances → Controller package."
        ),
        meta=(
            ("Window", "Business days 1–4"),
            ("Owner", "Senior Accountant"),
            ("Reviewer", "Controller"),
            ("Regions", "Northwest · Southwest · Central"),
        ),
        steps=(
            Step(
                name="Refresh bank registers",
                detail=(
                    "Per-entity register workbooks are extracted from the GL "
                    "system into the Treasury area — the evidence base for "
                    "the month's reconciliation."
                ),
                io=(
                    ("Input", "GL bank-register extracts, one per entity"),
                    ("Location", r"G:\Finance\Treasury\Bank Registers"),
                    (
                        "Watch for",
                        "Stale extracts — an extract is only usable once its "
                        "file date covers the full month.",
                    ),
                ),
            ),
            Step(
                name="Open regional trial balances",
                detail=(
                    "The three regional trial-balance workbooks — one tab per "
                    "entity — are the canvas the reconciliation is performed "
                    "on."
                ),
                io=(
                    ("Input", "Northwest / Southwest / Central TB workbooks"),
                    ("Location", r"G:\Finance\Trial Balances"),
                    (
                        "Watch for",
                        "File locks — work in a local copy, then post the "
                        "result back to the shared file.",
                    ),
                ),
            ),
            Step(
                name="Tie each account to the bank",
                detail=(
                    "For every cash and loan account, the ledger balance is "
                    "compared to the bank-confirmed balance. Dormant "
                    "accounts are verified as having had no activity, and "
                    "immaterial differences are documented with a comment on "
                    "the account."
                ),
                io=(
                    (
                        "Method",
                        "Reconcile to the bank-confirmed balance, with the "
                        "register providing the supporting detail.",
                    ),
                    (
                        "Rules",
                        "Zero-activity clearance for dormant accounts · a "
                        "documented materiality threshold · every comment "
                        "references its account.",
                    ),
                ),
            ),
            Step(
                name="Flag & document exceptions",
                detail=(
                    "Material differences receive sequential exception "
                    "identifiers and status color coding, and the "
                    "explanation is documented beside each item for review."
                ),
                io=(
                    ("Output", "Exception list + status colors + comments"),
                    ("Convention", "EX-<MM>-## exception identifiers"),
                ),
            ),
            Step(
                name="Package for the Controller",
                detail=(
                    "Each region closes with a summary memo and an evidence "
                    "package. Workbooks are referenced by link to their G: "
                    "location rather than attached."
                ),
                io=(
                    ("Output", "Three regional packages"),
                    ("Recipient", "Controller"),
                    ("Timing", "Complete by business day 4"),
                ),
            ),
            Step(
                name="Post & carry forward",
                detail=(
                    "Correcting entries are posted, balances are re-verified, "
                    "and structural items carry to next month's checklist so "
                    "nothing is rediscovered from scratch."
                ),
                io=(
                    ("Then", "Close reporting picks up from here."),
                ),
            ),
        ),
    ),
    Workstream(
        key="surplus",
        title="Foreign-Affiliate Surplus & ACB (T1134)",
        kicker="Annual · public-law framework",
        kicker_color="amber_ink",
        blurb=(
            "Per-entity workbooks that carry the surplus pools and adjusted "
            "cost base behind the T1134 information returns."
        ),
        meta=(
            ("Cycle", "Annual, entity by entity"),
            ("Preparer", "Tax staff"),
            ("Reviewer", "Tax Reviewer"),
            ("Feeds", "T1134 information returns"),
        ),
        steps=(
            Step(
                name="Gather source data",
                detail=(
                    "US partnership returns per entity-year and GL "
                    "capital-account extracts are assembled as the factual "
                    "base, alongside a published FX-rate reference."
                ),
                io=(
                    (
                        "Inputs",
                        "Form 1065 returns · capital-account extracts · "
                        "published central-bank FX rates",
                    ),
                    ("Location", r"G:\Finance\Tax\T1134\Surplus & ACB"),
                ),
            ),
            Step(
                name="Build the workbook",
                detail=(
                    "Each calculation follows the standard template — one "
                    "workbook per entity-owner pairing, with evidence, "
                    "calculation, and summary tabs so every figure traces to "
                    "a source."
                ),
                io=(
                    ("Template", r"...\Surplus & ACB\_Template"),
                    (
                        "Convention",
                        "One workbook per entity-owner pairing; evidence "
                        "→ calculation → summary lineage.",
                    ),
                ),
            ),
            Step(
                name="Apply the published rules",
                detail=(
                    "Surplus pools (exempt vs taxable), pre-acquisition "
                    "capital, and ACB move under the public Reg. 5907 series "
                    "and related ITA provisions: income adds to pools, "
                    "distributions consume them in statutory order, and ACB "
                    "moves only on capital events."
                ),
                io=(
                    (
                        "Reference",
                        "Public Canadian Income Tax Regulations (the Reg. "
                        "5907 series) — see this portfolio's "
                        "tax-surplus-engine for a working model.",
                    ),
                    (
                        "Watch for",
                        "FX treatment on distributions — document the rate "
                        "basis used and keep it consistent.",
                    ),
                ),
            ),
            Step(
                name="Verify independently",
                detail=(
                    "Before review, a second independent pass re-derives "
                    "every balance from the source data."
                ),
                io=(
                    ("Output", "Verification notes filed with the entity package"),
                ),
            ),
            Step(
                name="Reviewer sign-off",
                detail=(
                    "Workbooks go to the Tax Reviewer; approved versions are "
                    "filed to the Approved subfolder with the sign-off kept "
                    "alongside."
                ),
                io=(
                    (
                        "Rule",
                        "File the version the reviewer signs off on, and "
                        "retain the full version history alongside it.",
                    ),
                    ("Location", r"...\Surplus & ACB\Approved"),
                ),
            ),
            Step(
                name="Feed the filings",
                detail=(
                    "Approved surplus and ACB balances support the annual "
                    "T1134 information-return packages for the Canadian "
                    "parent."
                ),
                io=(
                    ("Output", "One package per foreign affiliate"),
                    ("Location", r"G:\Finance\Tax\T1134"),
                ),
            ),
        ),
    ),
    Workstream(
        key="close",
        title="Monthly Close & Recurring Entries",
        kicker="Monthly close",
        kicker_color="teal_ink",
        blurb=(
            "Standing schedules → recurring entries → GL posting "
            "→ support packages by entity."
        ),
        meta=(
            ("Window", "First week after month-end"),
            ("Owner", "Accounting staff"),
            ("System", "The GL system"),
            ("Entities", "Holding companies + active projects"),
        ),
        steps=(
            Step(
                name="Roll standing schedules",
                detail=(
                    "Per-entity schedule workbooks — prepaids, fixed assets, "
                    "and accruals — are rolled forward for the month."
                ),
                io=(
                    ("Location", r"G:\Finance\Accounting\Schedules\<Entity>"),
                    (
                        "Convention",
                        "One workbook per entity per schedule type, one "
                        "column per period.",
                    ),
                ),
            ),
            Step(
                name="Prepare recurring entries",
                detail=(
                    "The annual recurring-entry master plus the allocation "
                    "workbooks drive the month's standard entries."
                ),
                io=(
                    ("Location", r"G:\Finance\Accounting\Recurring Entries"),
                    (
                        "Reference",
                        "The recurring-entries procedure in the methodology "
                        "library — kept current.",
                    ),
                ),
            ),
            Step(
                name="Post to the GL",
                detail=(
                    "Entries are posted to the general ledger, and each "
                    "schedule is tied back to its trial-balance account."
                ),
                io=(
                    (
                        "Check",
                        "Schedule ending balance = trial-balance balance, "
                        "account by account.",
                    ),
                ),
            ),
            Step(
                name="File support packages",
                detail=(
                    "Each posted entry gets a support PDF named to the "
                    "convention, assembled for the month and filed into the "
                    "entity's JE Support folder."
                ),
                io=(
                    ("Location", r"G:\Finance\Accounting\<Entity>\JE Support"),
                    (
                        "Watch for",
                        "Inconsistent file names — the completeness checks "
                        "only work when the convention is followed exactly.",
                    ),
                ),
            ),
            Step(
                name="Assemble reporting",
                detail=(
                    "The month's combined financials are assembled once the "
                    "schedules and trial balances tie out."
                ),
                io=(
                    ("Location", r"G:\Finance\Reporting\Monthly Financials"),
                ),
            ),
            Step(
                name="Year-end rollforward",
                detail=(
                    "At fiscal year-end, every schedule workbook is rolled "
                    "into a new-year copy and the prior year is archived."
                ),
                io=(
                    ("Timing", "Each January (FYE December 31)"),
                ),
            ),
        ),
    ),
    Workstream(
        key="compliance",
        title="Compliance & Audit Cycle",
        kicker="Quarterly · annual",
        kicker_color="steel",
        blurb=(
            "State and local filings, estimated payments, information "
            "returns, and the annual external review."
        ),
        meta=(
            ("Cadence", "Quarterly + annual"),
            ("External", "Audit firm (review) · tax preparers (returns)"),
            ("Approval", "Tax Reviewer signs off payments"),
            ("Tracker", r"G:\Finance\Tax\Compliance Tracker"),
        ),
        steps=(
            Step(
                name="Quarterly state & local filings",
                detail=(
                    "Revenue extracts feed the filing worksheets; returns are "
                    "filed per entity and payment confirmations are filed "
                    "with the approvals."
                ),
                io=(
                    ("Location", r"G:\Finance\Tax\State & Local"),
                    ("Volume", "Dozens of entities per quarter"),
                ),
            ),
            Step(
                name="Estimated payments & extensions",
                detail=(
                    "Vouchers and extensions are prepared per entity per "
                    "year, each paired with its acceptance confirmation."
                ),
                io=(
                    (
                        "Check",
                        "Every extension has an acceptance confirmation "
                        "beside it.",
                    ),
                ),
            ),
            Step(
                name="Annual external review",
                detail=(
                    "A fresh audit folder is set up each year: year-end "
                    "trial balances and ledgers are exported entity by "
                    "entity, and a request-list workbook is assembled for "
                    "each reporting group."
                ),
                io=(
                    ("Location", r"G:\Finance\Accounting\Audit\<FY>"),
                    ("Convention", "“<Entity> TB 1231YY” + a YTD ledger per entity"),
                ),
            ),
            Step(
                name="Income tax returns",
                detail=(
                    "External preparers work under annual engagement "
                    "letters, with the compliance tracker carrying each "
                    "entity from extension through filed return."
                ),
                io=(
                    ("Location", r"G:\Finance\Tax\Compliance Tracker"),
                ),
            ),
            Step(
                name="January information returns",
                detail=(
                    "AP payment data is assembled per region, matched to "
                    "payee tax forms, filed, and the confirmations are kept "
                    "per entity."
                ),
                io=(
                    ("Location", r"G:\Finance\Accounting\AP\Information Returns"),
                    (
                        "Watch for",
                        "Missing payee forms — the usual bottleneck; chase "
                        "them before year-end.",
                    ),
                ),
            ),
            Step(
                name="Canadian information returns",
                detail=(
                    "The compliance year finishes with the Canadian parent's "
                    "T1134 packages, which draw on the surplus & ACB "
                    "workstream."
                ),
                io=(
                    ("Location", r"G:\Finance\Tax\T1134"),
                ),
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Find It — the lookup table. (need, location, notes, category)
# ---------------------------------------------------------------------------

FINDIT: Tuple[FindRow, ...] = (
    (
        "Bank statements (archive)",
        r"G:\Finance\Entity Registry\Bank Records\<Entity>",
        "Controlled access; by fiscal year; “<Entity> YYYY-MM <Bank>.pdf”",
        "Treasury",
    ),
    (
        "Bank registers (live)",
        r"G:\Finance\Treasury\Bank Registers",
        "One workbook per entity; refreshed through the close window",
        "Treasury",
    ),
    (
        "Trial balances — live",
        r"G:\Finance\Trial Balances",
        "Northwest / Southwest / Central workbooks; updated in place",
        "GL",
    ),
    (
        "Trial balances — history",
        r"G:\Finance\Trial Balances\Archive\<FY>",
        "Dated month-end snapshots by fiscal year",
        "GL",
    ),
    (
        "Cash JE support",
        r"G:\Finance\Treasury\Cash JE Support\<Region>",
        "Entity → year → month folders holding wire/transfer support",
        "Treasury",
    ),
    (
        "Wire approvals in progress",
        r"G:\Finance\Treasury\Wires - Pending Release",
        "Two-approval workflow; cleared items move to Released & Scheduled",
        "Treasury",
    ),
    (
        "Posting queue",
        r"G:\Finance\Treasury\Entries to Post",
        "Batches from the AP payment and construction-draw platforms",
        "Treasury",
    ),
    (
        "Written procedures",
        r"G:\Finance\Accounting\Procedures",
        "AP · close · recurring entries · draws · banking",
        "Methodology",
    ),
    (
        "Recurring-entry master",
        r"G:\Finance\Accounting\Recurring Entries",
        "One workbook per year; allocation workbooks sit beside it",
        "GL",
    ),
    (
        "Standing schedules",
        r"G:\Finance\Accounting\Schedules\<Entity>",
        "Prepaids, fixed assets, accruals; rolled forward monthly",
        "GL",
    ),
    (
        "JE support PDFs",
        r"G:\Finance\Accounting\<Entity>\JE Support",
        "“YYYY-MM <Entity> <description>.pdf”; FY archive subfolders",
        "GL",
    ),
    (
        "Audit workpapers",
        r"G:\Finance\Accounting\Audit\<FY>",
        "Year-end TBs and ledgers per entity, split by reporting group",
        "Audit",
    ),
    (
        "Request-list workbooks",
        r"G:\Finance\Accounting\Audit\<FY>\<Group>",
        "Rolled forward each year for the external review",
        "Audit",
    ),
    (
        "Structure charts (entity map)",
        r"G:\Finance\Tax\Structure Charts",
        "Annual entity-structure decks; the registry is authoritative",
        "Structure",
    ),
    (
        "Legal-entity records",
        r"G:\Finance\Entity Registry\Corporate Records",
        "One folder per entity: formation, agreements, consents, licensing",
        "Structure",
    ),
    (
        "New-entity intake form",
        r"G:\Finance\Entity Registry\Corporate Records\_New Entity",
        "Intake template standardizing new-entity setup",
        "Structure",
    ),
    (
        "Reconciliation templates & cash SOPs",
        r"G:\Finance\Entity Registry\Bank Records\_Recon Library",
        "Cash procedure set + regional reconciliation templates",
        "Methodology",
    ),
    (
        "Compliance tracker",
        r"G:\Finance\Tax\Compliance Tracker",
        "The live filing calendar — one row per entity per filing",
        "Tax",
    ),
    (
        "State & local filings",
        r"G:\Finance\Tax\State & Local",
        "Quarterly; per-entity returns + payment confirmations",
        "Tax",
    ),
    (
        "Surplus & ACB workbooks",
        r"G:\Finance\Tax\T1134\Surplus & ACB",
        "One workbook per entity-owner pairing; Approved subfolder",
        "Tax",
    ),
    (
        "Surplus workbook template",
        r"G:\Finance\Tax\T1134\Surplus & ACB\_Template",
        "Evidence → calculation → summary tab lineage",
        "Tax",
    ),
    (
        "Capital-account extracts",
        r"G:\Finance\Tax\T1134\Surplus & ACB\Capital Extracts",
        "Per-entity GL capital detail, refreshable queries",
        "Tax",
    ),
    (
        "Historical FX rates",
        r"G:\Finance\Tax\T1134\Surplus & ACB",
        "Published central-bank reference rates, kept with the working area",
        "Tax",
    ),
    (
        "T1134 packages",
        r"G:\Finance\Tax\T1134",
        "By year; one package per foreign affiliate + proof of delivery",
        "Tax",
    ),
    (
        "Information-return season files",
        r"G:\Finance\Accounting\AP\Information Returns",
        "By year; AP payment data matched to payee tax forms",
        "AP",
    ),
    (
        "Payee tax forms",
        r"G:\Finance\Accounting\AP\Payee Forms",
        "Match payees before the January filings",
        "AP",
    ),
    (
        "Card-program logs",
        r"G:\Finance\Accounting\Card Programs",
        "Per program: statements · coding log · entries · posted packets",
        "AP",
    ),
    (
        "Project draw packages",
        r"G:\Finance\Accounting\<Project>\Draws",
        "One folder per draw with pay applications + reconciliation",
        "Projects",
    ),
    (
        "Quarterly report packages",
        r"G:\Finance\Reporting\Quarterly Reports\<Year>",
        "Meeting folders rotating by region each quarter",
        "Reporting",
    ),
    (
        "Master project tracker",
        r"G:\Finance\Reporting\Project Tracker",
        "One clearly labeled live workbook; dated copies are snapshots",
        "Reporting",
    ),
    (
        "Report & letterhead templates",
        r"R:\Shared\Templates",
        "Identity standards for outward-facing documents",
        "Templates",
    ),
    (
        "Training recordings",
        r"L:\Training\Recordings",
        "Master index workbook lists sessions by topic",
        "Learning",
    ),
    (
        "Methodology notes",
        r"L:\Training\Methodology Notes",
        "One designated current notebook; the rest are dated snapshots",
        "Learning",
    ),
)


# ---------------------------------------------------------------------------
# Calendar — the recurring rhythm. (when, what, detail)
# ---------------------------------------------------------------------------

CALENDAR: Dict[str, Tuple[CalRow, ...]] = {
    "monthly": (
        (
            "Business days 1–4",
            "Cash reconciliation",
            "Three regions → Controller package",
        ),
        (
            "First week",
            "Recurring entries & standing schedules",
            "Post to the GL; tie schedules to the trial balance",
        ),
        (
            "First week",
            "JE support packages",
            "Support PDFs filed per entity to the naming convention",
        ),
        (
            "Mid-month",
            "Card-program cycle",
            "Statement → coding log → entry → posted packet",
        ),
        (
            "Monthly",
            "Project draws",
            "Lender and equity draws per active project",
        ),
        (
            "Monthly",
            "Bank statements filed",
            "To the controlled per-entity archive",
        ),
    ),
    "quarterly": (
        (
            "Quarter + 30 days",
            "State & local filings",
            "Per-entity returns; confirmations filed with approvals",
        ),
        (
            "Per filing schedule",
            "Estimated payments",
            "Vouchers per entity, paired with confirmations",
        ),
        (
            "Rotating",
            "Quarterly project reporting",
            "Region rotation; packages to G:\\Finance\\Reporting",
        ),
        (
            "Quarterly",
            "Compliance tracker review",
            "Status pass with the Tax Reviewer",
        ),
    ),
    "annual": (
        (
            "December 31",
            "Fiscal year-end",
            "Schedules, audit, and filings key off this date",
        ),
        (
            "January",
            "Schedule rollforward",
            "Clone standing schedules to the new year; archive priors",
        ),
        (
            "January",
            "Information-return season",
            "AP data → payee-form match → file → confirmations",
        ),
        (
            "Q1–Q2",
            "External review",
            "Year-end TBs, request lists, representation letters",
        ),
        (
            "Per filing schedule",
            "Income tax returns",
            "External preparers; tracked entity by entity",
        ),
        (
            "Per CRA schedule",
            "T1134 information returns",
            "Supported by the surplus & ACB workstream",
        ),
    ),
}
