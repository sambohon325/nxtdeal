import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canonicalApiUrl } from '../lib/canonicalApiUrl.ts';

test('known retired APIs use HTTPS NXTDeal origins before credentials are sent', () => {
  assert.equal(canonicalApiUrl('http://dealer1-api.dealeros.xyz:8000/'), 'https://api.nxtdeal.app');
  assert.equal(canonicalApiUrl('https://hub-api.dealeros.xyz/hub?x=1'), 'https://hub-api.nxtdeal.app/hub?x=1');
});
test('unknown retired tenants fail closed instead of guessing a destination', () => {
  for (const host of ['dealeros.xyz', 'other.dealeros.xyz']) {
    assert.throws(() => canonicalApiUrl(`https://${host}`), /needs its NXTDeal API/);
  }
});
test('other tenant addresses and local development remain unchanged', () => {
  for (const url of ['https://dealer.example/api', 'http://127.0.0.1:8000', 'https://api.nxtdeal.app']) {
    assert.equal(canonicalApiUrl(url), url);
  }
});
