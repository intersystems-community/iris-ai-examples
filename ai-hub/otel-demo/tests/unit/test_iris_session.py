"""A native connection outlives an IRIS restart only as a dead socket; the session recovers."""

import pytest

from demo_app.iris_session import IrisSession


class LinkError(Exception):
    pass


def make_connect(script):
    """Each connect() hands out the next native; each native runs its script of outcomes."""
    made = []

    def connect():
        outcomes = script[len(made)]
        made.append(outcomes)

        def fn_runner(fn, *args):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return fn_runner

    return connect, made


def call(native, *args):
    return native(call, *args)


def test_a_dead_reused_connection_is_replaced_and_the_call_retried_once():
    connect, made = make_connect([["ok", LinkError("<COMMUNICATION LINK ERROR>")], ["again"]])
    s = IrisSession(connect)
    assert s.call(call) == "ok"
    assert s.call(call) == "again"
    assert len(made) == 2


def test_a_fresh_connection_failing_is_not_retried():
    connect, made = make_connect([[LinkError("<COMMUNICATION LINK ERROR>")], ["unused"]])
    s = IrisSession(connect)
    with pytest.raises(LinkError):
        s.call(call)
    assert len(made) == 1


def test_other_errors_drop_the_connection_without_retry():
    connect, made = make_connect([["ok", ValueError("bad")], ["next"]])
    s = IrisSession(connect)
    s.call(call)
    with pytest.raises(ValueError):
        s.call(call)
    assert s.call(call) == "next"
    assert len(made) == 2
