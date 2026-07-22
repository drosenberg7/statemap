import os

from ticketbot.state import SeenState


def test_new_listing_notifies(tmp_path):
    st = SeenState(str(tmp_path / "s.json"))
    assert st.should_notify("abc", 200.0)


def test_seen_listing_suppressed(tmp_path):
    st = SeenState(str(tmp_path / "s.json"))
    st.record("abc", 200.0)
    assert not st.should_notify("abc", 200.0)


def test_price_drop_renotifies(tmp_path):
    st = SeenState(str(tmp_path / "s.json"))
    st.record("abc", 200.0)
    assert st.should_notify("abc", 180.0)


def test_price_increase_suppressed(tmp_path):
    st = SeenState(str(tmp_path / "s.json"))
    st.record("abc", 200.0)
    assert not st.should_notify("abc", 260.0)


def test_drop_pct_threshold(tmp_path):
    st = SeenState(str(tmp_path / "s.json"))
    st.record("abc", 200.0)
    # 5% drop required; 198 is only 1% off -> no.
    assert not st.should_notify("abc", 198.0, drop_pct=0.05)
    # 180 is 10% off -> yes.
    assert st.should_notify("abc", 180.0, drop_pct=0.05)


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "s.json")
    SeenState(path).record("abc", 200.0)
    assert not SeenState(path).should_notify("abc", 200.0)


def test_corrupt_state_recovers(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not valid json")
    st = SeenState(str(path))
    assert st.should_notify("abc", 200.0)  # starts fresh, no crash
