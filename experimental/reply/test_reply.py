"""
Interactive test for reply feature.
Runs in SANDBOX, does NOT modify the main library.

Usage:
    cd /storage/emulated/0/JetraUserAPI
    python experimental/reply/test_reply.py
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.reply.reply_client import ReplyJetraClient


async def show_dialogs(client, peer_type=None, limit=20):
    dialogs = await client.get_dialogs(peer_type)
    if not dialogs:
        print("  (no dialogs)")
        return []
    print("\n  #    Type    peer_id          title")
    print("  " + "-" * 60)
    for i, d in enumerate(dialogs[:limit], 1):
        title = (d['title'] or '')[:35]
        print("  {:<4} {:<7} {:<16} {}".format(
            i, d['peer_type'], d['peer_id'], title
        ))
    return dialogs[:limit]


async def test_manual_reply(client):
    print("\n--- Manual Reply ---")

    print("\nAvailable dialogs:")
    dialogs = await show_dialogs(client, limit=20)

    if not dialogs:
        print("No dialogs available.")
        return

    try:
        idx = int(input("\nPick dialog number: ").strip()) - 1
        d = dialogs[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return

    peer_id = d['peer_id']
    peer_type = d['peer_type']

    msgs = client.get_history(peer_id=peer_id, limit=20)
    msgs = [m for m in msgs if m['id'] != 0]

    if msgs:
        print("\nRecent received messages in '" + str(d['title']) + "':")
        print("  #    msg_id       text")
        print("  " + "-" * 60)
        for i, m in enumerate(msgs, 1):
            text = (m['text'] or '')[:40]
            print("  {:<4} {:<12} {}".format(i, m['id'], text))
        use_db = input(
            "\nPick # from DB, or press Enter to enter msg_id manually: "
        ).strip()
        if use_db:
            try:
                reply_to = msgs[int(use_db) - 1]['id']
            except (ValueError, IndexError):
                print("Invalid.")
                return
        else:
            reply_to = int(input("Enter msg_id to reply to: ").strip())
    else:
        print("No received messages in DB for this peer.")
        reply_to = int(input("Enter msg_id to reply to: ").strip())

    text = input("\nReply text: ").strip()
    if not text:
        print("Empty text, aborting.")
        return

    print("\nSending reply to msg_id=" + str(reply_to) +
          " in peer " + str(peer_id) + " (" + peer_type + ")...")
    try:
        await client.send_message(
            peer_id, text, peer_type=peer_type, reply_to=reply_to
        )
        print("Reply sent successfully.")
    except Exception as e:
        print("Failed: " + str(e))


async def test_auto_reply(client):
    print("\n--- Auto-Reply Mode ---")
    print("Every incoming message will be replied with 'Got it: <text>'.")
    print("Press Ctrl+C to stop.\n")

    @client.on_message
    async def on_message(message):
        print("[IN] peer=" + str(message.peer_id) +
              " from=" + str(message.from_id) +
              " msg_id=" + str(message.id) +
              ": " + str(message.text))
        if message.id == 0:
            print("  (skipping, invalid msg_id=0)")
            return
        try:
            await client.send_message(
                message.peer_id,
                "Got it: " + str(message.text),
                reply_to=message,
            )
            print("  [OUT] reply sent -> " + str(message.id))
        except Exception as e:
            print("  [ERR] reply failed: " + str(e))

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping auto-reply...")
        if on_message in client._message_handlers:
            client._message_handlers.remove(on_message)


async def main():
    print("=" * 60)
    print("Reply Feature Test (Sandbox)")
    print("=" * 60)

    client = ReplyJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    print("\nStarting client...")
    await client.start()
    print("Client ready.\n")

    while True:
        print("\n--- Menu ---")
        print("1. Manual reply to specific msg_id")
        print("2. Auto-reply on incoming messages")
        print("3. Show dialogs")
        print("4. Quit")
        choice = input("Choose [1-4]: ").strip()

        if choice == "1":
            await test_manual_reply(client)
        elif choice == "2":
            await test_auto_reply(client)
        elif choice == "3":
            pt = input("Filter (user/group/all): ").strip()
            await show_dialogs(client, None if pt == "all" else pt)
        elif choice == "4":
            break
        else:
            print("Invalid choice.")

    print("\nStopping client...")
    await client.stop()
    print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
