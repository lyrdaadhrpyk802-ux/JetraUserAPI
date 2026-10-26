"""
Parser for messages.sendMessage response.

The response is Updates (0x74AE4240) containing a vector of updates,
one of which contains a Jetra Message (0x7600B9D3). We search for the
Message ctor inside the bytes and parse it.

Also handles the case where the response is already a bare Message.
"""
import struct


MSG_CTOR_JETRA = 0x7600B9D3
SERVICE_MSG_CTOR_JETRA = 0x7A800E0A
PEER_USER = 0x59511722
PEER_CHANNEL = 0xA2A5371E

UPDATES_CTOR = 0x74AE4240
UPDATE_NEW_MESSAGE = 0x1F2B0AFD
UPDATE_NEW_CHANNEL_MESSAGE = 0x62BA04D9


def _parse_message_at(data, offset):
    """Parse a Message ctor starting at offset. Returns dict or None."""
    if offset + 4 > len(data):
        return None

    ctor = struct.unpack("<I", data[offset:offset + 4])[0]
    if ctor not in (MSG_CTOR_JETRA, SERVICE_MSG_CTOR_JETRA):
        return None

    try:
        pos = offset + 4

        if ctor == SERVICE_MSG_CTOR_JETRA:
            pos += 4
            msg_id = struct.unpack("<i", data[pos:pos + 4])[0]
            pos += 4
        else:
            pos += 4     # flags
            pos += 4     # empty field
            msg_id = struct.unpack("<i", data[pos:pos + 4])[0]
            pos += 4

        from_peer_ctor = struct.unpack("<I", data[pos:pos + 4])[0]
        pos += 4
        from_id = struct.unpack("<q", data[pos:pos + 8])[0]
        pos += 8

        peer_ctor = struct.unpack("<I", data[pos:pos + 4])[0]
        pos += 4
        peer_id = struct.unpack("<q", data[pos:pos + 8])[0]
        pos += 8

        date = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4

        text = ""
        try:
            text_len = data[pos]
            text = data[pos + 1:pos + 1 + text_len].decode(
                'utf-8', errors='ignore'
            )
        except Exception:
            pass

        if peer_ctor == PEER_USER:
            peer_type = 'user'
        elif peer_ctor == PEER_CHANNEL:
            peer_type = 'group'
        else:
            peer_type = 'unknown'

        return {
            'msg_id': msg_id,
            'from_id': from_id,
            'peer_id': peer_id,
            'peer_type': peer_type,
            'date': date,
            'text': text,
            'offset': offset,
        }
    except Exception:
        return None


def parse_sent_message(data):
    """
    Parse messages.sendMessage response and return dict with msg_id.

    Returns None if no Message ctor found.
    """
    if not data or len(data) < 4:
        return None

    # Case 1: response is Updates, search for Message inside
    top_ctor = struct.unpack("<I", data[:4])[0]
    if top_ctor == UPDATES_CTOR:
        needle = struct.pack("<I", MSG_CTOR_JETRA)
        pos = 4
        while True:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            parsed = _parse_message_at(data, pos)
            if parsed:
                return parsed
            pos += 4
        return None

    # Case 2: response is already a Message
    return _parse_message_at(data, 0)
