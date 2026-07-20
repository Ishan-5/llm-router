import{r as n,j as e,M as E,c as B,i as Q,k as J,A as g,l as b}from"./index-CZrRyd9-.js";const L=15,G=["curl","Python","JavaScript"];function W(i,u,r,l){const a=u.replace(/\\/g,"\\\\").replace(/"/g,'\\"');if(i==="curl"){const h=r!=="auto"?`  "override_tier": "${r}",
`:"";return`curl -X POST ${g}/route${l?"/stream":""} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${b}" \\
  -d '{
    "query": "${a}",
${h}${l?`  "stream": true,
`:""}}'`}return i==="Python"?l?`import requests

url = "${g}/route/stream"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${b}"
}
payload = {"query": "${a}"${r!=="auto"?`, "override_tier": "${r}"`:""}, "stream": True}

resp = requests.post(url, json=payload, headers=headers, stream=True)
for line in resp.iter_lines():
    if line:
        print(line.decode())`:`import requests

url = "${g}/route"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${b}"
}
payload = {"query": "${a}"${r!=="auto"?`, "override_tier": "${r}"`:""}}

resp = requests.post(url, json=payload, headers=headers)
data = resp.json()
print(data["response"])`:i==="JavaScript"?l?`const res = await fetch("${g}/route/stream", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${b}"
  },
  body: JSON.stringify({
    query: "${a}"${r!=="auto"?`,
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
}`:`const res = await fetch("${g}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${b}"
  },
  body: JSON.stringify({
    query: "${a}"${r!=="auto"?`,
    override_tier: "${r}"`:""}
  })
});

const data = await res.json();
console.log(data.response);`:""}function X({query:i,tier:u,streaming:r}){const[l,a]=n.useState("curl"),[h,p]=n.useState(!1),y=W(l,i,u,r);function x(){navigator.clipboard.writeText(y).then(()=>{p(!0),setTimeout(()=>p(!1),2e3)})}return e.jsxs("div",{className:"rounded-xl border border-line overflow-hidden",children:[e.jsxs("div",{className:"flex items-center justify-between bg-panel px-3 py-2 border-b border-line",children:[e.jsx("div",{className:"flex gap-1",children:G.map(c=>e.jsx("button",{onClick:()=>a(c),className:`font-mono text-[10px] px-2.5 py-1 rounded-md transition-colors ${l===c?"bg-signal/15 text-signal border border-signal/30":"text-muted hover:text-primary border border-transparent"}`,children:c},c))}),e.jsx("button",{onClick:x,className:"font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-1 rounded-md hover:bg-base",children:h?"copied":"copy"})]}),e.jsx("pre",{className:"bg-surface px-4 py-3 overflow-x-auto text-xs font-mono text-primary leading-relaxed max-h-64",children:e.jsx("code",{children:y})})]})}function m({label:i,value:u,color:r}){const l={signal:"text-signal bg-signal/10 border-signal/30",cool:"text-cool bg-cool/10 border-cool/30",danger:"text-danger bg-danger/10 border-danger/30",muted:"text-muted bg-surface border-line"};return e.jsxs("div",{className:`inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-1 rounded-md border ${l[r]||l.muted}`,children:[e.jsx("span",{className:"opacity-60",children:i}),e.jsx("span",{className:"font-semibold",children:u})]})}function V(){const[i,u]=n.useState(""),[r,l]=n.useState("auto"),[a,h]=n.useState(!1),[p,y]=n.useState(!1),[x,c]=n.useState(!1),[o,N]=n.useState(null),[f,w]=n.useState([]),[S,j]=n.useState(null),[$,D]=n.useState([]),[k,F]=n.useState(!1),[C,H]=n.useState(""),T=n.useRef(null),q=n.useRef(null),A=n.useRef(null);n.useEffect(()=>{const t=T.current;t&&(t.style.height="auto",t.style.height=Math.min(t.scrollHeight,140)+"px")},[i]),n.useEffect(()=>{var t;a&&f.length>0&&((t=q.current)==null||t.scrollIntoView({behavior:"smooth",block:"nearest"}))},[f,a]);function P(t){t&&t.preventDefault();const d=i.trim();if(!d||x)return;c(!0),j(null),N(null),w([]),H(d);const v=new AbortController;A.current=v;const K=Date.now();a?Q(d,r==="auto"?null:r,p,s=>w(_=>[..._,s]),null,s=>{const _=Date.now()-K;R({query:d,tier:(s==null?void 0:s.routed_to)||r,model:(s==null?void 0:s.routed_to)||"—",cost:(s==null?void 0:s.cost_usd)||0,latency_ms:(s==null?void 0:s.latency_ms)||_,cache_hit:(s==null?void 0:s.cache_hit)||!1,streaming:!0,response_text:"",timestamp:new Date().toISOString()}),c(!1)},s=>{j(s),c(!1)},v.signal):J(d,r==="auto"?null:r,p,v.signal).then(s=>{N(s),R({query:d,tier:s.routed_to,model:s.routed_to,cost:s.cost_usd||0,latency_ms:s.latency_ms||0,cache_hit:s.cache_hit||!1,streaming:!1,response_text:s.response||"",difficulty_score:s.difficulty_score,tokens_saved_usd:s.tokens_saved_usd,timestamp:new Date().toISOString()})}).catch(s=>j(s.message)).finally(()=>c(!1))}function R(t){D(d=>[t,...d].slice(0,L))}function O(t){t.key==="Enter"&&(t.metaKey||t.ctrlKey)&&(t.preventDefault(),P())}function I(t){u(t.query),l(t.tier==="auto"||!t.tier?"auto":t.tier)}function z(){var t;(t=A.current)==null||t.abort(),c(!1)}const M=f.join("");return e.jsxs("div",{className:"space-y-4",children:[e.jsx("form",{onSubmit:P,className:"space-y-3",children:e.jsxs("div",{className:"bg-panel border border-line rounded-xl overflow-hidden focus-within:border-signal/50 focus-within:ring-1 focus-within:ring-signal/20 transition-all",children:[e.jsx("textarea",{ref:T,value:i,onChange:t=>u(t.target.value),onKeyDown:O,placeholder:"Type a prompt to test your router...",rows:2,className:"w-full bg-transparent px-4 pt-4 pb-2 font-body text-sm text-primary placeholder:text-muted resize-none focus:outline-none leading-relaxed"}),e.jsxs("div",{className:"flex items-center justify-between px-3 pb-3",children:[e.jsxs("div",{className:"flex items-center gap-2 flex-wrap",children:[e.jsxs("select",{value:r,onChange:t=>l(t.target.value),className:"bg-surface border border-line rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-muted focus:outline-none focus:ring-1 focus:ring-signal/50",children:[e.jsx("option",{value:"auto",children:"Auto-route"}),e.jsx("option",{value:"cheap",children:"Cheap"}),e.jsx("option",{value:"mid",children:"Mid"}),e.jsx("option",{value:"frontier",children:"Frontier"})]}),e.jsx("button",{type:"button",onClick:()=>h(t=>!t),className:`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${a?"border-cool text-cool bg-cool/10":"border-line text-muted hover:text-primary"}`,children:a?"⚡ streaming":"streaming"}),e.jsx("button",{type:"button",onClick:()=>y(t=>!t),className:`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${p?"border-signal text-signal bg-signal/10":"border-line text-muted hover:text-primary"}`,children:p?"cache off":"cache on"}),e.jsx("span",{className:"font-mono text-[10px] text-muted/50 hidden sm:inline",children:"⌘+Enter to send"})]}),e.jsxs("div",{className:"flex items-center gap-2",children:[x&&e.jsx("button",{type:"button",onClick:z,className:"font-mono text-[10px] text-danger hover:text-danger/80 transition-colors px-2 py-1",children:"cancel"}),e.jsx("button",{type:"submit",disabled:x||!i.trim(),className:"h-8 px-4 flex items-center gap-1.5 rounded-lg bg-signal text-white text-xs font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition",children:x?e.jsxs(e.Fragment,{children:[e.jsx("svg",{width:"12",height:"12",viewBox:"0 0 14 14",className:"animate-spin",children:e.jsx("circle",{cx:"7",cy:"7",r:"5.5",fill:"none",stroke:"currentColor",strokeWidth:"1.5",strokeDasharray:"20 14"})}),"Running"]}):e.jsxs(e.Fragment,{children:[e.jsxs("svg",{width:"12",height:"12",viewBox:"0 0 14 14",fill:"none",stroke:"currentColor",strokeWidth:"1.8",strokeLinecap:"round",children:[e.jsx("line",{x1:"2",y1:"7",x2:"12",y2:"7"}),e.jsx("polyline",{points:"7,2 12,7 7,12"})]}),"Send"]})})]})]})]})}),S&&e.jsx("div",{className:"bg-danger/5 border border-danger/30 rounded-xl px-4 py-3",children:e.jsx("p",{className:"font-mono text-xs text-danger",children:S})}),a&&f.length>0&&e.jsxs("div",{className:"bg-panel border border-line rounded-xl px-5 py-4 space-y-3 animate-[slide-in_0.15s_ease-out]",children:[e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-2",children:[e.jsx("span",{className:"w-2 h-2 rounded-full bg-cool animate-pulse"}),e.jsx("span",{className:"font-mono text-[10px] text-cool uppercase tracking-wide",children:"Streaming response"})]}),e.jsxs("span",{className:"font-mono text-[10px] text-muted",children:[f.length," chunks"]})]}),e.jsxs("div",{className:`prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
            prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
            prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            max-h-96 overflow-y-auto
          `,children:[e.jsx(E,{remarkPlugins:[B],children:M}),e.jsx("div",{ref:q})]})]}),o&&!a&&e.jsxs("div",{className:"bg-panel border border-line rounded-xl px-5 py-4 space-y-4 animate-[slide-in_0.15s_ease-out]",children:[e.jsxs("div",{className:"flex items-center gap-2 flex-wrap",children:[e.jsx(m,{label:"tier",value:o.routed_to,color:o.routed_to==="frontier"?"danger":o.routed_to==="mid"?"signal":"cool"}),o.intended_tier&&o.intended_tier!==o.routed_to&&e.jsx(m,{label:"intended",value:o.intended_tier,color:"muted"}),o.predicted_tier&&e.jsx(m,{label:"predicted",value:o.predicted_tier,color:"muted"}),o.cache_hit&&e.jsx(m,{label:"cache",value:"hit",color:"cool"}),o.fallback_used&&e.jsx(m,{label:"fallback",value:"yes",color:"danger"}),o.difficulty_score!=null&&e.jsx(m,{label:"difficulty",value:o.difficulty_score.toFixed(2),color:"muted"})]}),e.jsxs("div",{className:"flex items-center gap-4 font-mono text-[11px] text-muted",children:[e.jsxs("span",{children:["$",(o.cost_usd||0).toFixed(4)]}),e.jsxs("span",{children:[(o.latency_ms||0).toFixed(0),"ms"]}),o.tokens_saved_usd>0&&e.jsxs("span",{className:"text-cool",children:["$",o.tokens_saved_usd.toFixed(4)," saved"]})]}),e.jsx("div",{className:"bg-surface rounded-lg border border-line px-4 py-3 max-h-96 overflow-y-auto",children:e.jsx("div",{className:`prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
              prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
              prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            `,children:e.jsx(E,{remarkPlugins:[B],children:o.response||""})})})]}),C&&e.jsxs("div",{className:"space-y-2",children:[e.jsxs("button",{onClick:()=>F(t=>!t),className:"font-mono text-[10px] text-muted hover:text-primary transition-colors flex items-center gap-1",children:[k?"▾":"▸"," Code snippets"]}),k&&e.jsx("div",{className:"animate-[cmd-slide_0.15s_ease-out]",children:e.jsx(X,{query:C,tier:r,streaming:a})})]}),$.length>0&&e.jsxs("div",{className:"space-y-2",children:[e.jsx("h4",{className:"font-mono text-[10px] text-muted uppercase tracking-wide",children:"History"}),e.jsx("div",{className:"space-y-1 max-h-72 overflow-y-auto",children:$.map((t,d)=>e.jsxs("button",{onClick:()=>I(t),className:"w-full text-left px-3 py-2.5 bg-surface hover:bg-panel border border-line hover:border-signal/30 rounded-lg transition-colors group",children:[e.jsxs("div",{className:"flex items-center gap-2 mb-1",children:[e.jsx("span",{className:`font-mono text-[9px] px-1.5 py-0.5 rounded border ${t.tier==="frontier"?"text-danger bg-danger/10 border-danger/30":t.tier==="mid"?"text-signal bg-signal/10 border-signal/30":"text-cool bg-cool/10 border-cool/30"}`,children:t.tier}),t.cache_hit&&e.jsx("span",{className:"font-mono text-[9px] text-cool",children:"cache"}),t.streaming&&e.jsx("span",{className:"font-mono text-[9px] text-muted",children:"stream"}),e.jsxs("span",{className:"font-mono text-[9px] text-muted ml-auto",children:["$",t.cost.toFixed(4)," · ",t.latency_ms.toFixed(0),"ms"]})]}),e.jsx("p",{className:"font-mono text-[11px] text-primary truncate group-hover:text-signal transition-colors",children:t.query})]},d))})]})]})}export{V as default};
