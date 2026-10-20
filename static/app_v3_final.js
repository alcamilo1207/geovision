// GeoVision Plant Extractor — Gemelo Digital & QRA (U044)
// Frontend SPA en React 18 con Leaflet, Plotly Wind Rose y API REST

const { useState, useEffect, useRef, useCallback } = React;

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error: error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', background: '#450a0a', border: '2px solid #ef4444', borderRadius: '0.75rem', margin: '1rem', color: '#fecaca' }}>
          <h3 style={{ color: '#f87171', fontSize: '1.1rem', marginBottom: '0.5rem' }}>⚠️ Error al renderizar esta pestaña</h3>
          <pre style={{ background: '#1c1917', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', overflowX: 'auto' }}>
            {this.state.error?.stack || this.state.error?.message || String(this.state.error)}
          </pre>
          <button 
            className="btn btn-secondary" 
            style={{ marginTop: '0.75rem', fontSize: '0.75rem' }} 
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            🔄 Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const MAPA_ICONOS = {
  horno: { color: "#dc2626", bg: "#7f1d1d", icon: "🔥", etiqueta: "Horno / Caldera" },
  caldera: { color: "#dc2626", bg: "#7f1d1d", icon: "🔥", etiqueta: "Horno / Caldera" },
  compresor: { color: "#9333ea", bg: "#581c87", icon: "⚙️", etiqueta: "Compresor" },
  "fin fan": { color: "#06b6d4", bg: "#164e63", icon: "❄️", etiqueta: "Fin Fan Cooler" },
  aeroenfriador: { color: "#06b6d4", bg: "#164e63", icon: "❄️", etiqueta: "Fin Fan Cooler" },
  filtro: { color: "#16a34a", bg: "#14532d", icon: "🟢", etiqueta: "Filtro / Separador" },
  separador: { color: "#16a34a", bg: "#14532d", icon: "🟢", etiqueta: "Filtro / Separador" },
  bomba: { color: "#2563eb", bg: "#1e3a8a", icon: "💧", etiqueta: "Bomba de Proceso" },
  torre: { color: "#10b981", bg: "#064e3b", icon: "🏭", etiqueta: "Torre Destilación" },
  tanque: { color: "#1d4ed8", bg: "#172554", icon: "🛢️", etiqueta: "Tanque Atmosférico" },
  esfera: { color: "#c026d3", bg: "#701a75", icon: "🟣", etiqueta: "Esfera / Bala GLP" },
  bala: { color: "#c026d3", bg: "#701a75", icon: "🟣", etiqueta: "Esfera / Bala GLP" },
  reactor: { color: "#d97706", bg: "#78350f", icon: "🧪", etiqueta: "Reactor" },
  intercambiador: { color: "#0d9488", bg: "#134e4a", icon: "🔄", etiqueta: "Intercambiador Calor" },
  rack: { color: "#64748b", bg: "#334155", icon: "📊", etiqueta: "Rack / Manifold" },
  tuberia: { color: "#64748b", bg: "#334155", icon: "📊", etiqueta: "Rack / Manifold" },
  subestacion: { color: "#475569", bg: "#0f172a", icon: "⚡", etiqueta: "Subestación / Control" },
  control: { color: "#475569", bg: "#0f172a", icon: "⚡", etiqueta: "Subestación / Control" },
  default: { color: "#0284c7", bg: "#0369a1", icon: "📦", etiqueta: "Equipo de Proceso" }
};

function getEstiloEquipo(tipo) {
  const t = (tipo || "").toLowerCase();
  for (const k of Object.keys(MAPA_ICONOS)) {
    if (k !== 'default' && t.includes(k)) return MAPA_ICONOS[k];
  }
  return MAPA_ICONOS.default;
}

function App() {
  const [activeTab, setActiveTab] = useState("plotplan");
  const [status, setStatus] = useState(null);
  const [equipos, setEquipos] = useState([]);
  const [condiciones, setCondiciones] = useState(null);
  const [plotplan, setPlotplan] = useState(null);
  const [plotplanFiles, setPlotplanFiles] = useState([]);
  const [selectedPlotplanFile, setSelectedPlotplanFile] = useState("");
  
  const [opacidad, setOpacidad] = useState(0.70);
  const [quitarBlanco, setQuitarBlanco] = useState(true);
  const [offsetX, setOffsetX] = useState(0.0);
  const [offsetY, setOffsetY] = useState(0.0);
  
  const [simParams, setSimParams] = useState({
    modo_origen_fuga: "🏭 Activo del Plot Plan",
    tag_emisor: "44-D-23",
    latitud: 10.314855,
    longitud: -75.487632,
    tipo_equipo: "Vessel / Drum",
    sustancia: "GLP / Propano",
    diametro_orificio_mm: 50.8,
    presion_bar: 18.0,
    temperatura_c: 45.0,
    inventario_kg: 15000.0,
    tiempo_fuga_min: 5.0,
    fenomeno: "Radiación Térmica (Jet/Pool Fire)",
    nivel_congestion: "Media (Proceso Estándar, eta=0.10)"
  });
  
  const [autoSim, setAutoSim] = useState(true);
  const [mostrarIsoriesgo, setMostrarIsoriesgo] = useState(true);
  const [simResult, setSimResult] = useState(null);
  const [loadingSim, setLoadingSim] = useState(false);
  const [simNotification, setSimNotification] = useState(null);

  const [pickMode, setPickMode] = useState(false);
  const [pickedCoords, setPickedCoords] = useState(null);

  const [editingEquipo, setEditingEquipo] = useState(null);
  const [damageMatrix, setDamageMatrix] = useState([]);

  useEffect(() => {
    fetchStatus();
    fetchEquipos();
    fetchCondiciones();
    fetchPlotplanCurrent();
    fetchPlotplanFiles();
    fetchDamageMatrix();
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      setStatus(data);
    } catch (e) {
      console.error("Error fetching status:", e);
    }
  };

  const fetchEquipos = async () => {
    try {
      const res = await fetch("/api/equipos");
      const data = await res.json();
      setEquipos(data);
      if (data.length > 0 && !simParams.tag_emisor) {
        setSimParams(p => ({ ...p, tag_emisor: data[0].tag }));
      }
    } catch (e) {
      console.error("Error fetching equipos:", e);
    }
  };

  const fetchCondiciones = async () => {
    try {
      const res = await fetch("/api/condiciones");
      const data = await res.json();
      setCondiciones(data);
    } catch (e) {
      console.error("Error fetching condiciones:", e);
    }
  };

  const fetchPlotplanCurrent = async () => {
    try {
      const res = await fetch("/api/plotplan/current");
      const data = await res.json();
      setPlotplan(data);
      if (data.opacidad !== undefined) setOpacidad(data.opacidad);
      if (data.quitar_blanco !== undefined) setQuitarBlanco(data.quitar_blanco);
      if (data.offset_x !== undefined) setOffsetX(data.offset_x);
      if (data.offset_y !== undefined) setOffsetY(data.offset_y);
    } catch (e) {
      console.error("Error fetching plotplan:", e);
    }
  };

  const fetchPlotplanFiles = async () => {
    try {
      const res = await fetch("/api/plotplan/files");
      const data = await res.json();
      setPlotplanFiles(data.files || []);
      setSelectedPlotplanFile(data.selected || "");
    } catch (e) {
      console.error("Error fetching plotplan files:", e);
    }
  };

  const fetchDamageMatrix = async () => {
    try {
      const res = await fetch("/api/financiero/matriz-dano");
      const data = await res.json();
      setDamageMatrix(data || []);
    } catch (e) {
      console.error("Error fetching damage matrix:", e);
    }
  };

  const updatePlotplanConfig = async (newConfig) => {
    try {
      const res = await fetch("/api/plotplan/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig)
      });
      const data = await res.json();
      setPlotplan(data);
    } catch (e) {
      console.error("Error updating plotplan config:", e);
    }
  };

  const handleRunSimulation = async (customParams = null) => {
    setLoadingSim(true);
    try {
      const p = customParams || simParams;
      const payload = {
        ...p,
        temperatura_ambiente_c: condiciones ? condiciones.temperatura_ambiente_c : 32.0,
        humedad_relativa_pct: condiciones ? condiciones.humedad_relativa_pct : 78.0,
        velocidad_viento_ms: condiciones ? condiciones.velocidad_viento_ms : 4.5,
        clase_estabilidad: condiciones ? condiciones.clase_estabilidad : "D"
      };
      const res = await fetch("/api/simulacion/calcular", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      setSimResult(data);

      const tasa = data.dinamica_fuga?.tasa_kg_s?.toFixed(2) || '0';
      const maxR = data.consecuencia?.anillos?.length > 0 ? data.consecuencia.anillos[data.consecuencia.anillos.length - 1].radio?.toFixed(1) : '0';
      const nAf = data.afectados?.length || 0;
      setSimNotification(`✅ Simulación Calculada: Tasa ${tasa} kg/s | Radio Máx: ${maxR} m | Receptores: ${nAf}`);
      setTimeout(() => setSimNotification(null), 5000);
    } catch (e) {
      console.error("Error running simulation:", e);
      alert("Error al ejecutar la simulación");
    } finally {
      setLoadingSim(false);
    }
  };

  // Auto-simulación al cambiar parámetros si autoSim está activo
  const handleParamChange = (newParams) => {
    setSimParams(newParams);
    if (autoSim) {
      handleRunSimulation(newParams);
    }
  };

  return (
    <div className="app-layout">
      {/* HEADER */}
      <header className="app-header">
        <div className="header-title-area">
          <h1>🏭 GeoVision Plant Extractor — Gemelo Digital & QRA (U044)</h1>
          <div className="header-badges">
            <span className="badge badge-cyan">API 581 Termodinámica</span>
            <span className="badge badge-green">
              ✅ OpenSRANE v0.1.6 Activo (Motor Multiplataforma Integrado)
            </span>
            <span className="badge badge-purple">Probit Cozzani</span>
            <span className="badge badge-gray">GeoTIFF WGS84</span>
            <span className="badge badge-green">● Backend Conectado</span>
          </div>
        </div>

        <div>
          <button 
            className={`btn ${pickMode ? 'btn-danger' : 'btn-secondary'}`}
            onClick={() => setPickMode(!pickMode)}
          >
            {pickMode ? "📍 Cancelar Captura Coordenadas" : "📍 Modo Captura en Mapa"}
          </button>
        </div>
      </header>

      {/* NOTIFICACIÓN DE SIMULACIÓN */}
      {simNotification && (
        <div style={{ background: '#064e3b', color: '#6ee7b7', borderBottom: '1px solid #10b981', padding: '0.5rem 1.5rem', fontSize: '0.82rem', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{simNotification}</span>
          <button style={{ background: 'transparent', border: 'none', color: '#6ee7b7', cursor: 'pointer', fontSize: '1rem' }} onClick={() => setSimNotification(null)}>✕</button>
        </div>
      )}

      {/* TABS NAVIGATION */}
      <nav className="tabs-nav">
        <button 
          className={`tab-btn ${activeTab === 'plotplan' ? 'active' : ''}`}
          onClick={() => setActiveTab('plotplan')}
        >
          📐 1. Plot Plan GeoTIFF & Gemelo Digital
        </button>
        <button 
          className={`tab-btn ${activeTab === 'consecuencias' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('consecuencias');
            if (!simResult) handleRunSimulation();
          }}
        >
          🗺️ 2. Simulación Escenarios QRA & Radios
        </button>
        <button 
          className={`tab-btn ${activeTab === 'domino' ? 'active' : ''}`}
          onClick={() => setActiveTab('domino')}
        >
          💥 3. Modelación Efecto Dominó (OpenSRANE)
        </button>
        <button 
          className={`tab-btn ${activeTab === 'qra' ? 'active' : ''}`}
          onClick={() => setActiveTab('qra')}
        >
          🌪️ 4. Rosa de Vientos & QRA (Purple / BEVI)
        </button>
        <button 
          className={`tab-btn ${activeTab === 'financiero' ? 'active' : ''}`}
          onClick={() => setActiveTab('financiero')}
        >
          💰 5. Criticidad Financiera Máxima (PML)
        </button>
      </nav>

      {/* MAIN CONTENT AREA */}
      <main className="main-content">
        {pickedCoords && (
          <div className="alert alert-info" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>📍 Coordenadas picadas en el mapa: <strong>Lat: {pickedCoords.lat.toFixed(6)}, Lon: {pickedCoords.lng.toFixed(6)}</strong></span>
            <div>
              <button 
                className="btn btn-primary" 
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem', marginRight: '0.5rem' }}
                onClick={() => {
                  const updated = { ...simParams, modo_origen_fuga: "📍 Punto Fuga Directo", latitud: pickedCoords.lat, longitud: pickedCoords.lng };
                  setSimParams(updated);
                  handleRunSimulation(updated);
                  setActiveTab("consecuencias");
                }}
              >
                Fijar como Fuga & Simular
              </button>
              <button 
                className="btn btn-secondary" 
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
                onClick={() => setPickedCoords(null)}
              >
                Cerrar
              </button>
            </div>
          </div>
        )}

        {activeTab === 'plotplan' && (
          <TabPlotPlan 
            plotplan={plotplan}
            plotplanFiles={plotplanFiles}
            selectedPlotplanFile={selectedPlotplanFile}
            setSelectedPlotplanFile={setSelectedPlotplanFile}
            opacidad={opacidad}
            setOpacidad={setOpacidad}
            quitarBlanco={quitarBlanco}
            setQuitarBlanco={setQuitarBlanco}
            offsetX={offsetX}
            setOffsetX={setOffsetX}
            offsetY={offsetY}
            setOffsetY={setOffsetY}
            updatePlotplanConfig={updatePlotplanConfig}
            equipos={equipos}
            fetchEquipos={fetchEquipos}
            fetchPlotplanCurrent={fetchPlotplanCurrent}
            pickMode={pickMode}
            setPickedCoords={setPickedCoords}
            onEditEquipo={(eq) => setEditingEquipo(eq)}
            onSetAsLeak={(eq) => {
              const updated = {
                ...simParams,
                modo_origen_fuga: "🏭 Activo del Plot Plan",
                tag_emisor: eq.tag,
                latitud: eq.latitud,
                longitud: eq.longitud,
                tipo_equipo: eq.tipo_equipo,
                sustancia: eq.sustancia,
                presion_bar: eq.presion_bar,
                temperatura_c: eq.temperatura_c,
                inventario_kg: eq.inventario_kg
              };
              setSimParams(updated);
              handleRunSimulation(updated);
              setActiveTab("consecuencias");
            }}
          />
        )}

        {activeTab === 'consecuencias' && (
          <TabConsecuencias 
            equipos={equipos}
            condiciones={condiciones}
            simParams={simParams}
            setSimParams={setSimParams}
            handleParamChange={handleParamChange}
            autoSim={autoSim}
            setAutoSim={setAutoSim}
            mostrarIsoriesgo={mostrarIsoriesgo}
            setMostrarIsoriesgo={setMostrarIsoriesgo}
            simResult={simResult}
            loadingSim={loadingSim}
            onRunSimulation={handleRunSimulation}
            plotplan={plotplan}
            pickMode={pickMode}
            setPickedCoords={setPickedCoords}
          />
        )}

        {activeTab === 'domino' && (
          <TabDomino 
            equipos={equipos}
            condiciones={condiciones}
            simParams={simParams}
            status={status}
            plotplan={plotplan}
          />
        )}

        {activeTab === 'qra' && (
          <ErrorBoundary>
            <TabQRAStandards 
              simParams={simParams}
              simResult={simResult}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'financiero' && (
          <TabFinanciero 
            equipos={equipos}
            simResult={simResult}
            damageMatrix={damageMatrix}
            fetchDamageMatrix={fetchDamageMatrix}
          />
        )}
      </main>

      {editingEquipo && (
        <ModalEquipo 
          equipo={editingEquipo}
          onClose={() => setEditingEquipo(null)}
          onSaved={() => {
            setEditingEquipo(null);
            fetchEquipos();
          }}
        />
      )}
    </div>
  );
}

// ==============================================================================
// MAP VIEW LEAFLET CON ISOSUPERFICIES DE ISORIESGO Y ANILLOS
// ==============================================================================
function MapView({ 
  center = [10.314855, -75.487632], 
  zoom = 18, 
  bounds = null, 
  imageUrl = null, 
  opacity = 0.7, 
  equipos = [], 
  anillos = [], 
  contornosIsoriesgo = null,
  mostrarIsoriesgo = true,
  fugaCenter = null,
  pickMode = false, 
  onPickCoords = null,
  onMarkerClick = null
}) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const imageOverlayRef = useRef(null);
  const markersLayerRef = useRef(null);
  const ringsLayerRef = useRef(null);
  const isoriesgoLayerRef = useRef(null);
  const [baseMap, setBaseMap] = useState("satellite");

  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: center,
      zoom: zoom,
      maxZoom: 22,
      zoomControl: true
    });

    const satLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 20, attribution: 'Tiles &copy; Esri' }
    );
    const osmLayer = L.tileLayer(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 19, attribution: '&copy; OpenStreetMap' }
    );

    satLayer.addTo(map);
    map._satLayer = satLayer;
    map._osmLayer = osmLayer;

    // Capas agrupadas
    const isoGroup = L.layerGroup().addTo(map);
    const ringsGroup = L.layerGroup().addTo(map);
    const markersGroup = L.layerGroup().addTo(map);

    isoriesgoLayerRef.current = isoGroup;
    ringsLayerRef.current = ringsGroup;
    markersLayerRef.current = markersGroup;

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Manejo de cambio de capa base
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (baseMap === "satellite") {
      if (map.hasLayer(map._osmLayer)) map.removeLayer(map._osmLayer);
      if (!map.hasLayer(map._satLayer)) map._satLayer.addTo(map);
    } else {
      if (map.hasLayer(map._satLayer)) map.removeLayer(map._satLayer);
      if (!map.hasLayer(map._osmLayer)) map._osmLayer.addTo(map);
    }
  }, [baseMap]);

  // Recenter dinámico cuando cambia el emisor de fuga
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (fugaCenter && Array.isArray(fugaCenter) && fugaCenter.length === 2 && !isNaN(fugaCenter[0])) {
      map.panTo(fugaCenter, { animate: true, duration: 0.6 });
    }
  }, [fugaCenter]);

  // Manejo de ImageOverlay Plot Plan GeoTIFF
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (imageOverlayRef.current) {
      map.removeLayer(imageOverlayRef.current);
      imageOverlayRef.current = null;
    }

    if (imageUrl && bounds && bounds.length === 2) {
      try {
        const overlay = L.imageOverlay(imageUrl, bounds, {
          opacity: opacity,
          interactive: false
        });
        overlay.addTo(map);
        imageOverlayRef.current = overlay;
      } catch (e) {
        console.error("Error loading imageOverlay:", e);
      }
    }
  }, [imageUrl, bounds, opacity]);

  // Manejo de Marcadores de Equipos
  useEffect(() => {
    const group = markersLayerRef.current;
    if (!group) return;
    group.clearLayers();

    equipos.forEach(eq => {
      if (eq.latitud && eq.longitud) {
        const estilo = getEstiloEquipo(eq.tipo_equipo);
        const iconHtml = `<div class="custom-equip-marker" style="background-color: ${estilo.color};">${estilo.icon}</div>`;
        const customIcon = L.divIcon({
          html: iconHtml,
          className: '',
          iconSize: [28, 28],
          iconAnchor: [14, 14]
        });

        const marker = L.marker([eq.latitud, eq.longitud], { icon: customIcon });
        const popupContent = `
          <div style="font-family: inherit; font-size: 0.82rem; min-width: 180px;">
            <div style="font-weight: bold; color: #38bdf8; font-size: 0.95rem; margin-bottom: 4px;">${eq.tag}</div>
            <div style="color: #94a3b8; margin-bottom: 2px;">${eq.tipo_equipo}</div>
            <div><strong>Sustancia:</strong> ${eq.sustancia || 'N/A'}</div>
            <div><strong>Presión:</strong> ${eq.presion_bar} bar | <strong>Temp:</strong> ${eq.temperatura_c} °C</div>
            <div><strong>Inventario:</strong> ${eq.inventario_kg?.toLocaleString()} kg</div>
            <div><strong>Valor Rep.:</strong> $${eq.valor_reposicion_usd?.toLocaleString()} USD</div>
            <div style="margin-top: 6px;">
              <small style="color: #64748b;">${eq.latitud.toFixed(6)}, ${eq.longitud.toFixed(6)}</small>
            </div>
          </div>
        `;
        marker.bindPopup(popupContent);
        marker.on('click', () => {
          if (onMarkerClick) onMarkerClick(eq);
        });
        group.addLayer(marker);
      }
    });
  }, [equipos]);

  // Renderizado de ISOSUPERFICIES DE ISORIESGO DIRECCIONAL (10^-5, 10^-6, 10^-7 /año)
  useEffect(() => {
    const group = isoriesgoLayerRef.current;
    if (!group) return;
    group.clearLayers();

    if (mostrarIsoriesgo && contornosIsoriesgo && typeof contornosIsoriesgo === 'object') {
      const keys = Object.keys(contornosIsoriesgo).sort((a, b) => parseFloat(a) - parseFloat(b)); // 1e-7 a 1e-5
      keys.forEach(k => {
        const info = contornosIsoriesgo[k];
        if (info && info.poligono_coords && info.poligono_coords.length >= 3) {
          const poly = L.polygon(info.poligono_coords, {
            color: info.color || '#F57C00',
            weight: 2.2,
            dashArray: '6, 6',
            fill: true,
            fillColor: info.color || '#F57C00',
            fillOpacity: 0.16
          });
          poly.bindTooltip(`<b>🎯 ${info.nombre}</b><br/>Radio Máximo: ${info.radio_maximo_m} m<br/>Radio Medio: ${info.radio_medio_m} m`);
          group.addLayer(poly);
        }
      });
    }
  }, [contornosIsoriesgo, mostrarIsoriesgo]);

  // Renderizado de Anillos Concéntricos de Consecuencia
  useEffect(() => {
    const group = ringsLayerRef.current;
    if (!group) return;
    group.clearLayers();

    if (fugaCenter && anillos && anillos.length > 0) {
      const pinIcon = L.divIcon({
        html: `<div style="background: #ef4444; color: #fff; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; border: 3px solid #ffffff; box-shadow: 0 0 10px #ef4444;">💥</div>`,
        className: '',
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });
      const centerMarker = L.marker(fugaCenter, { icon: pinIcon }).bindPopup(`<strong>Origen de Fuga</strong><br/>Lat: ${fugaCenter[0].toFixed(6)}<br/>Lon: ${fugaCenter[1].toFixed(6)}`);
      group.addLayer(centerMarker);

      const anillosOrdenados = [...anillos].sort((a, b) => b.radio - a.radio);
      anillosOrdenados.forEach((anillo) => {
        const circle = L.circle(fugaCenter, {
          radius: anillo.radio,
          color: anillo.color || '#ef4444',
          fillColor: anillo.color || '#ef4444',
          fillOpacity: 0.22,
          weight: 2.2
        });
        circle.bindTooltip(`<strong>${anillo.nombre}</strong><br/>Radio: ${anillo.radio.toFixed(1)} m | Umbral: ${anillo.umbral_valor}`);
        group.addLayer(circle);
      });
    }
  }, [fugaCenter, anillos]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    const handleClick = (e) => {
      if (pickMode && onPickCoords) {
        onPickCoords({ lat: e.latlng.lat, lng: e.latlng.lng });
      }
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [pickMode, onPickCoords]);

  const recentrar = () => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (fugaCenter) {
      map.setView(fugaCenter, 18);
    } else if (bounds && bounds.length === 2) {
      map.fitBounds(bounds);
    } else {
      map.setView(center, zoom);
    }
  };

  return (
    <div>
      <div className="map-controls-bar">
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Capa Base:</span>
          <button 
            className={`btn ${baseMap === 'satellite' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
            onClick={() => setBaseMap('satellite')}
          >
            🛰️ Satélite Esri
          </button>
          <button 
            className={`btn ${baseMap === 'osm' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
            onClick={() => setBaseMap('osm')}
          >
            🗺️ OpenStreetMap
          </button>
        </div>
        <div>
          <button 
            className="btn btn-secondary" 
            style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
            onClick={recentrar}
          >
            🎯 Recentrar Escenario
          </button>
        </div>
      </div>
      <div 
        ref={mapContainerRef} 
        className="map-container"
        style={{ cursor: pickMode ? 'crosshair' : 'default' }}
      />
    </div>
  );
}

// ==============================================================================
// TAB 1: PLOT PLAN GEOREFERENCIADO & GEMELO DIGITAL
// ==============================================================================
function TabPlotPlan({
  plotplan,
  plotplanFiles,
  selectedPlotplanFile,
  setSelectedPlotplanFile,
  opacidad,
  setOpacidad,
  quitarBlanco,
  setQuitarBlanco,
  offsetX,
  setOffsetX,
  offsetY,
  setOffsetY,
  updatePlotplanConfig,
  equipos,
  fetchEquipos,
  fetchPlotplanCurrent,
  pickMode,
  setPickedCoords,
  onEditEquipo,
  onSetAsLeak
}) {
  const [nuevoTag, setNuevoTag] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState("Vessel / Drum");
  const [nuevoLat, setNuevoLat] = useState(10.314855);
  const [nuevoLon, setNuevoLon] = useState(-75.487632);
  const [nuevoSustancia, setNuevoSustancia] = useState("GLP / Propano");
  const [nuevoInventario, setNuevoInventario] = useState(15000);
  const [nuevoPresion, setNuevoPresion] = useState(18.0);
  const [nuevoTemp, setNuevoTemp] = useState(45.0);
  const [nuevoDiam, setNuevoDiam] = useState(25.4);
  const [nuevoValorRep, setNuevoValorRep] = useState(850000);
  const [nuevoLeadTime, setNuevoLeadTime] = useState(8.0);
  const [nuevoImpactoDiario, setNuevoImpactoDiario] = useState(40000);

  const handleCrearEquipo = async (e) => {
    e.preventDefault();
    if (!nuevoTag) {
      alert("Ingrese el Tag del equipo");
      return;
    }
    try {
      const res = await fetch("/api/equipos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tag: nuevoTag,
          tipo_equipo: nuevoTipo,
          latitud: parseFloat(nuevoLat),
          longitud: parseFloat(nuevoLon),
          sustancia: nuevoSustancia,
          inventario_kg: parseFloat(nuevoInventario),
          presion_bar: parseFloat(nuevoPresion),
          temperatura_c: parseFloat(nuevoTemp),
          diametro_orificio_mm: parseFloat(nuevoDiam),
          altura_fuga_m: 1.5,
          valor_reposicion_usd: parseFloat(nuevoValorRep),
          lead_time_meses: parseFloat(nuevoLeadTime),
          impacto_diario_usd: parseFloat(nuevoImpactoDiario)
        })
      });
      if (res.ok) {
        alert(`Equipo '${nuevoTag}' registrado con éxito`);
        setNuevoTag("");
        fetchEquipos();
      } else {
        const err = await res.json();
        alert(err.detail || "Error al crear equipo");
      }
    } catch (err) {
      console.error(err);
      alert("Error de conexión");
    }
  };

  const handleEliminarEquipo = async (tag) => {
    if (!confirm(`¿Está seguro de eliminar el equipo '${tag}'?`)) return;
    try {
      await fetch(`/api/equipos/${tag}`, { method: "DELETE" });
      fetchEquipos();
    } catch (e) {
      console.error(e);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/plotplan/upload", {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        alert("Archivo subido con éxito");
        fetchPlotplanCurrent();
      } else {
        alert("Error al subir archivo");
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">📂 Calibración & Selección del Plot Plan</span>
          </div>

          <div className="form-group">
            <label>Plot Plan Activo:</label>
            <select 
              className="form-select"
              value={selectedPlotplanFile}
              onChange={(e) => {
                setSelectedPlotplanFile(e.target.value);
                updatePlotplanConfig({ fuente_sel: e.target.value });
              }}
            >
              {plotplanFiles.map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Subir Nuevo Plot Plan (.tif, .tiff, .png, .jpg):</label>
            <input 
              type="file" 
              className="form-control" 
              accept=".tif,.tiff,.png,.jpg,.jpeg"
              onChange={handleFileUpload}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>Opacidad del Plano ({Math.round(opacidad * 100)}%):</label>
              <input 
                type="range" 
                min="0.0" 
                max="1.0" 
                step="0.05"
                value={opacidad}
                className="form-control"
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setOpacidad(val);
                  updatePlotplanConfig({ opacidad: val });
                }}
              />
            </div>
            <div className="form-group" style={{ display: 'flex', alignItems: 'center', marginTop: '1.2rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', textTransform: 'none', color: '#fff' }}>
                <input 
                  type="checkbox" 
                  checked={quitarBlanco}
                  onChange={(e) => {
                    setQuitarBlanco(e.target.checked);
                    updatePlotplanConfig({ quitar_blanco: e.target.checked });
                  }}
                />
                Fondo blanco transparente
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>Micro-Ajuste ΔX (Longitud):</label>
              <input 
                type="number" 
                step="0.000005"
                className="form-control"
                value={offsetX}
                onChange={(e) => {
                  const v = parseFloat(e.target.value) || 0;
                  setOffsetX(v);
                  updatePlotplanConfig({ offset_x: v });
                }}
              />
            </div>
            <div className="form-group">
              <label>Micro-Ajuste ΔY (Latitud):</label>
              <input 
                type="number" 
                step="0.000005"
                className="form-control"
                value={offsetY}
                onChange={(e) => {
                  const v = parseFloat(e.target.value) || 0;
                  setOffsetY(v);
                  updatePlotplanConfig({ offset_y: v });
                }}
              />
            </div>
          </div>

          {plotplan?.has_plotplan && (
            <div className="alert alert-success" style={{ marginTop: '0.5rem', fontSize: '0.78rem' }}>
              <div>
                <strong>GeoTIFF Georreferenciado Activo:</strong> {plotplan.metadata?.crs || 'WGS84'} | {plotplan.metadata?.width}x{plotplan.metadata?.height} px<br/>
                <small>Límites WGS84: SW [{plotplan.bounds[0][0]?.toFixed(5)}, {plotplan.bounds[0][1]?.toFixed(5)}] | NE [{plotplan.bounds[1][0]?.toFixed(5)}, {plotplan.bounds[1][1]?.toFixed(5)}]</small>
              </div>
            </div>
          )}

          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
            <h4 style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '0.5rem' }}>📌 Leyenda de Iconos de Equipos:</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.35rem', fontSize: '0.75rem', color: '#cbd5e1' }}>
              <div>🔥 Hornos & Calderas</div>
              <div>⚙️ Compresores</div>
              <div>❄️ Fin Fan Coolers</div>
              <div>🟢 Filtros / Separadores</div>
              <div>💧 Bombas de Proceso</div>
              <div>🏭 Torres Fraccionadoras</div>
              <div>🛢️ Tanques Atmosféricos</div>
              <div>🟣 Esferas / Balas GLP</div>
              <div>🧪 Reactores Químicos</div>
              <div>🔄 Intercambiadores Calor</div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">🗺️ Visualizador GIS de Planta U044</span>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {equipos.length} Activos en Planta
            </span>
          </div>

          <MapView 
            center={plotplan?.center || [10.314855, -75.487632]}
            zoom={plotplan?.zoom || 18}
            bounds={plotplan?.bounds}
            imageUrl={plotplan?.has_plotplan ? plotplan.image_url : null}
            opacity={opacidad}
            equipos={equipos}
            pickMode={pickMode}
            onPickCoords={(coords) => {
              setNuevoLat(coords.lat);
              setNuevoLon(coords.lng);
              setPickedCoords(coords);
            }}
            onMarkerClick={(eq) => onEditEquipo(eq)}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">➕ Registrar Nuevo Activo Industrial (Gemelo Digital)</span>
        </div>
        <form onSubmit={handleCrearEquipo}>
          <div className="grid-4">
            <div className="form-group">
              <label>Tag del Equipo:</label>
              <input 
                type="text" 
                className="form-control" 
                placeholder="Ej. 44-D-25" 
                value={nuevoTag} 
                onChange={(e) => setNuevoTag(e.target.value)} 
                required 
              />
            </div>
            <div className="form-group">
              <label>Tipo de Equipo:</label>
              <select className="form-select" value={nuevoTipo} onChange={(e) => setNuevoTipo(e.target.value)}>
                <option value="Vessel / Drum">Vessel / Drum</option>
                <option value="Horno de Proceso (Fired Heater)">Horno de Proceso</option>
                <option value="Torre de Destilación / Fraccionadora">Torre de Destilación</option>
                <option value="Bomba de Proceso (Centrífuga / Desplazamiento)">Bomba de Proceso</option>
                <option value="Compresor Centrífugo / Reciprocante">Compresor</option>
                <option value="Intercambiador de Calor (Carcasa y Tubos / Placas)">Intercambiador de Calor</option>
                <option value="Reactor (Lecho Fijo / Tubular / CSTR)">Reactor</option>
                <option value="Tanque Atmosférico (Techo Fijo / Techo Flotante)">Tanque Atmosférico</option>
                <option value="Esfera Presurizada / Bala (LPG Sphere / Bullet)">Esfera Presurizada / Bala</option>
                <option value="Fin Fan Cooler / Aeroenfriador">Fin Fan Cooler</option>
                <option value="Filtro / Separador / Coalescedor">Filtro / Separador</option>
              </select>
            </div>
            <div className="form-group">
              <label>Latitud (WGS84):</label>
              <input 
                type="number" 
                step="0.000001" 
                className="form-control" 
                value={nuevoLat} 
                onChange={(e) => setNuevoLat(parseFloat(e.target.value))} 
                required 
              />
            </div>
            <div className="form-group">
              <label>Longitud (WGS84):</label>
              <input 
                type="number" 
                step="0.000001" 
                className="form-control" 
                value={nuevoLon} 
                onChange={(e) => setNuevoLon(parseFloat(e.target.value))} 
                required 
              />
            </div>
          </div>

          <div className="grid-4" style={{ marginTop: '0.5rem' }}>
            <div className="form-group">
              <label>Sustancia:</label>
              <input 
                type="text" 
                className="form-control" 
                value={nuevoSustancia} 
                onChange={(e) => setNuevoSustancia(e.target.value)} 
              />
            </div>
            <div className="form-group">
              <label>Presión (bar):</label>
              <input 
                type="number" 
                step="0.1" 
                className="form-control" 
                value={nuevoPresion} 
                onChange={(e) => setNuevoPresion(parseFloat(e.target.value))} 
              />
            </div>
            <div className="form-group">
              <label>Temperatura (°C):</label>
              <input 
                type="number" 
                step="0.1" 
                className="form-control" 
                value={nuevoTemp} 
                onChange={(e) => setNuevoTemp(parseFloat(e.target.value))} 
              />
            </div>
            <div className="form-group">
              <label>Inventario (kg):</label>
              <input 
                type="number" 
                step="100" 
                className="form-control" 
                value={nuevoInventario} 
                onChange={(e) => setNuevoInventario(parseFloat(e.target.value))} 
              />
            </div>
          </div>

          <div className="grid-4" style={{ marginTop: '0.5rem' }}>
            <div className="form-group">
              <label>Valor Reposición ($ USD):</label>
              <input 
                type="number" 
                className="form-control" 
                value={nuevoValorRep} 
                onChange={(e) => setNuevoValorRep(parseFloat(e.target.value))} 
              />
            </div>
            <div className="form-group">
              <label>Lead Time (Meses):</label>
              <input 
                type="number" 
                step="0.5" 
                className="form-control" 
                value={nuevoLeadTime} 
                onChange={(e) => setNuevoLeadTime(parseFloat(e.target.value))} 
              />
            </div>
            <div className="form-group">
              <label>Impacto Diario Lucro ($ USD):</label>
              <input 
                type="number" 
                className="form-control" 
                value={nuevoImpactoDiario} 
                onChange={(e) => setNuevoImpactoDiario(parseFloat(e.target.value))} 
              />
            </div>
            <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-success btn-block">
                💾 Guardar Activo en DB
              </button>
            </div>
          </div>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">📋 Inventario de Activos del Gemelo Digital ({equipos.length})</span>
        </div>
        <div className="table-responsive">
          <table className="custom-table">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Categoría</th>
                <th>Coordenadas (Lat / Lon)</th>
                <th>Sustancia</th>
                <th>Presión (bar)</th>
                <th>Temp (°C)</th>
                <th>Inventario (kg)</th>
                <th>Valor Rep. ($ USD)</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {equipos.map(eq => {
                const estilo = getEstiloEquipo(eq.tipo_equipo);
                return (
                  <tr key={eq.tag}>
                    <td style={{ fontWeight: 700, color: '#38bdf8' }}>{eq.tag}</td>
                    <td>
                      <span style={{ marginRight: '4px' }}>{estilo.icon}</span> {eq.tipo_equipo}
                    </td>
                    <td><small>{eq.latitud?.toFixed(6)}, {eq.longitud?.toFixed(6)}</small></td>
                    <td>{eq.sustancia}</td>
                    <td>{eq.presion_bar} bar</td>
                    <td>{eq.temperatura_c} °C</td>
                    <td>{eq.inventario_kg?.toLocaleString()} kg</td>
                    <td>${eq.valor_reposicion_usd?.toLocaleString()}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.35rem' }}>
                        <button 
                          className="btn btn-secondary" 
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                          title="Fijar como fuente de fuga"
                          onClick={() => onSetAsLeak(eq)}
                        >
                          💥 Fuga
                        </button>
                        <button 
                          className="btn btn-primary" 
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                          onClick={() => onEditEquipo(eq)}
                        >
                          ✏️ Editar
                        </button>
                        <button 
                          className="btn btn-danger" 
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                          onClick={() => handleEliminarEquipo(eq.tag)}
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ==============================================================================
// TAB 2: SIMULACIÓN DE ESCENARIOS QRA, RADIOS & ISOSUPERFICIES
// ==============================================================================
function TabConsecuencias({
  equipos,
  condiciones,
  simParams,
  setSimParams,
  handleParamChange,
  autoSim,
  setAutoSim,
  mostrarIsoriesgo,
  setMostrarIsoriesgo,
  simResult,
  loadingSim,
  onRunSimulation,
  plotplan,
  pickMode,
  setPickedCoords
}) {
  const PRESETS_ORIFICIO = [
    { label: '1/4" (6.4 mm) - Pequeña (Pinhole / Instrumentación)', val: 6.4 },
    { label: '1" (25.4 mm) - Mediana (Boquilla / Brida) [API 581]', val: 25.4 },
    { label: '2" (50.8 mm) - Intermedia (Tubería Secundaria)', val: 50.8 },
    { label: '4" (101.6 mm) - Grande (Tubería Principal)', val: 101.6 },
    { label: '6" (152.4 mm) - Ruptura Full Bore (6")', val: 152.4 },
    { label: '10" (254.0 mm) - Catastrófica Mayor (10")', val: 254.0 }
  ];

  const FENOMENOS = [
    "Radiación Térmica (Jet/Pool Fire)",
    "Sobrepresión por Explosión (VCE - Multi-Energy)",
    "Dispersión Tóxica / Inflamable (LFL / UFL / ERPG-2)",
    "Bolas de Fuego (BLEVE)"
  ];

  const CONGESTIONES = [
    "Baja (Espacio Abierto, eta=0.03)",
    "Media (Proceso Estándar, eta=0.10)",
    "Alta (Racks Densos, eta=0.20)",
    "Muy Alta / Confinada (Semi-Cerrado, eta=0.35)"
  ];

  const SUSTANCIAS = [
    "GLP / Propano",
    "Gas Natural / Metano",
    "Hidrógeno",
    "Nafta Ligera",
    "Gasolina / Nafta",
    "Gasóleo / Diesel",
    "Crudo / Hidrocarburo Mezcla",
    "Etileno"
  ];

  const updateParam = (key, value) => {
    const updated = { ...simParams, [key]: value };
    handleParamChange(updated);
  };

  return (
    <div>
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">🎯 Parámetros del Escenario de Fuga (API 581)</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input 
                  type="checkbox" 
                  checked={autoSim} 
                  onChange={(e) => setAutoSim(e.target.checked)} 
                />
                ⚡ Auto-calcular en vivo
              </label>
            </div>
          </div>

          <div className="form-group">
            <label>Modo de Origen de Fuga:</label>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button 
                type="button"
                className={`btn ${simParams.modo_origen_fuga === '🏭 Activo del Plot Plan' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => updateParam('modo_origen_fuga', '🏭 Activo del Plot Plan')}
                style={{ flex: 1 }}
              >
                🏭 Activo del Plot Plan
              </button>
              <button 
                type="button"
                className={`btn ${simParams.modo_origen_fuga === '📍 Punto Fuga Directo' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => updateParam('modo_origen_fuga', '📍 Punto Fuga Directo')}
                style={{ flex: 1 }}
              >
                📍 Punto Fuga Directo
              </button>
            </div>
          </div>

          {simParams.modo_origen_fuga === '🏭 Activo del Plot Plan' ? (
            <div className="form-group">
              <label>Activo Emisor de Fuga:</label>
              <select 
                className="form-select"
                value={simParams.tag_emisor}
                onChange={(e) => {
                  const tag = e.target.value;
                  const eq = equipos.find(x => x.tag === tag);
                  if (eq) {
                    handleParamChange({
                      ...simParams,
                      tag_emisor: tag,
                      latitud: eq.latitud,
                      longitud: eq.longitud,
                      tipo_equipo: eq.tipo_equipo,
                      sustancia: eq.sustancia || simParams.sustancia,
                      presion_bar: eq.presion_bar || simParams.presion_bar,
                      temperatura_c: eq.temperatura_c || simParams.temperatura_c,
                      inventario_kg: eq.inventario_kg || simParams.inventario_kg
                    });
                  } else {
                    updateParam('tag_emisor', tag);
                  }
                }}
              >
                {equipos.map(eq => (
                  <option key={eq.tag} value={eq.tag}>{eq.tag} — {eq.tipo_equipo} ({eq.sustancia})</option>
                ))}
              </select>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              <div className="form-group">
                <label>Latitud Fuga:</label>
                <input 
                  type="number" 
                  step="0.000001" 
                  className="form-control" 
                  value={simParams.latitud}
                  onChange={(e) => updateParam('latitud', parseFloat(e.target.value))}
                />
              </div>
              <div className="form-group">
                <label>Longitud Fuga:</label>
                <input 
                  type="number" 
                  step="0.000001" 
                  className="form-control" 
                  value={simParams.longitud}
                  onChange={(e) => updateParam('longitud', parseFloat(e.target.value))}
                />
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>Sustancia:</label>
              <select 
                className="form-select"
                value={simParams.sustancia}
                onChange={(e) => updateParam('sustancia', e.target.value)}
              >
                {SUSTANCIAS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label>Diámetro de Orificio:</label>
              <select 
                className="form-select"
                value={simParams.diametro_orificio_mm}
                onChange={(e) => updateParam('diametro_orificio_mm', parseFloat(e.target.value))}
              >
                {PRESETS_ORIFICIO.map(p => (
                  <option key={p.val} value={p.val}>{p.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
            <div className="form-group">
              <label>Presión (bar):</label>
              <input 
                type="number" 
                step="0.5" 
                className="form-control" 
                value={simParams.presion_bar}
                onChange={(e) => updateParam('presion_bar', parseFloat(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label>Temp (°C):</label>
              <input 
                type="number" 
                step="0.5" 
                className="form-control" 
                value={simParams.temperatura_c}
                onChange={(e) => updateParam('temperatura_c', parseFloat(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label>Inventario (kg):</label>
              <input 
                type="number" 
                step="500" 
                className="form-control" 
                value={simParams.inventario_kg}
                onChange={(e) => updateParam('inventario_kg', parseFloat(e.target.value))}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>Fenómeno Físico Activo:</label>
              <select 
                className="form-select"
                value={simParams.fenomeno}
                onChange={(e) => updateParam('fenomeno', e.target.value)}
              >
                {FENOMENOS.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label>Nivel de Congestión (VCE):</label>
              <select 
                className="form-select"
                value={simParams.nivel_congestion}
                onChange={(e) => updateParam('nivel_congestion', e.target.value)}
              >
                {CONGESTIONES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Tiempo de Fuga (minutos): {simParams.tiempo_fuga_min} min</label>
            <input 
              type="range" 
              min="0.5" 
              max="60" 
              step="0.5"
              className="form-control"
              value={simParams.tiempo_fuga_min}
              onChange={(e) => updateParam('tiempo_fuga_min', parseFloat(e.target.value))}
            />
          </div>

          <button 
            className="btn btn-primary btn-block"
            onClick={() => onRunSimulation()}
            disabled={loadingSim}
            style={{ marginTop: '0.5rem', padding: '0.75rem', fontWeight: 700 }}
          >
            {loadingSim ? "⏳ Calculando Dinámica de Fuga..." : "🚀 Recalcular Escenario de Consecuencias"}
          </button>
        </div>

        {/* MAPA CON RADIOS Y CONTORNOS DE ISORIESGO */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">🗺️ Impacto Espacial & Isosuperficies de Consecuencia</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <label style={{ fontSize: '0.75rem', color: '#f59e0b', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}>
                <input 
                  type="checkbox" 
                  checked={mostrarIsoriesgo} 
                  onChange={(e) => setMostrarIsoriesgo(e.target.checked)} 
                />
                🎯 Isosuperficies Isoriesgo
              </label>
            </div>
          </div>

          <MapView 
            center={simResult?.eq_emisor ? [simResult.eq_emisor.latitud, simResult.eq_emisor.longitud] : (plotplan?.center || [10.314855, -75.487632])}
            zoom={18}
            bounds={plotplan?.bounds}
            imageUrl={plotplan?.has_plotplan ? plotplan.image_url : null}
            opacity={0.65}
            equipos={equipos}
            anillos={simResult?.consecuencia?.anillos || []}
            contornosIsoriesgo={simResult?.qra_full?.contornos_isoriesgo || null}
            mostrarIsoriesgo={mostrarIsoriesgo}
            fugaCenter={simResult?.eq_emisor ? [simResult.eq_emisor.latitud, simResult.eq_emisor.longitud] : null}
            pickMode={pickMode}
            onPickCoords={(coords) => {
              updateParam('latitud', coords.lat);
              updateParam('longitud', coords.lng);
              setPickedCoords(coords);
            }}
          />
        </div>
      </div>

      {/* METRICAS DE SALIDA API 581 */}
      {simResult && (
        <div style={{ marginTop: '1.25rem' }}>
          <div className="grid-4">
            <div className="metric-box">
              <span className="metric-label">Tasa de Descarga API 581</span>
              <span className="metric-value">{simResult.dinamica_fuga?.tasa_kg_s?.toFixed(2)} kg/s</span>
              <span className="metric-sub">{simResult.dinamica_fuga?.tasa_kg_h?.toLocaleString()} kg/h</span>
            </div>
            <div className="metric-box">
              <span className="metric-label">Masa Total Liberada</span>
              <span className="metric-value">{simResult.dinamica_fuga?.masa_liberada_kg?.toLocaleString()} kg</span>
              <span className="metric-sub">{simResult.dinamica_fuga?.pct_inventario?.toFixed(1)}% del Inventario</span>
            </div>
            <div className="metric-box">
              <span className="metric-label">Tiempo de Vaciado</span>
              <span className="metric-value">{simResult.dinamica_fuga?.tiempo_vaciado_min?.toFixed(1)} min</span>
              <span className="metric-sub">Duración simulada: {simParams.tiempo_fuga_min} min</span>
            </div>
            <div className="metric-box">
              <span className="metric-label">Potencia / Severidad</span>
              <span className="metric-value" style={{ color: '#ef4444' }}>
                {simResult.consecuencia?.potencia_termica_mw ? `${simResult.consecuencia.potencia_termica_mw?.toFixed(1)} MW` : 'Alto Impacto'}
              </span>
              <span className="metric-sub">{simResult.consecuencia?.tipo || simParams.fenomeno}</span>
            </div>
          </div>

          {/* TABLA DE ANILLOS Y CONTORNOS DE ISORIESGO */}
          <div className="grid-2" style={{ marginTop: '1rem' }}>
            <div className="card">
              <div className="card-header">
                <span className="card-title">📏 Umbrales Físicos & Radios de Consecuencia</span>
              </div>
              <div className="table-responsive">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Zona / Umbral</th>
                      <th>Valor Físico</th>
                      <th>Radio</th>
                      <th>Nivel de Daño Esperado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simResult.consecuencia?.anillos?.map((a, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>
                          <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: '50%', backgroundColor: a.color, marginRight: 6 }}></span>
                          {a.nombre}
                        </td>
                        <td><strong>{a.umbral_valor}</strong> {simParams.fenomeno.includes('Radiación') ? 'kW/m²' : 'bar'}</td>
                        <td style={{ color: '#38bdf8', fontWeight: 700, fontSize: '0.95rem' }}>{a.radio?.toFixed(1)} m</td>
                        <td><span className="badge badge-amber">{a.nivel}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">🎯 Isosuperficies de Isoriesgo QRA (Purple / BEVI)</span>
              </div>
              <div className="table-responsive">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Contorno Isoriesgo</th>
                      <th>Radio Medio</th>
                      <th>Radio Máximo</th>
                      <th>Criterio Regulatorio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simResult.qra_full?.contornos_isoriesgo && Object.keys(simResult.qra_full.contornos_isoriesgo).map(k => {
                      const c = simResult.qra_full.contornos_isoriesgo[k];
                      return (
                        <tr key={k}>
                          <td style={{ fontWeight: 600 }}>
                            <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: '50%', backgroundColor: c.color, marginRight: 6 }}></span>
                            {c.nombre}
                          </td>
                          <td style={{ color: '#38bdf8', fontWeight: 700 }}>{c.radio_medio_m} m</td>
                          <td style={{ color: '#f59e0b', fontWeight: 700 }}>{c.radio_maximo_m} m</td>
                          <td><span className="badge badge-gray">{k} /año</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* TABLA DE RECEPTORES ALCANZADOS */}
          <div className="card" style={{ marginTop: '1rem' }}>
            <div className="card-header">
              <span className="card-title">💥 Receptores Alcanzados & Equipos Afectados (Efecto Dominó 1er Orden)</span>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                {simResult.afectados?.length || 0} Equipos en Zona de Impacto
              </span>
            </div>
            {simResult.afectados && simResult.afectados.length > 0 ? (
              <div className="table-responsive">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Tag</th>
                      <th>Tipo Equipo</th>
                      <th>Distancia (m)</th>
                      <th>Carga Incidente</th>
                      <th>Zona de Impacto</th>
                      <th>Daño Estimado</th>
                      <th>Tiempo Parada</th>
                      <th>Costo Daño Directo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simResult.afectados.map((af, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 700, color: '#f87171' }}>{af.tag}</td>
                        <td>{af.tipo_equipo}</td>
                        <td>{af.distancia_m?.toFixed(1)} m</td>
                        <td><strong>{af.carga_incidente?.toFixed(1)}</strong> {simParams.fenomeno.includes('Radiación') ? 'kW/m²' : 'bar'}</td>
                        <td><span className="badge badge-red">{af.anillo_maximo}</span></td>
                        <td><strong>{af.dano_estimado_pct || '45%'}</strong> ({af.clasificacion_severidad || 'Severo'})</td>
                        <td>{af.tiempo_reparacion_txt || `${af.dias_parada || 45} días`}</td>
                        <td style={{ color: '#34d399', fontWeight: 700 }}>
                          ${af.costo_dano_directo_usd ? af.costo_dano_directo_usd.toLocaleString() : (af.valor_reposicion_usd ? (af.valor_reposicion_usd * 0.45).toLocaleString() : 'N/A')} USD
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="alert alert-info" style={{ margin: '0.5rem 0' }}>
                ✅ Ningún equipo receptor predefinido se encuentra dentro de los radios de afectación de este escenario. Para simular afectación a activos vecinos, incremente el diámetro de orificio o la presión de operación.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ==============================================================================
// TAB 3: MODELACIÓN DE CONSECUENCIAS & EFECTO DOMINÓ (OPENSRANE)
// ==============================================================================
function TabDomino({ equipos, condiciones, simParams, status, plotplan }) {
  const [simDomino, setSimDomino] = useState(null);
  const [distMatrix, setDistMatrix] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchDistanceMatrix();
    handleRunDomino();
  }, [equipos]);

  const fetchDistanceMatrix = async () => {
    try {
      const res = await fetch("/api/domino/matriz-distancias");
      const data = await res.json();
      setDistMatrix(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRunDomino = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/domino/simular", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(simParams)
      });
      const data = await res.json();
      setSimDomino(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <span className="card-title">💥 Análisis Cuantitativo de Propagación y Efecto Dominó (OpenSRANE)</span>
          <button 
            className="btn btn-primary"
            onClick={handleRunDomino}
            disabled={loading}
          >
            {loading ? "⏳ Calculando Red OpenSRANE..." : "🚀 Ejecutar Red OpenSRANE"}
          </button>
        </div>

        <div className="alert alert-success">
          <div>
            <strong>Motor OpenSRANE v0.1.6 Activo (Multiplataforma):</strong> Simulación orientada a objetos de pérdidas de contención, radiación/sobrepresión y efecto dominó en red compleja.
          </div>
        </div>

        <div className="grid-3" style={{ marginTop: '1rem' }}>
          <div className="metric-box">
            <span className="metric-label">Equipo Primario Emisor</span>
            <span className="metric-value" style={{ color: '#38bdf8' }}>{simParams.tag_emisor}</span>
            <span className="metric-sub">{simParams.tipo_equipo} ({simParams.sustancia})</span>
          </div>
          <div className="metric-box">
            <span className="metric-label">Condiciones Termodinámicas</span>
            <span className="metric-value">{simParams.presion_bar} bar | {simParams.temperatura_c} °C</span>
            <span className="metric-sub">Orificio: {simParams.diametro_orificio_mm} mm</span>
          </div>
          <div className="metric-box">
            <span className="metric-label">Total Nodos en Red</span>
            <span className="metric-value">{equipos.length} Unidades</span>
            <span className="metric-sub">Matriz {equipos.length} x {equipos.length} Interdistancias</span>
          </div>
        </div>

        {/* ÁRBOL DE OBJETOS OPENSRANE */}
        {simDomino?.sim_data?.arbol_objetos && (
          <div style={{ marginTop: '1.25rem', background: '#0f172a', border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', color: '#38bdf8', marginBottom: '0.6rem' }}>
              🌳 Árbol de Objetos Generado en OpenSRANE (Memoria de Simulación Activa):
            </h4>
            <div className="grid-3">
              <div>
                <span className="metric-label">Site (Límites de Planta)</span>
                <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: '0.2rem' }}>
                  Temp: {simDomino.sim_data.arbol_objetos.Site?.Temperatura_K?.toFixed(1)} K | Pres: {simDomino.sim_data.arbol_objetos.Site?.Presion_Pa?.toLocaleString()} Pa
                </div>
              </div>
              <div>
                <span className="metric-label">OutFlow Model</span>
                <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: '0.2rem' }}>
                  {simDomino.sim_data.arbol_objetos.OutFlowModel?.tipo} (Orificio: {(simDomino.sim_data.arbol_objetos.OutFlowModel?.diametro_orificio_m * 1000).toFixed(1)} mm)
                </div>
              </div>
              <div>
                <span className="metric-label">Physical Effect</span>
                <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: '0.2rem' }}>
                  {simDomino.sim_data.arbol_objetos.PhysicalEffect?.tipo}
                </div>
              </div>
            </div>

            <div style={{ marginTop: '0.8rem' }}>
              <span className="metric-label">PlantUnits Mapeadas en Red ({simDomino.sim_data.arbol_objetos.PlantUnits?.length || 0}):</span>
              <div className="table-responsive" style={{ marginTop: '0.4rem' }}>
                <table className="custom-table" style={{ fontSize: '0.72rem' }}>
                  <thead>
                    <tr>
                      <th>OpenSRANE ID</th>
                      <th>Tag</th>
                      <th>Tipo</th>
                      <th>Posición Local X (m)</th>
                      <th>Posición Local Y (m)</th>
                      <th>Diámetro (m)</th>
                      <th>Altura (m)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simDomino.sim_data.arbol_objetos.PlantUnits?.map(u => (
                      <tr key={u.tag_id}>
                        <td style={{ color: '#38bdf8', fontWeight: 700 }}>Unit #{u.tag_id}</td>
                        <td style={{ fontWeight: 700 }}>{u.tag}</td>
                        <td>{u.tipo}</td>
                        <td>{u.x_m} m</td>
                        <td>{u.y_m} m</td>
                        <td>{u.diametro_m} m</td>
                        <td>{u.altura_m} m</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* DIAGRAMA DE PROPAGACIÓN EN CADENA */}
        <div style={{ marginTop: '1.25rem', background: '#0f172a', border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1rem', color: '#f1f5f9', marginBottom: '0.75rem' }}>
            🌳 Árbol de Propagación & Escalamiento Secundario (Domino Cascade)
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1.5rem', flexWrap: 'wrap', padding: '1rem' }}>
            <div style={{ background: '#7f1d1d', border: '2px solid #ef4444', borderRadius: '0.5rem', padding: '1rem', minWidth: '160px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.4rem' }}>💥</div>
              <div style={{ fontWeight: 800, color: '#fff', fontSize: '1.1rem' }}>{simParams.tag_emisor}</div>
              <div style={{ fontSize: '0.75rem', color: '#fecaca' }}>Iniciador Primario</div>
              <div style={{ fontSize: '0.72rem', color: '#cbd5e1', marginTop: '4px' }}>{simParams.sustancia}</div>
            </div>

            <div style={{ fontSize: '2rem', color: '#ef4444' }}>➔</div>

            <div style={{ background: '#78350f', border: '2px solid #f59e0b', borderRadius: '0.5rem', padding: '1rem', minWidth: '180px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.4rem' }}>⚠️</div>
              <div style={{ fontWeight: 800, color: '#fff', fontSize: '1.1rem' }}>Receptores 1er Nivel</div>
              <div style={{ fontSize: '0.75rem', color: '#fef08a' }}>Afectación Radiación / Choque</div>
              <div style={{ fontSize: '0.72rem', color: '#cbd5e1', marginTop: '4px' }}>Probit Falla: Cozzani 2005</div>
            </div>

            <div style={{ fontSize: '2rem', color: '#f59e0b' }}>➔</div>

            <div style={{ background: '#1e3a8a', border: '2px solid #38bdf8', borderRadius: '0.5rem', padding: '1rem', minWidth: '180px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.4rem' }}>🏭</div>
              <div style={{ fontWeight: 800, color: '#fff', fontSize: '1.1rem' }}>Escalamiento Global</div>
              <div style={{ fontSize: '0.75rem', color: '#bae6fd' }}>Pérdida Máxima Probable (PML)</div>
              <div style={{ fontSize: '0.72rem', color: '#cbd5e1', marginTop: '4px' }}>Parada Integral de Planta</div>
            </div>
          </div>
        </div>

        {/* TABLA DE RECEPTORES EVALUADOS OPENSRANE & PROBIT COZZANI */}
        {simDomino?.sim_data?.receptores_evaluados && simDomino.sim_data.receptores_evaluados.length > 0 && (
          <div style={{ marginTop: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', color: '#f1f5f9', marginBottom: '0.75rem' }}>
              💥 Vulnerabilidad de Receptores en Red (Probit Cozzani 2005 & Daño Físico OpenSRANE)
            </h3>
            <div className="table-responsive">
              <table className="custom-table" style={{ fontSize: '0.75rem' }}>
                <thead>
                  <tr>
                    <th>Tag Receptor</th>
                    <th>Tipo Activo</th>
                    <th>Distancia</th>
                    <th>Carga Incidente</th>
                    <th>Probit Y</th>
                    <th>Prob. Falla Pf</th>
                    <th>Escalamiento Secundario</th>
                    <th>Diagnóstico Dominó</th>
                  </tr>
                </thead>
                <tbody>
                  {simDomino.sim_data.receptores_evaluados.map(r => (
                    <tr key={r['TAG Receptor']}>
                      <td style={{ fontWeight: 700, color: '#38bdf8' }}>{r['TAG Receptor']}</td>
                      <td>{r['Tipo de Activo']}</td>
                      <td>{r['Distancia (m)']?.toFixed(1)} m</td>
                      <td style={{ color: '#f59e0b', fontWeight: 600 }}>{r['Carga Incidente']}</td>
                      <td style={{ fontFamily: 'monospace' }}>{r['Probit Y'] !== null && r['Probit Y'] !== undefined ? r['Probit Y'].toFixed(2) : 'N/A'}</td>
                      <td>
                        <span className={`badge ${r['Probabilidad Falla Pf (%)'] > 10 ? 'badge-danger' : (r['Probabilidad Falla Pf (%)'] > 0 ? 'badge-orange' : 'badge-green')}`}>
                          {r['Probabilidad Falla Pf (%)'] !== null && r['Probabilidad Falla Pf (%)'] !== undefined ? `${r['Probabilidad Falla Pf (%)'].toFixed(1)}%` : '0.0%'}
                        </span>
                      </td>
                      <td>
                        <span style={{ color: r['color_vector'] || '#cbd5e1', fontWeight: 600 }}>
                          {r['Escalamiento Secundario']}
                        </span>
                      </td>
                      <td style={{ color: '#cbd5e1', fontSize: '0.7rem' }}>{r['Diagnóstico Efecto Dominó']}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* MATRIZ DE INTERDISTANCIAS GEODÉSICAS */}
        {distMatrix && (
          <div style={{ marginTop: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', color: '#f1f5f9', marginBottom: '0.75rem' }}>
              📐 Matriz Geodésica de Interdistancias (Metros)
            </h3>
            <div className="table-responsive">
              <table className="custom-table" style={{ fontSize: '0.75rem' }}>
                <thead>
                  <tr>
                    <th>Tag \ Receptor</th>
                    {distMatrix.columns?.map(c => <th key={c}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {distMatrix.index?.map((rowName, rIdx) => (
                    <tr key={rowName}>
                      <td style={{ fontWeight: 700, color: '#38bdf8' }}>{rowName}</td>
                      {distMatrix.data[rIdx]?.map((val, cIdx) => (
                        <td key={cIdx} style={{ color: val === 0 ? '#64748b' : (val < 25 ? '#ef4444' : '#cbd5e1') }}>
                          {val === 0 ? '-' : `${val.toFixed(1)} m`}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ==============================================================================
// DATOS CLIMATOLÓGICOS DE RESPALDO (8,760 HORAS CARTAGENA / MAMONAL)
// ==============================================================================
const DEFAULT_WIND_DATA = {
  datos: {
    lat: 10.314855,
    lon: -75.487632,
    total_horas_analizadas: 8760,
    sector_predominante: "NNE",
    velocidad_media_global_ms: 2.42,
    calmas_pct: 1.56,
    sectores: ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"],
    frecuencias_pct: {
      "N": 10.9, "NNE": 16.02, "NE": 8.86, "ENE": 4.09, "E": 5.07, "ESE": 4.6,
      "SE": 4.92, "SSE": 4.65, "S": 4.66, "SSW": 4.98, "SW": 5.59, "WSW": 4.9,
      "W": 4.94, "WNW": 4.87, "NW": 5.32, "NNW": 5.64
    },
    velocidades_medias_sector: {
      "N": 3.35, "NNE": 2.87, "NE": 1.86, "ENE": 1.55, "E": 1.81, "ESE": 1.87,
      "SE": 1.84, "SSE": 1.89, "S": 2.07, "SSW": 2.54, "SW": 2.6, "WSW": 2.43,
      "W": 2.22, "WNW": 2.42, "NW": 2.51, "NNW": 2.97
    },
    matriz_bins_pct: {
      "0 - 2 m/s": [3.03, 4.46, 5.56, 3.31, 3.28, 2.73, 3.04, 2.84, 2.28, 1.82, 2.1, 1.67, 1.94, 1.76, 2.04, 2.04],
      "2 - 4 m/s": [3.96, 8.54, 3.23, 0.78, 1.66, 1.82, 1.83, 1.75, 2.23, 2.73, 2.66, 2.89, 2.84, 2.74, 2.6, 2.05],
      "4 - 6 m/s": [2.97, 2.87, 0.07, 0.0, 0.14, 0.06, 0.06, 0.06, 0.15, 0.43, 0.79, 0.34, 0.16, 0.38, 0.64, 1.19],
      "6 - 8 m/s": [0.94, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 0.0, 0.03, 0.35],
      "> 8 m/s": [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    },
    sectores_lista: [
      { sector: "N", frecuencia_pct: 10.9, velocidad_media_ms: 3.35, angulo_centro_deg: 0.0, angulo_downwind_deg: 180.0 },
      { sector: "NNE", frecuencia_pct: 16.02, velocidad_media_ms: 2.87, angulo_centro_deg: 22.5, angulo_downwind_deg: 202.5 },
      { sector: "NE", frecuencia_pct: 8.86, velocidad_media_ms: 1.86, angulo_centro_deg: 45.0, angulo_downwind_deg: 225.0 },
      { sector: "ENE", frecuencia_pct: 4.09, velocidad_media_ms: 1.55, angulo_centro_deg: 67.5, angulo_downwind_deg: 247.5 },
      { sector: "E", frecuencia_pct: 5.07, velocidad_media_ms: 1.81, angulo_centro_deg: 90.0, angulo_downwind_deg: 270.0 },
      { sector: "ESE", frecuencia_pct: 4.6, velocidad_media_ms: 1.87, angulo_centro_deg: 112.5, angulo_downwind_deg: 292.5 },
      { sector: "SE", frecuencia_pct: 4.92, velocidad_media_ms: 1.84, angulo_centro_deg: 135.0, angulo_downwind_deg: 315.0 },
      { sector: "SSE", frecuencia_pct: 4.65, velocidad_media_ms: 1.89, angulo_centro_deg: 157.5, angulo_downwind_deg: 337.5 },
      { sector: "S", frecuencia_pct: 4.66, velocidad_media_ms: 2.07, angulo_centro_deg: 180.0, angulo_downwind_deg: 0.0 },
      { sector: "SSW", frecuencia_pct: 4.98, velocidad_media_ms: 2.54, angulo_centro_deg: 202.5, angulo_downwind_deg: 22.5 },
      { sector: "SW", frecuencia_pct: 5.59, velocidad_media_ms: 2.6, angulo_centro_deg: 225.0, angulo_downwind_deg: 45.0 },
      { sector: "WSW", frecuencia_pct: 4.9, velocidad_media_ms: 2.43, angulo_centro_deg: 247.5, angulo_downwind_deg: 67.5 },
      { sector: "W", frecuencia_pct: 4.94, velocidad_media_ms: 2.22, angulo_centro_deg: 270.0, angulo_downwind_deg: 90.0 },
      { sector: "WNW", frecuencia_pct: 4.87, velocidad_media_ms: 2.42, angulo_centro_deg: 292.5, angulo_downwind_deg: 112.5 },
      { sector: "NW", frecuencia_pct: 5.32, velocidad_media_ms: 2.51, angulo_centro_deg: 315.0, angulo_downwind_deg: 135.0 },
      { sector: "NNW", frecuencia_pct: 5.64, velocidad_media_ms: 2.97, angulo_centro_deg: 337.5, angulo_downwind_deg: 157.5 }
    ]
  },
  meteoblue_url: "https://www.meteoblue.com/es/tiempo/semana/10.3149N75.4876W",
  meteoblue_windmap_url: "https://www.meteoblue.com/es/tiempo/mapas#coords=10.3149/-75.4876/13&map=windAnimation~rainbow~auto~10m~none"
};

// ==============================================================================
// COMPONENTE: ROSA DE LOS VIENTOS POLAR EN SVG NATIVO (100% OFFLINE & ROBUSTO)
// ==============================================================================
function WindRoseSVG({ datos }) {
  const [hovered, setHovered] = useState(null);

  const d = datos || DEFAULT_WIND_DATA.datos;
  const width = 430;
  const height = 430;
  const cx = width / 2;
  const cy = height / 2;
  const maxRadius = 155;
  const maxFreq = 20.0;

  const speedBins = [
    { key: "0 - 2 m/s", color: "#60a5fa", label: "0 - 2 m/s" },
    { key: "2 - 4 m/s", color: "#38bdf8", label: "2 - 4 m/s" },
    { key: "4 - 6 m/s", color: "#34d399", label: "4 - 6 m/s" },
    { key: "6 - 8 m/s", color: "#fbbf24", label: "6 - 8 m/s" },
    { key: "> 8 m/s", color: "#f87171", label: "> 8 m/s" }
  ];

  const gridCircles = [5, 10, 15, 20];

  const p2c = (r, deg) => {
    const rad = (deg * Math.PI) / 180;
    return [cx + r * Math.sin(rad), cy - r * Math.cos(rad)];
  };

  const getWedgePath = (rIn, rOut, degStart, degEnd) => {
    const [x1Out, y1Out] = p2c(rOut, degStart);
    const [x2Out, y2Out] = p2c(rOut, degEnd);
    if (rIn <= 0.5) {
      return `M ${cx.toFixed(1)} ${cy.toFixed(1)} L ${x1Out.toFixed(1)} ${y1Out.toFixed(1)} A ${rOut.toFixed(1)} ${rOut.toFixed(1)} 0 0 1 ${x2Out.toFixed(1)} ${y2Out.toFixed(1)} Z`;
    }
    const [x1In, y1In] = p2c(rIn, degStart);
    const [x2In, y2In] = p2c(rIn, degEnd);
    return `M ${x1In.toFixed(1)} ${y1In.toFixed(1)} L ${x1Out.toFixed(1)} ${y1Out.toFixed(1)} A ${rOut.toFixed(1)} ${rOut.toFixed(1)} 0 0 1 ${x2Out.toFixed(1)} ${y2Out.toFixed(1)} L ${x2In.toFixed(1)} ${y2In.toFixed(1)} A ${rIn.toFixed(1)} ${rIn.toFixed(1)} 0 0 0 ${x1In.toFixed(1)} ${y1In.toFixed(1)} Z`;
  };

  const wedges = [];
  if (d.sectores && d.matriz_bins_pct) {
    d.sectores.forEach((sec, secIdx) => {
      const centerDeg = secIdx * 22.5;
      const startDeg = centerDeg - 9.8;
      const endDeg = centerDeg + 9.8;

      let cumFreq = 0;
      speedBins.forEach(bin => {
        const vals = d.matriz_bins_pct[bin.key] || [];
        const val = vals[secIdx] || 0;
        if (val > 0) {
          const rIn = (cumFreq / maxFreq) * maxRadius;
          const nextCum = cumFreq + val;
          const rOut = (nextCum / maxFreq) * maxRadius;
          const path = getWedgePath(rIn, rOut, startDeg, endDeg);
          wedges.push({
            sector: sec,
            bin: bin.key,
            val: val,
            cumFreq: nextCum,
            color: bin.color,
            path: path,
            centerDeg: centerDeg
          });
          cumFreq = nextCum;
        }
      });
    });
  }

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {/* HUD BADGE DE HOVER */}
      <div style={{ 
        minHeight: '26px', 
        marginBottom: '6px', 
        fontSize: '0.78rem', 
        color: hovered ? '#38bdf8' : '#94a3b8',
        background: 'rgba(15, 23, 42, 0.8)',
        padding: '2px 12px',
        borderRadius: '9999px',
        border: '1px solid #334155',
        fontWeight: 600
      }}>
        {hovered ? (
          <span>
            📍 <strong>{hovered.sector}</strong> | Rango: <strong style={{ color: hovered.color }}>{hovered.bin}</strong> | Frecuencia: <strong>{hovered.val.toFixed(2)}%</strong> (Acum: {hovered.cumFreq.toFixed(1)}%)
          </span>
        ) : (
          <span>Pase el cursor sobre cualquier sector para ver detalles</span>
        )}
      </div>

      <svg 
        width="100%" 
        height="390" 
        viewBox={`0 0 ${width} ${height}`} 
        style={{ background: 'radial-gradient(circle, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.95) 75%)', borderRadius: '0.75rem', border: '1px solid #334155' }}
      >
        <defs>
          <radialGradient id="hubGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#0f172a" stopOpacity="0.9" />
          </radialGradient>
        </defs>

        {/* CÍRCULOS CONCÉNTRICOS DE FRECUENCIA */}
        {gridCircles.map(pct => {
          const r = (pct / maxFreq) * maxRadius;
          return (
            <g key={pct}>
              <circle 
                cx={cx} 
                cy={cy} 
                r={r} 
                fill="none" 
                stroke="#334155" 
                strokeDasharray="4, 4" 
                strokeWidth="1.2" 
              />
              <text 
                x={cx + 4} 
                y={cy - r + 11} 
                fill="#64748b" 
                fontSize="10" 
                fontWeight="600"
              >
                {pct}%
              </text>
            </g>
          );
        })}

        {/* RADIOS / RAYOS CARDINALES */}
        {d.sectores?.map((sec, i) => {
          const deg = i * 22.5;
          const [xSpoke, ySpoke] = p2c(maxRadius + 4, deg);
          const [xLabel, yLabel] = p2c(maxRadius + 18, deg);
          const isPredominant = sec === d.sector_predominante;
          const isPrimary = (i % 4 === 0);

          return (
            <g key={sec}>
              <line 
                x1={cx} 
                y1={cy} 
                x2={xSpoke} 
                y2={ySpoke} 
                stroke={isPrimary ? '#475569' : '#1e293b'} 
                strokeWidth={isPrimary ? 1.2 : 0.8} 
              />
              <text 
                x={xLabel} 
                y={yLabel + 4} 
                textAnchor="middle" 
                fill={isPredominant ? '#38bdf8' : (isPrimary ? '#f8fafc' : '#94a3b8')} 
                fontSize={isPrimary ? "12" : "10"} 
                fontWeight={isPredominant || isPrimary ? "800" : "500"}
              >
                {sec}
              </text>
            </g>
          );
        })}

        {/* PÉTALOS POLARES DE VIENTO APILADOS */}
        {wedges.map((w, idx) => {
          const isHovered = hovered && hovered.sector === w.sector && hovered.bin === w.bin;
          return (
            <path 
              key={idx} 
              d={w.path} 
              fill={w.color} 
              fillOpacity={isHovered ? 1 : 0.85} 
              stroke={isHovered ? "#ffffff" : "rgba(15, 23, 42, 0.4)"} 
              strokeWidth={isHovered ? 1.8 : 0.6}
              style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
              onMouseEnter={() => setHovered(w)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}

        {/* CENTRO DE BRÚJULA */}
        <circle cx={cx} cy={cy} r={16} fill="url(#hubGrad)" stroke="#38bdf8" strokeWidth="1.5" />
        <circle cx={cx} cy={cy} r={3} fill="#38bdf8" />

        {/* FLECHA INDICADORA DE NORTE */}
        <polygon 
          points={`${cx},${cy - maxRadius - 24} ${cx - 5},${cy - maxRadius - 13} ${cx + 5},${cy - maxRadius - 13}`} 
          fill="#ef4444" 
        />
        <text 
          x={cx} 
          y={cy - maxRadius - 28} 
          textAnchor="middle" 
          fill="#ef4444" 
          fontSize="11" 
          fontWeight="900"
        >
          N
        </text>
      </svg>

      {/* LEYENDA DE RANGOS DE VELOCIDAD */}
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'center', marginTop: '0.6rem' }}>
        {speedBins.map(b => (
          <div key={b.key} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.72rem', color: '#cbd5e1' }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: b.color, display: 'inline-block' }} />
            <span>{b.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==============================================================================
// TAB 4: ROSA DE VIENTOS & ESTÁNDARES QRA (BEVI / PURPLE / NIST)
// ==============================================================================
function TabQRAStandards({ simParams, simResult }) {
  const [windData, setWindData] = useState(DEFAULT_WIND_DATA);
  const [beviData, setBeviData] = useState(null);
  const [purpleData, setPurpleData] = useState(null);
  const [loadingWind, setLoadingWind] = useState(false);
  const [chartMode, setChartMode] = useState('svg'); // 'svg' (nativa) o 'plotly'
  const plotlyContainerRef = useRef(null);

  useEffect(() => {
    fetchWind();
    fetchBevi();
    fetchPurple();
  }, []);

  const fetchWind = async () => {
    try {
      setLoadingWind(true);
      const res = await fetch("/api/qra/rosa-vientos?lat=10.314855&lon=-75.487632");
      if (res.ok) {
        const d = await res.json();
        if (d && d.datos) {
          setWindData(d);
        }
      }
    } catch (e) {
      console.warn("Usando datos eólicos de respaldo:", e);
    } finally {
      setLoadingWind(false);
    }
  };

  const fetchBevi = async () => {
    try {
      const res = await fetch("/api/qra/bevi-frecuencias");
      if (res.ok) {
        const d = await res.json();
        setBeviData(d);
      }
    } catch (e) {
      console.warn(e);
    }
  };

  const fetchPurple = async () => {
    try {
      const res = await fetch("/api/qra/purple-book");
      if (res.ok) {
        const d = await res.json();
        setPurpleData(d);
      }
    } catch (e) {
      console.warn(e);
    }
  };

  // Renderizar gráfico Plotly si el usuario activa el modo 'plotly' y window.Plotly está disponible
  useEffect(() => {
    if (chartMode === 'plotly' && window.Plotly && plotlyContainerRef.current && windData?.plotly_fig) {
      try {
        const layout = {
          ...windData.plotly_fig.layout,
          paper_bgcolor: 'rgba(15, 23, 42, 0.95)',
          plot_bgcolor: 'rgba(15, 23, 42, 0.95)',
          font: { color: '#f8fafc', size: 11 },
          polar: {
            ...windData.plotly_fig.layout.polar,
            bgcolor: 'rgba(30, 41, 59, 0.7)',
            radialaxis: {
              ...windData.plotly_fig.layout.polar?.radialaxis,
              gridcolor: '#475569',
              linecolor: '#475569'
            },
            angularaxis: {
              ...windData.plotly_fig.layout.polar?.angularaxis,
              gridcolor: '#475569',
              linecolor: '#475569'
            }
          },
          margin: { l: 40, r: 40, t: 30, b: 50 },
          height: 400
        };
        Plotly.newPlot(plotlyContainerRef.current, windData.plotly_fig.data, layout, { responsive: true, displayModeBar: false });
      } catch (err) {
        console.error("Error rendering Plotly wind rose:", err);
      }
    }
  }, [chartMode, windData]);

  const datosEolicos = windData?.datos || DEFAULT_WIND_DATA.datos;

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <span className="card-title">🌪️ 1. Rosa de los Vientos Climatológica (Meteoblue / Reanálisis Horario 8,760 h)</span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {/* TOGGLE MODO DE VISUALIZACIÓN */}
            <div style={{ display: 'flex', background: '#0f172a', padding: '2px', borderRadius: '6px', border: '1px solid #334155' }}>
              <button 
                className={`btn ${chartMode === 'svg' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: '0.72rem', padding: '0.2rem 0.6rem' }}
                onClick={() => setChartMode('svg')}
              >
                🧭 Polar SVG
              </button>
              <button 
                className={`btn ${chartMode === 'plotly' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: '0.72rem', padding: '0.2rem 0.6rem' }}
                onClick={() => setChartMode('plotly')}
              >
                📈 Plotly
              </button>
            </div>

            {windData?.meteoblue_url && (
              <a 
                href={windData.meteoblue_url} 
                target="_blank" 
                rel="noreferrer"
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
              >
                🌐 Meteoblue Pronóstico ↗
              </a>
            )}
            {windData?.meteoblue_windmap_url && (
              <a 
                href={windData.meteoblue_windmap_url} 
                target="_blank" 
                rel="noreferrer"
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
              >
                💨 Mapa de Viento en Vivo ↗
              </a>
            )}
          </div>
        </div>

        <div className="grid-2">
          {/* GRÁFICO POLAR (SVG NATIVO O PLOTLY SEGÚN TOGGLE) */}
          <div>
            {chartMode === 'svg' ? (
              <WindRoseSVG datos={datosEolicos} />
            ) : (
              <div>
                <div 
                  ref={plotlyContainerRef} 
                  style={{ width: '100%', height: 420, borderRadius: '0.5rem', overflow: 'hidden' }}
                >
                  {loadingWind && (
                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
                      ⏳ Cargando datos climatológicos Meteoblue...
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* MÉTRICAS Y DATOS EÓLICOS */}
          <div>
            <div className="grid-3">
              <div className="metric-box">
                <span className="metric-label">Rumbo Predominante</span>
                <span className="metric-value" style={{ color: '#38bdf8' }}>
                  {datosEolicos.sector_predominante || 'NNE'}
                </span>
                <span className="metric-sub">Sopla hacia el SSW (Downwind)</span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Velocidad Media Global</span>
                <span className="metric-value">{datosEolicos.velocidad_media_global_ms ? datosEolicos.velocidad_media_global_ms.toFixed(2) : '2.42'} m/s</span>
                <span className="metric-sub">{((datosEolicos.velocidad_media_global_ms || 2.42) * 3.6).toFixed(1)} km/h</span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Porcentaje Calmas</span>
                <span className="metric-value">{datosEolicos.calmas_pct ? datosEolicos.calmas_pct.toFixed(1) : '1.6'}%</span>
                <span className="metric-sub">Condición D/F dispersión lenta</span>
              </div>
            </div>

            {/* TABLA DE 16 SECTORES CARDINALES */}
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
                📊 Distribución Frecuencia por Sector (16 Rumbos OMM):
              </h4>
              <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                <table className="custom-table" style={{ fontSize: '0.72rem' }}>
                  <thead>
                    <tr>
                      <th>Sector</th>
                      <th>Frecuencia (%)</th>
                      <th>Vel. Media (m/s)</th>
                      <th>Azimut Viento (°)</th>
                      <th>Azimut Pluma (°)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(datosEolicos.sectores_lista || []).map(item => {
                      const isMax = item.sector === datosEolicos.sector_predominante;
                      return (
                        <tr key={item.sector} style={{ background: isMax ? 'rgba(56, 189, 248, 0.15)' : 'transparent' }}>
                          <td style={{ fontWeight: 700, color: isMax ? '#38bdf8' : '#fff' }}>{item.sector}</td>
                          <td><strong>{item.frecuencia_pct ? item.frecuencia_pct.toFixed(2) : '0.00'}%</strong></td>
                          <td>{item.velocidad_media_ms ? item.velocidad_media_ms.toFixed(2) : '0.00'} m/s</td>
                          <td>{item.angulo_centro_deg}°</td>
                          <td style={{ color: '#f59e0b', fontWeight: 600 }}>{item.angulo_downwind_deg}°</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. BEVI V4.2 FRECUENCIAS LOC */}
      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">📗 2. BEVI v4.2 (RIVM): Frecuencias Genéricas de Pérdida de Contención (LOC)</span>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
          Frecuencias anuales estándar de fuga y ruptura catastrófica según la directiva oficial holandesa para Análisis Cuantitativo de Riesgo (QRA).
        </p>
        <div className="table-responsive">
          <table className="custom-table">
            <thead>
              <tr>
                <th>Categoría de Activo (BEVI)</th>
                <th>Frecuencia Ruptura Instantánea (año⁻¹)</th>
                <th>Frecuencia Fuga Continua 10 min (año⁻¹)</th>
                <th>Frecuencia Total LOC (año⁻¹)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontWeight: 600 }}>Recipiente a Presión (Vessels / Drums)</td>
                <td>5.0 × 10⁻⁷</td>
                <td>5.0 × 10⁻⁶</td>
                <td style={{ color: '#38bdf8', fontWeight: 700 }}>5.5 × 10⁻⁶</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Tubería de Proceso (por cada 10 metros)</td>
                <td>1.0 × 10⁻⁶</td>
                <td>5.0 × 10⁻⁵</td>
                <td style={{ color: '#38bdf8', fontWeight: 700 }}>5.1 × 10⁻⁵</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Bombas de Proceso (Sello Simple)</td>
                <td>1.0 × 10⁻⁴</td>
                <td>2.5 × 10⁻³</td>
                <td style={{ color: '#38bdf8', fontWeight: 700 }}>2.6 × 10⁻³</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Compresores Centrífugos / Reciprocantes</td>
                <td>1.0 × 10⁻⁴</td>
                <td>2.0 × 10⁻³</td>
                <td style={{ color: '#38bdf8', fontWeight: 700 }}>2.1 × 10⁻³</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Intercambiadores de Calor (Carcasa y Tubos)</td>
                <td>1.0 × 10⁻⁶</td>
                <td>1.0 × 10⁻⁵</td>
                <td style={{ color: '#38bdf8', fontWeight: 700 }}>1.1 × 10⁻⁵</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. PURPLE BOOK (PGS 3) PROBABILIDAD DE IGNICIÓN */}
      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">📘 3. Purple Book (PGS 3): Probabilidades de Ignición Directa & Diferida</span>
        </div>
        <div className="grid-3">
          <div className="metric-box">
            <span className="metric-label">Ignición Inmediata (P_direct)</span>
            <span className="metric-value">
              {simResult?.qra_full?.probabilidades_purple_book?.p_direct !== undefined ? (simResult.qra_full.probabilidades_purple_book.p_direct * 100).toFixed(1) + '%' : '50.0%'}
            </span>
            <span className="metric-sub">Jet Fire / Fireball inmediato</span>
          </div>
          <div className="metric-box">
            <span className="metric-label">Ignición Diferida (P_delayed)</span>
            <span className="metric-value">
              {simResult?.qra_full?.probabilidades_purple_book?.p_delayed !== undefined ? (simResult.qra_full.probabilidades_purple_book.p_delayed * 100).toFixed(1) + '%' : '94.1%'}
            </span>
            <span className="metric-sub">Fuentes fijas/móviles en planta</span>
          </div>
          <div className="metric-box">
            <span className="metric-label">Probabilidad Total de Fuego</span>
            <span className="metric-value" style={{ color: '#ef4444' }}>
              {simResult?.qra_full?.probabilidades_purple_book?.p_ignicion_total !== undefined ? (simResult.qra_full.probabilidades_purple_book.p_ignicion_total * 100).toFixed(1) + '%' : '97.0%'}
            </span>
            <span className="metric-sub">P_total = P_dir + (1-P_dir)·P_del</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==============================================================================
// TAB 5: CRITICIDAD FINANCIERA MÁXIMA (PML) & MATRIZ DE DAÑO
// ==============================================================================
function TabFinanciero({ equipos, simResult, damageMatrix, fetchDamageMatrix }) {
  const [editingRow, setEditingRow] = useState(null);
  const [editFormData, setEditFormData] = useState({});

  const afectados = simResult?.afectados || [];
  let totalDanoDirecto = 0;
  let totalLucroCesante = 0;
  let maxDiasParada = 0;
  let activoCritico = "Ninguno";
  let maxPerdidaActivo = 0;

  afectados.forEach(af => {
    const valRep = af.valor_reposicion_usd || 850000;
    const pctDano = (af.dano_estimado_pct ? parseFloat(af.dano_estimado_pct) : 45.0) / 100.0;
    const danoDirecto = valRep * pctDano;
    const dias = af.dias_parada || 45.0;
    const impactoDiario = af.impacto_diario_usd || 40000;
    const lucro = dias * impactoDiario;
    const totalActivo = danoDirecto + lucro;

    totalDanoDirecto += danoDirecto;
    totalLucroCesante += lucro;
    if (dias > maxDiasParada) maxDiasParada = dias;
    if (totalActivo > maxPerdidaActivo) {
      maxPerdidaActivo = totalActivo;
      activoCritico = af.tag;
    }
  });

  const totalPML = totalDanoDirecto + totalLucroCesante;

  const handleResetExcel = async () => {
    if (!confirm("¿Desea restablecer la matriz de daño a los valores estándar de ingeniería?")) return;
    try {
      const res = await fetch("/api/financiero/matriz-dano/reset", { method: "POST" });
      const data = await res.json();
      alert(data.message || "Matriz restablecida con éxito");
      fetchDamageMatrix();
    } catch (e) {
      console.error(e);
      alert("Error al restablecer matriz");
    }
  };

  const handleSaveDamageRow = async (e) => {
    e.preventDefault();
    const updated = damageMatrix.map(r => r.id === editFormData.id ? { ...r, ...editFormData } : r);
    try {
      const res = await fetch("/api/financiero/matriz-dano", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated)
      });
      if (res.ok) {
        alert("Modificaciones guardadas en la base de datos");
        setEditingRow(null);
        fetchDamageMatrix();
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <div className="grid-4">
        <div className="metric-box">
          <span className="metric-label">Pérdida Máxima Probable (PML)</span>
          <span className="metric-value" style={{ color: '#ef4444' }}>${(totalPML / 1e6).toFixed(2)}M USD</span>
          <span className="metric-sub">${totalPML.toLocaleString()} USD totales</span>
        </div>
        <div className="metric-box">
          <span className="metric-label">Daño Directo a la Propiedad</span>
          <span className="metric-value">${(totalDanoDirecto / 1e6).toFixed(2)}M USD</span>
          <span className="metric-sub">${totalDanoDirecto.toLocaleString()} USD activos</span>
        </div>
        <div className="metric-box">
          <span className="metric-label">Lucro Cesante / Parada</span>
          <span className="metric-value">${(totalLucroCesante / 1e6).toFixed(2)}M USD</span>
          <span className="metric-sub">Downtime máx: {maxDiasParada} días</span>
        </div>
        <div className="metric-box">
          <span className="metric-label">Activo Más Crítico</span>
          <span className="metric-value" style={{ color: '#38bdf8' }}>{activoCritico}</span>
          <span className="metric-sub">Impacto individual: ${(maxPerdidaActivo / 1e6).toFixed(2)}M USD</span>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">💼 Desglose de Pérdidas Financieras por Activo Afectado</span>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Escenario: {simResult?.consecuencia?.tipo || 'Simulación Activa'}
          </span>
        </div>
        {afectados.length > 0 ? (
          <div className="table-responsive">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Valor Reposición</th>
                  <th>% Daño Físico</th>
                  <th>Pérdida Directa</th>
                  <th>Días Parada</th>
                  <th>Lucro Cesante Diario</th>
                  <th>Pérdida Lucro Cesante</th>
                  <th>Pérdida Total Activo</th>
                </tr>
              </thead>
              <tbody>
                {afectados.map((af, i) => {
                  const valRep = af.valor_reposicion_usd || 850000;
                  const pctDano = (af.dano_estimado_pct ? parseFloat(af.dano_estimado_pct) : 45.0) / 100.0;
                  const danoDirecto = valRep * pctDano;
                  const dias = af.dias_parada || 45.0;
                  const impactoDiario = af.impacto_diario_usd || 40000;
                  const lucro = dias * impactoDiario;
                  const totalActivo = danoDirecto + lucro;

                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 700, color: '#f87171' }}>{af.tag}</td>
                      <td>${valRep.toLocaleString()} USD</td>
                      <td><strong>{(pctDano * 100).toFixed(0)}%</strong></td>
                      <td style={{ color: '#fbbf24', fontWeight: 600 }}>${danoDirecto.toLocaleString()}</td>
                      <td>{dias} días</td>
                      <td>${impactoDiario.toLocaleString()}/día</td>
                      <td style={{ color: '#fbbf24', fontWeight: 600 }}>${lucro.toLocaleString()}</td>
                      <td style={{ color: '#ef4444', fontWeight: 800 }}>${totalActivo.toLocaleString()} USD</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="alert alert-info">
            Para evaluar las pérdidas financieras de un escenario de fuga específico, incremente el diámetro de orificio o modifique la presión de proceso en la pestaña 2 para alcanzar activos circundantes.
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header">
          <span className="card-title">🗄️ Matriz de Daño y Tiempo de Reparación vs. Psig & kW/m² (Base de Datos SQLite)</span>
          <button className="btn btn-secondary" onClick={handleResetExcel}>
            🔄 Restablecer desde Estándares
          </button>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
          Umbrales físicos de radiación térmica y sobrepresión clasificados por categoría de equipo (Leve, Medio, Severo), con tiempos de parada y acciones de mitigación.
        </p>
        <div className="table-responsive">
          <table className="custom-table" style={{ fontSize: '0.75rem' }}>
            <thead>
              <tr>
                <th>Tipo Equipo</th>
                <th>Ps Leve (kPa)</th>
                <th>q Leve (kW/m²)</th>
                <th>Daño Leve</th>
                <th>Tiempo Leve</th>
                <th>Ps Severo (kPa)</th>
                <th>q Severo (kW/m²)</th>
                <th>Daño Severo</th>
                <th>Lead Time Severo</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {damageMatrix.map((row) => (
                <tr key={row.id}>
                  <td style={{ fontWeight: 700, color: '#38bdf8' }}>{row.tipo_equipo}</td>
                  <td>{row.ps_leve_min_kpa} – {row.ps_leve_max_kpa}</td>
                  <td>{row.q_leve_kw_m2}</td>
                  <td><span className="badge badge-green">{row.dano_leve_pct}</span></td>
                  <td>{row.tiempo_leve_txt}</td>
                  <td>{row.ps_severo_min_kpa}</td>
                  <td>{row.q_severo_kw_m2}</td>
                  <td><span className="badge badge-red">{row.dano_severo_pct}</span></td>
                  <td>{row.lead_time_severo_txt}</td>
                  <td>
                    <button 
                      className="btn btn-secondary" 
                      style={{ padding: '0.15rem 0.4rem', fontSize: '0.7rem' }}
                      onClick={() => {
                        setEditingRow(row);
                        setEditFormData(row);
                      }}
                    >
                      ✏️ Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editingRow && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="card-header">
              <span className="card-title">✏️ Modificar Umbrales de Daño: {editingRow.tipo_equipo}</span>
              <button className="btn btn-secondary" onClick={() => setEditingRow(null)}>✕</button>
            </div>
            <form onSubmit={handleSaveDamageRow}>
              <div className="grid-3">
                <div className="form-group">
                  <label>Ps Leve Min (kPa):</label>
                  <input 
                    type="number" 
                    step="0.5" 
                    className="form-control" 
                    value={editFormData.ps_leve_min_kpa || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, ps_leve_min_kpa: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label>q Leve (kW/m²):</label>
                  <input 
                    type="number" 
                    step="0.5" 
                    className="form-control" 
                    value={editFormData.q_leve_kw_m2 || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, q_leve_kw_m2: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label>Daño Leve (%):</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    value={editFormData.dano_leve_pct || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, dano_leve_pct: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid-3" style={{ marginTop: '0.5rem' }}>
                <div className="form-group">
                  <label>Ps Severo (kPa):</label>
                  <input 
                    type="number" 
                    step="0.5" 
                    className="form-control" 
                    value={editFormData.ps_severo_min_kpa || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, ps_severo_min_kpa: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label>q Severo (kW/m²):</label>
                  <input 
                    type="number" 
                    step="0.5" 
                    className="form-control" 
                    value={editFormData.q_severo_kw_m2 || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, q_severo_kw_m2: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label>Daño Severo (%):</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    value={editFormData.dano_severo_pct || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, dano_severo_pct: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setEditingRow(null)}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-success">
                  💾 Guardar Cambios en SQLite
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function ModalEquipo({ equipo, onClose, onSaved }) {
  const [formData, setFormData] = useState({ ...equipo });

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`/api/equipos/${equipo.tag}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        alert("Equipo actualizado correctamente");
        onSaved();
      } else {
        alert("Error al actualizar equipo");
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="card-header">
          <span className="card-title">✏️ Modificar Activo: {equipo.tag}</span>
          <button className="btn btn-secondary" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSave}>
          <div className="grid-2">
            <div className="form-group">
              <label>Tipo de Equipo:</label>
              <input 
                type="text" 
                className="form-control" 
                value={formData.tipo_equipo} 
                onChange={(e) => setFormData({ ...formData, tipo_equipo: e.target.value })} 
              />
            </div>
            <div className="form-group">
              <label>Sustancia:</label>
              <input 
                type="text" 
                className="form-control" 
                value={formData.sustancia} 
                onChange={(e) => setFormData({ ...formData, sustancia: e.target.value })} 
              />
            </div>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label>Latitud (WGS84):</label>
              <input 
                type="number" 
                step="0.000001" 
                className="form-control" 
                value={formData.latitud} 
                onChange={(e) => setFormData({ ...formData, latitud: parseFloat(e.target.value) })} 
              />
            </div>
            <div className="form-group">
              <label>Longitud (WGS84):</label>
              <input 
                type="number" 
                step="0.000001" 
                className="form-control" 
                value={formData.longitud} 
                onChange={(e) => setFormData({ ...formData, longitud: parseFloat(e.target.value) })} 
              />
            </div>
          </div>

          <div className="grid-3">
            <div className="form-group">
              <label>Presión (bar):</label>
              <input 
                type="number" 
                step="0.1" 
                className="form-control" 
                value={formData.presion_bar} 
                onChange={(e) => setFormData({ ...formData, presion_bar: parseFloat(e.target.value) })} 
              />
            </div>
            <div className="form-group">
              <label>Temperatura (°C):</label>
              <input 
                type="number" 
                step="0.1" 
                className="form-control" 
                value={formData.temperatura_c} 
                onChange={(e) => setFormData({ ...formData, temperatura_c: parseFloat(e.target.value) })} 
              />
            </div>
            <div className="form-group">
              <label>Inventario (kg):</label>
              <input 
                type="number" 
                step="100" 
                className="form-control" 
                value={formData.inventario_kg} 
                onChange={(e) => setFormData({ ...formData, inventario_kg: parseFloat(e.target.value) })} 
              />
            </div>
          </div>

          <div className="grid-3">
            <div className="form-group">
              <label>Valor Reposición ($ USD):</label>
              <input 
                type="number" 
                className="form-control" 
                value={formData.valor_reposicion_usd} 
                onChange={(e) => setFormData({ ...formData, valor_reposicion_usd: parseFloat(e.target.value) })} 
              />
            </div>
            <div className="form-group">
              <label>Lead Time (Meses):</label>
              <input 
                type="number" 
                step="0.5" 
                className="form-control" 
                value={formData.lead_time_meses} 
                onChange={(e) => setFormData({ ...formData, lead_time_meses: parseFloat(e.target.value) })} 
              />
            </div>
            <div className="form-group">
              <label>Impacto Diario ($ USD):</label>
              <input 
                type="number" 
                className="form-control" 
                value={formData.impacto_diario_usd} 
                onChange={(e) => setFormData({ ...formData, impacto_diario_usd: parseFloat(e.target.value) })} 
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary">
              💾 Guardar Cambios
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
