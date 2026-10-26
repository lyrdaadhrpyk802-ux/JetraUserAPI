import asyncio
from jetrauserapi import JetraClient
from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    users = await client.get_users()
    print(f"\nLoaded {len(users)} users. First 10:")
    for u in users[:10]:
        print(f"  - {u['title']} (ID: {u['peer_id']})")

    await client.stop()

asyncio.run(main())
