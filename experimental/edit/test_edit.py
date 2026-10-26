"""
Fully automatic test for edit feature.

1. Picks the first group dialog automatically.
2. Sends a message.
3. Waits 2 seconds.
4. Edits it.
5. Waits 2 seconds.
6. Edits it again.
7. Prints result.

No user interaction except choosing dialog (or auto-pick first group).

Usage:
    cd /storage/emulated/0/JetraUserAPI
    python experimental/edit/test_edit.py
"""
import sys
import os
import asyncio
import datetime

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.edit.edit_client import EditJetraClient


async def auto_test(client):
    print("\n--- AUTO TEST ---")

    groups = await client.get_groups()
    if not groups:
        print("No groups available.")
        return

    target = groups[0]
    peer_id = target['peer_id']
    peer_type = target['peer_type']
    print("Target: " + str(target['title']) +
          " (peer_id=" + str(peer_id) + ")")

    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    text1 = "AUTO-EDIT test 1 [" + stamp + "]"
    text2 = "AUTO-EDIT test 2 edited [" + stamp + "]"
    text3 = "AUTO-EDIT test 3 re-edited [" + stamp + "]"

    print("\n[1] Sending original: " + repr(text1))
    try:
        msg_id = await client.send_message(
            peer_id, text1, peer_type=peer_type
        )
    except Exception as e:
        print("    FAILED to send: " + str(e))
        return

    if not msg_id or msg_id == 0:
        print("    msg_id is 0, cannot proceed with edit.")
        return

    print("    Got msg_id=" + str(msg_id))
    await asyncio.sleep(2)

    print("\n[2] Editing to: " + repr(text2))
    try:
        await client.edit_message(
            peer_id, msg_id, text2, peer_type=peer_type
        )
        print("    Edit #1 OK")
    except Exception as e:
        print("    FAILED edit #1: " + str(e))
        return

    await asyncio.sleep(2)

    print("\n[3] Re-editing to: " + repr(text3))
    try:
        await client.edit_message(
            peer_id, msg_id, text3, peer_type=peer_type
        )
        print("    Edit #2 OK")
    except Exception as e:
        print("    FAILED edit #2: " + str(e))
        return

    print("\nAll steps done. Check the group in the official app.")
    print("You should see the message text = " + repr(text3))


async def main():
    print("=" * 60)
    print("Edit Feature Test (Sandbox, automatic)")
    print("=" * 60)

    client = EditJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    print("\nStarting client...")
    await client.start()
    print("Client ready.\n")

    await auto_test(client)

    print("\nStopping client...")
    await client.stop()
    print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
