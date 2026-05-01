from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        'demo/payment_system/docker-compose.yml',
        'demo/payment_system/services/payment_service/main.py',
        'demo/payment_system/services/order_service/main.py',
        'demo/payment_system/services/coupon_service/main.py',
        'demo/payment_system/prometheus/prometheus.yml',
        'demo/payment_system/promtail/promtail-config.yml',
        'data/payment_demo/deployments.json',
        'data/payment_demo/runtime/payment-service-version.txt',
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    report = {'ok': not missing, 'missing': missing, 'start_command': 'cd demo/payment_system && docker compose up --build'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not missing else 1)


if __name__ == '__main__':
    main()
