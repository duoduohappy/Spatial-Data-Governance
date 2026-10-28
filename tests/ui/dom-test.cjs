const fs=require('fs'),vm=require('vm'),path=require('path');
const {parseHTML}=require('linkedom');
const root=path.resolve(__dirname,'../..');
const {window}=parseHTML(fs.readFileSync(path.join(root,'geoacceptance/web/index.html'),'utf8').replace('__CSRF__','test-token'));
const document=window.document;
Object.defineProperty(window.HTMLSelectElement.prototype,'value',{get(){return this.querySelector('option[selected]')?.value||this.querySelector('option')?.value||''},set(v){for(const o of this.querySelectorAll('option')){if(o.value===v)o.setAttribute('selected','');else o.removeAttribute('selected')}}});
const context={window,document,Node:window.Node,console,setTimeout,clearTimeout,crypto:require('crypto').webcrypto,confirm:()=>true,
localStorage:{getItem:()=>null,setItem:()=>{}},FormData:class{},fetch:async(url)=>({ok:true,json:async()=>url==='/api/config'?{configured:false}:[]})};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'geoacceptance/web/app.js'),'utf8'),context);
setTimeout(()=>{
 try{
  if(!document.querySelector('h1')?.textContent.includes('验收结论'))throw Error('Welcome rendering failed');
  vm.runInContext(`project={id:'test',name:'DOM测试',revision:1,jobs:[],audit:[],files:{'poi.csv':'abc'},draft:null,approval:null,preview:{document:'x'},points:{records:2,shown:2,points:[{line:2,record_id:'a',name:'A',longitude:116.3,latitude:39.9},{line:3,record_id:'b',name:'B',longitude:null,latitude:null}],area:{type:'Polygon',coordinates:[[[116.2,39.8],[116.4,39.8],[116.4,40],[116.2,40],[116.2,39.8]]]}}};render();`,context);
  if(document.querySelectorAll('.stat').length!==4)throw Error('Stats failed');
  if(document.querySelectorAll('.map circle').length!==1)throw Error('Map point count');
  vm.runInContext(`tab='review';render();tab='results';render();tab='compare';render();tab='history';render();`,context);
    const fixture=JSON.parse(fs.readFileSync(path.join(root,'acceptance/stage-3/dom-fixture.json'),'utf8'));
  context.fixture=fixture;
  vm.runInContext(`project=fixture.project;report=fixture.report;projects=[project];tab='review';render();tab='results';render();tab='history';render();tab='overview';render();`,context);
  if(!document.querySelector('h1')?.textContent.includes('defective'))throw Error('Real API fixture rendering failed');
  vm.runInContext(`project.draft.collaboration={strategy:'dual_review',status:'NO_ISSUES_FOUND_NOT_APPROVED',limits:{max_model_calls:4},actual_model_calls:2,tool_trace:[],revision:null,review:{checks:[{requirement_id:'A1',status:'ISSUE',reason:'<img src=x onerror=alert(1)>'}]}};tab='review';render();`,context);
  if(!document.querySelector('h3')?.textContent.includes('协作审查'))throw Error('Collaborative review panel absent');
  if(document.querySelector('img'))throw Error('Review text executed as HTML');
  vm.runInContext(`config={configured:true,review_strategies:['single','dual_review']};tab='overview';render();`,context);
  if(![...document.querySelectorAll('button')].some(b=>b.textContent.includes('双 Agent')))throw Error('Collaboration action absent');
  console.log('DOM_OK=true: welcome, overview, stats, SVG map, empty review/results/compare/history');
  const out=path.resolve(root,process.env.GA_TEST_EVIDENCE_DIR||'acceptance/stage-3');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'dom-check.txt'),'DOM_OK=true\nIncludes collaboration panel, XSS-safe review text and collaboration action. DOM simulation, not real-browser visual evidence.\n');
 }catch(e){console.error(e);process.exitCode=1}
},30);



