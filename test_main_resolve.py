import asyncio
from jetrauserapi import JetraClient
from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    # Ask for username
    username = input("Enter username to resolve (e.g. UserBot): ").strip()
    
    print(f"Resolving @{username}...")
    result = await client.resolve_username(username)
    
    if result:
        print(f"Found: {result}")
    else:
        print("Not found in your contacts.")
        
    await client.stop()

asyncio.run(main())
