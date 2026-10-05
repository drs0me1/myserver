/* Built-in ZIP/RAR jobs. Progress is reported by the server, never simulated.
   DD-183: no jobs page. A running job shows one bar above the Files list (progress and
   cancel); its start and result are written to Ayarlar → Günlük by the server. */
"use strict";
window.createArchiveTools = function ({h, api, post, toast, fail, showDialog, closeDialog, root, downloads, refresh}) {
  let jobs = [], timer = null, loading = false, started = false;
  const active = (job) => ["queued", "running"].includes(job.status);
  const labels = {queued:"Sırada", running:"Çalışıyor", done:"Tamamlandı", skipped:"Atlandı", failed:"Başarısız", cancelled:"İptal edildi", interrupted:"Kesildi"};
  const containers = new Set();
  const canExtract = name => /\.(zip|rar|[r-z][0-9]{2})$/i.test(name);
  function paint() {
    const running = jobs.filter(active);
    for (const container of containers) {
      if (!container.isConnected) { containers.delete(container); continue; }
      container.hidden = !running.length;
      container.replaceChildren(...running.map((job) => h("div", {class:"archive-bar", role:"status", "aria-live":"polite"},
        h("span", {class:"spin", "aria-hidden":"true"}),
        h("p", null, h("strong", null, job.name), ` · ${labels[job.status] || job.status} · ${job.message}`),
        h("button", {type:"button", class:"btn btn-sm btn-quiet", onclick: async (e) => {
          e.currentTarget.disabled = true;
          try { await post("/api/archives/cancel", {id:job.id}); await load(); } catch (err) { fail(err); await load(); }
        }}, "İptal et"))));
    }
  }
  async function load(report = false) {
    if (loading) return;
    loading = true;
    try {
      const data = await api("/api/archives");
      const previous = new Map(jobs.map((j) => [j.id, j]));
      jobs = data.items;
      for (const job of jobs) if (started && !active(job) && previous.has(job.id) && active(previous.get(job.id))) {
        toast(`${job.name}: ${job.message}`);
        if (job.status === "done") refresh();
      }
      started = true;
      paint();
    } catch (err) { if (report) fail(err); }
    finally {
      loading = false; clearTimeout(timer);
      timer = setTimeout(() => { if (!document.hidden) load(); else timer = null; }, jobs.some(active) ? 1500 : 10000);
    }
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && started) load(); });
  function mount(container) { containers.add(container); paint(); if (!started) load(true); }
  function open(operation, path, items) {
    const unzip = operation === "unzip";
    let target = downloads(), browsing = false, working = false, sequence = 0;
    if (typeof target !== "string") { fail(new Error("İndirme klasörü bilgisi yüklenemedi; sayfayı yenileyin.")); return; }
    const initial = items.length === 1 ? items[0].name.replace(/(?:\.part[0-9]+)?\.(zip|rar|[r-z][0-9]{2})$/i, "") : "arsiv";
    const field = (label, input) => h("label", null, label, input);
    const name = h("input", {id:"archive-name", required:true, value:initial || "arsiv", maxlength:150, autocomplete:"off"});
    const targetText = h("span", {id:"archive-target"}, [root(),target].filter(Boolean).join("/"));
    const picker = h("div", {id:"archive-picker", class:"archive-picker", hidden:true, role:"group", "aria-label":"Hedef klasör seçimi"});
    const choose = h("button", {type:"button", class:"archive-target btn btn-quiet", "aria-label":"Hedef klasör seç", "aria-controls":"archive-picker", "aria-expanded":"false", onclick:() => {
      if (working) return;
      if (browsing) finishPicker();
      else { browsing = true; picker.hidden = false; choose.setAttribute("aria-expanded","true"); submit.disabled = true; browse(target); }
    }}, targetText, h("span", null, "Değiştir"));
    function finishPicker() {
      sequence++; browsing = false; picker.hidden = true; choose.setAttribute("aria-expanded","false"); submit.disabled = working; choose.focus();
    }
    async function browse(folder) {
      const request = ++sequence;
      const navigation = h("div", {class:"archive-picker-nav"},
        h("button", {type:"button", class:"btn btn-sm btn-quiet", disabled:!folder, onclick:() => browse(folder.split("/").slice(0,-1).join("/"))}, "Üst klasör"),
        h("button", {type:"button", class:"btn btn-sm btn-quiet", disabled:!folder, onclick:() => browse("")}, "Sunucu"));
      const listing = h("div", {class:"archive-folders", "aria-live":"polite"}, "Yükleniyor…");
      const use = h("button", {type:"button", class:"btn btn-sm btn-primary", disabled:true, onclick:() => {
        target = folder; targetText.textContent = [root(),target].filter(Boolean).join("/"); finishPicker();
      }}, "Bu klasörü seç");
      picker.replaceChildren(navigation, h("p", {class:"archive-location"}, [root(),folder].filter(Boolean).join("/")), listing,
        h("div", {class:"dlg-foot"}, h("button", {type:"button", class:"btn btn-sm btn-quiet", onclick:finishPicker}, "Geri"), use));
      try {
        const data = await api(`/api/list?dirs=1&path=${encodeURIComponent(folder)}`);
        if (!browsing || request !== sequence || !picker.isConnected) return;
        const dirs = data.entries.filter(item => item.type === "dir").sort((a,b) => a.name.localeCompare(b.name,"tr"));
        listing.replaceChildren(...dirs.map(item => h("button", {type:"button", class:"archive-folder btn btn-quiet", onclick:() => browse([folder,item.name].filter(Boolean).join("/"))}, item.name)));
        if (!dirs.length) listing.append(h("span", {class:"hint-s"}, "Alt klasör yok."));
        use.disabled = false;
        (listing.querySelector("button") || use).focus();
      } catch (err) {
        if (!browsing || request !== sequence || !picker.isConnected) return;
        listing.replaceChildren(h("p", {class:"err-s", role:"alert"}, err.message),
          h("button", {type:"button", class:"btn btn-sm btn-quiet", onclick:() => browse(folder)}, "Yeniden dene"));
      }
    }
    const conflict = h("select", {id:"archive-conflict"}, ...[["rename","Yeni ad ver: ad (2)"],["skip","Sonucu atla"],["stop","İşlemi durdur"]].map(([value,label]) => h("option", {value}, label)));
    const error = h("p", {class:"err-s", role:"alert", hidden:true});
    const submit = h("button", {type:"submit", class:"btn btn-primary"}, unzip ? "Arşivi aç" : "Oluştur");
    const form = h("form", {class:"dav-form archive-form", onsubmit:async (event) => {
      event.preventDefault();
      if (working || browsing) return;
      working = true; submit.disabled = true; choose.disabled = true; error.hidden = true;
      try {
        let resultName = name.value.trim();
        if (!unzip && !/\.zip$/i.test(resultName)) resultName += ".zip";
        const response = await post("/api/archives", {operation,path,names:items.map((item) => item.name),target,name:resultName,conflict:conflict.value});
        jobs = [response.job, ...jobs.filter((j) => j.id !== response.job.id)].slice(0,20);
        started = true;
        closeDialog();
        toast("Arşiv işlemi başladı; sonucu Ayarlar → Günlük'te de görünür."); await load(true);
      } catch (err) { error.textContent = err.message; error.hidden = false; working = false; submit.disabled = false; choose.disabled = false; }
    }}, field(unzip ? "Sonuç klasörü" : "Arşiv adı", name),
    h("div", {class:"archive-destination"}, h("span", null, "Hedef klasör"), choose, picker),
    field("Hedefte sonuç adı zaten varsa", conflict),
    error, h("div", {class:"dlg-foot"}, h("button", {type:"button", class:"btn btn-quiet", onclick:closeDialog}, "Vazgeç"), submit));
    showDialog(unzip ? "Arşiv açıcı" : "Arşiv oluştur", form); name.focus(); name.select();
  }
  return {mount, load, open, canExtract};
};
