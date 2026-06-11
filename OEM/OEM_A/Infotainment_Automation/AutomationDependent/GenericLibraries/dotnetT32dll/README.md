# dotnetT32dll - .NET DLL for CANoe CAPL Integration

This build provides a .NET 8.0 DLL that can be called from CAPL scripts in Vector CANoe.
.NET 8.0 is supported starting with CANoe v19.0.

## Overview

Per Vector CANoe documentation, CAPL can call functions from .NET DLLs that fulfill these requirements:
- Must be defined as `public` in a `public class`
- Must be `static`
- Must have a valid CAPL identifier as name
- Return type must be `void`, integer type, `bool`, or `double`
- Parameters must be integer types, `bool`, `double`, `string`, or 1D arrays of integer/double

## Project Structure

```
dotnetT32dll/
├── dotnetT32dll.csproj      # .NET 8.0 project file (x64)
├── dotnetT32dll.cs          # C# class with static methods
├── cdotnetT32dll.cin        # CAPL include file with wrapper functions
├── dotnetT32dll.dll         # Built .NET DLL (output)
├── Build-dotnetT32dll.ps1   # Build script
└── README.md                # This file
```

## Building

### Prerequisites
- .NET SDK 8.0 or higher
- Vector CANoe 19.0 or higher (for runtime execution)

### Build Steps

Run the build script `./Build-dotnetT32dll.ps1`

## Usage in CAPL

### Configuration

In your CAPL program, add:

```c
includes
{
    #include "path/to/cdotnetT32dll.cin"
}
```

### Calling Functions

**Using wrapper functions (recommended for readability):**
```c
// Write a test message to CANoe Write Window
dlldotnetT32dll_TestWriteMessage();

// Write a custom message
dlldotnetT32dll_TestWriteCustomMessage("Hello from CAPL!");

// Test addition
long result = dlldotnetT32dll_TestAdd(5, 3);  // Returns 8

// Wait using CANoe threading
dlldotnetT32dll_WaitMs(100);  // Wait 100ms

// Execute T32 command (non-blocking, recommended)
char msg[512];
long exitCode[1];
long result = dllRunT32cmdNonBlocking("C:\\T32\\T32_API.exe", "command", msg, exitCode);

// Execute T32 command (blocking, may cause RT overruns)
long result = dllRunT32cmdBlocking("C:\\T32\\T32_API.exe", "command", msg, exitCode);
```

**Calling .NET methods directly:**
```c
// Namespace::Class::Method format
char chMessage[512];
dotnetT32dllLib::dotnetT32dllHelper::TestWriteMessage(chMessage);

long result = dotnetT32dllLib::dotnetT32dllHelper::TestAdd(10, 20);
```

## Available Functions

| CAPL Wrapper                                              | .NET Method                                  | Description                                             |
|-----------------------------------------------------------|----------------------------------------------|---------------------------------------------------------|
| `dlldotnetT32dll_TestWriteMessage()`                      | `TestWriteMessage(out string)`               | Writes test message to Write Window                     |
| `dlldotnetT32dll_TestWriteCustomMessage(char[])`          | `TestWriteCustomMessage(string, out string)` | Writes custom message to Write Window                   |
| `dlldotnetT32dll_TestAdd(long, long)`                     | `TestAdd(int, int)`                          | Adds two integers, returns sum                          |
| `dlldotnetT32dll_WaitMs(long)`                            | `WaitMs(int)`                                | Waits specified milliseconds using CANoe threading      |
| `dllRunT32cmdBlocking(char[], char[], char[], long[])`    | `RunT32cmdBlocking(...)`                     | Blocking T32 execution (~60ms, may cause RT overruns)   |
| `dllRunT32cmdNonBlocking(char[], char[], char[], long[])` | `RunT32cmdNonBlocking(...)`                  | Non-blocking T32 execution (~75ms, yields to RT kernel) |

## Adding New Functions

1. Add new static method to `dotnetT32dll.cs`:
   ```csharp
   public static int MyNewFunction(string param1, int param2)
   {
       // For output to CAPL, use out parameter instead of Console.WriteLine
       return param2 * 2;
   }
   ```

2. Add wrapper function to `cdotnetT32dll.cin`:
   ```c
   long dlldotnetT32dll_MyNewFunction(char aParam1[], long aParam2)
   {
       return dotnetT32dllLib::dotnetT32dllHelper::MyNewFunction(aParam1, aParam2);
   }
   ```

3. Rebuild the DLL.

## Notes

- **Threading:** `Vector.CANoe.Threading.Execution.Wait()` and `WaitForTask()` work correctly for timing and non-blocking operations.
- **Performance:** First execution may be slower due to JIT compilation and assembly loading.
- **Platform:** DLL is built for x64 to match CANoe measurement setup. Change `PlatformTarget` in csproj for x86 if needed.

## Troubleshooting

### "Unknown symbol 'dotnetT32dllLib'" in CAPL (after .NET 8.0 recompile)
This is the most common error after switching from .NET Framework to .NET 8.0.
CANoe's `#pragma netlibrary` loads the DLL as a **native-hosted** .NET assembly and needs
`dotnetT32dll.runtimeconfig.json` alongside the DLL to bootstrap the .NET 8.0 runtime.

Ensure the `.csproj` contains:
```xml
<EnableDynamicLoading>true</EnableDynamicLoading>
```
Then rebuild. The build target and `Build-dotnetT32dll.ps1` will copy
`dotnetT32dll.runtimeconfig.json` and `dotnetT32dll.deps.json` to `controlLib\T32\`
alongside `dotnetT32dll.dll`. All three files must be present in the same directory.

### "Method not found in CAPL"
Ensure the DLL is properly referenced with `#pragma netlibrary("dotnetT32dll.dll")` and the DLL is in the search path.

### "Assembly load error"
Verify .NET 8.0 runtime is installed and the platform (x64/x86) matches your CANoe configuration.

### CANoe Realtime Overruns
Use `dllRunT32cmdNonBlocking()` instead of `dllRunT32cmdBlocking()`. The non-blocking version uses `Execution.WaitForTask()` to yield to CANoe's realtime kernel during process execution.
