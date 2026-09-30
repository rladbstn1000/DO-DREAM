/** Actual disabled server configuration, no response injection. */
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
let playwright;try{playwright=require('playwright');}catch{playwright=require('/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');}
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const origin='http://127.0.0.1:15174';let browser;let passed=false;let errorType;let external=0;
try{
  browser=await playwright.chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,
    args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
  const context=await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*',route=>{if(new URL(route.request().url()).origin!==origin){external++;return route.abort();}return route.continue();});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  const configuration=page.waitForResponse(r=>r.url().endsWith('/api/auth/demo/config'));
  await page.goto(origin+'/demo');const response=await configuration;
  assert.equal(response.status(),200);assert.equal((await response.json()).enabled,false);
  await page.getByText('이 서버에서는 학생 체험이 비활성화되어 있습니다.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'학생 체험 시작',exact:true}).isDisabled(),true);
  assert.equal(await page.evaluate(()=>localStorage.getItem('accessToken')),null);assert.equal(external,0);passed=true;
}catch(error){errorType=error.name;}finally{
  const version=browser?.version();if(browser)await browser.close();
  const report={status:passed?'PASS':'FAIL',mode:'ACTUAL_DISABLED_SERVER_UI',browser:'Chrome '+version,origin,external,errorType};
  const encoded=JSON.stringify(report,null,2)+'\n';
  for(const name of ['student-disabled-ui-'+Date.now()+'.json','student-disabled-ui.json'])await fs.writeFile(path.join(root,'.local/phase5/results',name),encoded);
  console.log(JSON.stringify(report));process.exitCode=passed?0:1;
}
