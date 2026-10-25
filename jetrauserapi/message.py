import datetime


class Message:
    """
    Represents a message in Jetra.
    
    Attributes:
        id (int): Message ID
        from_id (int): Sender's user ID
        peer_id (int): Chat/Group/Channel ID
        peer_type (str): 'user', 'group', or 'channel'
        date (int): Unix timestamp
        text (str): Message text
    """
    
    def __init__(self, msg_id, from_id, peer_id, peer_type, date, text):
        self.id = msg_id
        self.from_id = from_id
        self.peer_id = peer_id
        self.peer_type = peer_type
        self.date = date
        self.text = text
    
    @property
    def is_private(self):
        return self.peer_type == 'user'
    
    @property
    def is_group(self):
        return self.peer_type == 'group'
    
    @property
    def date_str(self):
        try:
            return datetime.datetime.fromtimestamp(self.date).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return str(self.date)
    
    def to_dict(self):
        return {
            'id': self.id,
            'from_id': self.from_id,
            'peer_id': self.peer_id,
            'peer_type': self.peer_type,
            'date': self.date,
            'text': self.text,
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            msg_id=data['id'],
            from_id=data['from_id'],
            peer_id=data['peer_id'],
            peer_type=data['peer_type'],
            date=data['date'],
            text=data['text'],
        )
    
    def __repr__(self):
        return f"<Message id={self.id} from={self.from_id} peer={self.peer_id} ({self.peer_type}) text='{self.text[:30]}'>"
