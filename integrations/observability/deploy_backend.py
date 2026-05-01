from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {'services': {}}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'services': {}}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


class DemoDeployBackend:
    def __init__(self, state_file: Path, version_file: Path):
        self.state_file = state_file
        self.version_file = version_file

    def recent_deploys(self, service: str, since: str = '2h') -> List[Dict[str, Any]]:
        state = _read_json(self.state_file)
        svc = state.get('services', {}).get(service, {})
        history = svc.get('history', [])
        return history or [{
            'evidence_id': 'ev_deploy_demo_missing_history',
            'source': 'deploy',
            'service': service,
            'summary': 'No demo deploy history was found.',
            'raw_ref': f'deploy://demo/{service}',
            'confidence': 0.4,
        }]

    def rollback_canary(self, service: str, target_revision: str, dry_run: bool = True, checkpoint_id: str = '') -> Dict[str, Any]:
        state = _read_json(self.state_file)
        services = state.setdefault('services', {})
        svc = services.setdefault(service, {})
        current = svc.get('current_version') or (self.version_file.read_text().strip() if self.version_file.exists() else 'unknown')
        payload = {
            'status': 'dry_run_succeeded' if dry_run else 'controlled_execution_succeeded',
            'service': service,
            'current_revision': current,
            'target_revision': target_revision,
            'dry_run': dry_run,
            'checkpoint_id': checkpoint_id,
            'raw_ref': f'rollback://payment-demo/{service}/{target_revision}',
            'message': 'Demo rollback writes the mounted payment-service version file only. It does not touch production.',
        }
        if not dry_run:
            self.version_file.parent.mkdir(parents=True, exist_ok=True)
            self.version_file.write_text(target_revision, encoding='utf-8')
            svc['previous_version'] = current
            svc['current_version'] = target_revision
            svc.setdefault('history', []).insert(0, {
                'evidence_id': f'ev_deploy_rollback_{int(time.time())}',
                'source': 'deploy',
                'service': service,
                'version': target_revision,
                'previous_version': current,
                'deployed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'operator': 'RunbookHermes controlled rollback',
                'summary': f'RunbookHermes changed {service} from {current} to {target_revision} in the payment demo.',
                'raw_ref': f'deploy://payment-demo/{service}/{target_revision}',
                'confidence': 0.95,
            })
            state['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            _write_json(self.state_file, state)
        return payload
