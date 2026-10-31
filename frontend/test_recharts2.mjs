import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

const data = [
  { name: "employee count", value: 45 },
  { name: "customer count", value: 500 },
];

const el = React.createElement(
  BarChart,
  { width: 400, height: 250, data },
  React.createElement(XAxis, { dataKey: "name" }),
  React.createElement(YAxis, null),
  React.createElement(Bar, { dataKey: "value", fill: "#46C0C8" })
);

const html = renderToStaticMarkup(el);
console.log(html);
