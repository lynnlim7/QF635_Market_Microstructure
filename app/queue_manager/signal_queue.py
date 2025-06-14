from collections import deque
from typing import Any
import threading

class SignalQueue:
    def __init__(self):
        self._queue = deque()
        self._lock = threading.Lock()
        self._sequence = 0  # Sequence counter
    
    def push(self, signal: Any):
        """Add signal to the queue with a sequence number."""
        with self._lock:
            self._sequence += 1
            self._queue.append((self._sequence, signal))

    def pop(self):
        """Pop the oldest signal from the queue."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def peek(self):
        """Peek at the next signal without removing it."""
        with self._lock:
            if self._queue:
                return self._queue[0]
            return None

    def size(self) -> int:
        """Return number of signals in the queue."""
        with self._lock:
            return len(self._queue)

    def clear(self):
        """Clear all signals in the queue."""
        with self._lock:
            self._queue.clear()
            self._sequence = 0

    def is_empty(self):
        with self._lock:
            return len(self._queue) == 0
