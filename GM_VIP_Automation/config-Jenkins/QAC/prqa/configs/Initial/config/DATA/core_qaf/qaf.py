import os, sys, inspect, platform, json
from ctypes import *

g_debug = False

def exit_success():
    """Exit with success (0)"""
    sys.exit(0)

def exit_error(code, cipFile=None):
    """Exit setting the error code and closing the CIP file if present."""
    if cipFile is not None:
        cipFile.close()
        os.remove(cipFile.name)

    sys.exit(code)

def debug(f_arg, *argv):
    """Internal use only"""
    if g_debug:
        sys.stdout.write('DEBUG: ')
        sys.stdout.write(f_arg)
        for arg in argv:
            sys.stdout.write(arg)
        sys.stdout.flush()

def write_pipe(pipeName, msg):
    """Internal use only"""
    if pipeName is not None:
        if pipeName.lower() == b'stderr' or pipeName.lower() == b'stdout':
            print((str(len(msg)).zfill(5)))
            print(msg)
        else:
            if platform.system() == "Windows":
                write_pipe_windows(pipeName, msg)
            else:
                write_pipe_linux(pipeName, msg)

def write_pipe_linux(pipeName, msg):
    """Internal use only"""
    if os.path.exists(pipeName):
        os.remove(pipeName)
    os.mkfifo(pipeName)
    fifo = open(pipeName, 'w')
    fifo.write(str(len(msg)).zfill(5))
    fifo.write(msg)
    fifo.close()

def write_pipe_windows(pipeName, msg):
    """Internal use only"""
    PIPE_ACCESS_OUTBOUND = 0x2

    PIPE_TYPE_BYTE = 0x0
    PIPE_READMODE_BYTE = 0x0
    PIPE_WAIT = 0x0

    INVALID_HANDLE_VALUE = -1

    ERROR_PIPE_CONNECTED = 535

    debug("Creating Named Pipe\n")
    hPipe = windll.kernel32.CreateNamedPipeA(   pipeName,
                                                PIPE_ACCESS_OUTBOUND,
                                                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                                                1,
                                                4096,
                                                0,
                                                5000,
                                                None
                                                )

    if (hPipe == INVALID_HANDLE_VALUE):
        print(windll.kernel32.GetLastError())

        debug("Error in creating Named Pipe :", str(windll.kernel32.GetLastError()), "\n")
        return

    debug("Connect Named Pipe...\n")
    fConnected = True if windll.kernel32.ConnectNamedPipe(hPipe, None) else windll.kernel32.GetLastError() == ERROR_PIPE_CONNECTED
    if not fConnected:
        debug("Failed to Connect\n")
        return
    debug("Connected\n")

    debug("Write Named Pipe Length...\n")
    local_msg = msg.encode("ascii", "ignore")
    msgLength = str(len(local_msg)).zfill(5).encode('ascii')
    cbWritten = c_ulong(0)
    fSuccess = windll.kernel32.WriteFile(   hPipe,
                                            c_char_p(msgLength),
                                            len(msgLength),
                                            byref(cbWritten),
                                            None
                                            )

    if ( (not fSuccess) or (len(msgLength) != cbWritten.value)):
        debug("Could not reply to the client's request from the pipe\n")
    else:
        debug("Number of bytes written:", str(cbWritten.value), "\n")

    debug("Write Named Pipe...\n")
    cbWritten = c_ulong(0)
    fSuccess = windll.kernel32.WriteFile(   hPipe,
                                            c_char_p(local_msg),
                                            len(local_msg),
                                            byref(cbWritten),
                                            None
                                            )

    if ( (not fSuccess) or (len(local_msg) != cbWritten.value)):
        debug("Could not reply to the client's request from the pipe\n")
    else:
        debug("Number of bytes written:", str(cbWritten.value), "\n")

    windll.kernel32.FlushFileBuffers(hPipe)
    windll.kernel32.DisconnectNamedPipe(hPipe)
    windll.kernel32.CloseHandle(hPipe)

class Cip:
    """
    A helper class that can be used by the CIP generation scripts.

    Routines are available to return commonly needed items such as
    Stub Directory, CCT Name etc. Additionally a return code and
    message can be propagated back to Framework and displayed in the CLI/GUI.
    """

    def __init__(self, scriptFile):
        if scriptFile is not None:
            self.currentFile = scriptFile

        if len(sys.argv) > 1:
            self.cctFile = sys.argv[1]
        else:
            self.cctFile = ""

        if len(sys.argv) > 2:
            self.pipe = sys.argv[2].encode('ascii')
        else:
            self.pipe = None

        self.isMaster = True
        if len(sys.argv) > 3:
            if sys.argv[3] == "False":
                self.isMaster = False

    def exit_error(self, code, msg, cipFile=None):
        """Exit with a return code and option message. Any existing CIP will the closed and deleted """
        if cipFile is not None:
            cipFile.close()
            os.remove(cipFile.name)

        if self.pipe is not None and len(msg) > 0:
            write_pipe(self.pipe, msg)

        sys.exit(code)

    def exit_success(self):
        """Exit with a return 0 - success. No msg sent back."""

        sys.exit(0)

    def fileName(self):
        """Return the script filename."""
        p = os.path.basename(self.filePath())
        return p

    def fileDir(self):
        """Return the script directory pathname."""
        p = os.path.dirname(os.path.abspath(self.filePath()))
        return p

    def filePath(self):
        """Return the pathname to the script file."""
        p = self.currentFile
        return p


    def cctFileName(self):
        """Return the CCT filename."""
        p = os.path.basename(self.cctFilePath())
        return p

    def cctDir(self):
        """Return the CCT directory pathname."""
        if self.isMaster:
            p = os.path.dirname(os.path.abspath(self.cctFilePath()))
        else:
            p = os.path.abspath(os.path.join(self.filePath(), "..", "..", "..", ".."))
        return p

    def cctFilePath(self):
        """Return the pathname to the CCT file."""
        p = self.cctFile
        return p


    def cipFileName(self):
        """Return the CIP filename."""
        p = os.path.splitext(self.cctFileName().strip())[0] + '.cip'
        return p

    def cipDir(self):
        """Return the CIP directory pathname."""
        if self.isMaster:
            p = os.path.join(self.configDir(), "cip")
            return p
        else:
            p = os.path.join(os.path.abspath(os.path.join(self.filePath(), "..", "..", "..", "..", "..")), "cip")
            return p

    def cipFilePath(self):
        """Return the pathname to the CIP file."""
        p = os.path.join(self.cipDir(), self.cipFileName())
        return p


    def cctParent(self):
        """Return the CCT parent directory pathname."""
        p = os.path.join(self.dataDir(), self.cctFileName().rstrip('.cct'))
        return p

    def dataDir(self):
        """Return the Data directory pathname."""
        p = os.path.join(self.cctDir(), "DATA")
        return p

    def configDir(self):
        """Return the Config directory pathname."""
        p = os.path.dirname(self.cctDir())
        return p

    def stubDir(self):
        """Return the Stub directory pathname."""
        p = os.path.join(self.cctParent(), "Stub")
        return p

    def scriptDir(self):
        """Return the script directory pathname."""
        p = os.path.join(self.cctParent(), "Script")
        return p

    def getForceIncludes(self, fiDir):
        """Return a sorted list of files to include.

        The sorting should ensure we get a consistent ordering of the files (os.listdir does not guarentee this).
        """
        files = os.listdir(fiDir)
        return files.sort()



class Cct:

    def __init__(self, cctFile):
        """Parse a CCT - throws if it cannot be read."""
        self.data = None
        self.body = []

        with open(cctFile) as file:
            inHeader = True
            headerString = ""
            for line in file:
                line = line.strip()
                if line:
                    if inHeader and line[0] == '*':
                        headerString += line[1:]
                    else:
                        inHeader = False
                        self.body.append(line)

            headerString = headerString[:headerString.rfind('}') + 1]
            self.data = json.loads(headerString)

    def header(self):
        """Return the JSON header of the CCT"""
        return self.data

    def body(self):
        """Return the CCT entries as a list"""
        return self.body
