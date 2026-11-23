# Deployment Tracks: Enterprise-Safe and Agent-Accelerated

This portfolio is designed to be explained two ways, because finance teams do not all have the same
IT permissions.

The core control framework is the same in both tracks:

1. Produce the work with a repeatable engine or documented workflow.
2. Capture source assumptions and evidence.
3. Validate with read-only deterministic checks where possible.
4. Use independent AI roles only inside a defined review structure.
5. Keep the human reviewer responsible for final sign-off.

The difference is the orchestration layer around that control framework: either a conservative
enterprise-safe workflow, or an optional orchestration layer that coordinates longer-running work in
approved, agent-enabled environments. In both tracks, AI performs the drafting and review work while
deterministic controls and a human gate keep it defensible.

---

## Track 1: Enterprise-Safe Mode

Use this track when the company cannot approve advanced agent tools, unattended AI workstations, or
third-party automation layers.

<p align="center"><img src="../assets/flows/enterprise-safe-flow.svg" alt="Enterprise-safe deployment flow" width="100%"></p>

### What it uses

- Python
- `openpyxl`
- `pytest`
- Excel-compatible workbooks
- Markdown and JSON evidence
- GitHub Actions or an internal CI equivalent
- human-gated review

### What it avoids

- no dependency on an orchestration layer
- no dependency on autonomous agents
- no need for live model credentials to run the public demo
- no confidential data in the repository
- no uncontrolled autonomous writes to final deliverables

### Why it still works

The finance controls do not depend on a single AI tool. The proof comes from deterministic behavior:
tests, hashes, tie-outs, formula checks, seeded data, and reproducible outputs.

This is the version to show a conservative IT, audit, or compliance audience first.

---

## Track 2: Agent-Enabled Mode

Use this track when the company permits a more advanced AI orchestration setup and wants higher
throughput across multi-step finance workflows.

### Where the orchestration layer fits

An optional orchestration layer can sit above the core engines. It is useful for work that benefits
from longer-running coordination, such as:

- dispatching work through an approved command surface
- keeping coordinated work available without operator supervision
- preparing draft workpapers from a known source bundle
- running background review passes
- packaging handoffs between AI roles
- monitoring multi-step tasks that do not require the operator at the keyboard
- routing findings into a fix packet, review memo, or sign-off checklist
- keeping separate preparer, reviewer, specialist, and audit roles organized
- drafting executive-ready report emails after validation completes

### What does not change

Even in agent-enabled mode:

- the AI does not become the source of truth
- the reviewer does not validate its own work
- deterministic checks still run
- evidence still ties to source
- final sign-off stays human
- client confidentiality and IT rules govern what can be automated

The orchestration layer can speed up execution, but the control layer is what makes the work
defensible.

### Executive package layer

After the engines run, the system can produce a management-ready package:

- report summary
- key findings
- exception list
- validation status
- attachments or links
- recommended next action
- CEO/CFO-ready email draft

The draft can be routed for approval, or sent under a pre-approved policy. The public portfolio
describes the capability without requiring any client to approve automatic email sending on day one.

---

## Client-Friendly Positioning

Use this language when explaining the platform:

> The public demo is intentionally enterprise-safe: Python, Excel, tests, CI, and fictional data.
> Where a client allows more advanced AI tooling, the same framework can be accelerated with an
> optional orchestration layer. Either way, the controls remain the same: independent review,
> deterministic validation, evidence trails, and human sign-off.

This keeps the claim precise. It confirms that orchestration capability exists without making the
runnable public demo depend on tools a corporate environment may not permit.

---

## Practical Example

### Enterprise-safe workflow

1. Run the close, reconciliation, surplus, or 1065 preparation engine.
2. Generate Markdown/JSON/.xlsx evidence.
3. Run the validation engine.
4. Review PASS / REVIEW / FAIL findings.
5. Human reviewer signs off.

### Agent-enabled workflow

1. The operator dispatches a command through an approved command surface.
2. The optional orchestration layer keeps coordinated work available without operator supervision.
3. The orchestration layer coordinates the source bundle, draft preparation, tax package build, and review queues.
4. Triangulate enforces AI separation of duties: preparer, reviewer, specialist, and a deterministic audit pass, with read-only review hash-enforced.
5. Deterministic validation checks the output.
6. Findings are packaged into a fix packet and executive-ready email draft.
7. The human reviewer decides what ships or what gets sent.

Both paths are credible. The right path depends on the client's IT environment.
