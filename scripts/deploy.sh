#!/usr/bin/env bash
#
# deploy.sh — deploy Recant and leave real consensus evidence on the explorer.
#
#   ./scripts/deploy.sh studionet
#
# A contract page showing only a deploy transaction proves the file compiles and
# nothing else. This deploys AND exercises the contract, so the explorer shows
# method calls with the leader's proposal and the validators' votes beside them.
#
# It also deliberately leaves a REFUSAL on chain. A page showing only successes
# is a weaker demonstration than one showing the primitive decline to answer.
#
# Requires: npm i -g genlayer

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NETWORK="${1:-studionet}"
gold() { printf '\033[33m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

gold "Recant → $NETWORK"
# `network` is a command group, not a value: `genlayer network studionet`
# answers "unknown command" and exits 1, which under `set -e` kills the script
# on its first line.
genlayer network set "$NETWORK"

dim "linting"
# genvm-lint needs its subcommand, and utf-8 stdout: the linter prints a U+2713
# tick on success and dies encoding it under the cp1252 stdout Windows hands a
# child process, reporting a PASSING contract as failed.
PYTHONIOENCODING=utf-8 genvm-lint lint contracts/recant.py

ADDR=$(genlayer deploy --contract contracts/recant.py \
       | grep -oE '0x[0-9a-fA-F]{40}' | head -1)
gold "deployed at $ADDR"

dim "register()  open a record. THIS caller becomes its registrar"
genlayer write "$ADDR" register --args "Example Org" >/dev/null

# Everything below is signed by the same account, which is the registrar. A
# different account calling state() here is refused, which is the point: the
# record has to be the author's own or the verdict computed from it means
# nothing. Delegation exists for the case where it genuinely is not the same
# key -- authorise(0, "0x...") then state() from that address.

dim "state()     three statements, the third fights the first"
genlayer write "$ADDR" state --args 0 "We will never sell or share user data with any third party." >/dev/null
genlayer write "$ADDR" state --args 0 "Our uptime target for the coming year is ninety nine percent." >/dev/null
genlayer write "$ADDR" state --args 0 "We share user data with selected commercial partners." >/dev/null

dim "check(0)    first statement: clear by construction, no inference spent"
genlayer write "$ADDR" check --args 0

dim "check(1)    unrelated subject, expected clear"
genlayer write "$ADDR" check --args 1

dim "check(2)    THE ONE THAT MATTERS -- expected contradicts, naming statement 0"
genlayer write "$ADDR" check --args 2

dim "latest(2)   the verdict and the statement it fights"
genlayer call "$ADDR" latest --args 2

dim "consistency() the rate this contract exists to publish"
genlayer call "$ADDR" consistency --args 0

# --- and now the refusal path, on chain -----------------------------------
dim "withdraw(0) the author takes the original commitment back"
genlayer write "$ADDR" withdraw --args 0 >/dev/null

dim "state()     say it again, now that the original is withdrawn"
genlayer write "$ADDR" state --args 0 "We share user data with commercial partners under contract." >/dev/null

dim "check(3)    expected STALE -- it fights only a withdrawn statement"
genlayer write "$ADDR" check --args 3
genlayer call "$ADDR" latest --args 3

cat <<TXT

  Contract:  $ADDR
  Explorer:  https://explorer-studio.genlayer.com/address/$ADDR

Open that page before submitting. It must show a Deploy transaction AND method
calls with a Consensus Result beside them.

Both paths should be on chain: statement 2 resolved contradicts, statement 3
came back stale.

  registrar(0)   the address that owns the record
  may_state(0, "0x...")   whether some other address could write to it

Neither costs a transaction. Both are worth reading once, because they are what
a consuming contract binds to instead of the label.

Then paste the address into README.md and SUBMISSION.md where {address} appears.

TXT
