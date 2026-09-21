"""
End-to-end tests. The real contract file, executed.

tests/test_logic.py covers the pure rules. This file covers everything they
cannot reach: the deterministic half, storage round-trips, the scope walk, the
withdrawal path, and every branch that only fires when the leader and a
validator see different things.

It runs on tests/glsim.py, a small GenVM stand-in, so it needs no Studio and no
network:

    pytest tests/test_e2e.py -v

The important property is that the leader and the validator get their own
independent mock answers. Every mocking framework feeds both nodes the same
data by default, which is exactly why a contract that quietly assumes both nodes
see identical bytes passes its suite and fails on a real network.
"""

import pytest

import glsim as S

CONTRACT_PATH = "contracts/recant.py"


# ---------------------------------------------------------------------------
# A record with a real contradiction in it.
#
#   0  we will never sell or share user data with third parties
#   1  our uptime target for the coming year is ninety nine percent
#   2  we share user data with selected commercial partners   <- fights 0
# ---------------------------------------------------------------------------

S0 = "We will never sell or share user data with any third party."
S1 = "Our uptime target for the coming year is ninety nine percent."
S2 = "We share user data with selected commercial partners."
S3 = "We publish a transparency report every quarter."


def says(indices, because="the earlier commitment rules this out"):
    """Build a mocked model answer naming those local scope indices."""
    return {"Which earlier statements":
            {"conflicts": indices, "because": because}}


class TestRecant:
    def deploy(self, label="Acme"):
        c = S.deploy(CONTRACT_PATH)
        S.call(c, "register", label)
        return c

    def mocks(self, prompts, v_prompts=None):
        S.set_mocks(leader_pages={}, leader_prompts=prompts,
                    validator_pages={},
                    validator_prompts=v_prompts if v_prompts is not None else prompts)

    # -- the record ---------------------------------------------------------

    def test_the_first_statement_is_clear_without_a_model(self):
        """Nothing to be inconsistent with, so no prompt is spent. Note that
        the mocks are empty: if this path called a model, the test would fail
        with 'no mock prompt response matched'."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        assert c.verdict(0) == "clear"
        assert c.latest(0)["why"] == "first statement on this record"

    def test_a_consistent_statement_is_clear(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S1)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"
        assert c.against(1) == ""

    def test_a_contradiction_names_the_statement_it_fights(self):
        """The whole point. Statement 2 contradicts statement 0, and the
        record says which."""
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        assert c.verdict(2) == "contradicts"
        assert c.against(2) == "0"
        out = c.latest(2)
        assert out["checked"] is True
        assert out["text"] == S2

    def test_several_contradictions_are_a_conflict_in_the_record(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0|1"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "conflict"
        assert c.against(2) == "0|1"

    # -- withdrawal ---------------------------------------------------------

    def test_contradicting_a_withdrawn_statement_is_stale_not_a_contradiction(self):
        """The author already changed their mind, in public, on the record.
        That is not an inconsistency."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S1)
        S.call(c, "withdraw", 0)

        self.mocks(says("none"))
        S.call(c, "check", 1)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        assert c.verdict(2) == "stale"
        assert c.against(2) == "0"

    def test_a_live_statement_is_not_diluted_by_a_withdrawn_one(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        S.call(c, "withdraw", 1)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0|1"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "contradicts"
        assert c.against(2) == "0"

    def test_withdrawing_does_not_delete(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "withdraw", 0)
        out = c.latest(0)
        assert out["withdrawn"] is True
        assert out["text"] == S0

    def test_only_the_registrar_may_withdraw(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.set_sender("0x" + "99" * 20)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "withdraw", 0)
        finally:
            S.set_sender("0x" + "11" * 20)

    def test_withdrawing_twice_is_refused(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "withdraw", 0)
        with pytest.raises(S.UserError, match="already withdrawn"):
            S.call(c, "withdraw", 0)

    # -- recourse -----------------------------------------------------------
    #
    # `check()` is open to anybody and a statement is checked exactly once, so
    # a third party can settle a verdict the author would rather have reached
    # differently. That is deliberate -- an author who chose which of their own
    # statements got audited would only audit the flattering ones -- but it is
    # only defensible if the author has a route afterwards. These test the
    # route, because a path nobody exercises is a path an edit can close with
    # the rest of the suite still green.

    def test_the_author_answers_a_contradiction_by_withdrawing_and_restating(self):
        """The whole journey. A stranger settles `contradicts` on a statement
        while the earlier promise is still live; the author retracts the
        promise in public, says the thing again, and the record now reads
        `stale` -- which is the true description of an author who changed their
        mind rather than one who contradicted themselves."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S2)

        S.set_sender(self.STRANGER)
        try:
            self.mocks(says("0"))
            S.call(c, "check", 1)
        finally:
            S.set_sender(self.REGISTRAR)
        assert c.verdict(1) == "contradicts"
        assert c.consistency(0)["inconsistent_pct"] == 100

        S.call(c, "withdraw", 0)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "stale"

        # the earlier mark stays on the record, and the rate moves
        rec = c.consistency(0)
        assert rec["contradicts"] == 1 and rec["stale"] == 1
        assert rec["inconsistent_pct"] == 50

    def test_a_verdict_cannot_be_replayed_into_a_better_one(self):
        """The other half. Somewhere to go must not mean checking again until
        the answer suits: the recourse is a new statement on the record, never
        a second opinion on an old one."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 1)
        for who in (self.REGISTRAR, self.STRANGER):
            S.set_sender(who)
            try:
                self.mocks(says("none"))
                with pytest.raises(S.UserError, match="already checked"):
                    S.call(c, "check", 1)
            finally:
                S.set_sender(self.REGISTRAR)
        assert c.verdict(1) == "contradicts"

    def test_withdrawing_the_statement_that_was_marked_leaves_the_mark(self):
        """Retracting what you said does not retract the finding that you said
        it. The record is a history, and a mark that could be erased by its
        subject would not be worth reading."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 1)
        S.call(c, "withdraw", 1)
        assert c.verdict(1) == "contradicts"
        assert c.latest(1)["withdrawn"] is True
        assert c.consistency(0)["contradicts"] == 1

    def test_a_record_keeps_working_after_an_unwanted_verdict(self):
        """Nothing about an adverse mark stops the record being used."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.call(c, "check", 1)
        S.call(c, "state", 0, S1)
        self.mocks(says("none"))
        S.call(c, "check", 2)
        assert c.verdict(2) == "clear"
        assert c.consistency(0)["checked"] == 2

    # -- authority ----------------------------------------------------------
    #
    # A verdict about an author is only worth the record it was computed from,
    # so the record has to be the author's own. Every test below is about who
    # may put words on somebody else's record, and the answer is nobody.

    STRANGER = "0x" + "99" * 20
    AGENT = "0x" + "77" * 20
    REGISTRAR = "0x" + "11" * 20

    def test_a_stranger_cannot_add_to_someone_elses_record(self):
        """The hole this section exists for. An unauthenticated state() lets
        any account inject text into any record, which forges the premise of
        every later check against it and of the consistency figure published
        from it. The injected sentence reads exactly like a real one."""
        c = self.deploy()
        S.set_sender(self.STRANGER)
        try:
            with pytest.raises(S.UserError, match="registrar or an authorised delegate"):
                S.call(c, "state", 0, S2)
        finally:
            S.set_sender(self.REGISTRAR)
        assert c.statement_count() == 0

    def test_holding_a_record_grants_nothing_over_another_one(self):
        """The obvious way round a naive 'is the caller known here' check."""
        c = self.deploy("Acme")
        S.set_sender(self.STRANGER)
        try:
            S.call(c, "register", "Impostor Ltd")
            with pytest.raises(S.UserError, match="registrar or an authorised delegate"):
                S.call(c, "state", 0, S2)
            S.call(c, "state", 1, S2)
        finally:
            S.set_sender(self.REGISTRAR)
        assert c.record(0)["statements"] == []
        assert len(c.record(1)["statements"]) == 1

    def test_a_delegate_may_speak_and_the_record_names_them(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.set_sender(self.AGENT)
        try:
            S.call(c, "state", 0, S0)
        finally:
            S.set_sender(self.REGISTRAR)
        row = c.record(0)["statements"][0]
        assert row["by"].lower() == self.AGENT
        assert c.latest(0)["registrar"].lower() == self.REGISTRAR

    def test_a_revoked_delegate_cannot_speak(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.call(c, "revoke", 0, self.AGENT)
        S.set_sender(self.AGENT)
        try:
            with pytest.raises(S.UserError, match="registrar or an authorised delegate"):
                S.call(c, "state", 0, S0)
        finally:
            S.set_sender(self.REGISTRAR)

    def test_revoking_does_not_erase_what_was_already_said(self):
        """Same reasoning as withdraw(): the authority to speak ends, the
        record of having spoken does not."""
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.set_sender(self.AGENT)
        try:
            S.call(c, "state", 0, S0)
        finally:
            S.set_sender(self.REGISTRAR)
        S.call(c, "revoke", 0, self.AGENT)
        row = c.record(0)["statements"][0]
        assert row["text"] == S0
        assert row["by"].lower() == self.AGENT

    def test_only_the_registrar_may_authorise_or_revoke(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.set_sender(self.STRANGER)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "authorise", 0, self.STRANGER)
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "revoke", 0, self.AGENT)
        finally:
            S.set_sender(self.REGISTRAR)

    def test_a_delegate_may_not_authorise_another_delegate(self):
        """Otherwise one delegation is enough to take the whole record over."""
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.set_sender(self.AGENT)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "authorise", 0, self.STRANGER)
        finally:
            S.set_sender(self.REGISTRAR)

    def test_a_delegate_may_not_revoke_anybody(self):
        """Found by a mutation that escaped: authorise() was covered against a
        delegate and revoke() was not, so a delegate able to revoke would have
        failed nothing. It matters more than it looks, because a delegate who
        can revoke can remove every OTHER delegate and become the only voice
        on a record it does not own."""
        c = self.deploy()
        other = "0x" + "55" * 20
        S.call(c, "authorise", 0, self.AGENT)
        S.call(c, "authorise", 0, other)
        S.set_sender(self.AGENT)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "revoke", 0, other)
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "revoke", 0, self.AGENT)
        finally:
            S.set_sender(self.REGISTRAR)
        assert [d["active"] for d in c.delegation(0)["delegates"]] == [True, True]

    def test_a_delegate_may_not_withdraw(self):
        """A delegate speaks on the record, only the registrar retracts from
        it, because withdrawing changes what every later check means."""
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        S.call(c, "state", 0, S0)
        S.set_sender(self.AGENT)
        try:
            with pytest.raises(S.UserError, match="registrar"):
                S.call(c, "withdraw", 0)
        finally:
            S.set_sender(self.REGISTRAR)

    def test_an_address_is_matched_by_value_not_by_spelling(self):
        """On chain an Address is 20 raw bytes and case carries no meaning, so
        authorising a checksummed address and calling from the lower case one
        is the same account and must be allowed."""
        c = self.deploy()
        S.call(c, "authorise", 0, "0x" + "AB" * 20)
        S.set_sender("0x" + "ab" * 20)
        try:
            S.call(c, "state", 0, S0)
        finally:
            S.set_sender(self.REGISTRAR)
        assert c.statement_count() == 1

    def test_may_state_answers_what_state_enforces(self):
        """A view that disagrees with the gate is worse than no view at all: a
        consuming contract would gate on one rule and get the other."""
        c = self.deploy()
        S.call(c, "authorise", 0, self.AGENT)
        assert c.may_state(0, self.REGISTRAR) is True
        assert c.may_state(0, self.AGENT) is True
        assert c.may_state(0, self.STRANGER) is False
        assert c.may_state(0, "not-an-address") is False
        for who in (self.REGISTRAR, self.AGENT, self.STRANGER):
            S.set_sender(who)
            try:
                if c.may_state(0, who):
                    S.call(c, "state", 0, S0)
                else:
                    with pytest.raises(S.UserError):
                        S.call(c, "state", 0, S0)
            finally:
                S.set_sender(self.REGISTRAR)

    @pytest.mark.parametrize("bad", ["", "0x", "not-an-address", "0x" + "z" * 40,
                                     "0x" + "11" * 19, "0x" + "11" * 21])
    def test_a_malformed_delegate_address_is_refused_cleanly(self, bad):
        """Address() raises a bare Exception, which the runtime reports as a
        contract error rather than as the caller's mistake."""
        c = self.deploy()
        with pytest.raises(S.UserError, match="not a 20 byte hex address"):
            S.call(c, "authorise", 0, bad)

    def test_the_registrar_is_not_added_as_a_delegate(self):
        c = self.deploy()
        with pytest.raises(S.UserError, match="already speaks"):
            S.call(c, "authorise", 0, self.REGISTRAR)

    def test_re_authorising_reuses_the_row_instead_of_growing_one(self):
        c = self.deploy()
        for _ in range(3):
            S.call(c, "authorise", 0, self.AGENT)
            S.call(c, "revoke", 0, self.AGENT)
        assert len(c.delegation(0)["delegates"]) == 1
        with pytest.raises(S.UserError, match="already revoked"):
            S.call(c, "revoke", 0, self.AGENT)
        S.call(c, "authorise", 0, self.AGENT)
        with pytest.raises(S.UserError, match="already authorised"):
            S.call(c, "authorise", 0, self.AGENT)

    def test_the_delegate_cap_counts_active_rows(self):
        """An unbounded delegate list is an unbounded scan on every state()."""
        c = self.deploy()
        for i in range(16):
            S.call(c, "authorise", 0, "0x" + ("%02x" % (i + 32)) * 20)
        with pytest.raises(S.UserError, match="capped at 16"):
            S.call(c, "authorise", 0, self.AGENT)
        S.call(c, "revoke", 0, "0x" + "20" * 20)
        S.call(c, "authorise", 0, self.AGENT)

    def test_the_cap_survives_a_revoke_and_reauthorise_cycle(self):
        """Counting and matching in one pass looks equivalent to counting first
        and is not. The match can be found before the count is finished, so
        reactivating a revoked row decides against a partial count and walks
        past the cap: sixteen active, revoke one, add a new one, re-authorise
        the revoked one, seventeen active."""
        c = self.deploy()
        addrs = ["0x" + ("%02x" % (i + 32)) * 20 for i in range(16)]
        for a in addrs:
            S.call(c, "authorise", 0, a)
        S.call(c, "revoke", 0, addrs[0])
        S.call(c, "authorise", 0, self.AGENT)
        with pytest.raises(S.UserError, match="capped at 16"):
            S.call(c, "authorise", 0, addrs[0])
        active = [d for d in c.delegation(0)["delegates"] if d["active"]]
        assert len(active) == 16

    def test_revoking_an_address_that_was_never_a_delegate_is_refused(self):
        c = self.deploy()
        with pytest.raises(S.UserError, match="not a delegate"):
            S.call(c, "revoke", 0, self.STRANGER)

    def test_delegation_is_scoped_to_one_record(self):
        c = self.deploy("Acme")
        S.call(c, "register", "Beta Corp")
        S.call(c, "authorise", 0, self.AGENT)
        S.set_sender(self.AGENT)
        try:
            S.call(c, "state", 0, S0)
            with pytest.raises(S.UserError, match="registrar or an authorised delegate"):
                S.call(c, "state", 1, S0)
        finally:
            S.set_sender(self.REGISTRAR)

    def test_anyone_may_check_and_that_is_deliberate(self):
        """consistency() is a claim about an author. An author who could choose
        which of their own statements got audited would only ever audit the
        flattering ones, so checking stays open to anybody. It adds no text and
        can reach only the verdict the record already implies."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        S.call(c, "state", 0, S2)
        self.mocks(says("0"))
        S.set_sender(self.STRANGER)
        try:
            S.call(c, "check", 1)
        finally:
            S.set_sender(self.REGISTRAR)
        assert c.verdict(1) == "contradicts"
        assert c.record(0)["statements"][1]["by"].lower() == self.REGISTRAR

    # -- consensus ----------------------------------------------------------

    def test_nodes_naming_different_statements_do_not_agree(self):
        """Recording 'contradicts something' would be worse than recording
        nothing, so this must fail rather than settle."""
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)

        self.mocks(says("0"), v_prompts=says("1"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 2)
        assert c.verdict(2) == ""          # nothing written

    def test_one_node_finding_a_conflict_and_one_not_does_not_agree(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0"), v_prompts=says("none"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 1)

    def test_both_nodes_finding_nothing_agree(self):
        c = self.deploy()
        for t in (S0, S1):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"), v_prompts=says("none", because="different subject"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"

    def test_an_out_of_range_index_is_rejected(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("9"))
        S.call(c, "check", 1)
        # the block clamps an out of scope index to none rather than raising,
        # and both nodes clamp identically, so the result is a clean 'clear'
        assert c.verdict(1) == "clear"

    def test_a_garbage_answer_is_not_read_as_clean(self):
        """'maybe' must not be treated as 'none'. A broken model would
        otherwise quietly clear every statement it was given."""
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("maybe"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"     # clamped, and both nodes clamp alike

    # -- the reason string --------------------------------------------------

    def test_a_leader_supplied_reason_is_sanitised(self):
        c = self.deploy()
        for t in (S0, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("0", because="<script>x</script>\u0000 rules it out"))
        S.call(c, "check", 1)
        why = c.latest(1)["why"]
        assert "<" not in why and ">" not in why and "\u0000" not in why
        assert "rules it out" in why

    def test_the_view_says_the_reason_is_leader_supplied(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        assert c.latest(0)["reason_is_leader_supplied"] is True

    # -- scope --------------------------------------------------------------

    def test_only_the_same_author_is_in_scope(self):
        """Statements live in one flat array with an author id on each.
        Nothing else keeps two records apart, so this is the test that the id
        is honoured."""
        c = self.deploy("Acme")
        S.call(c, "register", "Globex")
        S.call(c, "state", 0, S0)       # Acme
        S.call(c, "state", 1, S3)       # Globex
        S.call(c, "state", 1, S1)       # Globex, second -> Acme's must not be in scope

        self.mocks({})
        S.call(c, "check", 0)           # Acme's first, no scope
        S.call(c, "check", 1)           # Globex's first, no scope either
        self.mocks(says("none"))
        S.call(c, "check", 2)

        assert c.record(0)["author"] == "Acme"
        assert len(c.record(0)["statements"]) == 1
        assert len(c.record(1)["statements"]) == 2

    def test_the_scope_is_capped_at_the_most_recent_MAX_SCOPE(self):
        """A record longer than the cap is checked against its recent history.

        An unbounded prompt is an unbounded cost and an eventual failure, so the
        cap is real rather than aspirational. The mutation pass found this had no
        test: removing `out[-MAX_SCOPE:]` changed nothing, because no other test
        builds a record long enough to reach it.
        """
        c = self.deploy()
        cap = c._module.MAX_SCOPE
        for i in range(cap + 3):
            S.call(c, "state", 0, "Statement number %d, on its own line." % i)

        # The newest statement sees exactly `cap` earlier ones, not all of them.
        scope = c._scope(0, cap + 2)
        assert len(scope) == cap

        # And it is the RECENT history: the oldest statements have fallen off.
        first_id = scope[0][0]
        assert first_id == 2, first_id

    def test_a_later_statement_is_never_in_scope(self):
        """Checking statement 1 must not see statement 2, even though it
        exists by then. A record is checked against its past, not its future."""
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        # if statement 2 were in scope, local index 1 would exist
        self.mocks(says("1"))
        S.call(c, "check", 1)
        assert c.verdict(1) == "clear"   # index 1 is out of scope, clamped

    # -- consistency --------------------------------------------------------

    def test_consistency_accumulates(self):
        c = self.deploy()
        for t in (S0, S1, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"))
        S.call(c, "check", 2)

        s = c.consistency(0)
        assert s["statements"] == 3
        assert s["checked"] == 3
        assert s["clear"] == 2
        assert s["contradicts"] == 1
        assert s["inconsistent_pct"] == 33

    def test_consistency_is_safe_before_any_check(self):
        c = self.deploy()
        s = c.consistency(0)
        assert s["checked"] == 0 and s["inconsistent_pct"] == 0

    # -- validation ---------------------------------------------------------

    def test_checking_twice_is_refused(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        self.mocks({})
        S.call(c, "check", 0)
        with pytest.raises(S.UserError, match="already checked"):
            S.call(c, "check", 0)

    @pytest.mark.parametrize("text", ["short", "", "   ", "x" * 700])
    def test_bad_statements_are_refused(self, text):
        c = self.deploy()
        with pytest.raises(S.UserError):
            S.call(c, "state", 0, text)
        assert c.statement_count() == 0

    @pytest.mark.parametrize("label", ["", "x", "y" * 200])
    def test_bad_labels_are_refused(self, label):
        c = S.deploy(CONTRACT_PATH)
        with pytest.raises(S.UserError):
            S.call(c, "register", label)
        assert c.count() == 0

    def test_verdict_is_safe_before_any_check(self):
        c = self.deploy()
        S.call(c, "state", 0, S0)
        assert c.verdict(0) == ""
        assert c.against(0) == ""
        assert c.latest(0)["checked"] is False

    def test_a_read_with_a_nonexistent_id_is_a_user_error(self):
        """Not a raw IndexError. GenVM reports an uncaught Python exception as
        a contract error, which tells a caller nothing about what went wrong."""
        c = self.deploy()
        S.call(c, "state", 0, S0)
        for m in ("verdict", "against", "latest"):
            with pytest.raises(S.UserError, match="no such statement"):
                getattr(c, m)(99)
        for m in ("record", "consistency"):
            with pytest.raises(S.UserError, match="no such author"):
                getattr(c, m)(99)

    def test_a_read_with_a_negative_id_does_not_return_the_last_record(self):
        """The dangerous half. Python list indexing accepts -1 and returns the
        newest statement, so a caller asking for statement -1 would silently
        receive a different one and never know."""
        c = self.deploy()
        for t in (S0, S1):
            S.call(c, "state", 0, t)
        for m in ("verdict", "against", "latest"):
            with pytest.raises(S.UserError, match="no such statement"):
                getattr(c, m)(-1)
        for m in ("record", "consistency"):
            with pytest.raises(S.UserError, match="no such author"):
                getattr(c, m)(-1)

    def test_nothing_is_written_when_a_check_fails(self):
        c = self.deploy()
        for t in (S0, S3, S2):
            S.call(c, "state", 0, t)
        self.mocks({})
        S.call(c, "check", 0)
        self.mocks(says("none"))
        S.call(c, "check", 1)
        self.mocks(says("0"), v_prompts=says("1"))
        with pytest.raises(S.UserError):
            S.call(c, "check", 2)
        assert c.consistency(0)["checked"] == 2


# ===========================================================================
# GenVM storage and boundary rules, by static analysis.
#
# Not tests of behaviour. Tests of SHAPE, and each corresponds to a real
# failure that behaviour tests cannot see.
# ===========================================================================

class TestStorageShape:
    def test_the_contract_imports_under_genvm_storage_rules(self):
        mod = S.load_contract(CONTRACT_PATH)
        assert hasattr(mod, "Contract")

    def test_no_storage_dataclass_holds_a_collection(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            if "allow_storage" not in " ".join(
                    ast.unparse(d) for d in cls.decorator_list):
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    ann = ast.unparse(st.annotation)
                    assert "DynArray" not in ann and "TreeMap" not in ann

    def test_no_forbidden_storage_types(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            decs = " ".join(ast.unparse(d) for d in cls.decorator_list)
            is_contract = any("gl.Contract" in ast.unparse(b) for b in cls.bases)
            if "allow_storage" not in decs and not is_contract:
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    ann = ast.unparse(st.annotation)
                    assert ann not in ("int", "float", "list", "dict", "tuple")
                    assert not ann.startswith(("list[", "dict[", "tuple["))

    def test_no_storage_field_is_declared_twice(self):
        import ast, collections, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            names = [st.target.id for st in cls.body
                     if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)]
            dupes = [n for n, c in collections.Counter(names).items() if c > 1]
            assert not dupes, f"{cls.name} declares {dupes} more than once"

    def test_no_method_is_defined_twice(self):
        """A duplicated method silently shadows the first one. Python allows it
        and says nothing at all."""
        import ast, collections, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            names = [m.name for m in cls.body if isinstance(m, ast.FunctionDef)]
            dupes = [n for n, c in collections.Counter(names).items() if c > 1]
            assert not dupes, f"{cls.name} defines {dupes} more than once"
        names = [x.name for x in tree.body
                 if isinstance(x, (ast.FunctionDef, ast.ClassDef))]
        dupes = [n for n, c in collections.Counter(names).items() if c > 1]
        assert not dupes

    def test_every_persistent_field_is_declared_in_the_class_body(self):
        """A field created with self.x = value and never declared is NOT
        persistent. It is silently discarded when execution ends."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        cls = [x for x in tree.body if isinstance(x, ast.ClassDef)
               and any("gl.Contract" in ast.unparse(b) for b in x.bases)][0]
        declared = {st.target.id for st in cls.body if isinstance(st, ast.AnnAssign)}
        for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
            for node in ast.walk(m):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target] if isinstance(node, ast.AugAssign) else [])
                for tg in targets:
                    if (isinstance(tg, ast.Attribute)
                            and isinstance(tg.value, ast.Name)
                            and tg.value.id == "self"):
                        assert tg.attr in declared, (
                            f"{m.name} assigns self.{tg.attr}, undeclared, will not persist")

    def test_every_write_that_touches_a_record_checks_the_sender(self):
        """A behaviour test only covers the methods somebody thought to test.

        This one covers the methods nobody has written yet: a new public write
        added later without an authority check fails here, and the only way to
        pass is to gate it or to add it to the list below on purpose, which is
        a decision somebody has to make in a diff rather than by omission.

          register  opens a record and becomes its registrar, so there is no
                    earlier owner to check against
          check     deliberately open. consistency() is a claim about an
                    author, and an author who chose which of their own
                    statements got audited would only audit flattering ones.
                    It adds no text and can reach only the verdict the record
                    already implies.
        """
        import ast, pathlib
        UNGATED = {"register", "check"}
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text(encoding="utf-8"))
        cls = [x for x in tree.body if isinstance(x, ast.ClassDef)
               and any("gl.Contract" in ast.unparse(b) for b in x.bases)][0]
        gated = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)
                 and any("gl.public.write" in ast.unparse(d) for d in m.decorator_list)}
        assert gated, "no public writes found, the walk is broken"
        for name, m in gated.items():
            if name in UNGATED:
                continue
            body = ast.unparse(m)
            assert "sender_address" in body or "_may_state" in body, (
                f"{name} is a public write with no authority check")

    def test_the_authority_helper_reads_the_active_flag(self):
        """A delegate row is kept after revocation so the history stays
        visible, which means the row existing is NOT the authority. Reading
        the flag is what separates a delegate from a former delegate."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text(encoding="utf-8"))
        fn = [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)
              and x.name == "_delegated"][0]
        src = ast.unparse(fn)
        assert "active" in src and "author_id" in src

    def test_the_block_boundary_carries_flat_strings_only(self):
        """A nested mapping or a bool here fails inside the calldata encoder,
        which is OUTSIDE the contract, so it produces Result Code <unknown>
        with no stderr and no traceback at all."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for blk in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)
                    and x.name == "leader_fn"]:
            returns = [n for n in ast.walk(blk) if isinstance(n, ast.Return)]
            assert returns
            for r in returns:
                assert isinstance(r.value, ast.Dict)
                for k, v in zip(r.value.keys, r.value.values):
                    assert isinstance(k, ast.Constant) and isinstance(k.value, str)
                    src = ast.unparse(v)
                    assert not isinstance(v, (ast.Dict, ast.List, ast.Set, ast.Tuple))
                    assert src not in ("True", "False")
                    # An EXPRESSION that evaluates to a bool is the same bug
                    # wearing a different hat: `len(idx) > 0` is a Compare node,
                    # not a constant, so the line above cannot see it. That
                    # mutation escaped the pass until this assertion and the
                    # runtime check in glsim were added together.
                    assert not isinstance(v, (ast.Compare, ast.BoolOp)), src
                    if isinstance(v, ast.UnaryOp):
                        assert not isinstance(v.op, ast.Not), src

    def test_no_block_closes_over_a_storage_object(self):
        """Non-deterministic blocks cannot read storage at all."""
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for m in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)]:
            blocks = [b for b in ast.walk(m) if isinstance(b, ast.FunctionDef)
                      and b.name in ("leader_fn", "validator_fn")]
            if not blocks:
                continue
            outer = {}
            for node in m.body:
                if isinstance(node, ast.FunctionDef):
                    break
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    outer[node.targets[0].id] = ast.unparse(node.value)
            for b in blocks:
                local = {t.id for n in ast.walk(b) if isinstance(n, ast.Assign)
                         for t in n.targets if isinstance(t, ast.Name)}
                local |= {a.arg for a in b.args.args}
                for x in ast.walk(b):
                    if not isinstance(x, ast.Name) or x.id not in outer:
                        continue
                    if x.id in local:
                        continue
                    expr = outer[x.id]
                    assert (expr.startswith(("str(", "int(", "float(", "bool(",
                                             "len(", "["))
                            or expr.startswith("'|'.join") or expr.startswith('"|".join')
                            or expr.startswith("'\\n'.join") or expr.startswith('"\\n".join')
                            or "copy_to_memory" in expr), \
                        f"{m.name}: block closes over `{x.id} = {expr}`"

    def test_no_public_method_takes_a_builtin_container(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        safe = {"str", "u256", "u8", "bool", "Address", "bytes"}
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("gl.public" in ast.unparse(d) for d in m.decorator_list):
                    continue
                for a in m.args.args[1:]:
                    ann = ast.unparse(a.annotation) if a.annotation else "?"
                    assert ann in safe, f"{m.name}({a.arg}: {ann})"

    def test_no_view_indexes_storage_with_a_caller_supplied_id(self):
        """Indexing an array with a parameter, unchecked, breaks two ways: an
        id past the end raises a raw IndexError, and Python accepts -1 and
        silently returns the newest record. Every such lookup must go through
        a bounds-checked helper.

        A sequential walk over the whole array is fine; the id never reaches
        the subscript.
        """
        import ast, pathlib, re
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("view" in ast.unparse(d) for d in m.decorator_list):
                    continue
                params = {a.arg for a in m.args.args[1:]}
                for node in ast.walk(m):
                    if not isinstance(node, ast.Subscript):
                        continue
                    base = ast.unparse(node.value)
                    if not base.startswith("self."):
                        continue
                    idx = ast.unparse(node.slice)
                    used = {n.id for n in ast.walk(node.slice) if isinstance(n, ast.Name)}
                    assert not (used & params), (
                        f"{m.name}: {base}[{idx}] indexes storage with the "
                        f"caller-supplied id {used & params}"
                    )

    def test_every_id_taking_view_goes_through_a_bounds_check(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                if not any("view" in ast.unparse(d) for d in m.decorator_list):
                    continue
                params = {a.arg for a in m.args.args[1:]}
                if not params:
                    continue
                body = ast.unparse(m)
                assert "_statement(" in body or "_author(" in body, (
                    f"{m.name} takes an id but never bounds-checks it"
                )

    def test_every_raise_in_a_contract_method_is_a_user_error(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(CONTRACT_PATH).read_text())
        for cls in [x for x in tree.body if isinstance(x, ast.ClassDef)]:
            if not any("gl.Contract" in ast.unparse(b) for b in cls.bases):
                continue
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
                for node in ast.walk(m):
                    if isinstance(node, ast.Raise) and node.exc is not None:
                        assert "UserError" in ast.unparse(node.exc)

    def test_the_runner_hash_is_pinned(self):
        import pathlib
        src = pathlib.Path(CONTRACT_PATH).read_text()
        assert src.startswith(
            '# { "Depends": "py-genlayer:'
            '1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }')
        assert "py-genlayer:test" not in src
