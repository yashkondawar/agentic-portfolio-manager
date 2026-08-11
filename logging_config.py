import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from core.storage import connect

agent_id_ctx: ContextVar[str] = ContextVar("agent_id", default="-")
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="-")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.agent_id = agent_id_ctx.get()
        record.session_id = session_id_ctx.get()
        return True


class SQLiteLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.connection = connect(check_same_thread=False)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.connection.execute(
                """
                INSERT INTO application_logs(
                    created_at, level, logger, message, session_id, agent_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                    record.levelname,
                    record.name,
                    record.getMessage(),
                    getattr(record, "session_id", None),
                    getattr(record, "agent_id", None),
                ),
            )
            self.connection.commit()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self.connection.close()
        finally:
            super().close()


def setup_logging(app_name: str = "stock_research") -> None:
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - "
        "session=%(session_id)s agent=%(agent_id)s "
        "%(name)s - %(message)s"
    )

    sqlite_handler = SQLiteLogHandler()
    sqlite_handler.setFormatter(formatter)
    sqlite_handler.addFilter(ContextFilter())

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.addHandler(sqlite_handler)
    root.addHandler(stream_handler)
