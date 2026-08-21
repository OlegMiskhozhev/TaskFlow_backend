import pytest
from fastapi import HTTPException, status

from schemas.tags import TaskTags
from services.tags import search_tags, set_task_tags


@pytest.mark.asyncio
class TestTagsServiceIntegration:
    """Интеграционные тесты слоя бизнес-логики и связей тегов."""

    async def test_set_task_tags_add_and_remove(
        self,
        db_session,
        test_user,
        create_custom_task_factory,
        create_test_tag_factory,
    ):
        """Тест: успешное прикрепление и обновление M2M-связей тегов."""
        task = await create_custom_task_factory(test_user)

        tag1 = await create_test_tag_factory(test_user.id, 'tag1')
        tag2 = await create_test_tag_factory(test_user.id, 'tag2')
        tag3 = await create_test_tag_factory(test_user.id, 'tag3')

        await set_task_tags(
            user_id=test_user.id,
            task_id=task.id,
            new_tag_ids_model=TaskTags(tag_ids=[tag1.id, tag2.id]),
        )

        db_session.expire_all()
        await db_session.refresh(task)
        assert {t.id for t in task.tags} == {tag1.id, tag2.id}

        # Мутируем пачку: удаляем tag1, сохраняем tag2, докидываем tag3
        await set_task_tags(
            user_id=test_user.id,
            task_id=task.id,
            new_tag_ids_model=TaskTags(tag_ids=[tag2.id, tag3.id]),
        )

        db_session.expire_all()
        await db_session.refresh(task)
        assert {t.id for t in task.tags} == {tag2.id, tag3.id}

    async def test_set_task_tags_validation_error_on_alien_tag(
        self,
        db_session,
        test_user,
        test_inactive_user,
        create_custom_task_factory,
        create_test_tag_factory,
    ):
        """Тест: попытка привязать чужой тег вызывает ошибку 404."""
        task = await create_custom_task_factory(test_user)
        # Создаем тег, принадлежащий другому аккаунту
        alien_tag = await create_test_tag_factory(test_inactive_user.id, 'bad')

        with pytest.raises(HTTPException) as exc:
            await set_task_tags(
                user_id=test_user.id,
                task_id=task.id,
                new_tag_ids_model=TaskTags(tag_ids=[alien_tag.id]),
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_search_tags_by_substring(
        self, db_session, test_user, create_test_tag_factory
    ):
        """Тест: поисковая LIKE-выборка тегов пользователя по подстроке."""
        await create_test_tag_factory(test_user.id, 'important')
        await create_test_tag_factory(test_user.id, 'import')
        await create_test_tag_factory(test_user.id, 'urgent')

        result = await search_tags(user_id=test_user.id, search_param='imp')
        names = [t.name for t in result]

        assert 'important' in names
        assert 'import' in names
        assert 'urgent' not in names

    async def test_search_tags_empty_result(
        self, db_session, test_user, create_test_tag_factory
    ):
        """Тест: при отсутствии совпадений возвращается пустой массив."""
        await create_test_tag_factory(test_user.id, 'backend')

        result = await search_tags(user_id=test_user.id, search_param='front')
        assert len(result) == 0
