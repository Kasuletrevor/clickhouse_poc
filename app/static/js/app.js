import { PaymentsPage } from "./payments.js";

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

const titles={dashboard:"Dashboard",taxpayers:"Taxpayers",stations:"Stations",payments:"Payments",reports:"Reports",pipeline:"Pipeline Health",events:"Event Monitor",simulator:"Simulator"};
async function navigate(page){
  document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===page)); shell.title.textContent=titles[page]||"Tax Operations";
  if(page==="payments") return new PaymentsPage(shell).render();
  shell.content.innerHTML=`<div class="placeholder"><p class="eyebrow">Planned module</p><h2>${titles[page]}</h2><p>This module is part of the approved implementation plan and will be added after the Payments vertical slice.</p></div>`;
}
document.querySelectorAll(".nav-item").forEach(btn=>btn.onclick=()=>navigate(btn.dataset.page));
navigate("payments");
