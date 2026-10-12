"""Fresh Phase 3 hospital workflows through activated Phase 4 gateway policies."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_phase3
Base=verify_phase3.Actor
class PacedActor(Base):
    def login(self):
        time.sleep(2);super().login();time.sleep(2)
    def call(self,method,path,body=None,etag=None,key=None,codes=(200,)):
        from verify_phase2 import require
        headers={'Authorization':'Bearer '+self.token}
        if etag is not None:headers['If-Match']=etag
        if key is not None:headers['Idempotency-Key']=key
        for attempt in range(10):
            time.sleep(.3)
            response=self.client.request(method,path,json=body,headers=headers)
            if response.status_code!=429:break
            time.sleep(min(10,max(1,int(response.headers.get('Retry-After','1')))))
        return require(response,codes),response.headers.get('etag'),response.status_code
verify_phase3.Actor=PacedActor
if __name__=='__main__':verify_phase3.verify('http://127.0.0.1:8080',Path('artifacts/phase4/hospital-regression-fixture.json'))
