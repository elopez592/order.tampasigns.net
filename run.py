"""Local / single-container entrypoint. Never enable demonstration data on a live store."""
from __future__ import annotations
import argparse
import os
import uvicorn
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description='Run SignShop OS')
    parser.add_argument('--demo', action='store_true', help='Seed four clearly marked example jobs and a demo employee on first run.')
    parser.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8000')))
    args = parser.parse_args()
    app = create_app(demo=args.demo or os.getenv('DEMO_SEED') == '1')
    if app.state.initial_credentials:
        print('\nNEW ACCOUNTS - save these generated passwords securely:', flush=True)
        for role, address, password in app.state.initial_credentials:
            print(f'  {role}: {address}\n  Password: {password}\n', flush=True)
        print('Passwords are printed only at initial creation. Change them after sign-in.\n', flush=True)
    print(f'Customer calculator: {app.state.public_url}/\nStaff workspace: {app.state.public_url}/staff', flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level='info', access_log=False,
                proxy_headers=os.getenv('TRUST_PROXY', '0') == '1',
                forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS', '127.0.0.1'))


if __name__ == '__main__':
    main()
