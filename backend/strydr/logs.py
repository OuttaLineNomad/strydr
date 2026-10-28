"""Structured JSON logging with the AD-10 filter: coordinates, names and bodies never reach a log line."""
import json
import logging
import re
import sys

_COORD = re.compile(r"-?\d{1,3}\.\d{4,}")
_SENSITIVE_KEYS = ("latitude", "longitude", "lat", "lon", "source_name", "body")  # extras only; never LogRecord.name


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = _COORD.sub("[redacted]", record.getMessage())
        record.msg, record.args = msg, None
        for k in _SENSITIVE_KEYS:
            if hasattr(record, k):
                setattr(record, k, "[redacted]")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        if record.exc_info:
            out["exc"] = record.exc_info[0].__name__  # class only; messages and frames could carry data
        return json.dumps(out)


def setup() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    h.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines carry URLs (and the weather grid cell)
