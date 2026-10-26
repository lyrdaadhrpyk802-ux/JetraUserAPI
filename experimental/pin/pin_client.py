"""
PinJetraClient - JetraClient with pin/unpin message support.
"""
import struct

from jetrauserapi.high_level import (
    JetraClient as BaseJetraClient,
    INPUT_PEER_USER,
    INPUT_PEER_CHANNEL,
    RPC_ERROR
)
from jetrauserapi.client import wrap_init_connection

# Candidate constructor IDs for messages.updatePinnedMessage
UPDATE_PINNED_MESSAGE_IDS = [
    0x0D5A1CB5,  # Standard Telegram
    0x5A56D5D4,  # Older variant
    0x8DE9A1A1,  # Guess near sendMessage
]


class PinJetraClient(BaseJetraClient):
    
    async def pin_message(self, peer_id, msg_id, peer_type=None, unpin=False):
        """
        Pin or unpin a message in a chat.
        
        Args:
            peer_id: Target peer id.
            msg_id: Message id to pin/unpin.
            peer_type: 'user' or 'group' (auto-detected).
            unpin: If True, unpins the message instead of pinning.
        """
        if not self._is_running:
            raise Exception("Client not started.")

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

        # flags: bit 1 (0x2) = unpin
        flags = 0x2 if unpin else 0x0

        last_exception = None
        for ctor_id in UPDATE_PINNED_MESSAGE_IDS:
            try:
                # messages.updatePinnedMessage#<ctor> flags:# peer:InputPeer id:int
                body = (
                    struct.pack("<I", ctor_id) +
                    struct.pack("<I", flags) +
                    input_peer +
                    struct.pack("<i", msg_id)
                )
                
                result = await self.client.send_request(wrap_init_connection(body))
                if not result:
                    raise Exception("No response")
                    
                result = self._unwrap_gzip(result)
                resp_ctor = struct.unpack("<I", result[:4])[0]
                
                if resp_ctor == RPC_ERROR:
                    err = self._parse_rpc_error(result)
                    raise Exception(f"Server error: {err}")
                
                print(f"[SUCCESS] pinMessage worked with ctor {hex(ctor_id)} (unpin={unpin})")
                return True
                
            except Exception as e:
                last_exception = e
                msg = str(e)
                if "NOT_IMPLEMENTED" in msg or "METHOD_INVALID" in msg or "INPUT_REQUEST_INVALID" in msg:
                    print(f"[INFO] pinMessage {hex(ctor_id)} -> {msg[:40]} (trying next...)")
                    continue
                else:
                    raise
                    
        raise Exception(f"All pinMessage attempts failed. Last error: {last_exception}")
