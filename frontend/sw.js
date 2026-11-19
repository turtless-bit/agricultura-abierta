// Service worker de PapaQhawaq: guarda la página, los modelos de IA y las imágenes en el celular
// para que el diagnóstico y las recomendaciones funcionen sin internet.
// El servidor reemplaza __VERSION__ por una huella de los archivos: si cambian los modelos o la página,
// cambia la versión, el navegador instala este archivo de nuevo y se borra la caché vieja.
const CACHE = "papaqhawaq-__VERSION__";
const INICIALES = [
  "/",
  "/static/manifest.webmanifest",
  "/static/iconos/icono-192.png",
  "/static/iconos/icono-512.png",
  "/static/vendor/litert/litert.mjs",
  "/static/qu.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(INICIALES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k.startsWith("papaqhawaq-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// La página manda la lista de imágenes y documentos de los productos para guardarlos de una vez
self.addEventListener("message", (e) => {
  const urls = e.data && e.data.guardar;
  if (!Array.isArray(urls)) return;
  e.waitUntil(caches.open(CACHE).then((c) =>
    Promise.all(urls.map((u) => c.match(u).then((ya) => ya || c.add(u).catch(() => {}))))
  ));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;               // el diagnóstico por servidor (POST) va directo
  const url = new URL(req.url);
  if (url.origin === location.origin && url.pathname.startsWith("/api/")) return;  // clima: siempre en vivo

  // La página: primero internet (para tener la última versión); sin conexión, la guardada
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((r) => { const copia = r.clone(); caches.open(CACHE).then((c) => c.put("/", copia)); return r; })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Modelos, motor de IA, imágenes y fuentes: primero lo guardado; si no está, se descarga y se guarda
  e.respondWith(
    caches.match(req).then((guardado) => guardado || fetch(req).then((r) => {
      if (r.ok || r.type === "opaque") {
        const copia = r.clone();
        caches.open(CACHE).then((c) => c.put(req, copia));
      }
      return r;
    }))
  );
});
