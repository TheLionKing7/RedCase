"""Auth + tenant/user context resolution.

Full implementation lands with Task 1.2/1.4. The contract is fixed now
(HANDOFF.md §2.2, §2.5): every request resolves a tenant + user, and every
DB connection runs with `SET LOCAL app.tenant_id / app.user_ref /
app.user_clearance` so RLS policies — not Python — enforce isolation.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_ref: str
    user_clearance: str
    db: Any  # AsyncSession with RLS GUCs set (wired in Task 1.2)
