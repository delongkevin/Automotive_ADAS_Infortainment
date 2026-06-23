import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import Svg, { Polyline, Rect, Text as SvgText } from 'react-native-svg';

const API_BASE = 'http://10.0.2.2:8000';

const SCENARIOS = [
  { name: 'highway_cruise', label: 'Highway Cruise' },
  { name: 'emergency_braking', label: 'Emergency Braking' },
  { name: 'blind_spot_detection', label: 'Blind Spot Detection' },
  { name: 'city_driving_tsr', label: 'City Driving (TSR)' },
  { name: 'surround_view_camera', label: 'Surround View' },
  { name: 'autonomous_parking_parallel', label: 'Parking - Parallel' },
  { name: 'trailer_assistance', label: 'Trailer Assistance' },
];

export default function SimulationScreen() {
  const [scenario, setScenario] = useState('highway_cruise');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const runSimulation = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dt: 0.1, duration: 5.0, scenario }),
      });
      const data = await res.json();
      setResult(data);
    } catch {
      setResult({ error: 'Connection failed' });
    }
    setLoading(false);
  };

  const trace = result?.vehicle_trace || [];
  const maxSpeed = Math.max(...trace.map((p) => p.speed_kmh || 0), 1);

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Run Simulation</Text>
      <Text style={styles.subtitle}>Select a scenario and run the vehicle simulation</Text>

      {/* Scenario selector */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Scenario</Text>
        <View style={styles.scenarioGrid}>
          {SCENARIOS.map((s) => (
            <TouchableOpacity
              key={s.name}
              style={[styles.scenarioBtn, scenario === s.name && styles.scenarioBtnActive]}
              onPress={() => setScenario(s.name)}
            >
              <Text style={[styles.scenarioBtnText, scenario === s.name && { color: '#00d4ff' }]}>
                {s.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity style={styles.runBtn} onPress={runSimulation} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#0f1923" />
          ) : (
            <Text style={styles.runBtnText}>Run Simulation</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Results */}
      {result && !result.error && (
        <>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Speed Trace</Text>
            <View style={{ backgroundColor: '#0a1520', borderRadius: 8, padding: 8 }}>
              <Svg width="100%" height="120" viewBox="0 0 300 120">
                <Rect width="300" height="120" fill="#0a1520" />
                {trace.length > 1 && (
                  <Polyline
                    fill="none"
                    stroke="#00d4ff"
                    strokeWidth="2"
                    points={trace.map((pt, i) => {
                      const x = 10 + (i / trace.length) * 280;
                      const y = 110 - (pt.speed_kmh / maxSpeed) * 90;
                      return `${x},${y}`;
                    }).join(' ')}
                  />
                )}
                <SvgText x="150" y="115" textAnchor="middle" fill="#7a8fa0" fontSize="8">
                  Speed (km/h) over time
                </SvgText>
              </Svg>
            </View>
          </View>

          <View style={styles.metricsRow}>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{result.duration?.toFixed(1)}s</Text>
              <Text style={styles.metricLabel}>Duration</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{result.steps}</Text>
              <Text style={styles.metricLabel}>Steps</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{result.adas_events?.length || 0}</Text>
              <Text style={styles.metricLabel}>Events</Text>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Radio Display State</Text>
            <View style={styles.ecuRow}>
              <View style={[styles.dot, { backgroundColor: result.radio_display?.adas_icons?.acc_active ? '#00e676' : '#7a8fa0' }]} />
              <Text style={styles.ecuText}>ACC: {result.radio_display?.adas_icons?.acc_active ? 'Active' : 'Off'}</Text>
            </View>
            <View style={styles.ecuRow}>
              <View style={[styles.dot, { backgroundColor: result.radio_display?.adas_icons?.ldw_active ? '#ffab00' : '#00e676' }]} />
              <Text style={styles.ecuText}>LDW: {result.radio_display?.adas_icons?.ldw_active ? 'WARNING' : 'Ready'}</Text>
            </View>
            <View style={styles.ecuRow}>
              <View style={[styles.dot, { backgroundColor: result.radio_display?.adas_icons?.aeb_warning ? '#ff5252' : '#00e676' }]} />
              <Text style={styles.ecuText}>AEB: {result.radio_display?.adas_icons?.aeb_warning ? 'BRAKING' : 'Ready'}</Text>
            </View>
          </View>
        </>
      )}

      {result?.error && (
        <View style={[styles.card, { borderColor: 'rgba(255,82,82,0.3)' }]}>
          <Text style={{ color: '#ff5252' }}>{result.error}</Text>
          <Text style={styles.subtitle}>Make sure the backend API is running on port 8000</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f1923', padding: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#e0e8f0', marginBottom: 4 },
  subtitle: { fontSize: 12, color: '#7a8fa0', marginBottom: 16 },
  card: { backgroundColor: '#1a2733', borderRadius: 8, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },
  cardTitle: { fontSize: 11, color: '#7a8fa0', textTransform: 'uppercase', marginBottom: 12 },
  scenarioGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  scenarioBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', backgroundColor: 'rgba(0,0,0,0.2)' },
  scenarioBtnActive: { borderColor: '#00d4ff', backgroundColor: 'rgba(0,212,255,0.1)' },
  scenarioBtnText: { fontSize: 11, color: '#7a8fa0' },
  runBtn: { backgroundColor: '#00d4ff', padding: 12, borderRadius: 8, alignItems: 'center' },
  runBtnText: { color: '#0f1923', fontSize: 14, fontWeight: '600' },
  metricsRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  metricCard: { flex: 1, backgroundColor: '#1a2733', borderRadius: 8, padding: 12, alignItems: 'center' },
  metricValue: { fontSize: 20, fontWeight: '700', color: '#00d4ff' },
  metricLabel: { fontSize: 10, color: '#7a8fa0', marginTop: 2 },
  ecuRow: { flexDirection: 'row', alignItems: 'center', padding: 8, backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 6, marginBottom: 6 },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  ecuText: { color: '#e0e8f0', fontSize: 13 },
});
