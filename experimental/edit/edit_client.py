"""
EditJetraClient - JetraClient with reply and edit-message support.

This is a SANDBOX subclass. It does NOT modify the main library.

Features:
  - send_message with reply support (inherited from ReplyJetraClient)
  - send_message extracts real msg_id from server response and
    saves it to DB with correct id
  - edit_message with brute-force ctor discovery
"""
import struct
import random
import datetime

from experimental.reply.reply_client import ReplyJetraClient
from experimental.edit.send_parser import parse_sent_message
from jetrauserapi.high_level import (
    INPUT_PEER_USER,
    INPUT_PEER_CHANNEL,
    SEND_MESSAGE_ID,
    RPC_ERROR,
)
from jetrauserapi.message import Message
from jetrauserapi.client import wrap_init_connection


# Candidate constructor IDs for messages.editMessage.
# We try them in order until one works on Jetra layer 228.
EDIT_MESSAGE_CANDIDATE_IDS = [
    0x5C41B52A,   # messages.editMessage (standard Telegram)
    0xB0E17C5D,   # messages.editMessage (with quick_reply_shortcut_id)
    0xDFD5DC46,   # messages.editMessage (older variant)
    0xBE5CE37B,   # messages.editMessage (media edit variant)
    0x5442BD53,   # channels.editMessage (old variant)
    0xB15B355E,   # channels.editMessage (newer variant)
    0x81CC0FA0,   # messages.editInlineBotMessage
    0xFEF48F63,   # near sendMessage 0xFEF48F62 (next)
    0xFEF48F61,   # near sendMessage 0xFEF48F62 (prev)
    0xE58F52D3,   # near deleteMessages 0xE58F52D2
    0x84C1FD4F,   # near channels.deleteMessages 0x84C1FD4E
    0xA0F4CB50,   # near getDialogs 0xA0F4CB4F
    0xA0F4CB4E,   # near getDialogs 0xA0F4CB4F
    0xEDD4882B,   # near getState 0xEDD4882A
    0xEDD48829,   # near getState 0xEDD4882A
    0xBE7E8EF2,   # near req_pq 0xBE7E8EF1
    0xBE7E8EF0,   # near req_pq 0xBE7E8EF1
]


class EditJetraClient(ReplyJetraClient):
    """
    JetraClient with reply and edit support.
    """

    async def send_message(self, peer_id, text, peer_type=None, reply_to=None):
        """
        Override parent send_message to extract real msg_id from
        the server response and save it to DB. Otherwise edit
        cannot target our own outgoing messages.
        """
        if not self._is_running:
            raise Exception("Client is not started.")

        # Auto-detect peer type
        if peer_type is None:
            dialogs = self.db.get_dialogs()
            for d in dialogs:
                if d['peer_id'] == peer_id:
                    peer_type = d['peer_type']
                    break
            else:
                peer_type = 'group' if peer_id > 1000 else 'user'

        # Build InputPeer
        if peer_type == 'user':
            input_peer = (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", peer_id) +
                struct.pack("<q", 0)
            )
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d['peer_id'] == peer_id:
                    access_hash = d['access_hash'] or 0
                    break
            input_peer = (
                struct.pack("<I", INPUT_PEER_CHANNEL) +
                struct.pack("<q", peer_id) +
                struct.pack("<q", access_hash)
            )

        # Resolve reply_to
        reply_to_msg_id = None
        if reply_to is not None:
            if isinstance(reply_to, Message):
                reply_to_msg_id = reply_to.id
            elif isinstance(reply_to, int):
                reply_to_msg_id = reply_to
            else:
                raise TypeError("reply_to must be Message or int")
            if reply_to_msg_id == 0:
                raise ValueError("reply_to msg_id is 0 (invalid)")

        flags = 0
        reply_bytes = b""
        if reply_to_msg_id is not None:
            flags |= 0x1
            inner_flags = 0
            reply_bytes = (
                struct.pack("<I", 0x3BD4B7C2) +
                struct.pack("<I", inner_flags) +
                struct.pack("<i", reply_to_msg_id)
            )

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise Exception("No response from sendMessage")

        result = self._unwrap_gzip(result)
        ctor = struct.unpack("<I", result[:4])[0]
        if ctor == RPC_ERROR:
            err = self._parse_rpc_error(result)
            raise Exception("Server error: " + err)

        # Parse real msg_id from response
        parsed = parse_sent_message(result)
        if parsed:
            real_msg_id = parsed['msg_id']
            real_date = parsed['date']
            print("[INFO] sendMessage returned msg_id=" + str(real_msg_id))
        else:
            real_msg_id = 0
            real_date = int(datetime.datetime.now().timestamp())
            print("[WARN] could not parse response, storing msg_id=0")

        sent_msg = Message(
            msg_id=real_msg_id,
            from_id=self.session.user_id,
            peer_id=peer_id,
            peer_type=peer_type,
            date=real_date,
            text=text,
        )
        self.db.save_message(sent_msg)
        return real_msg_id

    async def edit_message(self, peer_id, msg_id, new_text, peer_type=None):
        """
        Edit an existing message.
        Tries all candidate ctor ids until one works.
        """
        if not self._is_running:
            raise Exception("Client is not started.")

        if not msg_id or msg_id == 0:
            raise ValueError("msg_id is 0 (invalid)")

        if peer_type is None:
            dialogs = self.db.get_dialogs()
            for d in dialogs:
                if d['peer_id'] == peer_id:
                    peer_type = d['peer_type']
                    break
            else:
                peer_type = 'group' if peer_id > 1000 else 'user'

        if peer_type == 'user':
            input_peer = (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", peer_id) +
                struct.pack("<q", 0)
            )
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d['peer_id'] == peer_id:
                    access_hash = d['access_hash'] or 0
                    break
            input_peer = (
                struct.pack("<I", INPUT_PEER_CHANNEL) +
                struct.pack("<q", peer_id) +
                struct.pack("<q", access_hash)
            )

        text_bytes = self._tl_string(new_text)

        last_exception = None
        for ctor_id in EDIT_MESSAGE_CANDIDATE_IDS:
            try:
                flags = 0x1
                random_id = random.getrandbits(63)

                body = (
                    struct.pack("<I", ctor_id) +
                    struct.pack("<I", flags) +
                    input_peer +
                    struct.pack("<i", msg_id) +
                    text_bytes +
                    struct.pack("<q", random_id)
                )

                result = await self.client.send_request(
                    wrap_init_connection(body)
                )
                if not result:
                    raise Exception("No response from editMessage")

                result = self._unwrap_gzip(result)
                ctor = struct.unpack("<I", result[:4])[0]

                if ctor == RPC_ERROR:
                    err = self._parse_rpc_error(result)
                    raise Exception("Server error: " + err)

                print("[SUCCESS] editMessage worked with ctor id: " +
                      hex(ctor_id))
                return True

            except Exception as e:
                last_exception = e
                msg = str(e)
                # Continue on structural/not-implemented errors, stop on others
                continue_signals = [
                    "INPUT_REQUEST_INVALID",
                    "CONSTRUCTOR_NOT_FOUND",
                    "METHOD_INVALID",
                    "NOT_IMPLEMENTED",
                    "METHOD_NOT_FOUND",
                ]
                should_continue = any(
                    sig in msg for sig in continue_signals
                )
                if not should_continue:
                    raise
                print("[INFO] ctor " + hex(ctor_id) +
                      " -> " + msg[:60] +
                      " (trying next...)")
                continue

        raise Exception(
            "All editMessage ctor ids failed. Last error: " +
            str(last_exception)
        )
