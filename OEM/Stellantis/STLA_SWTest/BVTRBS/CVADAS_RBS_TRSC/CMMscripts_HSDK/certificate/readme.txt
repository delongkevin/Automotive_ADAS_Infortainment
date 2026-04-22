1. Read UID via UART then disconnect. The UID is the last 32 bytes/64 characters prior to the terminating 'C' characters.

2. Drop in UID into the appropriate field in the x509_debug.txt file.
   debugUID = FORMAT:HEX,OCT:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

2. Create certificate using command:
    openssl req -new -x509 -key smpk.pem -nodes -outform der –out debug_unlock_cert.bin -config x509_debug.txt -sha512

**smpk.pem is ~\packages\ti\build\makerules\k3_dev_mpk.pem renamed
