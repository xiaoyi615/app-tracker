from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class AppRecord(db.Model):
    __tablename__ = 'app_records'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    app_name = db.Column(db.String(200), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False, default='open')  # open / close
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'app_name': self.app_name,
            'action': self.action,
            'timestamp': self.timestamp.isoformat(),
            'created_at': self.created_at.isoformat()
        }
    
    def __repr__(self):
        return f'<AppRecord {self.app_name} {self.action} @ {self.timestamp}>'
