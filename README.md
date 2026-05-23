# Autonomous Red Teaming

Autonomous Red Teaming is a learning project for building an AI-assisted security testing system that can discover, analyze, and learn from vulnerabilities in authorized environments.

The end goal is not a generic scanner. The goal is an autonomous security assistant that can produce useful outcomes: real findings, clear evidence, practical remediation, reusable skills, and a growing understanding of how to test systems safely and effectively.

HackerOne is the long-term proving ground. The project should first mature in local and guided learning labs, then move toward real-world bug bounty targets only when authorization, scope control, rate limiting, evidence collection, and human approval gates are reliable.

## Mission

Build an AI-driven security testing system that can:

- understand an authorized target
- decide what testing strategies are relevant
- run approved checks through controlled tools
- collect reproducible evidence
- explain why a weakness matters
- recommend practical fixes
- create reusable skills from confirmed discoveries
- avoid duplicate skills, tools, and findings
- improve its strategy over time

The system should help a human security tester move faster without removing human responsibility.

## Core principles

These principles should guide every design decision in the project.

1. Authorization first

   No target should be tested unless it is explicitly listed in the authorization registry. If the target is missing, expired, ambiguous, or out of scope, the system must refuse to run.

2. Fail closed

   When the system is uncertain about scope, risk, identity, rate limits, or allowed actions, it should stop and ask for human review.

3. Evidence over claims

   A finding is not valid just because the AI says it exists. A finding needs evidence, reproduction notes, affected components, severity reasoning, and remediation guidance.

4. Human approval for risk

   The AI may propose higher-risk actions, but it should not execute them automatically. Active exploitation, destructive testing, credential access, persistence, lateral movement, and availability-impacting tests require explicit human approval and should be disabled by default.

5. Learn in labs before real targets

   New skills should be developed and tested against intentionally vulnerable or owned systems before they are considered for real-world use.

6. Reuse before creating

   The system should inspect existing skills and tools before creating a new one. New skills should add distinct value.

7. Logs are part of the product

   Every important decision should be auditable: target selection, authorization checks, risk decisions, tool execution, AI reasoning summaries, findings, and user approvals.

8. Autonomy is earned

   The system should begin as a supervised assistant. It earns more autonomy only after it proves that it can enforce scope, avoid duplicate work, collect evidence, and handle failures safely.

## Safety and authorized use

This project is intended only for systems where testing is explicitly authorized, such as:

- personal labs
- intentionally vulnerable applications
- CTF or training environments
- owned applications and infrastructure
- internal company systems with written approval
- contracted security assessments with defined scope
- bug bounty programs whose policy explicitly allows the planned testing

The tool must not be used against third-party systems without written authorization.

The project should prioritize discovery, analysis, reproducible evidence, and human review. It should not become an unsupervised attack system. The commercial value should come from trustworthy findings, high-quality reports, and repeatable security insight.

## Commercial thesis

Someone may eventually pay for this tool if it can reliably reduce the time between "I have an authorized target" and "I have a useful security finding."

The product should optimize for:

- high-signal findings instead of noisy scan output
- reproducible evidence instead of vague claims
- clear remediation instead of raw tool dumps
- learned testing skills instead of one-off scripts
- safe automation instead of uncontrolled autonomy
- auditability for teams, customers, and bug bounty programs

The strongest commercial version of this project is a controlled AI security assistant that helps a human tester find, validate, explain, and report vulnerabilities faster.

## Non-goals

The project should not attempt to build or optimize:

- malware
- persistence mechanisms
- credential theft
- social engineering automation
- denial-of-service testing
- stealth or evasion features
- unauthorized scanning of public targets
- automatic exploitation against real third-party systems

These boundaries keep the project focused on legitimate security testing and make it more credible as a product.

## Testing environments

The project uses two environment classes: learning environments and real-world validation environments.

### Environment 1: learning lab

The learning lab is where the tool should be built first. These targets are intentionally vulnerable, owned, or controlled, which makes them suitable for repeatable experiments.

Good learning targets include:

- OWASP Juice Shop
- OWASP WebGoat
- PortSwigger Web Security Academy labs
- TryHackMe rooms and learning paths
- Hack The Box Academy and beginner labs
- local applications created specifically for testing

The first recommended target is OWASP Juice Shop because it is local-friendly, intentionally vulnerable, well documented, and useful for testing web security tooling.

The learning lab should be used to:

- build the authorization registry
- validate safe discovery skills
- test report quality
- practice vulnerability categories
- measure whether the tool can rediscover known issues
- improve the AI reasoning loop before real external targets

### Environment 2: real-world validation

HackerOne is the long-term validation environment. The goal is for the tool to eventually help discover real vulnerabilities in public or private bug bounty programs where testing is explicitly authorized.

Before any HackerOne testing, the system must:

- read and record the program policy
- record the policy URL and review date
- add exact in-scope targets to the authorization registry
- record out-of-scope targets and forbidden actions
- respect rate limits and automation restrictions
- require human approval before higher-risk tests
- produce clear evidence and remediation guidance

The tool should not run autonomous tests against HackerOne programs until the learning lab version can reliably enforce scope, risk limits, rate limits, and reporting requirements.

## Authorization registry

The authorization registry is the source of truth for what the tool may test.

Before running any scan, probe, exploit simulation, or automated test, the system must check the registry. This check should happen in code, not only in AI instructions.

An authorization entry should include:

- target identifier
- target type
- owner or approving party
- authorization source
- allowed testing
- disallowed testing
- valid start date
- valid end date
- rate limits
- risk limits
- notes about excluded systems or actions
- policy URL when applicable
- last reviewed date

Example:

```json
{
  "id": "local-juice-shop",
  "environment": "learning-lab",
  "target": "http://localhost:3001",
  "target_type": "web-application",
  "owner": "Personal lab",
  "authorized_by": "Winton Gee",
  "authorization_source": "owned-local-container",
  "expected_identity": {
    "title_contains": "OWASP Juice Shop",
    "marker_path": "/rest/admin/application-version",
    "marker_contains": "version"
  },
  "allowed_testing": [
    "reconnaissance",
    "web-misconfiguration-checks",
    "safe-validation"
  ],
  "disallowed_testing": [
    "destructive-actions",
    "credential-access",
    "persistence",
    "denial-of-service"
  ],
  "rate_limit": {
    "max_requests_per_second": 4,
    "max_concurrent_requests": 1
  },
  "risk_limit": "medium",
  "valid_from": "2026-05-10",
  "valid_until": "2026-12-31",
  "policy_url": null,
  "last_reviewed": "2026-05-21",
  "notes": "Local Docker Juice Shop on :3001 (owned). Safe-active checks authorized; no destructive/DoS/credential testing. Identity is fingerprint-verified before each engagement."
}
```

The `expected_identity` block is verified at runtime: before any engagement the
guard fetches the target and confirms it is the application it claims to be
(title + a marker endpoint), so a check can never run against the wrong host that
happens to answer on the right port. This is enforced in code and fails closed.

## Risk levels

Every skill and action should have a risk level.

| Level | Name | Description | Default behavior |
| --- | --- | --- | --- |
| 0 | Informational | Reads local data, documentation, previous findings, or target metadata without touching a remote system. | Allowed when target context is authorized. |
| 1 | Passive | Makes low-volume requests that should not change state, such as fetching headers or public metadata. | Allowed for authorized targets. |
| 2 | Safe active | Sends controlled requests that may test validation behavior but should not damage data or affect availability. | Requires explicit authorization and logging. |
| 3 | Intrusive | Attempts exploitation, authentication boundary testing, or actions that may change state. | Requires human approval. Disabled by default. |
| 4 | Prohibited | Destructive, stealthy, persistent, availability-impacting, or credential-theft behavior. | Not allowed in this project. |

The system started with levels 0 and 1 only. It now also runs level 2 (safe
active) where a target's authorization explicitly elevates its `risk_limit` to
`medium` — the current Juice Shop lab does this, enabling the level-2
`exposed_sensitive_paths` skill. Level 3+ remains gated behind the (not-yet-built)
human-approval gate; level 4 is never allowed. The `RiskEngine` honors each
target's authorized limit directly and falls back to a conservative project
ceiling only for a missing or malformed authorization.

## System architecture

The system should be built as a set of small components with clear responsibilities.

```text
User / Operator
  |
  v
AI Planner
  |
  v
Authorization Guard -> Risk Engine -> Human Approval Gate
  |
  v
Tool Runner
  |
  v
Evidence Store -> Finding Generator -> Report Writer
  |
  v
Skill Registry -> Deduplication Engine -> Learning Loop
```

### Components

- AI Planner: reasons about the target, chooses candidate skills, proposes next actions, and summarizes results.
- Authorization Guard: checks every target and action against the authorization registry.
- Risk Engine: classifies proposed actions by risk level and blocks actions above the allowed threshold.
- Human Approval Gate: requires explicit approval for higher-risk actions.
- Tool Runner: executes approved tools with rate limits, timeouts, and logging.
- Evidence Store: stores raw outputs, screenshots, HTTP metadata, command summaries, and reproduction notes.
- Finding Generator: turns evidence into structured findings.
- Report Writer: produces human-readable reports with severity, impact, evidence, and remediation.
- Skill Registry: stores reusable testing capabilities.
- Deduplication Engine: prevents duplicate skills, tools, and findings.
- Learning Loop: proposes new skills from confirmed findings and failed tests.

## AI boundaries and data handling

The AI is the reasoning layer, not the authority layer. Code should enforce authorization, risk limits, rate limits, and approval gates.

The AI may:

- summarize target context
- propose test plans
- choose from approved skills
- explain tool output
- draft reports
- propose new skills for review

The AI must not:

- bypass authorization checks
- execute tools directly without the tool runner
- override risk limits
- approve its own high-risk actions
- invent evidence that was not observed
- silently send sensitive target data to external services

Evidence may contain secrets, tokens, internal URLs, customer data, or other sensitive information. The system should:

- store evidence locally by default
- redact obvious secrets from reports and AI prompts
- keep raw evidence separate from report summaries
- log when evidence is sent to an AI model or external service
- avoid sending credentials, private keys, session tokens, or customer data to external AI services unless explicitly approved

The project should assume that security evidence is sensitive.

## Operating workflow

Every run should follow this sequence:

1. Intake

   The user provides a target, goal, and environment.

2. Authorization check

   The system verifies that the target is in the authorization registry and that the authorization has not expired.

3. Scope and risk review

   The system identifies allowed actions, disallowed actions, rate limits, and maximum risk level.

4. Plan

   The AI planner selects relevant skills and proposes a test plan.

5. Approval

   Low-risk actions may run automatically if allowed. Higher-risk actions require human approval.

6. Execute

   The tool runner executes approved skills with logging, timeouts, and rate limits.

7. Collect evidence

   The system stores raw outputs and structured observations.

8. Validate

   The system checks whether the evidence supports a real finding.

9. Report

   Confirmed findings are written with impact, reproduction notes, and remediation.

10. Learn

   The system updates the skill registry only if the new knowledge is distinct and useful.

## Skill model

A skill is a reusable testing capability. Skills should be small, inspectable, and scoped to a specific type of discovery.

A skill should include:

- id
- name
- category
- purpose
- risk level
- required inputs
- expected outputs
- target types
- tools used
- detection logic
- validation method
- evidence requirements
- references
- duplicate-detection tags
- creation source
- last tested environment

Example:

```json
{
  "id": "web.missing_security_headers",
  "name": "Missing Security Headers Check",
  "category": "web-security",
  "purpose": "Identify missing HTTP response headers that reduce browser-side attack resistance.",
  "risk_level": 1,
  "target_types": ["web-application"],
  "inputs": ["url"],
  "outputs": ["missing_headers", "observed_headers", "recommendations"],
  "tools": ["http-client"],
  "detection_logic": "Fetch the root URL and compare response headers against the required header list.",
  "validation_method": "Confirm headers are absent in the HTTP response for the tested route.",
  "evidence_requirements": ["request_url", "status_code", "response_headers"],
  "tags": ["headers", "http", "browser-security", "misconfiguration"],
  "created_from": "manual-seed",
  "last_tested_environment": "learning-lab"
}
```

## Finding model

A finding is a confirmed or suspected weakness backed by evidence.

A finding should include:

- id
- title
- target
- affected component
- vulnerability category
- severity
- confidence
- evidence
- reproduction steps
- impact
- remediation
- skill used
- authorization id
- timestamps
- confirmation status

Example:

```json
{
  "id": "finding-2026-0001",
  "title": "Missing Content-Security-Policy Header",
  "target": "http://localhost:3001",
  "affected_component": "HTTP response headers",
  "category": "web-misconfiguration",
  "severity": "low",
  "confidence": "confirmed",
  "evidence": {
    "status_code": 200,
    "missing_headers": ["content-security-policy"]
  },
  "reproduction_steps": [
    "Send an HTTP GET request to the target root URL.",
    "Inspect the response headers.",
    "Confirm that Content-Security-Policy is not present."
  ],
  "impact": "Missing browser security headers can increase exposure to client-side attack chains.",
  "remediation": "Add a Content-Security-Policy header appropriate for the application.",
  "skill_id": "web.missing_security_headers",
  "authorization_id": "local-juice-shop",
  "status": "confirmed"
}
```

## Learning loop

The learning loop is how the system improves.

The system may propose a new skill when:

- a finding does not map cleanly to an existing skill
- a failed test reveals a useful new detection pattern
- a confirmed vulnerability requires a repeatable validation method
- multiple findings share a pattern that can be generalized

Before adding a new skill, the system should:

- search existing skills by id, name, category, and tags
- compare purpose and detection logic
- check whether an existing skill can be extended instead
- require human review for generated skills
- test the skill in the learning lab

New skills should not be used against real-world targets until they have been validated in a controlled environment.

## Deduplication

Deduplication should apply to skills, tools, and findings.

The system should detect duplicates by comparing:

- normalized names
- categories
- tags
- target types
- detection logic
- affected components
- evidence patterns
- remediation guidance

When a possible duplicate is found, the system should prefer:

1. reusing the existing skill
2. extending the existing skill
3. creating a new skill only when the behavior is meaningfully different

## Initial scope

The first implementation should be intentionally narrow.

Build:

- a local authorization registry
- a local OWASP Juice Shop target
- a target authorization check
- a minimal skill registry
- one low-risk web skill
- one finding format
- one report format
- an audit log

The first skill should be a safe check such as missing security headers. This provides a practical first loop without jumping straight to exploitation.

## Suggested project structure

```text
autonomous-red-teaming/
  README.md
  authorizations/
    authorized-targets.json
  environments/
    learning-lab.json
    hackerone-template.json
  skills/
    web/
      missing-security-headers.json
  findings/
    .gitkeep
  reports/
    .gitkeep
  logs/
    .gitkeep
  src/
    authorization/
    audit/
    discovery/
    reporting/
    risk/
    skills/
    tools/
  tests/
    authorization/
    skills/
```

## Roadmap

Status as of 2026-05-23: Phases 0–5 are built and tested. The learning loop is
closed end to end — the LLM Learner and a deterministic end-of-engagement
distiller (`src/memory/distill.py`) both propose human-reviewed skills, five safe
web skills ship, and a measurement harness (`python -m src.measure`) scores
rediscovery against `groundtruth/juice-shop.json` (currently 100%, 5/5, live).
Still open within Phase 5: a report writer and embedding/semantic dedup. Phases
6–7 are not started.

### Phase 0: project foundation — done

- Define this README as the project charter.
- Create the folder structure.
- Add example authorization, skill, and finding files.
- Decide the first language and runtime.

### Phase 1: authorization and safety — done

- Implement target authorization checks.
- Implement expiration checks.
- Implement risk-level enforcement.
- Add audit logs for all blocked and allowed actions.

### Phase 2: first discovery loop — done

- Run OWASP Juice Shop locally.
- Add a missing security headers skill.
- Execute the skill only after authorization passes.
- Save evidence and generate a finding report.

### Phase 3: skill registry and deduplication — done (exact dedup; semantic dedup pending)

- Store skills as structured files.
- Search existing skills before adding new ones.
- Add duplicate detection for skills and findings.
- Add tests for deduplication behavior.

### Phase 4: AI planning layer — done (Claude reasoners active when ANTHROPIC_API_KEY is set)

- Let the AI propose a test plan from available skills.
- Require the authorization guard to approve every proposed action.
- Store AI reasoning summaries in the audit log.
- Keep execution deterministic where possible.

### Phase 5: learning loop — done (LLM + deterministic distillation; measured by rediscovery rate)

- Let the AI propose new skills from confirmed findings.
- Require human review before saving generated skills.
- Validate generated skills in the learning lab.
- Track skill performance over time.

### Phase 6: external training platforms

- Use TryHackMe, Hack The Box, and PortSwigger labs for broader practice.
- Keep each target represented in the authorization registry.
- Respect each platform's rules and acceptable use policies.

### Phase 7: HackerOne pilot

- Choose a beginner-friendly program with clear scope.
- Manually record the program policy.
- Start with passive or low-risk skills only.
- Submit only high-quality, reproducible findings.
- Do not automate beyond what the program allows.

## Definition of done

A feature is not done until:

- it checks authorization before touching a target
- it has a defined risk level
- it logs what it did
- it stores useful evidence
- it handles failure safely
- it has focused tests where practical
- it does not bypass the project safety rules

A finding is not done until:

- the affected target is identified
- the evidence is attached
- the severity is explained
- the reproduction steps are clear
- the remediation guidance is practical
- the authorization record is linked

A skill is not done until:

- its purpose is clear
- its inputs and outputs are defined
- its risk level is assigned
- its evidence requirements are listed
- it has been tested in a learning environment
- it has been checked for duplication

## Success metrics

The project is succeeding when it can:

- safely refuse out-of-scope targets
- rediscover known issues in learning labs
- generate useful reports from evidence
- reuse existing skills instead of duplicating them
- create reviewed skills from new patterns
- explain why each action is allowed
- explain why each finding matters
- eventually produce valid bug bounty reports on authorized targets

## Learning goals

This project should build practical skill in:

- cybersecurity fundamentals
- web application security
- red team methodology
- AI agent architecture
- tool orchestration
- vulnerability discovery
- evidence collection
- security reporting
- safe automation design
- product thinking for security tools

## Guiding product idea

The product should be valuable because it helps users find and understand real security weaknesses faster. The best version of this tool is not reckless autonomy. It is controlled autonomy: the AI thinks, plans, learns, and explains, while the system enforces scope, safety, evidence quality, and human approval.
