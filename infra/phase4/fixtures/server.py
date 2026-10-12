"""Inert reproducible synthetic policy fixtures; no patient/real insurer data."""
from http.server import BaseHTTPRequestHandler,HTTPServer
import json,os
PROVIDER=int(os.environ['PROVIDER_ID'])
REVISION=int(os.environ.get("POLICY_REVISION","1"))
COVERAGE=int(os.environ.get("COVERAGE_BPS","5000"))
if not 1<=REVISION<=9007199254740991 or not 0<=COVERAGE<=10000:raise ValueError("Invalid fixture configuration")
RULE={'policy_code':'DEMO','revision':REVISION,'effective_from':'2026-01-01T00:00:00Z','effective_to':'2027-01-01T00:00:00Z','currency':'INR','coverage_bps':COVERAGE,'deductible_minor':10000,'max_benefit_minor':100000,'covered_charge_codes':['consultation']}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/':body=b'<html><a href="/policy.html">Synthetic policy</a></html>'
        elif self.path=='/policy.html':body=('<html><script type="application/json" data-pulsegrid-insurance-policy>'+json.dumps(RULE,sort_keys=True)+'</script></html>').encode()
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
