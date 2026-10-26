import asyncio
from jetrauserapi import JetraClient
from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    @client.on_message
    async def on_message(msg):
        print(f"\n[INCOMING] peer={msg.peer_id}")
        print(f"Text: {msg.text}")
        if msg.entities:
            print("Formatting detected:")
            for e in msg.entities:
                print(f"  - {e}")
        else:
            print("No formatting detected (plain text).")

    print("Listening for messages...")
    print("Send a formatted message (bold, italic, link) from another account to test.")
    
    async with client:
        try:
            await asyncio.sleep(600) # Listen for 10 minutes
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    asyncio.run(main())
