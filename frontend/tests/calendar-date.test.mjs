import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const scope={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/calendarDate.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
const format=scope.exports.formatCalendarDate;
test('date-only arrival and warranty dates retain the entered calendar day west of UTC',()=>{
 assert.equal(format('2026-10-24','en-US',{timeZone:'America/Chicago'}),'10/24/2026');
 assert.equal(format('2026-10-24','en-US',{timeZone:'Pacific/Honolulu'}),'10/24/2026');
});
test('timestamps still respect local conversion and invalid dates are explicit',()=>{
 assert.equal(format('2026-10-24T00:00:00Z','en-US',{timeZone:'America/Chicago'}),'10/23/2026');
 assert.equal(format('not-a-date','en-US'),'—');
});
