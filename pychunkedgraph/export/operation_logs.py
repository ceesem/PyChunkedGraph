from typing import Optional
from typing import Iterable
from datetime import datetime


from ..graph import ChunkedGraph
from ..graph.attributes import OperationLogs


def _parse_attr(attr, val) -> str:
    from numpy import ndarray

    try:
        if isinstance(val, OperationLogs.StatusCodes):
            return (attr.key, val.value)
        if isinstance(val, ndarray):
            return (attr.key, val.tolist())
        return (attr.key, val)
    except AttributeError:
        return (attr, val)


def get_parsed_logs(
    cg: ChunkedGraph, start_time: Optional[datetime] = None
) -> Iterable[dict]:
    """Parse logs for compatibility with destination platform."""
    from .models import OperationLog

    logs = cg.client.read_log_entries(start_time=start_time)
    result = []
    for _id, _log in logs.items():
        log = {"id": int(_id)}
        log["status"] = int(_log.get("operation_status", 0))
        for attr, val in _log.items():
            attr, val = _parse_attr(attr, val)
            try:
                log[attr.decode("utf-8")] = val
            except AttributeError:
                log[attr] = val
        result.append(OperationLog(**log))
    return result


def get_logs_with_previous_roots(cg: ChunkedGraph, parsed_logs: Iterable) -> Iterable:
    """
    Adds a new entry for new roots' previous IDs.
    And timestamps for those roots.
    """
    from numpy import unique
    from numpy import concatenate
    from ..graph.lineage import get_previous_root_ids
    from ..graph.utils.context_managers import TimeIt

    roots = []
    for log in parsed_logs:
        roots.append(log.roots)
    roots = concatenate(roots)
    # get previous roots for all to avoid multiple network calls
    old_roots_d = get_previous_root_ids(cg, roots)
    old_roots_all = concatenate([*old_roots_d.values()])
    old_roots_ts = cg.get_node_timestamps(old_roots_all).tolist()
    old_roots_ts_d = dict(zip(old_roots_all, old_roots_ts))

    for log in parsed_logs:
        try:
            old_roots = concatenate([old_roots_d[id_] for id_ in log.roots])
            log.old_roots = unique(old_roots).tolist()
            log.old_roots_ts = [old_roots_ts_d[id_] for id_ in log.old_roots]
        except (KeyError, ValueError):
            log.status = OperationLogs.StatusCodes.WRITE_FAILED.value
            # print("failed write", log.id, log.roots)
    return parsed_logs
