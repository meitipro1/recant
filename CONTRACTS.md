# Recant — specification

Purpose, consensus, state, API, reuse. Written so a reviewer can judge the
design without opening the source, and so a builder can decide whether to lift
it without reading the tests.

**File:** [`contracts/recant.py`](contracts/recant.py)
**Runner:** `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`

## Purpose

Check a new statement against every earlier statement by the same author, and
name the one it contradicts.

The failure it catches is not a wrong answer. It is a *locally correct* answer
that fights the record. Each statement, read alone, is unremarkable; the
contradiction exists only in the pair.

Consensus alone does not reach it, because every validator receives only the new
statement: the earlier record is not part of the input at all, so five nodes
agree confidently on something the same contract already contradicted. The gap
is in what the block is given, and supplying it is what this contract is for.

## Consensus

`gl.vm.run_nondet_unsafe`. One prompt. The block receives the new statement and
every earlier statement by that author, numbered from zero, and returns the
indices it contradicts as a pipe-joined string, or `none`.

**What crosses consensus is a list of integers**, usually of length zero or one.
Not the reasoning, not a similarity score, not prose.

The validator has two layers:

| Layer | Check | Cost |
|---|---|---|
| 1 | Every index is in range, is not the statement being checked, and is not a duplicate. Checkable against data the validator already holds. | Zero. Runs before any prompt. |
| 2 | The index sets match exactly. Not "both found a conflict" — the same conflict. | One prompt. |

Layer 2 is deliberately strict, and the argument matters. Two nodes naming
different statements have agreed about nothing useful. Recording "contradicts
something" would be worse than recording nothing, because it looks like a
finding and names nobody.

## The four outcomes

Derived in the deterministic half, from the block's indices **and from
withdrawal state the block never saw**.

| Verdict | Condition |
|---|---|
| `clear` | no index returned |
| `contradicts` | exactly one index, pointing at a live statement |
| `conflict` | several indices pointing at live statements |
| `stale` | every index points at a withdrawn statement |

`stale` is the interesting one. It is not a weak contradiction; it is the
absence of one. The author already changed their mind, in public, on the record.

## State

Every collection is a **top level contract field**. No storage dataclass
contains a collection, because GenVM cannot construct one: `DynArray[T]()` is
refused, and `gl.storage.inmem_allocate` is for generic dataclasses rather than
for collections. A `Statement` carries the `author_id` it belongs to.

| Field | Type | Note |
|---|---|---|
| `authors` | `DynArray[Author]` | append only |
| `statements` | `DynArray[Statement]` | flat, each carries `author_id` |
| `delegates` | `DynArray[Delegate]` | flat, each carries `author_id` |
| `Author.registrar` | `Address` | owns the record. The identity, not the label |
| `Author.n_clear` … `n_stale` | `u256` | counters for `consistency()` |
| `Statement.by` | `Address` | the account that submitted this statement |
| `Statement.withdrawn` | `bool` | never deleted |
| `Statement.against` | `str` | pipe-joined statement ids |
| `Statement.why` | `str` | leader supplied, sanitised, **not** consensus |
| `Delegate.active` | `bool` | cleared on revoke, the row is kept |

### Scope

`_scope()` walks the flat array and returns earlier statements by the same
author, oldest first, capped at the most recent **24**. Two properties are
load-bearing and both are tested:

- **Only the same author.** Nothing else keeps two records apart.
- **Only earlier statements.** A record is checked against its past, never its
  future, even though later statements exist in the array by then.

The cap is stated rather than hidden. An unbounded prompt is an unbounded cost
and an eventual failure; quietly truncating without saying so would be worse
than the cap.

## Authority

A verdict about an author is worth exactly as much as the record it was computed
from, so the record must be the author's own. `register()` sets
`Author.registrar` to the caller and that address is the identity; `label` is a
display string and proves nothing about who typed it.

| Call | Who | Why |
|---|---|---|
| `register` | anyone | there is no earlier owner to check against |
| `state` | registrar or active delegate | see below |
| `authorise` / `revoke` | registrar | otherwise one delegation takes the record over |
| `withdraw` | registrar | withdrawing rewrites what later checks mean |
| `check` | anyone | an author who chose which statements got audited would audit only the flattering ones |

`state()` carries the weight. The scope a later statement is checked against,
its verdict, and the `consistency()` figure published about the author are all
computed from the rows `state()` writes, so an unauthenticated write there is a
forged premise for every conclusion downstream — and a planted sentence reads
exactly like a real one.

A delegate may speak on a record but may not retract from it, authorise anybody
else, or revoke anybody. Revoking clears `active` and keeps the row, so a former
delegate stays visible, and statements a delegate already made stay on the
record still naming the address that made them.

`Statement.by` records the submitting account on every row, so delegation is
readable rather than implied. A consuming contract should bind to
`registrar(author_id)`, never to the label.

Delegates are capped at **16 active per record**, because `state()` scans them
on every call and an unbounded list is an unbounded scan.

## API

```python
register(label: str)                      # anyone. caller becomes registrar
state(author_id: u256, text: str)         # registrar or authorised delegate
authorise(author_id: u256, who: str)      # registrar only
revoke(author_id: u256, who: str)         # registrar only
withdraw(statement_id: u256)              # registrar only
check(statement_id: u256)                 # anyone, deliberately

verdict(statement_id)   -> str
against(statement_id)   -> str
latest(statement_id)    -> dict
record(author_id)       -> dict
consistency(author_id)  -> dict
registrar(author_id)    -> str
may_state(author_id, who: str) -> bool
delegation(author_id)   -> dict
count() / statement_count() -> u256
```

The first statement on a record is `clear` by construction and **spends no
inference at all** — there is nothing to be inconsistent with, and that is
deterministic.

## Reuse

Governance promises, terms of service across versions, public commitments by a
team, roadmap claims, any record where somebody says things over time and is
expected to stay bound by them.

`consistency()` publishes an inconsistency rate per author. That number is the
product as much as any single verdict is.

The parser and the classifier are pure and copyable on their own — see
[`lib/recant_consensus.py`](lib/recant_consensus.py).
