// Custom SVG visuals drawn from live data: the ripple of a delayed transfer, the consequence timeline, an order journey.
import { h } from './util.js'

/** Order journey: the stage where the order is stuck is marked. */
export function journey(ctx, ex) {
  const o = ctx.S.orders.find((x) => x.order_id === ex.record_id)
  const stages = ['Created', 'Allocated', 'Picked', 'Packed', 'Shipped', 'Delivered'], at = Math.max(0, stages.indexOf(o.status))
  const stuck = !!o.issue
  return h('div', { class: 'vz-box' }, h('ol', { class: 'journey' }, stages.map((st, i) => h('li', { class: (i < at || (i === at && !stuck && o.status === 'Delivered') ? 'done ' : '') + (i === at ? (stuck ? 'stuck' : 'now') : '') },
    h('span', { class: 'dot' }), h('span', {}, st)))))
}
