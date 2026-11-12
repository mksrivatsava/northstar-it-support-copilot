"""Small per-process admission limits for the single-instance public demo."""
from collections import deque
import math
from threading import Lock
import time


class DemoLimits:
    def __init__(self, per_client, global_limit, max_inflight, clock=time.monotonic):
        self.per_client, self.global_limit, self.max_inflight = per_client, global_limit, max_inflight
        self.clock, self.lock = clock, Lock()
        self.clients, self.requests, self.active = {}, deque(), 0

    def begin(self, client):
        with self.lock:
            now = self.clock()
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            for key in list(self.clients):
                queue = self.clients[key]
                while queue and now - queue[0] >= 60:
                    queue.popleft()
                if not queue:
                    del self.clients[key]
            queue = self.clients.get(client, deque())
            if len(queue) >= self.per_client or len(self.requests) >= self.global_limit:
                oldest = queue[0] if len(queue) >= self.per_client else self.requests[0]
                return 429, max(1, math.ceil(60 - (now - oldest)))
            if self.active >= self.max_inflight:
                return 503, 5
            if client not in self.clients and len(self.clients) >= 1024:
                return 429, 60
            self.clients[client] = queue
            queue.append(now)
            self.requests.append(now)
            self.active += 1
            return None

    def finish(self):
        with self.lock:
            self.active = max(0, self.active - 1)
