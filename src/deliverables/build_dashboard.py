"""Build the offline interactive dashboard.

Output is a single self-contained HTML file (no CDN, no fonts, no network) plus
a JSON copy of the same payload for programmatic verification.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.deliverables import data as D
from src.deliverables import theme as T

TEMPLATES = Path(__file__).resolve().parent / 'templates'
OUT = T.DELIVERABLES / 'dashboard'


def _json_for_html(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    # A literal </script> inside the payload would end the tag early.
    return text.replace('</', '<\\/')


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or D.build_payload()
    css = (TEMPLATES / 'dashboard.css').read_text(encoding='utf-8')
    js = (TEMPLATES / 'dashboard.js').read_text(encoding='utf-8')
    shell = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')

    html = (shell
            .replace('/*__CSS__*/', css)
            .replace('/*__JS__*/', js)
            .replace('/*__DATA__*/', _json_for_html(payload)))

    OUT.mkdir(parents=True, exist_ok=True)
    index = OUT / 'index.html'
    index.write_text(html, encoding='utf-8')

    data_path = OUT / 'dashboard_data.json'
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    return {
        'index': str(index.relative_to(D.ROOT)),
        'data': str(data_path.relative_to(D.ROOT)),
        'bytes': index.stat().st_size,
        'bytes_data': data_path.stat().st_size,
        'sha256': D.sha256(index),
        'payload_sha256': D.sha256(data_path),
        'external_requests': _external_requests(html),
        'rows': {
            'bowler_published': len(payload['rankings']['bowler_chase']),
            'batter_published': len(payload['rankings']['batter_chase']),
            'pool_rows': sum(len(v) for v in payload['pool'].values()),
            'exclusions': len(payload['exclusions']),
        },
    }


def _external_requests(html: str) -> list[str]:
    """Anything that would need the network is a defect in an offline build."""
    markers = ['http://', 'https://', '//cdn.', '<script src=', '<link rel="stylesheet"']
    return [m for m in markers if m in html]


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
