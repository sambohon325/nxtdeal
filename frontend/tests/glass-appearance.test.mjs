import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/GlassAppearance.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:{})};
vm.runInNewContext(source,scope);
const {validatedGlassSettings,glassDefaults}=scope.exports;
test('invalid saved appearance cannot inject a URL or invalid colors',()=>{
 const saved=validatedGlassSettings({background:'https://other.example/track',a:'url(evil)',mode:'unknown',glass:Infinity,blur:-12,dim:200,motion:'false'});
 assert.equal(saved.background,glassDefaults.background);
 assert.equal(saved.a,glassDefaults.a);
 assert.equal(saved.mode,'dark'); assert.equal(saved.glass,56);
 assert.equal(saved.blur,0); assert.equal(saved.dim,90);assert.equal(saved.motion,true);
});
test('saved user appearance survives validation including reduced motion',()=>{
 const saved={...glassDefaults,mode:'light',background:'aurora',a:'#123abc',glass:72,motion:false};
 assert.equal(JSON.stringify(validatedGlassSettings(saved)),JSON.stringify(saved));
 assert.equal(JSON.stringify(validatedGlassSettings(null)),JSON.stringify(glassDefaults));
});
