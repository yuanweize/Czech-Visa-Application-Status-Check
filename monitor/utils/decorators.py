import functools
import threading
import time
from typing import Callable, Any

def thread_safe(lock_attr: str = '_lock'):
    """
    Decorator to make a method thread-safe using a specified lock attribute.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            lock = getattr(self, lock_attr)
            with lock:
                return func(self, *args, **kwargs)
        return wrapper
    return decorator

def synchronized(func: Callable):
    """
    Simple decorator for methods that use 'self._lock'.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)
    return wrapper

def log_execution_time(logger_func: Callable = print):
    """
    Decorator to log the execution time of a function.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger_func(f"Execution of {func.__name__} took {duration:.4f}s")
            return result
        return wrapper
    return decorator
