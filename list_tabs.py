from app import app
from models import Tab

with app.app_context():
    tabs = Tab.query.order_by(Tab.created_at.desc()).limit(10).all()
    for t in tabs:
        print('ID', t.id, 'Title:', t.title)
