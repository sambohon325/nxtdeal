import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import ts from 'typescript';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import { chromium } from './node_modules/playwright/index.mjs';

const source = fs.readFileSync(new URL('../components/SafeHtmlPreview.tsx', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.ESNext } }).outputText;

test('authored HTML cannot execute scripts, read parent storage, or submit forms', async () => {
  globalThis.__previewReact = React;
  // The imported component resolves React when rendered.
  const hostile = `<script>parent.compromised=true</script><img src=x onerror="parent.compromised=true"><form action="/leak"><input name="secret" value="attack"><button>Submit</button></form><p>Visible content</p>`;
  // React binding is captured at import; render using a freshly initialized module.
  const mod = await import('data:text/javascript;base64,' + Buffer.from('const React = globalThis.__previewReact;\n' + js + '\n// test').toString('base64'));
  const markup = renderToStaticMarkup(React.createElement(mod.SafeHtmlPreview, { html: hostile }));
  const requests = [];
  const server = http.createServer((req, res) => { requests.push(req.url); res.setHeader('Content-Type', 'text/html'); res.end(markup); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.SECURITY_CHROMIUM ? { executablePath: process.env.SECURITY_CHROMIUM } : {}) });
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(() => localStorage.setItem('session', 'secret'));
    assert.equal(await page.locator('iframe').getAttribute('sandbox'), '');
    const frame = page.frameLocator('iframe');
    await frame.getByText('Visible content').waitFor();
    await frame.getByRole('button', { name: 'Submit' }).click();
    assert.equal(await page.evaluate(() => window.compromised), undefined);
    assert.equal(requests.some(url => url.startsWith('/leak')), false);
    const child = page.frames()[1];
    assert.equal(await child.evaluate(() => { try { return parent.localStorage.getItem('session'); } catch { return 'blocked'; } }), 'blocked');
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
    delete globalThis.__previewReact;
  }
});
