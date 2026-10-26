"""
Parser for group management responses.
Scans raw bytes for Jetra User and Channel constructors.
"""
import struct

USER_CTOR = 0xB1B8CC83
CHANNEL_CTOR = 0xD49F34C6

def parse_users(data):
    """Scan data for User ctors and extract user_id."""
    users = []
    pos = 0
    needle = struct.pack("<I", USER_CTOR)
    
    while True:
        pos = data.find(needle, pos)
        if pos == -1:
            break
        try:
            # From high_level.py: ctor(4) + flags(8) + user_id(8)
            offset = pos + 4 + 8
            user_id = struct.unpack("<q", data[offset:offset+8])[0]
            users.append({"user_id": user_id})
        except Exception:
            pass
        pos += 4
    
    # Remove duplicates
    seen = set()
    unique_users = []
    for u in users:
        if u['user_id'] not in seen:
            seen.add(u['user_id'])
            unique_users.append(u)
    return unique_users

def parse_channels(data):
    """Scan data for Channel ctors and extract channel_id, title."""
    channels = []
    pos = 0
    needle = struct.pack("<I", CHANNEL_CTOR)
    
    while True:
        pos = data.find(needle, pos)
        if pos == -1:
            break
        try:
            # From high_level.py: ctor(4) + flags(8) + channel_id(8) + access_hash(8) + title
            offset = pos + 4 + 8
            channel_id = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 16 # skip access_hash
            title_len = data[offset]
            offset += 1
            title = data[offset:offset+title_len].decode('utf-8', errors='ignore')
            
            channels.append({
                "channel_id": channel_id,
                "title": title
            })
        except Exception:
            pass
        pos += 4
        
    # Remove duplicates
    seen = set()
    unique_channels = []
    for c in channels:
        if c['channel_id'] not in seen:
            seen.add(c['channel_id'])
            unique_channels.append(c)
    return unique_channels
