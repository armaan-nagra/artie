import heapq
import threading
import time


class FrankensteinQueue:
    def __init__(self, mode="fifo", use_priority=False):
        if mode not in ("fifo", "lifo"):
            raise ValueError(f"mode must be 'fifo' or 'lifo', got {mode!r}")
        self.use_priority = use_priority
        self.delay_heap = []
        self.ready_heap = []
        self.sequence = 0
        self.mode = mode
        # One lock guards both heaps and the sequence counter; pop moves
        # items between heaps, so they can't be locked independently.
        self._lock = threading.Lock()

    def _key(self, priority, seq):
        priority_key = -priority if self.use_priority else 0
        seq_key = seq if self.mode == "fifo" else -seq
        return (priority_key, seq_key)

    def push(self, item, priority=0, delay=0):
        with self._lock:
            self.sequence += 1
            if delay > 0:
                available_at = time.monotonic() + delay
                heapq.heappush(self.delay_heap, (available_at, self.sequence, item, priority))
            else:
                pk, sk = self._key(priority, self.sequence)
                heapq.heappush(self.ready_heap, (pk, sk, item))

    def _promote_ready(self):
        while self.delay_heap and self.delay_heap[0][0] <= time.monotonic():
            _, seq, item, priority = heapq.heappop(self.delay_heap)
            pk, sk = self._key(priority, seq)
            heapq.heappush(self.ready_heap, (pk, sk, item))

    def pop(self):
        with self._lock:
            self._promote_ready()
            if self.ready_heap:
                _, _, item = heapq.heappop(self.ready_heap)
                return item
            return Non    def next_available_at(self):
        with self._lock:
            self._promote_ready()
            if self.delay_heap:
                return self.delay_heap[0][0]
            return None


