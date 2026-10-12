"""Small deterministic boundary vectors; not a substitute for real-DB tests."""
from dataclasses import dataclass

@dataclass
class DeterministicClock:
    now_ms: int

    def __call__(self):
        return self.now_ms

    async def sleep(self, seconds):
        self.now_ms += 1


def golden_vectors(epoch_ms=1767225600000):
    return [dict(timestamp_ms=epoch_ms+t, worker_id=w, sequence=s,
                 id=(t<<22)|(w<<12)|s)
            for t,w,s in [(1,0,0),(1000,256,4095),((1<<41)-1,1023,4095)]]
