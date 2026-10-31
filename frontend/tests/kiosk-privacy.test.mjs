import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../lib/kioskPrivacy.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
function harness() {
  let now = 0, id = 0, expired = 0;
  const pending = new Map(), events = new Map(), warnings = [];
  const scope = { exports: {}, setTimeout: (fn, delay) => { pending.set(++id, {fn, at:now+delay}); return id; }, clearTimeout: id => pending.delete(id), window: {
    addEventListener: (name, fn) => events.set(name, fn),
    removeEventListener: (name, fn) => { if(events.get(name) === fn) events.delete(name); },
  }};
  vm.runInNewContext(source, scope);
  const timer = scope.exports.startKioskPrivacyTimer(v => warnings.push(v), () => expired++);
  function advance(ms) {
    const target = now + ms;
    while (true) {
      const next = [...pending].filter(([,v]) => v.at <= target).sort((a,b) => a[1].at-b[1].at)[0];
      if (!next) break;
      now = next[1].at; pending.delete(next[0]); next[1].fn();
    }
    now = target;
  }
  return {timer, advance, events, pending, warnings, expired: () => expired};
}

test('warns before clearing once and removes activity listeners', () => {
  const h = harness();
  h.advance(89999); assert.deepEqual(h.warnings, [false]);
  h.advance(1); assert.deepEqual(h.warnings, [false,true]);
  h.advance(29999); assert.equal(h.expired(), 0);
  h.advance(1); assert.equal(h.expired(), 1);
  assert.equal(h.events.size, 0); assert.equal(h.pending.size, 0);
  h.timer.restart(); h.advance(120000); assert.equal(h.expired(), 1);
});

test('pointer, keyboard and explicit keep-open restart the full interval', () => {
  for (const activity of ['pointerdown','keydown','button']) {
    const h = harness(); h.advance(100000);
    if(activity === 'button') h.timer.restart(); else h.events.get(activity)();
    assert.equal(h.warnings.at(-1), false);
    h.advance(119999); assert.equal(h.expired(), 0);
    h.advance(1); assert.equal(h.expired(), 1);
  }
});

test('unmount cleanup cancels pending warning and expiration', () => {
  const h = harness(); h.timer.stop(); h.timer.stop(); h.advance(240000);
  assert.equal(h.expired(), 0); assert.deepEqual(h.warnings, [false]);
  assert.equal(h.events.size, 0); assert.equal(h.pending.size, 0);
});
