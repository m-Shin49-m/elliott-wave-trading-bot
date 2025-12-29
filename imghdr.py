# Minimal shim for Python 3.13 compatibility for libraries expecting stdlib imghdr
# Only the 'what' function is required by python-telegram-bot for basic usage.
# This stub returns None for any input, which is sufficient for text messages.

def what(file, h=None):
    return None



