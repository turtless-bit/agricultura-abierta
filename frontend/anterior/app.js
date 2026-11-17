const $ = (s) => document.querySelector(s);
let CAT = null;
let archivo = null;

const pct = (x) => `${Math.round(x * 100)}%`;
const num = (x, d = 2) => Number(x).toLocaleString("es", { maximumFractionDigits: d });
const dinero = (x) => `S/ ${Number(x).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
// Dosis de etiqueta (kg o L por ha) expresada por cada 1.000 m² (g o mL)
const porMil = (dosisHa) => dosisHa * 100;
const subUnidad = (u) => (u === "kg" ? "g" : "mL");
// Envase legible: 0.25 L -> "250 mL", 1 kg -> "1 kg"
const envase = (cant, u) => (cant < 1 ? `${num(cant * 1000, 0)} ${subUnidad(u)}` : `${num(cant)} ${u}`);

function el(tag, attrs = {}, ...hijos) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (e.className = v) : (e[k] = v)));
  hijos.forEach((h) => e.append(h));
  return e;
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail?.[0]?.msg || data.detail || "Error del servidor");
  return data;
}

/* ---------- Pestañas ---------- */
const SECCIONES = ["diagnostico", "calculadora", "enfermedades"];
function mostrarPestana(id) {
  SECCIONES.forEach((s) => $("#" + s).classList.toggle("oculto", s !== id));
  document.querySelectorAll(".pestana").forEach((b) => b.classList.toggle("activa", b.dataset.tab === id));
  const hero = $(".hero");
  const tope = hero.offsetTop + hero.offsetHeight - $(".barra").offsetHeight;
  window.scrollTo({ top: tope, behavior: "smooth" });
}
document.querySelectorAll("[data-tab]").forEach((b) =>
  b.addEventListener("click", (e) => { e.preventDefault(); mostrarPestana(b.dataset.tab); })
);

/* ---------- Inicio ---------- */
async function iniciar() {
  CAT = await api("/api/catalogo");
  const cat = CAT;
  llenarEnfermedades();
  pintarListaEnfermedades();
}

function enfermedades() {
  return CAT.cultivos[$("#cultivo").value].enfermedades;
}

function llenarEnfermedades(seleccion) {
  const sel = $("#c-enfermedad");
  sel.innerHTML = "";
  Object.entries(enfermedades()).forEach(([id, e]) => sel.append(el("option", { value: id, textContent: e.nombre })));
  if (seleccion) sel.value = seleccion;
  llenarProductos();
}

function llenarProductos(seleccion) {
  const enf = enfermedades()[$("#c-enfermedad").value];
  const sel = $("#c-producto");
  sel.innerHTML = "";
  enf.productos.forEach((id) => sel.append(el("option", { value: id, textContent: CAT.productos[id].nombre })));
  if (seleccion) sel.value = seleccion;
  actualizarPrecio();
}

function actualizarPrecio() {
  const p = CAT.productos[$("#c-producto").value];
  if (!p) return;
  $("#c-precio").value = p.precio_presentacion;
  $("#c-precio-txt").textContent = `Precio por envase de ${envase(p.presentacion, p.unidad)} (S/)`;
  $("#c-aplicaciones").placeholder = `Máx. ${p.aplicaciones_max_ciclo} por cosecha`;
}

function pintarListaEnfermedades() {
  const cont = $("#lista-enf");
  cont.innerHTML = "";
  Object.values(enfermedades())
    .filter((e) => e.agente !== "—")
    .forEach((e) =>
      cont.append(
        el("div", { class: "enf" },
          el("h3", { textContent: e.nombre }),
          el("p", { class: "tenue", textContent: e.agente }),
          el("p", { textContent: e.sintomas }),
          el("p", { innerHTML: `<strong>Condiciones:</strong> ${e.condiciones}` }))
      )
    );
}

/* ---------- Foto ---------- */
function elegirArchivo(f) {
  if (!f || !f.type.startsWith("image/")) return;
  archivo = f;
  const img = $("#vista");
  img.src = URL.createObjectURL(f);
  img.classList.remove("oculto");
  $("#zona-texto").classList.add("oculto");
  $("#btn-diagnosticar").disabled = false;
}

$("#foto").addEventListener("change", (e) => elegirArchivo(e.target.files[0]));
const zona = $("#zona-foto");
["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("arrastre"); }));
["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("arrastre"); }));
zona.addEventListener("drop", (e) => elegirArchivo(e.dataTransfer.files[0]));

$("#btn-diagnosticar").addEventListener("click", async () => {
  const btn = $("#btn-diagnosticar");
  btn.disabled = true;
  btn.textContent = "Analizando…";
  btn.classList.add("cargando");
  try {
    const fd = new FormData();
    fd.append("foto", archivo);
    const r = await api(`/api/diagnosticar?cultivo=${$("#cultivo").value}`, { method: "POST", body: fd });
    mostrarResultado(r);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analizar foto";
    btn.classList.remove("cargando");
  }
});

function mostrarResultado(r) {
  const e = r.enfermedad;
  $("#r-nombre").textContent = e.nombre;
  $("#r-agente").textContent = e.agente;
  $("#r-conf").textContent = pct(r.confianza);
  $("#r-sintomas").textContent = e.sintomas;

  const probs = $("#r-probs");
  probs.innerHTML = "";
  Object.entries(r.probabilidades)
    .sort((a, b) => b[1] - a[1])
    .forEach(([id, p]) => {
      const barra = el("div", { class: "barra-p" }, el("div"));
      barra.firstChild.style.width = pct(p);
      probs.append(el("div", { class: "prob" }, el("span", { textContent: enfermedades()[id]?.nombre || id }), barra, el("span", { textContent: pct(p) })));
    });

  const ul = $("#r-manejo");
  ul.innerHTML = "";
  e.manejo_cultural.forEach((m) => ul.append(el("li", { textContent: m })));

  const cont = $("#r-productos");
  cont.innerHTML = "";
  r.productos.forEach((p) => {
    const btn = el("button", { class: "btn btn-sec", textContent: "Calcular dosis y costo →" });
    btn.addEventListener("click", () => {
      llenarEnfermedades(e.id);
      llenarProductos(p.id);
      mostrarPestana("calculadora");
    });
    cont.append(
      el("div", { class: "producto" },
        el("h5", { textContent: p.nombre }),
        el("small", { textContent: `${p.tipo} · FRAC ${p.frac}` }),
        el("span", { textContent: `Dosis: ${num(porMil(p.dosis_min_ha), 0)}–${num(porMil(p.dosis_max_ha), 0)} ${subUnidad(p.unidad)} por 1.000 m²` }),
        el("span", { textContent: `Cada ${p.intervalo_dias} días · carencia ${p.carencia_dias} días` }),
        btn)
    );
  });

  $("#resultado").classList.remove("oculto");
  $("#resultado").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Calculadora ---------- */
$("#c-enfermedad").addEventListener("change", () => llenarProductos());
$("#c-producto").addEventListener("change", actualizarPrecio);
$("#cultivo").addEventListener("change", () => { llenarEnfermedades(); pintarListaEnfermedades(); });
document.querySelectorAll("input[name=modo-area]").forEach((r) =>
  r.addEventListener("change", () => {
    const lados = r.value === "lados" && r.checked;
    $("#area-lados").classList.toggle("oculto", !lados);
    $("#area-total").classList.toggle("oculto", lados);
  })
);

$("#form-calc").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  let area, unidad;
  if (document.querySelector("input[name=modo-area]:checked").value === "lados") {
    area = parseFloat($("#c-largo").value) * parseFloat($("#c-ancho").value);
    unidad = "m2";
  } else {
    area = parseFloat($("#c-area").value);
    unidad = "m2";
  }
  if (!(area > 0)) return alert("Ingrese las medidas de la plantación.");

  const cuerpo = {
    producto_id: $("#c-producto").value,
    area, unidad,
    capacidad_tanque_l: parseFloat($("#c-tanque").value) || 20,
    nivel_dosis: $("#c-dosis").value,
    aplicaciones: parseInt($("#c-aplicaciones").value) || null,
    precio_presentacion: $("#c-precio").value === "" ? null : parseFloat($("#c-precio").value),
  };
  try {
    const r = await api("/api/calcular", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo),
    });
    mostrarCalculo(r);
  } catch (e) {
    alert(e.message);
  }
});

function mostrarCalculo(r) {
  const u = r.unidad_producto;
  $("#k-tanque").textContent = `${num(r.producto_por_tanque, 0)} ${r.unidad_por_tanque}`;
  $("#k-tanques").textContent = num(r.tanques_por_aplicacion, 0);
  $("#k-comprar").textContent = `${r.envases_a_comprar} × ${envase(r.presentacion, u)}`;
  $("#k-costo").textContent = dinero(r.costo_total);

  const filas = [
    ["Producto", r.producto.nombre],
    ["Área tratada", `${num(r.area_ha * 10000, 1)} m²`],
    ["Dosis usada", `${num(porMil(r.dosis_ha), 0)} ${subUnidad(u)} por 1.000 m²`],
    ["Producto por aplicación", `${num(r.producto_por_aplicacion, 3)} ${u}`],
    ["Agua por aplicación", `${num(r.agua_por_aplicacion_l, 1)} L`],
    ["Aplicaciones por cosecha", `${r.aplicaciones} (cada ${r.intervalo_dias} días)`],
    ["Producto total necesario", `${num(r.producto_total, 3)} ${u}`],
    ["Costo por aplicación", dinero(r.costo_por_aplicacion)],
    ["Costo total (envases completos)", dinero(r.costo_total)],
  ];
  const tb = $("#calc-tabla");
  tb.innerHTML = "";
  filas.forEach(([a, b]) => tb.append(el("tr", {}, el("td", { textContent: a }), el("td", { textContent: b }))));

  const ol = $("#calc-pasos");
  ol.innerHTML = "";
  r.pasos.forEach((p) => ol.append(el("li", { textContent: p })));

  $("#calc-res").classList.remove("oculto");
}

iniciar().catch((e) => alert("No se pudo conectar con el servidor: " + e.message));
