"""Versioned customer terms and explicit artwork/sizing acceptance records."""
import json
from html import escape

from fastapi import HTTPException

from .db import audit, now

VERSION = '2026-09-30'
SECTIONS = [
    ('Artwork and proof approval',
     'Review every file, preview and printed side, including spelling, numbers, logos, colors, '
     'layout, placement, quantities and finished dimensions. An uploaded file or instant preview '
     'that you explicitly approve is your production proof; a second approval of the same artwork '
     'is not required. Uploading a file or making a payment alone does not approve artwork. '
     'If you request design help, a revised shop proof must be approved before printing.'),
    ('Measurements and quoted scope',
     'You are responsible for checking the dimensions, units, quantities, installation surface '
     'and fit of your order. Quotes based on customer measurements, photos or estimates are '
     'subject to those details being accurate. A photo mockup is a visual reference, not a site '
     'measurement. Request a paid site survey before approving production if you need Tampa '
     'Signs and Stickers to verify measurements and provide the most accurate sizing and quote.'),
    ('Optional paid site survey',
     'Site surveys are available for an additional fee, quoted separately based on location, '
     'travel, access and scope. Requesting a survey does not book a visit or approve a fee. '
     'We confirm the survey price and appointment with you before proceeding. Orders awaiting '
     'a requested survey require the verified scope and artwork to be approved before printing.'),
    ('Final artwork and changes',
     'Approved artwork is final for the approved version and specifications. Request any change '
     'before production and wait for written confirmation that the job has been stopped. '
     'Changed artwork or dimensions require a revised quote or proof and new approval. '
     'Once printed, artwork cannot be changed; customer-requested corrections, resizing or '
     'replacement prints are a new paid order. Reprints needed because of customer-approved '
     'errors or incorrect customer measurements are at the customer\'s expense.'),
    ('Print appearance and production',
     'Screens and photo mockups do not guarantee exact printed color, physical scale or fit. '
     'Tell us before approval if exact color matching or a physical sample is required; any '
     'additional service will be quoted. We check files for production suitability. If our '
     'preflight requires an artwork or scope change, we obtain approval of that changed version. '
     'Production begins only after the required payment, approved artwork and any required '
     'survey or preparation are complete.'),
    ('Custom work and corrections',
     'Custom printed work cannot be returned or refunded for an error present in the approved '
     'artwork or for incorrect customer-supplied sizing. Contact us promptly if delivered work '
     'differs from the approved proof or has a production defect so we can review and correct '
     'it. These terms do not exclude rights or remedies required by applicable law.'),
]
CHECKOUT_CONFIRMATION = (
    'I checked the products, dimensions, quantities and supplied measurements and accept the '
    'Artwork, Sizing & Production Terms. I understand that approved artwork is final, '
    'changes after printing require a new paid order, and a site survey costs extra.'
)
APPROVAL_STATEMENT = (
    'I approve this exact artwork and preview package for production, including every printed '
    'side, spelling, content, dimensions, quantity, layout and placement. I have verified the '
    'measurements or obtained a site survey. I understand screen colors may differ from print, '
    'approved artwork is final, and changes after printing require a new paid order. '
    'I accept the Artwork, Sizing & Production Terms. This approval applies to this version '
    'and scope; changed artwork or sizing requires a new approval.'
)
PROOF_REVIEW_NOTICE = (
    'Your artwork proof and the Artwork, Sizing & Production Terms are ready to review '
    'together in your private order page. Check every file, spelling, dimensions and '
    'quantity before approving, or request changes. You are responsible for verifying '
    'your measurements; a site survey can be requested for an additional quoted fee. '
    'Approved artwork is final, and changes after printing require a new paid order.'
)


def public_terms():
    return {'version': VERSION, 'title': 'Artwork, Sizing & Production Terms',
            'sections': [{'title': title, 'text': body} for title, body in SECTIONS],
            'confirmation': CHECKOUT_CONFIRMATION}


def terms_page(shop):
    """Public website page; acceptance happens alongside the client's artwork."""
    name = escape(shop.get('shop_name') or 'Tampa Signs and Stickers')
    links = ''.join(f'<a href="#term-{index}">{escape(title)}</a>'
                    for index, (title, _) in enumerate(SECTIONS, 1))
    sections = ''.join(f'<section aria-labelledby="term-{index}"><h2 id="term-{index}">{escape(title)}</h2>'
                       f'<p>{escape(body)}</p></section>' for index, (title, body) in enumerate(SECTIONS, 1))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Artwork, Sizing &amp; Production Terms | {name}</title>'
            '<link rel="stylesheet" href="/static/styles.css?v=20260930-terms-2">'
            '</head><body class="terms-page"><div class="public-masthead"><header class="public-header">'
            f'<a class="brand" href="/" aria-label="{name} home"><img class="brand-logo" '
            f'src="/static/brand/tampa-white.png" alt="{name}"></a>'
            '<nav class="nav-links" aria-label="Customer navigation"><a href="/">Shop</a>'
            '<a href="/terms" aria-current="page">Terms</a><a href="/products">All products</a>'
            '<a href="/account">My orders</a><a href="/contact">Contact</a></nav></header></div>'
            '<main class="public-page terms-content"><div class="eyebrow">CLIENT ORDER TERMS</div>'
            '<h1>Artwork, Sizing &amp; Production Terms</h1>'
            '<p class="terms-intro">Review these terms on the website, then accept them together with '
            'your artwork approval at checkout or in your private order page.</p>'
            f'<p class="field-hint">Version {VERSION}</p>'
            f'<nav class="terms-section-links" aria-label="Terms sections">{links}</nav>'
            f'<article class="panel terms-document">{sections}</article>'
            '<aside class="panel terms-confirmation"><h2>What you confirm when approving</h2>'
            f'<p>{escape(APPROVAL_STATEMENT)}</p>'
            '<p class="field-hint mt">Your name, approval time, artwork version and accepted terms '
            'are saved with your order.</p></aside>'
            '<footer class="public-footer"><a href="/">Back to the shop</a>'
            '<a href="/account">My orders</a><a href="/contact">Ask about sizing or a site survey</a>'
            '</footer></main></body></html>')


def record_acceptance(conn, job, signer, method, proof_id=None, files=None, survey=False):
    snapshot = public_terms()
    scope = json.loads(job['quote_snapshot'])
    conn.execute('''INSERT INTO job_terms_acceptances
        (job_id,proof_id,quote_version,terms_version,signer_name,method,terms_snapshot,scope_snapshot,file_manifest,site_survey_requested,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (job['id'], proof_id, job['quote_version'], VERSION, signer, method,
         json.dumps(snapshot), json.dumps(scope), json.dumps(files or []), int(survey), now()))
    audit(conn, job['id'], signer + ' (private job link)', 'terms.accepted',
          {'version': VERSION, 'quote_version': job['quote_version'], 'method': method,
           'site_survey_requested': bool(survey)}, True)


def validate_version(payload, required=False):
    if (required and 'terms_version' not in payload) or payload.get('terms_version', VERSION) != VERSION:
        raise HTTPException(409, 'The order terms changed. Reload and review the current terms.')
