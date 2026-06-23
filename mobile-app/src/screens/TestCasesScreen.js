import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';

const API_BASE = 'http://10.0.2.2:8000';

const TEST_CASES = [
  { id: 'TC_AEB_Emergency', name: 'Automatic Emergency Braking', ecu: 'ADAS Camera', scenario: 'emergency_braking' },
  { id: 'TC_ACC_Highway', name: 'Adaptive Cruise Control', ecu: 'ADAS Camera', scenario: 'highway_cruise' },
  { id: 'TC_LDW_Departure', name: 'Lane Departure Warning', ecu: 'ADAS Camera', scenario: 'highway_cruise' },
  { id: 'TC_BSD_LaneChange', name: 'Blind Spot Detection', ecu: 'ADAS Camera', scenario: 'blind_spot_detection' },
  { id: 'TC_TSR_City', name: 'Traffic Sign Recognition - City', ecu: 'Radio Display', scenario: 'city_driving_tsr' },
  { id: 'TC_TSR_Highway', name: 'Traffic Sign Recognition - Highway', ecu: 'Radio Display', scenario: 'highway_driving_tsr' },
  { id: 'TC_SVC_Parking', name: 'Surround View Camera', ecu: 'Radio Display', scenario: 'surround_view_camera' },
  { id: 'TC_Parking_Parallel', name: 'Parking - Parallel', ecu: 'Radio Display', scenario: 'autonomous_parking_parallel' },
  { id: 'TC_Parking_Perpendicular', name: 'Parking - Perpendicular', ecu: 'Radio Display', scenario: 'autonomous_parking_perpendicular' },
  { id: 'TC_Trailer_Assist', name: 'Trailer Assistance', ecu: 'Radio Display', scenario: 'trailer_assistance' },
];

export default function TestCasesScreen() {
  const [results, setResults] = useState({});
  const [running, setRunning] = useState(null);

  const runTest = async (tc) => {
    setRunning(tc.id);
    try {
      const res = await fetch(`${API_BASE}/test-cases/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_id: tc.id,
          scenario: tc.scenario,
          duration: 3.0,
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

  const passCount = Object.values(results).filter((r) => r.status === 'PASS').length;
  const totalRun = Object.keys(results).length;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Test Cases</Text>
          <Text style={styles.subtitle}>Radio Display + ADAS Camera ECU Tests</Text>
        </View>
        <TouchableOpacity style={styles.btnPrimary} onPress={runAll}>
          <Text style={styles.btnText}>Run All</Text>
        </TouchableOpacity>
      </View>

      {totalRun > 0 && (
        <View style={styles.summaryCard}>
          <Text style={styles.summaryValue}>{passCount}/{totalRun}</Text>
          <Text style={styles.summaryLabel}>Tests Passed</Text>
        </View>
      )}

      {TEST_CASES.map((tc) => (
        <View key={tc.id} style={styles.testItem}>
          <View style={{ flex: 1 }}>
            <Text style={styles.testName}>{tc.name}</Text>
            <Text style={styles.testMeta}>{tc.ecu} | {tc.scenario}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {results[tc.id] && (
              <View style={[styles.badge, results[tc.id].status === 'PASS' ? styles.badgePass : styles.badgeFail]}>
                <Text style={[styles.badgeText, results[tc.id].status === 'PASS' ? { color: '#00e676' } : { color: '#ff5252' }]}>
                  {results[tc.id].status}
                </Text>
              </View>
            )}
            {running === tc.id ? (
              <ActivityIndicator size="small" color="#00d4ff" />
            ) : (
              <TouchableOpacity style={styles.btnOutline} onPress={() => runTest(tc)}>
                <Text style={styles.btnOutlineText}>Run</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f1923', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#e0e8f0' },
  subtitle: { fontSize: 12, color: '#7a8fa0', marginTop: 2 },
  summaryCard: { backgroundColor: '#1a2733', borderRadius: 8, padding: 16, marginBottom: 16, alignItems: 'center' },
  summaryValue: { fontSize: 32, fontWeight: '700', color: '#00d4ff' },
  summaryLabel: { fontSize: 12, color: '#7a8fa0' },
  testItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.04)' },
  testName: { fontSize: 14, color: '#e0e8f0' },
  testMeta: { fontSize: 11, color: '#7a8fa0', marginTop: 2 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 100 },
  badgePass: { backgroundColor: 'rgba(0,230,118,0.15)' },
  badgeFail: { backgroundColor: 'rgba(255,82,82,0.15)' },
  badgeText: { fontSize: 10, fontWeight: '700' },
  btnPrimary: { backgroundColor: '#00d4ff', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  btnText: { color: '#0f1923', fontSize: 13, fontWeight: '600' },
  btnOutline: { borderWidth: 1, borderColor: '#00d4ff', paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6 },
  btnOutlineText: { color: '#00d4ff', fontSize: 11, fontWeight: '600' },
});
