"""Integration tests, run against GenLayer Studio with gltest.

    pip install genlayer-test
    pip install genlayer-test
    GENLAYER_STUDIO=1 gltest --network studionet tests/test_integration.py

They are opt in: without GENLAYER_STUDIO set they skip, so that
`pytest tests/ -q` stays clean on a machine that has genlayer-test
installed but no Studio to talk to.

These are slower than the other two suites and they prove something different:
that the contract deploys, that storage round-trips, that the deterministic
gates fire, and that the whole leader-plus-validator cycle completes against a
real runtime rather than against tests/glsim.py.

Everything here exercises the deterministic half, which needs no inference: a
record opens, statements are added, one is withdrawn, and the refusal paths are
checked. The judging path costs a prompt and belongs in a manual Studio run.
"""

import os

import pytest

# gltest is only needed for this file. Skip cleanly when it is absent so that
# `pytest tests/` works out of the box on a machine with nothing installed but
# pytest, and still runs everything in test_logic.py and test_e2e.py.
gltest = pytest.importorskip(
    "gltest",
    reason="integration tests need genlayer-test and a running Studio: "
           "pip install genlayer-test, then GENLAYER_STUDIO=1 gltest",
)
from gltest import get_contract_factory, get_accounts        # noqa: E402
from gltest.assertions import tx_execution_succeeded         # noqa: E402


# The second half of the same guard, and it is the half that bites.
#
# importorskip above covers "genlayer-test is not installed". It does NOT cover
# "genlayer-test IS installed and there is no Studio to talk to", which is the
# common case for anybody who reviews GenLayer contracts: the plugin loads,
# collects this file, and every test in it fails on a connection error rather
# than skipping. `pytest tests/ -q` then reports a wall of ERRORs on a
# repository whose README promises a clean offline run, and the reader cannot
# tell an unreachable network from a broken contract.
#
# Detecting it does not work. A probe was tried first and thrown away: the
# transport failures here are INTERMITTENT rather than a clean threshold, so
# the probe passes and the deploy that follows it still dies. Something that
# answers correctly only most of the time is worse than no gate at all.
#
# So the gate is explicit. These tests need a live Studio, and you say so.
if not os.environ.get("GENLAYER_STUDIO"):
    pytest.skip(
        "integration tests run against a live GenLayer Studio and are opt in: "
        "set GENLAYER_STUDIO=1 to enable them. Everything else runs offline "
        "with pytest tests/ -q",
        allow_module_level=True,
    )


S0 = "We will never sell user data to anyone, under any circumstances."
S1 = "We share aggregated data with a small number of selected partners."


class TestRecant:
    @pytest.fixture
    def contract(self):
        factory = get_contract_factory(contract_file_path="recant.py")
        return factory.deploy(args=[])

    def test_a_record_opens_and_counts(self, contract):
        tx = contract.register(args=["Acme"])
        assert tx_execution_succeeded(tx)
        assert contract.record(args=[0])["author"] == "Acme"

    def test_statements_land_on_the_record_before_they_are_judged(self, contract):
        contract.register(args=["Acme"])
        assert tx_execution_succeeded(contract.state(args=[0, S0]))
        assert tx_execution_succeeded(contract.state(args=[0, S1]))
        rec = contract.record(args=[0])
        assert len(rec["statements"]) == 2
        # Recording is not judging: neither has a verdict yet.
        assert contract.verdict(args=[0]) == ""
        assert contract.verdict(args=[1]) == ""

    def test_withdrawing_does_not_delete(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        assert tx_execution_succeeded(contract.withdraw(args=[0]))
        rec = contract.record(args=[0])
        assert len(rec["statements"]) == 1
        assert rec["statements"][0]["withdrawn"] is True

    def test_withdrawing_twice_is_refused(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        contract.withdraw(args=[0])
        with pytest.raises(Exception):
            contract.withdraw(args=[0])

    def test_a_view_is_safe_before_any_check(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        # Empty rather than raising, so a consuming contract has one branch.
        assert contract.verdict(args=[0]) == ""
        assert contract.against(args=[0]) == ""

    def test_an_unknown_statement_is_refused(self, contract):
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        with pytest.raises(Exception):
            contract.verdict(args=[9])

    def test_a_negative_id_does_not_return_the_newest_record(self, contract):
        # Python accepts -1 and hands back the last row, correctly formatted,
        # with nothing failing anywhere.
        contract.register(args=["Acme"])
        contract.state(args=[0, S0])
        with pytest.raises(Exception):
            contract.verdict(args=[-1])


class TestAuthority:
    """The authorisation rules, against a real runtime.

    These matter more than the rest of this file. tests/glsim.py models
    gl.message.sender_address with a variable a test can set; a node derives it
    from a signature. A rule that holds in the simulator and not on chain would
    be invisible to every other test here.
    """

    @pytest.fixture
    def two(self):
        accounts = get_accounts()
        if len(accounts) < 2:
            pytest.skip(
                "needs two configured accounts on this network, so that a "
                "refusal is a refusal and not an unfunded sender"
            )
        return accounts[0], accounts[1]

    @pytest.fixture
    def contract(self, two):
        owner, _ = two
        factory = get_contract_factory(contract_file_path="recant.py")
        return factory.deploy(args=[], account=owner)

    def test_a_stranger_cannot_add_to_someone_elses_record(self, contract, two):
        _, stranger = two
        contract.register(args=["Acme"])
        with pytest.raises(Exception):
            contract.connect(stranger).state(args=[0, S0])
        assert contract.record(args=[0])["statements"] == []

    def test_a_delegate_may_speak_and_the_record_names_them(self, contract, two):
        _, agent = two
        contract.register(args=["Acme"])
        assert tx_execution_succeeded(contract.authorise(args=[0, agent.address]))
        assert tx_execution_succeeded(contract.connect(agent).state(args=[0, S0]))
        row = contract.record(args=[0])["statements"][0]
        assert row["by"].lower() == agent.address.lower()
        assert contract.registrar(args=[0]).lower() != agent.address.lower()

    def test_a_revoked_delegate_cannot_speak(self, contract, two):
        _, agent = two
        contract.register(args=["Acme"])
        contract.authorise(args=[0, agent.address])
        contract.connect(agent).state(args=[0, S0])
        assert tx_execution_succeeded(contract.revoke(args=[0, agent.address]))
        with pytest.raises(Exception):
            contract.connect(agent).state(args=[0, S1])
        # revoking ends the authority and keeps what was already said
        assert len(contract.record(args=[0])["statements"]) == 1

    def test_a_delegate_may_not_withdraw_or_delegate(self, contract, two):
        _, agent = two
        contract.register(args=["Acme"])
        contract.authorise(args=[0, agent.address])
        contract.state(args=[0, S0])
        with pytest.raises(Exception):
            contract.connect(agent).withdraw(args=[0])
        with pytest.raises(Exception):
            contract.connect(agent).authorise(args=[0, agent.address])
        with pytest.raises(Exception):
            contract.connect(agent).revoke(args=[0, agent.address])

    def test_may_state_answers_what_state_enforces(self, contract, two):
        owner, agent = two
        contract.register(args=["Acme"])
        assert contract.may_state(args=[0, owner.address]) is True
        assert contract.may_state(args=[0, agent.address]) is False
        contract.authorise(args=[0, agent.address])
        assert contract.may_state(args=[0, agent.address]) is True

    def test_an_address_is_matched_by_value_not_by_spelling(self, contract, two):
        """An Address is 20 raw bytes on chain, so case carries no meaning."""
        _, agent = two
        contract.register(args=["Acme"])
        contract.authorise(args=[0, agent.address.lower()])
        assert contract.may_state(args=[0, agent.address.upper().replace("0X", "0x")]) is True

    def test_a_malformed_delegate_address_is_refused(self, contract):
        contract.register(args=["Acme"])
        with pytest.raises(Exception):
            contract.authorise(args=[0, "not-an-address"])
