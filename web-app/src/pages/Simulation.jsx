import React, { useState } from 'react';
import VehicleVisualizer from '../components/VehicleVisualizer';
import { apiRequest } from '../lib/api';

const SCENARIOS = [
  { name: 'highway_cruise', label: 'Highway Cruise' },
  { name: 'emergency_braking', label: 'Emergency Braking' },
  { name: 'blind_spot_detection', label: 'Blind Spot Detection' },
  { name: 'city_driving_tsr', label: 'City Driving (TSR)' },
  { name: 'highway_driving_tsr', label: 'Highway (TSR)' },
  { name: 'surround_view_camera', label: 'Surround View' },
  { name: 'autonomous_parking_parallel', label: 'Parking - Parallel' },
  { name: 'autonomous_parking_perpendicular', label: 'Parking - Perpendicular' },
  { name: 'trailer_assistance', label: 'Trailer Assistance' },
];

export default function Simulation() {
  const [scenario, setScenario] = useState('highway_cruise');
  const [duration, setDuration] = useState(5);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const runSimulation = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dt: 0.1, duration, scenario }),
      });
      setResult(data);
    } catch (error) {
      setResult({ error: error.message || 'Failed to connect to API' });
    }
    setLoading(false);
  };

  return (
    <div>
      <h2 className="page-title">Run Simulation</h2>
      <p className="page-subtitle">
        Configure and execute vehicle simulation with visual output
      </p>

      <div className="dashboard-grid">
        <div className="card">
          <div className="card-header"><h3>Configuration</h3></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <label>
              <div className="metric-label">Scenario</div>
              <select
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: '#0a1520', color: '#e0e8f0', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                {SCENARIOS.map((s) => (
                  <option key={s.name} value={s.name}>{s.label}</option>
                ))}
              </select>
            </label>
            <label>
              <div className="metric-label">Duration (seconds)</div>
              <input
                type="number"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                min={1}
                max={60}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: '#0a1520', color: '#e0e8f0', border: '1px solid rgba(255,255,255,0.1)' }}
              />
            </label>
            <button className="btn btn-primary" onClick={runSimulation} disabled={loading}>
              {loading ? 'Simulating...' : 'Run Simulation'}
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Vehicle View</h3></div>
          <VehicleVisualizer trace={result?.vehicle_trace} />
        </div>

        {result && !result.error && (
          <>
            <div className="card">
              <div className="card-header"><h3>Results</h3></div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <div className="metric-value">{result.duration?.toFixed(1)}s</div>
                  <div className="metric-label">Duration</div>
                </div>
                <div>
                  <div className="metric-value">{result.steps}</div>
                  <div className="metric-label">Steps</div>
                </div>
                <div>
                  <div className="metric-value">{result.adas_events?.length || 0}</div>
                  <div className="metric-label">ADAS Events</div>
                </div>
                <div>
                  <div className="metric-value">{result.radio_display?.warnings_triggered || 0}</div>
                  <div className="metric-label">Warnings</div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header"><h3>Radio Display State</h3></div>
              <div className="ecu-indicator">
                <div className="ecu-dot" />
                <span>LDW: {result.radio_display?.adas_icons?.ldw_active ? 'ACTIVE' : 'Ready'}</span>
              </div>
              <div className="ecu-indicator">
                <div className="ecu-dot" />
                <span>ACC: {result.radio_display?.adas_icons?.acc_active ? 'ACTIVE' : 'Off'}</span>
              </div>
              <div className="ecu-indicator">
                <div className="ecu-dot" style={{ background: result.radio_display?.adas_icons?.aeb_warning ? '#ff5252' : '#00e676' }} />
                <span>AEB: {result.radio_display?.adas_icons?.aeb_warning ? 'WARNING' : 'Ready'}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
