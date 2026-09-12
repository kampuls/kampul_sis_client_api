import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.hot_events import (
    create_hot_event,
    get_active_hot_events_list,
    get_visible_hot_event_history,
)
from app.models.hot_event import HotEvent, HotEventImpression
from app.schemas import HotEventCreate


class _ParentUser:
    id = 7
    role = None
    is_parent = True


def _session():
    engine = create_engine('sqlite:///:memory:')
    HotEvent.__table__.create(engine)
    HotEventImpression.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_popup_filter_returns_every_supported_popup_type():
    db = _session()
    now = datetime.now()
    event_types = (
        'banner',
        'popup_promotion',
        'popup_announcement',
        'popup_reminder',
    )
    db.add_all(
        [
            HotEvent(
                title=event_type,
                message='Message',
                start_at=now - timedelta(minutes=1),
                end_at=now + timedelta(days=1),
                audience='all',
                event_type=event_type,
                is_active=True,
            )
            for event_type in event_types
        ]
    )
    db.commit()

    popups = asyncio.run(
        get_active_hot_events_list(
            type='popup',
            db=db,
            current_user=_ParentUser(),
        )
    )
    banners = asyncio.run(
        get_active_hot_events_list(
            type='banner',
            db=db,
            current_user=_ParentUser(),
        )
    )

    assert {event.event_type for event in popups} == {
        'popup_promotion',
        'popup_announcement',
        'popup_reminder',
    }
    assert [event.event_type for event in banners] == ['banner']
    db.close()


def test_history_includes_expired_events_but_only_for_assigned_audience():
    db = _session()
    now = datetime.now()
    db.add_all(
        [
            HotEvent(
                title='Past parent post',
                message='Still available in history',
                start_at=now - timedelta(days=3),
                end_at=now - timedelta(days=2),
                audience='parent',
                event_type='banner',
                is_active=True,
            ),
            HotEvent(
                title='Teacher only',
                message='Not visible to parents',
                end_at=now + timedelta(days=1),
                audience='teacher',
                event_type='popup_announcement',
                is_active=True,
            ),
            HotEvent(
                title='Hidden post',
                message='Not visible while inactive',
                end_at=now + timedelta(days=1),
                audience='all',
                event_type='banner',
                is_active=False,
            ),
        ]
    )
    db.commit()

    history = asyncio.run(
        get_visible_hot_event_history(db=db, current_user=_ParentUser())
    )

    assert [event.title for event in history] == ['Past parent post']
    assert history[0].end_at < now
    db.close()


def test_deleted_event_is_removed_from_history():
    db = _session()
    event = HotEvent(
        title='Temporary post',
        message='Delete me',
        end_at=datetime.now() - timedelta(days=1),
        audience='all',
        event_type='banner',
        is_active=True,
    )
    db.add(event)
    db.commit()

    before_delete = asyncio.run(
        get_visible_hot_event_history(db=db, current_user=_ParentUser())
    )
    assert [item.title for item in before_delete] == ['Temporary post']

    db.delete(event)
    db.commit()
    after_delete = asyncio.run(
        get_visible_hot_event_history(db=db, current_user=_ParentUser())
    )
    assert after_delete == []
    db.close()


class _CreateDb:
    added = None

    def add(self, event):
        self.added = event
        event.id = 12
        event.created_at = datetime.now()

    def commit(self):
        pass

    def refresh(self, event):
        pass


def test_create_preserves_popup_footer_text():
    db = _CreateDb()
    body = HotEventCreate(
        title='Reminder',
        message='Bring your uniform',
        end_at=datetime.now() + timedelta(days=1),
        event_type='popup_reminder',
        status_text='Urgent',
        send_notification=False,
    )

    with patch('app.api.v1.hot_events._is_admin', return_value=True):
        response = asyncio.run(
            create_hot_event(
                body=body,
                background_tasks=BackgroundTasks(),
                db=db,
                current_user=_ParentUser(),
            )
        )

    assert db.added.status_text == 'Urgent'
    assert response.status_text == 'Urgent'
