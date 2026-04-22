// VectorCANoeThreading.cs
// =======================
// CI-only stub for the Vector.CANoe.Threading namespace.
//
// Provides minimal no-op / pass-through implementations of the types used
// by dotnetT32dll.cs so that the project compiles in a CI environment where
// a full Vector CANoe installation is not available.
//
// DO NOT deploy this stub to production test benches.  The real
// Vector.CANoe.Threading.dll from the Vector CANoe installation must be
// present at runtime; only this stub is swapped in during CI builds.

namespace Vector.CANoe.Threading
{
    /// <summary>Delegate type for tasks submitted to <see cref="Execution.WaitForTask"/>.</summary>
    public delegate int TaskDelegate(TaskCancelToken token);

    /// <summary>Token passed to a WaitForTask delegate (stub: no cancellation support).</summary>
    public class TaskCancelToken { }

    /// <summary>
    /// Provides static helpers for executing work that interacts with the
    /// CANoe realtime kernel (stub: executes synchronously without yielding).
    /// </summary>
    public static class Execution
    {
        /// <summary>Waits for the specified number of milliseconds (stub: no-op).</summary>
        public static void Wait(int milliseconds) { }

        /// <summary>
        /// Executes a task and returns its result (stub: calls synchronously).
        /// </summary>
        public static int WaitForTask(TaskDelegate task)
            => task(new TaskCancelToken());
    }
}
