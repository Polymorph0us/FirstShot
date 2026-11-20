"""initial_schema

Revision ID: f9c34cc4caf9
Revises:
Create Date: 2026-11-19 21:57:14.873953

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9c34cc4caf9"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "booking_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("preference_id", sa.Integer(), nullable=True),
        sa.Column("target_event_id", sa.String(length=100), nullable=True),
        sa.Column("session_id", sa.String(length=50), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=True),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("response_message", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(), nullable=True),
        sa.Column("execution_duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "booking_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_title", sa.String(length=255), nullable=False),
        sa.Column("target_date", sa.String(length=50), nullable=True),
        sa.Column("preferred_room", sa.String(length=100), nullable=True),
        sa.Column("preferred_start_time", sa.String(length=20), nullable=True),
        sa.Column("preferred_end_time", sa.String(length=20), nullable=True),
        sa.Column("alternative_times", sa.String(length=255), nullable=True),
        sa.Column("accept_waitlist", sa.Boolean(), nullable=True),
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=True),
        sa.Column("max_bookings", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("target_event_id", sa.String(length=100), nullable=True),
        sa.Column("current_status", sa.String(length=50), nullable=True),
        sa.Column("capacity", sa.String(length=50), nullable=True),
        sa.Column("waitlist_capacity", sa.String(length=50), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("booking_mode", sa.String(length=20), nullable=True),
        sa.Column("is_armed", sa.Boolean(), nullable=True),
        sa.Column("armed_at", sa.DateTime(), nullable=True),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("user_permitted_automation", sa.Boolean(), nullable=True),
        sa.Column("execution_status", sa.String(length=50), nullable=True),
        sa.Column("retry_window_seconds", sa.Integer(), nullable=True),
        sa.Column("last_preflight_status", sa.String(length=50), nullable=True),
        sa.Column("last_preflight_details", sa.Text(), nullable=True),
        sa.Column("last_preflight_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "discovered_events",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("date", sa.String(length=50), nullable=False),
        sa.Column("start_time", sa.String(length=20), nullable=False),
        sa.Column("end_time", sa.String(length=20), nullable=False),
        sa.Column("venue", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("booking_status", sa.String(length=50), nullable=False),
        sa.Column("booking_window_start", sa.String(length=100), nullable=True),
        sa.Column("booking_window_end", sa.String(length=100), nullable=True),
        sa.Column("cancellation_deadline", sa.String(length=100), nullable=True),
        sa.Column("capacity", sa.String(length=50), nullable=True),
        sa.Column("waitlist_capacity", sa.String(length=50), nullable=True),
        sa.Column("reward_points", sa.Integer(), nullable=True),
        sa.Column("attendance_cluster", sa.String(length=255), nullable=True),
        sa.Column("can_book", sa.Boolean(), nullable=True),
        sa.Column("has_waitlist", sa.Boolean(), nullable=True),
        sa.Column("purpose_required", sa.Boolean(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "monitoring_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("target_event_id", sa.String(length=100), nullable=True),
        sa.Column("filter_term", sa.String(length=50), nullable=True),
        sa.Column("filter_slot_name", sa.String(length=100), nullable=True),
        sa.Column("filter_date_from", sa.String(length=50), nullable=True),
        sa.Column("filter_date_to", sa.String(length=50), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status_from", sa.String(length=50), nullable=True),
        sa.Column("status_to", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("notification_logs")
    op.drop_table("monitoring_jobs")
    op.drop_table("discovered_events")
    op.drop_table("booking_preferences")
    op.drop_table("booking_attempts")
