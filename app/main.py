import asyncio

import typer
from loguru import logger

from app.config import LOGGING_LEVEL
from config.settings import settings
from core.scheduler import SchedulerService
from database.database import initialize_database
from database.models import Queue, QueueStatus
from database.repositories import QueueRepository

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Initialize the local database before running commands."""
    initialize_database()


@app.command()
def hello() -> None:
    """Simple placeholder command for scaffold validation."""
    logger.info("MAIE scaffold is ready")
    typer.echo(f"Hello from {settings.app_name}!")


scheduler_app = typer.Typer(help="Manage the runtime scheduler")
app.add_typer(scheduler_app, name="scheduler")


queue_app = typer.Typer(help="Manually review opportunities before notification")
app.add_typer(queue_app, name="queue")


def _queue_repository(database_url: str | None) -> QueueRepository:
    """Create queue storage, allowing commands to target an explicit database."""
    initialize_database(database_url)
    return QueueRepository(database_url=database_url)


def _echo_queue(item: Queue) -> None:
    typer.echo(
        f"{item.id}\t{item.status.value}\t{item.opportunity_id}\t{item.review_notes or ''}"
    )


@queue_app.command("list")
def queue_list(
    status: QueueStatus | None = typer.Option(
        None, "--status", help="Only show this status"
    ),
    database_url: str | None = typer.Option(
        None, "--database-url", help="SQLite database path or URL"
    ),
) -> None:
    """List opportunities in the review queue."""
    repository = _queue_repository(database_url)
    items = repository.list_by_status(status) if status else repository.list()
    for item in items:
        _echo_queue(item)


def _change_queue_status(
    queue_id: str,
    action: str,
    notes: str | None,
    database_url: str | None,
) -> None:
    repository = _queue_repository(database_url)
    method = getattr(repository, action)
    item = method(queue_id, notes)
    if item is None:
        typer.echo(f"Queue item not found: {queue_id}", err=True)
        raise typer.Exit(code=1)
    _echo_queue(item)


@queue_app.command("review")
def queue_review(
    queue_id: str = typer.Argument(..., help="Queue item UUID"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Review notes"),
    database_url: str | None = typer.Option(
        None, "--database-url", help="SQLite database path or URL"
    ),
) -> None:
    """Mark an opportunity as being reviewed."""
    _change_queue_status(queue_id, "review", notes, database_url)


@queue_app.command("approve")
def queue_approve(
    queue_id: str = typer.Argument(..., help="Queue item UUID"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Approval notes"),
    database_url: str | None = typer.Option(
        None, "--database-url", help="SQLite database path or URL"
    ),
) -> None:
    """Approve an opportunity; approved items are eligible for notification."""
    _change_queue_status(queue_id, "approve", notes, database_url)


@queue_app.command("reject")
def queue_reject(
    queue_id: str = typer.Argument(..., help="Queue item UUID"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Rejection notes"),
    database_url: str | None = typer.Option(
        None, "--database-url", help="SQLite database path or URL"
    ),
) -> None:
    """Reject an opportunity so it is never notified."""
    _change_queue_status(queue_id, "reject", notes, database_url)


@queue_app.command("archive")
def queue_archive(
    queue_id: str = typer.Argument(..., help="Queue item UUID"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Archive notes"),
    database_url: str | None = typer.Option(
        None, "--database-url", help="SQLite database path or URL"
    ),
) -> None:
    """Archive an opportunity after review."""
    _change_queue_status(queue_id, "archive", notes, database_url)


@scheduler_app.command("status")
def scheduler_status() -> None:
    """Show scheduler configuration and recent execution metrics."""
    service = SchedulerService(settings=settings)
    payload = service.status()
    typer.echo(f"Scheduler running: {payload['running']}")
    typer.echo(
        f"Enabled collectors: {', '.join(payload['enabled_collectors']) or 'none'}"
    )
    typer.echo(f"Interval (minutes): {payload['interval_minutes']}")
    typer.echo(f"Metrics recorded: {payload['metrics_count']}")
    if payload["latest_metrics"]:
        for metric in payload["latest_metrics"]:
            typer.echo(
                f"- {metric['collector']}: {metric['status']} ({metric['attempts']} attempts)"
            )


@scheduler_app.command("run")
def scheduler_run(
    collector_name: str = typer.Argument(..., help="Collector name to execute once"),
) -> None:
    """Run a collector job immediately."""
    service = SchedulerService(settings=settings)
    result = asyncio.run(service.run_job(collector_name))
    typer.echo(
        f"{result['collector']}: {result['status']} "
        f"discovered={result.get('discovered', 0)} "
        f"persisted={result.get('persisted', 0)} "
        f"skipped={result.get('skipped', 0)} "
        f"failed={result.get('failed', 0)}"
    )


@scheduler_app.command("start")
def scheduler_start() -> None:
    """Start the scheduler and keep it running until interrupted."""
    async def run_scheduler() -> None:
        service = SchedulerService(settings=settings)
        service.start()
        typer.echo("Scheduler started; press Ctrl+C to stop")
        try:
            await asyncio.Event().wait()
        finally:
            service.shutdown()

    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        typer.echo("Scheduler stopped")


@scheduler_app.command("stop")
def scheduler_stop() -> None:
    """Stop the background scheduler."""
    service = SchedulerService(settings=settings)
    service.shutdown()
    typer.echo("Scheduler stopped")


logger.remove()
logger.add("logs/maie.log", rotation="1 day", level=LOGGING_LEVEL, serialize=True)


if __name__ == "__main__":
    app()
