"""
Automatic test for pin/unpin feature.
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.pin.pin_client import PinJetraClient

async def main():
    print("=" * 60)
    print("Pin Message Test (Sandbox)")
    print("=" * 60)

    client = PinJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    groups = await client.get_groups()
    if not groups:
        print("No groups available.")
        await client.stop()
        return

    target = groups[0]
    peer_id = target['peer_id']
    print(f"Target group: {target['title']} (peer_id={peer_id})")

    print("\n1. Sending a message to pin...")
    try:
        msg_id = await client.send_message(peer_id, "PIN-TEST: This is a pinned message!", peer_type="group")
        print(f"   Sent! msg_id={msg_id}")
    except Exception as e:
        print(f"   Failed to send: {e}")
        await client.stop()
        return

    await asyncio.sleep(2)

    print(f"\n2. Pinning msg_id={msg_id}...")
    try:
        await client.pin_message(peer_id, msg_id, peer_type="group", unpin=False)
        print("   Pinned successfully! Go check the group in the official app.")
    except Exception as e:
        print(f"   Failed to pin: {e}")
        await client.stop()
        return

    await asyncio.sleep(3)

    print(f"\n3. Unpinning msg_id={msg_id}...")
    try:
        await client.pin_message(peer_id, msg_id, peer_type="group", unpin=True)
        print("   Unpinned successfully! Check the group again.")
    except Exception as e:
        print(f"   Failed to unpin: {e}")

    await client.stop()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
