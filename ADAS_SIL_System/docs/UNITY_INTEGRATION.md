# Unity/Unreal Engine Integration Guide

This guide explains how to integrate the ADAS SIL System with Unity or Unreal Engine for 3D visualization.

## Overview

The ADAS SIL System provides a WebSocket-based API that streams simulation state in real-time to your 3D visualization engine. The system uses JSON messages over WebSocket for maximum compatibility.

## Connection Setup

### Python Side (ADAS SIL)

Start the Unity bridge when launching the simulator:

```bash
python main.py --scenario highway_cruise --unity-bridge --port 5555
```

Or programmatically:

```python
from ADAS_SIL_System.visualization import UnityBridge

bridge = UnityBridge(host='localhost', port=5555)
bridge.start()

# In your simulation loop:
bridge.send_state(simulator.get_state())
```

### Unity Side (C#)

Create a WebSocket client to connect to the ADAS SIL bridge:

```csharp
using System;
using System.Collections;
using UnityEngine;
using WebSocketSharp;
using Newtonsoft.Json;

public class ADASSILClient : MonoBehaviour
{
    private WebSocket ws;
    public string serverUrl = "ws://localhost:5555";

    void Start()
    {
        ConnectToSIL();
    }

    void ConnectToSIL()
    {
        ws = new WebSocket(serverUrl);

        ws.OnMessage += (sender, e) =>
        {
            // Parse JSON message
            var data = JsonConvert.DeserializeObject<SimulationState>(e.Data);

            // Update Unity scene on main thread
            UnityMainThreadDispatcher.Instance().Enqueue(() => {
                UpdateVehicle(data);
                UpdateADAS(data);
            });
        };

        ws.OnOpen += (sender, e) =>
        {
            Debug.Log("Connected to ADAS SIL System");
        };

        ws.OnError += (sender, e) =>
        {
            Debug.LogError($"WebSocket Error: {e.Message}");
        };

        ws.Connect();
    }

    void OnDestroy()
    {
        if (ws != null && ws.IsAlive)
        {
            ws.Close();
        }
    }
}
```

### Unreal Engine Side (C++)

Using Unreal Engine's WebSocket plugin:

```cpp
#include "IWebSocket.h"
#include "WebSocketsModule.h"

class FADASSILClient
{
public:
    void Connect(const FString& ServerURL)
    {
        if (!FModuleManager::Get().IsModuleLoaded("WebSockets"))
        {
            FModuleManager::Get().LoadModule("WebSockets");
        }

        WebSocket = FWebSocketsModule::Get().CreateWebSocket(ServerURL);

        WebSocket->OnConnected().AddLambda([]()
        {
            UE_LOG(LogTemp, Log, TEXT("Connected to ADAS SIL System"));
        });

        WebSocket->OnMessage().AddLambda([this](const FString& Message)
        {
            // Parse JSON message
            TSharedPtr<FJsonObject> JsonObject;
            TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);

            if (FJsonSerializer::Deserialize(Reader, JsonObject))
            {
                UpdateFromSimulation(JsonObject);
            }
        });

        WebSocket->Connect();
    }

private:
    TSharedPtr<IWebSocket> WebSocket;
};
```

## Message Format

### State Update Message

The SIL system sends state updates at your configured frame rate:

```json
{
  "type": "state_update",
  "timestamp": 12.34,
  "vehicle": {
    "position": {
      "x": 123.45,
      "y": 67.89,
      "z": 0.0
    },
    "rotation": {
      "roll": 0.0,
      "pitch": 0.0,
      "yaw": 0.523
    },
    "velocity": {
      "vx": 25.0,
      "vy": 0.5,
      "vz": 0.0,
      "speed": 25.01
    },
    "controls": {
      "throttle": 0.3,
      "brake": 0.0,
      "steering_angle": 0.1
    }
  },
  "adas": {
    "ldw": {
      "feature": "LDW",
      "enabled": true,
      "warning_active": false,
      "warning_side": null,
      "lateral_offset": -0.05,
      "lane_width": 3.5
    },
    "acc": {
      "feature": "ACC",
      "enabled": true,
      "active": true,
      "set_speed": 27.78,
      "target_speed": 25.0,
      "lead_vehicle_detected": true,
      "lead_vehicle_distance": 45.2
    },
    "aeb": {
      "feature": "AEB",
      "enabled": true,
      "warning_active": false,
      "braking_active": false
    }
  }
}
```

### Command Message (Unity → SIL)

You can send commands back to the SIL system:

```json
{
  "command": "ping"
}

{
  "command": "get_status"
}
```

## Unity Example Implementation

### Data Classes

```csharp
[Serializable]
public class SimulationState
{
    public string type;
    public float timestamp;
    public VehicleData vehicle;
    public ADASData adas;
}

[Serializable]
public class VehicleData
{
    public Position position;
    public Rotation rotation;
    public Velocity velocity;
    public Controls controls;
}

[Serializable]
public class Position
{
    public float x, y, z;
}

[Serializable]
public class Rotation
{
    public float roll, pitch, yaw;
}

[Serializable]
public class ADASData
{
    public LDWStatus ldw;
    public ACCStatus acc;
    public AEBStatus aeb;
}
```

### Vehicle Controller

```csharp
public class VehicleController : MonoBehaviour
{
    public Transform vehicleTransform;
    public GameObject ldwWarningUI;
    public GameObject aebWarningUI;

    public void UpdateVehicle(SimulationState state)
    {
        // Update position
        vehicleTransform.position = new Vector3(
            state.vehicle.position.x,
            state.vehicle.position.z,  // Z is up in Unity
            state.vehicle.position.y
        );

        // Update rotation
        vehicleTransform.rotation = Quaternion.Euler(
            state.vehicle.rotation.pitch * Mathf.Rad2Deg,
            state.vehicle.rotation.yaw * Mathf.Rad2Deg,
            state.vehicle.rotation.roll * Mathf.Rad2Deg
        );

        // Update ADAS UI
        ldwWarningUI.SetActive(state.adas.ldw.warning_active);
        aebWarningUI.SetActive(state.adas.aeb.braking_active);
    }
}
```

### Sensor Visualization

```csharp
public class SensorVisualizer : MonoBehaviour
{
    public Material radarMaterial;
    public Material cameraM material;

    void DrawSensorFOV(SensorData sensor)
    {
        // Draw radar/camera field of view
        float range = sensor.max_range;
        float fov = sensor.fov_horizontal * Mathf.Rad2Deg;

        // Create cone mesh for FOV visualization
        var cone = CreateFOVCone(range, fov);
        Graphics.DrawMesh(cone, transform.localToWorldMatrix,
                         sensor.type == "radar" ? radarMaterial : cameraMaterial,
                         0);
    }
}
```

## Performance Considerations

### Frame Rate Matching

The SIL system runs at 100Hz by default. For Unity visualization at 60 FPS:

```csharp
// Buffer incoming messages
private Queue<SimulationState> stateBuffer = new Queue<SimulationState>();

void OnMessageReceived(SimulationState state)
{
    stateBuffer.Enqueue(state);

    // Keep buffer size reasonable
    while (stateBuffer.Count > 10)
    {
        stateBuffer.Dequeue();
    }
}

void Update()
{
    if (stateBuffer.Count > 0)
    {
        var state = stateBuffer.Dequeue();
        UpdateVehicle(state);
    }
}
```

### Interpolation

For smooth visualization, interpolate between states:

```csharp
private SimulationState currentState;
private SimulationState nextState;
private float interpolationProgress = 0f;

void Update()
{
    interpolationProgress += Time.deltaTime / expectedUpdateInterval;

    if (interpolationProgress >= 1f && stateBuffer.Count > 0)
    {
        currentState = nextState;
        nextState = stateBuffer.Dequeue();
        interpolationProgress = 0f;
    }

    // Interpolate position and rotation
    vehicleTransform.position = Vector3.Lerp(
        ToUnityPosition(currentState.vehicle.position),
        ToUnityPosition(nextState.vehicle.position),
        interpolationProgress
    );
}
```

## Environment Setup

### Required Unity Packages

1. **WebSocket Sharp**: For WebSocket communication
   - Available on GitHub: https://github.com/sta/websocket-sharp
   - Or use Unity Asset Store alternatives

2. **JSON.NET**: For JSON parsing
   - Unity Package Manager: `com.unity.nuget.newtonsoft-json`

### Required Unreal Plugins

1. **WebSockets Plugin** (built-in)
2. **JSON Utilities** (built-in)

## Troubleshooting

### Connection Issues

```csharp
// Add connection retry logic
IEnumerator RetryConnection()
{
    int retries = 0;
    while (!ws.IsAlive && retries < 5)
    {
        yield return new WaitForSeconds(2f);
        Debug.Log($"Retry attempt {retries + 1}...");
        ws.Connect();
        retries++;
    }
}
```

### Message Parsing Errors

```csharp
try
{
    var data = JsonConvert.DeserializeObject<SimulationState>(message);
    UpdateVehicle(data);
}
catch (Exception e)
{
    Debug.LogError($"Failed to parse message: {e.Message}");
    Debug.LogError($"Message content: {message}");
}
```

## Example Unity Project Structure

```
UnityProject/
├── Assets/
│   ├── Scripts/
│   │   ├── ADASSILClient.cs
│   │   ├── VehicleController.cs
│   │   ├── SensorVisualizer.cs
│   │   └── ADASUIController.cs
│   ├── Prefabs/
│   │   ├── EgoVehicle.prefab
│   │   └── SensorFOV.prefab
│   └── Materials/
│       ├── RadarFOV.mat
│       └── CameraFOV.mat
```

## Next Steps

1. Implement vehicle model and physics proxy in Unity
2. Create sensor visualization overlays
3. Build ADAS status dashboard UI
4. Add environment rendering (roads, traffic, etc.)
5. Implement replay functionality for saved simulations

For more information, see the main README.md and example scenarios.
