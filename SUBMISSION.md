# Submission

One submission, under **Builder -> Intelligent Contracts**. This repository is
one standalone primitive.

---

## Before you submit, in order

1. **Measure, do not estimate.**

   ```bash
   python scripts/measure.py --write
   ```

   Runs the suite, runs the full mutation pass, and writes both numbers into
   README.md. It refuses to write anything if the suite is red or a mutation
   escapes, so a number in the README is always one that was checked.

2. **Deploy and exercise.** Through the Studio web interface at
   studio.genlayer.com, or `./scripts/deploy.sh studionet` for the CLI route.
   Never put a private key into a file.

3. **Put a refusal on chain, not only a success.** The story the script tells is
   the submission: three statements where the third fights the first, then the
   author withdraws the original and says it again, so the same words come back
   `stale` instead of `contradicts`. A page showing only successes proves the
   file compiles and nothing else.

4. **Open the explorer page and check it.** It must show a Deploy transaction
   **and** method calls with a Consensus Result beside them, and no failed or
   abandoned transaction.

5. **Prove the address is evidence for this repository.**

   ```bash
   python scripts/verify_deployment.py 0xYourAddress
   ```

   Reads the source back out of the deploy transaction on chain, diffs it
   against `contracts/recant.py`, and runs `genvm-lint lint` on those bytes. A
   submission is judged on the deployed source, so a correct repository proves
   nothing on its own if the address points at an earlier draft. Exits non-zero
   if either check fails.

6. **Paste the address** into README.md and into this file, then push.

7. **Upload `brand/social.png`** under Settings → General → Social preview.
   GitHub has no API for this, so it is the one step that must be done by hand.


---

## What changed since the first submission

The first submission was rejected on one point, and it was correct:

> the record's attribution is not currently protected: any account can call
> `state()` for any registered author, inject arbitrary statements into that
> author's history, and change the published consistency result.

That was true. `withdraw()` compared the sender against `Author.registrar`;
`state()` compared nothing. The record is the premise of every verdict the
contract computes, so an unauthenticated write to it forged the premise, and a
planted sentence was indistinguishable from a real one once stored.

The contract now carries an explicit provenance model, and both options the
review offered are in it:

- `state()` requires the registrar of that record, or an address the registrar
  has authorised. Nobody else, on any record.
- `authorise(author_id, who)` and `revoke(author_id, who)` are registrar-only, so
  a delegate can neither appoint nor remove anybody. A delegate may speak on a
  record and may not retract from it, because withdrawing rewrites what every
  later check means.
- `Statement.by` stores the submitting account on every row. `latest()` and
  `record()` publish it, and `registrar()` and `may_state()` let a consuming
  contract bind to an address rather than to a label.
- A static test asserts that every `@gl.public.write` except `register` and
  `check` references the sender, so a new write added later cannot be ungated by
  omission — only on purpose, in a diff.

`check()` is still open to anybody, deliberately: `consistency()` is a claim
about an author, and an author who could choose which of their own statements
got audited would only ever audit the flattering ones. Checking adds no text and
can reach only the verdict the record already implies.

The reasoning, and the two further holes the mutation pass found while this was
being closed, are in [DECISIONS.md](DECISIONS.md).

**The contract was redeployed.** The address below is the fixed source, and
`contracts/recant.py` in this repository is byte-identical to what was deployed.

---

## On chain

Deployed and exercised on studionet at
[`0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9`](https://explorer-studio.genlayer.com/address/0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9).
Thirteen transactions, every one `FINALIZED`, no failed or abandoned transaction
on the page. Every value below was read back from the chain with view calls
after the fact, not copied from a local run.

| # | Transaction | Result |
|---|---|---|
| 1 | deploy | finalized |
| 2 | `register("Example Org")` | record 0 opens, registrar recorded |
| 3 | `state(0, "We will never sell or share user data with any third party.")` | statement 0 |
| 4 | `state(0, "Our uptime target for the coming year is ninety nine percent.")` | statement 1 |
| 5 | `state(0, "We share user data with selected commercial partners.")` | statement 2 |
| 6 | `check(0)` | `clear` — first on the record, no inference spent |
| 7 | `check(1)` | `clear` — unrelated subject |
| 8 | `check(2)` | **`contradicts`**, `against` = `0` |
| 9 | `withdraw(0)` | statement 0 marked withdrawn, still readable |
| 10 | `state(0, "We share user data with commercial partners under contract.")` | statement 3 |
| 11 | `check(3)` | **`stale`**, `against` = `0` |
| 12 | `authorise(0, 0x7777…)` | delegate added |
| 13 | `revoke(0, 0x7777…)` | delegate deactivated, row kept |

Rows 8 and 11 are the point. Statement 2 and statement 3 say the same thing;
between them the author withdrew the promise they both fight. The first is a
live contradiction, the second is a contradiction with something already
retracted, and the contract tells them apart without being told which is which.
Only a withdrawal flag differs, and the block never sees it.

`consistency(0)` returns:

```json
{"statements": 4, "checked": 4, "clear": 2, "contradicts": 1,
 "conflict": 0, "stale": 1, "inconsistent_pct": 25}
```

### The provenance model, exercised

The first submission was rejected because `state()` had no sender check. Rows 12
and 13 put the replacement on chain: `delegation(0)` reads

```json
{"registrar": "0x3e1D268c8B1Ba7d042968ab713467C5631831513",
 "delegates": [{"who": "0x7777777777777777777777777777777777777777", "active": false}]}
```

A revoked delegate keeps its row, so a delegation that existed stays visible.
Every statement also carries the account that submitted it, readable through
`latest()` and `record()`.

### Reproducing the check

```bash
python scripts/verify_deployment.py 0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9
```

Reads the source out of the deploy transaction, compares it to
`contracts/recant.py`, and runs `genvm-lint lint` on those bytes. It reports the
deployed source as identical: pasting into the Studio editor rewrote the line
endings and dropped the final newline, and nothing runs either of those.

---

## Title

```
Recant: self-consistency across a record of statements
```

## Notes (945 characters, the box caps at 1000)

```
Recant checks a new statement against every earlier statement by the same author, and names the one it contradicts, so a record that grows over months stays answerable to itself. In March an organisation says it will never sell user data, in October it says it shares data with partners, and each reads fine alone, because the contradiction lives in the pair rather than in either half. Recant holds the pair: the block receives the new statement and the author's numbered record together, and returns one integer, the index it contradicts, or none, so the judgment stays hard while the thing crossing consensus stays a number. Agreement is exact on the indices, never on whether both nodes merely found something. A record belongs to the address that opened it, only that address or a delegate it authorised may add to one, and every statement stores the account that submitted it, so a verdict is always computed from a record its author owns.
```

## Links

```
GitHub:   https://github.com/meitipro/recant
Contract: https://github.com/meitipro/recant/blob/main/contracts/recant.py
Spec:     https://github.com/meitipro/recant/blob/main/CONTRACTS.md
Decisions https://github.com/meitipro/recant/blob/main/DECISIONS.md
Tests:    https://github.com/meitipro/recant/tree/main/tests
Explorer: https://explorer-studio.genlayer.com/address/0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9
```

---

## What clears the bar, line by line

The category rejects "thin LLM wrappers" and "generic AI decides X demos".

- **The model never decides.** It points at a row in a list the contract owns.
  Which statements are in scope, whether the target is withdrawn, whether a
  multi-way conflict is reportable, and what the record then says are all
  deterministic.
- **The validator function is the contribution.** A free structural check before
  any prompt, then exact agreement on the indices. Explained in
  [CONTRACTS.md](CONTRACTS.md) with the code.
- **Refusing is designed.** `clear`, `stale`, and a failed consensus are all
  better than a confident wrong name.
- **The tests have teeth.** A passing count is a claim; the mutation table in
  the README is evidence, and it is generated by a script that refuses to emit
  a table if anything escapes.
- **It runs with nothing installed.** `pip install pytest && pytest tests/ -q`.
  A reviewer with two minutes can verify the whole thing.
- **The limits are stated.** [DECISIONS.md](DECISIONS.md) says what this cannot
  do, including the scope cap and the fact that it measures self-consistency
  rather than truth.

## One thing worth putting in the notes if there is room

The strongest single line for a reviewer is that **the judgment is hard and the
thing crossing consensus is a number**. Everything else in the design follows
from it.
