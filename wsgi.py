"""
WSGI entry point for Vercel deployment
"""
from app import app

# For Vercel
if __name__ == '__main__':
    app.run()
