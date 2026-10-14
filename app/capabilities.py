"""
A user's capabilities: what they can actually do, derived from live
state rather than the static `role` column. See CLAUDE.md's Roles
convention — `role` is a signup-time default only, never an access
gate or a filter; `capabilities` is what a caller (or a client
deciding what UI to show) should actually look at.

Every non-admin user always has "customer"; "provider" is added once
they have a ProviderProfile row. Admin is a separate, exclusive
account type (see app/db_triggers.py and app/routers/providers.py) —
an admin account has neither capability.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole


async def get_capabilities(db: AsyncSession, user: User) -> list[str]:
    if user.role == UserRole.admin:
        return []
    result = await db.execute(select(ProviderProfile.id).where(ProviderProfile.user_id == user.id))
    has_provider_profile = result.scalar_one_or_none() is not None
    return ["customer", "provider"] if has_provider_profile else ["customer"]
