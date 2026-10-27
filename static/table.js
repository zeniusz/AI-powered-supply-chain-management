// Data table: sticky header, click-to-sort, built-in filter, keyboard selection, row flash for changed records.
import { h } from './util.js'

const memory = {} // filter + sort survive full page re-renders, keyed by table id

/**
 * columns: [{ key, label, align?, value?(row) -> sortable/filterable primitive, render?(row) -> Node|string, wrap?, sortable? }]
 * opts: { id, rows, rowId(row), selected, onSelect(id,row), maxHeight, filter (show box), flash (Set of ids), empty }
 */
export function table(columns, opts) {
  const m = (memory[opts.id] ||= { q: '', sort: null, f: {}, from: '', to: '' })
  const body = h('tbody')
  const head = h('tr', {})
  const text = (row, c) => (c.value ? c.value(row) : row[c.key])
  const sortVal = (row, c) => { const v = text(row, c); return typeof v === 'number' ? v : String(v ?? '').toLowerCase() }

  const paintHead = () => {
    head.replaceChildren(...columns.map((c) => {
      const active = m.sort && m.sort.key === c.key
      return h('th', {
        class: (c.align === 'r' ? 'r ' : '') + (c.sortable === false ? '' : 'sortable'), scope: 'col', title: c.title, 'aria-sort': active ? (m.sort.dir > 0 ? 'ascending' : 'descending') : 'none',
        onclick: c.sortable === false ? null : () => { m.sort = active && m.sort.dir < 0 ? null : { key: c.key, dir: active ? -1 : 1 }; paintHead(); paintBody() },
      }, c.label, active ? h('span', { class: 'arrow' }, m.sort.dir > 0 ? '▲' : '▼') : null)
    }))
  }

  const paintBody = () => {
    const q = m.q.trim().toLowerCase()
    let rows = opts.rows.filter((r) => !q || columns.map((c) => text(r, c)).join(' ').toLowerCase().includes(q))
    if ((m.from || m.to) && opts.dateOf) rows = rows.filter((r) => { const d = String(opts.dateOf(r) || '').slice(0, 10); return d && (!m.from || d >= m.from) && (!m.to || d <= m.to) })
    ;(opts.facets || []).forEach((fc, i) => { const v = m.f[i]; if (v) rows = rows.filter((r) => String(fc.value(r)) === v) })
    if (m.sort) {
      const c = columns.find((x) => x.key === m.sort.key)
      rows = [...rows].sort((a, b) => { const x = sortVal(a, c), y = sortVal(b, c); return (x < y ? -1 : x > y ? 1 : 0) * m.sort.dir })
    }
    body.replaceChildren(...rows.map((r) => {
      const id = opts.rowId(r)
      const tr = h('tr', {
        class: [opts.onSelect ? 'pick' : '', id === opts.selected ? 'sel' : '', opts.flash && opts.flash.has(id) ? 'flash' : ''].join(' ').trim(),
        tabindex: opts.onSelect ? 0 : null, 'data-id': id, 'aria-selected': opts.onSelect ? String(id === opts.selected) : null,
      }, columns.map((c) => h('td', { class: (c.align === 'r' ? 'r ' : '') + (c.wrap ? 'wrap' : '') }, c.render ? c.render(r) : (text(r, c) ?? '—'))))
      if (opts.onSelect) {
        tr.addEventListener('click', () => opts.onSelect(id, r))
        tr.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opts.onSelect(id, r) }
          if (e.key === 'ArrowDown' && tr.nextElementSibling) { e.preventDefault(); tr.nextElementSibling.focus() }
          if (e.key === 'ArrowUp' && tr.previousElementSibling) { e.preventDefault(); tr.previousElementSibling.focus() }
        })
      }
      return tr
    }))
    if (!rows.length) body.replaceChildren(h('tr', {}, h('td', { colspan: columns.length, class: 'wrap muted', style: 'padding:20px;text-align:center' }, opts.empty || 'Nothing matches.')))
  }

  paintHead(); paintBody()
  const showFilter = opts.filter ?? opts.rows.length > 8
  const input = h('input', { type: 'search', placeholder: 'Filter rows', 'aria-label': 'Filter rows', value: m.q, onInput: (e) => { m.q = e.target.value; paintBody() } })
  const facets = (opts.facets || []).map((fc, i) => {
    const vals = [...new Set(opts.rows.map((r) => String(fc.value(r))))].sort()
    if (m.f[i] && !vals.includes(m.f[i])) m.f[i] = ''
    return h('select', { class: 'input', 'aria-label': fc.label, onChange: (e) => { m.f[i] = e.target.value; paintBody() } },
      h('option', { value: '' }, `All ${fc.label.toLowerCase()}`), vals.map((v) => h('option', { value: v, selected: m.f[i] === v }, fc.fmt ? fc.fmt(v) : v)))
  })
  const dayKey = (r) => String(opts.dateOf(r) || '').slice(0, 10)
  const dateIn = (key, label) => h('input', { type: 'date', class: 'dayin', 'aria-label': label, title: label, value: m[key], onInput: (e) => { m[key] = e.target.value; paintBody() } })
  const dayBtn = opts.dateOf ? h('span', { class: 'dayrange' }, dateIn('from', 'From day'), '–', dateIn('to', 'To day')) : null
  const scroll = h('div', { class: 'tbl-scroll', style: opts.maxHeight ? `max-height:${opts.maxHeight}px` : '' }, h('table', {}, h('thead', {}, head), body))
  const el = h('div', { class: 'tbl' }, showFilter ? h('div', { class: 'tbl-bar' }, input, dayBtn, facets) : null, scroll)
  const sel = body.querySelector('tr.sel'); if (sel) requestAnimationFrame(() => sel.scrollIntoView({ block: 'nearest' }))
  return el
}
