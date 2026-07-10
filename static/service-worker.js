const CACHE = "sistema-experto-v18";
const PAGES = ["/login", "/sensor-input"];

// ── IndexedDB: pending mutations + page cache ──
const DB_NAME = "sensor-input-db";
const STORE_NAME = "pending";
const PAGE_STORE = "pages";

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 3);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME))
        db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
      if (!db.objectStoreNames.contains(PAGE_STORE))
        db.createObjectStore(PAGE_STORE, { keyPath: "path" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function cachePageHTML(path, html) {
  try {
    const db = await openDB();
    const tx = db.transaction(PAGE_STORE, "readwrite");
    tx.objectStore(PAGE_STORE).put({ path: path, html: html });
    await new Promise((r) => { tx.oncomplete = r; });
  } catch (e) {}
}

async function getPageHTML(path) {
  try {
    const db = await openDB();
    const tx = db.transaction(PAGE_STORE, "readonly");
    const r = tx.objectStore(PAGE_STORE).get(path);
    const result = await new Promise((resolve) => { r.onsuccess = () => resolve(r.result); });
    return result ? result.html : null;
  } catch (e) {
    return null;
  }
}

async function clearPageCache() {
  try {
    const db = await openDB();
    const tx = db.transaction(PAGE_STORE, "readwrite");
    tx.objectStore(PAGE_STORE).clear();
    await new Promise((r) => { tx.oncomplete = r; });
  } catch (e) {}
}

async function replayQueue() {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, "readonly");
  const all = tx.objectStore(STORE_NAME).getAll();
  const items = await new Promise((r) => { all.onsuccess = () => r(all.result || []); });
  if (items.length === 0) return;
  const successIds = [];
  for (const item of items) {
    try {
      const r = await fetch("/api/sensor-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          asset: item.asset,
          sensor: item.sensor,
          value: item.value,
          captured_at: item._capturedAt || item.captured_at || Date.now(),
          sync_uuid: item._sync_uuid || item.sync_uuid || crypto.randomUUID(),
        }),
      });
      if (r.ok) successIds.push(item.id);
    } catch (e) {}
  }
  if (successIds.length > 0) {
    const delTx = db.transaction(STORE_NAME, "readwrite");
    for (const id of successIds) delTx.objectStore(STORE_NAME).delete(id);
    await new Promise((r) => { delTx.oncomplete = r; });
  }
  const clients = await self.clients.matchAll();
  for (const client of clients) {
    client.postMessage({ action: "sync-complete" });
    try { client.postMessage({ action: "pending-updated" }); } catch(e) {}
  }
}

function serveWithPending(html) {
  var script = '<script>' +
    '(function(){' +
    'var I=null,D="sensor-input-db",S="pending";' +
    'function O(){return new Promise(function(r,j){var q=indexedDB.open(D,3);q.onupgradeneeded=function(e){var d=e.target.result;if(!d.objectStoreNames.contains(S))d.createObjectStore(S,{keyPath:"id",autoIncrement:true});if(!d.objectStoreNames.contains("pages"))d.createObjectStore("pages",{keyPath:"path"})};q.onsuccess=function(){r(q.result)};q.onerror=function(){j(q.error)}})}' +
    'async function show(){try{var db=await O();var c=db.transaction(S,"readonly").objectStore(S).count();var n=await new Promise(function(s){c.onsuccess=function(){s(c.result)}});if(!n){var e=document.getElementById("_pe");if(e)e.style.display="none";return}var a=db.transaction(S,"readonly").objectStore(S).getAll();var items=await new Promise(function(s){a.onsuccess=function(){s(a.result||[])}});var e=document.getElementById("_pe");if(!e){e=document.createElement("div");e.id="_pe";var h=document.createElement("div");h.style.cssText="font-size:0.85rem;font-weight:600;color:#fef08a;cursor:pointer";h.textContent=" pendiente(s) por sincronizar ▼";var l=document.createElement("div");l.style.display="none";l.style.fontSize="0.75rem";l.style.color="#94a3b8";h.onclick=function(){l.style.display=l.style.display==="none"?"block":"none";h.textContent=n+" pendiente(s) por sincronizar "+(l.style.display==="none"?"▼":"▲")};e.style.cssText="margin-top:1rem;border-top:1px solid #334155;padding-top:0.75rem";e.appendChild(h);e.appendChild(l);var ins=document.querySelector(".form-section")||document.querySelector("#lastReadings")||document.querySelector("body");if(ins&&ins.parentNode)ins.parentNode.insertBefore(e,ins.nextSibling)}e.style.display="block";var h=e.children[0],l=e.children[1];h.textContent=n+" pendiente(s) por sincronizar "+(l.style.display==="none"?"▼":"▲");l.innerHTML=items.map(function(i){return\'<div style="padding:0.15rem 0">\'+(i.asset||"")+" › "+(i.sensor||"")+": <strong>"+i.value+\'</strong> <span style="color:#64748b">\'+new Date(i._capturedAt||i.captured_at).toLocaleString("es-VE",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",timeZone:"America/Caracas"})+"</span></div>"}).join("")}catch(e){}}' +
    'if(document.readyState==="complete"||document.readyState==="interactive"){show();I=setInterval(show,1000)}else document.addEventListener("DOMContentLoaded",function(){show();I=setInterval(show,1000)})' +
    '})()' +
    '</script>';
  return new Response(html.replace("</body>", script + "</body>"), {
    status: 200,
    headers: { "Content-Type": "text/html;charset=utf-8" },
  });
}

function inject(htmlOrResponse) {
  if (htmlOrResponse instanceof Response) {
    return htmlOrResponse.text().then(function(text) {
      return serveWithPending(text);
    });
  }
  return serveWithPending(htmlOrResponse);
}

function loginPage() {
  return new Response('<!DOCTYPE html>\n<html lang="es"><head><meta charset="UTF-8">\n<title>Iniciar sesión</title>\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<style>\n*{margin:0;padding:0;box-sizing:border-box}\nbody{font-family:\'Segoe UI\',Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:1rem;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;text-align:center}\nh1{font-size:1.3rem;margin-bottom:0.5rem}\n.sub{color:#94a3b8;font-size:0.85rem;margin-bottom:1.5rem}\n.login-card{background:#1e293b;border-radius:12px;padding:2rem;width:100%;max-width:320px}\n.info{color:#fef08a;font-size:0.8rem;margin-top:1rem;padding:0.5rem;background:#1e293b;border-radius:8px;line-height:1.4}\na{color:#93c5fd;font-size:0.8rem;margin-top:1rem;display:inline-block}\n</style>\n</head><body>\n<div class="login-card">\n<h1>🔐 Iniciar sesión</h1>\n<p class="sub">Sin conexión al servidor</p>\n<div class="info">Conéctate a internet para iniciar sesión y acceder al sistema</div>\n<a href="/login">Reintentar</a>\n</div>\n</body></html>', {
    status: 200,
    headers: { "Content-Type": "text/html;charset=utf-8" },
  });
}

// ── Install: pre-cache login + sensor-input ──
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      Promise.allSettled(
        PAGES.map((url) =>
          fetch(url, { credentials: "same-origin" }).then((r) => {
            if (r.ok && new URL(r.url).pathname === url) cache.put(url, r);
          }).catch(() => {})
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  event.waitUntil(clients.claim());
  event.waitUntil(replayQueue());
});

// ── Messages ──
self.addEventListener("message", (event) => {
  const data = event.data;
  if (!data) return;
  if (data.action === "replay-sync") {
    replayQueue();
  }
  if (data.action === "auth-login") {
    event.waitUntil(
      Promise.all([
        caches.open(CACHE).then(async (cache) => {
          const pages = ["/sensor-input", "/login"];
          for (const page of pages) {
            try {
              const res = await fetch(page, { credentials: "same-origin" });
              if (res.ok && new URL(res.url).pathname === page) {
                await cache.put(page, res);
                await cachePageHTML(page, await res.clone().text());
              }
            } catch (e) {}
          }
        }),
        replayQueue(),
      ])
    );
  }
  if (data.action === "auth-logout" || data.action === "clear-cache") {
    event.waitUntil(
      Promise.all([
        clearPageCache(),
        caches.open(CACHE).then((cache) =>
          cache.keys().then((keys) =>
            Promise.all(
              keys.map((key) => {
                var url = new URL(key.url);
                if (url.pathname === "/login" || url.pathname.startsWith("/static/")) {
                  return Promise.resolve();
                }
                return cache.delete(key);
              })
            )
          )
        ),
      ])
    );
  }
});

// ── Fetch ──
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  const path = url.pathname;

  // CDN: cache-first
  if (url.hostname !== self.location.hostname) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetched = fetch(request).then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then((cache) => cache.put(request, clone));
          }
          return res;
        });
        return cached || fetched;
      }).catch(() => fetch(request))
    );
    return;
  }

  // API: network-first
  if (path.startsWith("/api/")) {
    if (request.method !== "GET") {
      event.respondWith(
        fetch(request).catch(() => new Response(JSON.stringify({ error: "offline" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }))
      );
      return;
    }
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then((cache) => cache.put(request, clone));
          }
          return res;
        })
        .catch(() => new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } }))
    );
    return;
  }

  // Navigation: network-first for /login and /sensor-input
  if (PAGES.indexOf(path) !== -1) {
    event.respondWith(
      fetch(request, { credentials: "same-origin" }).then(function(res) {
        if (res.ok && res.type === "basic") {
          var resUrl = new URL(res.url);
          if (resUrl.pathname === path) {
            var clone = res.clone();
            caches.open(CACHE).then(function(cache) { cache.put(request, clone); });
          }
        }
        return res;
      }).catch(function() {
        return caches.match(request).then(function(cached) {
          if (cached) return inject(cached);
          return getPageHTML(path).then(function(html) {
            if (html) return serveWithPending(html);
            return loginPage();
          });
        });
      })
    );
    return;
  }

  // Other navigation: network-only, no offline fallback
  event.respondWith(
    fetch(request, { credentials: "same-origin" }).then(function(res) {
      return res;
    }).catch(function() {
      return caches.match("/login").then(function(cachedLogin) {
        if (cachedLogin) return cachedLogin;
        return loginPage();
      });
    })
  );
});

// ── Replay queue on online ──
self.addEventListener("online", () => {
  setTimeout(replayQueue, 1000);
});

// Periodic queue check (every 30s)
setInterval(function() {
  if (navigator.onLine !== false) {
    replayQueue();
  }
}, 30000);

// ── Push notifications ──
self.addEventListener("push", (event) => {
  let data = { title: "Condominium Expert", body: "Alerta del sistema" };
  try {
    if (event.data) data = JSON.parse(event.data.text());
  } catch (e) {}
  const options = {
    body: data.body,
    icon: "/static/sensor-icon.svg",
    badge: "/static/sensor-icon.svg",
    tag: data.tag || "default",
    data: { url: data.url || "/" },
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url === url && "focus" in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});
