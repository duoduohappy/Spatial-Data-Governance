'use strict';
// Real Chromium check with isolated synthetic data; no user project or provider calls.
const {chromium}=require('playwright-core');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'acceptance/stage-3/browser');
const DEMO=process.argv.includes('--demo');
const PY=process.env.GA_TEST_PYTHON||path.join(ROOT,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const PORT=Number(process.env.GA_TEST_PORT||8976),URL=`http://127.0.0.1:${PORT}`;
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),stamp=new Date().toISOString().replace(/[:.]/g,'-');
const runDir=path.join(ROOT,'work/browser-check',stamp),evidence=path.join(OUT,stamp);
fs.mkdirSync(evidence,{recursive:true});
const summary={at:new Date().toISOString(),mode:'real Chromium, automated synthetic review',checks:[],screenshots:[],errors:[]};
const check=name=>summary.checks.push({name,status:'PASS'});
let server,browser,context,page;
async function capture(name){const file=`${name}.png`;await page.screenshot({path:path.join(evidence,file),fullPage:true});summary.screenshots.push(file);}
async function dwell(){if(DEMO)await sleep(22000);}
async function waitText(text){await page.getByText(text,{exact:true}).first().waitFor({state:'visible',timeout:30000});}
async function noOverflow(label){const v=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));assert.ok(v.scroll<=v.width+1,`${label}: ${JSON.stringify(v)}`);check(label);}
async function main(){
 const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONUTF8:'1'};
 for(const k of Object.keys(env))if(k.startsWith('GA_'))delete env[k];
 server=spawn(PY,['-X','utf8','-m','geoacceptance.server','--port',String(PORT),'--data-dir',runDir],{cwd:ROOT,env,windowsHide:true});
 const log=fs.createWriteStream(path.join(evidence,'server.txt'));server.stdout.pipe(log);server.stderr.pipe(log);
 let ready=false;for(let i=0;i<100;i++){if(server.exitCode!==null)throw Error('Test server exited');try{const r=await fetch(URL+'/api/config');if(r.ok){ready=true;break;}}catch{}await sleep(100);}
 assert.ok(ready,'Server ready');
 const options={headless:true,downloadsPath:path.join(runDir,"downloads")};
 fs.mkdirSync(options.downloadsPath,{recursive:true});
 const local=process.env.GA_TEST_BROWSER||(process.platform==='win32'?'C:/Program Files/Google/Chrome/Application/chrome.exe':'');
 if(local && local!=='bundled')options.executablePath=local;
 browser=await chromium.launch(options);summary.browser_version=browser.version();
 context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:path.join(evidence,'video'),size:{width:1440,height:1000}},acceptDownloads:true});
 page=await context.newPage();page.on('pageerror',e=>summary.errors.push(e.message));
 await page.goto(URL);await waitText('让每一条验收结论，都有依据。');
 await capture('01-welcome');await noOverflow('desktop welcome has no horizontal overflow');await dwell();
 await page.getByRole('button',{name:'体验含缺陷示例',exact:true}).click();await page.getByRole('heading',{name:'示例 · defective',exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'执行检查 →',exact:true}).isEnabled(),false);
 assert.equal(await page.getByRole('button',{name:'真实模型生成',exact:true}).isEnabled(),false);
 check('unapproved execution blocked; unconfigured live disabled');await capture('02-import');await dwell();
 await page.getByRole('button',{name:'离线规则基线',exact:true}).click();
 await page.locator('#reviewer').waitFor({state:'visible',timeout:30000});
 assert.equal(await page.locator('.clause').count(),10);check('10 source clauses visible');
 await page.getByRole('button',{name:'确认并批准当前版本',exact:true}).click();await waitText('请先确认已完成审核');
 assert.equal(await page.getByRole('button',{name:'执行检查 →',exact:true}).isEnabled(),false);check('unchecked review cannot approve');
 await page.locator('#reviewer').fill('自动化浏览器示例（非真实用户审核）');await page.locator('#confirmed').check();
 await capture('03-review');await dwell();
 await page.getByRole('button',{name:'确认并批准当前版本',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('.hero-actions button').disabled);
 await page.getByRole('button',{name:'执行检查 →',exact:true}).click();
 await page.getByRole('link',{name:'导出 JSON ↗',exact:true}).waitFor({timeout:30000});
 assert.equal(await page.locator('.stats .badge').innerText(),'不通过');
 const beforeId=await page.evaluate(()=>localStorage.getItem('ga-project'));
 assert.ok(await page.locator('.map svg circle').count());check('defective batch FAIL; real SVG rendered');
 await capture('04-failure-evidence');await dwell();
 await page.locator('.map svg circle').first().click();await waitText('清除定位');check('map click links to evidence');
 await page.getByRole('button',{name:'清除定位',exact:true}).click();
 for(const ext of ['JSON','HTML']){const link=page.getByRole('link',{name:`导出 ${ext} ↗`,exact:true});const href=await link.getAttribute('href');const event=page.waitForEvent('download');await link.click();const download=await event;try{await download.saveAs(path.join(evidence,'report.'+ext.toLowerCase()));}catch(e){summary.download_status='BLOCKED: Chromium headless shell cancels attachment downloads in this environment';const response=await context.request.get(URL+href);assert.equal(response.status(),200);fs.writeFileSync(path.join(evidence,'report.'+ext.toLowerCase()),await response.body());}}
 const report=JSON.parse(fs.readFileSync(path.join(evidence,'report.json'),'utf8'));assert.equal(report.aggregate_verdict,'FAIL');check(summary.download_status?'JSON and HTML export HTTP bodies verified; browser save pending':'JSON and HTML downloaded');
 await page.getByRole('button',{name:'整改复验',exact:true}).click();
 await page.locator('#correction-files').setInputFiles(path.join(ROOT,'examples/corrected/poi.csv'));
 await page.getByRole('button',{name:'创建整改批次',exact:true}).click();
 await page.waitForFunction(id=>localStorage.getItem('ga-project')!==id,beforeId);
 await page.getByRole('button',{name:'执行检查 →',exact:true}).click();
 await page.getByRole('link',{name:'导出 JSON ↗',exact:true}).waitFor({timeout:30000});
 assert.equal(await page.locator('.stats .badge').innerText(),'通过');check('corrected batch PASS');
 await capture('05-corrected');await dwell();
 await page.getByRole('button',{name:'整改复验',exact:true}).click();
 await page.getByLabel('整改前项目',{exact:true}).selectOption(beforeId);
 await page.getByRole('button',{name:'生成复验对比',exact:true}).click();await waitText('复验无法判定');
 check('duplicate original identity prevents false ledger closure');await capture('06-compare');await dwell();
 await page.getByRole('button',{name:'操作记录',exact:true}).click();await waitText('任务记录');await capture('07-audit');await dwell();
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'交付概览',exact:true}).click();
 await noOverflow('mobile overview has no horizontal overflow');await capture('08-mobile');
 await page.getByLabel('切换交付项目',{exact:true}).selectOption(beforeId);
 await page.waitForFunction(id=>localStorage.getItem('ga-project')===id,beforeId);check('mobile can switch existing projects');await dwell();
 assert.deepEqual(summary.errors,[],'No uncaught page errors');check('no uncaught browser JavaScript errors');summary.status='PASS';
}
(async()=>{try{await main();}catch(e){summary.status='FAIL';summary.error=e.stack;if(page)try{await capture('failure');}catch{}}
 finally{if(context){const video=page.video();await context.close();if(video)summary.video=path.relative(evidence,await video.path()).replaceAll('\\','/');}
 if(browser)await browser.close();if(server)server.kill();
 fs.writeFileSync(path.join(evidence,'results.json'),JSON.stringify(summary,null,2));
 fs.writeFileSync(path.join(OUT,'latest.json'),JSON.stringify({directory:stamp,...summary},null,2));
 console.log(JSON.stringify({status:summary.status,checks:summary.checks.length,evidence}));process.exitCode=summary.status==='PASS'?0:1;}
})();
