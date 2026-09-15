"""The Session Explorer: scrub the session's timeline and see what was on screen.

The thumbnail source is stubbed throughout - a real one would build a QMediaPlayer.
"""
from pathlib import Path

import pytest

from src.SessionExplorerDialog import SessionExplorerDialog


class _StubThumbnailSource:
    """Stands in for VideoThumbnailQueue; answers immediately and records what it was asked."""

    def __init__(self, answer=None):
        self.requested = []
        self.cancelled = False
        self._answer = answer

    def request(self, path, callback):
        self.requested.append(path)
        callback(path, self._answer)

    def cancel_all(self):
        self.cancelled = True


def timeline(segments=None, **overrides):
    base = {
        "started_at": 1000.0,
        "ended_at": 1100.0,
        "climax_at": None,
        "climax_outcome": None,
        "segments": segments if segments is not None else [segment()],
    }
    base.update(overrides)
    return base


def segment(kind="beat", pattern="Standard Beat", freq=2.0, start=1000.0, end=1100.0, media=()):
    return {
        "kind": kind, "pattern": pattern, "freq": freq,
        "start": start, "end": end, "media": list(media),
    }


def medium(path="a.png", start=1000.0, end=1100.0, carried_over=False):
    return {"path": path, "start": start, "end": end, "carried_over": carried_over}


@pytest.fixture
def source():
    return _StubThumbnailSource()


@pytest.fixture
def make_dialog(qtbot, source):
    def build(data):
        dialog = SessionExplorerDialog(data, thumbnail_source=source, parent=None)
        qtbot.addWidget(dialog)
        dialog.resize(900, 600)
        dialog.show()
        qtbot.waitExposed(dialog)
        return dialog

    return build


# --- the timeline bar ---


def test_the_bar_spans_the_whole_session(make_dialog):
    dialog = make_dialog(timeline(ended_at=1100.0))
    bar = dialog.timeline_bar

    assert bar.time_at_x(0) == pytest.approx(0.0)
    assert bar.time_at_x(bar.width()) == pytest.approx(100.0, abs=1.0)


def test_a_position_halfway_along_is_halfway_through(make_dialog):
    dialog = make_dialog(timeline(ended_at=1100.0))
    bar = dialog.timeline_bar
    assert bar.time_at_x(bar.width() / 2) == pytest.approx(50.0, abs=1.0)


def test_a_zero_length_session_does_not_divide_by_zero(make_dialog):
    dialog = make_dialog(timeline([], ended_at=1000.0))
    assert dialog.timeline_bar.time_at_x(50) == 0.0


def test_the_bar_knows_where_the_climax_sits(make_dialog):
    dialog = make_dialog(timeline(climax_at=1075.0, climax_outcome="ruined"))
    bar = dialog.timeline_bar

    assert bar.climax_offset == pytest.approx(75.0)
    assert bar.x_for_time(75.0) == pytest.approx(bar.width() * 0.75, abs=2.0)


# --- scrubbing ---


def test_scrubbing_shows_the_medium_that_was_on_screen(make_dialog):
    dialog = make_dialog(
        timeline([segment(media=[medium("early.png", 1000.0, 1050.0), medium("late.png", 1050.0, 1100.0)])])
    )

    dialog.scrub_to(10.0)
    assert dialog.selected_path == "early.png"

    dialog.scrub_to(80.0)
    assert dialog.selected_path == "late.png"


def test_scrubbing_reports_the_segment_at_that_moment(make_dialog):
    dialog = make_dialog(
        timeline([
            segment(pattern="Slow Pulse", freq=1.25, start=1000.0, end=1050.0),
            segment(kind="pause", pattern=None, freq=None, start=1050.0, end=1100.0),
        ])
    )

    dialog.scrub_to(10.0)
    assert "Slow Pulse" in dialog.moment_label.text()
    assert "1.25" in dialog.moment_label.text()

    dialog.scrub_to(80.0)
    assert "Pause" in dialog.moment_label.text()
    assert "Hz" not in dialog.moment_label.text()


def test_the_moment_label_shows_the_time(make_dialog):
    dialog = make_dialog(timeline([segment(start=1000.0, end=1100.0)]))
    dialog.scrub_to(65.0)
    assert "1:05" in dialog.moment_label.text()


def test_scrubbing_past_every_medium_clears_the_preview(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png", 1000.0, 1010.0)])]))

    dialog.scrub_to(50.0)

    assert dialog.selected_path is None


def test_scrubbing_moves_the_playhead(make_dialog):
    dialog = make_dialog(timeline(ended_at=1100.0))
    dialog.scrub_to(40.0)
    assert dialog.timeline_bar.playhead_offset == pytest.approx(40.0)


def test_a_finale_segment_is_still_scrubbable(make_dialog):
    dialog = make_dialog(timeline([segment(kind="finale", start=1000.0, end=1100.0)]))
    dialog.scrub_to(50.0)
    assert "Finale" in dialog.moment_label.text()


# --- thumbnails ---


def test_only_videos_go_to_the_thumbnail_source(make_dialog, source):
    """Images and GIFs decode straight off disk - queueing them behind a video would make
    them appear late for no reason."""
    dialog = make_dialog(
        timeline([segment(media=[medium("a.png", 1000.0, 1050.0), medium("b.mp4", 1050.0, 1100.0)])])
    )

    dialog.scrub_to(10.0)
    dialog.scrub_to(80.0)

    assert source.requested == ["b.mp4"]


def test_a_video_frame_is_only_grabbed_once(make_dialog, source):
    """Scrubbing back and forth over the same clip must not re-decode it every time."""
    dialog = make_dialog(timeline([segment(media=[medium("b.mp4", 1000.0, 1100.0)])]))

    dialog.scrub_to(10.0)
    dialog.scrub_to(20.0)
    dialog.scrub_to(30.0)

    assert source.requested == ["b.mp4"]


def test_nothing_is_decoded_before_the_first_scrub(make_dialog, source):
    make_dialog(timeline([segment(media=[medium("b.mp4", 1000.0, 1100.0)])]))
    assert source.requested == []


# --- acting on what you found ---


def test_the_buttons_are_disabled_until_something_is_on_screen(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png", 1000.0, 1010.0)])]))
    assert dialog.reveal_button.isEnabled() is False

    dialog.scrub_to(5.0)

    assert dialog.reveal_button.isEnabled() is True


def test_revealing_opens_the_containing_folder(make_dialog, monkeypatch, tmp_path):
    opened = {}
    monkeypatch.setattr(
        "src.SessionExplorerDialog.QDesktopServices.openUrl",
        lambda url: opened.setdefault("url", url.toLocalFile()),
    )
    media_file = tmp_path / "keep_this.png"
    media_file.write_bytes(b"")
    dialog = make_dialog(timeline([segment(media=[medium(str(media_file), 1000.0, 1100.0)])]))
    dialog.scrub_to(50.0)

    dialog.reveal_button.click()

    # QUrl.toLocalFile() hands back forward slashes even on Windows.
    assert Path(opened["url"]) == tmp_path


def test_the_play_button_only_shows_for_video(make_dialog):
    dialog = make_dialog(
        timeline([segment(media=[medium("a.png", 1000.0, 1050.0), medium("b.mp4", 1050.0, 1100.0)])])
    )

    dialog.scrub_to(10.0)
    assert dialog.play_button.isHidden()

    dialog.scrub_to(80.0)
    assert not dialog.play_button.isHidden()


# --- lifecycle ---


def test_closing_cancels_pending_thumbnail_work(make_dialog, source):
    dialog = make_dialog(timeline([segment(media=[medium("a.mp4", 1000.0, 1100.0)])]))
    dialog.scrub_to(10.0)

    dialog.close()

    assert source.cancelled is True


def test_a_timeline_with_no_segments_does_not_raise(make_dialog):
    dialog = make_dialog(timeline([]))
    dialog.scrub_to(10.0)
    assert dialog.selected_path is None
