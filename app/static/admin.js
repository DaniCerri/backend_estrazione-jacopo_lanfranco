// Conferma o motivo obbligatorio prima di inviare i form marcati
document.addEventListener("submit", (e) => {
  const form = e.target
  const domanda = form.dataset.prompt
  if (domanda) {
    const motivo = window.prompt(domanda)?.trim()
    if (!motivo || motivo.length < 3) {
      e.preventDefault()
      return
    }
    form.elements.motivo.value = motivo
  }
  const msg = form.dataset.confirm
  if (msg && !window.confirm(msg)) e.preventDefault()
})

// Filtro client-side della tabella iscritti
document.querySelectorAll("[data-filtro]").forEach((input) => {
  const righe = document.querySelectorAll(`${input.dataset.filtro} tbody tr`)
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase()
    righe.forEach((tr) => {
      tr.hidden = q !== "" && !tr.dataset.cerca.includes(q)
    })
  })
})

// Aggiorna i contatori ogni 10s senza ricaricare la pagina.
// L'impronta attesa per l'estrazione NON si aggiorna: se la lista cambia
// il server rifiuta l'estrazione e chiede di ricaricare.
const aggiorna = async () => {
  try {
    const res = await fetch("/admin/api/stats", { credentials: "same-origin" })
    if (res.status === 401) return window.location.assign("/admin/login")
    if (!res.ok) return
    const s = await res.json()
    const set = (k, v) => {
      const el = document.querySelector(`[data-stat="${k}"]`)
      if (el) el.textContent = v
    }
    set("totale", s.totale)
    set("marketing", s.marketing)
    set("aperte", s.aperte ? "Aperte" : "Chiuse")
    set("in_gara", s.in_gara)
    set("in_gara_hash", s.in_gara_hash)
    Object.entries(s.per_zona).forEach(([z, n]) => set(`zona-${z}`, n))
    const atteso = document.querySelector("[data-hash-atteso]")
    const box = document.querySelector('[data-stat="in_gara_hash"]')
    if (atteso && box) box.classList.toggle("is-cambiato", atteso.value !== s.in_gara_hash)
  } catch {
    // rete assente: riprova al giro successivo
  }
}
if (document.querySelector("[data-stat]")) setInterval(aggiorna, 10000)
