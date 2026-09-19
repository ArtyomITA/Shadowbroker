/**
 * Vergilius: backend layer name -> dashboard toggle key.
 *
 * The two vocabularies do not match. The agent channel talks in backend layer
 * names (`military_flights`, `commercial_flights`, `gdelt`), while the toggles
 * in WorldviewLeftPanel use short UI keys (`military`, `flights`,
 * `global_incidents`). Some backend layers map to several toggles: asking for
 * "ships" has to light up four separate vessel categories.
 *
 * Unknown names fall through unchanged, so a toggle key sent directly still
 * works and a future backend layer does not need this table updated to be
 * switchable.
 */

const MAP: Record<string, string[]> = {
  // aviation
  commercial_flights: ['flights'],
  flights: ['flights'],
  private_flights: ['private'],
  private_jets: ['jets'],
  military_flights: ['military'],
  tracked_flights: ['tracked'],
  gps_jamming: ['gps_jamming'],
  // maritime — one backend name, four toggles
  ships: ['ships_military', 'ships_cargo', 'ships_civilian', 'ships_passenger'],
  ships_military: ['ships_military'],
  fishing_activity: ['fishing_activity'],
  tracked_yachts: ['ships_tracked_yachts'],
  // events and news
  gdelt: ['global_incidents'],
  global_incidents: ['global_incidents'],
  news: ['global_incidents'],
  finnhub_news: ['finnhub_news'],
  telegram_osint: ['telegram_osint'],
  crowdthreat: ['crowdthreat'],
  frontlines: ['ukraine_frontline'],
  ukraine_alerts: ['ukraine_alerts'],
  correlations: ['correlations'],
  gt_risk: ['gt_risk'],
  // hazards
  earthquakes: ['earthquakes'],
  firms_fires: ['firms'],
  volcanoes: ['volcanoes'],
  weather_alerts: ['weather_alerts'],
  air_quality: ['air_quality'],
  wastewater: ['wastewater'],
  // infrastructure
  internet_outages: ['internet_outages'],
  datacenters: ['datacenters'],
  power_plants: ['power_plants'],
  military_bases: ['military_bases'],
  trains: ['trains'],
  cctv: ['cctv'],
  submarine_cables: ['submarine_cables'],
  scm_suppliers: ['scm_suppliers'],
  malware_threats: ['malware_c2'],
  cyber_threats: ['cyber_threats'],
  // space and signals
  satellites: ['satellites'],
  satnogs_stations: ['satnogs'],
  tinygs_satellites: ['tinygs'],
  kiwisdr: ['kiwisdr'],
  psk_reporter: ['psk_reporter'],
  scanners: ['scanners'],
  sigint: ['sigint_meshtastic', 'sigint_aprs'],
  meshtastic_map_nodes: ['sigint_meshtastic'],
  sar_anomalies: ['sar'],
  sar: ['sar'],
  uap_sightings: ['uap_sightings'],
};

/** Toggle keys for a backend layer name. Unknown names pass through. */
export function AGENT_LAYER_KEYS(name: string): string[] {
  const k = String(name || '').trim().toLowerCase();
  if (!k) return [];
  return MAP[k] ?? [k];
}

/**
 * Never switched off by a "show only these" request. These are base map
 * furniture and the agent's own overlay: hiding them makes the dashboard look
 * broken without conveying anything.
 */
export const AGENT_LAYER_ALWAYS = new Set<string>([
  'day_night',
  'ai_intel',
  'highres_satellite',
  'gibs_imagery',
  'sentinel_hub',
  'viirs_nightlights',
  'shodan_overlay',
  'contradictions',
]);
