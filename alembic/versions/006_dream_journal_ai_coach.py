"""dream journal tables and default symbols

Revision ID: 006
Revises: 005
Create Date: 2026-02-12
"""

from datetime import datetime
from uuid import uuid4
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_SYMBOLS: list[tuple[str, str, str, str]] = [
    ("вода", "Связь с эмоциями, восстановлением и глубинными чувствами.", "стихии", "юнгианский"),
    ("огонь", "Энергия действия, импульс и потребность проявиться.", "стихии", "юнгианский"),
    ("земля", "Опора, тело, безопасность и практические задачи.", "стихии", "интегративный"),
    ("воздух", "Мысли, идеи и стремление к свободе.", "стихии", "интегративный"),
    ("дом", "Личные границы, семья и внутреннее чувство защищенности.", "дом", "гештальт"),
    ("комната", "Отдельная часть внутреннего мира или актуальная тема.", "дом", "гештальт"),
    ("дверь", "Переход, выбор и готовность к новому этапу.", "дом", "интегративный"),
    ("окно", "Новый взгляд на привычную ситуацию.", "дом", "интегративный"),
    ("лестница", "Развитие и движение к более зрелой позиции.", "дом", "интегративный"),
    ("подвал", "Скрытые переживания и вытесненные эмоции.", "дом", "юнгианский"),
    ("крыша", "Контроль, убеждения и ощущение стабильности.", "дом", "интегративный"),
    ("море", "Сильные чувства, которые важно прожить осознанно.", "стихии", "юнгианский"),
    ("река", "Течение жизни и способность адаптироваться.", "стихии", "интегративный"),
    ("дождь", "Эмоциональная разрядка и очищение.", "погода", "интегративный"),
    ("снег", "Пауза, отстранение, необходимость замедлиться.", "погода", "интегративный"),
    ("ветер", "Перемены и внутреннее беспокойство.", "погода", "интегративный"),
    ("гроза", "Накопленное напряжение и потребность выразить чувства.", "погода", "интегративный"),
    ("солнце", "Жизненная энергия, ясность и поддержка.", "небо", "интегративный"),
    ("луна", "Интуиция, уязвимость и бессознательные процессы.", "небо", "юнгианский"),
    ("звезды", "Смысл, ориентиры и чувство направления.", "небо", "экзистенциальный"),
    ("птица", "Стремление к свободе и новому взгляду.", "животные", "интегративный"),
    ("собака", "Верность, поддержка и тема доверия.", "животные", "интегративный"),
    ("кошка", "Границы, автономия и контакт с интуицией.", "животные", "интегративный"),
    ("лошадь", "Сила, выносливость и контроль над импульсом.", "животные", "интегративный"),
    ("змея", "Тревога, трансформация и тонкая чувствительность.", "животные", "юнгианский"),
    ("рыба", "Глубинные эмоции и потребность в принятии.", "животные", "юнгианский"),
    ("волк", "Самозащита, инстинкты и социальная дистанция.", "животные", "интегративный"),
    ("медведь", "Внутренняя сила и тема личной территории.", "животные", "интегративный"),
    ("ребенок", "Уязвимая часть личности и потребность в заботе.", "люди", "гештальт"),
    ("мать", "Поддержка, контроль и ранние эмоциональные сценарии.", "люди", "психодинамический"),
    ("отец", "Правила, опора, авторитет и самооценка.", "люди", "психодинамический"),
    ("незнакомец", "Неисследованная часть себя или новый опыт.", "люди", "юнгианский"),
    ("толпа", "Социальное давление и потребность быть принятым.", "люди", "интегративный"),
    ("друг", "Поддержка, контакт и близость.", "люди", "интегративный"),
    ("бывший", "Незавершенные эмоции и повторяющийся сценарий.", "люди", "интегративный"),
    ("поезд", "Движение по жизненному пути и ритм перемен.", "транспорт", "интегративный"),
    ("самолет", "Амбиции, скачок и выход из рутины.", "транспорт", "интегративный"),
    ("машина", "Контроль над жизнью и личные решения.", "транспорт", "интегративный"),
    ("автобус", "Влияние окружения на направление выбора.", "транспорт", "интегративный"),
    ("дорога", "Путь, цели и жизненная перспектива.", "транспорт", "экзистенциальный"),
    ("мост", "Переход между этапами и примирение противоположностей.", "транспорт", "юнгианский"),
    ("погоня", "Избегание сложных эмоций или задач.", "сюжеты", "гештальт"),
    ("падение", "Потеря опоры, тревога и контроль.", "сюжеты", "интегративный"),
    ("полет", "Желание свободы и расширения возможностей.", "сюжеты", "интегративный"),
    ("экзамен", "Самооценка, страх ошибки и ожидания.", "сюжеты", "интегративный"),
    ("школа", "Обучение, социальные роли и прошлые установки.", "места", "интегративный"),
    ("больница", "Восстановление и потребность в заботе о себе.", "места", "интегративный"),
    ("лес", "Неопределенность и поиск внутреннего пути.", "места", "юнгианский"),
    ("гора", "Цель, усилие и личная зрелость.", "места", "экзистенциальный"),
    ("телефон", "Потребность в контакте и непроговоренные темы.", "предметы", "интегративный"),
    ("ключ", "Доступ к новому решению и внутренним ресурсам.", "предметы", "интегративный"),
    ("часы", "Тема времени, дедлайнов и давления ожиданий.", "предметы", "интегративный"),
]


def upgrade() -> None:
    op.create_table(
        "dreams",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("dream_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("emotions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("interpretation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("chat_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("recurring_group_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dream_symbols",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("personal_meaning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "symbol", name="uq_dream_symbols_user_symbol"),
    )

    op.create_table(
        "default_symbols",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_default_symbols_symbol"),
    )

    op.create_table(
        "dream_recurring_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("first_dream_id", sa.String(length=36), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_occurrence", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["first_dream_id"], ["dreams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "fk_dreams_recurring_group",
        "dreams",
        "dream_recurring_groups",
        ["recurring_group_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_dreams_user_profile", "dreams", ["user_id", "profile_id"], unique=False)
    op.create_index("ix_dreams_user_recorded", "dreams", ["user_id", "recorded_at"], unique=False)
    op.create_index("ix_dreams_user_recurring", "dreams", ["user_id", "is_recurring"], unique=False)
    op.create_index("ix_dreams_recurring_group_id", "dreams", ["recurring_group_id"], unique=False)
    op.create_index("ix_dream_symbols_user_symbol", "dream_symbols", ["user_id", "symbol"], unique=False)

    symbols_table = sa.table(
        "default_symbols",
        sa.column("id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("description", sa.Text),
        sa.column("category", sa.String),
        sa.column("source", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.utcnow()
    op.bulk_insert(
        symbols_table,
        [
            {
                "id": str(uuid4()),
                "symbol": symbol,
                "description": description,
                "category": category,
                "source": source,
                "created_at": now,
            }
            for symbol, description, category, source in DEFAULT_SYMBOLS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_dream_symbols_user_symbol", table_name="dream_symbols")
    op.drop_index("ix_dreams_recurring_group_id", table_name="dreams")
    op.drop_index("ix_dreams_user_recurring", table_name="dreams")
    op.drop_index("ix_dreams_user_recorded", table_name="dreams")
    op.drop_index("ix_dreams_user_profile", table_name="dreams")

    op.drop_constraint("fk_dreams_recurring_group", "dreams", type_="foreignkey")
    op.drop_table("dream_recurring_groups")
    op.drop_table("default_symbols")
    op.drop_table("dream_symbols")
    op.drop_table("dreams")
