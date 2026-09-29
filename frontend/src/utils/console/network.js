/**
 * Fixed facts about the simulated network that the API does not return:
 * map coordinates, busy hours per demand profile, and short display names.
 */

/** Simulator id → short key used by the map ("station-coxsbazar" → "coxs"). */
export function nodeKey(id = '') {
  const k = id.replace(/^(station|depot|route)-/, '')
  return k === 'coxsbazar' ? 'coxs' : k
}

const DISPLAY = { mirpur: 'Mirpur', tongi: 'Tongi', karnaphuli: 'Karnaphuli', coxs: "Cox's Bazar", gazipur: 'Gazipur', patiya: 'Patiya' }

/** Display name: the known short name for this id, else the API name without "Station"/"Depot". */
export const shortName = (name = '', id = '') =>
  DISPLAY[nodeKey(id)] ?? name.replace(/\s+(Fuel Station|Station|Depot)$/i, '')

/** "region-chattogram" → "Chattogram" */
export const regionName = (id = '') => {
  const k = id.replace(/^region-/, '')
  return k.charAt(0).toUpperCase() + k.slice(1)
}

/** Approximate [lat, lon], spread so nearby Dhaka sites stay legible. */
export const LL = {
  gazipur: [24.05, 90.55],
  tongi: [24.4, 89.85],
  mirpur: [23.45, 89.85],
  patiya: [22.25, 92.05],
  karnaphuli: [22.75, 91.35],
  coxs: [21.4, 92.0],
}

/** Positions in the 640 × 520 map box, used until (or if) the geography fails to load. */
export const FALLBACK_XY = {
  gazipur: [330, 190],
  tongi: [270, 150],
  mirpur: [270, 250],
  patiya: [440, 360],
  karnaphuli: [390, 320],
  coxs: [440, 440],
}

/** Labels drawn to the left of the marker (the rest go right). */
export const LABEL_LEFT = { tongi: true, mirpur: true, karnaphuli: true }

/** Busy hours per demand profile (from the simulator guide, confirmed in our dataset). */
export const RUSH = {
  urban_high: '07–09 and 16–20',
  industrial: '06:00–17:59',
  highway: '06–09 and 16–20',
  regional: '07:00–20:59',
}
