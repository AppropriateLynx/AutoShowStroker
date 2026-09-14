"""Opt-in diagnostic logging.

The shipped app is built with PyInstaller's `--windowed`, where `sys.stdout` is None and
every `print()` is silently discarded. That left a user's "callouts stopped working" with
no artifact at all to look at - the one message that would have explained it went nowhere.

It is **off by default**, and that is a product decision, not an oversight. A log in an app
like this is a record of when someone used it, so it only exists once they have asked for
one (Settings > Playback > "Write a diagnostic log file"). It lives beside the other data
files and is deletable on its own from Help > Privacy & Data.

**What may go in it** (see also CLAUDE.md's Logging section):

- INFO is the floor. There is deliberately no DEBUG or TRACE: this log explains a problem
  to a human, it does not trace execution, and per-beat chatter would bury the one line
  that matters.
- Never a media folder path. That reveals where the collection lives on disk, which is
  exactly what the Privacy & Data work exists to keep under the user's control.
- A bare *filename* is allowed in a WARNING/ERROR about that specific file, because
  "which file breaks the thumbnailer" is unanswerable without it.
- Paths the app owns (the data directory, res/) are fine and useful.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "gooner"
LOG_FILE_NAME = "gooner.log"
# Small on purpose: this is a support artifact someone might paste into a Discord message,
# not an archive. Two backups is enough to survive a restart mid-problem.
MAX_BYTES = 512 * 1024
BACKUP_COUNT = 2

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Created at import so every get_logger() child has a real parent to inherit from, even
# before configure() runs - otherwise logging silently reparents them to the root logger.
_app_logger = logging.getLogger(LOGGER_NAME)
_app_logger.setLevel(logging.INFO)
_app_logger.propagate = False


def get_logger(module_name: str) -> logging.Logger:
    """The logger for one module - call it as `get_logger(__name__)` at module scope.

    Returns a child of the app logger, so a single configure() governs all of them and
    nothing leaks into the root logger.
    """
    short_name = module_name.split(".")[-1]
    return logging.getLogger(f"{LOGGER_NAME}.{short_name}")


def log_file_path(log_dir) -> Path:
    return Path(log_dir) / LOG_FILE_NAME


def log_file_paths(log_dir) -> list:
    """Every log file currently on disk, rotated backups included."""
    directory = Path(log_dir)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(f"{LOG_FILE_NAME}*") if p.is_file())


def configure(enabled: bool, log_dir) -> None:
    """(Re)builds the app logger's handlers. Safe to call repeatedly and at any time.

    Never raises: a log file that cannot be opened is a reason to run without one, not a
    reason to fail startup.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # Without this, pytest's root handlers and anything a library installs would pick up
    # every line we emit.
    logger.propagate = False

    _close_handlers(logger)

    # Always present: discarded in the windowed build, genuinely useful when running
    # `python main.py` from a terminal, and it writes nothing to disk either way.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    logger.addHandler(stream_handler)

    if not enabled or log_dir is None:
        return

    try:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / LOG_FILE_NAME,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            # delay=True so the file appears on the first actual message. Without it,
            # merely enabling the setting - or re-arming after a delete - would recreate
            # an empty log immediately, which makes "delete my data" look like it failed.
            delay=True,
        )
    except OSError as error:
        logger.warning("Diagnostic log could not be opened, continuing without one: %s", error)
        return

    file_handler.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    logger.addHandler(file_handler)


def is_file_logging_active() -> bool:
    return any(
        isinstance(handler, RotatingFileHandler)
        for handler in logging.getLogger(LOGGER_NAME).handlers
    )


def delete_log_files(log_dir) -> bool:
    """Removes the log and its backups. Returns whether anything was there.

    Deleting lives here rather than in UserDataStore because the file handler holds the
    log open - on Windows that locks it, so the handler has to be closed first and then
    reopened if logging is still switched on.
    """
    was_active = is_file_logging_active()
    logger = logging.getLogger(LOGGER_NAME)
    if was_active:
        _close_handlers(logger, only_files=True)

    removed = False
    for path in log_file_paths(log_dir):
        try:
            path.unlink()
            removed = True
        except OSError as error:
            logger.warning("Could not delete %s: %s", path.name, error)

    if was_active:
        configure(enabled=True, log_dir=log_dir)
    return removed


def _close_handlers(logger: logging.Logger, only_files: bool = False) -> None:
    for handler in list(logger.handlers):
        if only_files and not isinstance(handler, RotatingFileHandler):
            continue
        logger.removeHandler(handler)
        try:
            handler.close()
        except OSError:
            pass
