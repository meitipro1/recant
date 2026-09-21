# Deploying Recant

Everything you need is on this page. Deploy through the Studio web interface at
**studio.genlayer.com** — paste the contract, deploy, and call the methods
through the form. Never put a private key into a file or hand one to a tool.

---

## 1 · Get the contract

Open the raw file and copy all of it:

**https://raw.githubusercontent.com/meitipro/recant/main/contracts/recant.py**

Take it from that link, not from a local copy. What gets deployed has to be the
file in this repository, byte for byte — the reviewer reads the deployed source
back off the chain and diffs it, and a submission has been rejected for nothing
but a stale address with the fix already sitting in the repo.

Paste it into Studio and deploy. **The constructor takes no arguments.**

---

## 2 · Run the demo

Twelve writes, in this order. Field names are exactly as Studio labels them.

### Open the record

| # | Method | Field | Value |
|---|---|---|---|
| 1 | `register` | `label` | `Example Org` |

### Three statements, where the third fights the first

| # | Method | Field | Value |
|---|---|---|---|
| 2 | `state` | `author_id` | `0` |
| | | `text` | `We will never sell or share user data with any third party.` |
| 3 | `state` | `author_id` | `0` |
| | | `text` | `Our uptime target for the coming year is ninety nine percent.` |
| 4 | `state` | `author_id` | `0` |
| | | `text` | `We share user data with selected commercial partners.` |

### Judge them

| # | Method | Field | Value | Expect |
|---|---|---|---|---|
| 5 | `check` | `statement_id` | `0` | `clear`, and **no inference spent** — the first statement on a record has nothing to be inconsistent with |
| 6 | `check` | `statement_id` | `1` | `clear` — unrelated subject |
| 7 | `check` | `statement_id` | `2` | **`contradicts`**, naming statement `0` |

> ### ⛔ Stop here and read `verdict(2)`
>
> - **`contradicts`** — correct. Carry on.
> - **`clear`** — stop, and tell me. The model did not see the conflict.
> - **transaction failed** — stop, and tell me. The validators disagreed.

### The retraction, and the same claim again

| # | Method | Field | Value |
|---|---|---|---|
| 8 | `withdraw` | `statement_id` | `0` |
| 9 | `state` | `author_id` | `0` |
| | | `text` | `We share user data with commercial partners under contract.` |
| 10 | `check` | `statement_id` | `3` |

Statement 3 says the same thing as statement 2. Between them the author
retracted the promise they both fight, so this one comes back **`stale`** rather
than `contradicts` — from a withdrawal flag the block never sees.

### The provenance model, on chain

| # | Method | Field | Value |
|---|---|---|---|
| 11 | `authorise` | `author_id` | `0` |
| | | `who` | `0x7777777777777777777777777777777777777777` |
| 12 | `revoke` | `author_id` | `0` |
| | | `who` | `0x7777777777777777777777777777777777777777` |

These two put the delegated-provenance model on the explorer. The first
submission was rejected because `state()` had no sender check at all, so a
reviewer will look for this working rather than merely described.

---

## 3 · Reads — free, no transaction

| Call | Argument | Expect |
|---|---|---|
| `verdict` | `2` | `contradicts` |
| `verdict` | `3` | `stale` |
| `record` | `0` | four statements, each with the account that submitted it |
| `consistency` | `0` | `checked 4, clear 2, contradicts 1, stale 1, inconsistent_pct 25` |
| `delegation` | `0` | the registrar, and one revoked delegate |
| `registrar` | `0` | your deploying address |

---

## 4 · Before the portal

```bash
python scripts/verify_deployment.py 0xYourAddress
```

Reads the source back out of the deploy transaction, diffs it against
`contracts/recant.py`, and runs `genvm-lint lint` on those bytes. It must print
**"The address is evidence for this repository. Safe to submit."**

If it prints anything else, do not submit that address.

---

## 5 · Done

This has been run. The contract is live at
[`0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9`](https://explorer-studio.genlayer.com/address/0x70A9197A6b2c573C3Bdb12182Ac36f0feE9622f9),
thirteen transactions, every one finalized, and every outcome above came back as
described. `verify_deployment.py` reports the deployed source as identical to
`contracts/recant.py`, and the state read back off the chain is written up in
[SUBMISSION.md](SUBMISSION.md#on-chain).

The page is kept here because the next deployment of this contract, by anybody,
should follow the same order and stop at the same checkpoint.

One step stays manual: uploading `brand/social.png` under
Settings → General → Social preview. GitHub has no API for it.
