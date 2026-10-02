"""Server-owned capabilities for each company subscription."""
from contextvars import ContextVar
from fastapi import HTTPException
from .db import transaction

FEATURES = ('mobile_app', 'instant_proofing', 'product_generators')
PLAN_FEATURES = {name: dict.fromkeys(FEATURES, name != 'starter')
                 for name in ('starter', 'studio', 'business')}
current = ContextVar('company_entitlements', default=None)

def for_app(app):
    root = getattr(app.state, 'support_root', None)
    if not root:
        return {'plan_id': 'included', 'seats': getattr(app.state, 'seat_limit', None),
                **dict.fromkeys(FEATURES, True)}
    with transaction(root.state.database) as conn:
        row = conn.execute('SELECT billing_mode,plan_id,seats FROM platform_companies WHERE slug=?',
                           (app.state.support_slug,)).fetchone()
        if row and row['billing_mode'] in ('pilot', 'stripe'):
            plan = conn.execute('SELECT seats FROM subscription_plans WHERE id=?', (row['plan_id'],)).fetchone()
            # A missing plan fails closed; legacy contract edits cannot increase tier limits.
            return {'plan_id': row['plan_id'], 'seats': (plan['seats'] if row['billing_mode']=='pilot' else min(row['seats'], plan['seats'])) if plan else 1,
                    **PLAN_FEATURES.get(row['plan_id'], dict.fromkeys(FEATURES, False))}
    return {'plan_id': 'manual', 'seats': row['seats'] if row else 1,
            **dict.fromkeys(FEATURES, True)}

def require(feature):
    capabilities = current.get()
    if capabilities is not None and not capabilities[feature]:
        raise HTTPException(403, 'This feature requires Studio or Business. Manage your subscription at /staff/billing.')

def product_config(config):
    config = dict(config)
    capabilities = current.get()
    if capabilities is not None:
        if not capabilities['instant_proofing']:
            config.update(instant=False, self_approve_artwork=False)
        if not capabilities['product_generators']:
            config.update(usdot_customizer=False, contour_customizer=False, product_generators=False)
    return config

def denied_feature(path, method, mobile=False):
    if mobile or path in ('/staff/app', '/staff/sw.js', '/staff/manifest.webmanifest') or path.startswith('/api/staff/surveys'):
        return 'mobile_app'
    if method == 'POST':
        if path == '/api/orders' or path == '/api/portal/artwork-preview/approve' or (path.startswith('/api/portal/artwork/') and path.endswith('/approve')):
            return 'instant_proofing'
        if path.startswith('/api/staff/jobs/') and path.endswith('/layout'):
            return 'product_generators'
    return None


def seat_allowed(app, user, capabilities=None):
    capabilities = capabilities or for_app(app)
    if not capabilities['seats'] or user.get('support_company'):
        return True
    with transaction(app.state.database) as conn:
        allowed = [r['id'] for r in conn.execute(
            "SELECT id FROM users WHERE active=1 ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END,id LIMIT ?",
            (capabilities['seats'],))]
    return user['id'] in allowed
