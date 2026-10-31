import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deploymentRedirect } from '../lib/deploymentRouting.ts';

test('shared apps landing and deep links stay on the app suite', () => {
  assert.equal(deploymentRedirect('apps', '/'), '/apps');
  for (const path of ['/apps', '/apps/mysales', '/apps/serviceops', '/checkin/token', '/approve/token', '/pay/token']) {
    assert.equal(deploymentRedirect('apps', path), null);
  }
  for (const path of ['/workspace', '/admin', '/hub-console', '/apps-other']) {
    assert.equal(deploymentRedirect('apps', path), '/apps');
  }
});

test('Hub routing stays scoped and the marketing deployment is a one-page handoff', () => {
  assert.equal(deploymentRedirect('hub', '/'), '/hub-console');
  assert.equal(deploymentRedirect('hub', '/hub-console'), null);
  assert.equal(deploymentRedirect('hub', '/hub-console-other'), '/hub-console');
  assert.equal(deploymentRedirect('hub', '/apps'), '/hub-console');
  assert.equal(deploymentRedirect('marketing', '/'), null);
  for (const path of ['/pricing', '/app-suite', '/start-free', '/solutions', '/industries/sales', '/contact', '/workspace', '/api/demo']) {
    assert.equal(deploymentRedirect('marketing', path), '/');
  }
  for (const path of ['/apps', '/hub-console', '/pricing-other']) {
    assert.equal(deploymentRedirect('marketing', path), '/');
  }
});

test('brand and installation assets are reachable without opening dealer routes', () => {
  for (const mode of ['hub', 'marketing', 'apps']) {
    for (const path of ['/brand/logo.png', '/icon.png', '/apple-icon.png', '/manifest.webmanifest', '/_next/static/app.js']) {
      assert.equal(deploymentRedirect(mode, path), null);
    }
    assert.notEqual(deploymentRedirect(mode, '/private.json'), null);
    assert.notEqual(deploymentRedirect(mode, '/api-lookalike'), null);
  }
});

test('dealer deployment keeps workspace, app and customer routes', () => {
  for (const path of ['/workspace', '/apps', '/apps/reception', '/profile/customer', '/checkin/token']) {
    assert.equal(deploymentRedirect(undefined, path), null);
  }
});
