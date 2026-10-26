import asyncio
from jetrauserapi import JetraClient
from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    groups = await client.get_groups()
    if groups:
        g = groups[0]
        print(f"\nFetching participants for {g['title']}...")
        
        # Calling the newly merged method!
        users = await client.get_participants(g['peer_id'])
        print(f"Found {len(users)} users: {users}")

    await client.stop()

asyncio.run(main())
