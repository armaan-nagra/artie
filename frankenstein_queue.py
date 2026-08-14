import heapq
import json
import os
import threading
import time


class FrankensteinQueue:
    def __init__(self, mode="fifo", use_priority=False, log_path=None):
        if mode not in ("fifo", "lifo"):
            raise ValueError(f"mode must be 'fifo' or 'lifo', got {mode!r}")
        self.use_priority = use_priority
        self.mode = mode
        self.delay_heap = []  # (available_at, seq, item, priority)
        self.ready_heap = []  # (priority_key, seq_key, seq, item, priority)
        self.sequence = 0
        # One lock guards the heaps, the sequence counter and the log: pop
        # moves items between heaps, and log order must match memory order.
        self._lock = threading.Lock()
        self.log_path = log_path
        self._log_file = None
        if log_path is not None:
            self._replay()
            self._log_file = open(log_path, "a", encoding="utf-8")

    def _key(self, priority, seq):
        priority_key = -priority if self.use_priority else 0
        seq_key = seq if self.mode == "fifo" else -seq
        return (priority_key, seq_key)

    def _append_log(self, record):
        if self._log_file is None:
            return
        self._log_file.write(json.dumps(record) + "\n")
        self._log_file.flush()
        os.fsync(self._log_file.fileno())

    def _replay(self):
        if not os.path.exists(self.log_path):
            return
        pending = {}
        good_bytes = 0
        with open(self.log_path, "rb") as f:
            for line in f:
                # A complete write always ends in a newline; a torn line from
                # a crash mid-write doesn't (or won't parse). Stop there.
                if not line.endswith(b"\n"):
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    break
                good_bytes += len(line)
                if record["op"] == "push":
                    pending[record["seq"]] = record
                    self.sequence = max(self.sequence, record["seq"])
                elif record["op"] == "pop":
                    pending.pop(record["seq"], None)
        # Truncate the torn tail, otherwise the next append glues onto it,
        # producing an unparseable line that loses every record after it
        # on the following restart.
        if good_bytes < os.path.getsize(self.log_path):
            with open(self.log_path, "r+b") as f:
                f.truncate(good_bytes)
        now = time.time()
        for seq, record in pending.items():
            item, priority = record["item"], record["priority"]
            available_at = record["available_at"]
            if available_at is not None and available_at > now:
                heapq.heappush(self.delay_heap, (available_at, seq, item, priority))
            else:
                pk, sk = self._key(priority, seq)
                heapq.heappush(self.ready_heap, (pk, sk, seq, item, priority))

    def push(self, item, priority=0, delay=0):
        with self._lock:
            self.sequence += 1
            seq = self.sequence
            available_at = time.time() + delay if delay > 0 else None
            self._append_log({"op": "push", "seq": seq, "item": item,
                              "priority": priority, "available_at": available_at})
            if available_at is not None:
                heapq.heappush(self.delay_heap, (available_at, seq, item, priority))
            else:
                pk, sk = self._key(priority, seq)
                heapq.heappush(self.ready_heap, (pk, sk, seq, item, priority))
            return seq

    def _promote_ready(self):
        while self.delay_heap and self.delay_heap[0][0] <= time.time():
            _, seq, item, priority = heapq.heappop(self.delay_heap)
            pk, sk = self._key(priority, seq)
            heapq.heappush(self.ready_heap, (pk, sk, seq, item, priority))

    def pop(self):
        with self._lock:
            self._promote_ready()
            if self.ready_heap:
                _, _, seq, item, _ = heapq.heappop(self.ready_heap)
                self._append_log({"op": "pop", "seq": seq})
                return item
            return None

    def next_available_at(self):
        with self._lock:
            self._promote_ready()
            if self.delay_heap:
                return self.delay_heap[0][0]
            return None

    def size(self):
        with self._lock:
            self._promote_ready()
            return len(self.ready_heap) + len(self.delay_heap)

    def compact(self):
        """Rewrite the log to contain only still-pending messages.

        The log otherwise grows forever (pops are appended, never erased).
        Writes to a temp file and atomically swaps it in, so a crash
        mid-compaction leaves the old log intact.
        """
        if self.log_path is None:
            return
        with self._lock:
            if self._log_file is None:  # already closed
                return
            records = [
                {"op": "push", "seq": seq, "item": item, "priority": priority,
                 "available_at": available_at}
                for available_at, seq, item, priority in self.delay_heap
            ]
            records += [
                {"op": "push", "seq": seq, "item": item,
                 "priority": priority, "available_at": None}
                for _, _, seq, item, priority in self.ready_heap
            ]
            records.sort(key=lambda r: r["seq"])
            tmp_path = self.log_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as tmp:
                for record in records:
                    tmp.write(json.dumps(record) + "\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            self._log_file.close()
            os.replace(tmp_path, self.log_path)
            self._log_file = open(self.log_path, "a", encoding="utf-8")

    def close(self):
        with self._lock:
            if self._log_file is not None:
                self._log_file.close()
                self._log_file = None
