from db import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Table, Column, Integer, ForeignKey


class Tab(db.Model):
    __tablename__ = "tabs"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # difficulty: 1 (very easy) .. 5 (very hard)
    difficulty = db.Column(db.Integer, default=3, nullable=False)
    # song speed in beats per minute (BPM) - optional
    speed_bpm = db.Column(db.Integer, default=120, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user = db.relationship('User', backref=db.backref('tabs', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Association table for user favorites (many-to-many)
favorites_table = Table(
    'favorites',
    db.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('tab_id', Integer, ForeignKey('tabs.id', ondelete='CASCADE'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


# Association table for followers (self-referential many-to-many)
followers_table = Table(
    'followers',
    db.metadata,
    Column('follower_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('followed_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar_filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationship to the tabs that this user favorited
    favorites = db.relationship('Tab', secondary=favorites_table, backref=db.backref('favorited_by', lazy='dynamic'), lazy='dynamic')

    # followers / following (self-referential many-to-many)
    # - followers: users who follow this user
    # - following: users that this user follows
    followers = db.relationship(
        'User',
        secondary=followers_table,
        primaryjoin=(followers_table.c.followed_id == id),
        secondaryjoin=(followers_table.c.follower_id == id),
        backref=db.backref('following', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
