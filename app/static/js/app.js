import { DashboardPage } from "./dashboard.js";
import { EfrisErrorsPage } from "./efris_errors.js";
import { PaymentsPage } from "./payments.js";
import { StationsPage } from "./stations.js";
import { TaxpayersPage } from "./taxpayers.js";

const shell = {
  content: document.querySelector("#app-content"),
  title: document.querySelector("#page-title"),
  drawer: document.querySelector("#drawer"),
  backdrop: document.querySelector("#drawer-backdrop"),
  openDrawer(html){ this.drawer.innerHTML = html; this.drawer.classList.add("open"); this.drawer.setAttribute("aria-hidden","false"); this.backdrop.classList.remove("hidden"); },
  closeDrawer(){ this.drawer.classList.remove("open"); this.drawer.setAttribute("aria-hidden","true"); this.backdrop.classList.add("hidden"); },
  toast(message, error=false){ const el=document.createElement("div"); el.className=`toast${error?" error":""}`; el.textContent=message; document.querySelector("#toast-region").appendChild(el); setTimeout(()=>el.remove(),3800); }
};
shell.backdrop.onclick = () => shell.closeDrawer();

const titles={dashboard:"Dashboard",taxpayers:"Taxpayers",stations:"Stations",payments:"Payments","efris-errors":"EFRIS Errors",reports:"Reports",pipeline:"Pipeline Health",events:"Event Monitor",simulator:"Simulator"};
let activePage = null;

async function navigate(page){
  if(activePage && typeof activePage.destroy === "function") activePage.destroy();
  activePage = null;
  document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===page));
  shell.title.textContent=titles[page]||"Tax Operations";
  shell.closeDrawer();
  if(page==="dashboard") { activePage = new DashboardPage(shell); await activePage.render(); return; }
  if(page==="payments") { activePage = new PaymentsPage(shell); await activePage.render(); return; }
  if(page==="taxpayers") { activePage = new TaxpayersPage(shell); await activePage.render(); return; }
  if(page==="stations") { activePage = new StationsPage(shell); await activePage.render(); return; }
  if(page==="efris-errors") { activePage = new EfrisErrorsPage(shell); await activePage.render(); return; }
  shell.content.innerHTML=`<div class="placeholder"><p class="eyebrow">Planned module</p><h2>${titles[page]}</h2><p>This module is part of the approved implementation plan and will be added in the next vertical slices.</p></div>`;
}
document.querySelectorAll(".nav-item").forEach(btn=>btn.onclick=()=>navigate(btn.dataset.page));
navigate("dashboard");
