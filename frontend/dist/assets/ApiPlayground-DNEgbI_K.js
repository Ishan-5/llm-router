import{r as n,k as L,j as e,T as G,l as W,M as D,c as F,m as X,n as Y,A as b,o as y}from"./index-B0Rc-JyB.js";const V=15,U=["curl","Python","JavaScript"];function Z(l,u,r,a){const c=u.replace(/\\/g,"\\\\").replace(/"/g,'\\"');if(l==="curl"){const h=r!=="auto"?`  "override_tier": "${r}",
`:"";return`curl -X POST ${b}/route${a?"/stream":""} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${y}" \\
  -d '{
    "query": "${c}",
${h}${a?`  "stream": true,
`:""}}'`}return l==="Python"?a?`import requests

url = "${b}/route/stream"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${y}"
}
payload = {"query": "${c}"${r!=="auto"?`, "override_tier": "${r}"`:""}, "stream": True}

resp = requests.post(url, json=payload, headers=headers, stream=True)
for line in resp.iter_lines():
    if line:
        print(line.decode())`:`import requests

url = "${b}/route"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${y}"
}
payload = {"query": "${c}"${r!=="auto"?`, "override_tier": "${r}"`:""}}

resp = requests.post(url, json=payload, headers=headers)
data = resp.json()
print(data["response"])`:l==="JavaScript"?a?`const res = await fetch("${b}/route/stream", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${y}"
  },
  body: JSON.stringify({
    query: "${c}"${r!=="auto"?`,
    override_tier: "${r}"`:""},
    stream: true
  })
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value));
}`:`const res = await fetch("${b}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${y}"
  },
  body: JSON.stringify({
    query: "${c}"${r!=="auto"?`,
    override_tier: "${r}"`:""}
  })
});

const data = await res.json();
console.log(data.response);`:""}function ee({query:l,tier:u,streaming:r}){const[a,c]=n.useState("curl"),[h,i]=n.useState(!1),j=Z(a,l,u,r);function p(){navigator.clipboard.writeText(j).then(()=>{i(!0),setTimeout(()=>i(!1),2e3)})}return e.jsxs("div",{className:"rounded-xl border border-line overflow-hidden",children:[e.jsxs("div",{className:"flex items-center justify-between bg-panel px-3 py-2 border-b border-line",children:[e.jsx("div",{className:"flex gap-1",children:U.map(x=>e.jsx("button",{onClick:()=>c(x),className:`font-mono text-[10px] px-2.5 py-1 rounded-md transition-colors ${a===x?"bg-signal/15 text-signal border border-signal/30":"text-muted hover:text-primary border border-transparent"}`,children:x},x))}),e.jsx("button",{onClick:p,className:"font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-1 rounded-md hover:bg-base",children:h?"copied":"copy"})]}),e.jsx("pre",{className:"bg-surface px-4 py-3 overflow-x-auto text-xs font-mono text-primary leading-relaxed max-h-64",children:e.jsx("code",{children:j})})]})}function m({label:l,value:u,color:r}){const a={signal:"text-signal bg-signal/10 border-signal/30",cool:"text-cool bg-cool/10 border-cool/30",danger:"text-danger bg-danger/10 border-danger/30",muted:"text-muted bg-surface border-line"};return e.jsxs("div",{className:`inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-1 rounded-md border ${a[r]||a.muted}`,children:[e.jsx("span",{className:"opacity-60",children:l}),e.jsx("span",{className:"font-semibold",children:u})]})}function se(){const[l,u]=n.useState(""),[r,a]=n.useState("auto"),[c,h]=n.useState(()=>L()??1),[i,j]=n.useState(!1),[p,x]=n.useState(!1),[v,f]=n.useState(!1),[o,S]=n.useState(null),[g,$]=n.useState([]),[k,_]=n.useState(null),[C,H]=n.useState([]),[T,O]=n.useState(!1),[q,I]=n.useState(""),A=n.useRef(null),P=n.useRef(null),R=n.useRef(null);n.useEffect(()=>{const t=A.current;t&&(t.style.height="auto",t.style.height=Math.min(t.scrollHeight,140)+"px")},[l]),n.useEffect(()=>{var t;i&&g.length>0&&((t=P.current)==null||t.scrollIntoView({behavior:"smooth",block:"nearest"}))},[g,i]);function E(t){t&&t.preventDefault();const d=l.trim();if(!d||v)return;f(!0),_(null),S(null),$([]),I(d);const N=new AbortController;R.current=N;const J=Date.now();i?X(d,r==="auto"?null:r,p,s=>$(w=>[...w,s]),null,s=>{const w=Date.now()-J;B({query:d,tier:(s==null?void 0:s.routed_to)||r,model:(s==null?void 0:s.routed_to)||"—",cost:(s==null?void 0:s.cost_usd)||0,latency_ms:(s==null?void 0:s.latency_ms)||w,cache_hit:(s==null?void 0:s.cache_hit)||!1,streaming:!0,response_text:"",timestamp:new Date().toISOString()}),f(!1)},s=>{_(s),f(!1)},N.signal,c):Y(d,r==="auto"?null:r,p,N.signal,c).then(s=>{S(s),B({query:d,tier:s.routed_to,model:s.routed_to,cost:s.cost_usd||0,latency_ms:s.latency_ms||0,cache_hit:s.cache_hit||!1,streaming:!1,response_text:s.response||"",difficulty_score:s.difficulty_score,tokens_saved_usd:s.tokens_saved_usd,timestamp:new Date().toISOString()})}).catch(s=>_(s.message)).finally(()=>f(!1))}function B(t){H(d=>[t,...d].slice(0,V))}function z(t){t.key==="Enter"&&(t.metaKey||t.ctrlKey)&&(t.preventDefault(),E())}function M(t){u(t.query),a(t.tier==="auto"||!t.tier?"auto":t.tier)}function K(){var t;(t=R.current)==null||t.abort(),f(!1)}const Q=g.join("");return e.jsxs("div",{className:"space-y-4",children:[e.jsx("form",{onSubmit:E,className:"space-y-3",children:e.jsxs("div",{className:"bg-panel border border-line rounded-xl overflow-hidden focus-within:border-signal/50 focus-within:ring-1 focus-within:ring-signal/20 transition-all",children:[e.jsx("textarea",{ref:A,value:l,onChange:t=>u(t.target.value),onKeyDown:z,placeholder:"Type a prompt to test your router...",rows:2,className:"w-full bg-transparent px-4 pt-4 pb-2 font-body text-sm text-primary placeholder:text-muted resize-none focus:outline-none leading-relaxed"}),e.jsxs("div",{className:"flex items-center justify-between px-3 pb-3",children:[e.jsxs("div",{className:"flex items-center gap-2 flex-wrap",children:[e.jsxs("select",{value:r,onChange:t=>a(t.target.value),className:"bg-surface border border-line rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-muted focus:outline-none focus:ring-1 focus:ring-signal/50",children:[e.jsx("option",{value:"auto",children:"Auto-route"}),e.jsx("option",{value:"cheap",children:"Cheap"}),e.jsx("option",{value:"mid",children:"Mid"}),e.jsx("option",{value:"frontier",children:"Frontier"})]}),e.jsx("button",{type:"button",onClick:()=>j(t=>!t),className:`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${i?"border-cool text-cool bg-cool/10":"border-line text-muted hover:text-primary"}`,children:i?"⚡ streaming":"streaming"}),e.jsx("button",{type:"button",onClick:()=>x(t=>!t),className:`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${p?"border-signal text-signal bg-signal/10":"border-line text-muted hover:text-primary"}`,children:p?"cache off":"cache on"}),e.jsx("div",{className:"w-28 sm:w-36",children:e.jsx(G,{value:c,onChange:t=>{h(t),W(t)},compact:!0})}),e.jsx("span",{className:"font-mono text-[10px] text-muted/50 hidden sm:inline",children:"⌘+Enter to send"})]}),e.jsxs("div",{className:"flex items-center gap-2",children:[v&&e.jsx("button",{type:"button",onClick:K,className:"font-mono text-[10px] text-danger hover:text-danger/80 transition-colors px-2 py-1",children:"cancel"}),e.jsx("button",{type:"submit",disabled:v||!l.trim(),className:"h-8 px-4 flex items-center gap-1.5 rounded-lg bg-signal text-white text-xs font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition",children:v?e.jsxs(e.Fragment,{children:[e.jsx("svg",{width:"12",height:"12",viewBox:"0 0 14 14",className:"animate-spin",children:e.jsx("circle",{cx:"7",cy:"7",r:"5.5",fill:"none",stroke:"currentColor",strokeWidth:"1.5",strokeDasharray:"20 14"})}),"Running"]}):e.jsxs(e.Fragment,{children:[e.jsxs("svg",{width:"12",height:"12",viewBox:"0 0 14 14",fill:"none",stroke:"currentColor",strokeWidth:"1.8",strokeLinecap:"round",children:[e.jsx("line",{x1:"2",y1:"7",x2:"12",y2:"7"}),e.jsx("polyline",{points:"7,2 12,7 7,12"})]}),"Send"]})})]})]})]})}),k&&e.jsx("div",{className:"bg-danger/5 border border-danger/30 rounded-xl px-4 py-3",children:e.jsx("p",{className:"font-mono text-xs text-danger",children:k})}),i&&g.length>0&&e.jsxs("div",{className:"bg-panel border border-line rounded-xl px-5 py-4 space-y-3 animate-[slide-in_0.15s_ease-out]",children:[e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-2",children:[e.jsx("span",{className:"w-2 h-2 rounded-full bg-cool animate-pulse"}),e.jsx("span",{className:"font-mono text-[10px] text-cool uppercase tracking-wide",children:"Streaming response"})]}),e.jsxs("span",{className:"font-mono text-[10px] text-muted",children:[g.length," chunks"]})]}),e.jsxs("div",{className:`prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
            prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
            prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            max-h-96 overflow-y-auto
          `,children:[e.jsx(D,{remarkPlugins:[F],children:Q}),e.jsx("div",{ref:P})]})]}),o&&!i&&e.jsxs("div",{className:"bg-panel border border-line rounded-xl px-5 py-4 space-y-4 animate-[slide-in_0.15s_ease-out]",children:[e.jsxs("div",{className:"flex items-center gap-2 flex-wrap",children:[e.jsx(m,{label:"tier",value:o.routed_to,color:o.routed_to==="frontier"?"danger":o.routed_to==="mid"?"signal":"cool"}),o.intended_tier&&o.intended_tier!==o.routed_to&&e.jsx(m,{label:"intended",value:o.intended_tier,color:"muted"}),o.predicted_tier&&e.jsx(m,{label:"predicted",value:o.predicted_tier,color:"muted"}),o.cache_hit&&e.jsx(m,{label:"cache",value:"hit",color:"cool"}),o.fallback_used&&e.jsx(m,{label:"fallback",value:"yes",color:"danger"}),o.difficulty_score!=null&&e.jsx(m,{label:"difficulty",value:o.difficulty_score.toFixed(2),color:"muted"})]}),e.jsxs("div",{className:"flex items-center gap-4 font-mono text-[11px] text-muted",children:[e.jsxs("span",{children:["$",(o.cost_usd||0).toFixed(4)]}),e.jsxs("span",{children:[(o.latency_ms||0).toFixed(0),"ms"]}),o.tokens_saved_usd>0&&e.jsxs("span",{className:"text-cool",children:["$",o.tokens_saved_usd.toFixed(4)," saved"]})]}),e.jsx("div",{className:"bg-surface rounded-lg border border-line px-4 py-3 max-h-96 overflow-y-auto",children:e.jsx("div",{className:`prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
              prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
              prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            `,children:e.jsx(D,{remarkPlugins:[F],children:o.response||""})})})]}),q&&e.jsxs("div",{className:"space-y-2",children:[e.jsxs("button",{onClick:()=>O(t=>!t),className:"font-mono text-[10px] text-muted hover:text-primary transition-colors flex items-center gap-1",children:[T?"▾":"▸"," Code snippets"]}),T&&e.jsx("div",{className:"animate-[cmd-slide_0.15s_ease-out]",children:e.jsx(ee,{query:q,tier:r,streaming:i})})]}),C.length>0&&e.jsxs("div",{className:"space-y-2",children:[e.jsx("h4",{className:"font-mono text-[10px] text-muted uppercase tracking-wide",children:"History"}),e.jsx("div",{className:"space-y-1 max-h-72 overflow-y-auto",children:C.map((t,d)=>e.jsxs("button",{onClick:()=>M(t),className:"w-full text-left px-3 py-2.5 bg-surface hover:bg-panel border border-line hover:border-signal/30 rounded-lg transition-colors group",children:[e.jsxs("div",{className:"flex items-center gap-2 mb-1",children:[e.jsx("span",{className:`font-mono text-[9px] px-1.5 py-0.5 rounded border ${t.tier==="frontier"?"text-danger bg-danger/10 border-danger/30":t.tier==="mid"?"text-signal bg-signal/10 border-signal/30":"text-cool bg-cool/10 border-cool/30"}`,children:t.tier}),t.cache_hit&&e.jsx("span",{className:"font-mono text-[9px] text-cool",children:"cache"}),t.streaming&&e.jsx("span",{className:"font-mono text-[9px] text-muted",children:"stream"}),e.jsxs("span",{className:"font-mono text-[9px] text-muted ml-auto",children:["$",t.cost.toFixed(4)," · ",t.latency_ms.toFixed(0),"ms"]})]}),e.jsx("p",{className:"font-mono text-[11px] text-primary truncate group-hover:text-signal transition-colors",children:t.query})]},d))})]})]})}export{se as default};
