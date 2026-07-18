from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import jwt
import redis.asyncio as aioredis
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.db import connection
from models.users import Token, User

_ph = PasswordHasher()


class CryptoService:
    """Сервис хеширования и верификации паролей в пуле потоков."""

    async def hash_password(self, password: str) -> str:
        """Сгенерировать хэш Argon2id без блокировки Event Loop."""
        return await run_in_threadpool(_ph.hash, password)

    async def verify_password(
        self, plain_password: str, hashed_password: str
    ) -> bool:
        """Сверить пароль с хэшем в независимом пуле потоков."""
        try:
            await run_in_threadpool(
                _ph.verify, hashed_password, plain_password
            )
            return True
        except (VerifyMismatchError, Exception):
            return False


class JwtService:
    """Сервис для сборки, разбора и валидации JWT-сессий в СУБД."""

    def _encode_token(self, payload: dict[str, Any]) -> str:
        """Синхронная утилита кодирования токена."""
        return jwt.encode(
            payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

    def _decode_token(self, token: str) -> dict[str, Any]:
        """Синхронная утилита декодирования токена."""
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

    def _calculate_exp(self, delta: timedelta) -> int:
        """Рассчитать целочисленный UNIX-timestamp в UTC для поля exp."""
        tz_utc = ZoneInfo('UTC')
        return int((datetime.now(tz_utc) + delta).timestamp())

    async def verify_token_payload(
        self, token: str, expected_type: str
    ) -> dict[str, Any]:
        """Разобрать и валидировать тип и время жизни токена."""
        try:
            payload = await run_in_threadpool(self._decode_token, token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    'type': 'Ошибка авторизации',
                    'field': 'Authorization',
                    'msg': 'Срок действия токена истек.',
                },
            ) from None
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    'type': 'Ошибка авторизации',
                    'field': 'Authorization',
                    'msg': 'Невалидный токен.',
                },
            ) from None

        if payload.get('type') != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    'type': 'Ошибка авторизации',
                    'field': 'Authorization',
                    'msg': 'Неверный тип токена.',
                },
            ) from None
        return payload

    async def create_confirmation_token(self, user_id: int) -> str:
        """Создать токен подтверждения регистрации."""
        delta = timedelta(hours=settings.CONFIRM_TOKEN_LIFETIME_HOURS)
        payload = {
            'user_id': user_id,
            'type': 'confirm',
            'exp': self._calculate_exp(delta),
        }
        return await run_in_threadpool(self._encode_token, payload)

    async def create_password_recovery_token(self, user_id: int) -> str:
        """Создать токен восстановления пароля на 15 минут."""
        payload = {
            'user_id': user_id,
            'type': 'password_recovery',
            'exp': self._calculate_exp(timedelta(minutes=15)),
        }
        return await run_in_threadpool(self._encode_token, payload)

    @connection
    async def create_token_pair(
        self, user_id: int, session: AsyncSession
    ) -> dict[str, str]:
        """Сгенерировать и атомарно сохранить пару сессионных токенов."""
        acc_delta = timedelta(minutes=settings.ACCESS_TOKEN_LIFETIME_MINUTS)
        ref_delta = timedelta(hours=settings.REFRESH_TOKEN_LIFETIME_HOURS)

        access_payload = {
            'user_id': user_id,
            'type': 'access',
            'exp': self._calculate_exp(acc_delta),
        }
        refresh_payload = {
            'user_id': user_id,
            'type': 'refresh',
            'exp': self._calculate_exp(ref_delta),
        }

        access_token = await run_in_threadpool(
            self._encode_token, access_payload
        )
        refresh_token = await run_in_threadpool(
            self._encode_token, refresh_payload
        )

        token_record = Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            is_active=True,
        )
        session.add(token_record)
        await session.commit()

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
        }

    @connection
    async def get_token_by_refresh(
        self, token_str: str, session: AsyncSession
    ) -> Token | None:
        """Извлечь токен обновления из PostgreSQL."""
        query = (
            select(Token)
            .where(Token.refresh_token == token_str)
            .order_by(Token.id.desc())
        )
        result = await session.execute(query)
        return result.scalars().first()

    @connection
    async def get_token_by_access(
        self, token_str: str, session: AsyncSession
    ) -> Token | None:
        """Извлечь токен доступа из PostgreSQL."""
        query = (
            select(Token)
            .where(Token.access_token == token_str)
            .order_by(Token.id.desc())
        )
        result = await session.execute(query)
        return result.scalars().first()


class BruteForceService:
    """Сервис защиты от брутфорса на базе скользящих счетчиков Redis."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self._max_attempts = settings.LOGIN_MAX_ATTEMPTS
        self._lock_timeout = settings.USER_LOCK_TIMEOUT

    async def check_lock_status(self, user: User) -> None:
        """Проверить, заблокирован ли аккаунт, и рассчитать TTL."""
        if user.is_blocked:
            lock_key = f'locked_user:{user.email}'
            ttl = await self.redis.ttl(lock_key)
            minutes_left = max(1, ttl // 60) if ttl > 0 else 1
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    'type': 'Аккаунт заблокирован.',
                    'field': '',
                    'msg': (
                        f'Превышено число попыток. Попробуйте через '
                        f'{minutes_left} мин.'
                    ),
                },
            )

    async def register_failed_attempt(self, user: User) -> int:
        """Инкрементировать счетчик ошибок в Redis и вернуть его значение."""
        attempts_key = f'login_attempts:{user.email}'
        lock_key = f'locked_user:{user.email}'

        attempts = await self.redis.incr(attempts_key)
        if attempts == 1:
            await self.redis.expire(attempts_key, self._lock_timeout)

        if attempts >= self._max_attempts:
            await self.redis.set(lock_key, '1', ex=self._lock_timeout)
            await self.redis.delete(attempts_key)

        return attempts

    async def clear_attempts(self, email: str) -> None:
        """Сбросить счетчик неудачных попыток входа при успехе."""
        attempts_key = f'login_attempts:{email}'
        await self.redis.delete(attempts_key)


class AuthService:
    """Главный фасад-контроллер над всеми подсистемами авторизации."""

    def __init__(self) -> None:
        self.redis = aioredis.from_url(
            settings.redis_settings.redis_url, decode_responses=True
        )
        self.crypto = CryptoService()
        self.jwt = JwtService()
        self.brute_force = BruteForceService(self.redis)

    @connection
    async def _execute_db_lock(
        self, user: User, session: AsyncSession
    ) -> None:
        """Изолированная хирургическая транзакция блокировки в СУБД."""
        session.add(user)
        user.is_blocked = True
        await session.commit()

    async def handle_login_attempt(
        self, user: User, plain_password: str
    ) -> None:
        """Валидировать попытку входа с выводом оставшихся попыток из ТЗ."""
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    'type': 'Доступ запрещен.',
                    'field': '',
                    'msg': 'Аккаунт не активирован или удален.',
                },
            )

        # 1. Проверяем блокировку по Redis (база данных не трогается)
        await self.brute_force.check_lock_status(user)

        # 2. Верифицируем хэш Argon2 в пуле потоков
        is_password_correct = await self.crypto.verify_password(
            plain_password, user.password
        )

        # 3. Если пароль верный — очищаем кэш брутфорса и выходим
        if is_password_correct:
            await self.brute_force.clear_attempts(user.email)
            return

        # 4. Если пароль неверный — инкрементируем попытки в Redis
        attempts_count = await self.brute_force.register_failed_attempt(user)

        # 5. Если это 5-я попытка — атомарно блокируем в Postgres
        if attempts_count >= self.brute_force._max_attempts:
            await self._execute_db_lock(user=user)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    'type': 'Аккаунт заблокирован.',
                    'field': '',
                    'msg': (
                        'Вы ввели неверный пароль 5 раз. '
                        'Аккаунт заблокирован на 1 час.'
                    ),
                },
            )

        # 6. Рассчитываем остаток попыток для ТЗ
        attempts_left = self.brute_force._max_attempts - attempts_count

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка авторизации.',
                'field': 'password',
                'msg': (
                    f'Неверный логин или пароль. '
                    f'Осталось попыток: {attempts_left}.'
                ),
            },
        )

    @connection
    async def deactivate_token_object(
        self, token_record: Token, session: AsyncSession
    ) -> None:
        """Выставить флаг неактивности сессии токена."""
        session.add(token_record)
        token_record.is_active = False
        await session.commit()


# Экспортируем синглтон-клиент для всего приложения FastAPI
auth_service = AuthService()
