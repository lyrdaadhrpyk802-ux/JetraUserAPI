"""
ReplyJetraClient - JetraClient with reply-to-message support.

This is a SANDBOX subclass. It does NOT modify the main library.
"""
import struct
import random
import datetime

from jetrauserapi.high_level import (
    JetraClient as _BaseJetraClient,
    INPUT_PEER_USER,
    INPUT_PEER_CHANNEL,
    SEND_MESSAGE_ID,
    RPC_ERROR,
)
from jetrauserapi.message import Message
from jetrauserapi.client import wrap_init_connection


# Constructor ID for InputReplyToMessage (confirmed working on Jetra layer 228)
INPUT_REPLY_TO_MESSAGE_ID = 0x3BD4B7C2


class ReplyJetraClient(_BaseJetraClient):
    """
    JetraClient with reply support.

    Usage:
        client = ReplyJetraClient(session_file, db_file)
        await client.start()
        await client.send_message(peer_id, "text", reply_to=message_obj)
        # or:
        await client.send_message(peer_id, "text", reply_to=12345)
    """

    async def send_message(self, peer_id, text, peer_type=None, reply_to=None):
        """
        Send a text message, optionally as a reply.

        Args:
            peer_id:    Target peer id (int).
            text:       Message body.
            peer_type:  'user' | 'group' | None (auto-detect).
            reply_to:   Message | int (msg_id) | None.

        Returns:
            True on success. Raises Exception on RPC error.
        """
        if not self._is_running:
            raise Exception("Client is not started. Call await client.start() first.")

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
                raise TypeError(
                    "reply_to must be Message or int, got " +
                    type(reply_to).__name__
                )
            if reply_to_msg_id == 0:
                raise ValueError("reply_to msg_id is 0 (invalid)")

        # Build flags and optional InputReplyToMessage
        flags = 0
        reply_bytes = b""
        if reply_to_msg_id is not None:
            flags |= 0x1

            # InputReplyToMessage#3bd4b7c2 flags:# reply_to_msg_id:int
            inner_flags = 0
            reply_bytes = (
                struct.pack("<I", INPUT_REPLY_TO_MESSAGE_ID) +
                struct.pack("<I", inner_flags) +
                struct.pack("<i", reply_to_msg_id)
            )

        # Serialize sendMessage
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

        # Save locally
        sent_msg = Message(
            msg_id=0,
            from_id=self.session.user_id,
            peer_id=peer_id,
            peer_type=peer_type,
            date=int(datetime.datetime.now().timestamp()),
            text=text,
        )
        self.db.save_message(sent_msg)
        return True
