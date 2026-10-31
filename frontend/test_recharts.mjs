import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

const data = [
  { name: "employee count", value: 45 },
  { name: "customer count", value: 500 },
  { name: "lead count", value: 1000 },
  { name: "vehicle count", value: 500 },
  { name: "finance count", value: 120 },
];

const el = React.createElement(
  BarChart,
  { width: 400, height: 250, data },
  React.createElement(XAxis, { dataKey: "name" }),
  React.createElement(YAxis, null),
  React.createElement(Bar, { dataKey: "value", fill: "#46C0C8" })
);

const html = renderToStaticMarkup(el);
console.log(html.includes('<rect') ? "HAS RECT ELEMENTS" : "NO RECT ELEMENTS FOUND");
console.log(html.length, "chars total");
// dump rects
const rects = html.match(/<rect[^>]*>/g) || [];
console.log("rect count:", rects.length);
rects.slice(0, 10).forEach(r => console.log(r));
