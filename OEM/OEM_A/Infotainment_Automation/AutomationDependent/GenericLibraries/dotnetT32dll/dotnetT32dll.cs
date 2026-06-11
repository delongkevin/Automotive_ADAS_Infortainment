using System;
using System.Diagnostics;
using System.Text;
using Vector.CANoe.Threading;

namespace dotnetT32dllLib
{
    /// <summary>
    /// Public static class containing methods callable from CAPL.
    /// Call from CAPL using: dotnetT32dllLib::dotnetT32dllHelper::MethodName(args)
    /// </summary>
    public class dotnetT32dllHelper
    {
        // Maximum time to wait for T32_API.exe to exit.
        // If the process does not exit within this window it is killed and the
        // call returns a failure code.  The caller (CAPL) reports a FAIL step
        // and the operator re-runs the test case – there is no automatic retry.
        private const int T32_PROCESS_TIMEOUT_MS = 5000;

        /// <summary>
        /// Test function that outputs a greeting message via out parameter.
        /// CAPL calls this and receives the string in the out parameter.
        /// </summary>
        /// <param name="message">Output: A greeting message string</param>
        public static void TestWriteMessage(out string message)
        {
            message = "dotnetT32dll: Hello from .NET! TestWriteMessage() was called successfully.";
        }

        /// <summary>
        /// Test function that formats a custom message.
        /// </summary>
        /// <param name="inputMessage">The input message</param>
        /// <param name="outputMessage">Output: The formatted message</param>
        public static void TestWriteCustomMessage(string inputMessage, out string outputMessage)
        {
            outputMessage = $"dotnetT32dll: {inputMessage}";
        }

        /// <summary>
        /// Simple test function that returns a value to verify DLL is working.
        /// </summary>
        /// <param name="a">First integer</param>
        /// <param name="b">Second integer</param>
        /// <returns>Sum of a and b</returns>
        public static int TestAdd(int a, int b)
        {
            return a + b;
        }

        /// <summary>
        /// Function demonstrating Execution.Wait usage from Vector.CANoe.Threading.
        /// Waits for the specified number of milliseconds.
        /// </summary>
        /// <param name="milliseconds">Time to wait in milliseconds</param>
        public static void WaitMs(int milliseconds)
        {
            Execution.Wait(milliseconds);
        }

        #region T32 Execution Wrappers

        // -----------------------------------------------------------------------
        // Internal helper: run T32_API.exe synchronously on the calling thread.
        // stdout and stderr are read asynchronously via events to prevent the
        // ReadToEnd() deadlock that occurs when both pipes fill their OS buffers
        // before the process exits.  A hard timeout kills the process if it does
        // not exit within T32_PROCESS_TIMEOUT_MS to prevent CANoe from hanging.
        //
        // No path pre-validation is performed: exePath is passed directly to
        // ProcessStartInfo.FileName, which accepts both absolute and relative
        // paths.  Relative paths are resolved by the OS relative to the process
        // working directory (CANoe's working directory, typically the bench
        // configuration folder).  WorkingDirectory is intentionally left unset
        // so that CANoe manages process context via its .NET 8.0 backend.
        // There is NO retry: if the process fails the caller receives a non-zero
        // exit code and the CAPL test step is marked FAIL.
        // -----------------------------------------------------------------------
        private static int RunT32cmdCore(string exePath, string command,
                                         out string message, int[] exitCode)
        {
            string outputMessage = "";
            string errorMessage  = "";
            int processExitCode  = -1;

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName               = exePath,
                    Arguments              = command,
                    // WorkingDirectory is intentionally not set: the process
                    // inherits CANoe's working directory so that relative paths
                    // such as "../AutomationDependent/GenericLibraries/T32_API.exe"
                    // are resolved correctly by the OS.  CANoe manages the
                    // .NET 8.0 execution context via Execution.WaitForTask.
                    UseShellExecute        = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError  = true,
                    CreateNoWindow         = true
                };

                using (Process process = new Process())
                {
                    process.StartInfo = psi;

                    // Async event handlers prevent the stdout/stderr deadlock.
                    StringBuilder sbOut = new StringBuilder();
                    StringBuilder sbErr = new StringBuilder();
                    process.OutputDataReceived += (s, e) => { if (e.Data != null) sbOut.AppendLine(e.Data); };
                    process.ErrorDataReceived  += (s, e) => { if (e.Data != null) sbErr.AppendLine(e.Data); };

                    process.Start();
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();

                    bool exited = process.WaitForExit(T32_PROCESS_TIMEOUT_MS);
                    if (!exited)
                    {
                        // Process hung – kill it and report failure.
                        // The caller propagates this as a FAIL test step.
                        try { process.Kill(); } catch { /* ignore – process may have just exited */ }
                        errorMessage    = $"T32_API.exe did not exit within {T32_PROCESS_TIMEOUT_MS} ms and was killed.";
                        processExitCode = -2;
                    }
                    else
                    {
                        // Call WaitForExit() without a timeout a second time to
                        // flush any remaining async output-read callbacks before
                        // we read the StringBuilders.
                        process.WaitForExit();
                        processExitCode = process.ExitCode;
                        outputMessage   = sbOut.ToString().Trim();
                        errorMessage    = sbErr.ToString().Trim();
                    }
                }
            }
            catch (Exception ex)
            {
                errorMessage    = $"Exception: {ex.Message}";
                processExitCode = -1;
            }

            message = !string.IsNullOrEmpty(errorMessage) ? errorMessage : outputMessage;

            if (exitCode != null && exitCode.Length > 0)
                exitCode[0] = processExitCode;

            return (processExitCode == 0 || processExitCode == 259) ? 0 : -1;
        }

        /// <summary>
        /// Blocking execution of T32_API.exe.
        /// WARNING: May cause CANoe realtime kernel overruns if the command is slow.
        /// Prefer RunT32cmdNonBlocking for production use.
        /// </summary>
        /// <param name="exePath">Path to T32_API.exe</param>
        /// <param name="command">Command string to send to T32</param>
        /// <param name="message">Output: Response message from T32_API.exe</param>
        /// <param name="exitCode">Output array for exit code (long[] in CAPL)</param>
        /// <returns>0 on success, negative value on failure</returns>
        public static int RunT32cmdBlocking(string exePath, string command,
                                            out string message, int[] exitCode)
        {
            return RunT32cmdCore(exePath, command, out message, exitCode);
        }

        /// <summary>
        /// Non-blocking execution of T32_API.exe using Execution.WaitForTask.
        /// Yields to CANoe's realtime kernel during execution to prevent overruns.
        /// </summary>
        /// <param name="exePath">Path to T32_API.exe</param>
        /// <param name="command">Command string to send to T32</param>
        /// <param name="message">Output: Response message from T32_API.exe</param>
        /// <param name="exitCode">Output array for exit code (long[] in CAPL)</param>
        /// <returns>0 on success, negative value on failure</returns>
        public static int RunT32cmdNonBlocking(string exePath, string command,
                                               out string message, int[] exitCode)
        {
            string capturedMessage = "";
            int    capturedExit    = -1;

            // Temporary array so the lambda can write the exit code.
            int[] innerExitCode = new int[1] { -1 };

            int waitResult = Execution.WaitForTask((TaskCancelToken tct) =>
            {
                string msg;
                int rc = RunT32cmdCore(exePath, command, out msg, innerExitCode);
                capturedMessage = msg;
                capturedExit    = rc;
                return (rc == 0) ? 1 : -1;
            });

            message = capturedMessage;

            if (exitCode != null && exitCode.Length > 0)
                exitCode[0] = innerExitCode[0];

            if (waitResult <= 0)
                return -1;

            return capturedExit;
        }

        #endregion
    }
}
