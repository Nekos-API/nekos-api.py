from datetime import datetime

import time
import typing


# The time the last request was made. Since the API only allows 2 requests per
# second, this variable is used to prevent 429 status codes.
last_request: typing.Optional[datetime] = None


def prevent_ratelimit(func: typing.Optional[typing.Callable] = None):
    """
    Waits until a new request can be made without getting a 429 status code.
    """

    def sleep():
        global last_request
        if last_request:
            time.sleep(0.5 - (datetime.now() - last_request).total_seconds())
            last_request = datetime.now()

    if func is not None:
        def wrapper(*args, **kwargs):
            sleep()
            return func(*args, **kwargs)

        return wrapper
    
    sleep()
