"""The overlay captions, tested against a score tracker double rather than a whole window.

What these hold that the GoonerApp tests could not: the widget decides for itself whether a
session is running, so the "hide when there is no session" rule can be checked without
building a main window and starting one.
"""
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QLabel

from src.SessionHudWidget import SessionHudWidget


class _TrackerDouble:
    def __init__(self, bests=None, chase=None, elapsed=0.0):
        self._bests = bests or {"total_dur_sec": 100.0}
        self._chase = chase
        self.elapsed = elapsed
        self.bests_asked = 0

    def get_all_time_bests(self):
        self.bests_asked += 1
        return dict(self._bests)

    def record_chase_status(self, _session_start_bests):
        return self._chase

    def live_metrics(self):
        return {"total_dur_sec": self.elapsed}


@pytest.fixture
def hud(qtbot, tmp_path):
    def build(tracker=None, **stored):
        settings = QSettings(str(tmp_path / "hud.ini"), QSettings.Format.IniFormat)
        for name, value in stored.items():
            settings.setValue(f"{SessionHudWidget.SETTINGS_GROUP}/{name}", value)
        widget = SessionHudWidget(QLabel("media"), tracker or _TrackerDouble(), settings)
        qtbot.addWidget(widget)
        return widget

    return build


def test_captions_start_hidden(hud):
    widget = hud()

    assert widget.record_chase_label.isHidden()
    assert widget.session_timer_label.isHidden()
    assert widget.callout_label.isHidden()


def test_nothing_is_shown_outside_a_session(hud):
    """The settings dialog refreshes after every save, including with no session running.
    Before, that put a frozen clock back on screen counting from the previous start."""
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 50.0, 100.0), elapsed=42.0))

    widget.refresh()

    assert widget.record_chase_label.isHidden()
    assert widget.session_timer_label.isHidden()


def test_a_started_session_shows_the_clock(hud):
    widget = hud(_TrackerDouble(elapsed=65.0))

    widget.session_started()

    assert not widget.session_timer_label.isHidden()
    assert "1:05" in widget.session_timer_label.text()


def test_the_chase_names_the_record_being_closed_in_on(hud):
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 50.0, 100.0)))

    widget.session_started()

    text = widget.record_chase_label.text()
    assert "Closing in on" in text
    assert "Total Duration" in text


def test_beating_the_record_says_so(hud):
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 150.0, 100.0)))

    widget.session_started()

    assert "New Total Duration Record!" in widget.record_chase_label.text()


def test_no_chase_worth_showing_hides_the_caption(hud):
    widget = hud(_TrackerDouble(chase=None))

    widget.session_started()

    assert widget.record_chase_label.isHidden()


def test_the_bests_are_the_ones_the_session_started_with(hud):
    """The chase is against the record you walked in with. Read live, you would end up
    chasing yourself the moment you beat it."""
    tracker = _TrackerDouble(chase=("total_dur_sec", 50.0, 100.0))
    widget = hud(tracker)

    widget.session_started()
    widget.refresh_record_chase()
    widget.refresh_record_chase()

    assert tracker.bests_asked == 1


def test_switching_the_chase_off_hides_it_on_the_next_refresh(hud):
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 50.0, 100.0)))
    widget.session_started()
    assert not widget.record_chase_label.isHidden()

    widget.show_record_chase = False
    widget.refresh()

    assert widget.record_chase_label.isHidden()
    assert not widget.session_timer_label.isHidden(), "the clock is a separate switch"


def test_switching_the_clock_off_hides_it_on_the_next_refresh(hud):
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 50.0, 100.0)))
    widget.session_started()

    widget.show_session_timer = False
    widget.refresh()

    assert widget.session_timer_label.isHidden()
    assert not widget.record_chase_label.isHidden(), "the chase is a separate switch"


def test_ending_a_session_clears_both_captions_and_stops_the_clock(hud):
    widget = hud(_TrackerDouble(chase=("total_dur_sec", 50.0, 100.0)))
    widget.session_started()
    assert widget._clock.isActive()

    widget.session_ended()

    assert widget.record_chase_label.isHidden()
    assert widget.session_timer_label.isHidden()
    assert not widget._clock.isActive()


def test_a_tease_is_shown_and_then_cleared(hud):
    widget = hud()

    widget.show_tease("good boy")
    assert widget.callout_label.text() == "good boy"
    assert not widget.callout_label.isHidden()

    widget.hide_tease()
    assert widget.callout_label.text() == ""
    assert widget.callout_label.isHidden()


def test_the_content_widget_sits_under_the_captions(qtbot, tmp_path):
    """All four share one grid cell - that is what makes it an overlay rather than a row."""
    content = QLabel("media")
    settings = QSettings(str(tmp_path / "hud.ini"), QSettings.Format.IniFormat)
    widget = SessionHudWidget(content, _TrackerDouble(), settings)
    qtbot.addWidget(widget)

    grid = widget.layout()
    positions = {grid.itemAt(i).widget(): grid.getItemPosition(i)[:2] for i in range(grid.count())}

    assert positions[content] == (0, 0)
    assert positions[widget.callout_label] == (0, 0)
    assert positions[widget.record_chase_label] == (0, 0)
    assert positions[widget.session_timer_label] == (0, 0)
