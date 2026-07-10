# OKF v0.1 — condensed normative reference

Distilled from the spec at
`https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`
(announced in [How the Open Knowledge Format can improve data
sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/)).
Kept here so the skill works offline. Section numbers match the upstream spec.

OKF is deliberately tiny: *a directory of markdown files with YAML frontmatter*.
No schema registry, no central authority, no required tooling.

## §2 Terminology

- **Knowledge Bundle** — the directory tree; the unit of distribution.
- **Concept** — one unit of knowledge = one markdown document.
- **Concept ID** — the file's bundle-relative path minus `.md`.
  `architecture/auth.md` → `architecture/auth`.
- **Frontmatter** — YAML block delimited by `---` at the top of the file.
- **Body** — everything after the frontmatter.

## §3.1 Reserved filenames

`index.md` and `log.md` have defined meaning at **any** level of the tree and
MUST NOT be used as concept documents. Every other `.md` file is a concept.

## §4.1 Frontmatter

**`type` is the only required field.** It is a short free-form string
(`Module`, `Decision`, `Playbook`, …). Type values are *not* registered
centrally; consumers MUST tolerate unknown types.

Recommended, in priority order:

| Field | Meaning |
|---|---|
| `title` | Display name. Consumers MAY derive one from the filename if absent. |
| `description` | One sentence. Feeds `index.md` entries, search snippets, previews. |
| `resource` | URI uniquely identifying the underlying asset. Omit for abstract concepts. |
| `tags` | YAML list of short strings. |
| `timestamp` | ISO 8601 datetime of last meaningful change. |

Producers MAY add any other keys. Consumers SHOULD preserve unknown keys and
MUST NOT reject documents that carry them.

## §4.2 Body

Standard markdown. Producers SHOULD favour **structural** markdown — headings,
lists, tables, fenced code — over freeform prose, because structure aids both
human reading and agent retrieval.

No body sections are required. These headings carry conventional meaning:

| Heading | Purpose |
|---|---|
| `# Schema` | Structured description of an asset's columns/fields. |
| `# Examples` | Concrete usage examples. |
| `# Citations` | External sources backing claims in the body (§8). |

## §5 Cross-linking

Plain markdown links — **not** `[[wikilinks]]`. Two forms:

- **Absolute (bundle-relative)** — begins with `/`, resolved from the bundle
  root: `[customers](/tables/customers.md)`. **Recommended**: survives moving
  the *linking* document.
- **Relative** — `[sibling](./other.md)`.

A link asserts an untyped relationship; the *kind* of relationship is conveyed
by surrounding prose, not the link. Consumers **MUST tolerate broken links** — a
link to a missing target is not malformed, it may simply be knowledge not yet
written. (So forward-referencing a concept you intend to write is legal.)

## §6 Index files

`index.md` MAY appear in any directory. It enumerates that directory's contents
to support **progressive disclosure** — letting a reader or agent see what
exists before opening anything.

Index files **contain no frontmatter**, with exactly one exception: the
bundle-root `index.md` MAY declare `okf_version: "0.1"` (§11). This is the only
place frontmatter is permitted in an index.

Body is one or more `#` sections of bullets:

```markdown
# Section / Group Heading

* [Title 1](relative-url-1) - short description of item 1
* [Subdirectory](subdir/) - short description of the subdirectory
```

Entries SHOULD reuse the linked concept's `description`. Producers MAY generate
indexes; consumers MAY synthesize one when absent.

## §7 Log files

`log.md` MAY appear at any level to record changes to that scope. Flat,
date-grouped, **newest first**. Date headings MUST be ISO 8601 `YYYY-MM-DD`.

```markdown
# Directory Update Log

## 2026-05-22
* **Update**: Added new table reference for [Customer Metrics](/tables/customer-metrics.md).
* **Creation**: Established the [Dataplex Playbook](/playbooks/dataplex.md).
```

The leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is
convention, not requirement.

## §8 Citations

Claims sourced from external material SHOULD be listed under a trailing
`# Citations` heading, numbered:

```markdown
# Citations

[1] [BigQuery announcement](https://cloud.google.com/blog/...)
[2] [Internal runbook](https://wiki.acme.internal/data/quality)
```

Citation links MAY be absolute URLs, bundle-relative paths, or paths into a
`references/` subdirectory that mirrors external material as first-class
concepts.

## §9 Conformance

A bundle is conformant if:

1. Every non-reserved `.md` file has a parseable YAML frontmatter block.
2. Every frontmatter block has a non-empty `type`.
3. Every `index.md` / `log.md` present follows §6 / §7.

Consumers MUST NOT reject a bundle for: missing optional fields, unknown `type`
values, unknown extra frontmatter keys, broken cross-links, or missing
`index.md`. This permissiveness is intentional — bundles grow, get refactored,
and are partly agent-generated.

## §11 Versioning

`<major>.<minor>`. Minor = backward-compatible additions. Major = breaking.
Declare the target version via `okf_version: "0.1"` in the root `index.md`
frontmatter. Consumers that do not understand a declared version SHOULD attempt
best-effort consumption rather than refusing the bundle.

## Non-goals (§1)

OKF does **not** define a fixed taxonomy of types, prescribe storage/serving/query
infrastructure, or replace domain schemas (Avro, Protobuf, OpenAPI). It
*references* those; it does not subsume them.
