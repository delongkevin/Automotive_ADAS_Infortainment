"""
MIL (Model-in-the-Loop) Testing Framework for ADAS SIL System

Provides comprehensive testing infrastructure for ADAS features including:
- Scenario-based testing
- Performance metrics collection
- Real-time validation
- Results reporting and analysis
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np
from pathlib import Path


@dataclass
class PerformanceMetrics:
    """Collects and stores performance metrics for a test run"""
    feature_name: str
    test_name: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    
    # Execution metrics
    simulation_time: float = 0.0
    step_count: int = 0
    avg_step_time_ms: float = 0.0
    max_step_time_ms: float = 0.0
    min_step_time_ms: float = float('inf')
    
    # Validation metrics
    validations_passed: int = 0
    validations_failed: int = 0
    validation_accuracy: float = 0.0
    
    # Latency metrics
    max_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    latency_measurements: List[float] = field(default_factory=list)
    
    # Success/Failure
    passed: bool = False
    failure_reason: str = ""
    
    def finalize(self) -> None:
        """Finalize metrics and calculate derived values"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000.0
        
        if self.step_count > 0:
            self.avg_step_time_ms = self.simulation_time / self.step_count
        
        if self.latency_measurements:
            self.max_latency_ms = max(self.latency_measurements)
            self.avg_latency_ms = np.mean(self.latency_measurements)
        
        total_validations = self.validations_passed + self.validations_failed
        if total_validations > 0:
            self.validation_accuracy = self.validations_passed / total_validations


@dataclass
class ValidationResult:
    """Result of a single validation check"""
    name: str
    time: float
    passed: bool
    expected: Any
    actual: Any
    error_msg: str = ""
    latency_ms: float = 0.0


@dataclass
class ScenarioResults:
    """Results from running a complete scenario"""
    scenario_name: str
    test_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    
    metrics: Dict[str, PerformanceMetrics] = field(default_factory=dict)
    validations: List[ValidationResult] = field(default_factory=list)
    
    total_pass: int = 0
    total_fail: int = 0
    overall_pass: bool = False
    
    def add_metric(self, feature: str, metric: PerformanceMetrics) -> None:
        """Add performance metrics for a feature"""
        self.metrics[feature] = metric
        metric.finalize()
        
        if metric.passed:
            self.total_pass += 1
        else:
            self.total_fail += 1
    
    def add_validation(self, result: ValidationResult) -> None:
        """Add validation result"""
        self.validations.append(result)
    
    def finalize(self) -> None:
        """Finalize results"""
        self.overall_pass = self.total_fail == 0


class ScenarioValidator:
    """Validates feature behavior against scenario expectations"""
    
    def __init__(self, simulator: Any, metrics: PerformanceMetrics):
        self.simulator = simulator
        self.metrics = metrics
        self.validations: List[ValidationResult] = []
    
    def validate_field(
        self,
        validation_spec: Dict[str, Any],
        current_time: float
    ) -> Tuple[bool, str]:
        """Validate a single field against specification"""
        feature_name = validation_spec.get('feature')
        check_field = validation_spec.get('check_field')
        
        if feature_name not in self.simulator.adas_features:
            return False, f"Feature '{feature_name}' not found"
        
        feature = self.simulator.adas_features[feature_name]
        status = feature.status if hasattr(feature, 'status') else {}
        
        if check_field not in status:
            return False, f"Field '{check_field}' not in feature status"
        
        actual_value = status[check_field]
        
        # Handle different validation types
        if 'expected' in validation_spec:
            expected = validation_spec['expected']
            if actual_value != expected:
                return False, f"Expected {expected}, got {actual_value}"
        
        elif 'expected_min' in validation_spec:
            expected_min = validation_spec['expected_min']
            if actual_value < expected_min:
                return False, f"Expected >= {expected_min}, got {actual_value}"
        
        elif 'expected_min_abs' in validation_spec:
            expected_min = validation_spec['expected_min_abs']
            if abs(actual_value) < expected_min:
                return False, f"Expected |value| >= {expected_min}, got {actual_value}"
        
        elif 'expected_max_abs' in validation_spec:
            expected_max = validation_spec['expected_max_abs']
            if abs(actual_value) > expected_max:
                return False, f"Expected |value| <= {expected_max}, got {actual_value}"
        
        elif 'expected_contains' in validation_spec:
            expected_value = validation_spec['expected_contains']
            if isinstance(actual_value, list):
                if expected_value not in actual_value:
                    return False, f"Expected {expected_value} in {actual_value}"
            else:
                return False, f"Expected list value, got {type(actual_value)}"
        
        return True, "Validation passed"
    
    def record_validation(
        self,
        name: str,
        time: float,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
        error_msg: str = "",
        latency_ms: float = 0.0
    ) -> None:
        """Record a validation result"""
        result = ValidationResult(
            name=name,
            time=time,
            passed=passed,
            expected=expected,
            actual=actual,
            error_msg=error_msg,
            latency_ms=latency_ms
        )
        self.validations.append(result)
        
        if passed:
            self.metrics.validations_passed += 1
        else:
            self.metrics.validations_failed += 1


class MILScenarioRunner:
    """Executes MIL test scenarios and collects metrics"""
    
    def __init__(self, simulator: Any):
        """
        Args:
            simulator: ADASSILSimulator instance
        """
        self.simulator = simulator
        self.results_list: List[ScenarioResults] = []
        self.pending_detections: Dict[str, List[Dict]] = {}  # Active sign/object detections indexed by time
    
    def load_scenario(self, scenario_path: str) -> Dict[str, Any]:
        """Load scenario from JSON file"""
        with open(scenario_path, 'r') as f:
            return json.load(f)
    
    def run_scenario(self, scenario_path: str) -> ScenarioResults:
        """Run a complete test scenario"""
        scenario = self.load_scenario(scenario_path)
        scenario_name = scenario.get('name', Path(scenario_path).stem)
        
        # Initialize result tracking
        results = ScenarioResults(scenario_name=scenario_name)
        
        # Setup vehicle configuration
        vehicle_config = scenario.get('vehicle_config', {})
        if 'enabled_features' in vehicle_config:
            self._enable_features(vehicle_config['enabled_features'])
        
        # Initialize metrics for each feature
        feature_metrics: Dict[str, PerformanceMetrics] = {}
        for feature_name in vehicle_config.get('enabled_features', []):
            feature_metrics[feature_name] = PerformanceMetrics(
                feature_name=feature_name,
                test_name=scenario_name
            )
        
        # Run simulation with events
        duration = scenario.get('duration', 60.0)
        events = scenario.get('events', [])
        dt = self.simulator.dt
        
        current_time = 0.0
        event_index = 0
        validations = []
        step_times = []
        
        print(f"\n{'='*70}")
        print(f"Running MIL Scenario: {scenario_name}")
        print(f"Duration: {duration}s | Events: {len(events)}")
        print(f"{'='*70}")
        
        while current_time < duration:
            step_start = time.time()
            
            # Process events at current time
            while event_index < len(events) and events[event_index]['time'] <= current_time:
                event = events[event_index]
                self._process_event(event, results, feature_metrics, current_time)
                event_index += 1
            
            # Get vehicle state
            vehicle_state = self.simulator.vehicle.get_state()
            
            # Collect sensor data
            sensor_data = []
            for sensor in self.simulator.sensors.values():
                detections = sensor.sense(self.simulator.vehicle, self.simulator.environment, current_time)
                sensor_data.extend(detections)
            
            # Inject pending detections into sensor data (from environment_setup events)
            sensor_data.extend(self._get_active_detections(current_time))
            
            # Update simulation
            self.simulator.step()
            
            # Record metrics
            step_time = (time.time() - step_start) * 1000.0
            step_times.append(step_time)
            
            for metrics in feature_metrics.values():
                metrics.step_count += 1
                metrics.simulation_time += dt
                metrics.max_step_time_ms = max(metrics.max_step_time_ms, step_time)
                metrics.min_step_time_ms = min(metrics.min_step_time_ms, step_time)
            
            current_time += dt
        
        # Process success criteria
        success_criteria = scenario.get('success_criteria', {})
        for feature_name, metrics in feature_metrics.items():
            metrics.passed = self._check_success_criteria(
                metrics, 
                success_criteria,
                results
            )
            results.add_metric(feature_name, metrics)
        
        results.duration_seconds = duration
        results.finalize()
        
        # Print summary
        self._print_scenario_summary(results)
        
        self.results_list.append(results)
        return results
    
    def _enable_features(self, feature_names: List[str]) -> None:
        """Enable specified ADAS features"""
        for feature_name in feature_names:
            if feature_name in self.simulator.adas_features:
                feature = self.simulator.adas_features[feature_name]
                if hasattr(feature, 'enable'):
                    feature.enable()
    
    def _process_event(
        self,
        event: Dict[str, Any],
        results: ScenarioResults,
        metrics: Dict[str, PerformanceMetrics],
        current_time: float = 0.0
    ) -> None:
        """Process a scenario event"""
        event_type = event.get('type')
        event_name = event.get('name')
        
        print(f"  [{event.get('time')}s] {event_name}")
        
        if event_type == 'validation':
            self._handle_validation(event, results, metrics)
        elif event_type == 'feature_command':
            self._handle_feature_command(event)
        elif event_type == 'vehicle_motion':
            self._handle_vehicle_motion(event)
        elif event_type == 'environment_setup':
            self._handle_environment_setup(event, current_time)
    
    def _handle_validation(
        self,
        event: Dict[str, Any],
        results: ScenarioResults,
        metrics: Dict[str, PerformanceMetrics]
    ) -> None:
        """Handle a validation event"""
        params = event.get('parameters', {})
        feature_name = params.get('feature')
        
        if feature_name not in metrics:
            return
        
        validator = ScenarioValidator(self.simulator, metrics[feature_name])
        passed, msg = validator.validate_field(params, event.get('time', 0.0))
        
        validator.record_validation(
            name=event.get('name'),
            time=event.get('time', 0.0),
            passed=passed,
            error_msg=msg
        )
        
        for validation in validator.validations:
            results.add_validation(validation)
        
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"    {status}: {msg}")
    
    def _handle_feature_command(self, event: Dict[str, Any]) -> None:
        """Handle a feature command event"""
        params = event.get('parameters', {})
        feature_name = params.get('feature')
        command = params.get('command')
        
        if feature_name not in self.simulator.adas_features:
            return
        
        feature = self.simulator.adas_features[feature_name]
        
        if command == 'enable':
            if hasattr(feature, 'enable'):
                feature.enable()
        elif command == 'disable':
            if hasattr(feature, 'disable'):
                feature.disable()
        elif command == 'set_guidance_mode':
            if hasattr(feature, 'set_guidance_mode'):
                feature.set_guidance_mode(
                    params.get('mode', 'auto'),
                    strength=params.get('strength', 0.8)
                )
    
    def _handle_vehicle_motion(self, event: Dict[str, Any]) -> None:
        """Handle vehicle motion event"""
        params = event.get('parameters', {})
        duration = params.get('duration', 1.0)
        
        # Get current vehicle state
        vehicle_state = self.simulator.vehicle.get_state()
        
        if 'gear' in params:
            gear = params['gear']
            vehicle_state['gear'] = gear
        
        if 'speed_target' in params:
            target_speed = params['speed_target']
            current_speed = vehicle_state.get('velocity', {}).get('v', 0.0)
            accel = (target_speed - current_speed) / max(duration, 0.1)
            
            steps = int(duration / self.simulator.dt)
            for _ in range(steps):
                vehicle_state = self.simulator.vehicle.get_state()
                vehicle_state['velocity']['v'] = current_speed + accel * self.simulator.dt
                self.simulator.step()
        elif 'steering_angle' in params:
            # Handle steering
            steering = params['steering_angle']
            vehicle_state['steering_angle'] = steering
            self.simulator.step()
        else:
            # Just run the simulator for the duration
            steps = int(duration / self.simulator.dt)
            for _ in range(steps):
                self.simulator.step()
    
    def _handle_environment_setup(self, event: Dict[str, Any], current_time: float) -> None:
        """Handle environment setup event (traffic signs, obstacles, etc.)"""
        params = event.get('parameters', {})
        
        # Create detection object based on type
        sign_type = params.get('sign_type')
        if sign_type:
            # Create camera detection for traffic sign
            detection = {
                'sensor_type': 'camera',
                'sign_class': sign_type,
                'distance': params.get('distance', 50.0),
                'confidence': params.get('confidence', 0.9),
                'direction': params.get('direction', 'ahead'),
                'x': params.get('position', [0.0, 0.0])[0],
                'y': params.get('position', [0.0, 0.0])[1]
            }
            
            # Store detection for injection into sensor data
            # Detections are active for a duration (default 5 seconds)
            duration = params.get('active_duration', 5.0)
            end_time = current_time + duration
            
            if 'active_detections' not in self.__dict__:
                self.active_detections = {}
            
            if end_time not in self.active_detections:
                self.active_detections[end_time] = []
            
            self.active_detections[end_time].append(detection)
    
    def _get_active_detections(self, current_time: float) -> List[Dict]:
        """Get all active detections at current time"""
        if not hasattr(self, 'active_detections'):
            self.active_detections = {}
        
        active = []
        expired_times = []
        
        for end_time, detections in self.active_detections.items():
            if current_time < end_time:
                active.extend(detections)
            else:
                expired_times.append(end_time)
        
        # Clean up expired detections
        for end_time in expired_times:
            del self.active_detections[end_time]
        
        return active
    
    def _check_success_criteria(
        self,
        metrics: PerformanceMetrics,
        criteria: Dict[str, Any],
        results: ScenarioResults
    ) -> bool:
        """Check if metrics meet success criteria"""
        if criteria.get('all_validations_pass') and metrics.validations_failed > 0:
            metrics.failure_reason = f"{metrics.validations_failed} validations failed"
            return False
        
        if 'min_accuracy' in criteria:
            if metrics.validation_accuracy < criteria['min_accuracy']:
                metrics.failure_reason = f"Accuracy {metrics.validation_accuracy:.2%} below {criteria['min_accuracy']:.2%}"
                return False
        
        if 'max_latency_ms' in criteria:
            if metrics.max_latency_ms > criteria['max_latency_ms']:
                metrics.failure_reason = f"Max latency {metrics.max_latency_ms:.1f}ms exceeds {criteria['max_latency_ms']}ms"
                return False
        
        return True
    
    def _print_scenario_summary(self, results: ScenarioResults) -> None:
        """Print scenario execution summary"""
        overall_status = "✓ PASSED" if results.overall_pass else "✗ FAILED"
        
        print(f"\n{'-' * 70}")
        print(f"Scenario Result: {overall_status}")
        print(f"Duration: {results.duration_seconds:.2f}s")
        print(f"Total Validations: {results.total_pass + results.total_fail}")
        print(f"  Passed: {results.total_pass}")
        print(f"  Failed: {results.total_fail}")
        
        for feature_name, metrics in results.metrics.items():
            feature_status = "✓" if metrics.passed else "✗"
            print(f"\n{feature_status} Feature: {feature_name}")
            print(f"    Duration: {metrics.duration_ms:.2f}ms")
            print(f"    Validations: {metrics.validations_passed}/{metrics.validations_passed + metrics.validations_failed}")
            print(f"    Accuracy: {metrics.validation_accuracy:.1%}")
            if metrics.failure_reason:
                print(f"    Failure: {metrics.failure_reason}")
        
        print(f"{'-' * 70}\n")
    
    def generate_report(self, output_path: str = None) -> str:
        """Generate comprehensive MIL test report"""
        if not self.results_list:
            return "No test results to report"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("MIL (Model-in-the-Loop) TEST REPORT")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Summary statistics
        total_scenarios = len(self.results_list)
        passed_scenarios = sum(1 for r in self.results_list if r.overall_pass)
        
        report_lines.append("SUMMARY")
        report_lines.append("-" * 80)
        report_lines.append(f"Total Scenarios: {total_scenarios}")
        report_lines.append(f"Passed: {passed_scenarios}")
        report_lines.append(f"Failed: {total_scenarios - passed_scenarios}")
        report_lines.append(f"Success Rate: {passed_scenarios/total_scenarios*100:.1f}%")
        report_lines.append("")
        
        # Detailed results
        report_lines.append("DETAILED RESULTS")
        report_lines.append("-" * 80)
        
        for results in self.results_list:
            report_lines.append(f"\nScenario: {results.scenario_name}")
            report_lines.append(f"Timestamp: {results.test_timestamp}")
            report_lines.append(f"Status: {'PASSED' if results.overall_pass else 'FAILED'}")
            report_lines.append(f"Duration: {results.duration_seconds:.2f}s")
            report_lines.append(f"Validations: {results.total_pass}/{results.total_pass + results.total_fail}")
            
            for feature_name, metrics in results.metrics.items():
                report_lines.append(f"\n  Feature: {feature_name}")
                report_lines.append(f"    Status: {'PASS' if metrics.passed else 'FAIL'}")
                report_lines.append(f"    Step Count: {metrics.step_count}")
                report_lines.append(f"    Avg Step Time: {metrics.avg_step_time_ms:.3f}ms")
                report_lines.append(f"    Max Step Time: {metrics.max_step_time_ms:.3f}ms")
                report_lines.append(f"    Validation Accuracy: {metrics.validation_accuracy:.1%}")
                if metrics.failure_reason:
                    report_lines.append(f"    Failure Reason: {metrics.failure_reason}")
        
        report_lines.append("\n" + "=" * 80)
        
        report_text = "\n".join(report_lines)
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(report_text)
            print(f"Report saved to: {output_path}")
        
        return report_text


def run_mil_test_suite(simulator: Any, scenarios_dir: str = None) -> Dict[str, Any]:
    """
    Run complete MIL test suite
    
    Args:
        simulator: ADASSILSimulator instance
        scenarios_dir: Path to scenarios directory
    
    Returns:
        Dictionary with test results
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent / "scenarios"
    
    runner = MILScenarioRunner(simulator)
    
    # Discover and run all scenario files
    scenario_files = sorted(Path(scenarios_dir).glob("*.json"))
    
    print(f"\nDiscovered {len(scenario_files)} scenarios")
    print("Starting MIL Test Suite Execution...\n")
    
    for scenario_file in scenario_files:
        try:
            runner.run_scenario(str(scenario_file))
        except Exception as e:
            print(f"Error running scenario {scenario_file.name}: {e}")
    
    # Generate report
    report = runner.generate_report()
    print(report)
    
    return {
        'runner': runner,
        'results': runner.results_list,
        'report': report
    }
