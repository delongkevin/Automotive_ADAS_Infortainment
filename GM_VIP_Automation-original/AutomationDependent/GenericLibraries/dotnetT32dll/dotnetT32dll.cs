/*
 * dotnetT32dllHelper.cs
 *
 * .NET DLL for CANoe CAPL Integration
 *
 * This class provides static methods that can be called from CAPL scripts.
 * Methods must be:
 *   - public static
 *   - Return type: void, integer types, bool, or double
 *   - Parameters: integer types, bool, double, string, or 1D arrays of integer/double
 *
 * Created: 31.01.2026
 * Description: Helper functions callable from CAPL via #pragma netlibrary
 *
 * Note: For standalone CAPL-called DLLs, Vector.CANoe.Runtime.Output doesn't work.
 *       Return strings to CAPL and use write()/writeLineEx() there for Write Window output.
 *       Vector.CANoe.Threading.Execution.Wait() DOES work for timing.
 */

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

        /// <summary>
        /// Blocking execution of T32_API.exe using Process.Start.
        /// WARNING: Will cause CANoe realtime kernel overruns if T32 command takes too long or ran TOO quickly in succession.
        /// This function is provided to closer emulate existing CAPL dll.
        /// Use RunT32cmdNonBlocking for production use.
        /// </summary>
        /// <param name="exePath">Path to T32_API.exe</param>
        /// <param name="command">Command string to send to T32</param>
        /// <param name="message">Output: Response message from T32_API.exe</param>
        /// <param name="exitCode">Output array for exit code (long[] in CAPL)</param>
        /// <returns>0 on success, negative value on failure</returns>
        public static int RunT32cmdBlocking(string exePath, string command, out string message, int[] exitCode)
        {
            string outputMessage = "";
            string errorMessage = "";
            int processExitCode = -1;

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = exePath,
                    Arguments = command,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };

                using (Process process = new Process())
                {
                    process.StartInfo = psi;
                    process.Start();

                    outputMessage = process.StandardOutput.ReadToEnd();
                    errorMessage = process.StandardError.ReadToEnd();

                    process.WaitForExit();
                    processExitCode = process.ExitCode;
                }
            }
            catch (Exception ex)
            {
                errorMessage = $"Exception: {ex.Message}";
                processExitCode = -1;
            }

            message = !string.IsNullOrEmpty(errorMessage) ? errorMessage : outputMessage;

            if (exitCode != null && exitCode.Length > 0)
            {
                exitCode[0] = processExitCode;
            }

            return (processExitCode == 0 || processExitCode == 259) ? 0 : -1;
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
        public static int RunT32cmdNonBlocking(string exePath, string command, out string message, int[] exitCode)
        {
            string outputMessage = "";
            string errorMessage = "";
            int processExitCode = -1;

            int waitResult = Execution.WaitForTask((TaskCancelToken tct) =>
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo
                    {
                        FileName = exePath,
                        Arguments = command,
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true
                    };

                    using (Process process = new Process())
                    {
                        process.StartInfo = psi;
                        process.Start();

                        outputMessage = process.StandardOutput.ReadToEnd();
                        errorMessage = process.StandardError.ReadToEnd();

                        process.WaitForExit();
                        processExitCode = process.ExitCode;
                    }
                    return 1;
                }
                catch (Exception ex)
                {
                    errorMessage = $"Exception: {ex.Message}";
                    processExitCode = -1;
                    return -1;
                }
            });

            message = !string.IsNullOrEmpty(errorMessage) ? errorMessage : outputMessage;

            if (exitCode != null && exitCode.Length > 0)
            {
                exitCode[0] = processExitCode;
            }

            if (waitResult <= 0)
            {
                return -1;
            }

            return (processExitCode == 0 || processExitCode == 259) ? 0 : -1;
        }

        #endregion
    }
}
