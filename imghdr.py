# Fake imghdr module for compatibility in Python 3.13+
# This prevents ModuleNotFoundError for libraries expecting imghdr.

def what(file, h=None):
    """
    Fake detection: just return 'jpeg' always for Telegram photos
    """
    return 'jpeg'