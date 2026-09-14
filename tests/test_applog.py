import logging

import pytest

from src import applog


@pytest.fixture(autouse=True)
def _reset_logging():
    """Handlers live on a module-level logger, so a test that leaves one attached would
    keep writing into the previous test's tmp_path."""
    yield
    applog.configure(enabled=False, log_dir=None)


def test_get_logger_returns_a_child_of_the_app_logger():
    logger = applog.get_logger("src.BeatHandler")

    assert logger.name == "gooner.BeatHandler"
    assert logger.parent.name == applog.LOGGER_NAME


def test_nothing_is_written_when_logging_is_disabled(tmp_path):
    applog.configure(enabled=False, log_dir=tmp_path)

    applog.get_logger("src.Test").error("something went wrong")

    assert applog.log_file_paths(tmp_path) == []


def test_enabling_writes_to_a_file(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)

    applog.get_logger("src.Test").info("hello from the test")

    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert "hello from the test" in contents
    assert "INFO" in contents


@pytest.mark.parametrize(
    ("level", "expected"),
    [("info", True), ("warning", True), ("error", True), ("critical", True), ("debug", False)],
)
def test_info_is_the_lowest_level_that_gets_through(tmp_path, level, expected):
    """Deliberately no DEBUG/TRACE: the log exists to explain a user's problem, not to
    trace execution, and a chatty log in an app like this is a liability."""
    applog.configure(enabled=True, log_dir=tmp_path)

    getattr(applog.get_logger("src.Test"), level)("marker-%s", level)

    path = applog.log_file_path(tmp_path)
    # A filtered-out message writes nothing at all - the handler opens the file lazily.
    contents = path.read_text(encoding="utf-8") if path.exists() else ""
    assert (f"marker-{level}" in contents) is expected


def test_the_level_name_is_recorded(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)

    applog.get_logger("src.Test").warning("careful")

    assert "WARNING" in applog.log_file_path(tmp_path).read_text(encoding="utf-8")


def test_exception_details_are_captured(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)

    try:
        raise ValueError("boom")
    except ValueError:
        applog.get_logger("src.Test").exception("while doing a thing")

    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert "while doing a thing" in contents
    assert "ValueError: boom" in contents


def test_disabling_again_stops_writing(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)
    applog.get_logger("src.Test").info("first")

    applog.configure(enabled=False, log_dir=tmp_path)
    applog.get_logger("src.Test").info("second")

    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert "first" in contents
    assert "second" not in contents


def test_reconfiguring_does_not_stack_handlers(tmp_path):
    for _ in range(3):
        applog.configure(enabled=True, log_dir=tmp_path)

    applog.get_logger("src.Test").info("once please")

    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert contents.count("once please") == 1


def test_configure_survives_an_unwritable_directory(tmp_path):
    """A log that cannot be opened must never stop the app from starting."""
    blocker = tmp_path / "logs"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")

    applog.configure(enabled=True, log_dir=blocker)

    applog.get_logger("src.Test").info("still alive")


def test_log_file_paths_lists_rotated_backups(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)
    applog.get_logger("src.Test").info("current")
    (tmp_path / f"{applog.LOG_FILE_NAME}.1").write_text("older", encoding="utf-8")

    names = sorted(p.name for p in applog.log_file_paths(tmp_path))

    assert names == [applog.LOG_FILE_NAME, f"{applog.LOG_FILE_NAME}.1"]


def test_delete_log_files_removes_them_while_logging_is_active(tmp_path):
    """Windows keeps the file locked while the handler holds it open, so deleting has to
    close the handler first - this is the whole reason delete lives in this module."""
    applog.configure(enabled=True, log_dir=tmp_path)
    applog.get_logger("src.Test").info("to be deleted")
    (tmp_path / f"{applog.LOG_FILE_NAME}.1").write_text("older", encoding="utf-8")

    assert applog.delete_log_files(tmp_path) is True
    assert applog.log_file_paths(tmp_path) == []


def test_logging_still_works_after_a_delete(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)
    applog.get_logger("src.Test").info("before")
    applog.delete_log_files(tmp_path)

    applog.get_logger("src.Test").info("after")

    assert "after" in applog.log_file_path(tmp_path).read_text(encoding="utf-8")


def test_delete_reports_false_when_there_was_nothing(tmp_path):
    applog.configure(enabled=False, log_dir=tmp_path)

    assert applog.delete_log_files(tmp_path) is False


def test_rotation_is_bounded(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)
    logger = applog.get_logger("src.Test")

    for i in range(4000):
        logger.info("padding line %s with enough text to push the file over the limit", i)

    paths = applog.log_file_paths(tmp_path)
    assert len(paths) <= applog.BACKUP_COUNT + 1
    assert all(p.stat().st_size <= applog.MAX_BYTES * 2 for p in paths)


def test_app_logger_does_not_leak_into_the_root_logger(tmp_path, caplog):
    """propagate=False - otherwise pytest's own root handlers (and anything a library
    installs) would pick up every line."""
    applog.configure(enabled=True, log_dir=tmp_path)

    assert logging.getLogger(applog.LOGGER_NAME).propagate is False


# --- level selection ---


def test_the_default_level_is_info(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path)

    applog.get_logger("src.Test").info("visible by default")

    assert "visible by default" in applog.log_file_path(tmp_path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("level", "info_kept", "warning_kept", "error_kept"),
    [
        ("INFO", True, True, True),
        ("WARNING", False, True, True),
        ("ERROR", False, False, True),
    ],
)
def test_the_configured_level_filters_everything_below_it(
    tmp_path, level, info_kept, warning_kept, error_kept
):
    applog.configure(enabled=True, log_dir=tmp_path, level=level)
    logger = applog.get_logger("src.Test")

    logger.info("an-info-line")
    logger.warning("a-warning-line")
    logger.error("an-error-line")

    path = applog.log_file_path(tmp_path)
    contents = path.read_text(encoding="utf-8") if path.exists() else ""
    assert ("an-info-line" in contents) is info_kept
    assert ("a-warning-line" in contents) is warning_kept
    assert ("an-error-line" in contents) is error_kept


def test_info_stays_the_floor_even_if_a_lower_level_is_asked_for(tmp_path):
    """No DEBUG/TRACE in this app - a level below the floor is clamped, not honoured."""
    applog.configure(enabled=True, log_dir=tmp_path, level="DEBUG")

    applog.get_logger("src.Test").debug("should never appear")
    applog.get_logger("src.Test").info("should appear")

    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert "should never appear" not in contents
    assert "should appear" in contents


def test_an_unknown_level_name_falls_back_to_info(tmp_path):
    applog.configure(enabled=True, log_dir=tmp_path, level="LOUD")

    applog.get_logger("src.Test").info("still recorded")

    assert "still recorded" in applog.log_file_path(tmp_path).read_text(encoding="utf-8")


def test_selectable_levels_are_exposed_for_the_ui():
    """The dialog builds its dropdown from this, so it cannot drift from what configure()
    actually accepts."""
    assert applog.LEVELS == ("INFO", "WARNING", "ERROR")


def test_deleting_the_log_keeps_the_chosen_level(tmp_path):
    """Delete and the level picker sit in the same dialog - wiping the file must not
    quietly widen what gets recorded afterwards."""
    applog.configure(enabled=True, log_dir=tmp_path, level="ERROR")
    applog.get_logger("src.Test").error("before the delete")

    applog.delete_log_files(tmp_path)

    applog.get_logger("src.Test").info("an info line")
    applog.get_logger("src.Test").error("an error line")
    contents = applog.log_file_path(tmp_path).read_text(encoding="utf-8")
    assert "an info line" not in contents
    assert "an error line" in contents


def test_no_stream_handler_without_a_stderr(tmp_path, monkeypatch):
    """PyInstaller's --windowed build has sys.stderr set to None. A StreamHandler built
    against it fails on every emit and logging swallows the error - wasted work in exactly
    the build this log exists for."""
    import logging as _logging
    import sys as _sys

    monkeypatch.setattr(_sys, "stderr", None)

    applog.configure(enabled=True, log_dir=tmp_path)

    handlers = _logging.getLogger(applog.LOGGER_NAME).handlers
    assert not any(type(h) is _logging.StreamHandler for h in handlers)


def test_file_logging_still_works_without_a_stderr(tmp_path, monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "stderr", None)
    applog.configure(enabled=True, log_dir=tmp_path)

    applog.get_logger("src.Test").warning("still recorded")

    assert "still recorded" in applog.log_file_path(tmp_path).read_text(encoding="utf-8")
