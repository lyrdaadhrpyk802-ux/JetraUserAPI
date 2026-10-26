import asyncio
from jetrauserapi import JetraClient, JetraError, JetraAuthError
from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

async def main():
    print("Testing Context Manager & Exceptions...\n")
    
    # Test 1: Context Manager (async with)
    try:
        async with JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE) as client:
            print("Successfully connected using async with!")
            
            # Test 2: RPC Error catching (trying a blocked method)
            try:
                print("\nTrying a blocked method (editMessage) to test exceptions...")
                # We manually trigger an RPC error to see if our custom class works
                import struct
                from jetrauserapi.client import wrap_init_connection
                body = struct.pack("<I", 0x5C41B52A) + struct.pack("<I", 0)
                await client.client.send_request(wrap_init_connection(body))
            except JetraError as e:
                print(f"Caught a JetraError as expected: {e}")
            except Exception as e:
                print(f"Caught general exception: {e}")
                
    except JetraAuthError as e:
        print(f"Auth error: {e}")
    except JetraError as e:
        print(f"Jetra error: {e}")
        
    print("\nClient automatically stopped when exiting 'async with' block!")

if __name__ == "__main__":
    asyncio.run(main())
