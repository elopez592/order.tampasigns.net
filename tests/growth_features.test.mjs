import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';

const app = await readFile(new URL('../app/static/app.js', import.meta.url), 'utf8');
const shop = await readFile(new URL('../app/static/shop.js', import.meta.url), 'utf8');
const upload = await readFile(new URL('../app/static/window-upload.js', import.meta.url), 'utf8');
const customers = await readFile(new URL('../app/customers.py', import.meta.url), 'utf8');
const domain = await readFile(new URL('../app/domain.py', import.meta.url), 'utf8');
const main = await readFile(new URL('../app/main.py', import.meta.url), 'utf8');

test('project center exposes proof, scheduling and commercial customer workflow', () => {
  assert.match(app, /PROJECT CENTER/);
  assert.match(app, /project-center-overview/);
  assert.match(app, /portal-appointment/);
  assert.match(main, /portal\/appointment-request/);
  assert.match(shop, /customer-reorder/);
  assert.match(shop, /customer-profile/);
  assert.match(customers, /customer_profiles/);
  assert.match(customers, /\/reorder/);
});

test('discovery, samples and artwork preflight are present', () => {
  assert.match(app, /help-choose/);
  assert.match(app, /Build something like this/);
  assert.match(shop, /industryProfiles/);
  assert.match(shop, /sample-kit-request/);
  assert.match(upload, /preflightArtwork/);
  assert.match(upload, /PPI at ordered size/);
  assert.match(domain, /rush_requested/);
});

test('reorders preserve review safety and current-price recalculation', () => {
  assert.match(customers, /create_job/);
  assert.match(customers, /Pricing is recalculated at current rates/);
  assert.match(customers, /new proof is still required/);
});


test('customer journey cleanup prioritizes next actions and progressive disclosure', () => {
  assert.match(app, /NEXT STEP/);
  assert.match(app, /More project details/);
  assert.match(app, /portal-primary-panel/);
  assert.match(shop, /business-profile-details/);
  assert.match(shop, /finder-step/);
  assert.match(shop, /Your best starting point/);
  assert.match(shop, /Drag the artwork to position it/);
  assert.match(shop, /white corner handle to resize/);
  assert.match(shop, /Save mockup to Project/);
});
