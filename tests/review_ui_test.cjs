// Regression check for the approval failure path; no browser framework or network.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const elements = new Map();
function element(key) {
  if (!elements.has(key)) elements.set(key, {value:"", textContent:"", innerHTML:"", disabled:false,
    handlers:{}, classList:{toggle(){}}, appendChild(){}, focus(){},
    addEventListener(name, fn){this.handlers[name]=fn;}});
  return elements.get(key);
}
const memory = new Map();
const context = vm.createContext({
  document:{querySelector:element,querySelectorAll:()=>[],createElement:()=>element(Symbol())},
  window:{addEventListener(){}},
  localStorage:{getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,value)},
  console:{warn(){},error(){}},
  fetch:async()=>{throw new Error("simulated server failure");}
});
const source = fs.readFileSync(path.join(__dirname,"../web/review.js"),"utf8");
vm.runInContext(source.slice(0,source.lastIndexOf("\ninit().catch")),context);
(async()=>{
  vm.runInContext('state.ocrRecords=[{index:7},{index:11}]; bindEvents(); els.correctedText.value="はい。";',context);
  await element("#approveButton").handlers.click();
  assert.equal(vm.runInContext("state.currentIndex",context),0,"failed approval must not advance");
  assert.equal(vm.runInContext('state.reviewRows.get("7").approved',context),"");
  assert.match(element("#reviewStatusLabel").textContent,/not approved/);
  assert.ok([...memory.values()].every(v=>!v.includes('"approved":"yes"')));
  element("#correctedText").value="";
  await element("#approveButton").handlers.click();
  assert.match(element("#reviewStatusLabel").textContent,/non-empty/);
  context.fetch=async()=>({ok:true,json:async()=>({saved_to_csv:true,row:{index:"7",approved:"yes",corrected_japanese_text:"はい。"}})});
  element("#correctedText").value="はい。";
  await element("#approveButton").handlers.click();
  assert.equal(vm.runInContext("state.currentIndex",context),1,"confirmed approval may advance");
  assert.equal(vm.runInContext('state.reviewRows.get("7").approved',context),"yes");
  console.log("Review UI approval/failure/recovery checks passed.");
})().catch(error=>{console.error(error);process.exitCode=1;});
