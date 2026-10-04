(() => {
  const panel=document.querySelector("[data-attendance-panel]");
  if (!panel) return;
  const api=window.SchoolRunAPI;
  const status=panel.querySelector("[data-attendance-status]");
  const rows=[...panel.querySelectorAll("[data-attendance-row]")];
  const token=panel.querySelector("[name=csrfmiddlewaretoken]").value;
  let loading=false, saving=false, active=true, tripActive=false;

  function disable(disabled) {
    rows.forEach(row=>row.querySelectorAll("select, button").forEach(control=>{control.disabled=disabled;}));
  }
  async function refresh() {
    if (loading || saving || document.hidden || !active) return;
    loading=true;
    disable(true);
    try {
      const roster=await api.request(panel.dataset.rosterUrl);
      if (!active) return;
      tripActive=roster.status==="active";
      rows.forEach(row=>{
        const student=roster.students.find(item=>String(item.student_id)===row.dataset.studentId);
        if (!student) {
          row.hidden=true;
          return;
        }
        row.hidden=false;
        const observation=student.attendance;
        const notice=student.absence_notice==="reported"?"Reported absent":student.absence_notice==="cancelled"?"Notice cancelled":"No notice";
        row.querySelector("[data-child-facts]").textContent=`Parent: ${notice}. Observed: ${observation}. Recorded: ${api.date(student.recorded_at)}.`;
        const select=row.querySelector("select");
        if (!row.dataset.dirty) select.value=observation==="unrecorded"?"":observation;
      });
      status.textContent=tripActive?"Trip active. Record each child's observation.":`Trip ${roster.status}; attendance is read-only.`;
      disable(!tripActive);
    } catch(error) {status.textContent=error.message; disable(true);}
    finally {loading=false;}
  }
  rows.forEach(row=>{
    const form=row.querySelector("[data-record-form]");
    const select=row.querySelector("select");
    select.addEventListener("change",()=>{row.dataset.dirty="true";});
    form.addEventListener("submit",async event=>{
      event.preventDefault();
      if (loading || saving || !tripActive || select.disabled || !select.value) return;
      saving=true; disable(true);
      try {
        await api.request(row.dataset.recordUrl, {method:"POST", headers:{"Content-Type":"application/json","X-CSRFToken":token},body:JSON.stringify({status:select.value})});
        delete row.dataset.dirty;
        status.textContent="Observation saved.";
      } catch(error) {status.textContent=error.message; if (error.status===409) tripActive=false;}
      finally {saving=false; disable(!tripActive);}
      await refresh();
    });
  });
  panel.querySelector("[data-attendance-refresh]").addEventListener("click",refresh);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
  const timer=setInterval(refresh,15000);
  window.addEventListener("pagehide",()=>{active=false;clearInterval(timer);});
  refresh();
})();
