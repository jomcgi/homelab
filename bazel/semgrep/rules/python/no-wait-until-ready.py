# Tests for no-wait-until-ready rule.
import asyncio


# ruleid: no-wait-until-ready
async def bad_background_task_wait(bot):
    await bot.wait_until_ready()
    print("bot is ready")


# ruleid: no-wait-until-ready
async def bad_prefixed_client_wait(client):
    await client.wait_until_ready()
    print("client is ready")


# ok: no-wait-until-ready
async def ok_polling_loop(bot):
    while not bot.is_ready():
        await asyncio.sleep(2)
    print("bot is ready")


# ok: no-wait-until-ready
async def ok_on_ready_event(bot):
    # Using the on_ready event listener is also safe
    pass
