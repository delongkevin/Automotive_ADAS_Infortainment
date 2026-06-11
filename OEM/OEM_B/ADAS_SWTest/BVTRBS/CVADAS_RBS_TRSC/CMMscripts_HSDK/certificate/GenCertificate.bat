@echo off


@echo Generating certificate make sure UID in x509_debug.txt matches your SoC
@echo off
openssl req -new -x509 -key smpk.pem -nodes -outform der -out flash_unlock_cert.bin -config x509_flash.txt -sha512

openssl req -new -x509 -key smpk.pem -nodes -outform der -out debug_unlock_cert.bin -config x509_debug.txt -sha512
