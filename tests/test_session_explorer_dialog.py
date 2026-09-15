"""The Session Explorer: the timeline you scroll back through after a session.

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
        "ended_at": 1120.0,
        "climax_at": None,
        "climax_outcome": None,
        "segments": segments if segments is not None else [segment()],
    }
    base.update(overrides)
    return base


def segment(kind="beat", pattern="Standard Beat", freq=2.0, start=1000.0, end=1060.0, media=()):
    return {
        "kind": kind, "pattern": pattern, "freq": freq,
        "start": start, "end": end, "media": list(media),
    }


def medium(path="a.png", start=1005.0, end=1010.0, carried_over=False):
    return {"path": path, "start": start, "end": end, "carried_over": carried_over}


@pytest.fixture
def source():
    return _StubThumbnailSource()


@pytest.fixture
def make_dialog(qtbot, source):
    def build(data):
        dialog = SessionExplorerDialog(data, thumbnail_source=source, parent=None)
        qtbot.addWidget(dialog)
        dialog.resize(700, 500)
        dialog.show()  # thumbnails are loaded from showEvent, like the real dialog
        qtbot.waitExposed(dialog)
        return dialog

    return build


# --- the segment cards ---


def test_one_card_per_segment(make_dialog):
    dialog = make_dialog(timeline([segment(start=1000.0, end=1030.0), segment(start=1030.0, end=1060.0)]))
    assert len(dialog.segment_cards) == 2


def test_a_card_reports_rhythm_speed_and_type(make_dialog):
    dialog = make_dialog(timeline([segment(pattern="Quick Swing", freq=3.25)]))

    text = dialog.segment_cards[0].summary()

    assert "Quick Swing" in text
    assert "3.25" in text
    assert "Beat" in text


def test_a_pause_card_says_pause_and_shows_no_rhythm(make_dialog):
    dialog = make_dialog(timeline([segment(kind="pause", pattern=None, freq=None)]))

    text = dialog.segment_cards[0].summary()

    assert "Pause" in text
    assert "Hz" not in text


def test_a_card_reports_when_it_started_and_how_long_it_ran(make_dialog):
    dialog = make_dialog(timeline([segment(start=1000.0, end=1030.0), segment(start=1030.0, end=1095.0)]))

    assert "0:00" in dialog.segment_cards[0].summary()
    assert "0:30" in dialog.segment_cards[1].summary()
    assert "1:05" in dialog.segment_cards[1].summary()  # 65s long


def test_the_finale_card_is_labelled_as_the_run_in(make_dialog):
    dialog = make_dialog(timeline([segment(kind="finale")]))
    assert "Finale" in dialog.segment_cards[0].summary()


def test_the_card_covering_the_climax_is_marked(make_dialog):
    dialog = make_dialog(
        timeline(
            [segment(start=1000.0, end=1030.0), segment(start=1030.0, end=1060.0)],
            climax_at=1040.0,
            climax_outcome="ruined",
        )
    )

    assert dialog.segment_cards[0].climax_outcome is None
    assert dialog.segment_cards[1].climax_outcome == "ruined"


def test_no_card_is_marked_without_a_climax(make_dialog):
    dialog = make_dialog(timeline([segment()]))
    assert all(card.climax_outcome is None for card in dialog.segment_cards)


# --- the media inside a card ---


def test_a_card_holds_a_cell_per_medium(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png"), medium("b.png")])]))
    assert len(dialog.segment_cards[0].media_cells) == 2


def test_a_carried_over_medium_is_marked_as_continuing(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png", carried_over=True)])]))
    assert dialog.segment_cards[0].media_cells[0].carried_over is True


def test_a_segment_without_media_still_gets_a_card(make_dialog):
    dialog = make_dialog(timeline([segment(media=[])]))
    assert len(dialog.segment_cards) == 1
    assert dialog.segment_cards[0].media_cells == []


# --- lazy loading ---


def test_thumbnails_are_not_built_until_a_card_is_near_the_viewport(qtbot, source):
    """A long session holds hundreds of media - building them all up front would stall the
    open. Only what is nearly on screen gets decoded."""
    far_away = [
        segment(start=1000.0 + i * 30, end=1030.0 + i * 30, media=[medium(f"clip{i}.mp4")])
        for i in range(60)
    ]
    dialog = SessionExplorerDialog(timeline(far_away), thumbnail_source=source, parent=None)
    qtbot.addWidget(dialog)
    dialog.resize(700, 400)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert len(source.requested) < len(far_away)


def test_scrolling_loads_the_cards_that_come_into_view(qtbot, source):
    segments = [
        segment(start=1000.0 + i * 30, end=1030.0 + i * 30, media=[medium(f"clip{i}.mp4")])
        for i in range(60)
    ]
    dialog = SessionExplorerDialog(timeline(segments), thumbnail_source=source, parent=None)
    qtbot.addWidget(dialog)
    dialog.resize(700, 400)
    dialog.show()
    qtbot.waitExposed(dialog)
    before = len(source.requested)

    bar = dialog.scroll_area.verticalScrollBar()
    bar.setValue(bar.maximum())

    assert len(source.requested) > before


def test_only_videos_go_to_the_thumbnail_source(make_dialog, source):
    """Images and GIFs decode straight off disk - queueing them behind a video would make
    them appear late for no reason."""
    make_dialog(timeline([segment(media=[medium("a.png"), medium("b.gif"), medium("c.mp4")])]))
    assert source.requested == ["c.mp4"]


# --- the detail pane ---


def test_the_detail_pane_starts_empty(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png")])]))
    assert dialog.selected_path is None


def test_selecting_a_medium_fills_the_detail_pane(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("/some/where/a.png")])]))

    dialog.select_medium("/some/where/a.png")

    assert dialog.selected_path == "/some/where/a.png"
    assert "a.png" in dialog.detail_name_label.text()


def test_the_reveal_button_is_disabled_until_something_is_selected(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png")])]))
    assert dialog.reveal_button.isEnabled() is False

    dialog.select_medium("a.png")

    assert dialog.reveal_button.isEnabled() is True


def test_revealing_opens_the_containing_folder(make_dialog, monkeypatch, tmp_path):
    opened = {}
    monkeypatch.setattr(
        "src.SessionExplorerDialog.QDesktopServices.openUrl",
        lambda url: opened.setdefault("url", url.toLocalFile()),
    )
    media_file = tmp_path / "keep_this.png"
    media_file.write_bytes(b"")
    dialog = make_dialog(timeline([segment(media=[medium(str(media_file))])]))
    dialog.select_medium(str(media_file))

    dialog.reveal_button.click()

    # QUrl.toLocalFile() hands back forward slashes even on Windows.
    assert Path(opened["url"]) == tmp_path


def test_the_play_button_only_shows_for_video(make_dialog):
    dialog = make_dialog(timeline([segment(media=[medium("a.png"), medium("b.mp4")])]))

    dialog.select_medium("a.png")
    assert dialog.play_button.isHidden()

    dialog.select_medium("b.mp4")
    assert not dialog.play_button.isHidden()


# --- lifecycle ---


def test_closing_cancels_pending_thumbnail_work(make_dialog, source):
    dialog = make_dialog(timeline([segment(media=[medium("a.mp4")])]))

    dialog.close()

    assert source.cancelled is True


def test_a_timeline_with_no_segments_does_not_raise(make_dialog):
    dialog = make_dialog(timeline([]))
    assert dialog.segment_cards == []


# --- many media in one segment ---


def test_media_wrap_into_rows_instead_of_running_off_the_card(make_dialog):
    """A 45-second segment at the default slideshow speed holds dozens of media - in a
    single row they run straight off the side of the card."""
    many = [medium(f"pic{i}.png", start=1000.0 + i) for i in range(12)]
    dialog = make_dialog(timeline([segment(media=many)]))
    card = dialog.segment_cards[0]

    assert card.media_columns < 12
    rows = {cell.pos().y() for cell in card.media_cells}
    assert len(rows) > 1


def test_a_wider_card_fits_more_media_per_row(qtbot, source):
    many = [medium(f"pic{i}.png", start=1000.0 + i) for i in range(12)]
    dialog = SessionExplorerDialog(timeline([segment(media=many)]), thumbnail_source=source, parent=None)
    qtbot.addWidget(dialog)
    dialog.resize(600, 500)
    dialog.show()
    qtbot.waitExposed(dialog)
    narrow = dialog.segment_cards[0].media_columns

    dialog.resize(1400, 500)
    qtbot.wait(20)

    assert dialog.segment_cards[0].media_columns > narrow


def test_every_medium_still_gets_a_cell_when_wrapped(make_dialog):
    many = [medium(f"pic{i}.png", start=1000.0 + i) for i in range(12)]
    dialog = make_dialog(timeline([segment(media=many)]))
    assert len(dialog.segment_cards[0].media_cells) == 12
