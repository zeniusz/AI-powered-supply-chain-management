// DOM helpers, formatting, API client, toasts, modals. No framework; every piece of data is inserted as text, never as HTML.

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue
    if (k === 'class') el.className = v
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v)
    else if (k === 'html') el.innerHTML = v // only used with trusted static strings (icons)
    else if (v === true) el.setAttribute(k, '')
    else el.setAttribute(k, v)
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)))
  }
  return el
}

const ICONS = {
  inbox: '<path d="M3 13l2.5-8h13L21 13v6H3z"/><path d="M3 13h5l1.5 2.5h5L16 13h5"/>',
  network: '<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="18" r="2.2"/><circle cx="19" cy="18" r="2.2"/><path d="M11 7l-5 9M13 7l5 9M7.2 18h9.6"/>',
  boxes: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5L12 12l8-4.5M12 12v9"/>',
  receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  history: '<path d="M3 12a9 9 0 109-9 9 9 0 00-7 3.4L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z"/>',
  play: '<path d="M6 4l9 8-9 8zM18 5v14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>',
  send: '<path d="M21 3L3 11l7 3 3 7z"/><path d="M10 14l11-11"/>',
  retry: '<path d="M4 12a8 8 0 0114-5l2 2M20 4v5h-5M20 12a8 8 0 01-14 5l-2-2M4 20v-5h5"/>',
  tune: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
}
export function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  s.setAttribute('class', 'ico'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true')
  s.innerHTML = ICONS[name] || ''
  return s
}

// ---------- formatting (demo clock times are naive 'YYYY-MM-DDTHH:MM' strings) ----------
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function parse(iso) { const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso || ''); return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null }
export function nice(iso) {
  const d = parse(iso); if (!d) return '—'
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
export function day(iso) { const d = parse(iso); return d ? `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}` : '—' }
export function shiftIso(iso, hours) {
  const d = parse(iso); d.setMinutes(d.getMinutes() + Math.round(hours * 60))
  const z = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`
}
export const age = (hours) => hours < 48 ? `${Math.round(hours)} h` : `${(hours / 24).toFixed(1)} d`
export const num = (n) => Number(n).toLocaleString('en')

// ---------- status tones ----------
const TONE = {
  crit: ['P1', 'Failed', 'Customs hold', 'Exception', 'Rejected', 'Allocation failed', 'At risk', 'Open'],
  warn: ['P2', 'Awaiting approval', 'Awaiting stock', 'Delayed', 'Partially received', 'Return in transit', 'Short', 'Draft', 'Planned (waiting)'],
  ok: ['Received', 'Delivered', 'Simulated send', 'Sent', 'Resolved', 'On time', 'Returned', 'Allocated', 'applied', 'allocated', 'delivered', 'restocked'],
  move: ['In transit', 'Shipped', 'Picked', 'Packed', 'Assigned', 'Action in progress', 'Arrived', 'shipped'],
}
export function tone(label) {
  const t = String(label)
  for (const [k, list] of Object.entries(TONE)) if (list.includes(t)) return k
  if (t.startsWith('rejected')) return 'crit'
  if (t.startsWith('duplicate')) return 'warn'
  return 'idle'
}
export const STATUS_HELP = {
  P1: 'Priority 1: a customer promise or store stockout falls within 48 hours.', P2: 'Priority 2: other downstream impact, or a delay of 24 hours or more.', P3: 'Priority 3: no downstream dependency found.',
  'Awaiting approval': 'Drafted by a rule. A person must approve it before it is sent.', Draft: 'Drafted and ready to send.', Failed: 'Delivery failed. You can retry.',
  Superseded: 'Replaced by a newer message because the facts changed. Never sent.', Rejected: 'Declined by an operator. Never sent.',
  'Simulated send': 'Delivered in demo mode: logged, nothing left this machine.', Sent: 'Delivered through a configured provider.',
  'Customs hold': 'Held by customs until the paperwork is corrected.', 'At risk': 'Projected to arrive after the promised date, or blocked.', 'On time': 'Projected to arrive by the promised date.',
  'Awaiting stock': 'Waiting for an inbound transfer to bring stock.', 'Partially received': 'Fewer units arrived than were shipped.', 'In transit': 'On the way to its destination.',
  Exception: 'A quality or handling problem stopped this transfer.', 'Allocation failed': 'No sellable stock could be assigned.', Open: 'Not yet resolved.',
  'Action in progress': 'A response has been applied and is being tracked.', Assigned: 'Someone owns this exception.', Resolved: 'The condition cleared or an operator closed it.',
}
export const chip = (text, t) => h('span', { class: `chip ${t || tone(text)}`, title: STATUS_HELP[text] }, text)
export const TONE_COLOR = { crit: '#C0334A', warn: '#E0A21B', ok: '#3E7B3F', move: '#2F6DB5', idle: '#8A8576' }

// ---------- API ----------
export async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
  return data
}

// ---------- toasts ----------
export function toast(message, { error = false, lines = [], action = null, ms = 4500 } = {}) {
  const box = document.getElementById('toasts')
  const el = h('div', { class: 'toast' + (error ? ' err' : ''), role: error ? 'alert' : 'status' },
    h('div', { class: 'row' }, h('span', { style: 'flex:1' }, message), action && h('button', { class: 'btn', onclick: () => { action.run(); el.remove() } }, action.label)),
    lines.length ? h('ul', {}, lines.map((l) => h('li', {}, l))) : null)
  el.title = 'Click to dismiss'; el.addEventListener('click', () => el.remove())
  box.append(el)
  setTimeout(() => el.remove(), ms)
}

// ---------- modal ----------
export function modal({ title, body, actions = [], large = false, onClose }) {
  const opener = document.activeElement
  const close = () => { scrim.remove(); document.removeEventListener('keydown', esc); opener && opener.focus && opener.focus(); onClose && onClose() }
  const esc = (e) => {
    if (e.key === 'Escape') close()
    if (e.key === 'Tab') { // keep keyboard focus inside the dialog
      const f = [...scrim.querySelectorAll('button,input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.offsetParent !== null)
      if (!f.length) return
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() } else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
    }
  }
  const scrim = h('div', { class: 'scrim', onclick: (e) => { if (e.target === scrim) close() } },
    h('div', { class: 'modal' + (large ? ' large' : ''), role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('div', { class: 'modal-h' }, h('h3', {}, title), h('button', { class: 'btn ghost sm', 'aria-label': 'Close', onclick: close }, icon('x'))),
      h('div', { class: 'modal-b' }, body),
      actions.length ? h('div', { class: 'modal-f' }, actions.map((a) => h('button', {
        class: 'btn' + (a.primary ? ' primary' : ''),
        onclick: async (e) => { if (a.run) { e.target.disabled = true; const keep = await a.run(close); if (keep) e.target.disabled = false } else close() },
      }, a.label))) : null))
  document.addEventListener('keydown', esc)
  document.body.append(scrim)
  const first = scrim.querySelector('textarea,input,select,.btn.primary')
  first && first.focus()
  return close
}

// ---------- tiny markdown (bold, bullets, tables, paragraphs) for assistant answers ----------
export function markdown(text) {
  const root = h('div'), lines = String(text).split('\n')
  const inline = (s) => { const out = []; s.split(/(\*\*[^*]+\*\*)/).forEach((p) => out.push(p.startsWith('**') ? h('b', {}, p.slice(2, -2)) : p)); return out }
  let i = 0
  while (i < lines.length) {
    const ln = lines[i]
    if (/^\|.*\|$/.test(ln.trim())) {
      const rows = []; while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) rows.push(lines[i++].trim().slice(1, -1).split('|').map((c) => c.trim()))
      const body = rows.filter((r) => !r.every((c) => /^-+$/.test(c)))
      root.append(h('table', {}, h('thead', {}, h('tr', {}, body[0].map((c) => h('th', {}, c)))), h('tbody', {}, body.slice(1).map((r) => h('tr', {}, r.map((c) => h('td', {}, inline(c))))))))
    } else if (/^\s*[-•]\s/.test(ln)) {
      const ul = h('ul'); while (i < lines.length && /^\s*[-•]\s/.test(lines[i])) ul.append(h('li', {}, inline(lines[i++].replace(/^\s*[-•]\s/, ''))))
      root.append(ul)
    } else if (ln.trim()) { root.append(h('p', {}, inline(ln))); i++ } else i++
  }
  return root
}
