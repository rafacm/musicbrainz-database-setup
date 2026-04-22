"""Nested progress bars. Single Progress instance so live displays stay coherent."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from musicbrainz_db_setup.logging import get_console


class ProgressManager:
    """Singleton-ish wrapper around rich.progress.Progress.

    Use via ``ProgressManager.instance()`` or the ``progress_session`` context
    manager. Bar columns are mixed (download-friendly + generic count); rich
    hides irrelevant columns per task when fields are None.
    """

    _instance: ProgressManager | None = None

    def __init__(self) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            DownloadColumn(binary_units=True),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            TextColumn("{task.fields[note]}", style="dim"),
            console=get_console(),
            transient=False,
        )
        self._started = False

    @classmethod
    def instance(cls) -> ProgressManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self) -> None:
        if not self._started:
            self._progress.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self._progress.stop()
            self._started = False

    def add_task(
        self,
        description: str,
        total: float | None = None,
        *,
        note: str = "",
    ) -> TaskID:
        self.start()
        return self._progress.add_task(description, total=total, note=note)

    def advance(self, task_id: TaskID, amount: float) -> None:
        self._progress.advance(task_id, amount)

    def update(
        self,
        task_id: TaskID,
        *,
        completed: float | None = None,
        total: float | None = None,
        description: str | None = None,
        note: str | None = None,
    ) -> None:
        kwargs: dict[str, object] = {}
        if completed is not None:
            kwargs["completed"] = completed
        if total is not None:
            kwargs["total"] = total
        if description is not None:
            kwargs["description"] = description
        if note is not None:
            kwargs["note"] = note
        self._progress.update(task_id, **kwargs)

    def remove_task(self, task_id: TaskID) -> None:
        self._progress.remove_task(task_id)


@contextmanager
def progress_session() -> Iterator[ProgressManager]:
    pm = ProgressManager.instance()
    pm.start()
    try:
        yield pm
    finally:
        pm.stop()
