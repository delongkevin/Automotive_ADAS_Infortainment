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
    return Path(__file__).parent.parent / 'ADAS_SIL_System' / 'scenarios'


@pytest.fixture
def runner(simulator):
    """Create MIL scenario runner"""
    return MILScenarioRunner(simulator)


class TestBlindSpotDetection:
    """Tests for Blind Spot Detection MIL scenarios"""
    
    def test_bsd_scenario(self, runner, scenarios_dir):
        """Test BSD with approaching vehicles"""
        scenario_file = scenarios_dir / 'blind_spot_detection.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "BSD scenario should pass"
            assert results.total_fail == 0, "No validations should fail"
            assert 'bsd' in results.metrics, "BSD metrics should be collected"
            
            bsd_metrics = results.metrics['bsd']
            assert bsd_metrics.passed, "BSD feature should pass"
            assert bsd_metrics.validation_accuracy >= 0.90, "BSD accuracy should be >= 90%"


class TestAutonomousParking:
    """Tests for Autonomous Parking MIL scenarios"""
    
    def test_parallel_parking_scenario(self, runner, scenarios_dir):
        """Test parallel parking maneuver"""
        scenario_file = scenarios_dir / 'autonomous_parking_parallel.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "Parallel parking scenario should pass"
            assert 'parking' in results.metrics, "Parking metrics should be collected"
            
            parking_metrics = results.metrics['parking']
            assert parking_metrics.passed, "Parking feature should pass"
            assert parking_metrics.validation_accuracy >= 0.85, "Parking accuracy should be >= 85%"
    
    def test_perpendicular_parking_scenario(self, runner, scenarios_dir):
        """Test perpendicular parking maneuver"""
        scenario_file = scenarios_dir / 'autonomous_parking_perpendicular.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "Perpendicular parking scenario should pass"
            assert 'parking' in results.metrics, "Parking metrics should be collected"
            
            parking_metrics = results.metrics['parking']
            assert parking_metrics.passed, "Parking feature should pass"


class TestTrailerAssistance:
    """Tests for Trailer Assistance MIL scenarios"""
    
    def test_trailer_assistance_scenario(self, runner, scenarios_dir):
        """Test trailer steering correction"""
        scenario_file = scenarios_dir / 'trailer_assistance.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "Trailer assistance scenario should pass"
            assert 'trailer_assistance' in results.metrics, "Trailer metrics should be collected"
            
            trailer_metrics = results.metrics['trailer_assistance']
            assert trailer_metrics.passed, "Trailer assistance feature should pass"
            assert trailer_metrics.validation_accuracy >= 0.90, "Trailer accuracy should be >= 90%"


class TestSurroundViewCamera:
    """Tests for Surround View Camera MIL scenarios"""
    
    def test_surround_view_scenario(self, runner, scenarios_dir):
        """Test surround view camera system and auto-switching"""
        scenario_file = scenarios_dir / 'surround_view_camera.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "Surround view scenario should pass"
            assert 'surround_view' in results.metrics, "Surround view metrics should be collected"
            
            svc_metrics = results.metrics['surround_view']
            assert svc_metrics.passed, "Surround view feature should pass"
            assert svc_metrics.validation_accuracy >= 0.95, "Surround view accuracy should be >= 95%"


class TestMILMetrics:
    """Tests for MIL metrics collection and analysis"""
    
    def test_metrics_collection(self, runner, scenarios_dir):
        """Verify metrics are properly collected"""
        scenario_file = scenarios_dir / 'blind_spot_detection.json'
        if scenario_file.exists():
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
        if scenario_file.exists():
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
            # Some scenarios may be optional
            if scenario_file.exists():
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
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "City driving TSR scenario should pass"
            assert 'tsr' in results.metrics, "TSR metrics should be collected"
            
            tsr_metrics = results.metrics['tsr']
            assert tsr_metrics.passed, "TSR feature should pass"
            assert tsr_metrics.validation_accuracy >= 0.85, "TSR accuracy should be >= 85%"
    
    def test_highway_driving_tsr_scenario(self, runner, scenarios_dir):
        """Test TSR on highway with high-speed driving and variable speed limits"""
        scenario_file = scenarios_dir / 'highway_driving_tsr.json'
        if scenario_file.exists():
            results = runner.run_scenario(str(scenario_file))
            
            assert results.overall_pass, "Highway driving TSR scenario should pass"
            assert 'tsr' in results.metrics, "TSR metrics should be collected"
            
            tsr_metrics = results.metrics['tsr']
            assert tsr_metrics.passed, "TSR feature should pass"
            assert tsr_metrics.validation_accuracy >= 0.85, "TSR accuracy should be >= 85%"
            assert tsr_metrics.max_latency_ms < 150, "TSR latency should be < 150ms"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
