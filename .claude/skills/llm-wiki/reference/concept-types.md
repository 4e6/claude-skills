# Concept types & templates for a codebase wiki

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
| `Module` | weeks | *What is this subsystem for, and where are its edges?* | `architecture/` |
| `Overview` | weeks | *What is this project?* | bundle root |
| `Open Question` | short | *What don't we know yet?* | `questions/` |
| `Reference` | — | mirrored external material backing a citation | `references/` |

`Module` and `Overview` have the shortest half-life of the durable types, so they
are the ones the sync loop touches most. Keep them about **responsibility and
boundaries**, never about function signatures.

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
status: accepted            # proposed | accepted | superseded
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
those are what the code is for, and they rot within days.

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
confabulating. Delete the page when it is answered — and write the answer as a
`Decision`.

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
