import { h, icon, nice, day, age, num, tone, chip, modal, markdown, shiftIso, parse } from './util.js'

const heldHours = (r) => (r.status === 'Resolved' && r.resolved_at ? (parse(r.resolved_at) - parse(r.detected_at)) / 36e5 : r.age_h)
import { table } from './table.js'
import { networkMap } from './map.js'
import { journey } from './viz.js'

// ---------- shared pieces ----------
// Number tiles. A tile with a 5th element { on, click } doubles as a filter button.
const stats = (items) => h('div', { class: 'stats' }, items.map(([v, label, t, tip, act]) => h(act ? 'button' : 'div', { class: 'stat' + (act && act.on ? ' on' : ''), title: tip, onClick: act && act.click, 'aria-pressed': act ? String(!!act.on) : null },
  h('b', { class: t || '' }, v), h('span', {}, label))))
const kv = (rows) => h('dl', { class: 'kv' }, rows.filter(Boolean).flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]))
const timeline = (rows) => h('div', { class: 'tl' }, rows.map((r) => h('div', { class: `tl-i ${r.tone || ''}` }, h('div', { class: 'tl-t' }, r.t), h('div', { class: 'tl-h' }, r.title), r.detail ? h('div', {}, r.detail) : null)))
const field = (label, control) => h('div', { class: 'field' }, h('label', {}, label), control)
const link = (text, onClick) => h('button', { class: 'btn ghost sm', onClick }, text, icon('open'))
const eventTone = (e) => (e.outcome !== 'applied' ? tone(e.outcome) : /REJECTED|FAILED|HOLD|DELAY/.test(e.event_type) ? 'crit' : 'move')
const pretty = (s) => s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())
const skuName = (S, sku) => (S.skus[sku] ? S.skus[sku].name : sku)

function tabs(ctx, key, defs) {
  const cur = ctx.ui.tabs[key] && defs.some((d) => d.id === ctx.ui.tabs[key]) ? ctx.ui.tabs[key] : defs[0].id
  const body = h('div', { class: 'tab-body' })
  const paint = () => body.replaceChildren(defs.find((d) => d.id === ctx.ui.tabs[key]).render())
  ctx.ui.tabs[key] = cur
  const bar = h('div', { class: 'tabs', role: 'tablist' }, defs.map((d) => h('button', {
    role: 'tab', 'aria-selected': String(d.id === cur),
    onClick: (e) => { ctx.ui.tabs[key] = d.id; bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', 'false')); e.currentTarget.setAttribute('aria-selected', 'true'); paint() },
  }, d.label, d.n ? h('span', { class: 'n' }, d.n) : null)))
  paint()
  return h('div', {}, bar, body)
}

// A message is one quiet row. Click it to read it; messages that need a decision say "Review".
function messageRow(ctx, n) {
  const todo = ['Awaiting approval', 'Draft', 'Failed'].includes(n.status)
  return h('button', { class: `mrow${todo ? ' todo' : ''}${n.status === 'Failed' ? ' bad' : ''}`, title: `To ${n.recipient}`, onClick: () => reviewMessage(ctx, n) },
    chip(n.status), h('span', { class: 't' }, n.subject), todo ? h('span', { class: 'go' }, 'Review') : null)
}

function reviewMessage(ctx, n) {
  const editable = ['Awaiting approval', 'Draft'].includes(n.status), failed = n.status === 'Failed', todo = editable || failed
  const area = editable ? h('textarea', { class: 'input', rows: 9, 'aria-label': 'Message text', style: 'width:100%' }, n.body) : h('pre', { class: 'readonly' }, n.body)
  const act = (path, body) => async (close) => { const ok = await ctx.act(path, body()); if (ok) close(); return !ok }
  modal({
    title: n.subject, large: true,
    body: h('div', {}, h('div', { class: 'chips', style: 'margin-bottom:8px' }, chip(n.status), chip(n.audience, 'idle'), h('span', { class: 'meta' }, `To ${n.recipient} · ${nice(n.created_at)}`)),
      area, n.last_error ? h('p', { class: 'meta', style: 'color:var(--crit)' }, `Last error: ${n.last_error}`) : null,
      h('details', { class: 'fold plain' }, h('summary', {}, 'Why this was created and its history'), h('div', {}, h('p', { class: 'sm muted' }, n.reason),
        timeline(n.history.map((x) => ({ t: x.split(' · ')[0].replace('T', ' '), title: x.split(' · ').slice(1).join(' · ') })))))),
    actions: todo
      ? [{ label: 'Reject', run: act(`/api/notifications/${n.notification_id}/reject`, () => ({ note: 'Not appropriate for this situation' })) },
        editable ? { label: n.requires_approval ? 'Approve and send' : 'Send', primary: true, run: act(`/api/notifications/${n.notification_id}/send`, () => ({ body: area.value })) }
          : { label: 'Retry', primary: true, run: act(`/api/notifications/${n.notification_id}/retry`, () => ({})) }]
      : [{ label: 'Close' }],
  })
}

// Full editor, used in the Communications detail panel.
function messageCard(ctx, n, full = false) {
  if (!full) return messageRow(ctx, n)
  const editable = ['Awaiting approval', 'Draft'].includes(n.status)
  const area = h('textarea', { class: 'input', 'aria-label': 'Message text', disabled: !editable }, n.body)
  return h('div', { class: 'msg' },
    h('div', { class: 'msg-h' }, chip(n.status), chip(n.audience, 'idle'), h('b', {}, n.subject)),
    h('div', { class: 'meta', title: n.reason }, `To ${n.recipient} · ${nice(n.created_at)}`),
    area, n.last_error ? h('div', { class: 'meta', style: 'color:var(--crit)' }, `Last error: ${n.last_error}`) : null,
    h('div', { class: 'actions' },
      editable ? h('button', { class: 'btn primary', onClick: () => ctx.act(`/api/notifications/${n.notification_id}/send`, { body: area.value }) }, icon('send'), n.requires_approval ? 'Approve and send' : 'Send') : null,
      n.status === 'Failed' ? h('button', { class: 'btn', onClick: () => ctx.act(`/api/notifications/${n.notification_id}/retry`, {}) }, icon('retry'), 'Retry') : null,
      ['Awaiting approval', 'Draft', 'Failed'].includes(n.status) ? h('button', { class: 'btn', onClick: () => ctx.act(`/api/notifications/${n.notification_id}/reject`, { note: 'Not appropriate for this situation' }) }, 'Reject') : null))
}

// ---------- action confirmation ----------
const ACTION_TEXT = {
  reallocate_orders: 'Allocate the at-risk backorders to another DC that can still meet each promise. Orders become split shipments where needed.',
  repromise_orders: 'Set new promise dates for orders no source can meet. A customer update is drafted for approval.',
  emergency_replenishment: 'Create an express transfer to the store. Units are reserved at the source immediately.',
  resubmit_order: 'Confirm the corrected address with the customer and resubmit the carrier booking.',
}
export function confirmAction(ctx, exId, opt) {
  const ex = ctx.S.exceptions.find((e) => e.id === exId)
  const qty = opt.action === 'emergency_replenishment' ? h('input', { class: 'input', type: 'number', min: 1, value: opt.args.qty, style: 'width:90px', 'aria-label': 'Units' }) : null
  modal({
    title: opt.label, body: h('div', {}, h('p', { style: 'margin-top:0' }, h('b', {}, ex ? ex.title : exId)), h('p', {}, opt.detail || ACTION_TEXT[opt.action]), h('p', { class: 'muted sm' }, ACTION_TEXT[opt.action]),
      qty ? field('Units', qty) : null, h('p', { class: 'muted sm' }, 'Changes demo records only. Messages follow the communication rules and policy.')),
    actions: [{ label: 'Cancel' }, { label: 'Confirm', primary: true, run: async (close) => { const ok = await ctx.act(`/api/exceptions/${exId}/actions`, { action: opt.action, args: qty ? { ...opt.args, qty: +qty.value } : opt.args || {} }); if (ok) close(); return !ok } }],
  })
}

// ---------- Action queue ----------
export function queuePage(ctx) {
  const { S, sel } = ctx
  const f = (ctx.filters.queue ||= { focus: 'open' })
  const isOpen = (e) => e.status !== 'Resolved'
  const tests = { open: isOpen, p1: (e) => isOpen(e) && e.priority === 'P1', orders: (e) => isOpen(e) && e.orders.length > 0, stores: (e) => isOpen(e) && e.stores.length > 0, resolved: (e) => !isOpen(e) }
  const count = (key) => S.exceptions.filter(tests[key]).length, rows = S.exceptions.filter(tests[f.focus]), k = S.kpis
  if (!rows.some((r) => r.id === sel.ex)) sel.ex = rows[0] ? rows[0].id : null
  const tile = (key, v, label, t, tip) => [v, label, t, tip, { on: f.focus === key, click: () => { f.focus = key; ctx.render() } }]
  const row = (e) => {
    const [head, ...rest] = e.title.split(' · ')
    const pills = [e.orders.length ? `${e.orders.length} ${e.orders.length === 1 ? 'order' : 'orders'}` : null, e.stores.length ? `${e.stores.length} ${e.stores.length === 1 ? 'store' : 'stores'}` : null].filter(Boolean)
    return h('button', { class: `inb ${e.priority === 'P1' ? 'crit' : e.priority === 'P2' ? 'warn' : ''}${e.id === sel.ex ? ' sel' : ''}${ctx.flash.has(e.record_id) ? ' flash' : ''}`, role: 'option', 'aria-selected': String(e.id === sel.ex), title: e.title, onClick: () => ctx.pick('ex', e.id) },
      h('div', { class: 'inb-top' }, chip(e.priority), h('span', { class: 'inb-t' }, head), e.status !== 'Open' ? chip(e.status) : null, h('span', { class: 'inb-age' }, age(heldHours(e)))),
      h('div', { class: 'inb-s' }, h('span', {}, rest.join(' · ') || e.kind_label), pills.length ? h('em', {}, pills.join(' · ')) : null))
  }
  const list = h('div', { class: 'inbox', role: 'listbox', 'aria-label': 'Exceptions' }, rows.length ? rows.map(row) : h('div', { class: 'empty' }, 'Nothing here.'))
  return h('div', { class: 'qpage' },
    stats([tile('open', count('open'), 'Open exceptions', '', 'Exceptions not yet resolved. Click any number to filter the list.'), tile('p1', count('p1'), 'P1', count('p1') ? 'crit' : '', S.rules[0]),
      tile('orders', k.orders_at_risk, 'Orders at risk', k.orders_at_risk ? 'warn' : '', 'Customer orders projected to miss their promised date, or blocked.'),
      tile('stores', k.stores_short, 'Stores facing shortage', k.stores_short ? 'warn' : '', 'Stores projected to run out before their replenishment arrives.'), tile('resolved', count('resolved'), 'Resolved', 'ok', 'Closed exceptions.')]),
    h('div', { class: 'qgrid' }, list, sel.ex ? workspace(ctx, S.exceptions.find((e) => e.id === sel.ex)) : null))
}

function workspace(ctx, ex) {
  const panel = h('div', { class: 'panel ws', 'aria-busy': 'true' }, h('div', { class: 'pad' }, h('div', { class: 'skel', style: 'width:70%;height:24px' }), h('div', { class: 'skel', style: 'width:100%;height:220px;margin-top:16px' }), h('div', { class: 'skel', style: 'width:100%;height:90px;margin-top:12px' })))
  const token = ++ctx.seq.ws
  fetch(`/api/exceptions/${ex.id}`).then((r) => r.json()).then((w) => { if (token === ctx.seq.ws) { panel.removeAttribute('aria-busy'); panel.replaceChildren(workspaceBody(ctx, ex, w)) } })
  return panel
}

function workspaceBody(ctx, ex, w) {
  const { S } = ctx, a = w.assessment, im = w.impact, resolved = ex.status === 'Resolved', rec = a.options[0], more = a.options.slice(1)
  const open = w.messages.filter((n) => ['Awaiting approval', 'Draft', 'Failed'].includes(n.status)).length
  const goRecord = () => (ex.record_type === 'order' ? ctx.go('orders', { order: ex.record_id }) : ctx.go('network', { transfer: ex.record_id, facility: null }))
  const viz = !resolved && ex.record_type === 'order' ? journey(ctx, ex) : null
  const details = () => {
    const t = ex.record_type === 'transfer' ? S.transfers.find((x) => x.transfer_id === ex.record_id) : null
    const o = ex.record_type === 'order' ? S.orders.find((x) => x.order_id === ex.record_id) : null
    return h('div', {},
      t ? kv([['Route', `${t.source_name} → ${t.destination_name} · ${t.mode}, ${t.carrier}`], ['Contents', t.lines.map((l) => `${l.qty} × ${l.sku}`).join(', ')], ['Planned arrival', nice(t.planned_arrival)],
        ['Current ETA', [nice(t.eta), im.delay_h ? chip(`+${Math.round(im.delay_h)} h`, 'warn') : null]], ['Usable at destination', nice(im.ready_at)]])
        : o ? kv([['Customer', `${o.customer_ref} · ${o.city}`], ['Promise', nice(o.promised_by)], ['Items', o.items.map((i) => `${i.qty} × ${i.sku} (${i.allocation.replace('_', ' ')})`).join(', ')]]) : null,
      im && im.orders.length ? [h('div', { class: 'sec' }, 'Customer orders'), table([
        { key: 'order_id', label: 'Order' }, { key: 'item', label: 'Item', value: (r) => `${r.qty} × ${r.sku}` }, { key: 'promised_by', label: 'Promised', render: (r) => nice(r.promised_by) },
        { key: 'projected', label: 'Projected', render: (r) => nice(r.projected) }, { key: 'at_risk', label: 'Status', value: (r) => (r.at_risk ? 'At risk' : 'On time'), render: (r) => chip(r.at_risk ? 'At risk' : 'On time') }],
        { id: 'impact-orders', rows: im.orders.map((x, i) => ({ ...x, i })), rowId: (r) => String(r.i), onSelect: (_, r) => ctx.go('orders', { order: r.order_id }), filter: false, maxHeight: 240 })] : null,
      im && im.stock.length ? [h('div', { class: 'sec' }, `Stock at ${t.destination_name}`), table([
        { key: 'sku', label: 'SKU' }, { key: 'on_hand', label: 'On hand', align: 'r' }, { key: 'allocated', label: 'Allocated', align: 'r' }, { key: 'quarantined', label: 'Quarantined', align: 'r' },
        { key: 'available', label: 'Available', align: 'r' }, { key: 'incoming', label: 'Incoming', align: 'r' }, { key: 'gap', label: 'Needed beyond stock', align: 'r', value: (r) => im.gap[r.sku] || 0 }],
        { id: 'impact-stock', rows: im.stock, rowId: (r) => r.sku, filter: false })] : null,
      w.evidence.length ? [h('div', { class: 'sec' }, 'Evidence'), timeline(w.evidence.slice().reverse().map((e) => ({ t: `${nice(e.ts)} · ${e.source}`, title: pretty(e.event_type), detail: e.detail, tone: 'move' })))] : null)
  }
  const row = (o) => h('div', { class: 'opt', title: `Trade-off: ${o.tradeoff}` }, h('div', {}, h('b', {}, o.label), h('div', { class: 'sm' }, o.detail)),
    h('button', { class: 'btn sm', disabled: resolved, onClick: () => confirmAction(ctx, ex.id, o) }, 'Apply'))
  return h('div', { class: 'pad' },
    h('div', { class: 'ws-head' }, h('h2', { class: 'ws-title' }, ex.title.split(' · ')[0]), h('div', { class: 'spacer' }),
      h('button', { class: 'btn sm', disabled: !!ex.owner || resolved, onClick: () => ctx.act(`/api/exceptions/${ex.id}/assign`, {}) }, icon('user'), ex.owner ? ex.owner : 'Assign to me'),
      h('button', { class: 'btn sm', disabled: resolved, onClick: () => resolveDialog(ctx, ex) }, icon('check'), 'Resolve'),
      h('button', { class: 'btn ghost sm', title: `Open ${ex.record_id}`, 'aria-label': `Open ${ex.record_id}`, onClick: goRecord }, icon('open')),
      h('button', { class: 'btn ghost sm', title: 'Ask the assistant about this', 'aria-label': 'Ask the assistant', onClick: () => ctx.openAssistant({ exception_id: ex.id }) }, icon('spark'))),
    h('div', { class: 'chips' }, chip(ex.priority), chip(ex.status)),
    viz ? h('div', { class: 'viz-wrap' }, viz) : null,
    resolved ? h('div', { class: 'finding' }, h('span', { class: 'lbl' }, 'Resolution'), ex.resolution || 'Resolved.')
      : rec ? h('div', { class: 'rec' }, h('div', { class: 'rec-l' }, h('span', { class: 'lbl' }, 'Recommended next step'), h('b', {}, rec.label), h('div', { class: 'sm' }, rec.detail), h('div', { class: 'meta' }, `Trade-off: ${rec.tradeoff}`)),
        h('button', { class: 'btn primary', onClick: () => confirmAction(ctx, ex.id, rec) }, 'Review and apply'))
        : h('div', { class: 'finding' }, a.finding),
    more.length && !resolved ? h('details', { class: 'fold plain' }, h('summary', {}, `${more.length} other options`), h('div', {}, more.map(row))) : null,
    tabs(ctx, 'ws', [{ id: 'messages', label: 'Messages', n: open || '', render: () => {
        const todo = w.messages.filter((n) => ['Awaiting approval', 'Draft', 'Failed'].includes(n.status)), done = w.messages.filter((n) => !todo.includes(n))
        if (!w.messages.length) return h('p', { class: 'muted' }, 'No messages yet. Rules draft them when stores, DCs or customers are affected.')
        return h('div', {}, todo.map((n) => messageCard(ctx, n)), done.length ? h('details', { class: 'fold plain', open: !todo.length }, h('summary', {}, `${done.length} sent or closed`), h('div', { style: 'padding-top:6px' }, done.map((n) => messageCard(ctx, n)))) : null)
      } },
      { id: 'details', label: 'Details', render: details },
      { id: 'history', label: 'History', render: () => (w.history.length ? timeline(w.history.map((x) => ({ t: nice(x.ts), title: `${x.action} · ${x.actor}`, detail: x.detail }))) : h('p', { class: 'muted' }, 'No history yet. Decisions and system actions appear here.')) }]))
}

function resolveDialog(ctx, ex) {
  const note = h('textarea', { class: 'input', rows: 3, style: 'width:100%', placeholder: 'What was decided and why', 'aria-label': 'Resolution note' })
  modal({ title: 'Resolve exception', body: h('div', {}, h('p', { style: 'margin-top:0' }, h('b', {}, ex.title)), note),
    actions: [{ label: 'Cancel' }, { label: 'Resolve', primary: true, run: async (close) => { if (!note.value.trim()) { note.focus(); return true } const ok = await ctx.act(`/api/exceptions/${ex.id}/resolve`, { note: note.value }); if (ok) close(); return !ok } }] })
}

// ---------- Supply network ----------
export function networkPage(ctx) {
  const { S, sel } = ctx
  const t = S.transfers.find((x) => x.transfer_id === sel.transfer), fac = S.facilities.find((x) => x.facility_id === sel.facility)
  const rows = S.transfers.filter((x) => x.open)
  const tbl = table([
    { key: 'transfer_id', label: 'Transfer' }, { key: 'kind', label: 'Flow' }, { key: 'source_name', label: 'From' }, { key: 'destination_name', label: 'To' }, { key: 'units', label: 'Units', align: 'r' },
    { key: 'status', label: 'Status', render: (r) => [chip(r.status), r.depends_on ? chip('waiting', 'warn') : null] }, { key: 'eta', label: 'ETA', render: (r) => nice(r.eta) },
  ], { id: 'transfers', rows, rowId: (r) => r.transfer_id, selected: sel.transfer, onSelect: (id) => ctx.pick('transfer', id), maxHeight: 340, filter: true, dateOf: (r) => r.eta, facets: [{ label: 'Flow', value: (r) => r.kind }, { label: 'Status', value: (r) => r.status }] })
  const mapEl = networkMap(S, sel, (kind, id) => ctx.pick(kind, id))
  return h('div', {},
    S.config.tiles.ok ? null : h('div', { class: 'notice' }, `${S.config.tiles.message} The map may be blank; use the table for locations and routes.`),
    h('div', { class: 'split wide-left' },
      h('div', {}, mapEl, h('div', { class: 'sec', style: 'margin:14px 0 6px' }, 'Open transfers'), tbl),
      t ? transferDetail(ctx, t) : fac ? facilityDetail(ctx, fac) : null))
}

function transferDetail(ctx, t) {
  const { S } = ctx, events = S.events.filter((e) => e.record_id === t.transfer_id)
  return h('div', { class: 'panel sticky pad' },
    h('h2', { class: 'ws-title' }, `${t.transfer_id} · ${t.kind}`), h('div', { class: 'chips', style: 'margin-bottom:10px' }, chip(t.status), t.depends_on ? chip(`waits for ${t.depends_on}`, 'warn') : null),
    kv([['From', t.source_name], ['To', t.destination_name], ['Mode', `${t.mode} · ${t.carrier}`], ['Reference', t.reference],
      ['Departure', `planned ${nice(t.planned_departure)}${t.actual_departure ? ` · actual ${nice(t.actual_departure)}` : ''}`],
      ['Arrival', `planned ${nice(t.planned_arrival)} · ETA ${nice(t.eta)}${t.actual_arrival ? ` · actual ${nice(t.actual_arrival)}` : ''}`], ['Exception', t.exception || '—']]),
    table([{ key: 'sku', label: 'SKU' }, { key: 'product', label: 'Product', value: (l) => skuName(S, l.sku) }, { key: 'qty', label: 'Qty', align: 'r' }, { key: 'received', label: 'Received', align: 'r' }],
      { id: 'tr-lines', rows: t.lines, rowId: (l) => l.sku, filter: false }),
    h('div', { class: 'sec' }, 'Milestones'),
    events.length ? timeline(events.map((e) => ({ t: `${nice(e.ts)} · ${e.source}`, title: pretty(e.event_type), detail: e.detail, tone: eventTone(e) }))) : h('p', { class: 'muted' }, 'No events yet.'),
    t.exception_id ? h('button', { class: 'btn', onClick: () => ctx.go('queue', { ex: t.exception_id }) }, 'Open exception', icon('open')) : null)
}

function facilityDetail(ctx, f) {
  const { S } = ctx, pos = S.positions.filter((p) => p.facility_id === f.facility_id)
  const inbound = S.transfers.filter((t) => t.destination === f.facility_id && t.open), outbound = S.transfers.filter((t) => t.source === f.facility_id && t.open)
  const orders = S.orders.filter((o) => ['Created', 'Allocated', 'Picked', 'Packed'].includes(o.status) && o.items.some((i) => i.facility_id === f.facility_id || (i.awaiting_transfer && S.transfers.find((t) => t.transfer_id === i.awaiting_transfer)?.destination === f.facility_id)))
  return h('div', { class: 'panel sticky pad' },
    h('h2', { class: 'ws-title' }, f.name), h('div', { class: 'chips', style: 'margin-bottom:10px' }, chip(f.facility_type, 'idle'), h('span', { class: 'meta' }, `${f.city}, ${f.country} · ${f.contact}`)),
    pos.length ? table([{ key: 'sku', label: 'SKU' }, { key: 'on_hand', label: 'On hand', align: 'r' }, { key: 'allocated', label: 'Allocated', align: 'r' }, { key: 'reserved', label: 'Reserved', align: 'r' },
      { key: 'quarantined', label: 'Quarantined', align: 'r' }, { key: 'available', label: 'Available', align: 'r' }, { key: 'incoming', label: 'Incoming', align: 'r' }],
      { id: 'fac-stock', rows: pos, rowId: (p) => p.sku, onSelect: (_, p) => ctx.go('inventory', { pos: `${p.sku}|${p.facility_id}` }), filter: false, maxHeight: 280 }) : null,
    kv([['Inbound', inbound.map((t) => `${t.transfer_id} (${t.status})`).join(', ') || 'none'], ['Outbound', outbound.map((t) => `${t.transfer_id} (${t.status})`).join(', ') || 'none'], ['Open orders', orders.map((o) => o.order_id).join(', ') || 'none']]))
}

// ---------- Inventory ----------
export function inventoryPage(ctx) {
  const { S, sel } = ctx
  const f = (ctx.filters.inventory ||= {})
  f.bucket ||= 'all'; f.sku ||= 'All SKUs'
  const all = S.positions.map((p) => ({ ...p, key: `${p.sku}|${p.facility_id}` })), base = all.filter((p) => f.sku === 'All SKUs' || p.sku === f.sku)
  const sum = (k) => base.reduce((n, r) => n + r[k], 0), rows = f.bucket === 'all' ? base : base.filter((r) => r[f.bucket] > 0)
  const cur = rows.find((r) => r.key === sel.pos)
  const tile = (key, label, t, tip) => [num(sum(key === 'all' ? 'on_hand' : key)), label, t, tip, { on: f.bucket === key, click: () => { f.bucket = f.bucket === key ? 'all' : key; ctx.render() } }]
  return h('div', { class: 'qpage' },
    stats([tile('all', 'On hand'), tile('allocated', 'Allocated to orders', '', 'Click to show only rows with allocated units.'), tile('reserved', 'Reserved for transfers'), tile('quarantined', 'Quarantined', sum('quarantined') ? 'warn' : ''),
      tile('available', 'Available', 'ok', 'On hand − allocated − reserved − quarantined.'), tile('incoming', 'Incoming', '', 'Units on open inbound transfers. Not part of on hand.')]),
    f.sku !== 'All SKUs' ? h('div', { class: 'chips', style: 'margin:-4px 0 10px' }, h('button', { class: 'btn sm', onClick: () => { f.sku = 'All SKUs'; ctx.render() } }, `SKU ${f.sku}`, icon('x'))) : null,
    h('div', { class: 'split wide-left' },
      table([{ key: 'facility', label: 'Facility' }, { key: 'sku', label: 'SKU' }, { key: 'on_hand', label: 'On hand', align: 'r' }, { key: 'allocated', label: 'Allocated', align: 'r' }, { key: 'reserved', label: 'Reserved', align: 'r' },
        { key: 'quarantined', label: 'Quarantined', align: 'r' }, { key: 'available', label: 'Available', align: 'r', title: 'On hand − allocated − reserved − quarantined. Incoming and in-transit units are not part of on hand.', render: (r) => h('b', {}, r.available) }, { key: 'incoming', label: 'Incoming', align: 'r' },
        { key: 'backordered', label: 'Backordered', align: 'r' }, { key: 'cover_days', label: 'Cover (days)', align: 'r', title: 'Available units divided by average daily sales (stores only)', value: (r) => r.cover_days ?? -1, render: (r) => (r.cover_days == null ? '—' : r.cover_days) }],
        { id: 'inv', rows, rowId: (r) => r.key, selected: sel.pos, onSelect: (id) => ctx.pick('pos', id), maxHeight: 560, filter: true, facets: [{ label: 'Facility', value: (r) => r.facility }, { label: 'SKU', value: (r) => r.sku }], empty: 'No stock positions match.' }),
      cur ? positionDetail(ctx, cur) : null))
}

function positionDetail(ctx, p) {
  const { S } = ctx
  const st = (ctx.ui.pos ||= { open: null })
  const allocated = S.orders.filter((o) => ['Created', 'Allocated', 'Picked', 'Packed'].includes(o.status) && o.items.some((i) => i.allocation === 'allocated' && i.sku === p.sku && i.facility_id === p.facility_id))
  const inbound = S.transfers.filter((t) => t.destination === p.facility_id && t.open && t.lines.some((l) => l.sku === p.sku))
  const outbound = S.transfers.filter((t) => t.source === p.facility_id && ['Planned', 'Loading'].includes(t.status) && t.lines.some((l) => l.sku === p.sku))
  const back = S.orders.filter((o) => o.items.some((i) => i.allocation === 'awaiting_inbound' && i.sku === p.sku && inbound.some((t) => t.transfer_id === i.awaiting_transfer)))
  const img = S.skus[p.sku].image
  const parts = [['available', 'Available', p.available, 'ok', 'Free to allocate to new orders.'], ['allocated', 'Allocated to orders', p.allocated, 'move', 'Held for customer orders not yet shipped.'],
    ['reserved', 'Reserved for transfers', p.reserved, 'warn', 'Held for outbound transfers.'], ['quarantined', 'Quarantined', p.quarantined, 'crit', 'Damaged or under inspection. Not sellable.']]
    .filter(([k, , n]) => n > 0 || k === 'available')
  const color = { ok: '#2F8A3F', move: '#2F6DB5', warn: '#E0A21B', crit: '#C0334A' }
  const links = (list, fn) => h('div', { class: 'chips', style: 'margin-top:8px' }, list.map(fn))
  const related = {
    allocated: () => links(allocated, (o) => link(o.order_id, () => ctx.go('orders', { order: o.order_id }))),
    reserved: () => links(outbound, (t) => link(`${t.transfer_id}${t.depends_on ? ' (waits on inbound)' : ''}`, () => ctx.go('network', { transfer: t.transfer_id, facility: null }))),
    quarantined: () => h('p', { class: 'meta', style: 'margin:8px 0 0' }, 'Returns and damaged goods wait here until inspected.'),
    available: () => h('p', { class: 'meta', style: 'margin:8px 0 0' }, 'Nothing is holding these units.'),
  }
  const box = h('div', { class: 'part-detail' }), bar = h('div', { class: 'stack', role: 'group', 'aria-label': 'Stock breakdown' }), legend = h('div', { class: 'chips' })
  const paint = () => {
    const cur = parts.find((x) => x[0] === st.open)
    bar.replaceChildren(...parts.filter((x) => x[2] > 0).map(([k, label, n, t]) => h('button', {
      style: `flex:${n};background:${color[t]};opacity:${!cur || cur[0] === k ? 1 : 0.35}`, title: `${label}: ${n}`, 'aria-label': `${label}: ${n}`, onClick: () => { st.open = st.open === k ? null : k; paint() } })))
    legend.replaceChildren(...parts.map(([k, label, n, t]) => h('button', { class: 'pill', 'aria-pressed': String(st.open === k), onClick: () => { st.open = st.open === k ? null : k; paint() } },
      h('i', { class: 'dot', style: `background:${color[t]}` }), `${label} ${n}`)))
    if (cur) box.replaceChildren(h('div', {}, h('div', { class: 'sm muted' }, cur[4]), related[cur[0]]()))
    else box.replaceChildren()
  }
  paint()
  return h('div', { class: 'panel sticky pad' },
    h('div', { class: 'item', style: 'border:0;padding-top:0' }, img ? h('img', { class: 'thumb', src: `/assets/products/${img}`, alt: p.product }) : h('div', { class: 'thumb' }), h('div', { class: 'grow' }, h('b', {}, p.product), h('div', { class: 'meta' }, p.facility))),
    h('div', { class: 'big-row' }, h('span', { class: 'big' }, p.available), h('span', { class: 'meta' }, `available of ${p.on_hand} on hand`)),
    bar, legend, box,
    p.incoming ? h('div', { class: 'sec' }, `Incoming ${p.incoming}${p.in_transit ? ` (${p.in_transit} in transit)` : ''}`) : null,
    p.incoming ? links(inbound, (t) => link(`${t.transfer_id} · ETA ${nice(t.eta)}`, () => ctx.go('network', { transfer: t.transfer_id, facility: null }))) : null,
    back.length ? [h('div', { class: 'sec' }, 'Orders waiting on this stock'), links(back, (o) => link(o.order_id, () => ctx.go('orders', { order: o.order_id })))] : null)
}

// ---------- Orders ----------
export function ordersPage(ctx) {
  const { S, sel } = ctx
  const f = (ctx.filters.orders ||= { group: 'all' })
  const groups = { all: () => true, risk: (o) => o.risk, stock: (o) => ['Awaiting stock', 'Allocation failed', 'Rejected'].includes(o.state), shipped: (o) => o.status === 'Shipped', done: (o) => ['Delivered', 'Returned', 'Return in transit'].includes(o.status) }
  const count = (g) => S.orders.filter(groups[g]).length, rows = S.orders.filter(groups[f.group])
  if (!rows.some((o) => o.order_id === sel.order)) sel.order = rows[0] ? rows[0].order_id : null
  const cur = S.orders.find((o) => o.order_id === sel.order)
  const tile = (g, label, t, tip) => [count(g), label, t, tip, { on: f.group === g, click: () => { f.group = g; ctx.render() } }]
  return h('div', { class: 'qpage' },
    stats([tile('all', 'All orders'), tile('risk', 'At risk', count('risk') ? 'crit' : '', 'Projected to miss the promise, or blocked.'), tile('stock', 'Waiting on stock', count('stock') ? 'warn' : ''), tile('shipped', 'Shipped', 'move'), tile('done', 'Delivered or returned', 'ok')]),
    h('div', { class: 'split wide-left' },
      table([{ key: 'order_id', label: 'Order' }, { key: 'channel', label: 'Channel' }, { key: 'state', label: 'State', render: (r) => chip(r.state) }, { key: 'city', label: 'City' }, { key: 'promised_by', label: 'Promised', render: (r) => nice(r.promised_by) },
        { key: 'projected', label: 'Projected', render: (r) => (r.projected ? nice(r.projected) : '—') }, { key: 'risk', label: 'Risk', value: (r) => (r.risk ? 'At risk' : 'On time'), render: (r) => chip(r.risk ? 'At risk' : 'On time') }, { key: 'units', label: 'Items', align: 'r' }],
        { id: 'orders', rows, rowId: (r) => r.order_id, selected: sel.order, onSelect: (id) => ctx.pick('order', id), flash: ctx.flash, maxHeight: 600, filter: true, dateOf: (r) => r.promised_by, facets: [{ label: 'State', value: (r) => r.state }, { label: 'Promised day', value: (r) => (r.promised_by || '').slice(0, 10), fmt: v=>new Date(v).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'}) }, { label: 'City', value: (r) => r.city }] }),
      cur ? orderDetail(ctx, cur) : null))
}

function orderDetail(ctx, o) {
  const { S } = ctx
  const events = S.events.filter((e) => e.record_id === o.order_id), msgs = S.notifications.filter((n) => n.recipient_ref === o.order_id && n.status !== 'Superseded')
  const ex = S.exceptions.find((e) => e.status !== 'Resolved' && (e.record_id === o.order_id || e.orders.includes(o.order_id)))
  const waits = [...new Set(o.items.map((i) => i.awaiting_transfer).filter(Boolean))]
  const split = new Set(o.items.map((i) => i.facility_id).filter(Boolean)).size > 1
  return h('div', { class: 'panel sticky pad' },
    h('h2', { class: 'ws-title' }, o.order_id), h('div', { class: 'chips', style: 'margin-bottom:10px' }, chip(o.state), chip(o.channel, 'idle'), h('span', { class: 'meta' }, `${o.customer_ref} · ${o.customer_email_masked} · ${o.city}, ${o.country}`)),
    kv([['Created', nice(o.created_at)], ['Promised', nice(o.promised_by)], ['Projected', o.projected ? nice(o.projected) : 'unknown'], ['Carrier', o.carrier ? `${o.carrier} · ${o.tracking_code}` : '—'],
      ['Last scan', o.last_scan_at ? `${nice(o.last_scan_at)} · ${o.last_scan_location}` : '—'], o.pickup_store ? ['Collect at', o.pickup_store_name] : ['Ship to', o.city]]),
    split ? h('p', { class: 'meta' }, 'Split fulfilment: items ship from different facilities.') : null,
    o.items.map((i) => h('div', { class: 'item' }, i.image ? h('img', { class: 'thumb', src: `/assets/products/${i.image}`, alt: i.name }) : h('div', { class: 'thumb' }),
      h('div', { class: 'grow' }, h('b', {}, i.name), h('div', { class: 'meta' }, `Size ${i.size} · qty ${i.qty}`), h('div', { class: 'chips', style: 'margin-top:3px' }, chip(i.allocation.replace('_', ' ').replace(/^./, (c) => c.toUpperCase()), i.allocation === 'awaiting_inbound' ? 'warn' : tone(i.allocation)),
        h('span', { class: 'meta' }, i.facility_id ? S.facilities.find((f) => f.facility_id === i.facility_id).name : i.awaiting_transfer ? `waits for ${i.awaiting_transfer}` : 'no stock'))))),
    h('div', { class: 'actions', style: 'margin:12px 0' },
      h('button', { class: 'btn', onClick: () => ctx.preview(o.order_id) }, icon('eye'), 'Customer tracking preview'),
      waits.map((t) => link(`Open ${t}`, () => ctx.go('network', { transfer: t, facility: null }))), ex ? link(`Open exception ${ex.priority}`, () => ctx.go('queue', { ex: ex.id })) : null,
      o.issue === 'INTEGRATION_REJECTED' ? h('button', { class: 'btn', onClick: () => ctx.act(`/api/orders/${o.order_id}/resubmit`, {}) }, 'Resubmit after address check') : null,
      o.status === 'Returned' && o.items.some((i) => i.allocation === 'returned') ? h('button', { class: 'btn', onClick: () => ctx.act(`/api/orders/${o.order_id}/restock`, {}) }, 'Inspect and restock') : null),
    tabs(ctx, 'order', [{ id: 'tl', label: 'Timeline', render: () => (events.length ? timeline(events.slice().reverse().map((e) => ({ t: nice(e.ts), title: pretty(e.event_type), detail: e.detail, tone: /REJECTED|FAILED/.test(e.event_type) ? 'crit' : 'move' }))) : h('p', { class: 'muted' }, 'No events.')) },
      { id: 'msg', label: 'Customer messages', n: msgs.length || '', render: () => (msgs.length ? msgs.map((n) => messageCard(ctx, n)) : h('p', { class: 'muted' }, 'No customer messages.')) }]))
}

// ---------- Communications ----------
export function commsPage(ctx) {
  const { S, sel } = ctx
  const f = (ctx.filters.comms ||= { view: 'todo' })
  const ns = S.notifications, groups = { todo: ['Awaiting approval', 'Draft', 'Failed'], failed: ['Failed'], sent: ['Simulated send', 'Sent'], all: null }
  const count = (g) => ns.filter((n) => !groups[g] || groups[g].includes(n.status)).length, rows = ns.filter((n) => !groups[f.view] || groups[f.view].includes(n.status))
  if (!rows.some((n) => n.notification_id === sel.nt)) sel.nt = rows[0] ? rows[0].notification_id : null
  const cur = ns.find((n) => n.notification_id === sel.nt)
  const tile = (g, label, t, tip) => [count(g), label, t, tip, { on: f.view === g, click: () => { f.view = g; ctx.render() } }]
  return h('div', { class: 'qpage' },
    stats([tile('todo', 'Needs action', count('todo') ? 'warn' : '', 'Awaiting approval, drafts and failed deliveries.'), tile('failed', 'Failed', count('failed') ? 'crit' : ''), tile('sent', 'Sent', 'ok'), tile('all', 'All messages')]),
    h('div', { class: 'split' },
      table([{ key: 'status', label: 'Status', render: (n) => chip(n.status) }, { key: 'audience', label: 'Audience' }, { key: 'recipient', label: 'Recipient' }, { key: 'subject', label: 'Subject', wrap: true }, { key: 'created_at', label: 'Created', render: (n) => nice(n.created_at) }],
        { id: 'comms', rows, rowId: (n) => n.notification_id, selected: sel.nt, onSelect: (id) => ctx.pick('nt', id), maxHeight: 600, filter: true, dateOf: (n) => n.created_at, facets: [{ label: 'Status', value: (n) => n.status }, { label: 'Audience', value: (n) => n.audience }], empty: 'Nothing here.' }),
      cur ? h('div', { class: 'panel sticky pad' }, messageCard(ctx, cur, true),
        h('details', { class: 'fold plain' }, h('summary', {}, 'Details and history'), h('div', {},
          kv([['Rule', cur.rule_id], ['Triggered by', cur.trigger_event], ['Approval', cur.requires_approval ? 'required' : 'not required'], ['Attempts', cur.attempts], ['Approved by', cur.approved_by || '—']]),
          timeline(cur.history.slice().reverse().map((x) => ({ t: x.split(' · ')[0].replace('T', ' '), title: x.split(' · ').slice(1).join(' · ') }))))),
        h('button', { class: 'btn ghost', onClick: () => ctx.go('queue', { ex: cur.exception_id }) }, 'Open exception', icon('open'))) : null))
}

// ---------- Activity & audit ----------
export function activityPage(ctx) {
  const { S } = ctx, m = S.demo.metrics, dup = S.events.filter((e) => e.outcome === 'duplicate ignored').length, rej = S.events.filter((e) => e.outcome.startsWith('rejected')).length
  const hrs = (v) => (v == null ? '—' : `${v} h`)
  return h('div', {},
    stats([[m.open, 'Open exceptions'], [m.resolved, 'Resolved', 'ok'], [hrs(m.resolve_h), 'Avg time to resolve', '', 'Demo clock: detection to resolution.'], [S.events.length, 'Events received', rej || dup ? 'warn' : '', `${dup} duplicates ignored, ${rej} rejected. See the event log.`]]),
    tabs(ctx, 'activity', [
      { id: 'audit', label: 'Audit log', render: () => table([{ key: 'ts', label: 'Time', render: (a) => nice(a.ts) }, { key: 'actor', label: 'Actor' }, { key: 'action', label: 'Action' }, { key: 'record_id', label: 'Record' }, { key: 'detail', label: 'Detail', wrap: true }], { id: 'audit', rows: S.audit, rowId: (a) => a.ts + a.action + a.record_id + a.detail, filter: true, dateOf: (a) => a.ts, facets: [{ label: 'Actor', value: (a) => a.actor }, { label: 'Action', value: (a) => a.action }], maxHeight: 560 }) },
      { id: 'events', label: 'Event log', render: () => table([{ key: 'event_id', label: 'Event' }, { key: 'ts', label: 'Time', render: (e) => nice(e.ts) }, { key: 'event_type', label: 'Type' }, { key: 'record_id', label: 'Record' }, { key: 'source', label: 'Source' }, { key: 'outcome', label: 'Outcome', render: (e) => chip(e.outcome) }, { key: 'detail', label: 'Detail', wrap: true }],
        { id: 'events', rows: S.events, rowId: (e, i) => e.event_id + e.outcome + e.ts, filter: true, dateOf: (e) => e.ts, facets: [{ label: 'Type', value: (e) => e.event_type }, { label: 'Outcome', value: (e) => e.outcome }], maxHeight: 560 }) },
      { id: 'sim', label: 'Simulate events', render: () => simulatePanel(ctx) }]))
}

const TRANSFER_EVENTS = [
  ['delay', 'Delay', 'Carrier reports a delay and a new ETA. Dependent transfers, stores and orders are re-checked.'],
  ['customs_hold', 'Customs hold', 'Puts the shipment on hold at customs. It cannot move until released.'],
  ['customs_released', 'Customs released', 'Releases the hold so haulage can continue.'],
  ['departed', 'Departed', 'The goods leave the source. Stock moves out of on-hand there.'],
  ['arrived', 'Arrived', 'The shipment reaches the destination, before goods-in.'],
  ['received', 'Received in full', 'All lines are received into stock and waiting orders are allocated.'],
]
const ORDER_EVENTS = [
  ['scan', 'Carrier scan', 'A parcel scan updates the last known location.'], ['delay', 'Carrier delay', 'Flags the shipment as delayed.'],
  ['picked', 'Picked', 'Items are picked in the warehouse.'], ['packed', 'Packed', 'The parcel is packed and labelled.'],
  ['shipped', 'Shipped', 'Hands the parcel to the carrier. Stock leaves the facility.'], ['delivered', 'Delivered', 'The customer has received the order.'],
]

function choices(options, get, set) {
  const box = h('div', { class: 'chips', role: 'group' })
  const paint = () => box.replaceChildren(...options.map(([id, label]) => h('button', { class: 'pill', 'aria-pressed': String(get() === id), onClick: () => { set(id); paint() } }, label)))
  paint()
  return box
}

function simulatePanel(ctx) {
  const { S } = ctx
  const st = (ctx.ui.sim ||= { tk: 'delay', hours: 24, ok: 'scan', tid: null, oid: null, rid: null })
  const open = S.transfers.filter((t) => t.open)
  if (!open.some((t) => t.transfer_id === st.tid)) st.tid = (open.find((t) => t.transfer_id === 'TR-5301') || open[0] || {}).transfer_id
  if (!S.orders.some((o) => o.order_id === st.oid)) st.oid = S.orders[0].order_id
  const replayable = S.events.filter((e) => e.outcome === 'applied').slice(0, 12)
  if (!replayable.some((e) => e.event_id === st.rid)) st.rid = replayable[0] && replayable[0].event_id

  const send = async (path, body) => { const r = await ctx.act(path, body, { quiet: true }); if (r) ctx.toastResult(r.message === 'applied' ? 'Event applied. Exceptions, messages and stock are updated; see Latest events.' : r.message === 'duplicate ignored' ? 'Duplicate ignored: nothing changed.' : r.message) }
  const sel = (items, get, set, label) => field(label, h('select', { class: 'select', 'aria-label': label, onChange: (e) => { set(e.target.value); refresh() } }, items.map(([v, l]) => h('option', { value: v, selected: v === get() }, l))))

  // transfer card
  const tPreview = h('div', { class: 'preview' }), tHours = h('div', { class: 'hours' })
  const paintT = () => {
    const t = S.transfers.find((x) => x.transfer_id === st.tid), ev = TRANSFER_EVENTS.find((e) => e[0] === st.tk)
    tHours.hidden = st.tk !== 'delay'
    tHours.replaceChildren(field('Delay', h('div', { class: 'chips' },
      [6, 12, 24, 48].map((n) => h('button', { class: 'pill', 'aria-pressed': String(st.hours === n), onClick: () => { st.hours = n; paintT() } }, `+${n} h`)),
      h('input', { class: 'input', type: 'number', min: 1, max: 240, value: st.hours, style: 'width:76px', 'aria-label': 'Hours', onInput: (e) => { st.hours = +e.target.value || 1; paintTPreview() } }))))
    paintTPreview()
    function paintTPreview() {
      const eta = t ? shiftIso(t.eta > S.now ? t.eta : S.now, st.hours) : ''
      tPreview.replaceChildren(h('b', {}, t ? `${t.transfer_id} · ${t.kind}` : 'No open transfer'), h('div', { class: 'sm' }, st.tk === 'delay' ? `New ETA ${nice(eta)} (currently ${nice(t.eta)}). ${ev[2]}` : ev[2]))
    }
  }
  const tCard = h('div', { class: 'panel sim' }, h('div', { class: 'panel-h' }, h('h3', {}, 'Disrupt or advance a transfer')),
    h('div', { class: 'pad' }, sel(open.map((t) => [t.transfer_id, `${t.transfer_id} · ${t.status} · ${t.source_name} → ${t.destination_name}`]), () => st.tid, (v) => { st.tid = v }, 'Transfer'),
      field('What happens', choices(TRANSFER_EVENTS, () => st.tk, (v) => { st.tk = v; paintT() })), tHours, tPreview,
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', disabled: !st.tid, onClick: () => send('/api/simulate/transfer', { transfer_id: st.tid, kind: st.tk, hours: st.hours }) }, icon('send'), 'Send event'))))
  // order card
  const oPreview = h('div', { class: 'preview' })
  const paintO = () => { const o = S.orders.find((x) => x.order_id === st.oid), ev = ORDER_EVENTS.find((e) => e[0] === st.ok); oPreview.replaceChildren(h('b', {}, `${o.order_id} · ${o.state}`), h('div', { class: 'sm' }, ev[2])) }
  paintO()
  const oCard = h('div', { class: 'panel sim' }, h('div', { class: 'panel-h' }, h('h3', {}, 'Update an order')),
    h('div', { class: 'pad' }, sel(S.orders.map((o) => [o.order_id, `${o.order_id} · ${o.state} · ${o.city}`]), () => st.oid, (v) => { st.oid = v }, 'Order'),
      field('What happens', choices(ORDER_EVENTS, () => st.ok, (v) => { st.ok = v; paintO() })), oPreview,
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', onClick: () => send('/api/simulate/order', { order_id: st.oid, kind: st.ok }) }, icon('send'), 'Send event'))))
  // replay card
  const rCard = h('div', { class: 'panel sim' }, h('div', { class: 'panel-h' }, h('h3', {}, 'Send the same event twice')),
    h('div', { class: 'pad' }, sel(replayable.map((e) => [e.event_id, `${e.event_id} · ${pretty(e.event_type)} · ${e.record_id}`]), () => st.rid, (v) => { st.rid = v }, 'Already processed event'),
      h('div', { class: 'actions', style: 'margin-top:12px' }, h('button', { class: 'btn', disabled: !st.rid, onClick: () => send('/api/simulate/replay', { event_id: st.rid }) }, icon('retry'), 'Replay as duplicate'))))
  const feed = h('div', { class: 'panel sim' }, h('div', { class: 'panel-h' }, h('h3', {}, 'Latest events')),
    h('div', { class: 'pad' }, timeline(S.events.slice(0, 6).map((e) => ({ t: `${nice(e.ts)} · ${e.event_id}`, title: `${pretty(e.event_type)} · ${e.record_id}`, detail: e.outcome === 'applied' ? e.detail : `${e.outcome}`, tone: eventTone(e) })))))
  const refresh = () => { paintT(); paintO() }
  paintT()
  return h('div', {}, h('div', { class: 'sim-grid' }, h('div', { class: 'sim-col' }, tCard, oCard), h('div', { class: 'sim-col' }, rCard, feed)))
}
