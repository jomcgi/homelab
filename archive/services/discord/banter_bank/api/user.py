from services.discord.banter_bank.models import User


async def insert_user(user: User) -> User:
    """Insert a user into the database"""
    user.save()
    return user
