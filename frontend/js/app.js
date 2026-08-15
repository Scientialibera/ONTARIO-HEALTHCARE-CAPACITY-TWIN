const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("en-CA");
const fmtCompact = new Intl.NumberFormat("en-CA", {notation:"compact", maximumFractionDigits:1});

let state = null;
let baseline = null;
let selectedHospitalId = null;
let proposed = null;
let placeMode = false;
let activeLayer = "stress";
let hospitalMarkers = [];
let regionMarkers = [];
let proposedMarker = null;

const map = L.map("map", {zoomControl:true, minZoom:4}).setView([44.05,-79.5], 7);
const tiles = {
  dark: L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    maxZoom:19, attribution:"&copy; OpenStreetMap &copy; CARTO"
  }),
  aerial: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom:19, attribution:"Tiles &copy; Esri"
  })
};
tiles.dark.addTo(map);

function toast(text){
  const t=$("toast"); t.textContent=text; t.classList.add("show");
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.classList.remove("show"),2400);
}
function number(n){return fmt.format(Math.round(n||0))}
function compact(n){return fmtCompact.format(n||0)}
function pct(n,d=1){return `${Number(n||0).toFixed(d)}%`}
function minutes(n){return `${Number(n||0).toFixed(1)} min`}

function requestParams(){
  return {
    year:Number(document.querySelector(".year-switch button.active").dataset.year),
    access_minutes:Number($("accessMinutes").value),
    ed_visits_per_capita:Number($("edRate").value),
    beds:Number($("bedsInput").value),
    annual_ed_capacity:Number($("edCapacityInput").value)
  };
}
async function getState(){
  const p=requestParams();
  const q=new URLSearchParams({year:p.year,access_minutes:p.access_minutes,ed_visits_per_capita:p.ed_visits_per_capita});
  const res=await fetch(`/api/state?${q}`); if(!res.ok)throw new Error("state request failed");
  baseline=await res.json(); state=baseline; proposed=null; render();
}
async function runScenario(lat,lon){
  const p=requestParams();
  const res=await fetch("/api/scenario",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({...p,lat,lon})});
  if(!res.ok)throw new Error("scenario request failed");
  state=await res.json(); proposed={lat,lon}; render(); showScenarioDelta();
}
async function optimize(){
  const p=requestParams(); $("optimizeButton").textContent="Scoring Ontario candidates…"; $("optimizeButton").disabled=true;
  try{
    const res=await fetch("/api/optimize",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({...p,objective:$("objective").value})});
    const data=await res.json(); renderRecommendations(data.recommendations);
    if(data.recommendations[0]){
      const top=data.recommendations[0];
      map.flyTo([top.lat,top.lon],8,{duration:.8});
      toast(`Top ${$("objective").selectedOptions[0].text}: ${top.name}`);
    }
  }finally{$("optimizeButton").textContent="Find best candidate sites";$("optimizeButton").disabled=false;}
}
function renderRecommendations(rows){
  const el=$("recommendationList"); el.innerHTML="";
  rows.forEach((r,i)=>{
    const d=document.createElement("button"); d.className="reco-card";
    const improvement=r.delta.coverage_pct;
    d.innerHTML=`<i>${i+1}</i><div><b>${r.name}</b><span>Δ coverage ${improvement>=0?"+":""}${improvement.toFixed(1)} pp · avg ${r.metrics.avg_nearest_minutes.toFixed(1)} min</span></div><strong>${Math.round(r.metrics.proposed_ed_visits_shifted/1000)}k</strong>`;
    d.addEventListener("click",()=>runScenario(r.lat,r.lon));
    el.appendChild(d);
  });
}
function loadColor(ratio){
  if(ratio>=1.05)return "#ff5c6c"; if(ratio>=.92)return "#ff8b47"; if(ratio>=.80)return "#f0bc4d"; return "#59d88b";
}
function accessColor(score, min,max){
  const t=(score-min)/Math.max(max-min,.001);
  return t>.66?"#4be0c2":t>.33?"#36d6ff":"#5c79ff";
}
function renderMap(){
  hospitalMarkers.forEach(m=>map.removeLayer(m)); hospitalMarkers=[];
  regionMarkers.forEach(m=>map.removeLayer(m)); regionMarkers=[];
  if(proposedMarker){map.removeLayer(proposedMarker);proposedMarker=null}

  const accessVals=state.regions.map(r=>r.accessibility_score);
  const amin=Math.min(...accessVals), amax=Math.max(...accessVals);

  state.regions.forEach(r=>{
    let intensity, color;
    if(activeLayer==="demand"){intensity=Math.sqrt(r.population)/42;color="#398bff";}
    else if(activeLayer==="access"){intensity=11+28*(r.accessibility_score-amin)/Math.max(amax-amin,.001);color=accessColor(r.accessibility_score,amin,amax);}
    else{
      const nearby=state.facilities.filter(f=>distanceApprox(r,f)<140).sort((a,b)=>distanceApprox(r,a)-distanceApprox(r,b))[0];
      const ratio=nearby?nearby.load_ratio:.7; intensity=10+Math.min(32,Math.max(0,(ratio-.55)*60));color=loadColor(ratio);
    }
    const cm=L.circleMarker([r.lat,r.lon],{radius:Math.max(8,Math.min(35,intensity)),color,weight:1,fillColor:color,fillOpacity:.13,opacity:.7})
      .bindTooltip(`<b>${r.name}</b><br>${number(r.population)} people · ${minutes(r.nearest_minutes)} nearest access<br>E2SFCA ${r.accessibility_score.toFixed(0)}`,{direction:"top"});
    cm.addTo(map); regionMarkers.push(cm);
  });

  state.facilities.forEach(f=>{
    const icon=L.divIcon({className:"",html:`<div class="hospital-marker ${f.proposed?"proposed":""}">+</div>`,iconSize:f.proposed?[28,28]:[20,20],iconAnchor:f.proposed?[14,14]:[10,10]});
    const marker=L.marker([f.lat,f.lon],{icon,zIndexOffset:f.proposed?1000:300}).addTo(map);
    marker.bindTooltip(`<b>${f.name}</b><br>${pct(f.load_ratio*100)} modelled ED load · ${number(f.assigned_ed_visits)} assigned visits`,{direction:"top"});
    marker.on("click",()=>{selectedHospitalId=f.id;renderHospital();});
    hospitalMarkers.push(marker);
    if(f.proposed)proposedMarker=marker;
  });
}
function distanceApprox(a,b){
  const dx=(a.lon-b.lon)*80,dy=(a.lat-b.lat)*111;return Math.sqrt(dx*dx+dy*dy)
}
function renderMetrics(){
  const m=state.metrics;
  $("metricPopulation").textContent=compact(m.population);
  $("metricYear").textContent=`${state.year} planning year`;
  $("metricCoverage").textContent=pct(m.coverage_pct);
  $("metricCoverageSub").textContent=`within ${state.access_minutes} minutes`;
  $("metricTravel").textContent=minutes(m.avg_nearest_minutes);
  $("metricOverloaded").textContent=String(m.overloaded_facilities);
  $("metricEquity").textContent=m.access_equity_cv.toFixed(2);
  $("metricShifted").textContent=m.proposed_ed_visits_shifted?compact(m.proposed_ed_visits_shifted):"—";
  $("systemDemand").textContent=compact(m.annual_ed_demand);
  const pressure=Math.min(100,(m.overloaded_facilities/Math.max(1,state.facilities.length))*180+25);
  $("systemBar").style.width=`${pressure}%`;
  $("systemNarrative").textContent=`${pct(m.coverage_pct)} of modelled population is within the ${state.access_minutes}-minute access target. ${m.overloaded_facilities} hospital sites exceed their public-POC ED planning capacity under the gravity assignment.`;
}
function populateHospitalSelect(){
  const s=$("hospitalSelect"); const current=selectedHospitalId;
  s.innerHTML="";
  state.facilities.forEach(f=>{const o=document.createElement("option");o.value=f.id;o.textContent=f.proposed?`★ ${f.name}`:f.name;s.appendChild(o)});
  selectedHospitalId = state.facilities.some(f=>f.id===current)?current:(state.facilities.find(f=>f.proposed)?.id||state.facilities[0]?.id);
  if(selectedHospitalId)s.value=selectedHospitalId;
}
function renderHospital(){
  const f=state.facilities.find(x=>x.id===selectedHospitalId)||state.facilities[0]; if(!f)return;
  $("hospitalSelect").value=f.id;
  $("hospitalCard").innerHTML=`<div class="hospital-icon">+</div><div><strong>${f.name}</strong><span>${f.system} · ${f.type}</span></div>`;
  $("hospitalBeds").textContent=number(f.planning_beds);
  $("hospitalCapacity").textContent=compact(f.annual_ed_capacity);
  $("hospitalDemand").textContent=compact(f.assigned_ed_visits);
  $("hospitalLoad").textContent=pct(f.load_ratio*100);
  $("hospitalLoad").style.color=loadColor(f.load_ratio);
  $("selectedBasis").textContent=f.proposed?"SCENARIO":(f.capacity_basis.includes("observed")?"MIXED":"PROXY");
  const q=f.queue;$("stressBand").textContent=q.stress_band;$("stressBand").style.color=loadColor(f.load_ratio);
  $("stressBar").style.width=`${Math.min(100,q.utilization*85)}%`;$("stressBar").style.background=loadColor(f.load_ratio);
  $("stressDetail").textContent=`Erlang-C proxy ${q.wait_proxy_minutes.toFixed(0)} min · ${pct(f.capacity_risk.probability_capacity_breach*100)} Monte-Carlo daily breach risk`;
}
function renderRegions(){
  const el=$("regionList");el.innerHTML="";
  [...state.regions].sort((a,b)=>b.population-a.population).slice(0,10).forEach(r=>{
    const row=document.createElement("div");row.className="region-row";
    row.innerHTML=`<b>${r.name}</b><span>${compact(r.population)}</span><strong style="color:${r.within_target?"#59d88b":"#ff8b47"}">${r.nearest_minutes.toFixed(0)}m</strong>`;
    row.addEventListener("click",()=>map.flyTo([r.lat,r.lon],8,{duration:.6}));
    el.appendChild(row);
  });
}
function showScenarioDelta(){
  if(!proposed||!baseline){$("scenarioDelta").classList.add("hidden");return}
  const a=baseline.metrics,b=state.metrics;
  const el=$("scenarioDelta");el.classList.remove("hidden");
  el.innerHTML=`<h4>SCENARIO IMPACT</h4>
    <div class="delta-row"><span>Coverage</span><b class="good">${(b.coverage_pct-a.coverage_pct)>=0?"+":""}${(b.coverage_pct-a.coverage_pct).toFixed(1)} pp</b></div>
    <div class="delta-row"><span>Avg nearest access</span><b class="good">${(b.avg_nearest_minutes-a.avg_nearest_minutes).toFixed(1)} min</b></div>
    <div class="delta-row"><span>ED demand shifted</span><b class="good">${compact(b.proposed_ed_visits_shifted)}</b></div>
    <div class="delta-row"><span>Overloaded sites</span><b>${b.overloaded_facilities-a.overloaded_facilities>=0?"+":""}${b.overloaded_facilities-a.overloaded_facilities}</b></div>`;
}
function render(){
  $("yearValue").textContent=state.year;$("accessMinutesValue").textContent=`${state.access_minutes} min`;
  $("edRateValue").textContent=`${state.ed_visits_per_capita.toFixed(2)} / person`;
  $("scenarioStatus").textContent=proposed?"ACTIVE":"OFF";$("scenarioStatus").classList.toggle("live",!!proposed);
  renderMetrics();populateHospitalSelect();renderHospital();renderRegions();renderMap();showScenarioDelta();
}
function resetPlaceMode(on=false){
  placeMode=on;$("mapModeBanner").classList.toggle("visible",on);
  $("mapFrame").style.cursor=on?"crosshair":"";
  $("placeButton").textContent=on?"Click map to place":"Place new hospital";
}
map.on("click",e=>{if(placeMode){resetPlaceMode(false);runScenario(e.latlng.lat,e.latlng.lng)}});

document.querySelectorAll(".year-switch button").forEach(btn=>btn.addEventListener("click",async()=>{
  document.querySelectorAll(".year-switch button").forEach(b=>b.classList.remove("active"));btn.classList.add("active");await getState();
}));
document.querySelectorAll("[data-layer]").forEach(btn=>btn.addEventListener("click",()=>{
  document.querySelectorAll("[data-layer]").forEach(b=>b.classList.remove("active"));btn.classList.add("active");activeLayer=btn.dataset.layer;renderMap();
}));
document.querySelectorAll("[data-basemap]").forEach(btn=>btn.addEventListener("click",()=>{
  document.querySelectorAll("[data-basemap]").forEach(b=>b.classList.remove("active"));btn.classList.add("active");
  Object.values(tiles).forEach(t=>map.removeLayer(t));tiles[btn.dataset.basemap].addTo(map);
}));
$("placeButton").addEventListener("click",()=>resetPlaceMode(!placeMode));
$("clearScenarioButton").addEventListener("click",()=>{state=baseline;proposed=null;selectedHospitalId=null;render();toast("Scenario cleared")});
$("optimizeButton").addEventListener("click",optimize);
$("hospitalSelect").addEventListener("change",e=>{selectedHospitalId=e.target.value;renderHospital()});
$("accessMinutes").addEventListener("input",e=>$("accessMinutesValue").textContent=`${e.target.value} min`);
$("accessMinutes").addEventListener("change",getState);
$("edRate").addEventListener("input",e=>$("edRateValue").textContent=`${Number(e.target.value).toFixed(2)} / person`);
$("edRate").addEventListener("change",getState);
["bedsInput","edCapacityInput"].forEach(id=>$(id).addEventListener("change",()=>{if(proposed)runScenario(proposed.lat,proposed.lon)}));

getState().catch(err=>{console.error(err);toast("Could not load planning model")});
