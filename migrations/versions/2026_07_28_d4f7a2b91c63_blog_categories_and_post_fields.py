"""blog categories, richer post fields, configurable section label

Revamps the "Success Stories" section into a proper blog:
  * blog_categories — a per-doctor category entity, replacing the free-text
    gallery_posts.category string
  * gallery_posts    — description renamed to introduction, plus body (rich
    text), cover_image, category_id, display_order and display_date
  * doctor_settings  — section_label, so the doctor picks the public wording

Safe to run as a plain rename/add: the section had no rows in any environment
when this was written.

Revision ID: d4f7a2b91c63
Revises: c9e5a1f7d2b8
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4f7a2b91c63"
down_revision = "c9e5a1f7d2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "doctor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("doctor_id", "slug", name="uq_blog_categories_doctor_id_slug"),
    )
    op.create_index("ix_blog_categories_doctor_id", "blog_categories", ["doctor_id"])

    # The old free-text category is superseded by the FK below.
    op.drop_column("gallery_posts", "category")
    op.alter_column("gallery_posts", "description", new_column_name="introduction")

    op.add_column("gallery_posts", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("gallery_posts", sa.Column("cover_image", sa.Text(), nullable=True))
    op.add_column(
        "gallery_posts",
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blog_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("gallery_posts", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("gallery_posts", sa.Column("display_date", sa.Date(), nullable=True))
    op.create_index("ix_gallery_posts_category_id", "gallery_posts", ["category_id"])

    op.add_column(
        "doctor_settings", sa.Column("section_label", sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("doctor_settings", "section_label")

    op.drop_index("ix_gallery_posts_category_id", table_name="gallery_posts")
    op.drop_column("gallery_posts", "display_date")
    op.drop_column("gallery_posts", "display_order")
    op.drop_column("gallery_posts", "category_id")
    op.drop_column("gallery_posts", "cover_image")
    op.drop_column("gallery_posts", "body")

    op.alter_column("gallery_posts", "introduction", new_column_name="description")
    op.add_column("gallery_posts", sa.Column("category", sa.String(length=100), nullable=True))

    op.drop_index("ix_blog_categories_doctor_id", table_name="blog_categories")
    op.drop_table("blog_categories")
