"""Create private tenant-scoped buckets for firm branding and restricted KYC."""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both buckets are private. All reads/writes are proxied through the API,
    # which authenticates a firm-admin JWT and enforces tenant-prefixed keys.
    # In particular, no authenticated/anon storage policy can fetch KYC bytes.
    op.execute(
        """
        DO $do$
        BEGIN
          IF to_regclass('storage.buckets') IS NOT NULL THEN
            INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
            VALUES
              ('firm-kyc', 'firm-kyc', false, 10485760,
               ARRAY['application/pdf','image/jpeg','image/png']),
              ('firm-brand', 'firm-brand', false, 10485760,
               ARRAY['application/pdf','image/jpeg','image/png'])
            ON CONFLICT (id) DO UPDATE SET
              public = false,
              file_size_limit = EXCLUDED.file_size_limit,
              allowed_mime_types = EXCLUDED.allowed_mime_types;
          END IF;
        END $do$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $do$
        BEGIN
          IF to_regclass('storage.buckets') IS NOT NULL THEN
            DELETE FROM storage.buckets WHERE id IN ('firm-kyc','firm-brand');
          END IF;
        END $do$
        """
    )