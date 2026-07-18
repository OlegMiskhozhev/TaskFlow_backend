import secrets
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException, status

from core.config import settings
from models.users import User
from services.auth import auth_service  # Перешли на универсальный фасад
from services.base import service
from services.users import get_user_by_email

ParseFunc = Callable[[dict[str, Any], str], dict[str, str]]


class OAuthProvider:
    """Универсальный класс OAuth2 провайдера."""

    def __init__(
        self,
        name: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_url: str,
        userinfo_url: str,
        parse_user_info_func: ParseFunc,
    ) -> None:
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_url = token_url
        self.userinfo_url = userinfo_url
        self.parse_user_info = parse_user_info_func

    def _raise_oauth_error(self, field: str, message: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': f'Ошибка авторизации через {self.name}',
                'field': field,
                'msg': message,
            },
        )

    async def get_user_data(self, code: str) -> dict[str, str]:
        """Универсальный пайплайн запросов к OAuth-сервисам."""
        t_url = str(self.token_url)
        u_url = str(self.userinfo_url)

        async with httpx.AsyncClient(base_url='') as client:
            # 1. Обмен кода на токен
            try:
                token_resp = await client.post(
                    t_url,
                    data={
                        'client_id': self.client_id,
                        'client_secret': self.client_secret,
                        'code': code,
                        'redirect_uri': self.redirect_uri,
                        'grant_type': 'authorization_code',
                    },
                    timeout=10.0,
                )
            except httpx.RequestError as exc:
                self._raise_oauth_error(
                    'network', f'Ошибка сети при запросе токена: {exc}'
                )

            if token_resp.status_code != 200:
                self._raise_oauth_error(
                    'code',
                    'Не удалось обменять код на токен. Код устарел.',
                )

            token_json = token_resp.json()
            access_token = token_json.get('access_token')

            if not access_token:
                self._raise_oauth_error(
                    'access_token', 'Провайдер не вернул access_token.'
                )

            # 2. Запрос данных профиля
            try:
                user_resp = await client.get(
                    f'{u_url}?access_token={access_token}',
                    timeout=10.0,
                )
            except httpx.RequestError as exc:
                self._raise_oauth_error(
                    'network', f'Ошибка сети при запросе профиля: {exc}'
                )

            if user_resp.status_code != 200:
                self._raise_oauth_error(
                    'oauth_token', 'Токен не принят сервером провайдера.'
                )

            # 3. Распаковка данных
            parsed_data = await self.parse_user_info(
                user_resp.json(), access_token
            )

            if not parsed_data.get('email'):
                self._raise_oauth_error(
                    'email', 'Профиль не предоставил email-адрес.'
                )

            return parsed_data


# --- ФУНКЦИИ ПАРСИНГА ПРОФИЛЕЙ ---


async def parse_google_info(
    data: dict[str, Any], access_token: str
) -> dict[str, str]:
    email = data.get('email')
    username = (
        data.get('given_name')
        or data.get('name')
        or (email.split('@')[0] if email else 'Google User')
    )
    return {'email': email, 'username': username}


async def parse_gitlab_info(
    data: dict[str, Any],
    access_token: str,
) -> dict[str, str]:
    email = data.get('email')

    if not email:
        async with httpx.AsyncClient(base_url='') as client:
            emails_resp = await client.get(
                'https://gitlab.com',
                headers={'Authorization': f'Bearer {access_token}'},
            )
            if emails_resp.status_code == 200:
                resp_json = emails_resp.json()

                if isinstance(resp_json, list) and resp_json:
                    email = resp_json[0].get('email')
                elif isinstance(resp_json, dict):
                    email = resp_json.get('email')

    username = (
        data.get('username')
        or data.get('name')
        or (email.split('@')[0] if email else 'GitLab User')
    )
    return {'email': email, 'username': username}


# --- ГЛОБАЛЬНЫЙ СЛОВАРЬ КЛИЕНТОВ ---

PROVIDERS: dict[str, OAuthProvider] = {
    'google': OAuthProvider(
        name='Google',
        client_id=settings.google_settings.GOOGLE_CLIENT_ID,
        client_secret=settings.google_settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.google_settings.GOOGLE_REDIRECT_URI,
        token_url='https://oauth2.googleapis.com/token',
        userinfo_url='https://www.googleapis.com/oauth2/v3/userinfo',
        parse_user_info_func=parse_google_info,
    ),
    'gitlab': OAuthProvider(
        name='GitLab',
        client_id=settings.gitlab_settings.GITLAB_CLIENT_ID,
        client_secret=settings.gitlab_settings.GITLAB_CLIENT_SECRET,
        redirect_uri=settings.gitlab_settings.GITLAB_REDIRECT_URI,
        token_url='https://gitlab.com/oauth/token',
        userinfo_url='https://gitlab.com/api/v4/user',
        parse_user_info_func=parse_gitlab_info,
    ),
}


# --- БИЗНЕС-ЛОГИКА ---


async def process_oauth_login(provider_name: str, code: str) -> dict[str, str]:
    """Основной метод авторизации/регистрации пользователей через OAuth2."""
    provider = PROVIDERS.get(provider_name.lower())

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка конфигурации OAuth',
                'field': 'provider',
                'msg': f"Провайдер '{provider_name}' не поддерживается.",
            },
        )

    user_data = await provider.get_user_data(code)

    email = user_data['email']
    username = user_data['username']

    user: User = await get_user_by_email(email)

    if not user:
        random_password = secrets.token_urlsafe(16)
        # Оптимизировано: хешируем случайный пароль в пуле потоков
        hashed_pwd = await auth_service.crypto.hash_password(random_password)

        new_user_data = {
            'email': email,
            'username': username,
            'password': hashed_pwd,
            'is_active': True,
        }
        user = await service.add(model=User, values=new_user_data)
    elif not user.is_active:
        user = await service.update(
            model=User, id=user.id, values={'is_active': True}
        )

    # Оптимизировано: вызов токенов через наш сгруппированный JwtService
    tokens = await auth_service.jwt.create_token_pair(user_id=user.id)

    return {
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
    }


def get_provider_auth_url(provider_name: str) -> str:
    """Возвращает готовую ссылку для авторизации из f-строк."""
    name_lower = provider_name.lower()

    providers_links: dict[str, str] = {
        'google': (
            'https://accounts.google.com/o/oauth2/v2/auth'
            f'?client_id={settings.google_settings.GOOGLE_CLIENT_ID}'
            f'&redirect_uri={settings.google_settings.GOOGLE_REDIRECT_URI}'
            '&response_type=code'
            '&scope=openid+email+profile'
            '&access_type=offline'
            '&prompt=consent'
        ),
        'gitlab': (
            'https://gitlab.com/oauth/authorize'
            f'?client_id={settings.gitlab_settings.GITLAB_CLIENT_ID}'
            f'&redirect_uri={settings.gitlab_settings.GITLAB_REDIRECT_URI}'
            '&response_type=code'
            '&scope=read_user'
            '&state=AAA'
        ),
    }

    auth_url = providers_links.get(name_lower)

    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка конфигурации OAuth',
                'field': 'provider',
                'msg': f"Провайдер '{provider_name}' не поддерживается.",
            },
        )

    return auth_url
