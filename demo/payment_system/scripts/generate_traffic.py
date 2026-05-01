from __future__ import annotations

import argparse
import os
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://127.0.0.1:8080')
parser.add_argument('--fault', default='PAYMENT_503_AFTER_DEPLOY')
parser.add_argument('--requests', type=int, default=60)
parser.add_argument('--sleep', type=float, default=0.1)
args = parser.parse_args()

print(f'Generating {args.requests} payment requests against {args.base_url}; fault mode is controlled by docker-compose env: {args.fault}')
for i in range(args.requests):
    try:
        r = httpx.post(f'{args.base_url}/pay', params={'order_id': f'order-{i}', 'amount_cents': 1999}, timeout=2.0)
        print(i, r.status_code, r.text[:100])
    except Exception as exc:
        print(i, 'error', exc)
    time.sleep(args.sleep)
