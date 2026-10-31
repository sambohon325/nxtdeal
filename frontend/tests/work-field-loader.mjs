import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as React from 'react';
import * as jsx from 'react/jsx-runtime';
const scope = {exports: {}, require: name => name === 'react' ? React : name === 'react/jsx-runtime' ? jsx : {}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/WorkField.tsx', import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText, scope);
export const WorkField = scope.exports.WorkField;
