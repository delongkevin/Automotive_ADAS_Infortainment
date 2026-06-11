@echo off
REM ********************************************************************************************
REM  $Copyright: $
REM            MAGNA Electronics - C O N F I D E N T I A L
REM            This document in its entirety is CONFIDENTIAL and may not be
REM            disclosed, disseminated or distributed to parties outside MAGNA
REM            Electronics without written permission from MAGNA Electronics.
REM ********************************************************************************************
REM $Id: prepareTools.bat 1.6 2020/05/15 11:10:38CEST Adis Malkic (adismalk) draft  $
REM ********************************************************************************************
REM

echo.
echo ^+--------------------------------------------------^+
echo ^+               Powersupply OFF                    ^|
echo ^+--------------------------------------------------^+
echo.
Title Powersupply ON / OFF  

REM ******************************************
REM Install and update all the tools
REM ******************************************

REM TENMA | RELAY
if "%POWERSUPPLY_ENV_VAR%"=="" set POWERSUPPLY_ENV_VAR=TENMA
::C:\prjtools\python\ver_2.7.14_p9\python.exe %~dp0\powersupply.py -off
