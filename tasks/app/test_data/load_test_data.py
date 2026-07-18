import os
from pathlib import Path

import psycopg2
from csv_generator import (
    create_attachments_csv,
    create_avatars_csv,
    create_projects_csv,
    create_subtasks_csv,
    create_tags_csv,
    create_task_attachments_csv,
    create_task_tag_csv,
    create_tasklists_csv,
    create_tasks_csv,
    create_users_csv,
)
from dotenv import load_dotenv

load_dotenv()

DB_URL = (
    f'postgresql://{os.getenv("TASKS_DB_USER")}:'
    f'{os.getenv("TASKS_DB_PASSWORD")}@'
    f'{os.getenv("TASKS_DB_HOST")}:'
    f'{os.getenv("TASKS_DB_PORT")}/'
    f'{os.getenv("TASKS_DB")}'
)
CSV_DIR = Path(__file__).parent / 'csv_data'
CSV_DIR.mkdir(exist_ok=True)


def load_test_data() -> None:
    """Функция загрузки тестовых данных."""
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        print('\n✅ Подключено к базе данных')

        # Создаем CSV файлы
        print('\n📁 Создание CSV файлов:')
        print('=' * 50)
        users_csv = create_users_csv()
        projects_csv = create_projects_csv()
        tasklists_csv = create_tasklists_csv()
        tasks_csv = create_tasks_csv()
        tags_csv = create_tags_csv()
        subtasks_csv = create_subtasks_csv()
        attachments_csv = create_attachments_csv()
        task_tag_csv = create_task_tag_csv()
        task_attachments_csv = create_task_attachments_csv()
        avatars_csv = create_avatars_csv()

        print('\n🧹 Очистка таблиц:')
        print('=' * 50)
        tables_order = [
            'task_attachments',
            'task_tag',
            'reminders',
            'subtasks',
            'tasks',
            'tasklists',
            'projects',
            'avatars',
            'tags',
            'tokens',
            'users',
            'attachments',
        ]
        for table in tables_order:
            try:
                cur.execute(f'TRUNCATE TABLE {table} RESTART IDENTITY CASCADE')
                print(f'  ✓ Очищена таблица {table}')
            except Exception as e:
                print(f'  ✗ Ошибка очистки {table}: {e}')

        print('\n📥 Загрузка данных:')
        print('=' * 50)

        with open(users_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY users '
                    '(email, password, username, timezone, is_active, role ) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(avatars_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY avatars '
                    '(filename, minio_name, mime_type, user_id) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(projects_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY projects '
                    '(name,description,deadline,status,user_id, created_at) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(tasklists_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY tasklists '
                    '(name,seq_number,status,project_id) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(tasks_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY tasks '
                    '(name, description, status, priority, '
                    'start_at, deadline, reminder_datetime, '
                    'reminder_periodic, tasklist_id, '
                    'created_at) FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(subtasks_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY subtasks '
                    '(name,task_id,status) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(tags_csv, encoding='utf-8') as f:
            cur.copy_expert(
                ('COPY tags (name,user_id) FROM STDIN WITH CSV HEADER'), f
            )

        with open(task_tag_csv, encoding='utf-8') as f:
            cur.copy_expert(
                ('COPY task_tag (task_id,tag_id) FROM STDIN WITH CSV HEADER'),
                f,
            )

        with open(attachments_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY attachments '
                    '(filename, size, minio_name, mime_type) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        with open(task_attachments_csv, encoding='utf-8') as f:
            cur.copy_expert(
                (
                    'COPY task_attachments '
                    '(task_id,attachment_id) '
                    'FROM STDIN WITH CSV HEADER'
                ),
                f,
            )

        conn.commit()
        print('\n✅ Все данные успешно загружены!')
        print(f'📁 CSV файлы сохранены в: {CSV_DIR}')
        print('\n' + '=' * 50)
        print('👥 СОЗДАННЫЕ ПОЛЬЗОВАТЕЛИ:')
        print('=' * 50)

        cur.execute("""
                    SELECT email, username, is_active, role
                    FROM users
                    ORDER BY id
                """)
        cur.fetchall()

        print('\n' + '=' * 50)
        print('🔑 ЛОГИНЫ И ПАРОЛИ:')
        print('=' * 50)

        cur.execute('SELECT email FROM users ORDER BY id')
        for (email,) in cur.fetchall():
            password = email.split('@')[0] + 'Test123!'
            print(f'  {email} : {password}')

        print('=' * 50)

    except Exception as e:
        print(f'\n❌ Ошибка: {e}')
        if conn:
            conn.rollback()
            print('🔄 Выполнен откат транзакции')
        import traceback

        traceback.print_exc()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


if __name__ == '__main__':
    load_test_data()
