"""tune startup vkr prompts

Revision ID: 0006_tune_startup_vkr_prompts
Revises: 0005_add_startup_vkr_agent_flow
Create Date: 2026-08-06 00:00:06.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_tune_startup_vkr_prompts"
down_revision = "0005_add_startup_vkr_agent_flow"
branch_labels = None
depends_on = None


CRITIC_SYSTEM_PROMPT = (
    "Ты независимый критик STARTUP_VKR. Проверяй только результат worker и доказательства по документу. "
    "Не переписывай работу за автора. Не проходи гейты и не меняй статус Assessment. Ответ только JSON по схеме. "
    "Пиши кратко: максимум 5 элементов в каждом списке, каждая строка до 240 символов."
)

CRITIC_USER_TEMPLATE = (
    "Агент: {{ agent_code }} {{ agent_name }}\n"
    "Правила агента: {{ agent_rules }}\n"
    "Контекст документа:\n{{ document_excerpt }}\n"
    "Результаты worker:\n{{ worker_results }}\n"
    "Верни компактный JSON без markdown."
)

FINAL_SYSTEM_PROMPT = (
    "Ты финальный эксперт STARTUP_VKR. Синтезируй заключение только из подготовленного пакета Worker и Critic. "
    "Не изменяй результаты отдельных агентов. Не выставляй overall_score без утвержденной формулы. Ответ только JSON по схеме. "
    "Пиши кратко: максимум 7 рекомендаций, каждая строка до 300 символов."
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            update prompt_templates
            set system_prompt = :system_prompt,
                user_template = :user_template
            where id = 'startup-vkr-critic-prompt'
            """
        ),
        {"system_prompt": CRITIC_SYSTEM_PROMPT, "user_template": CRITIC_USER_TEMPLATE},
    )
    bind.execute(
        sa.text(
            """
            update prompt_templates
            set system_prompt = :system_prompt
            where id = 'startup-vkr-final-prompt'
            """
        ),
        {"system_prompt": FINAL_SYSTEM_PROMPT},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            update prompt_templates
            set system_prompt = 'Ты независимый критик STARTUP_VKR. Проверяй только результат worker и доказательства по документу. Не переписывай работу за автора. Не проходи гейты и не меняй статус Assessment. Ответ только JSON по схеме.',
                user_template = 'Агент: {{ agent_code }} {{ agent_name }}
Правила агента: {{ agent_rules }}
Контекст документа:
{{ document_excerpt }}
Результаты worker:
{{ worker_results }}'
            where id = 'startup-vkr-critic-prompt'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            update prompt_templates
            set system_prompt = 'Ты финальный эксперт STARTUP_VKR. Синтезируй заключение только из подготовленного пакета Worker и Critic. Не изменяй результаты отдельных агентов. Не выставляй overall_score без утвержденной формулы. Ответ только JSON по схеме.'
            where id = 'startup-vkr-final-prompt'
            """
        )
    )
