import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const fixture={active_employees:{count:2},user_administration:{count:2,rows:[{employee_id:'SYN1',name:'Avery Example',role:'manager'},{employee_id:'SYN2',name:'Jordan Example',role:'sales'}]},permission_requests:{count:0}};
function setup(state){let cursor=0,requests=0;
 const source=ts.transpileModule(fs.readFileSync(new URL('../components/AdminUsersBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];}};
  if(name==='@/lib/productTheme')return {PRODUCT_ACCENT_COLORS:['blue']};
  return {getUsersOverview:async()=>{requests++;return fixture;}};
 }};vm.runInNewContext(source,scope);
 return {render:()=>{cursor=0;return elements(scope.exports.AdminUsersBoard({theme:'dark'}));},requests:()=>requests};
}
test('employee directory searches role and preserves search through record return',()=>{
 const state=[fixture,null,false,'manager',null],h=setup(state);
 let rows=h.render().filter(e=>e.props.row);assert.equal(rows.length,1);assert.equal(rows[0].props.row.employee_id,'SYN1');
 rows[0].props.onOpen('SYN1');let tree=h.render();tree.find(e=>e.props.employeeId==='SYN1').props.onClose();assert.equal(state[3],'manager');
 state[3]='missing';tree=h.render();tree.find(e=>e.props.children==='Clear search').props.onClick();assert.equal(h.render().filter(e=>e.props.row).length,2);assert.equal(h.requests(),0);
});
test('directory failures can retry without changing access',async()=>{
 const state=[null,'Offline',false,'',null],h=setup(state);
 let tree=h.render();assert.ok(tree.some(e=>e.props.role==='alert'));tree.find(e=>e.props.children==='Retry directory').props.onClick();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.requests(),1);assert.equal(state[1],null);assert.equal(h.render().filter(e=>e.props.row).length,2);
});

test('employee roster pages every record and returns to the same search and page inline',()=>{
 const data={...fixture,user_administration:{count:52,rows:Array.from({length:52},(_,i)=>({employee_id:`SYN${i}`,name:`Employee ${i}`,role:'sales'}))}};
 const state=[data,null,false,'sales',null],h=setup(state);
 assert.equal(h.render().filter(e=>e.props.row).length,25);
 h.render().find(e=>e.props.label==='Employees').props.onPageChange(1);
 let rows=h.render().filter(e=>e.props.row);assert.equal(rows[0].props.row.employee_id,'SYN25');
 rows[0].props.onOpen('SYN25');const tree=h.render();assert.equal(tree.filter(e=>e.props.row).length,0);
 tree.find(e=>e.props.employeeId==='SYN25').props.onClose();assert.equal(h.render().filter(e=>e.props.row)[0].props.row.employee_id,'SYN25');
 h.render().find(e=>e.props.label==='Employees').props.onPageChange(2);assert.equal(h.render().filter(e=>e.props.row).length,2);
 h.render().find(e=>e.props['aria-label']==='Find an employee').props.onChange({target:{value:'Employee 0'}});
 assert.equal(h.render().filter(e=>e.props.row).length,1);assert.equal(state[5],0);
});
