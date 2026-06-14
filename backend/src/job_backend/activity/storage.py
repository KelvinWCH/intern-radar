from job_backend.activity.models import ActivityData, ActivityEvent, ActivityKind, ActivityRecord
from job_backend.persistence.session import Session


def record_activity(
    connection: Session,
    *,
    event_id: str,
    kind: ActivityKind,
    occurred_at: int,
    data: ActivityData,
) -> bool:
    event = ActivityEvent(id=event_id, kind=kind, occurred_at=occurred_at, data=data)
    if connection.get(ActivityRecord, event_id) is not None:
        return False
    connection.add(
        ActivityRecord(
            id=event.id,
            kind=event.kind,
            occurred_at=event.occurred_at,
            data=event.data.model_dump(mode="json"),
        )
    )
    return True
