"""Real HTTP authentication journey through Traefik and optionally Vite.

Synthetic accounts and immutable audit history are retained. No tokens are printed.
Run with the backend test environment's httpx installed. No browser claims.
"""
import argparse
import base64
import secrets
import time
import uuid
import httpx


def verify(base_url, origin, expiry=False):
    body = {"email": f"integration-{uuid.uuid4().hex}@example.test",
            "password": secrets.token_urlsafe(32), "display_name": "Synthetic Integration Patient"}
    command = {"Idempotency-Key": str(uuid.uuid4()),
               "X-Anonymous-Command-ID": secrets.token_urlsafe(32)}
    with httpx.Client(base_url=base_url, headers={"Origin": origin}, timeout=10) as c:
        def csrf():
            r = c.get('/api/v1/auth/csrf')
            assert r.status_code == 200
            assert r.json()['header_name'] == 'X-CSRF-Token'
            assert 'HttpOnly' in r.headers['set-cookie']
            return {'X-CSRF-Token': r.json()['csrf_token']}

        assert c.get('/api/v1/patients/me').status_code == 401
        assert c.get('/api/v1/patients/me', headers={'Authorization': 'Bearer invalid'}).status_code == 401
        if base_url != origin:
            assert c.get('/internal/v1/auth/jwks').status_code == 404
            assert c.post('/internal/v1/authorization/check', json={}).status_code == 404
        assert c.post('/api/v1/auth/register', json=body).status_code == 400
        r = c.post('/api/v1/auth/register', json={**body, 'roles': ['hospital_admin']}, headers=command)
        assert r.status_code == 422
        r = c.post('/api/v1/auth/register', json=body, headers=command)
        assert r.status_code == 201
        profile = r.json()
        assert c.post('/api/v1/auth/register', json=body, headers=command).json() == profile
        assert c.post('/api/v1/auth/register', json=body, headers={
            'Idempotency-Key': str(uuid.uuid4()), 'X-Anonymous-Command-ID': secrets.token_urlsafe(32),
        }).status_code == 409
        assert c.post('/api/v1/auth/login', json=body, headers=csrf()).status_code == 422  # extra fields forbidden
        credentials = {k: body[k] for k in ['email', 'password']}
        assert c.post('/api/v1/auth/login', json=credentials).status_code == 403
        assert c.post('/api/v1/auth/login', json=credentials, headers={'X-CSRF-Token': 'invalid'}).status_code == 403
        headers = csrf()
        assert c.post('/api/v1/auth/login', json=credentials, headers={**headers, 'Origin': 'https://attacker.example'}).status_code == 403
        assert c.get('/api/v1/auth/csrf', headers={'Origin': 'null'}).status_code == 403
        if base_url != origin:  # Vite handles development preflight locally; gateway policy checked directly.
            r = c.options('/api/v1/auth/login', headers={'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type,x-csrf-token,x-anonymous-command-id,idempotency-key'})
            assert r.status_code == 200
            assert r.headers['access-control-allow-origin'] == origin
            assert r.headers['access-control-allow-credentials'] == 'true'
            r = c.options('/api/v1/auth/login', headers={'Origin': 'https://attacker.example',
                'Access-Control-Request-Method': 'POST'})
            assert r.status_code == 400 and 'access-control-allow-origin' not in r.headers
        r = c.post('/api/v1/auth/login', json=credentials, headers=csrf())
        assert r.status_code == 200
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=lax' in r.headers['set-cookie']
        assert 'Path=/api/v1/auth' in r.headers['set-cookie']
        token = r.json()
        assert token['token_type'] == 'Bearer'
        claims = __import__('json').loads(base64.urlsafe_b64decode(token['access_token'].split('.')[1] + '==='))
        assert claims['roles'] == ['patient']
        authorization = {'Authorization': 'Bearer ' + token['access_token']}
        r = c.get('/api/v1/patients/me', headers=authorization)
        assert r.status_code == 200 and r.json() == profile and r.headers.get('etag')
        old_cookie = c.cookies.get('pulsegrid_refresh')
        if expiry:
            assert token['expires_in'] <= 60, 'Set AUTH_ACCESS_SECONDS=60 for bounded expiry verification'
            time.sleep(token['expires_in'] + 2)
            assert c.get('/api/v1/patients/me', headers=authorization).status_code == 401
        r = c.post('/api/v1/auth/refresh', headers=csrf())
        assert r.status_code == 200 and c.cookies.get('pulsegrid_refresh') != old_cookie
        authorization = {'Authorization': 'Bearer ' + r.json()['access_token']}
        assert c.get('/api/v1/patients/me', headers=authorization).status_code == 200
        assert c.post('/api/v1/auth/logout', headers=csrf()).status_code == 204
        assert c.post('/api/v1/auth/refresh', headers=csrf()).status_code == 401
        assert c.get('/api/v1/patients/me', headers=authorization).status_code == 401
        # Separate login family: reuse its consumed parent and prove family revocation.
        assert c.post('/api/v1/auth/login', json=credentials, headers=csrf()).status_code == 200
        parent = c.cookies.get('pulsegrid_refresh')
        assert c.post('/api/v1/auth/refresh', headers=csrf()).status_code == 200
        child = c.cookies.get('pulsegrid_refresh')
        headers = csrf()
        headers['Cookie'] = f'pulsegrid_refresh={parent}; pulsegrid_csrf={headers["X-CSRF-Token"]}'
        assert c.post('/api/v1/auth/refresh', headers=headers).status_code == 401
        headers = csrf()
        headers['Cookie'] = f'pulsegrid_refresh={child}; pulsegrid_csrf={headers["X-CSRF-Token"]}'
        assert c.post('/api/v1/auth/refresh', headers=headers).status_code == 401
    print(f'PASS {base_url}: registration/retry/duplicate, login/profile, rotation/logout/replay, CSRF/origin'
          + (', CORS/private routes' if base_url != origin else ', frontend proxy')
          + (', real access expiry' if expiry else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--origin', default='http://127.0.0.1:5173')
    parser.add_argument('--expiry', action='store_true')
    args = parser.parse_args()
    verify(args.base_url, args.origin, args.expiry)
