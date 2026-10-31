import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  pretendToBeVisual: true,
});

global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.HTMLElement = dom.window.HTMLElement;
global.SVGElement = dom.window.SVGElement;

// jsdom has no ResizeObserver or layout engine (getBoundingClientRect always 0).
// Patch getBoundingClientRect to return a real size like a real browser would.
dom.window.HTMLElement.prototype.getBoundingClientRect = function () {
  return { width: 400, height: 250, top: 0, left: 0, right: 400, bottom: 250, x: 0, y: 0, toJSON(){} };
};

global.ResizeObserver = class {
  constructor(cb) { this.cb = cb; }
  observe(el) {
    // fire immediately with a fake entry, mimicking real browser initial measurement
    this.cb([{ target: el, contentRect: { width: 400, height: 250 } }]);
  }
  unobserve() {}
  disconnect() {}
};

const React = (await import('react')).default;
const { createRoot } = await import('react-dom/client');
const { BarChart, Bar, XAxis, YAxis, Tooltip } = await import('recharts');

const data = [
  { name: "employee count", value: 45 },
  { name: "customer count", value: 500 },
  { name: "lead count", value: 1000 },
];

const el = React.createElement(
  'div',
  { style: { width: 400, height: 250 } },
  React.createElement(
    BarChart,
    { width: 400, height: 250, data },
    React.createElement(XAxis, { dataKey: "name" }),
    React.createElement(YAxis, null),
    React.createElement(Bar, { dataKey: "value", fill: "#46C0C8" })
  )
);

const root = createRoot(document.getElementById('root'));
root.render(el);

// give effects a tick to flush
await new Promise((r) => setTimeout(r, 200));

const html = document.getElementById('root').innerHTML;
const rects = html.match(/<rect[^>]*>/g) || [];
console.log("rect count:", rects.length);
rects.forEach(r => console.log(r));
console.log("--- full length", html.length);
