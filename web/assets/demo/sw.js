// Scope is this demo directory. Never cache workbench API, models or manuals.
const CACHE='vault-demo-v2.1.0-r2';
const FILES=['./index.html','./app.js','./model.js','./style.css','./manifest.webmanifest','./icon.svg','../builder-stage.js','../palette.json','../vendor/three.module.js','../vendor/OrbitControls.js','../vendor/THREE-LICENSE.txt'];
const urls=FILES.map(p=>new URL(p,self.location.href).href);
self.addEventListener('install',event=>event.waitUntil((async()=>{
  const existed=(await caches.keys()).includes(CACHE),cache=await caches.open(CACHE);
  try{await cache.addAll(urls.map(url=>new Request(url,{cache:'reload'})));}catch(e){if(!existed)await caches.delete(CACHE);throw e;}
  await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  for(const key of await caches.keys())if(key.startsWith('vault-demo-')&&key!==CACHE)await caches.delete(key);
  await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  const nav=event.request.mode==='navigate'&&url.origin===self.location.origin&&[new URL('./',self.location.href).pathname,new URL('index.html',self.location.href).pathname].includes(url.pathname);
  const target=nav?new URL('index.html',self.location.href).href:event.request.url;
  if(!urls.includes(target))return;
  event.respondWith((async()=>{const cache=await caches.open(CACHE);return await cache.match(target)||fetch(event.request);})());
});
