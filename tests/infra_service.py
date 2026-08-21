import os
import subprocess
import time
from abc import ABC, abstractmethod


class BaseTestInfraService(ABC):
    """Абстрактный интерфейс управления тестовой инфраструктурой."""

    @abstractmethod
    def start_infra(self) -> None:
        pass

    @abstractmethod
    def stop_infra(self) -> None:
        pass

    @abstractmethod
    def get_db_url(self) -> str:
        pass


class DockerSubprocessInfraService(BaseTestInfraService):
    """Управляет тестовым контейнером PostgreSQL через subprocess."""

    def __init__(
        self,
        container_name: str,
        env_file_path: str,
        host_port: int,
        db_image: str = 'postgres:14.0',
    ) -> None:
        self._container_name = container_name
        self._env_file = env_file_path
        self._port = host_port
        self._image = db_image

    def start_infra(self) -> None:
        """Запуск контейнера СУБД с верификацией готовности."""
        print(
            f'\n[INFRA] Зачистка старого контейнера {self._container_name}...',
            flush=True,
        )
        self.stop_infra()

        print(
            f'[INFRA] Запуск тестовой СУБД на порту {self._port}...',
            flush=True,
        )
        cmd = [
            'docker',
            'run',
            '-d',
            '--name',
            self._container_name,
            '--env-file',
            self._env_file,
            '-p',
            f'{self._port}:5432',
            self._image,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

        # 🧠 Умный опрос готовности СУБД (Healthcheck)
        print(
            '[INFRA] Ожидание инициализации кластера PostgreSQL: ',
            end='',
            flush=True,
        )

        # Задаем имя пользователя для проверки
        user = os.getenv('POSTGRES_USER', 'admin')
        ready_cmd = [
            'docker',
            'exec',
            self._container_name,
            'pg_isready',
            '-U',
            user,
        ]

        # Пытаемся достучаться до базы максимум 15 секунд
        for _attempt in range(15):
            result = subprocess.run(
                ready_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if result.returncode == 0:
                print('База готова! 🚀\n', flush=True)
                # Даем полсекунды на окончательную стабилизацию сокетов
                time.sleep(0.5)
                return

            print('. ', end='', flush=True)
            time.sleep(1)

        print('Внимание: Таймаут инициализации СУБД!\n', flush=True)

    def stop_infra(self) -> None:
        """Принудительное удаление контейнера с выводом статуса."""
        # Проверяем существование контейнера перед остановкой
        check_cmd = [
            'docker', 'ps', '-a', '-q', '-f',
            f'name={self._container_name}',
        ]
        result = subprocess.run(check_cmd, capture_output=True, text=True)

        if result.stdout.strip():
            print(
                f'[INFRA] Остановка и удаление контейнера'
                f'{self._container_name}...',
                flush=True,
            )
            subprocess.run(
                ['docker', 'stop', self._container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ['docker', 'rm', '-v', self._container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def get_db_url(self) -> str:
        user: str = os.getenv('POSTGRES_USER', 'admin')
        password: str = os.getenv('POSTGRES_PASSWORD', 'admin123')
        host: str = os.getenv('POSTGRES_HOST', 'localhost')
        db: str = os.getenv('POSTGRES_DB', 'test_db')
        return (
            f'postgresql+asyncpg://{user}:{password}@{host}:{self._port}/{db}'
        )
