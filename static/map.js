// Supply network map (Leaflet). The map element is created once and reused so tiles don't reload on every update.
import { h, TONE_COLOR } from './util.js'

const GLYPH = {
  Factory: '<path d="M3 20V9l6 3V9l6 3V5h3v15z"/>',
  'Material supplier': '<path d="M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8"/>',
  Port: '<circle cx="12" cy="5" r="2"/><path d="M12 7v13M6 12H4a8 8 0 0016 0h-2M8 10h8"/>',
  'Distribution centre': '<path d="M3 20V9l9-5 9 5v11M8 20v-6h8v6"/>',
  '3PL gateway': '<path d="M2 7h12v9H2zM14 10h4l3 3v3h-7"/><circle cx="6" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/>',
  Store: '<path d="M4 9l1.5-5h13L20 9M4 9h16v11H4zM9 20v-6h6v6"/>',
}
let M = null

function create(tiles) {
  const node = h('div', { id: 'netmap', role: 'application', 'aria-label': 'Supply network map' })
  const el = h('div', { class: 'mapbox' }, node)
  const map = L.map(node, { zoomControl: true, scrollWheelZoom: true, worldCopyJump: false })
  L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: 18 }).addTo(map)
  const layer = L.layerGroup().addTo(map)
  const legend = L.control({ position: 'topright' })
  legend.onAdd = () => {
    const d = L.DomUtil.create('div', 'legend')
    d.innerHTML = [['ok', 'No open issue'], ['warn', 'Open exception'], ['crit', 'P1 or hold'], ['move', 'Moving on plan']]
      .map(([t, l]) => `<div><i style="background:${TONE_COLOR[t]}"></i>${l}</div>`).join('') + '<div><u></u>In transit</div><div><s></s>Planned or waiting</div>'
    return d
  }
  legend.addTo(map)
  new ResizeObserver(() => map.invalidateSize()).observe(el)
  M = { el, map, layer, fitted: false, tilesOk: false }
  map.eachLayer((l) => { if (l instanceof L.TileLayer) l.on('tileload', () => { M.tilesOk = true }) })
  setTimeout(() => {
    if (!M.tilesOk && !el.querySelector('.map-note')) {
      node.after(h('div', { class: 'map-note' }, h('div', {}, h('b', {}, 'Map tiles could not be loaded.'), h('br'), `${tiles.name} is unreachable from this browser. Locations and routes are listed in the table below.`)))
    }
  }, 8000)
}

/** Draw facilities and open transfers. sel = { transfer, facility }. onPick(kind, id) on marker or route click. Returns the map element. */
export function networkMap(S, sel, onPick) {
  if (!M) create(S.config.tiles)
  const { map, layer } = M
  layer.clearLayers()
  const fac = Object.fromEntries(S.facilities.map((f) => [f.facility_id, f]))
  const selT = S.transfers.find((t) => t.transfer_id === sel.transfer)
  for (const t of S.transfers) {
    if (!t.open && t.transfer_id !== sel.transfer) continue
    const a = fac[t.source], b = fac[t.destination], on = t.transfer_id === sel.transfer
    L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { color: TONE_COLOR[t.tone], weight: on ? 6 : 3, opacity: on ? 1 : 0.8, dashArray: t.waiting ? '3 8' : null })
      .bindTooltip(`${t.transfer_id} · ${t.status} · ${a.city} → ${b.city}`).on('click', () => onPick('transfer', t.transfer_id)).addTo(layer)
  }
  for (const f of S.facilities) {
    const on = f.facility_id === sel.facility || (selT && (selT.source === f.facility_id || selT.destination === f.facility_id))
    const size = on ? 38 : 30
    const icon = L.divIcon({ className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      html: `<div class="pin${on ? ' sel' : ''}${f.tone === 'crit' ? ' crit' : ''}" style="width:${size}px;height:${size}px;background:${TONE_COLOR[f.tone]}"><svg class="ico" style="width:${size * 0.55}px;height:${size * 0.55}px" viewBox="0 0 24 24">${GLYPH[f.facility_type] || ''}</svg></div>` })
    L.marker([f.lat, f.lon], { icon, keyboard: true, title: f.name }).bindTooltip(`${f.facility_id} · ${f.name}`).on('click', () => onPick('facility', f.facility_id)).addTo(layer)
  }
  setTimeout(() => {
    map.invalidateSize()
    if (!M.fitted && M.el.offsetHeight > 0) { map.fitBounds(S.facilities.map((f) => [f.lat, f.lon]), { padding: [36, 36], maxZoom: 7 }); M.fitted = true }
  }, 60)
  return M.el
}
