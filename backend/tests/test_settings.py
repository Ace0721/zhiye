import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.services.ai_client import AIError
from app.routers import settings as settings_router


async def test_settings_redact_key_preserve_blank_and_validate(config: Settings) -> None:
    application = create_app(config)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            initial = (await client.get('/api/settings')).json()
            assert initial['api_key_configured'] and 'api_key' not in initial
            payload = {"base_url": "https://example.invalid/v1/", "model": "new-model", "api_key": "private-test-value"}
            response = await client.put('/api/settings', json=payload)
            assert response.status_code == 200
            assert 'private-test-value' not in response.text
            assert response.json()['base_url'] == 'https://example.invalid/v1'
            payload['api_key'] = ''
            await client.put('/api/settings', json=payload)
            from app.models import AppSetting
            with application.state.sessions() as session:
                assert session.get(AppSetting, 'api_key').value == 'private-test-value'
            payload['base_url'] = 'https://user:private-test-value@example.invalid/v1'
            response = await client.put('/api/settings', json=payload)
            assert response.status_code == 422
            assert 'private-test-value' not in response.text


@pytest.mark.parametrize('category', [None, '认证失败', '模型不存在', '网络超时', '其他'])
async def test_connection_uses_unsaved_form_and_saved_key(config: Settings, monkeypatch: pytest.MonkeyPatch, category: str | None) -> None:
    seen = []

    class FakeClient:
        def __init__(self, ai_config, timeout: int) -> None:
            seen.append(ai_config)

        async def complete(self, prompt: str, text: str, *, max_tokens: int) -> str:
            assert max_tokens == 1
            if category:
                raise AIError('脱敏错误', error_type=category)
            return 'ok'

        async def close(self) -> None:
            pass

    monkeypatch.setattr(settings_router, 'AIClient', FakeClient)
    application = create_app(config)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            result = (await client.post('/api/settings/test', json={"base_url": "https://unsaved.invalid/v1", "model": "unsaved"})).json()
            assert result['success'] is (category is None)
            assert result['error_type'] == category
            assert seen[0].api_key == config.ai_api_key
            assert seen[0].base_url == 'https://unsaved.invalid/v1'
            saved = (await client.get('/api/settings')).json()
            assert saved['model'] != 'unsaved'
