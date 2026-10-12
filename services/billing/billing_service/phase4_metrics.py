"""Bounded process-local component diagnostics; never public gateway metrics."""
from collections import defaultdict
from threading import Lock
from fastapi.responses import PlainTextResponse

class Observer:
    def __init__(self):self.values=defaultdict(float);self.lock=Lock()
    def _key(self,name,labels):
        if not name.startswith('pulsegrid_'):raise ValueError('Invalid metric')
        allowed={'component','owner','policy','outcome','backend','kind','node_id','worker_id','state','class','dependency'}
        if set(labels)-allowed:raise ValueError('Invalid metric labels')
        return name,tuple(sorted((k,str(v)) for k,v in labels.items()))
    def increment(self,name,labels,value=1):
        with self.lock:
            key=self._key(name,labels)
            if key not in self.values and len(self.values)>=2048:return
            self.values[key]+=value
    def observe(self,name,seconds,labels):
        self.increment(name+'_sum',labels,seconds);self.increment(name+'_count',labels)
    def gauge(self,name,value,labels):
        with self.lock:
            key=self._key(name,labels)
            if key not in self.values and len(self.values)>=2048:return
            self.values[key]=value
    def render(self):
        with self.lock:
            return '\n'.join(name+'{'+','.join(k+'="'+v.replace('"','')+'"' for k,v in labels)+'} '+str(value) for (name,labels),value in sorted(self.values.items()))+'\n'

def mount(app):
    app.state.phase4_observer=Observer()
    @app.get('/metrics',include_in_schema=False)
    async def metrics():return PlainTextResponse(app.state.phase4_observer.render())
