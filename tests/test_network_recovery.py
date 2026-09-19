"""Exercise the real application lifecycle with Telegram's HTTP boundary replaced."""

import asyncio
import logging
from collections import Counter
from urllib.parse import parse_qs

import httpx
import pytest
from telegram.error import BadRequest, InvalidToken, NetworkError, TimedOut
from telegram.ext import Application
from telegram.request import HTTPXRequest

import bot


@pytest.fixture
def run_bot(monkeypatch):
    """Run main without credentials, real network traffic, or OS signal handlers."""
    def run(transport_handler):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        original_run_polling = Application.run_polling
        applications = []
        watchdog_fired = []

        def run_polling(application, **kwargs):
            applications.append(application)

            def stop_on_timeout():
                watchdog_fired.append(True)
                application.stop_running()

            watchdog = loop.call_later(10, stop_on_timeout)
            try:
                return original_run_polling(
                    application, **kwargs, close_loop=False, stop_signals=None,
                )
            finally:
                watchdog.cancel()

        def stop():
            loop.call_soon(applications[0].stop_running)

        monkeypatch.setattr(bot, 'BOT_TOKEN', '123456:TEST_ONLY')
        monkeypatch.setattr(Application, 'run_polling', run_polling)
        monkeypatch.setattr(
            HTTPXRequest, '_build_client',
            lambda self: httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: transport_handler(request, stop)),
                timeout=1,
            ),
        )
        try:
            bot.main()
            assert not watchdog_fired, 'Bot did not recover and answer /start'
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            asyncio.set_event_loop(None)

    return run


@pytest.mark.parametrize('failing_method', ['getMe', 'deleteWebhook', 'getUpdates'])
def test_bot_answers_after_connection_recovers(run_bot, failing_method, caplog):
    """Startup retries and polling must survive protocol and DNS failures."""
    calls = Counter()
    replies = []
    update_sent = False

    async def telegram(request, stop):
        nonlocal update_sent
        method = request.url.path.rsplit('/', 1)[-1]
        calls[method] += 1
        if method == failing_method:
            if calls[method] == 1:
                raise httpx.RemoteProtocolError('Server disconnected without sending a response.')
            if calls[method] == 2:
                raise httpx.ConnectError('[Errno -3] Temporary failure in name resolution')
        if method == 'getMe':
            result = {'id': 123456, 'is_bot': True, 'first_name': 'Test', 'username': 'test_bot'}
        elif method == 'deleteWebhook':
            result = True
        elif method == 'getUpdates':
            if update_sent:
                await asyncio.sleep(0.01)
                result = []
            else:
                update_sent = True
                result = [{
                    'update_id': 1,
                    'message': {
                        'message_id': 1, 'date': 1,
                        'chat': {'id': 42, 'type': 'private'},
                        'from': {'id': 42, 'is_bot': False, 'first_name': 'User'},
                        'text': '/start',
                        'entities': [{'type': 'bot_command', 'offset': 0, 'length': 6}],
                    },
                }]
        elif method == 'sendMessage':
            payload = parse_qs(request.content.decode())
            replies.append(payload)
            result = {
                'message_id': 2, 'date': 1,
                'chat': {'id': 42, 'type': 'private'}, 'text': payload['text'][0],
            }
            stop()
        else:
            pytest.fail(f'Unexpected Telegram method: {method}')
        return httpx.Response(200, json={'ok': True, 'result': result})

    with caplog.at_level(logging.WARNING):
        run_bot(telegram)

    assert calls[failing_method] >= 3
    assert len(replies) == 1
    assert replies[0]['chat_id'] == ['42']
    assert 'Привет' in replies[0]['text'][0]
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_invalid_token_is_not_retried(run_bot):
    async def telegram(request, stop):
        return httpx.Response(401, json={'ok': False, 'error_code': 401, 'description': 'Unauthorized'})

    with pytest.raises(InvalidToken):
        run_bot(telegram)


@pytest.mark.parametrize('error', [NetworkError('connection lost'), TimedOut()])
async def test_network_error_is_logged_without_traceback(error, caplog):
    from types import SimpleNamespace

    with caplog.at_level(logging.WARNING):
        await bot.error_handler(None, SimpleNamespace(error=error))

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert caplog.records[0].exc_info is None


@pytest.mark.parametrize('error', [BadRequest('invalid request'), RuntimeError('bug')])
async def test_non_network_errors_keep_diagnostics(error, caplog):
    from types import SimpleNamespace

    with caplog.at_level(logging.WARNING):
        await bot.error_handler(None, SimpleNamespace(error=error))

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert caplog.records[0].exc_info[1] is error
