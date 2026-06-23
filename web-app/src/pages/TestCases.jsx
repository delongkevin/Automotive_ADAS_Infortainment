import React, { useState } from 'react';

const TEST_CASES = [
  { id: 'TC_AEB_Emergency', name: 'Automatic Emergency Braking', ecu: 'ADAS Camera', scenario: 'emergency_braking' },
  { id: 'TC_ACC_Highway', name: 'Adaptive Cruise Control - Highway', ecu: 'ADAS Camera', scenario: 'highway_cruise' },
  { id: 'TC_LDW_Departure', name: 'Lane Departure Warning', ecu: 'ADAS Camera', scenario: 'highway_cruise' },
  { id: 'TC_BSD_LaneChange', name: 'Blind Spot Detection', ecu: 'ADAS Camera', scenario: 'blind_spot_detection' },
  { id: 'TC_TSR_City', name: 'Traffic Sign Recognition - City', ecu: 'Radio Display', scenario: 'city_driving_tsr' },
  { id: 'TC_TSR_Highway', name: 'Traffic Sign Recognition - Highway', ecu: 'Radio Display', scenario: 'highway_driving_tsr' },
  { id: 'TC_SVC_Parking', name: 'Surround View Camera - Parking', ecu: 'Radio Display', scenario: 'surround_view_camera' },
  { id: 'TC_Parking_Parallel', name: 'Autonomous Parking - Parallel', ecu: 'Radio Display', scenario: 'autonomous_parking_parallel' },
  { id: 'TC_Parking_Perpendicular', name: 'Autonomous Parking - Perpendicular', ecu: 'Radio Display', scenario: 'autonomous_parking_perpendicular' },
  { id: 'TC_Trailer_Assist', name: 'Trailer Assistance', ecu: 'Radio Display', scenario: 'trailer_assistance' },
];

export default function TestCases() {
  const [results, setResults] = useState({});
  const [running, setRunning] = useState(null);

  const runTest = async (tc) => {
    setRunning(tc.id);
    try {
      const res = await fetch('/api/test-cases/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_id: tc.id,
          scenario: tc.scenario,
          duration: 5.0,
          adas_features: ['ldw', 'acc', 'aeb', 'bsd', 'tsr'],
        }),
      });
      const data = await res.json();
      setResults((prev) => ({ ...prev, [tc.id]: data }));
    } catch {
      setResults((prev) => ({ ...prev, [tc.id]: { status: 'ERROR' } }));
    }
    setRunning(null);
  };

  const runAll = async () => {
    for (const tc of TEST_CASES) {
      await runTest(tc);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 className="page-title">Test Case Execution</h2>
          <p className="page-subtitle">
            Execute ADAS test cases with visual output for Radio Display + Camera ECUs
          </p>
        </div>
        <button className="btn btn-primary" onClick={runAll}>
          Run All Tests
        </button>
      </div>

      <div className="card">
        <ul className="test-list">
          {TEST_CASES.map((tc) => (
            <li key={tc.id} className="test-item">
              <div>
                <div className="test-item-name">{tc.name}</div>
                <div className="test-item-ecu">{tc.ecu} &middot; {tc.scenario}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                {results[tc.id] && (
                  <span className={`status-badge ${results[tc.id].status === 'PASS' ? 'pass' : 'fail'}`}>
                    {results[tc.id].status}
                  </span>
                )}
                <button
                  className="btn btn-outline"
                  onClick={() => runTest(tc)}
                  disabled={running === tc.id}
                >
                  {running === tc.id ? 'Running...' : 'Run'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {Object.keys(results).length > 0 && (
        <div className="dashboard-grid" style={{ marginTop: '1.5rem' }}>
          <div className="card">
            <div className="card-header">
              <h3>Results Summary</h3>
            </div>
            <div className="metric-value">
              {Object.values(results).filter((r) => r.status === 'PASS').length}/{Object.keys(results).length}
            </div>
            <div className="metric-label">Tests Passed</div>
          </div>
          <div className="card">
            <div className="card-header">
              <h3>Last Execution Trace</h3>
            </div>
            <div className="vehicle-canvas" style={{ height: '150px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg className="trace-svg" viewBox="0 0 400 150">
                {Object.values(results).slice(-1).map((r) =>
                  r.vehicle_trace?.map((pt, i, arr) => {
                    if (i === 0) return null;
                    const prev = arr[i - 1];
                    const x1 = 20 + (prev.time / r.duration) * 360;
                    const y1 = 130 - (prev.speed_kmh / 150) * 120;
                    const x2 = 20 + (pt.time / r.duration) * 360;
                    const y2 = 130 - (pt.speed_kmh / 150) * 120;
                    return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#00d4ff" strokeWidth="1.5" />;
                  })
                )}
                <text x="10" y="145" fill="#7a8fa0" fontSize="8">Speed (km/h) over time</text>
              </svg>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
