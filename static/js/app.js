const $ = (id) => document.getElementById(id);
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
let currentQuery = "ventas";
const money = (n) => new Intl.NumberFormat("es-CO", {style:"currency", currency:"COP", maximumFractionDigits:0}).format(Number(n || 0));
const number = (n) => new Intl.NumberFormat("es-CO").format(Number(n || 0));
const safe = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function showError(message) { $("error-area").hidden = false; $("error-area").textContent = message; }
function clearError() { $("error-area").hidden = true; $("error-area").textContent = ""; }
function summary(items) { $("summary-row").innerHTML = items.map(x => `<div class="summary-item"><div class="summary-label">${safe(x.label)}</div><div class="summary-value">${safe(x.value)}</div><div class="summary-note">${safe(x.note || "")}</div></div>`).join(""); }
function table(headers, rows) {
  if (!rows.length) return `<div class="empty">No hay resultados para mostrar. Comprueba que las tablas de DynamoDB tengan datos.</div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th class="${h.right?'numeric':''}">${safe(h.label)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((cell,i)=>`<td class="${headers[i]?.right?'numeric':''}">${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
async function getJSON(url, options={}) {
  const response = await fetch(url, {
    ...options,
    headers: {...(options.headers || {}), "X-CSRFToken": csrfToken}
  });
  const data = await response.json().catch(()=>({error:"El servidor devolvió una respuesta no válida."}));
  if (!response.ok) throw new Error(data.error || `Error HTTP ${response.status}`);
  return data;
}
function getClientFilters() {
  const params = new URLSearchParams();
  for (const [key, value] of new FormData($("reto-search-form")).entries()) {
    const normalized = String(value).trim();
    if (normalized) params.set(key, normalized);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}
async function loadQuery(query=currentQuery) {
  currentQuery = query; clearError();
  document.querySelectorAll(".query-card").forEach(b=>b.classList.toggle("active", b.dataset.query===query));
  $("results-area").innerHTML = `<div class="loading"><span class="spinner"></span> Consultando DynamoDB...</div>`;
  const config = {
    ventas: {url:"/api/ventas-por-ciudad",title:"Ventas por ciudad",subtitle:"Resumen de ventas agrupadas por ciudad del cliente."},
    ingresos: {url:"/api/ingresos-por-categoria",title:"Ingresos por categoría",subtitle:"Suma ventas → productos (precio × cantidad) agrupado por categoría."},
    clientes: {url:"/api/clientes-por-categoria",title:"Clientes por categoría",subtitle:"Clientes únicos relacionados con cada categoría comprada."}
  }[query];
  $("hero-title").textContent=config.title;
  $("hero-subtitle").textContent=config.subtitle;
  $("results-title").textContent=config.title; $("results-subtitle").textContent=config.subtitle;
  try {
    const data=await getJSON(config.url+getClientFilters());
    if(query==="ventas"){
      const results=data.results||[];
      summary([{label:"VENTAS REGISTRADAS",value:number(data.totalVentas),note:"De clientes que coinciden"},{label:"CLIENTES",value:number(data.matchedClients),note:"Coinciden con los filtros"},{label:"INGRESOS ESTIMADOS",value:money(results.reduce((s,r)=>s+Number(r.ingresos||0),0)),note:"Precio × cantidad"}]);
      $("results-area").innerHTML=table([{label:"Ciudad"},{label:"N.º de ventas",right:true},{label:"Unidades",right:true},{label:"Ingresos estimados",right:true}],results.map(r=>[`<strong>${safe(r.ciudad)}</strong>`,number(r.cantidadVentas),number(r.unidades),money(r.ingresos)]));
    } else if(query==="ingresos"){
      const results=data.results||[];
      summary([{label:"INGRESOS TOTALES",value:money(data.totalIngresos),note:"De clientes que coinciden"},{label:"CLIENTES",value:number(data.matchedClients),note:"Coinciden con los filtros"},{label:"UNIDADES VENDIDAS",value:number(results.reduce((s,r)=>s+Number(r.unidades||0),0)),note:"Total de unidades"}]);
      $("results-area").innerHTML=table([{label:"Categoría"},{label:"Unidades",right:true},{label:"Ingresos",right:true}],results.map(r=>[`<span class="pill">${safe(r.categoria)}</span>`,number(r.unidades),money(r.ingresos)]));
    } else {
      const groups=data.results||[];
      const rows=groups.flatMap(g=>g.clientes.map(c=>[safe(c.nombre),safe(c.clienteId),safe(c.ciudad),safe(c.correo),`<span class="pill">${safe(g.categoria)}</span>`]));
      summary([{label:"CATEGORÍAS",value:number(groups.length),note:"Con clientes que coinciden"},{label:"CLIENTES",value:number(data.matchedClients),note:"Coinciden con los filtros"},{label:"RELACIONES CLIENTE-CATEGORÍA",value:number(rows.length),note:"Sin repetir por categoría"}]);
      $("results-area").innerHTML=table([{label:"Cliente"},{label:"ID"},{label:"Ciudad"},{label:"Correo"},{label:"Categoría"}],rows);
    }
  } catch(e) {
    summary([{label:"ESTADO",value:"Sin conexión",note:"Revisa servidor y permisos AWS"},{label:"CONSULTA",value:config.title,note:"No fue posible completarla"},{label:"SIGUIENTE PASO",value:"Revisar",note:"Ver mensaje debajo"}]);
    $("results-area").innerHTML="";
    showError(e.message);
  }
}
document.querySelectorAll(".query-card").forEach(b=>b.addEventListener("click",()=>void loadQuery(b.dataset.query)));
$("refresh-button").addEventListener("click",()=>void loadQuery());
$("reto-search-form").addEventListener("submit",e=>{e.preventDefault();void loadQuery();});
function renderClientResult(box, client) {
  box.replaceChildren();
  const strong = document.createElement("strong");
  strong.textContent = client.nombre || "";
  box.append(strong, document.createElement("br"));
  box.append("ID: ", client.clienteId || "", document.createElement("br"));
  box.append("Ciudad: ", client.ciudad || "", document.createElement("br"));
  box.append("Correo: ", client.correo || "");
}
$("reto-search-form").addEventListener("reset",()=>setTimeout(()=>void loadQuery(),0));
$("search-form").addEventListener("submit",async e=>{
  e.preventDefault(); const id=$("client-id").value.trim(); const box=$("client-result"); box.hidden=false;box.className="mini-result";box.textContent="Buscando...";
  try{const data=await getJSON(`/api/clientes/${encodeURIComponent(id)}`);box.className="mini-result success";renderClientResult(box,data.cliente);}
  catch(err){box.className="mini-result failure";box.textContent=err.message;}
});
$("new-client-form").addEventListener("submit",async e=>{
  e.preventDefault();const form=e.currentTarget;const box=$("new-client-result");box.hidden=false;box.className="mini-result";box.textContent="Guardando...";
  const body=Object.fromEntries(new FormData(form).entries());
  try{const data=await getJSON("/api/clientes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});box.className="mini-result success";box.textContent=`${data.message} ID asignado: ${data.cliente.clienteId}`;form.reset();}
  catch(err){box.className="mini-result failure";box.textContent=err.message;}
});
$("upload-form").addEventListener("submit",async e=>{
  e.preventDefault();const files=$("json-file").files;const box=$("upload-result");box.hidden=false;box.className="mini-result";box.textContent="Insertando datos en DynamoDB...";
  const fd=new FormData();for(const file of files)fd.append("archivos",file);
  try{
    const data=await getJSON("/api/subir-archivo",{method:"POST",body:fd});
    const details=(data.files||[]).map(file=>`${file.filename}: ${file.inserted} insertados, ${file.skipped} ya existían`).join(" · ");
    box.className="mini-result success";
    box.textContent=`${data.message} Total insertados: ${data.inserted}; omitidos: ${data.skipped}.${details?` ${details}`:""}`;
    $("upload-form").reset();
    if(data.inserted)void loadQuery();
  }
  catch(err){box.className="mini-result failure";box.textContent=err.message;}
});
void getJSON("/api/health").then(data=>{$("connection-label").textContent="Panel listo · "+data.region;$("footer-region").textContent="AWS "+data.region;}).catch(()=>{$("connection-label").textContent="Servidor pendiente";});
void loadQuery("ventas");
