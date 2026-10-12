"""Fresh Phase 3 hospital workflows through activated Phase 4 gateway policies."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_phase3
Base=verify_phase3.Actor
class PacedActor(Base):
    def login(self):
        time.sleep(2);super().login();time.sleep(2)
    def call(self,*args,**kwargs):
        time.sleep(.3);return super().call(*args,**kwargs)
verify_phase3.Actor=PacedActor
if __name__=='__main__':verify_phase3.verify('http://127.0.0.1:8080',Path('artifacts/phase4/hospital-regression-fixture.json'))
