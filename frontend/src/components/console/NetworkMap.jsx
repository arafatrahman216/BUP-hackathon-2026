import { geoBounds, geoMercator, geoPath } from 'd3-geo'
import { useCallback, useEffect, useRef, useState } from 'react'
import { feature } from 'topojson-client'
import topo from 'world-atlas/countries-110m.json'
import { cv, lvlColor, pct, pctN } from '../../utils/console/format'
import { FALLBACK_XY, LABEL_LEFT, LL } from '../../utils/console/network'
import styles from './Console.module.css'

const W = 640
const H = 520
const K_MAX = 5

let geoCache = null
/** Bangladesh and its neighbours projected into the 640 × 520 box (computed once). */
function getGeo() {
  if (geoCache) return geoCache
  try {
    const all = feature(topo, topo.objects.countries).features
    const near = all.filter((f) => {
      const [[x0, y0], [x1, y1]] = geoBounds(f)
      return x1 > 84 && x0 < 98 && y1 > 16 && y0 < 30
    })
    const proj = geoMercator().fitExtent([[20, 20], [620, 500]], { type: 'MultiPoint', coordinates: [[87.6, 26.8], [93.2, 20.5]] })
    const path = geoPath(proj)
    const land = near.map((f) => ({ id: f.id, d: path(f), bd: f.id === '050' })).filter((x) => x.d)
    const xy = {}
    for (const k of Object.keys(LL)) xy[k] = proj([LL[k][1], LL[k][0]])
    const lbl = { bd: proj([89.4, 25.4]), india: proj([88.3, 23.2]), india2: proj([92.4, 25.9]), myanmar: proj([93.0, 21.2]), bay: proj([90.2, 21.0]) }
    geoCache = { land, xy, lbl }
  } catch {
    geoCache = { land: [], xy: FALLBACK_XY, lbl: null }
  }
  return geoCache
}

const NS = { vectorEffect: 'non-scaling-stroke' }

/** Keep the zoomed layer covering the map box (no empty edges). */
function clampTo(el, z) {
  if (!el) return z
  const w = el.clientWidth
  const h = el.clientHeight
  return { k: z.k, x: Math.min(0, Math.max(w - w * z.k, z.x)), y: Math.min(0, Math.max(h - h * z.k, z.y)) }
}

function Label({ at, text, size = 12, italic = false, weight = 500 }) {
  return (
    <text x={at[0]} y={at[1]} fontSize={size} letterSpacing={italic ? 0 : '0.12em'} fill="var(--faint)" textAnchor="middle"
          fontStyle={italic ? 'italic' : 'normal'} fontWeight={weight} fontFamily="inherit">
      {text}
    </text>
  )
}

/**
 * Real Bangladesh geography with depots (squares), stations (rings coloured by lowest fuel %),
 * roads and trucks. Drag to pan, wheel or buttons to zoom; markers keep their size.
 */
export function NetworkMap({ stations, depots, roads, trucks, onOpen }) {
  const geo = getGeo()
  const xy = (key) => geo.xy[key] ?? FALLBACK_XY[key]
  const [z, setZ] = useState({ k: 1, x: 0, y: 0 })
  const [hover, setHover] = useState(null)
  const [dragging, setDragging] = useState(false)
  const mapRef = useRef(null)
  const drag = useRef(null)
  const moved = useRef(false)

  const clampZ = (next) => clampTo(mapRef.current, next)

  const zoomAt = useCallback((f, cx, cy) => {
    const el = mapRef.current
    if (!el) return
    const px = cx ?? el.clientWidth / 2
    const py = cy ?? el.clientHeight / 2
    setZ((s) => {
      const k = Math.min(K_MAX, Math.max(1, s.k * f))
      const r = k / s.k
      return clampTo(el, { k, x: px - (px - s.x) * r, y: py - (py - s.y) * r })
    })
  }, [setZ])

  // wheel zoom needs a non-passive listener so the page doesn't scroll
  useEffect(() => {
    const el = mapRef.current
    if (!el) return undefined
    const onWheel = (e) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  const panStart = (e) => {
    drag.current = { x: e.clientX, y: e.clientY, zx: z.x, zy: z.y }
    moved.current = false
  }
  const panMove = (e) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!moved.current && Math.abs(dx) + Math.abs(dy) < 4) return
    moved.current = true
    setDragging(true)
    setHover(null)
    setZ((s) => clampZ({ k: s.k, x: d.zx + dx, y: d.zy + dy }))
  }
  const panEnd = () => {
    drag.current = null
    setDragging(false)
    setTimeout(() => { moved.current = false }, 0)
  }

  const pos = (key) => {
    const p = xy(key)
    return p ? { left: `${(p[0] / W) * 100}%`, top: `${(p[1] / H) * 100}%` } : null
  }
  const inv = { '--inv': 1 / z.k }

  const nodes = [
    ...depots.map((d) => ({ id: d.id, key: d.key, name: d.name, depot: true, entity: d })),
    ...stations.map((s) => ({ id: s.id, key: s.key, name: s.name, depot: false, entity: s, c: lvlColor(s.minP) })),
  ].filter((n) => xy(n.key))

  const hovered = nodes.find((n) => n.id === hover)

  return (
    <div className={styles.mapWrap}>
      <div
        ref={mapRef}
        className={`${styles.map} ${dragging ? styles.mapDragging : ''}`}
        onMouseDown={panStart}
        onMouseMove={panMove}
        onMouseUp={panEnd}
        onMouseLeave={panEnd}
        role="group"
        aria-label="Network map"
      >
        <div className={styles.layer} style={{ transform: `translate(${z.x}px, ${z.y}px) scale(${z.k})` }}>
          <svg className={styles.mapSvg} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
            {geo.land.map((l) => (
              <path key={l.id} d={l.d} fill={l.bd ? 'var(--land)' : 'var(--land2)'} stroke="var(--landLine)"
                    strokeWidth={l.bd ? 1.3 : 0.8} strokeLinejoin="round" {...NS} />
            ))}
            {geo.lbl && (
              <>
                <Label at={geo.lbl.bd} text="BANGLADESH" size={13} weight={600} />
                <Label at={geo.lbl.india} text="INDIA" />
                <Label at={geo.lbl.india2} text="INDIA" />
                <Label at={geo.lbl.myanmar} text="MYANMAR" />
                <Label at={geo.lbl.bay} text="Bay of Bengal" size={14} italic />
              </>
            )}
            {roads.map((r) => {
              const a = xy(r.a)
              const b = xy(r.b)
              if (!a || !b) return null
              return (
                <g key={r.id}>
                  <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--surface)" strokeWidth={r.main ? 6 : 4}
                        strokeLinecap="round" opacity={0.9} {...NS} />
                  <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={r.closure ? 'var(--urgent)' : 'var(--road)'}
                        strokeWidth={r.main ? 2.8 : 2} strokeDasharray={r.closure ? '6 5' : r.main ? undefined : '5 5'}
                        strokeLinecap="round" {...NS} />
                </g>
              )
            })}
            {trucks.map((tr, i) => {
              const road = roads.find((r) => r.id === tr.road)
              const a = road && xy(road.a)
              const b = road && xy(road.b)
              if (!a || !b) return null
              return (
                <circle key={`tk${i}`} cx={a[0] + (b[0] - a[0]) * tr.p} cy={a[1] + (b[1] - a[1]) * tr.p} r={5 / z.k}
                        fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} {...NS} />
              )
            })}
          </svg>

          {nodes.map((n) => (
            <button
              key={n.id}
              type="button"
              className={styles.node}
              style={{ ...pos(n.key), ...inv }}
              onMouseEnter={() => !dragging && setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(n.id)}
              onBlur={() => setHover(null)}
              onClick={() => { if (!moved.current) { setHover(null); onOpen(n.id) } }}
              aria-label={`${n.name}${n.depot ? ' depot' : ' station'}`}
            >
              {n.depot ? <div className={styles.depotMark} /> : <div className={styles.stationMark} style={cv(n.c)} />}
              <span className={`${styles.nodeLabel} ${LABEL_LEFT[n.key] ? styles.nodeLabelLeft : ''}`}>{n.name}</span>
            </button>
          ))}

          {hovered && !dragging && (
            <div className={styles.tip} style={{ ...pos(hovered.key), ...inv }} role="tooltip">
              <span className={styles.tipName}>{hovered.name}{hovered.depot ? ' depot' : ''}</span>
              {hovered.entity.fuels.map((f) => (
                <div key={f.f} className={styles.tipRow}>
                  <span className={styles.muted}>{f.f}</span>
                  <div className={styles.barThin}><div className={styles.barFill} style={{ width: pct(f.lvl, f.cap), ...cv(lvlColor(pctN(f.lvl, f.cap))) }} /></div>
                  <span className={styles.tipPct}>{pct(f.lvl, f.cap)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className={styles.zoom} onMouseDown={(e) => e.stopPropagation()}>
          <button type="button" className={styles.zoomBtn} onClick={() => zoomAt(1.4)} aria-label="Zoom in">+</button>
          <button type="button" className={styles.zoomBtn} onClick={() => zoomAt(1 / 1.4)} aria-label="Zoom out">−</button>
          <button type="button" className={styles.zoomFit} onClick={() => setZ({ k: 1, x: 0, y: 0 })}>Fit</button>
        </div>
        <span className={styles.mapHint}>Scroll to zoom · drag to move</span>
      </div>

      <div className={styles.legend}>
        <span className={styles.legendItem}><span className={styles.swDepot} />Depot</span>
        <span className={styles.legendItem}><span className={styles.swRing} style={cv('var(--low)')} />Low &lt;25%</span>
        <span className={styles.legendItem}><span className={styles.swRing} style={cv('var(--mid)')} />Medium 25–50%</span>
        <span className={styles.legendItem}><span className={styles.swRing} style={cv('var(--good)')} />Good &gt;50%</span>
        <span className={styles.legendItem}><span className={styles.swDash} style={cv('var(--road)')} />Backup road</span>
        <span className={styles.legendItem}><span className={styles.swDash} style={cv('var(--urgent)')} />Closure ahead</span>
      </div>
    </div>
  )
}
