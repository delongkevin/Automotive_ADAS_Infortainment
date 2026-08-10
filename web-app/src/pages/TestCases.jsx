import React, { useState } from 'react';
import { useEffect } from 'react';
import { apiRequest } from '../lib/api';

export default function TestCases() {
  const [testCases, setTestCases] = useState([]);
  const [results, setResults] = useState({});
  const [lastTestId, setLastTestId] = useState(null);
  const [running, setRunning] = useState(null);
  const [loadingCases, setLoadingCases] = useState(false);
  const [listError, setListError] = useState(null);

  useEffect(() => {
    const loadCases = async () => {
      setLoadingCases(true);
      setListError(null);
      try {
        const data = await apiRequest('/test-cases');
        setTestCases(data.test_cases || []);
      } catch (error) {
        setListError(error.message);
      } finally {
        setLoadingCases(false);
      }
    };

    loadCases();
  }, []);

  const runTest = async (tc) => {
    setRunning(tc.id);
    try {
      const data = await apiRequest('/test-cases/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_id: tc.id,
          scenario: tc.scenario,
          duration: tc.default_duration || 8.0,
          adas_features: tc.adas_features || ['ldw', 'acc', 'aeb'],
        }),
      });
      setResults((prev) => ({ ...prev, [tc.id]: data }));
      setLastTestId(tc.id);
    } catch (error) {
      setResults((prev) => ({
        ...prev,
        [tc.id]: { status: 'ERROR', error: error.message },
      }));
      setLastTestId(tc.id);
    }
    setRunning(null);
  };

  const runAll = async () => {
    for (const tc of testCases) {
      await runTest(tc);
    }
  };

  const lastResult = lastTestId ? results[lastTestId] : null;
  const lastChecks = lastResult?.validation?.checks || [];
  const passedChecks = lastChecks.filter((check) => check.passed).length;

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

      {loadingCases && <p className="page-subtitle">Loading test catalog...</p>}
      {listError && <p className="page-subtitle" style={{ color: '#ff8a80' }}>{listError}</p>}

      <div className="card">
        <ul className="test-list">
          {testCases.map((tc) => (
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
                {results[tc.id]?.error && (
                  <span className="metric-label" style={{ color: '#ff8a80' }}>{results[tc.id].error}</span>
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

          <div className="card">
            <div className="card-header">
              <h3>Validation Checks</h3>
            </div>
            {lastChecks.length === 0 ? (
              <div className="metric-label">Run a test to view deterministic pass/fail criteria.</div>
            ) : (
              <>
                <div className="metric-value">{passedChecks}/{lastChecks.length}</div>
                <div className="metric-label" style={{ marginBottom: '0.75rem' }}>Checks Passed</div>
                <ul className="test-list">
                  {lastChecks.map((check) => (
                    <li key={check.name} className="test-item" style={{ padding: '0.4rem 0' }}>
                      <span className={`status-badge ${check.passed ? 'pass' : 'fail'}`}>{check.passed ? 'PASS' : 'FAIL'}</span>
                      <span className="metric-label">{check.name}: expected {check.expected}, actual {check.actual}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
