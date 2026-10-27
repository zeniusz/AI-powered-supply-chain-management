import { h, icon, nice, day, api, toast, modal, markdown, chip } from './util.js'
import { queuePage, networkPage, inventoryPage, ordersPage, commsPage, activityPage, confirmAction } from './pages.js'

const PAGES = [
  { id: 'queue', label: 'Action queue', icon: 'inbox', render: queuePage, sel: 'ex' },
  { id: 'network', label: 'Supply network', icon: 'network', render: networkPage },
  { id: 'inventory', label: 'Inventory', icon: 'boxes', render: inventoryPage, sel: 'pos' },
  { id: 'orders', label: 'Orders', icon: 'receipt', render: ordersPage, sel: 'order' },
  { id: 'comms', label: 'Communications', icon: 'mail', render: commsPage, sel: 'nt' },
  { id: 'activity', label: 'Activity & audit', icon: 'history', render: activityPage },
]

const ctx = {
  S: null, page: 'queue', sel: { ex: null, transfer: null, facility: null, order: null, nt: null, pos: null },
  filters: {}, ui: { tabs: {} }, seq: { ws: 0 }, flash: new Set(), assistant: { open: false, chat: [] }, live: null,
}
let shell = null

// ---------- routing ----------
function readHash() {
  const [, page, id] = decodeURIComponent(location.hash).split('/')
  const p = PAGES.find((x) => x.id === page)
  if (!p) return
  ctx.page = p.id
  if (id) {
    if (p.id === 'network') { ctx.sel.transfer = id.startsWith('TR-') ? id : null; ctx.sel.facility = id.startsWith('TR-') ? null : id } else if (p.sel) ctx.sel[p.sel] = id
  }
}
function writeHash() {
  const p = PAGES.find((x) => x.id === ctx.page)
  const id = p.id === 'network' ? ctx.sel.transfer || ctx.sel.facility : p.sel ? ctx.sel[p.sel] : null
  const next = `#/${p.id}${id ? `/${encodeURIComponent(id)}` : ''}`
  if (location.hash !== next) history.replaceState(null, '', next)
}
ctx.go = (page, sel = {}) => { ctx.page = page; Object.assign(ctx.sel, sel); ctx.render(); document.querySelector('.page')?.scrollTo(0, 0) }
ctx.pick = (kind, id) => {
  if (kind === 'transfer') Object.assign(ctx.sel, { transfer: id, facility: null })
  else if (kind === 'facility') Object.assign(ctx.sel, { facility: id, transfer: null })
  else ctx.sel[kind] = id
  ctx.render()
}

// ---------- actions ----------
ctx.act = async (path, body, { quiet = false } = {}) => {
  try {
    const data = await api(path, body)
    if (data.state) ctx.S = data.state
    if (!quiet && data.message) toast(data.message)
    ctx.render()
    return data
  } catch (e) { toast(e.message, { error: true }); return null }
}
ctx.toastResult = (m) => toast(m, { error: String(m).startsWith('rejected') })
ctx.openAssistant = (context) => { ctx.assistant.open = true; if (context) ctx.assistant.context = context; paintDrawer() }
ctx.preview = async (orderId) => {
  try { const d = await api(`/api/track/${orderId}`); modal({ title: 'Customer tracking preview', large: true, body: h('div', {}, customerView(d), h('p', { class: 'muted xs' }, `Shareable demo link: ?view=customer&order=${orderId}. Production links would use a signed, expiring token.`)) }) } catch (e) { toast(e.message, { error: true }) }
}

async function nextEvent({ navigate = true } = {}) {
  let data
  try { data = await api('/api/demo/next', {}) } catch (e) { toast(e.message, { error: true }); return }
  ctx.S = data.state
  const ev = data.event, changes = data.changes
  const exChanges = changes.filter((c) => /^Exception (detected|resolved|reopened)/.test(c.action)), flash = new Set()
  changes.forEach((c) => flash.add(c.record_id))
  if (ev) flash.add(ev.record_id)
  ctx.flash = flash; setTimeout(() => { ctx.flash = new Set() }, 3200)
  if (navigate && ev) {
    if (ev.record_type === 'transfer') { ctx.page = 'network'; Object.assign(ctx.sel, { transfer: ev.record_id, facility: null }) } else { ctx.page = 'orders'; ctx.sel.order = ev.record_id }
  }
  ctx.render()
  const lines = changes.filter((c) => !/^Event (applied|rejected)|^Duplicate event/.test(c.action)).map((c) => `${c.action}: ${c.detail}`.slice(0, 130))
  const target = exChanges.find((c) => !/resolved/.test(c.action)) || exChanges[0]
  const headline = ev ? `Event ${data.state.demo.cursor}/${data.state.demo.total} · ${ev.event_type.replace(/_/g, ' ').toLowerCase()} · ${ev.record_id}${ev.outcome === 'applied' ? '' : ` (${ev.outcome})`}` : data.message
  toast(headline, { lines: ev ? (lines.length ? lines.slice(0, 5) : [ev.detail, ev.outcome === 'applied' ? 'No new exceptions or messages were needed.' : 'Nothing was changed.']) : [], ms: navigate ? 9000 : 5000,
    action: navigate && target ? { label: 'View exception', run: () => ctx.go('queue', { ex: target.record_id }) } : null })
}

// ---------- shell ----------
function buildShell() {
  const nav = h('nav', { class: 'nav', 'aria-label': 'Main' }, PAGES.map((p) => h('button', { 'data-page': p.id, title: p.label, 'aria-label': p.label, onClick: () => ctx.go(p.id) }, icon(p.icon), h('span', { class: 'l' }, p.label), h('span', { class: 'badge', hidden: true }))))
  const step = h('div', { class: 'row' }), liveSw = h('input', { type: 'checkbox', onChange: (e) => setLive(e.target.checked) }), autoSw = h('input', { type: 'checkbox', onChange: (e) => ctx.act('/api/demo/auto-send', { enabled: e.target.checked }, { quiet: true }) })
  const meta = h('div', { class: 'meta' })
  const nextBtn = h('button', { class: 'btn primary', onClick: () => { document.querySelector('.demo').open = false; nextEvent() }, title: 'Release the next scenario event and jump to what it touched' }, icon('play'), 'Next event', h('span', { class: 'xs', style: 'opacity:.8' }))
  const demo = h('details', { class: 'demo' }, h('summary', { class: 'btn' }, icon('tune'), 'Demo'),
    h('div', { class: 'demo-panel' }, step, h('div', { class: 'row' }, nextBtn),
      h('div', { class: 'row' }, h('label', { class: 'switch' }, liveSw, 'Live demo')), h('div', { class: 'hint' }, 'Plays the remaining events every 8 seconds, jumping to each record.'),
      h('div', { class: 'row' }, h('label', { class: 'switch' }, autoSw, 'Auto-send internal messages')), h('div', { class: 'hint' }, 'Off: every message waits for review. Customer messages always do.'),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', onClick: resetDemo }, icon('retry'), 'Reset demo data')), meta))
  document.addEventListener('click', (e) => { if (!demo.contains(e.target)) demo.open = false; document.querySelectorAll('details.pop[open]').forEach((d) => { if (!d.contains(e.target)) d.open = false }) })
  const input = h('input', { type: 'search', placeholder: 'Search orders, transfers, SKUs, facilities', 'aria-label': 'Search', autocomplete: 'off' })
  const results = h('div', { class: 'results', hidden: true, role: 'listbox' })
  input.addEventListener('input', () => paintResults(input, results))
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { input.value = ''; results.hidden = true } if (e.key === 'Enter') results.querySelector('button')?.click() })
  input.addEventListener('blur', () => setTimeout(() => { results.hidden = true }, 180))
  const clock = h('div', { class: 'clock' }), assist = h('button', { class: 'btn', onClick: () => { ctx.assistant.open = !ctx.assistant.open; paintDrawer() } }, icon('spark'), 'Assistant')
  const top = h('header', { class: 'top' }, h('div', { class: 'brand' }, 'threadline', h('small', {}, 'Operations')), h('div', { class: 'search' }, icon('search'), input, h('kbd', {}, '/'), results),
    h('div', { class: 'spacer' }), clock, assist, demo)
  const page = h('main', { class: 'page', id: 'page' })
  const root = document.getElementById('root'); root.replaceChildren(h('div', { class: 'app' }, top, nav, page))
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); input.focus() }
    if (e.key === 'Escape' && ctx.assistant.open && !document.querySelector('.scrim')) { ctx.assistant.open = false; paintDrawer() }
  })
  shell = { nav, step, liveSw, autoSw, meta, clock, nextBtn, page, assist }
}

function updateShell() {
  const { S } = ctx, k = S.kpis
  shell.nav.querySelectorAll('button').forEach((b) => {
    b.toggleAttribute('aria-current', b.dataset.page === ctx.page); if (b.dataset.page === ctx.page) b.setAttribute('aria-current', 'page')
    const badge = b.querySelector('.badge'), n = b.dataset.page === 'queue' ? k.open : b.dataset.page === 'comms' ? k.to_approve : 0
    badge.hidden = !n; badge.textContent = n; badge.classList.toggle('amber', b.dataset.page === 'comms')
  })
  shell.step.textContent = `Scenario step ${S.demo.cursor} of ${S.demo.total}`
  shell.liveSw.checked = !!ctx.live; shell.autoSw.checked = S.demo.auto_send
  shell.meta.textContent = `Assistant: ${S.demo.assistant} · Messages: ${S.demo.delivery}`
  shell.clock.replaceChildren('Demo clock ', h('b', {}, nice(S.now)))
  const next = shell.nextBtn; next.hidden = S.demo.cursor >= S.demo.total; next.querySelector('span').textContent = `${S.demo.cursor}/${S.demo.total}`
}

function setLive(on) {
  clearInterval(ctx.live)
  const busy = () => { // don't pull the user away mid-edit: a dialog is open, or a text field has focus
    const el = document.activeElement
    const typing = el && (el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || (el.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(el.type)))
    return !!document.querySelector('.scrim') || typing
  }
  ctx.live = on ? setInterval(() => {
    if (ctx.S.demo.cursor >= ctx.S.demo.total) { setLive(false); toast('Scenario complete. Live demo stopped.'); return }
    if (!busy()) nextEvent()
  }, 8000) : null
  if (!on) updateShell()
}
async function resetDemo() {
  setLive(false)
  Object.assign(ctx.sel, { ex: null, transfer: null, facility: null, order: null, nt: null, pos: null }); ctx.assistant.chat = []
  const d = await ctx.act('/api/demo/reset', {}, { quiet: true })
  if (d) { paintDrawer(); toast('Demo data reset') }
}

function paintResults(input, box) {
  const q = input.value.trim().toLowerCase(), S = ctx.S
  if (!q) { box.hidden = true; return }
  const hit = (label, kind, go) => ({ label, kind, go }), out = []
  S.orders.forEach((o) => { if ([o.order_id, o.customer_ref, o.customer_name, o.tracking_code].join(' ').toLowerCase().includes(q)) out.push(hit(`${o.order_id} · ${o.state}`, 'Order', () => ctx.go('orders', { order: o.order_id }))) })
  S.transfers.forEach((t) => { if ([t.transfer_id, t.reference].join(' ').toLowerCase().includes(q)) out.push(hit(`${t.transfer_id} · ${t.status}`, 'Transfer', () => ctx.go('network', { transfer: t.transfer_id, facility: null }))) })
  S.facilities.forEach((f) => { if ([f.name, f.city, f.facility_id].join(' ').toLowerCase().includes(q)) out.push(hit(f.name, 'Facility', () => ctx.go('network', { facility: f.facility_id, transfer: null }))) })
  Object.entries(S.skus).forEach(([sku, s]) => { if (s.sellable && `${sku} ${s.name}`.toLowerCase().includes(q)) out.push(hit(`${sku} · ${s.name}`, 'SKU', () => { ctx.filters.inventory = { scope: 'All', fac: 'All facilities', sku, problems: false }; ctx.go('inventory', { pos: null }) })) })
  box.replaceChildren(...(out.length ? out.slice(0, 8).map((r) => h('button', { onMousedown: (e) => { e.preventDefault(); r.go(); input.value = ''; box.hidden = true } }, r.label, h('small', {}, r.kind))) : [h('div', { class: 'empty' }, 'No matching order, transfer, facility or SKU.')]))
  box.hidden = false
}

// ---------- assistant drawer ----------
function assistantContext() {
  const { sel, page, S } = ctx, ex = (id) => S.exceptions.find((e) => e.status !== 'Resolved' && (e.record_id === id || e.orders.includes(id)))
  if (page === 'queue' && sel.ex) return { exception_id: sel.ex }
  if (page === 'orders' && sel.order) return { order_id: sel.order, ...(ex(sel.order) ? { exception_id: ex(sel.order).id } : {}) }
  if (page === 'network' && sel.transfer) return { transfer_id: sel.transfer, ...(ex(sel.transfer) ? { exception_id: ex(sel.transfer).id } : {}) }
  return {}
}

let drawer = null
function paintDrawer() {
  const wasOpen = !!drawer
  drawer?.remove(); drawer = null
  if (!ctx.assistant.open) { if (wasOpen && shell) shell.assist.focus(); return }
  const context = assistantContext(), a = ctx.assistant
  const suggestions = context.exception_id ? ['What should I do?', 'Which orders are affected?', 'Draft an update for affected customers', 'Notify a store that its incoming transfer is delayed', 'Create an engineering ticket']
    : ['Which deliveries are at risk today?', 'How much overshirt stock is available at the Madrid store?', 'Why is order OR-20491 delayed?', 'Which facility can replenish overshirts to the Madrid store?']
  const log = h('div', { class: 'drawer-b', 'aria-live': 'polite' })
  const input = h('input', { class: 'input', placeholder: 'Ask about an order, transfer, stock or exception', 'aria-label': 'Ask the assistant', style: 'flex:1' })
  const ask = async (q) => {
    if (!q.trim()) return
    a.chat.push({ q, pending: true }); paintLog()
    try { const r = await api('/api/assistant', { question: q, context: assistantContext() }); Object.assign(a.chat[a.chat.length - 1], { pending: false, r }); ctx.S = (await api('/api/state')) } catch (e) { Object.assign(a.chat[a.chat.length - 1], { pending: false, err: e.message }) }
    paintLog(); updateShell()
  }
  const paintLog = () => {
    log.replaceChildren(
      h('div', { class: 'chips', style: 'margin-bottom:12px' }, suggestions.map((s) => h('button', { class: 'pill', style: 'font-weight:500', onClick: () => ask(s) }, s))),
      ...a.chat.map((t) => h('div', { class: 'turn' }, h('div', { class: 'q' }, t.q),
        t.pending ? h('div', { class: 'a muted' }, 'Reading records…') : t.err ? h('div', { class: 'a', style: 'color:var(--crit)' }, t.err) : h('div', { class: 'a' }, markdown(t.r.text),
          h('div', { class: 'meta' }, `${t.r.provider} · tools: ${t.r.tools.map((x) => x.tool).join(', ') || 'none'}`),
          h('div', { class: 'chips', style: 'margin-top:6px' }, t.r.proposals.filter((p) => p.exception_id).map((p) => h('button', { class: 'btn sm', onClick: () => confirmAction(ctx, p.exception_id, p) }, `Review: ${p.label}`))),
          t.r.tools.length ? h('details', {}, h('summary', {}, 'Evidence retrieved'), t.r.tools.map((x) => h('div', {}, h('div', { class: 'meta' }, `${x.tool}(${Object.entries(x.args).map(([k, v]) => `${k}=${v}`).join(', ')})`), h('pre', {}, JSON.stringify(x.result, null, 1))))) : null))))
    log.scrollTop = log.scrollHeight
  }
  const form = h('form', { class: 'drawer-f', onSubmit: (e) => { e.preventDefault(); const q = input.value; input.value = ''; ask(q) } }, input, h('button', { class: 'btn primary', type: 'submit' }, icon('send'), 'Ask'))
  drawer = h('aside', { class: 'drawer', role: 'complementary', 'aria-label': 'Assistant' },
    h('div', { class: 'drawer-h' }, h('h3', { style: 'flex:1' }, 'Assistant'),
      h('button', { class: 'btn ghost sm', 'aria-label': 'Close assistant', onClick: () => { a.open = false; paintDrawer() } }, icon('x'))), log, form)
  document.body.append(drawer); paintLog(); input.focus()
}

// ---------- customer-facing view ----------
function customerView(d) {
  const headline = { 1: "We're preparing your order", 2: 'Your order is on its way', 4: 'Delivered' }[d.stage]
  const when = d.stage === 4 ? (d.channel === 'Click & collect' ? 'Collected' : 'Delivered') : `${d.channel === 'Click & collect' ? 'Ready for collection by ' : 'Expected by '}${day(d.expected_by)}${d.updated ? ' (updated)' : ''}`
  const steps = ['Ordered', 'Preparing', 'Shipped', 'Delivered']
  return h('div', { class: 'cust' }, h('div', { class: 'cust-brand' }, 'threadline', h('small', {}, `Order ${d.order_id}`)), h('h2', {}, headline), h('div', {}, when),
    h('ol', { class: 'stepper' }, steps.map((s, i) => h('li', { class: `step ${i < d.stage ? 'done' : i === d.stage ? 'now' : ''}` }, h('span', { class: 'dot' }), h('span', {}, s)))),
    d.items.map((i) => h('div', { class: 'item' }, i.image ? h('img', { class: 'thumb', src: `/assets/products/${i.image}`, alt: i.name }) : h('div', { class: 'thumb' }), h('div', {}, h('b', {}, i.name), h('div', { class: 'meta' }, `Size ${i.size} · Qty ${i.qty}`)))),
    d.timeline.length ? h('div', { class: 'tl', style: 'margin-top:14px' }, d.timeline.map((t) => h('div', { class: 'tl-i ok' }, h('div', { class: 'tl-t' }, nice(t.ts)), h('div', { class: 'tl-h' }, t.text)))) : null,
    d.tracking_code ? h('p', { class: 'meta' }, `${d.carrier} tracking ${d.tracking_code}`) : null, h('p', { class: 'meta' }, 'Questions? Reply to your order email and our customer care team will help.'))
}

// ---------- render + boot ----------
ctx.render = () => {
  if (!ctx.S) return
  const p = PAGES.find((x) => x.id === ctx.page), page = shell.page, y = ctx.lastPage === ctx.page ? page.scrollTop : 0
  ctx.lastPage = ctx.page
  const keepFocus = document.activeElement && page.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') : null
  page.replaceChildren(p.render(ctx))
  page.classList.toggle('fill', ['queue', 'orders', 'inventory', 'comms'].includes(ctx.page))
  page.scrollTop = y
  writeHash(); updateShell()
  if (keepFocus) page.querySelector(`[aria-label="${keepFocus}"]`)?.focus()
}

async function boot() {
  const q = new URLSearchParams(location.search)
  if (q.get('view') === 'customer') {
    const root = document.getElementById('root')
    try { root.replaceChildren(h('div', { class: 'cust-page' }, h('div', { class: 'cust-card' }, customerView(await api(`/api/track/${q.get('order') || ''}`))))) } catch (e) { root.replaceChildren(h('div', { class: 'cust-page' }, h('div', { class: 'cust-card cust' }, h('h2', {}, "We couldn't find that order"), h('p', {}, 'Check the link in your email or contact customer care.')))) }
    return
  }
  try { ctx.S = await api('/api/state') } catch (e) { document.getElementById('root').textContent = `Could not load data: ${e.message}`; return }
  buildShell(); readHash(); ctx.render()
  window.addEventListener('hashchange', () => { readHash(); ctx.render() })
}
boot()
