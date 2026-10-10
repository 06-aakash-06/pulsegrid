"""Phase 2 IDs must not activate the deferred Snowflake worker algorithm."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from emergency_service.commands import _new_id
from emergency_service.exceptions import DomainHTTPException


def test_random_id_retries_collision_without_worker_mutation():
    session = AsyncMock()
    session.scalar.side_effect = [True, False]
    with patch('emergency_service.commands.secrets.randbelow', side_effect=[40, 41]):
        assert asyncio.run(_new_id(session, 6)) == 42
    assert session.scalar.await_count == 2
    session.execute.assert_not_awaited()
    assert 'id_worker_state' not in str(session.scalar.call_args.args[0])


def test_random_id_collision_budget_fails_closed():
    session = AsyncMock()
    session.scalar.return_value = True
    with pytest.raises(DomainHTTPException) as error:
        asyncio.run(_new_id(session, 6))
    assert error.value.status_code == 503
    assert session.scalar.await_count == 3
