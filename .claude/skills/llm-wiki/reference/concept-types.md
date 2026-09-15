# Concept types & templates for a codebase wiki

## Contents

- **The type table** below — every `type`, its half-life, what it answers, and its
  directory. Ordered by half-life, highest first.
- **`Decision` or `Module`?** — the distinction most often got wrong, the rules
  that settle it, the common case that is neither, and what to do to an older
  page whose prose the change has passed by.
- **Templates** for seven of the twelve types: Decision (ADR), Invariant, Module,
  Gotcha, Playbook, Glossary Term, Open Question. The rest — `Integration`,
  `Data Model`, `Convention`, `Overview`, `Reference` — have none; follow the
  frontmatter contract and the nearest template.

OKF leaves `type` free-form (§4.1). This is the vocabulary this skill uses. Stick
to it unless the project genuinely needs a new kind — a consistent `type` set is
what makes `index.md` grouping and type-filtered retrieval useful.

Each type below is ordered by **knowledge half-life** — how long the content
stays true. High half-life first. If a proposed page doesn't fit any of these,
that is a strong hint it belongs in the code, not the wiki.

| `type` | Half-life | Answers | Directory |
|---|---|---|---|
| `Decision` | years | *Why is it this way? What did we reject?* | `decisions/` |
| `Invariant` | years | *What must always hold?* | `invariants/` |
| `Glossary Term` | years | *What does this word mean here?* | `domain/` |
| `Gotcha` | years | *What bites people?* | `gotchas/` |
| `Integration` | months | *How do we talk to this third party?* | `integrations/` |
| `Data Model` | months | *What is stored, and what does it mean?* | `domain/` |
| `Playbook` | months | *How do I do this operational task?* | `playbooks/` |
| `Convention` | months | *How do we write code here?* | `conventions/` |
| `Module` | weeks | *What is this for, where are its edges, and why — where no fork was taken?* | `architecture/` |
| `Overview` | weeks | *What is this project?* | bundle root |
| `Open Question` | short | *What don't we know yet?* | `questions/` |
| `Reference` | — | mirrored external material backing a citation | `references/` |

`Module` and `Overview` have the shortest half-life of the durable types, so they
are the ones the sync loop touches most. Keep them about **responsibility,
boundaries and the reasoning behind both**, never about function signatures.

## `Decision` or `Module`?

The two most-confused types, and the confusion runs one way: `decisions/` gets
reached for by default, because the word *decision* appears in the trigger list
of almost every prompt about recording knowledge. Being a trigger does not make
it a destination. Four rules and a disposition settle nearly every case.

**A `Decision` is written about something that already happened.** It records a
fork taken, under the constraints in play at the time, and it is dated and
numbered because both of those are claims about a moment. An ADR for a design
that has not been built is a plan with a permanent number on it, and the number
outlives the plan changing. If no live alternative existed that somebody might
re-litigate, it is not a decision — whatever else it is.

**Changing something already decided is usually neither.** The two rules above
sort *new* work, and most work is not new. The test is entailment: **does an
existing `Decision` already commit the project to this outcome?** If it does, the
work implements that decision rather than taking one — fixing a bug that made an
existing decision untrue ends with the project doing what was already written down.
Weighing alternatives is not deciding either: refusing to overturn a decision
leaves it standing, and a page recording that refusal adds a number to the ledger
without adding a fork to it.

Entailment rather than *did anything change*, because plenty changes without a
fork being taken. Work that only moves which cases fall which side of a rule an
existing decision already settles is that rule meeting better inputs, and gets no
ADR. Work that settles something the earlier page left open does get one — so
**narrowing or widening a decision's scope is a fork whenever the earlier page
did not already commit to the new scope**, and is not when it did. A decision
that delegates its own scope to a derived list has committed to whatever the list
says next; one that names its bounds has not.

When entailment answers yes, the rule that now has to hold is an `Invariant`, and
the argument for the behaviour belongs to the page that owns the surface.

**A third disposition, which is neither an ADR nor silence.** Making an entailed
outcome true often falsifies a *sentence* in some older decision — the mechanism
it happened to describe. That page is frozen and stays frozen: correct it in
place with a short note saying which claim has been passed by and where the live
answer is, and leave its number, its status and its reasoning alone. A note is
not an amendment; reach for `amends`/`amended_by` only when the new page actually
revises what the old one decided.

**A new surface is a `Module`, and often a `Module` *and* the decisions behind
it.** The page says what the thing is, what it owns and where it stops; the ADRs
say why it is not the alternative. Describing and justifying are different jobs,
and a `Module` that re-argues its own ADRs — or a `Decision` that inventories a
surface — is doing the other one badly. Link them instead: the module names its
decisions in a short section and delegates its *forks* to them, so neither page
repeats the other and superseding one does not strand the other.

**Delegating forks is not delegating every why.** A `Module` carries the argument
for behaviour nobody forked over — why the boundary falls there, which case it
was drawn around, what it costs. Only an argument with a fork behind it
delegates, and the rules above are what decide that; a live alternative is
necessary for a `Decision`, never sufficient for one. Read instead as *send all
rationale to an ADR*, this leaves an author holding an argument with nowhere to
put it but a new number.

---

## Templates

### Decision (ADR)

Immutable once accepted. Never rewrite the reasoning of an accepted decision —
supersede it with a new one and cross-link both.

```markdown
---
type: Decision
title: Use JWTs for service-to-service auth
description: Chose stateless JWTs over a shared session store for internal RPC.
status: accepted            # proposed | accepted | amended | superseded
tags: [auth, security]
timestamp: 2026-07-10T09:00:00Z
superseded_by: /decisions/0009-mtls.md   # only when status: superseded
---

# Context

What forced a choice. Constraints in play at the time.

# Decision

What we chose, stated in one sentence.

# Alternatives considered

* **Shared session store** — rejected: adds a Redis dependency on the hot path.
* **mTLS** — deferred: no cert rotation story yet. See [open question](/questions/cert-rotation.md).

# Consequences

What this makes easy, and what it makes hard. Include the bill: what we now
have to live with.
```

Filename: `NNNN-kebab-slug.md`, zero-padded, monotonic. Never renumber.

### Invariant

The highest-value, lowest-maintenance page type. A property the code must
uphold, plus how it is enforced and what breaks if it isn't.

```markdown
---
type: Invariant
title: Every order has exactly one payment intent
description: Orders and payment intents are 1:1; a second intent means a bug upstream.
tags: [billing]
timestamp: 2026-07-10T09:00:00Z
sources: [src/billing/**]
source_commit: 4f2a1c9e...
---

# Statement

For every row in `orders`, exactly one `payment_intent` exists.

# Why

Stripe charges idempotently per intent. Two intents = double charge.

# Enforced by

* Unique constraint `payment_intents.order_id`.
* [Charge module](/architecture/billing.md) creates the intent inside the order transaction.

# If violated

Customers are double-charged. See [refund playbook](/playbooks/refunds.md).
```

### Module

Responsibility and edges. **No signatures, no line numbers, no file trees** —
those are what the code is for, and they rot within days. Name the decisions
behind the surface and let them carry the forks; keep the reasoning no fork was
taken over. See [`Decision` or `Module`?](#decision-or-module).

```markdown
---
type: Module
title: Auth
description: Issues and verifies sessions for the web and mobile clients.
tags: [auth]
timestamp: 2026-07-10T09:00:00Z
sources: [src/auth/**]
source_commit: 4f2a1c9e...
---

# Responsibility

Owns session issuance, verification, and revocation. Does **not** own user
records — that is [accounts](/architecture/accounts.md).

# Boundaries

* Everything outside this module reaches auth through `verifySession()`. No
  other module reads the session cookie directly.
* Talks to [Redis](/integrations/redis.md) for the revocation list only.

# Decisions

* [JWTs for service-to-service auth](/decisions/0004-jwt-auth.md) — why this is
  stateless, and what a shared session store would have cost.

# Invariants

* [Sessions are revocable within 30s](/invariants/session-revocation.md)

# Gotchas

* [Clock skew breaks JWT verification](/gotchas/clock-skew.md)
```

### Gotcha

Hard-won knowledge that cost someone an afternoon. Cheap to write, enormous
payoff, essentially never goes stale.

```markdown
---
type: Gotcha
title: Clock skew breaks JWT verification
description: Hosts more than 60s ahead of the issuer reject freshly minted tokens.
tags: [auth, ops]
timestamp: 2026-07-10T09:00:00Z
---

# Symptom

`TokenNotYetValid` on a token that was just issued.

# Cause

`nbf` is checked against local time; our issuer and verifier are different hosts.

# Fix

Ensure `chrony` is running. We allow 60s leeway, not more — see
[decision](/decisions/0004-jwt-leeway.md).
```

### Playbook

```markdown
---
type: Playbook
title: Rotate the signing key
description: Steps to rotate the JWT signing key without logging everyone out.
tags: [oncall, auth]
timestamp: 2026-07-10T09:00:00Z
---

# When

Quarterly, or immediately on suspected compromise.

# Steps

1. Add the new key to `JWT_KEYS` as a *verification* key. Deploy. Wait one TTL.
2. Promote it to the signing key. Deploy.
3. Remove the old key after one TTL.

# Verification

`curl /healthz/jwt` reports the active `kid`.
```

### Glossary Term

```markdown
---
type: Glossary Term
title: Settlement
description: The point at which funds irrevocably move, distinct from authorization.
tags: [billing, domain]
timestamp: 2026-07-10T09:00:00Z
---

Authorization reserves funds; **settlement** moves them. Our `orders.status`
says `paid` at *authorization*, not settlement — a naming wart we kept for
backward compatibility. See [decision](/decisions/0007-order-status.md).
```

### Open Question

Explicitly recording what you don't know is what stops the wiki from
confabulating. When it is answered, set `status: answered` and write the answer
where it belongs — a `Decision` only if answering it took a fork, and otherwise
an `Invariant`, a `Module` or whichever type the answer is. `okf.py` sinks an
answered question under *No longer current* rather than deleting it: it is still
a true record of what was once unknown.

```markdown
---
type: Open Question
title: How do we rotate mTLS certs?
description: No rotation story exists; blocks the mTLS decision.
status: open
tags: [security]
timestamp: 2026-07-10T09:00:00Z
---

# Question

Blocks [mTLS](/decisions/0009-mtls.md). Nobody has owned this.
```
