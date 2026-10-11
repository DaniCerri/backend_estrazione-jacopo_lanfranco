// Conferma prima di inviare i form marcati con data-confirm
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset.confirm
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

// Aggiorna i contatori ogni 10s senza ricaricare la pagina
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
    Object.entries(s.per_zona).forEach(([z, n]) => set(`zona-${z}`, n))
  } catch {
    // rete assente: riprova al giro successivo
  }
}
if (document.querySelector("[data-stat]")) setInterval(aggiorna, 10000)
