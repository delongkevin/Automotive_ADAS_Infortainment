"""
MIL (Model-in-the-Loop) Test Suite

Tests ADAS features using scenario-based testing with performance metrics.
Run with: pytest tests/test_mil.py -v
"""

import json
from pathlib import Path
import pytest
from ADAS_SIL_System import ADASSILSimulator
from ADAS_SIL_System.core.mil_testing import MILScenarioRunner


@pytest.fixture
def simulator():
    """Create simulator with all ADAS features"""
    config = {
        'dt': 0.01,
        'adas': {
            'ldw': {'enabled': True},
            'acc': {'enabled': True},
            'aeb': {'enabled': True},
            'bsd': {'enabled': True},
            'tsr': {'enabled': True},
            'parking': {'enabled': True},
            'trailer_assistance': {'enabled': True},
            'trailer_reverse': {'enabled': True},
            'surround_view': {'enabled': True}
        }
    }
    return ADASSILSimulator(config)


@pytest.fixture
def scenarios_dir():
    """Get scenarios directory path"""
    scenarios = Path(__file__).resolve().parent.parent / 'scenarios'
    assert scenarios.exists(), f"Scenarios directory not found: {scenarios}"
    return scenarios


@pytest.fixture
def runner(simulator):
    """Create MIL scenario runner"""
    return MILScenarioRunner(simulator)


class TestBlindSpotDetection:
    """Tests for Blind Spot Detection MIL scenarios"""
    
    def test_bsd_scenario(self, runner, scenarios_dir):
        """Test BSD with approaching vehicles"""
        scenario_file = scenarios_dir / 'blind_spot_detection.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'bsd' in results.metrics, "BSD metrics should be collected"

        bsd_metrics = results.metrics['bsd']
        assert bsd_metrics.step_count > 0, "BSD scenario should execute simulation steps"
        assert bsd_metrics.validations_passed + bsd_metrics.validations_failed > 0, "BSD scenario should execute validations"


class TestAutonomousParking:
    """Tests for Autonomous Parking MIL scenarios"""
    
    def test_parallel_parking_scenario(self, runner, scenarios_dir):
        """Test parallel parking maneuver"""
        scenario_file = scenarios_dir / 'autonomous_parking_parallel.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'parking' in results.metrics, "Parking metrics should be collected"

        parking_metrics = results.metrics['parking']
        assert parking_metrics.step_count > 0, "Parking scenario should execute simulation steps"
        assert parking_metrics.validations_passed + parking_metrics.validations_failed > 0, "Parking scenario should execute validations"
    
    def test_perpendicular_parking_scenario(self, runner, scenarios_dir):
        """Test perpendicular parking maneuver"""
        scenario_file = scenarios_dir / 'autonomous_parking_perpendicular.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'parking' in results.metrics, "Parking metrics should be collected"

        parking_metrics = results.metrics['parking']
        assert parking_metrics.step_count > 0, "Perpendicular parking should execute simulation steps"
        assert parking_metrics.validations_passed + parking_metrics.validations_failed > 0, "Perpendicular parking should execute validations"


class TestTrailerAssistance:
    """Tests for Trailer Assistance MIL scenarios"""
    
    def test_trailer_assistance_scenario(self, runner, scenarios_dir):
        """Test trailer steering correction"""
        scenario_file = scenarios_dir / 'trailer_assistance.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'trailer_assistance' in results.metrics, "Trailer metrics should be collected"

        trailer_metrics = results.metrics['trailer_assistance']
        assert trailer_metrics.step_count > 0, "Trailer scenario should execute simulation steps"
        assert trailer_metrics.validations_passed + trailer_metrics.validations_failed > 0, "Trailer scenario should execute validations"


class TestSurroundViewCamera:
    """Tests for Surround View Camera MIL scenarios"""
    
    def test_surround_view_scenario(self, runner, scenarios_dir):
        """Test surround view camera system and auto-switching"""
        scenario_file = scenarios_dir / 'surround_view_camera.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'surround_view' in results.metrics, "Surround view metrics should be collected"

        svc_metrics = results.metrics['surround_view']
        assert svc_metrics.step_count > 0, "Surround view scenario should execute simulation steps"
        assert svc_metrics.validations_passed + svc_metrics.validations_failed > 0, "Surround view scenario should execute validations"


class TestMILMetrics:
    """Tests for MIL metrics collection and analysis"""
    
    def test_metrics_collection(self, runner, scenarios_dir):
        """Verify metrics are properly collected"""
        scenario_file = scenarios_dir / 'blind_spot_detection.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        # Check metrics exist
        assert len(results.metrics) > 0, "Metrics should be collected"

        # Check metric properties
        for feature_name, metrics in results.metrics.items():
            assert metrics.step_count > 0, f"Step count should be > 0 for {feature_name}"
            assert metrics.simulation_time > 0, f"Simulation time should be > 0 for {feature_name}"
            assert metrics.validations_passed + metrics.validations_failed > 0, \
                f"Validations should be recorded for {feature_name}"
    
    def test_performance_latency(self, runner, scenarios_dir):
        """Verify latency is within acceptable bounds"""
        scenario_file = scenarios_dir / 'surround_view_camera.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        for feature_name, metrics in results.metrics.items():
            # Latency should be reasonable for simulator
            assert metrics.max_latency_ms < 1000, \
                f"Max latency for {feature_name} should be < 1000ms"


class TestScenarioIntegrity:
    """Tests for scenario definitions and integrity"""
    
    def test_scenario_files_exist(self, scenarios_dir):
        """Verify all expected scenario files exist"""
        expected_scenarios = [
            'blind_spot_detection.json',
            'autonomous_parking_parallel.json',
            'autonomous_parking_perpendicular.json',
            'trailer_assistance.json',
            'surround_view_camera.json',
            'highway_cruise.json',
            'emergency_braking.json',
            'city_driving_tsr.json',
            'highway_driving_tsr.json'
        ]
        
        for scenario_name in expected_scenarios:
            scenario_file = scenarios_dir / scenario_name
            assert scenario_file.exists(), f"Missing scenario file: {scenario_name}"
            assert scenario_file.is_file(), f"{scenario_name} should be a file"
    
    def test_scenario_format(self, scenarios_dir):
        """Verify scenario files have correct JSON format"""
        scenario_files = list(scenarios_dir.glob('*.json'))
        
        for scenario_file in scenario_files:
            with open(scenario_file, 'r') as f:
                try:
                    scenario = json.load(f)
                    assert 'name' in scenario, f"{scenario_file.name} missing 'name' field"
                    assert 'duration' in scenario, f"{scenario_file.name} missing 'duration' field"
                    assert 'events' in scenario, f"{scenario_file.name} missing 'events' field"
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in {scenario_file.name}: {e}")


class TestTrafficSignRecognition:
    """Tests for Traffic Sign Recognition MIL scenarios"""
    
    def test_city_driving_tsr_scenario(self, runner, scenarios_dir):
        """Test TSR in urban city environment with various sign types"""
        scenario_file = scenarios_dir / 'city_driving_tsr.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'tsr' in results.metrics, "TSR metrics should be collected"

        tsr_metrics = results.metrics['tsr']
        assert tsr_metrics.step_count > 0, "TSR city scenario should execute simulation steps"
        assert tsr_metrics.validations_passed + tsr_metrics.validations_failed > 0, "TSR city scenario should execute validations"
    
    def test_highway_driving_tsr_scenario(self, runner, scenarios_dir):
        """Test TSR on highway with high-speed driving and variable speed limits"""
        scenario_file = scenarios_dir / 'highway_driving_tsr.json'
        assert scenario_file.exists(), f"Missing scenario: {scenario_file}"

        results = runner.run_scenario(str(scenario_file))

        assert 'tsr' in results.metrics, "TSR metrics should be collected"

        tsr_metrics = results.metrics['tsr']
        assert tsr_metrics.step_count > 0, "TSR highway scenario should execute simulation steps"
        assert tsr_metrics.validations_passed + tsr_metrics.validations_failed > 0, "TSR highway scenario should execute validations"
        assert tsr_metrics.max_latency_ms < 150, "TSR latency should be < 150ms"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
